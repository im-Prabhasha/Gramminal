```markdown
# Telegram Terminal Client

A modern, lightweight Telegram client that runs entirely inside your terminal. Built with [Telethon](https://github.com/LonamiWebs/Telethon) and [Textual](https://github.com/Textualize/textual).

![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

- **Session-based auto-login** — drop in `.session` files and go; no phone/OTP prompts
- **Multi-account support** — switch between accounts with `Ctrl+A`
- **Categorized chat list** — tabs for All / Private / Groups / Channels
- **Full message history** — scrollable, paginated, with "load more" at the top
- **Real-time updates** — incoming messages appear live, unread counts refresh automatically
- **Search** — filter chats by name (`Ctrl+K`) or search messages within a chat
- **Media downloads** — see file size in the terminal, download with `Ctrl+D`
- **Local SQLite cache** — instant chat/message loading on repeat visits
- **Graceful error handling** — FloodWait auto-retry, expired session detection, offline cache fallback
- **Cross-platform** — works on Linux and Windows
- **Telegram-style keybindings** — `Ctrl+K` search, `Esc` back, `Tab` cycle tabs

---

## 📸 Screenshots

> *Screenshots will be added here. Run the client and take some!*

| Session Selection | Chat List | Chat View |
|---|---|---|
| *Coming soon* | *Coming soon* | *Coming soon* |

---

## 📦 Installation

### Prerequisites

- Python 3.9 or newer
- A Telegram API ID and API hash from [my.telegram.org](https://my.telegram.org/apps)
- At least one Telethon `.session` file

### Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/tg-terminal.git
cd tg-terminal
pip install -r requirements.txt
```

---

## ⚙️ Configuration

### API Credentials

Set your Telegram API credentials via environment variables:

```bash
export TG_API_ID=12345678
export TG_API_HASH="abcdef1234567890abcdef1234567890"
```

Or create a `.env` file in the project root:

```env
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890
```

### Session Files

Place your `.session` files in the `sessions/` directory (created automatically on first run). You can also customize the path:

```bash
export TG_SESSION_DIR=/path/to/your/sessions
```

### Optional Paths

| Variable | Default | Description |
|---|---|---|
| `TG_SESSION_DIR` | `./sessions` | Directory containing `.session` files |
| `TG_CACHE_DIR` | `./cache` | Local SQLite message cache |
| `TG_DOWNLOAD_DIR` | `./downloads` | Downloaded media files |

---

## 🚀 Usage

```bash
python main.py
```

### Flow

1. **Session Selection** — the app scans your session directory, validates each file, and shows a list of valid accounts. Select one with arrow keys or type a number and press `Enter`.
2. **Chat List** — all your dialogs appear grouped by tabs. Use `Tab` / `Shift+Tab` to switch categories, `Ctrl+K` to search, and `Enter` to open a chat.
3. **Chat View** — messages load from cache first (instant), then fresh data is fetched from Telegram. Scroll up to load older messages. Press `Esc` to return.
4. **Switch Account** — press `Ctrl+A` at any time to return to session selection.

---

## ⌨️ Keybindings

### Global

| Key | Action |
|---|---|
| `Ctrl+A` | Switch account |
| `Ctrl+Q` | Quit |

### Session Selection

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate sessions |
| `0`–`9` | Jump to session by number |
| `Enter` | Connect to selected session |
| `Esc` | Quit |

### Chat List

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate chats |
| `0`–`9` | Jump to chat by number |
| `Enter` | Open selected chat |
| `Tab` | Next tab (All → Private → Groups → Channels) |
| `Shift+Tab` | Previous tab |
| `Ctrl+K` | Toggle search bar |
| `Esc` | Close search / Switch account |

### Chat View

| Key | Action |
|---|---|
| `↑` / `↓` | Navigate messages |
| `Ctrl+D` | Download media on highlighted message |
| `Ctrl+K` | Toggle in-chat message search |
| `Enter` | Execute search (in search bar) |
| `Esc` | Close search / Back to chat list |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────┐
│                  main.py                     │
│               (entry point)                  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│              ui/app.py                       │
│   TelegramApp (Textual App)                  │
│   • Owns ClientManager                      │
│   • Bridges Telethon → Textual messages     │
│   • Custom message bus                      │
└──┬───────────────┬──────────────────────────┘
   │               │
   │  ┌────────────▼────────────┐
   │  │   client_manager.py     │
   │  │   • Telethon wrapper    │
   │  │   • Error handling      │
   │  │   • Event callbacks     │
   │  └────────────┬────────────┘
   │               │
   │  ┌────────────▼────────────┐
   │  │   cache_manager.py      │
   │  │   • aiosqlite wrapper   │
   │  │   • Chat & message CRUD │
   │  └─────────────────────────┘
   │
   │  ┌─────────────────────────────────────────┐
   │  │               ui/                        │
   │  │  ┌─────────────────┐  ┌───────────────┐  │
   │  │  │ session_screen  │  │ chat_list_    │  │
   │  │  │                 │  │ screen        │  │
   │  │  └─────────────────┘  └───────┬───────┘  │
   │  │                               │          │
   │  │  ┌─────────────────┐  ┌───────▼───────┐  │
   │  │  │ widgets.py      │  │ chat_view_    │  │
   │  │  │ • SessionItem   │  │ screen        │  │
   │  │  │ • ChatItem      │  │               │  │
   │  │  │ • MessageItem   │  │               │  │
   │  │  │ • StatusBar     │  │               │  │
   │  │  └─────────────────┘  └───────────────┘  │
   │  │                                         │
   │  │  ┌─────────────────┐                     │
   │  │  │ styles.tcss     │                     │
   │  │  └─────────────────┘                     │
   │  └─────────────────────────────────────────┘
   │
   ┌──────────────────────────────────┐
   │  session_manager.py              │
   │  • Scan & validate .session      │
   │  • Retrieve phone / display name │
   └──────────────────────────────────┘
   
   ┌──────────────────────────────────┐
   │  models.py                       │
   │  • ChatInfo, MessageInfo, etc.   │
   │  • Pure dataclasses, no deps     │
   └──────────────────────────────────┘
   
   ┌──────────────────────────────────┐
   │  config.py                       │
   │  • Paths, API creds, constants   │
   │  • .env loader, helpers          │
   └──────────────────────────────────┘
```

### Design Principles

- **No framework coupling in business logic** — `client_manager.py`, `cache_manager.py`, and `session_manager.py` never import Textual. They expose plain Python callbacks.
- **Message bus pattern** — Telethon events are converted to Textual messages (`NewMessageReceived`, `UnreadCountChanged`, etc.) in `app.py`, and each screen handles only what it needs.
- **Cache-first strategy** — messages load from SQLite instantly, then fresh data is fetched from Telegram in the background.
- **Thread-safe downloads** — Telethon's download progress runs in a worker thread; UI updates are marshalled via `app.call_from_thread()`.
- **Graceful degradation** — FloodWait triggers automatic retry, expired sessions show clear errors, network failures silently fall back to cache.

---

## 📁 Project Structure

```
tg-terminal/
├── main.py                 # Entry point
├── config.py               # Paths, API credentials, helpers
├── models.py               # Dataclasses (ChatInfo, MessageInfo, etc.)
├── session_manager.py      # Scan & validate .session files
├── client_manager.py       # Telethon wrapper, error handling
├── cache_manager.py        # aiosqlite cache layer
├── ui/
│   ├── __init__.py
│   ├── app.py              # Root Textual app, message bus, theme
│   ├── session_screen.py   # Account selection screen
│   ├── chat_list_screen.py # Dialog list with tabs & search
│   ├── chat_view_screen.py # Message history with search & download
│   ├── widgets.py          # Reusable Rich-rendered widgets
│   └── styles.tcss         # Textual CSS stylesheet
├── requirements.txt
└── README.md
```

---

## 🔧 How Session Files Work

This client does **not** ask for your phone number or OTP. It expects you to already have a Telethon `.session` file. You can generate one using the official Telethon script:

```bash
pip install telethon
python -c "
from telethon import TelegramClient
import getpass
api_id = int(input('API ID: '))
api_hash = input('API Hash: ')
phone = input('Phone: ')
client = TelegramClient(f'sessions/my_session', api_id, api_hash)
client.start(phone)
print('Session created successfully!')
client.disconnect()
"
```

Place the resulting `.session` file in the `sessions/` directory and the terminal client will pick it up automatically.

---

## 🛡 Error Handling

| Scenario | Behavior |
|---|---|
| Expired / invalid session | Shown as invalid in session list with error reason |
| Two-factor auth required | Marked as invalid (auto-login not supported for 2FA) |
| FloodWait | Automatically waits the required duration and retries |
| Network timeout | Falls back to cached data; shows error notification |
| Missing API credentials | Clear error notification on startup |
| Private channel access | Falls back to cache for search; error for new fetches |
| Download failure | Error notification with details; no crash |

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -am 'Add my feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

### Development tips

- Run with debug logging: `LOG_LEVEL=DEBUG python main.py`
- Clear cache: `rm -rf cache/`
- The `.env` file is gitignored — never commit credentials

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [Telethon](https://github.com/LonamiWebs/Telethon) — Async Telegram MTProto library
- [Textual](https://github.com/Textualize/textual) — Python TUI framework
- [Rich](https://github.com/Textualize/rich) — Terminal formatting engine
- [aiosqlite](https://github.com/omnilib/aiosqlite) — Async SQLite bindings
```

Replace `YOUR_USERNAME` in the clone URL with your actual GitHub username. You may also want to add a `LICENSE` file (e.g., `MIT`) to the root if you haven't already.
