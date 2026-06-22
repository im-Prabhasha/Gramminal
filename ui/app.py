"""
Main Textual application class.

Owns the ``ClientManager`` and ``CacheManager`` instances, registers a
custom dark theme, and defines the custom message types used for
cross-screen communication.
"""

import logging
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.theme import Theme
from textual.worker import Worker, get_current_worker

from models import MessageInfo, ConnectionStatus
from client_manager import ClientManager
from config import API_ID, API_HASH
from ui.session_screen import SessionSelectScreen
from ui.chat_list_screen import ChatListScreen
from ui.chat_view_screen import ChatViewScreen

logger = logging.getLogger(__name__)

# ======================================================================
# Custom Textual messages (inter-screen communication bus)
# ======================================================================

class NewMessageReceived:
    """A new incoming message from Telethon."""
    def __init__(self, message: MessageInfo) -> None:
        self.message = message


class UnreadCountChanged:
    """Unread count for a chat needs refreshing."""
    def __init__(self, chat_id: int, count: int = -1) -> None:
        self.chat_id = chat_id
        # -1 means "unknown — re-fetch from API"
        self.count = count


class ConnectionStatusChanged:
    """Connection state transitioned."""
    def __init__(self, status: str) -> None:
        self.status = status


class DownloadProgress:
    """Media download progress update."""
    def __init__(self, progress: float = 0.0, status: str = "idle",
                 path: Optional[str] = None, error: Optional[str] = None) -> None:
        self.progress = progress
        self.status = status  # idle | downloading | completed | error
        self.path = path
        self.error = error


# ======================================================================
# Custom theme — Telegram-inspired dark palette
# ======================================================================

TELEGRAM_DARK = Theme(
    name="telegram_dark",
    primary="#7c8aff",
    secondary="#59c9ff",
    accent="#ff6b9d",
    background="#1a1a2e",
    surface="#16213e",
    panel="#0f3460",
    dark="#0a0a1a",
    success="#4ade80",
    warning="#fbbf24",
    error="#f87171",
    text="#e0e0e0",
    text_muted="#7a7a9a",
)


# ======================================================================
# Application
# ======================================================================

class TelegramApp(App):
    """
    Root Textual application.

    Lifecycle:
    1. Shows :class:`SessionSelectScreen` to pick an account.
    2. On selection, creates a :class:`ClientManager`, connects, then
       pushes :class:`ChatListScreen`.
    3. Opening a chat pushes :class:`ChatViewScreen`.
    4. ``Ctrl+A`` at any time returns to session selection.
    """

    # Use our custom theme and CSS
    CSS_PATH = str(Path(__file__).parent / "styles.tcss")
    TITLE = "Telegram Terminal"

    # Bindings available globally
    BINDINGS = [
        ("ctrl+a", "switch_account", "Switch account"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client: Optional[ClientManager] = None
        self.connection_status: str = "disconnected"

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.register_theme(TELEGRAM_DARK)
        self.theme = "telegram_dark"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_switch_account(self) -> None:
        """Return to the session-selection screen (disconnecting first)."""
        self._disconnect_client()
        self.push_screen(SessionSelectScreen())

    # ------------------------------------------------------------------
    # Client lifecycle helpers (called from screens)
    # ------------------------------------------------------------------

    async def connect_client(self, session_path: Path) -> bool:
        """
        Create a ClientManager for *session_path* and connect.

        Returns ``True`` on success.  On failure, shows a notification
        and returns ``False``.
        """
        # Validate API credentials early
        if not API_ID or not API_HASH:
            self.notify(
                "Set TG_API_ID and TG_API_HASH env vars (or in .env file)",
                severity="error",
                title="Missing API credentials",
            )
            return False

        try:
            self.client = ClientManager(session_path)

            # Wire callbacks → post Textual messages to the *current* screen
            self.client.on_connection_status = self._on_connection_status
            self.client.on_new_message = self._on_new_message
            self.client.on_unread_update = self._on_unread_update

            await self.client.connect()
            return True

        except PermissionError as exc:
            self.notify(str(exc), severity="error", title="Auth error")
        except Exception as exc:
            logger.exception("Connection failed")
            self.notify(str(exc), severity="error", title="Connection error")
        return False

    def _disconnect_client(self) -> None:
        if self.client:
            # Fire-and-forget disconnect in background to avoid blocking UI
            self.run_worker(self.client.disconnect, exclusive=False)
            self.client = None
        self.connection_status = "disconnected"

    # ------------------------------------------------------------------
    # Callback bridge: Telethon → Textual message bus
    # ------------------------------------------------------------------

    def _on_connection_status(self, status: str) -> None:
        self.connection_status = status
        self.screen.post_message(ConnectionStatusChanged(status))

    def _on_new_message(self, message: MessageInfo) -> None:
        try:
            self.screen.post_message(NewMessageReceived(message))
        except Exception:
            pass  # screen may be transitioning

    def _on_unread_update(self, chat_id: int, count: int) -> None:
        try:
            self.screen.post_message(UnreadCountChanged(chat_id, count))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Compose — start with session selection
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield SessionSelectScreen()
