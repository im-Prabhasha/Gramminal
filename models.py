"""
Data models used throughout the application.

Pure dataclasses and enums — no framework dependencies here so that both
the Telethon layer and the Textual UI layer can import without coupling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ===================================================================
# Enums
# ===================================================================

class ChatType(Enum):
    """Kinds of Telegram conversations."""
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"
    BOT = "bot"


class MediaType(Enum):
    """Types of media attachments on a message."""
    NONE = "none"
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    STICKER = "sticker"
    ANIMATION = "animation"


class ConnectionStatus(Enum):
    """Connection-state machine for the status bar."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


# ===================================================================
# Data classes
# ===================================================================

@dataclass
class ChatInfo:
    """Metadata for a single dialog / chat."""
    chat_id: int
    name: str
    chat_type: ChatType
    unread_count: int = 0
    last_message_text: str = ""
    last_message_date: Optional[datetime] = None
    last_message_sender: str = ""


@dataclass
class MessageInfo:
    """A single message inside a chat."""
    message_id: int
    chat_id: int
    sender_id: int
    sender_name: str
    text: str
    date: datetime
    media_type: MediaType = MediaType.NONE
    media_size: int = 0
    media_filename: str = ""
    is_reply: bool = False
    reply_to_msg_id: Optional[int] = None
    is_forwarded: bool = False
    forward_from: str = ""


@dataclass
class SessionInfo:
    """Represents a discovered .session file on disk."""
    path: Path
    filename: str
    phone: Optional[str] = None
    name: Optional[str] = None
    is_valid: bool = False
    error: str = ""
