"""
Local SQLite cache for chat metadata and message history.

Using ``aiosqlite`` so all database operations are non-blocking and
coexist happily with the Textual / Telethon async loops.

Each account gets its own database file to avoid data cross-contamination:
    ``cache/<session_name>_cache.db``
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiosqlite

from models import ChatInfo, ChatType, MessageInfo, MediaType

logger = logging.getLogger(__name__)


class CacheManager:
    """Async SQLite wrapper for offline message / chat storage."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Create (or open) the database and ensure schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.debug("Cache opened: %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id       INTEGER PRIMARY KEY,
                name          TEXT    NOT NULL,
                chat_type     TEXT    NOT NULL,
                unread_count  INTEGER DEFAULT 0,
                last_message_text    TEXT DEFAULT '',
                last_message_date    TEXT,
                last_message_sender  TEXT DEFAULT '',
                updated_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id      INTEGER NOT NULL,
                chat_id         INTEGER NOT NULL,
                sender_id       INTEGER,
                sender_name     TEXT    DEFAULT '',
                text            TEXT    DEFAULT '',
                date            TEXT    NOT NULL,
                media_type      TEXT    DEFAULT 'none',
                media_size      INTEGER DEFAULT 0,
                media_filename  TEXT    DEFAULT '',
                is_reply        INTEGER DEFAULT 0,
                reply_to_msg_id INTEGER,
                is_forwarded    INTEGER DEFAULT 0,
                forward_from    TEXT    DEFAULT '',
                PRIMARY KEY (message_id, chat_id)
            );

            CREATE INDEX IF NOT EXISTS idx_msgs_chat_date
                ON messages(chat_id, date);
            CREATE INDEX IF NOT EXISTS idx_msgs_chat_search
                ON messages(chat_id, text);
        """)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Chat operations
    # ------------------------------------------------------------------

    async def save_chats(self, chats: List[ChatInfo]) -> None:
        now = datetime.utcnow().isoformat()
        await self._db.executemany(
            """INSERT OR REPLACE INTO chats
               (chat_id, name, chat_type, unread_count,
                last_message_text, last_message_date,
                last_message_sender, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    c.chat_id, c.name, c.chat_type.value,
                    c.unread_count, c.last_message_text,
                    c.last_message_date.isoformat() if c.last_message_date else None,
                    c.last_message_sender, now,
                )
                for c in chats
            ],
        )
        await self._db.commit()

    async def get_chats(self) -> List[ChatInfo]:
        cursor = await self._db.execute(
            "SELECT * FROM chats ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        return [self._row_to_chat(r) for r in rows]

    # ------------------------------------------------------------------
    # Message operations
    # ------------------------------------------------------------------

    async def save_messages(self, messages: List[MessageInfo]) -> None:
        if not messages:
            return
        await self._db.executemany(
            """INSERT OR REPLACE INTO messages
               (message_id, chat_id, sender_id, sender_name,
                text, date, media_type, media_size, media_filename,
                is_reply, reply_to_msg_id, is_forwarded, forward_from)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    m.message_id, m.chat_id, m.sender_id, m.sender_name,
                    m.text, m.date.isoformat(),
                    m.media_type.value, m.media_size, m.media_filename,
                    int(m.is_reply), m.reply_to_msg_id,
                    int(m.is_forwarded), m.forward_from,
                )
                for m in messages
            ],
        )
        await self._db.commit()

    async def get_messages(
        self,
        chat_id: int,
        limit: int = 50,
        before_id: Optional[int] = None,
    ) -> List[MessageInfo]:
        """
        Return *limit* messages from *chat_id*, in chronological order.
        If *before_id* is given, only messages older than that ID are
        returned (for "load more" pagination).
        """
        if before_id is not None:
            sql = (
                "SELECT * FROM messages "
                "WHERE chat_id = ? AND message_id < ? "
                "ORDER BY message_id DESC LIMIT ?"
            )
            params: tuple = (chat_id, before_id, limit)
        else:
            sql = (
                "SELECT * FROM messages "
                "WHERE chat_id = ? "
                "ORDER BY message_id DESC LIMIT ?"
            )
            params = (chat_id, limit)

        cursor = await self._db.execute(sql, params)
        rows = await cursor.fetchall()
        # Reverse so oldest-first (chronological)
        return [self._row_to_message(r) for r in reversed(rows)]

    async def search_messages(
        self, chat_id: int, query: str, limit: int = 50
    ) -> List[MessageInfo]:
        """Case-insensitive LIKE search within a chat's cached messages."""
        sql = (
            "SELECT * FROM messages "
            "WHERE chat_id = ? AND text LIKE ? "
            "ORDER BY date DESC LIMIT ?"
        )
        cursor = await self._db.execute(sql, (chat_id, f"%{query}%", limit))
        rows = await cursor.fetchall()
        return [self._row_to_message(r) for r in reversed(rows)]

    async def get_message_count(self, chat_id: int) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) AS cnt FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0

    async def get_message_by_id(
        self, chat_id: int, message_id: int
    ) -> Optional[MessageInfo]:
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        )
        row = await cursor.fetchone()
        return self._row_to_message(row) if row else None

    # ------------------------------------------------------------------
    # Row → model converters
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_chat(row: aiosqlite.Row) -> ChatInfo:
        return ChatInfo(
            chat_id=row["chat_id"],
            name=row["name"],
            chat_type=ChatType(row["chat_type"]),
            unread_count=row["unread_count"],
            last_message_text=row["last_message_text"] or "",
            last_message_date=(
                datetime.fromisoformat(row["last_message_date"])
                if row["last_message_date"]
                else None
            ),
            last_message_sender=row["last_message_sender"] or "",
        )

    @staticmethod
    def _row_to_message(row: aiosqlite.Row) -> MessageInfo:
        return MessageInfo(
            message_id=row["message_id"],
            chat_id=row["chat_id"],
            sender_id=row["sender_id"] or 0,
            sender_name=row["sender_name"] or "Unknown",
            text=row["text"] or "",
            date=datetime.fromisoformat(row["date"]),
            media_type=MediaType(row["media_type"]),
            media_size=row["media_size"] or 0,
            media_filename=row["media_filename"] or "",
            is_reply=bool(row["is_reply"]),
            reply_to_msg_id=row["reply_to_msg_id"],
            is_forwarded=bool(row["is_forwarded"]),
            forward_from=row["forward_from"] or "",
        )
