"""
Session discovery and validation.

Scans the configured directory for ``.session`` files, then briefly
connects to Telegram with each one to retrieve the associated phone
number and display name.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyError,
    AuthKeyUnregisteredError,
    SessionPasswordNeededError,
)

from config import API_ID, API_HASH, SESSION_DIR
from models import SessionInfo

logger = logging.getLogger(__name__)


class SessionManager:
    """Find and validate Telegram ``.session`` files."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def scan_sessions(directory: Optional[Path] = None) -> List[Path]:
        """
        Return a list of ``.session`` file paths found in *directory*.

        Parameters
        ----------
        directory:
            Defaults to :pydata:`config.SESSION_DIR`.
        """
        directory = directory or SESSION_DIR
        if not directory.exists():
            logger.warning("Session directory does not exist: %s", directory)
            return []
        return sorted(directory.glob("*.session"))

    @staticmethod
    async def validate_session(session_path: Path) -> SessionInfo:
        """
        Connect to Telegram using *session_path* just long enough to
        determine whether the session is valid and, if so, retrieve the
        phone number and display name of the account.

        Returns a :class:`models.SessionInfo` with ``is_valid`` set
        appropriately.
        """
        info = SessionInfo(
            path=session_path,
            filename=session_path.stem,
        )

        client: Optional[TelegramClient] = None
        try:
            client = TelegramClient(
                str(session_path), API_ID, API_HASH,
                # Use a short timeout so we don't hang on bad sessions
                connect_timeout=10,
            )
            await asyncio.wait_for(client.connect(), timeout=15)

            if not await client.is_user_authorized():
                info.error = "Session not authorized (may need re-login)"
                return info

            me = await client.get_me()
            info.phone = me.phone
            info.name = _display_name(me)
            info.is_valid = True

        except (AuthKeyError, AuthKeyUnregisteredError) as exc:
            info.error = f"Auth key invalid/expired: {exc}"
        except SessionPasswordNeededError:
            info.error = "Two-factor auth required (not supported for auto-login)"
        except asyncio.TimeoutError:
            info.error = "Connection timed out"
        except Exception as exc:
            info.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Failed to validate session %s", session_path)
        finally:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        return info

    @staticmethod
    async def validate_all(directory: Optional[Path] = None) -> List[SessionInfo]:
        """Validate every ``.session`` file found in *directory*."""
        paths = SessionManager.scan_sessions(directory)
        tasks = [SessionManager.validate_session(p) for p in paths]
        return list(await asyncio.gather(*tasks))


# ===================================================================
# Internal helpers
# ===================================================================

def _display_name(user) -> str:
    """Build ``'First Last'`` or ``'@username'`` from a Telethon User."""
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(p for p in parts if p).strip()
    if not name and user.username:
        name = f"@{user.username}"
    return name or "Unknown"
