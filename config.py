"""
Configuration constants for the Telegram terminal client.

All paths are configurable via environment variables.
API credentials MUST be set via TG_API_ID and TG_API_HASH.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so sibling imports work regardless
# of how the script is invoked (python main.py, python -m tg_terminal, etc.)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Load a simple .env file (no third-party dependency required).
# Each line: KEY=VALUE  (# comments and blank lines are ignored)
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> None:
    """Read KEY=VALUE pairs from *path* into ``os.environ`` (no overwrites)."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())

_load_env_file(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SESSION_DIR: Path = Path(os.getenv("TG_SESSION_DIR", "./sessions"))
CACHE_DIR: Path = Path(os.getenv("TG_CACHE_DIR", "./cache"))
DOWNLOAD_DIR: Path = Path(os.getenv("TG_DOWNLOAD_DIR", "./downloads"))

# ---------------------------------------------------------------------------
# Telegram API credentials (required)
# ---------------------------------------------------------------------------
API_ID: int = int(os.getenv("TG_API_ID", "0"))
API_HASH: str = os.getenv("TG_API_HASH", "")

# ---------------------------------------------------------------------------
# UI / pagination tuning
# ---------------------------------------------------------------------------
MAX_CHAT_PREVIEW_LEN: int = 60       # Characters shown for last-message preview
MESSAGES_PER_LOAD: int = 50          # Messages fetched per API / cache page
SEARCH_RESULT_LIMIT: int = 50        # Max search results returned
CHAT_LIST_PAGE: int = 500            # Max dialogs fetched from Telegram

# ---------------------------------------------------------------------------
# Ensure required directories exist at import time
# ---------------------------------------------------------------------------
SESSION_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_file_size(size_bytes: int) -> str:
    """Return a human-readable file size string (e.g. ``'2.4 MB'``)."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    size = float(size_bytes)
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    return f"{size:.1f} {units[idx]}"


def format_timestamp(dt) -> str:
    """
    Return a compact, Telegram-style timestamp.
    * Today          -> ``'14:32'``
    * Yesterday      -> ``'Yesterday'``
    * Same year      -> ``'Mar 15'``
    * Different year -> ``'Mar 15, 2023'``
    """
    from datetime import datetime, date

    if dt is None:
        return ""

    # Accept both datetime and date objects
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)

    now = datetime.now()
    today = now.date()
    msg_date = dt.date()

    if msg_date == today:
        return dt.strftime("%H:%M")
    if msg_date == today.replace(day=today.day - 1):
        return "Yesterday"
    if msg_date.year == today.year:
        return dt.strftime("%b %d")
    return dt.strftime("%b %d, %Y")


def media_type_icon(media_type: str) -> str:
    """Map a MediaType value to a Unicode icon."""
    icons = {
        "photo": "🖼  Photo",
        "video": "🎥 Video",
        "document": "📎 Document",
        "audio": "🎵 Audio",
        "voice": "🎤 Voice",
        "sticker": "🏷  Sticker",
        "animation": "🎞  GIF",
    }
    return icons.get(media_type, "📦 Media")
