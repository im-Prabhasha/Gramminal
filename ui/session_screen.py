"""
Session selection screen.

Discovers ``.session`` files, validates each one in parallel, and
presents a navigable list.  The user picks an account with arrow keys
or number input, then presses Enter to connect.
"""

from typing import List

from textual import work
from textual.screen import Screen
from textual.widgets import ListView, ListItem, Static, Label
from textual.containers import Vertical, Horizontal
from textual.worker import Worker, WorkerState

from models import SessionInfo
from session_manager import SessionManager
from ui.widgets import SessionItem
from ui.app import TelegramApp


class SessionSelectScreen(Screen):
    """Let the user choose which Telegram account to use."""

    BINDINGS = [
        ("escape", "app.quit", "Quit"),
    ]

    def compose(self):
        yield Vertical(
            Label("Telegram Terminal Client", id="title"),
            Label("Select an account to use", id="subtitle"),
            Static("Scanning sessions…", id="loading-hint"),
            ListView(id="session-list"),
            Label("↑↓ Navigate  |  Enter Select  |  Ctrl+Q Quit", id="footer"),
            id="session-container",
        )

    def on_mount(self) -> None:
        self._run_validation()

    @work(exclusive=True, group="session_scan")
    async def _run_validation(self) -> None:
        """Scan and validate all sessions in the background."""
        loading = self.query_one("#loading-hint", Static)
        list_view = self.query_one("#session-list", ListView)
        app: TelegramApp = self.app

        sessions: List[SessionInfo] = await SessionManager.validate_all()

        await list_view.remove_children()
        loading.visible = False

        if not sessions:
            loading.update(
                "No .session files found.\n"
                f"Place them in: {SessionManager.scan_sessions.__defaults__[0]}"
            )
            loading.visible = True
            return

        valid = [s for s in sessions if s.is_valid]
        invalid = [s for s in sessions if not s.is_valid]

        if not valid:
            lines = ["No valid sessions found."]
            for s in invalid:
                lines.append(f"  ✗ {s.filename}: {s.error}")
            loading.update("\n".join(lines))
            loading.visible = True
            return

        for idx, session in enumerate(valid):
            item = ListItem(
                SessionItem(index=idx + 1, session=session),
                id=f"session-{idx}",
            )
            await list_view.mount(item)

        # Show warnings for invalid sessions
        if invalid:
            warn_lines = ["⚠ Invalid sessions (skipped):"]
            for s in invalid:
                warn_lines.append(f"  {s.filename}: {s.error}")
            # We could log these; for now just log
            for line in warn_lines:
                app.log(line)

        # Focus the list so arrow keys work immediately
        list_view.focus()

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """User pressed Enter on a session item — connect."""
        item: ListItem = event.item
        session_item: SessionItem = item.get_child_by_type(SessionItem)
        if not session_item:
            return

        session: SessionInfo = session_item.session
        app: TelegramApp = self.app

        # Disable the list while connecting
        event.list_view.disabled = True

        async def _connect():
            success = await app.connect_client(session.path)
            if success:
                self.app.push_screen(ChatListScreen())
            else:
                event.list_view.disabled = False

        self.run_worker(_connect, exclusive=True)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle number-key shortcut: pressing a digit jumps to that item."""
        pass  # Number keys are handled in on_key below

    def on_key(self, event) -> None:
        """Allow typing a number to jump directly to a session."""
        if event.character and event.character.isdigit():
            idx = int(event.character) - 1
            list_view = self.query_one("#session-list", ListView)
            children = list_view.children
            if 0 <= idx < len(children):
                list_view.index = idx
                list_view.focus()
