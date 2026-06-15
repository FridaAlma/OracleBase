# Oracle — Autonomous AI Coding Agent

**Oracle** is an autonomous coding agent built on [Agno](https://github.com/agno-agi/agno), designed to read, write, edit, search, and execute code — all on its own.

> 🧠 It doesn't just follow instructions. It figures out what tools it needs, builds them on the fly, and gets the job done.

---

## ✨ What It Can Do

Out of the box, Oracle can:

- **Read** any file in your project
- **Write & edit** code atomically with surgical precision
- **Search** files with glob patterns and contents with regex
- **Run** arbitrary shell commands
- **Remember** your preferences and context across sessions
- **Create its own tools** on the fly — and reuse them later
- **Launch sub-agents** for complex, multi-step research

No tool for the job? Oracle builds one.

---

## 🏗️ Architecture

Oracle is delightfully simple: just Agno + a thin wrapper.

```
D:\Work\AGI\Oracle/
│
├── coding_agent.py        # Agent definition + FastAPI server + chat API
├── cli.py                 # Interactive CLI interface
├── chat.html              # Web chatbot UI
├── system_prompt.md       # Agent's system prompt (personality + rules)
├── oracle.bat             # Windows launcher (CLI or UI)
├── .env                   # Configuration (API key, model, server)
├── .env.example           # Template for .env
├── requirements.txt       # Python dependencies
└── coding_agent.db        # SQLite: sessions, agent memory
```

### What Agno Brings to the Table

| Component | Description |
|-----------|-------------|
| **`OpenAIChat`** | Drop-in integration with any OpenAI-compatible model (DeepSeek, GPT, etc.) |
| **`CodingTools`** | Native tools: `read`, `write`, `edit`, `search`, `grep`, `shell`, `task` |
| **`Workspace`** | Directory-level tools: `list`, `read`, `search`, `shell` |
| **`Agent`** | The master orchestrator — model + tools + memory + instructions |
| **`AgentOS`** | FastAPI server with built-in routing and tracing |
| **`SqliteDb`** | Persistent storage for sessions and agent memory |
| **Agentic Memory** | Cross-session memory for user preferences |

**Bottom line:** Agno is the engine. Oracle is the driver.

---

## 🚀 Getting Started

### 1. Clone the repo

```bash
git clone <repository-url>
cd D:\Work\AGI\Oracle
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Linux/Mac
```

Edit `.env` with your settings (see [Configuration](#configuration)).

---

## ⚙️ Configuration

Everything lives in `.env`:

```ini
# ── AI Model ──
MODEL_ID=deepseek-v4-flash        # Model to use
API_BASE_URL=https://api.deepseek.com/v1  # API endpoint
API_KEY=your-api-key-here          # Your DeepSeek API key
MAX_TOKENS=16384                   # Max tokens per response
REQUEST_TIMEOUT=120                # Request timeout in seconds

# ── FastAPI Server ──
HOST=127.0.0.1                     # Bind address
PORT=8000                          # Server port
```

---

## 🎮 Usage

Oracle comes with two interfaces: **Web UI** (default) and **CLI**.

### 🌐 Web UI (Chatbot)

A modern chatbot interface with real-time streaming. **This is the default mode.**

```bash
oracle.bat
```

What happens:
1. Launches the FastAPI server in a separate window
2. Opens your browser to `http://localhost:8000/ui`
3. Press Ctrl+C in the batch window to stop

Or manually:

```bash
python coding_agent.py --port 8000
```

Then open `http://localhost:8000/ui` in your browser.

**Web UI features:**
- Real-time response streaming (SSE)
- Rendered Markdown (code, tables, lists)
- Visual indicators during tool calls
- Automatic session management
- New conversation button
- Interruptible (stop button / Esc key)

### 💻 Interactive CLI

Start an interactive session with command history and multi-line support:

```bash
oracle.bat --cli
```

Or directly:

```bash
python cli.py
```

In the CLI:
- Type a prompt and press Enter
- **Paste multi-line code** — automatically detected (bracketed paste mode)
- `exit` or `quit` to leave
- `Ctrl+C` to interrupt

### ⚡ One-shot command

```bash
python cli.py "Create a README for this project"
```

### 🖥️ FastAPI Server (direct)

```bash
python coding_agent.py --port 8080
```

**Options:**
| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8000` | Server port |
| `--host` | `0.0.0.0` | Bind address |

### 🪟 Windows Launcher (`oracle.bat`)

| Command | Effect |
|---------|--------|
| `oracle.bat` | Launch Web UI (default) |
| `oracle.bat --cli` | Launch interactive CLI |
| `oracle.bat --port 8080` | Web UI on port 8080 |
| `oracle.bat --help` | Show help |

---

## 📁 Project Breakdown

### `coding_agent.py` — The Brains

The heart of the project. Defines the Oracle agent with:

- **AI Model**: DeepSeek (or any OpenAI-compatible model via `API_BASE_URL`)
- **Core Tools (Agno)**: `CodingTools` (read, write, edit, shell, task) and `Workspace` (file navigation)
- **Memory**: Persistent SQLite (`coding_agent.db`) + agentic memory
- **Context**: Last 3 conversations injected for continuity
- **FastAPI Server**: Endpoints at `/api/chat`, `/api/chat/stream` (SSE), `/api/chat/sessions`
- **Retry Logic**: Auto-retries on connection errors

### `cli.py` — The Terminal Companion

Interactive CLI with:
- **Persistent history** (`.cli_history` file)
- **Multi-line input** with automatic paste detection (bracketed paste mode)
- **Real-time streaming** responses

### `oracle.bat` — The One-Click Launcher

Batch script that:
1. Checks Python is installed
2. Verifies `.env` exists
3. Fires up Web UI or CLI
4. Cleans up browser and server on shutdown

### `system_prompt.md` — The Personality

Defines Oracle's persona, behavioral rules, and operating protocols:
- General behavior guidelines
- Software engineering workflow
- Code conventions
- Debugging and testing protocols
- **Tool creation mandate**: Oracle never says "I can't" — it builds what it needs

---

## 📋 Requirements

### Python Dependencies (`requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| `agno` | >=2.6.4 | AI agent framework |
| `python-dotenv` | >=1.1.1 | Environment variable loader |
| `httpx` | >=0.28.1 | HTTP client with configurable timeouts |
| `uvicorn` | >=0.40.0 | ASGI server for FastAPI |
| `openai` | >=1.0.0 | OpenAI-compatible API client |
| `sqlalchemy` | >=2.0.0 | ORM for database |
| `aiosqlite` | >=0.19.0 | Async SQLite |
| `fastapi` | >=0.100.0 | Web server for API |

---

## 🔒 Security Notes

- Your **API key** lives in `.env` — never share it
- Oracle won't modify files outside the project directory
- Potentially dangerous shell commands require confirmation

---

## 📄 License

MIT — for legitimate research and development purposes.

---

> *Crafted with care by Oracle 🤖*
