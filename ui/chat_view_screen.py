"""
Chat message view screen.

Displays message history in a scrollable list, supports:
* Loading older messages on scroll-to-top.
* In-chat search (Ctrl+K).
* Media download (Ctrl+D on the highlighted message).
* Real-time incoming messages.
"""

from typing import List, Optional

from textual import work
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    ListView, ListItem, Static, Label, Input,
)
from textual.worker import Worker, WorkerState

from models import ChatInfo, MessageInfo, MediaType
from config import format_file_size, format_timestamp, media_type_icon
from ui.widgets import MessageItem, StatusBar
from ui.app import (
    TelegramApp, NewMessageReceived, UnreadCountChanged,
    ConnectionStatusChanged, DownloadProgress,
)


class ChatViewScreen(Screen):
    """Message history for a single chat."""

    # Currently highlighted message index (for Ctrl+D download)
    highlighted_msg_id: reactive[Optional[int]] = reactive(None)
    loading_more: reactive[bool] = reactive(False)

    BINDINGS = [
        ("ctrl+k", "toggle_search", "Search"),
        ("escape", "go_back", "Back to chats"),
        ("ctrl+d", "download_media", "Download media"),
    ]

    def __init__(self, chat: ChatInfo, **kwargs):
        super().__init__(**kwargs)
        self.chat = chat
        self.chat_id: int = chat.chat_id
        self.chat_name: str = chat.name
        self._messages: List[MessageInfo] = []
        self._oldest_id: Optional[int] = None
        self._search_visible: bool = False
        self._search_results: List[MessageInfo] = []
        self._search_index: int = 0

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self):
        with Vertical(id="chat-view-root"):
            # Header
            with Horizontal(id="chat-header"):
                yield Label("← Esc Back", id="back-hint")
                yield Label(self.chat_name, id="chat-title")
                yield Label("Ctrl+K Search", id="search-hint")

            # Search bar (hidden by default)
            with Horizontal(id="search-container", visible=False):
                yield Input(
                    placeholder="Search messages… (Enter to jump, Esc to close)",
                    id="msg-search",
                )
                yield Label("", id="search-result-count")

            # Message list
            yield ListView(id="message-list")

            # Status bar
            yield StatusBar(id="status-bar")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._load_initial_messages()

    # ------------------------------------------------------------------
    # Message loading
    # ------------------------------------------------------------------

    @work(exclusive=True, group="msg_load")
    async def _load_initial_messages(self) -> None:
        app: TelegramApp = self.app
        if not app.client:
            return

        # Try cache first for instant display, then fetch from API
        cached = await app.client.cache.get_messages(self.chat_id, limit=50)
        if cached:
            self._messages = cached
            self._oldest_id = cached[0].message_id
            self._rebuild_message_list(scroll_to="bottom")

        # Always fetch fresh from API
        fresh = await app.client.get_messages(self.chat_id, limit=50)
        if fresh:
            self._messages = fresh
            self._oldest_id = fresh[0].message_id
            self._rebuild_message_list(scroll_to="bottom")

        self._update_status()

    @work(exclusive=True, group="msg_load_more")
    async def _load_older_messages(self) -> None:
        if self.loading_more or self._oldest_id is None:
            return
        self.loading_more = True

        app: TelegramApp = self.app
        older = await app.client.get_messages(
            self.chat_id, limit=50, before_id=self._oldest_id
        )

        if older:
            self._messages = older + self._messages
            self._oldest_id = older[0].message_id
            # Rebuild and keep the highlight on the same message
            self._rebuild_message_list(scroll_to="keep")

        self.loading_more = False
        self._update_status()

    def _rebuild_message_list(self, scroll_to: str = "bottom") -> None:
        """
        Rebuild the ListView children from ``self._messages``.

        *scroll_to* can be ``"bottom"``, ``"top"``, or ``"keep"``
        (preserve the currently highlighted message).
        """
        list_view = self.query_one("#message-list", ListView)
        old_highlight_id = self.highlighted_msg_id

        list_view.clear()
        if not self._messages:
            list_view.mount(ListItem(Static("No messages yet.", id="empty-hint")))
            return

        for msg in self._messages:
            item = ListItem(
                MessageItem(message=msg),
                id=f"msg-{msg.message_id}",
            )
            list_view.mount(item)

        # Scroll behaviour
        if scroll_to == "bottom":
            list_view.scroll_end(animate=False)
            # Highlight the last message
            if self._messages:
                self.highlighted_msg_id = self._messages[-1].message_id
                list_view.index = len(self._messages) - 1
        elif scroll_to == "keep" and old_highlight_id:
            # Find the same message in the new list
            for idx, msg in enumerate(self._messages):
                if msg.message_id == old_highlight_id:
                    list_view.index = idx
                    list_view.scroll_to_widget(
                        list_view.children[idx], animate=False
                    )
                    break
        elif scroll_to == "top":
            list_view.scroll_home(animate=False)

    # ------------------------------------------------------------------
    # Navigation / highlight tracking
    # ------------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Track which message is currently highlighted."""
        item: ListItem = event.item
        msg_widget: MessageItem = item.get_child_by_type(MessageItem) if item else None
        if msg_widget:
            self.highlighted_msg_id = msg_widget.message.message_id
            self._update_status()

        # Load more when reaching the top
        if event.list_view.index == 0 and not self.loading_more:
            self._load_older_messages()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def action_toggle_search(self) -> None:
        container = self.query_one("#search-container", Horizontal)
        inp = self.query_one("#msg-search", Input)
        self._search_visible = not self._search_visible
        container.visible = self._search_visible
        if self._search_visible:
            inp.focus()
            inp.value = ""
            self.query_one("#search-result-count", Label).update("")
        else:
            inp.value = ""
            self._search_results = []
            self.query_one("#message-list", ListView).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the search bar — execute search and jump to result."""
        if event.input.id != "msg-search":
            return
        query = event.value.strip()
        if not query:
            return

        app: TelegramApp = self.app
        if not app.client:
            return

        async def _do_search():
            results = await app.client.search_messages(
                self.chat_id, query, limit=50
            )
            self._search_results = results
            count_label = self.query_one("#search-result-count", Label)
            count_label.update(f"{len(results)} results")
            if results:
                self._jump_to_message(results[0].message_id)

        self.run_worker(_do_search, exclusive=True)

    def _jump_to_message(self, message_id: int) -> None:
        """Scroll the message list to show *message_id*, loading context
        if the message isn't already in ``self._messages``."""
        for idx, msg in enumerate(self._messages):
            if msg.message_id == message_id:
                list_view = self.query_one("#message-list", ListView)
                list_view.index = idx
                list_view.scroll_to_widget(
                    list_view.children[idx], animate=False
                )
                return

        # Message not in current range — fetch around it
        self._fetch_around_message(message_id)

    @work(exclusive=True, group="msg_fetch_around")
    async def _fetch_around_message(self, message_id: int) -> None:
        app: TelegramApp = self.app
        if not app.client:
            return

        # Fetch 25 messages before and 25 after
        after = await app.client.get_messages(
            self.chat_id, limit=25, before_id=message_id
        )
        before_msgs = await app.client.get_messages(
            self.chat_id, limit=25, min_id=message_id
        )
        # The target message itself
        target = await app.client.get_messages(
            self.chat_id, ids=message_id
        )

        combined = after
        if target:
            combined = combined + [target] if not any(
                m.message_id == message_id for m in combined
            ) else combined
        combined = combined + before_msgs

        if combined:
            self._messages = combined
            self._oldest_id = combined[0].message_id
            self._rebuild_message_list(scroll_to="keep")
            # Find and highlight the target
            for idx, msg in enumerate(self._messages):
                if msg.message_id == message_id:
                    list_view = self.query_one("#message-list", ListView)
                    list_view.index = idx
                    list_view.scroll_to_widget(
                        list_view.children[idx], animate=False
                    )
                    break

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------

    def action_download_media(self) -> None:
        """Download media from the currently highlighted message."""
        if self.highlighted_msg_id is None:
            return

        # Find the message
        target_msg = None
        for msg in self._messages:
            if msg.message_id == self.highlighted_msg_id:
                target_msg = msg
                break

        if not target_msg or target_msg.media_type == MediaType.NONE:
            self.app.notify("No media on this message", severity="warning")
            return

        app: TelegramApp = self.app
        if not app.client:
            return

        self._update_status(download_status="downloading")

        async def _do_download():
            def progress(downloaded, total):
                # Runs in a thread — must use call_from_thread for UI
                pct = downloaded / total if total else 0
                app.call_from_thread(
                    lambda p=pct: self._update_status(
                        download_status=f"downloading {p:.0%}"
                    )
                )

            try:
                path = await app.client.download_media(
                    self.chat_id,
                    self.highlighted_msg_id,
                    progress_callback=progress,
                )
                if path:
                    app.call_from_thread(
                        lambda: self._update_status(
                            download_status=f"saved {path.name}"
                        )
                    )
                    app.call_from_thread(
                        lambda: app.notify(
                            f"Saved: {path}", title="Download complete"
                        )
                    )
                else:
                    app.call_from_thread(
                        lambda: self._update_status(download_status="failed")
                    )
            except Exception as exc:
                app.call_from_thread(
                    lambda: (
                        self._update_status(download_status="error"),
                        app.notify(str(exc), severity="error", title="Download failed"),
                    )
                )

        self.run_worker(_do_download, exclusive=True)

    # ------------------------------------------------------------------
    # Real-time updates
    # ------------------------------------------------------------------

    def on_new_message_received(self, event: NewMessageReceived) -> None:
        """Append a new message if it belongs to this chat."""
        msg: MessageInfo = event.message
        if msg.chat_id != self.chat_id:
            return

        # Avoid duplicates
        if any(m.message_id == msg.message_id for m in self._messages):
            return

        self._messages.append(msg)

        list_view = self.query_one("#message-list", ListView)
        item = ListItem(
            MessageItem(message=msg),
            id=f"msg-{msg.message_id}",
        )
        list_view.mount(item)

        # Auto-scroll to bottom
        list_view.scroll_end(animate=False)
        list_view.index = len(self._messages) - 1
        self.highlighted_msg_id = msg.message_id

    def on_connection_status_changed(self, event: ConnectionStatusChanged) -> None:
        self._update_status()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        if self._search_visible:
            self.action_toggle_search()
        else:
            self.app.pop_screen()

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _update_status(
        self,
        connection: Optional[str] = None,
        download_status: Optional[str] = None,
    ) -> None:
        bar = self.query_one("#status-bar", StatusBar)
        conn = connection or self.app.connection_status

        parts = []
        if self.highlighted_msg_id:
            # Show media info for the highlighted message
            for msg in self._messages:
                if msg.message_id == self.highlighted_msg_id:
                    if msg.media_type != MediaType.NONE:
                        size_str = format_file_size(msg.media_size)
                        parts.append(
                            f"{media_type_icon(msg.media_type.value)} ({size_str})"
                        )
                    break

        if download_status:
            parts.append(f"Download: {download_status}")

        parts.append(f"{len(self._messages)} messages")
        bar.update(connection=conn, extra="  |  ".join(parts) if parts else "")
