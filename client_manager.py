"""
High-level Telethon wrapper.

Provides async methods for fetching dialogs, messages, searching, and
downloading media.  All Telethon-specific error handling lives here so
the UI layer stays clean.

Callback hooks (``on_new_message``, ``on_unread_update``, etc.) are
plain callables set by the UI layer — this file never imports Textual.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from telethon import TelegramClient, events
from telethon.tl import types
from telethon.errors import (
    FloodWaitError,
    ChatAdminRequiredError,
    ChannelPrivateError,
)

from config import API_ID, API_HASH, CACHE_DIR, DOWNLOAD_DIR
from models import ChatInfo, ChatType, MessageInfo, MediaType
from cache_manager import CacheManager

logger = logging.getLogger(__name__)

# Type aliases for the callback hooks
NewMessageCallback = Optional[Callable[[MessageInfo], None]]
UnreadCallback = Optional[Callable[[int, int], None]]
StatusCallback = Optional[Callable[[str], None]]


class ClientManager:
    """
    Manages a single Telegram connection.

    Parameters
    ----------
    session_path:
        Path to the ``.session`` file.
    """

    def __init__(self, session_path: Path) -> None:
        self.session_path = session_path
        self.client = TelegramClient(
            str(session_path), API_ID, API_HASH,
            connect_timeout=15,
        )
        self.cache = CacheManager(
            CACHE_DIR / f"{session_path.stem}_cache.db"
        )
        self._me: Optional[types.User] = None

        # Callbacks — set by the UI before calling :meth:`connect`
        self.on_new_message: NewMessageCallback = None
        self.on_unread_update: UnreadCallback = None
        self.on_connection_status: StatusCallback = None

    # ==================================================================
    # Lifecycle
    # ==================================================================

    async def connect(self) -> None:
        """Connect, authorize, initialise cache, and register handlers."""
        self._emit_status("connecting")
        await self.client.connect()

        if not await self.client.is_user_authorized():
            raise PermissionError("Session is not authorized")

        self._me = await self.client.get_me()
        await self.cache.init()
        self._register_event_handlers()
        self._emit_status("connected")
        logger.info(
            "Connected as %s (%s)", self._display_name(self._me), self._me.phone
        )

    async def disconnect(self) -> None:
        """Gracefully shut down."""
        try:
            await self.client.disconnect()
        except Exception:
            pass
        await self.cache.close()
        self._emit_status("disconnected")

    @property
    def me(self) -> types.User:
        assert self._me, "Not connected"
        return self._me

    # ==================================================================
    # Dialogs (chat list)
    # ==================================================================

    async def get_dialogs(self) -> List[ChatInfo]:
        """
        Fetch the user's dialog list from Telegram and persist to cache.

        Handles ``FloodWaitError`` automatically.
        """
        chats: List[ChatInfo] = []
        try:
            async for dialog in self.client.iter_dialogs(limit=500):
                chats.append(self._parse_dialog(dialog))
        except FloodWaitError as exc:
            logger.warning("FloodWait on get_dialogs: waiting %ss", exc.seconds)
            import asyncio
            await asyncio.sleep(exc.seconds + 1)
            return await self.get_dialogs()  # retry once

        await self.cache.save_chats(chats)
        return chats

    # ==================================================================
    # Messages
    # ==================================================================

    async def get_messages(
        self,
        chat_id: int,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> List[MessageInfo]:
        """
        Fetch messages from Telegram, falling back to cache on error.

        Returns messages in **chronological** order (oldest first).
        """
        try:
            tg_messages = await self.client.get_messages(
                chat_id,
                limit=limit,
                min_id=before_id or 0,
            )
            # Telegram returns newest-first; reverse to chronological
            parsed = [self._parse_message(m) for m in reversed(tg_messages)]
            if parsed:
                await self.cache.save_messages(parsed)
            return parsed
        except FloodWaitError as exc:
            logger.warning("FloodWait on get_messages: %ss", exc.seconds)
            import asyncio
            await asyncio.sleep(exc.seconds + 1)
            return await self.cache.get_messages(chat_id, limit, before_id)
        except Exception as exc:
            logger.error("get_messages failed, using cache: %s", exc)
            return await self.cache.get_messages(chat_id, limit, before_id)

    async def search_messages(
        self, chat_id: int, query: str, limit: int = 50
    ) -> List[MessageInfo]:
        """Search messages on the Telegram server."""
        try:
            results = await self.client.get_messages(
                chat_id, search=query, limit=limit
            )
            parsed = [self._parse_message(m) for m in reversed(results)]
            if parsed:
                await self.cache.save_messages(parsed)
            return parsed
        except (FloodWaitError, ChannelPrivateError, ChatAdminRequiredError) as exc:
            logger.warning("Server search failed: %s — falling back to cache", exc)
            return await self.cache.search_messages(chat_id, query, limit)

    # ==================================================================
    # Media download
    # ==================================================================

    async def download_media(
        self,
        chat_id: int,
        message_id: int,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[Path]:
        """
        Download the media attached to *message_id* in *chat_id*.

        *progress_callback(downloaded, total)* is called from a
        download thread — use ``app.call_from_thread`` in the UI.
        """
        messages = await self.client.get_messages(chat_id, ids=message_id)
        if not messages or not messages[0].media:
            return None

        msg = messages[0]
        # Determine file name
        filename = self._media_filename(msg)
        save_path = DOWNLOAD_DIR / filename

        result = await self.client.download_media(
            msg,
            file=str(save_path),
            progress_callback=progress_callback,
        )
        return Path(result) if result else None

    # ==================================================================
    # Event handlers (real-time updates)
    # ==================================================================

    def _register_event_handlers(self) -> None:
        self.client.add_event_handler(
            self._handle_new_message, events.NewMessage(incoming=True)
        )
        self.client.add_event_handler(
            self._handle_unread, events.ReadHistoryInbox()
        )

    async def _handle_new_message(self, event: events.NewMessage.Event) -> None:
        msg_info = self._parse_message(event.message, chat_id=event.chat_id)
        await self.cache.save_messages([msg_info])
        if self.on_new_message:
            self.on_new_message(msg_info)

    async def _handle_unread(self, event: events.ReadHistoryInbox.Event) -> None:
        # event.max_id is the last read message; we can't easily derive
        # the exact unread count from this alone, so we re-fetch dialogs
        # on the next view.  For now just notify.
        if self.on_unread_update:
            self.on_unread_update(event.chat_id, -1)  # -1 = "unknown, refresh"

    # ==================================================================
    # Parsers — Telethon objects → our models
    # ==================================================================

    def _parse_dialog(self, dialog) -> ChatInfo:
        entity = dialog.entity
        chat_type = self._classify_entity(entity)

        last_msg = dialog.message
        last_text = ""
        last_date = None
        last_sender = ""
        if last_msg:
            last_text = last_msg.text or ""
            last_date = last_msg.date
            last_sender = self._sender_display(last_msg)

        return ChatInfo(
            chat_id=dialog.id,
            name=dialog.name or "Unknown",
            chat_type=chat_type,
            unread_count=dialog.unread_count,
            last_message_text=last_text,
            last_message_date=last_date,
            last_message_sender=last_sender,
        )

    def _parse_message(self, msg, chat_id: Optional[int] = None) -> MessageInfo:
        actual_chat_id = chat_id or (msg.chat_id if hasattr(msg, "chat_id") else 0)

        sender_name = self._sender_display(msg)
        media_type, media_size, media_filename = self._parse_media(msg.media)

        forward_from = ""
        is_forwarded = False
        if msg.forward:
            is_forwarded = True
            fwd = msg.forward
            forward_from = fwd.from_name or ""
            if not forward_from and fwd.from_id:
                if isinstance(fwd.from_id, types.PeerUser):
                    forward_from = f"User #{fwd.from_id.user_id}"
                else:
                    forward_from = "Forwarded"

        reply_to_id = None
        is_reply = False
        if msg.reply_to:
            is_reply = True
            reply_to_id = getattr(msg.reply_to, "reply_to_msg_id", None)

        return MessageInfo(
            message_id=msg.id,
            chat_id=actual_chat_id,
            sender_id=msg.sender_id or 0,
            sender_name=sender_name,
            text=msg.text or "",
            date=msg.date,
            media_type=media_type,
            media_size=media_size,
            media_filename=media_filename,
            is_reply=is_reply,
            reply_to_msg_id=reply_to_id,
            is_forwarded=is_forwarded,
            forward_from=forward_from,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_entity(entity) -> ChatType:
        if isinstance(entity, types.User):
            return ChatType.BOT if entity.bot else ChatType.PRIVATE
        if isinstance(entity, types.Chat):
            return ChatType.GROUP
        if isinstance(entity, types.Channel):
            return ChatType.CHANNEL
        return ChatType.PRIVATE

    def _sender_display(self, msg) -> str:
        """Best-effort sender name for a message."""
        if msg.out:
            return "You"
        sender = msg.sender
        if sender is None:
            return "Unknown"
        if isinstance(sender, types.User):
            return self._display_name(sender)
        if isinstance(sender, (types.Chat, types.Channel)):
            return sender.title or "Unknown"
        return "Unknown"

    @staticmethod
    def _display_name(user: types.User) -> str:
        parts = [user.first_name or "", user.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        if not name and user.username:
            name = f"@{user.username}"
        return name or "Deleted Account"

    @staticmethod
    def _parse_media(media) -> tuple:
        """Return ``(MediaType, size_bytes, filename)``."""
        if media is None:
            return MediaType.NONE, 0, ""

        if isinstance(media, types.MessageMediaPhoto):
            size = 0
            if media.photo and hasattr(media.photo, "sizes"):
                size = sum(
                    getattr(s, "size", 0)
                    for s in media.photo.sizes
                    if hasattr(s, "size")
                )
            return MediaType.PHOTO, size, "photo.jpg"

        if isinstance(media, types.MessageMediaDocument):
            doc = media.document
            if not isinstance(doc, types.Document):
                return MediaType.NONE, 0, ""

            fname = "file"
            for attr in doc.attributes:
                if isinstance(attr, types.DocumentAttributeFilename):
                    fname = attr.file_name
                    break

            mime = doc.mime_type or ""
            attrs = doc.attributes or []

            if any(isinstance(a, types.DocumentAttributeSticker) for a in attrs):
                return MediaType.STICKER, doc.size, fname
            if any(isinstance(a, types.DocumentAttributeAnimated) for a in attrs):
                return MediaType.ANIMATION, doc.size, fname
            if mime.startswith("video/"):
                return MediaType.VIDEO, doc.size, fname
            if any(
                isinstance(a, types.DocumentAttributeAudio) and a.voice
                for a in attrs
            ):
                return MediaType.VOICE, doc.size, fname
            if mime.startswith("audio/"):
                return MediaType.AUDIO, doc.size, fname
            return MediaType.DOCUMENT, doc.size, fname

        return MediaType.NONE, 0, ""

    @staticmethod
    def _media_filename(msg) -> str:
        """Determine a sensible local filename for a message's media."""
        if msg.media and isinstance(msg.media, types.MessageMediaDocument):
            doc = msg.media.document
            if isinstance(doc, types.Document):
                for attr in doc.attributes:
                    if isinstance(attr, types.DocumentAttributeFilename):
                        return attr.file_name
        return f"media_{msg.id}"

    def _emit_status(self, status: str) -> None:
        if self.on_connection_status:
            self.on_connection_status(status)
