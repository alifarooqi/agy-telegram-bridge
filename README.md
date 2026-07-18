# Antigravity Telegram Bot Bridge

A robust Python application that bridges a Telegram Bot with the **Google Antigravity SDK**, allowing you to chat with and run tasks on your local Antigravity Agent running on your Mac directly from your Telegram mobile app.

Designed with open-source standards in mind, this project supports isolated multi-session conversations, session persistence across restarts, and strong safety controls to prevent unauthorized remote code execution.

---

## Features

- **Isolated Multi-Session Management**: Uses Telegram `chat_id` mappings to create separate stateful `google.antigravity.Conversation` instances for each user. Conversation state does not bleed between users.
- **Session Persistence**: Saves the mapping of Telegram chats to Antigravity conversation IDs in a local `sessions.json` file. Conversation history is automatically resumed when the bot restarts.
- **Selective Security Policy**: Denies all write tools and shell command execution by default, *except* for `git` commands (e.g., `git status`, `git diff`, `git add`, `git commit`). All read-only tools (like directory search and file viewing) and web search are fully allowed.
- **Access Control**: Rejects requests from unauthorized Telegram IDs using an strict verification layer configured in environmental variables.
- **Message Chunking**: Automatically splits and delivers response texts longer than Telegram's 4096-character limit.

---

## Architecture

- `config.py`: Loads environment configurations and builds the `LocalAgentConfig` with strict tool policies.
- `session_manager.py`: Manages the active agent instances, starts sessions on demand, and maintains local session persistence mapping.
- `bot.py`: Starts the async polling runtime using `python-telegram-bot`, intercepts incoming messages, enforces security checks, and routes prompts.
- `requirements.txt`: Project dependencies list.

---

## Installation & Setup

### 1. Prerequisites
- **macOS** (since Google Antigravity SDK builds run locally on macOS)
- **Python 3.10+**

### 2. Clone and Setup Environment
```bash
git clone https://github.com/yourusername/agy-telegram-bridge.git
cd agy-telegram-bridge

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Telegram Bot Setup
1. Message [@BotFather](https://t.me/BotFather) on Telegram and type `/newbot`.
2. Follow the prompts to name your bot and obtain the **HTTP API Token**.
3. Message [@userinfobot](https://t.me/userinfobot) to find your numeric Telegram **User ID**.

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Edit the `.env` file:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_TELEGRAM_USER_IDS=your_telegram_id_here
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## Running the Bot

Start the bot bridge by running:
```bash
python3 bot.py
```

### Telegram Bot Commands
- `/start`: Initializes the chat session and returns a greeting.
- `/reset`: Closes the current agent session, clears the local history cache, and starts a fresh conversation.

---

## Security Model & Customization

### Selective Safety Policies
To protect your Mac from malicious command execution while allowing the bot to perform helpful operations, we enforce a strict policy stack in `config.py`:
- `policy.deny_all()` blocks all tools by default.
- Read-only tools (`list_directory`, `search_directory`, `find_file`, `view_file`, `read_url_content`) are explicitly whitelisted.
- `search_web` is whitelisted for web search capability.
- `run_command` is selectively allowed **only** for `git` commands through a custom predicate check:
  ```python
  def _is_git_command(args: dict) -> bool:
      cmd_line = args.get("CommandLine", "").strip()
      return cmd_line == "git" or cmd_line.startswith("git ")
  ```

If you wish to allow other commands or disable these safety policies completely, modify the `policies` list inside `config.py`.

---

## License

This project is licensed under the Apache License 2.0. See the `LICENSE` file for details.
