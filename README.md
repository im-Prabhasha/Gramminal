How to use
1. Install dependencies:

bash

pip install -r requirements.txt
2. Set your Telegram API credentials (obtain from https://my.telegram.org):

bash

export TG_API_ID=12345678
export TG_API_HASH="your_api_hash_here"
Or create a .env file in the project root:

text

TG_API_ID=12345678
TG_API_HASH=your_api_hash_here
3. Place your .session files in the ./sessions/ directory (created automatically).

4. Run:

bash

python main.py
Keybindings summary
Key
Action
↑ / ↓	Navigate lists
Enter	Select / Open
0-9	Jump to item by number
Ctrl+K	Toggle search
Esc	Back / Close search
Ctrl+D	Download media (chat view)
Tab / Shift+Tab	Cycle chat tabs
Ctrl+A	Switch account
Ctrl+Q	Quit

Architecture notes
Zero UI imports in business logic — client_manager.py, cache_manager.py, and session_manager.py never import Textual. They communicate upward via plain Python callbacks.
Cross-screen messaging — The TelegramApp bridges Telethon callbacks into Textual's screen.post_message() system using the message classes defined in ui/app.py. Each screen handles only the messages it cares about via @on(MessageType) methods.
Cache-first loading — ChatViewScreen shows cached messages instantly, then fetches fresh data from Telegram in the background, ensuring fast perceived load times.
Thread-safe downloads — Telethon's download progress callback runs in a worker thread. The UI update is marshalled back to the main loop via app.call_from_thread().
Graceful error handling — FloodWait triggers automatic retry with the correct delay, expired sessions show clear errors and return to account selection, and network failures silently fall back to cache.
