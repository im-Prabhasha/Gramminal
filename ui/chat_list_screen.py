"""
Chat list screen with tabs, search, and live unread-count updates.

Tabs: All | Private | Groups | Channels
Search: Ctrl+K opens an inline search bar.
Navigation: Arrow keys + Enter, or type a number.
"""

from typing import List, Optional

from textual import work
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    ListView, ListItem, Static, Label, Input, Button,
)
from textual.worker import Worker, WorkerState

from models import ChatInfo, ChatType, MessageInfo
from config import MAX_CHAT_PREVIEW_LEN
from ui.widgets import ChatItem, StatusBar
from ui.app import (
    TelegramApp, NewMessageReceived, UnreadCountChanged,
    ConnectionStatusChanged,
)


class ChatListScreen(Screen):
    """Displays the user's dialog list with filtering and search."""

    # Active tab filter
    active_tab: reactive[str] = reactive("all")
    # Search query (empty = show all)
    search_query: reactive[str] = reactive("")
    # Whether we're currently loading
    loading: reactive[bool] = reactive(False)

    BINDINGS = [
        ("ctrl+k", "toggle_search", "Search"),
        ("escape", "escape_action", "Back"),
        ("tab", "next_tab", "Next tab"),
        ("shift+tab", "prev_tab", "Prev tab"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._all_chats: List[ChatInfo] = []
        self._filtered_chats: List[ChatInfo] = []
        self._search_visible: bool = False

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self):
        with Vertical(id="chat-list-root"):
            # Tab bar
            with Horizontal(id="tab-bar"):
                yield Button("All", id="tab-all", variant="primary")
                yield Button("Private", id="tab-private")
                yield Button("Groups", id="tab-group")
                yield Button("Channels", id="tab-channel")
                yield Label("Ctrl+K Search", id="search-hint")

            # Search input (hidden by default)
            yield Input(
                placeholder="Type to search chats…",
                id="chat-search",
                visible=False,
            )

            # Chat list
            yield ListView(id="chat-list")

            # Status bar
            yield StatusBar(id="status-bar")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self._update_tab_styles()
        self._load_dialogs()

    async def on_screen_resume(self) -> None:
        """When returning from chat view, refresh the list."""
        self._load_dialogs()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @work(exclusive=True, group="dialog_load")
    async def _load_dialogs(self) -> None:
        app: TelegramApp = self.app
        if not app.client:
            return

        self.loading = True
        try:
            self._all_chats = await app.client.get_dialogs()
            self._apply_filters()
        except Exception as exc:
            app.notify(f"Failed to load chats: {exc}", severity="error")
        finally:
            self.loading = False

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def _apply_filters(self) -> None:
        """Recompute ``_filtered_chats`` from ``_all_chats`` using current
        tab and search query, then rebuild the ListView."""
        chats = self._all_chats

        # Tab filter
        tab = self.active_tab
        if tab != "all":
            type_map = {
                "private": {ChatType.PRIVATE, ChatType.BOT},
                "group": {ChatType.GROUP},
                "channel": {ChatType.CHANNEL},
            }
            allowed = type_map.get(tab, set())
            chats = [c for c in chats if c.chat_type in allowed]

        # Search filter
        q = self.search_query.lower().strip()
        if q:
            chats = [c for c in chats if q in c.name.lower()]

        self._filtered_chats = chats
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        """Re-mount chat items in the ListView."""
        list_view = self.query_one("#chat-list", ListView)

        # Remember old index to preserve position
        old_index = list_view.index

        list_view.clear()
        for idx, chat in enumerate(self._filtered_chats):
            item = ListItem(
                ChatItem(index=idx + 1, chat=chat),
                id=f"chat-{chat.chat_id}",
            )
            list_view.mount(item)

        # Restore index if possible
        if 0 <= old_index < len(self._filtered_chats):
            list_view.index = old_index

        # Update status
        status = self.query_one("#status-bar", StatusBar)
        status.update(
            connection=self.app.connection_status,
            extra=f"{len(self._filtered_chats)} chats",
        )

    # ------------------------------------------------------------------
    # Tab handling
    # ------------------------------------------------------------------

    def _update_tab_styles(self) -> None:
        """Highlight the active tab button."""
        for tab_id in ("all", "private", "group", "channel"):
            btn = self.query_one(f"#tab-{tab_id}", Button)
            if tab_id == self.active_tab:
                btn.variant = "primary"
                btn.add_class("active-tab")
            else:
                btn.variant = "default"
                btn.remove_class("active-tab")

    def watch_active_tab(self, old: str, new: str) -> None:
        self._update_tab_styles()
        self._apply_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button
        if btn.id and btn.id.startswith("tab-"):
            self.active_tab = btn.id.replace("tab-", "")

    def action_next_tab(self) -> None:
        order = ["all", "private", "group", "channel"]
        idx = order.index(self.active_tab)
        self.active_tab = order[(idx + 1) % len(order)]

    def action_prev_tab(self) -> None:
        order = ["all", "private", "group", "channel"]
        idx = order.index(self.active_tab)
        self.active_tab = order[(idx - 1) % len(order)]

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def action_toggle_search(self) -> None:
        inp = self.query_one("#chat-search", Input)
        self._search_visible = not self._search_visible
        inp.visible = self._search_visible
        if self._search_visible:
            inp.focus()
            inp.value = ""
        else:
            inp.value = ""
            self.search_query = ""
            self.query_one("#chat-list", ListView).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "chat-search":
            self.search_query = event.value

    def watch_search_query(self, old: str, new: str) -> None:
        self._apply_filters()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item: ListItem = event.item
        chat_item: ChatItem = item.get_child_by_type(ChatItem)
        if chat_item:
            self.app.push_screen(ChatViewScreen(chat_item.chat))

    def on_key(self, event) -> None:
        # Number shortcut — only when search is not focused
        if self._search_visible:
            return
        if event.character and event.character.isdigit():
            idx = int(event.character) - 1
            list_view = self.query_one("#chat-list", ListView)
            if 0 <= idx < len(self._filtered_chats):
                list_view.index = idx
                list_view.focus()

    def action_escape_action(self) -> None:
        if self._search_visible:
            self.action_toggle_search()
        else:
            self.app.action_switch_account()

    # ------------------------------------------------------------------
    # Real-time updates
    # ------------------------------------------------------------------

    def on_new_message_received(self, event: NewMessageReceived) -> None:
        """A new message arrived — update the chat list entry."""
        msg: MessageInfo = event.message
        for chat in self._all_chats:
            if chat.chat_id == msg.chat_id:
                chat.last_message_text = msg.text or "[Media]"
                chat.last_message_date = msg.date
                chat.last_message_sender = msg.sender_name
                if chat.chat_id != self._get_current_chat_id():
                    chat.unread_count += 1
                # Move to top
                self._all_chats.remove(chat)
                self._all_chats.insert(0, chat)
                break
        self._apply_filters()

    def on_unread_count_changed(self, event: UnreadCountChanged) -> None:
        """Refresh dialog list to get accurate unread counts."""
        self._load_dialogs()

    def on_connection_status_changed(self, event: ConnectionStatusChanged) -> None:
        status = self.query_one("#status-bar", StatusBar)
        status.update(connection=event.status, extra=f"{len(self._filtered_chats)} chats")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_current_chat_id(self) -> Optional[int]:
        """If a ChatViewScreen is on the stack, return its chat_id."""
        for screen in self.app.screen_stack:
            if hasattr(screen, "chat_id"):
                return screen.chat_id
        return None
