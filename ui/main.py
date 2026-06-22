"""
Telegram Terminal Client — entry point.

Usage:
    1. Set environment variables (or create a .env file):
         TG_API_ID=12345
         TG_API_HASH=abcdef123456...
    2. Place .session files in the ./sessions/ directory.
    3. Run:  python main.py
"""

import logging
import sys

# Configure logging early so all modules benefit
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Import the Textual app
from ui.app import TelegramApp  # noqa: E402


def main() -> None:
    app = TelegramApp()
    app.run()


if __name__ == "__main__":
    main()
