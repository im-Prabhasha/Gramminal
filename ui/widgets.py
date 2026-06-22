"""
Reusable Textual widgets.

Each widget is a ``Static`` subclass that renders rich content using
the Rich ``Text`` class for inline colour/style control.
"""

from rich.text import Text
from textual.widgets import Static, ListView

from models import ChatInfo, MessageInfo, MediaType, SessionInfo, ConnectionStatus
from config import MAX_CHAT_PREVIEW_LEN, format_timestamp, format_file_size, media_type_icon


# ======================================================================
# Connection status icons
# ======================================================================

_STATUS_ICONS = {
    "connected": "[green]●[/green]",
    "connecting": "[yellow]●[/yellow]",
    "disconnected": "[red]●[/red]",
    "error": "[red]●[/red]",
}


# ======================================================================
# SessionItem — one row in the session-selection list
# ======================================================================

class SessionItem(Static):
    """Displays a single discovered session."""

    def __init__(self, index: int, session: SessionInfo, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self._index = index
        self._build()

    def _build(self) -> None:
        s = self.session
        text = Text()
        text.append(f"  {self._index}. ", style="bold dim")
        text.append("📱 ", style="")
        text.append(s.name or s.filename, style="bold cyan")
        if s.phone:
            text.append(f"  ({s.phone})", style="dim")
        if not s.is_valid:
            text.append(f"  [INVALID: {s.error}]", style="bold red")
        self.update(text)


# ======================================================================
# ChatItem — one row in the chat list
# ======================================================================

class ChatItem(Static):
    """Displays one dialog with name, preview, unread badge, and time."""

    def __init__(self, index: int, chat: ChatInfo, **kwargs):
        super().__init__(**kwargs)
        self.chat = chat
        self._index = index
        self._build()

    def _build(self) -> None:
        c = self.chat
        text = Text()

        # Index number
        text.append(f"{self._index:>3}. ", style="bold dim")

        # Chat name
        type_icons = {
            "private": "👤",
            "bot": "🤖",
            "group": "👥",
            "channel": "📢",
        }
        icon = type_icons.get(c.chat_type.value, "💬")
        text.append(f"{icon} ", style="")
        text.append(self._truncate(c.name, 30), style="bold")

        # Unread badge (right-aligned is tricky in Static, so pad)
        if c.unread_count > 0:
            badge = f"  [{c.unread_count}]"
            text.append(badge, style="bold on #7c8aff")

        # Time (right side)
        time_str = format_timestamp(c.last_message_date)
        if time_str:
            text.append(f"  {time_str:>12}", style="dim")

        # Second line: preview
        text.append("\n      ", style="")
        if c.last_message_sender:
            sender = self._truncate(c.last_message_sender, 15)
            text.append(f"{sender}: ", style="cyan")
        preview = self._truncate(c.last_message_text or "[No messages]", MAX_CHAT_PREVIEW_LEN)
        text.append(preview, style="dim")

        self.update(text)

    @staticmethod
    def _truncate(s: str, max_len: int) -> str:
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"


# ======================================================================
# MessageItem — one message bubble in the chat view
# ======================================================================

class MessageItem(Static):
    """Renders a single message with sender, time, text, and media info."""

    def __init__(self, message: MessageInfo, **kwargs):
        super().__init__(**kwargs)
        self.message = message
        self._build()

    def _build(self) -> None:
        m = self.message
        text = Text()

        # Forward header
        if m.is_forwarded and m.forward_from:
            text.append(f"  ↩ Forwarded from {m.forward_from}\n", style="italic yellow")

        # Reply header
        if m.is_reply and m.reply_to_msg_id:
            text.append(f"  ↰ Reply to #{m.reply_to_msg_id}\n", style="italic dim")

        # Sender + timestamp line
        if m.sender_name == "You":
            text.append(f"  {m.sender_name}", style="bold green")
        else:
            text.append(f"  {m.sender_name}", style="bold cyan")

        time_str = m.date.strftime("%H:%M") if m.date else ""
        text.append(f"    {time_str}", style="dim")

        # Message body
        if m.text:
            text.append("\n  ")
            text.append(m.text, style="")
            # Ensure trailing newline for spacing
            if not m.text.endswith("\n"):
                text.append("")

        # Media line
        if m.media_type != MediaType.NONE:
            text.append("  ")
            icon_str = media_type_icon(m.media_type.value)
            size_str = format_file_size(m.media_size)
            text.append(f"{icon_str}", style="bold #7c8aff")
            text.append(f" ({size_str})", style="dim")
            if m.media_filename:
                text.append(f" — {m.media_filename}", style="dim")
            text.append("  [Ctrl+D to download]", style="italic yellow")
            text.append("\n")

        self.update(text)


# ======================================================================
# StatusBar — bottom information bar
# ======================================================================

class StatusBar(Static):
    """Persistent status bar showing connection state and extra info."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.update(connection="disconnected", extra="")

    def update(self, connection: str = "", extra: str = "", **kwargs) -> None:  # type: ignore[override]
        icon = _STATUS_ICONS.get(connection, "[dim]●[/dim]")
        text = Text()
        text.append(f" {icon} ", style="")
        text.append(connection.capitalize(), style="bold" if connection == "connected" else "dim")
        if extra:
            text.append(f"  │  {extra}", style="dim")
        super().update(text)
