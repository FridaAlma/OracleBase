# Oracle — Autonomous AI Coding Agent

**Oracle** is an autonomous AI coding agent powered by [Agno](https://github.com/agno-agi/agno). It reads, writes, edits, searches, and executes code automatically through a CLI or a modern web chat interface.

---

## Features

- **Code manipulation** — Read, write, edit, search, and grep files in your project
- **Shell execution** — Run arbitrary commands with timeout control
- **Cross-session memory** — SQLite-backed persistent memory with agentic memory for user preferences
- **Dual model support** — Auto-detects task complexity and routes to a fast (Flash) or powerful (Pro) model
- **Web UI** — Modern chatbot interface with real-time streaming, Markdown rendering, and tool activity panel
- **Interactive CLI** — Rich CLI with multi-line paste support and command history
- **Sub-agents** — Launches sub-agents for complex parallel research tasks
- **Tool creation** — Dynamically builds missing tools, registers them, and reuses them across sessions
- **Vector memory** — ChromaDB-based semantic search with multimodal (text + image) support
- **FastAPI server** — REST API with streaming SSE endpoints for custom integrations

---

## Architecture

```
oracle/
├── coding_agent.py         # Agent definition + FastAPI server + SSE streaming
├── cli.py                  # Interactive CLI interface
├── chat.html               # Web chat UI (single-file HTML + JS)
├── system_prompt.md        # Agent system instructions
├── oracle.bat              # Windows launcher (CLI or UI)
├── .env                    # Configuration (API key, model, server)
├── .env.example            # Template for .env
├── requirements.txt        # Python dependencies
├── tools/
│   ├── vector_memory.py    # ChromaDB vector memory engine
│   └── multimodal_encoder.py # CLIP-based image/text encoder
└── workspace/
    ├── tool_repository.py  # Tool registry and search
    └── tool_lifecycle.py   # Tool lifecycle management (auto-cleanup)
```

### Built on Agno

| Component | Purpose |
|-----------|---------|
| **`OpenAIChat`** | Integration with OpenAI-compatible models (DeepSeek, GPT, etc.) |
| **`CodingTools`** | Native tools: `read`, `write`, `edit`, `search`, `grep`, `shell`, `task` |
| **`Workspace`** | Directory navigation tools: `list`, `read`, `search`, `shell` |
| **`Agent`** | Orchestrator: model + tools + memory + instructions |
| **`AgentOS`** | FastAPI server with routing and tracing |
| **`SqliteDb`** | Persistent session and memory storage |
| **Agentic Memory** | Cross-session memory for user preferences |

---

## Requirements

- Python 3.10+
- API key for an OpenAI-compatible provider (DeepSeek, OpenAI, etc.)

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `agno` | >=2.6.4 | AI agent framework |
| `fastapi` | >=0.100.0 | Web server |
| `uvicorn` | >=0.40.0 | ASGI server |
| `httpx` | >=0.28.1 | HTTP client |
| `openai` | >=1.0.0 | OpenAI-compatible API client |
| `sqlalchemy` | >=2.0.0 | ORM for database |
| `aiosqlite` | >=0.19.0 | Async SQLite |
| `chromadb` | >=1.5.0 | Vector database |
| `transformers` | >=4.30.0 | ML models (multimodal) |
| `torch` | >=2.0.0 | PyTorch (multimodal) |
| `Pillow` | >=10.0.0 | Image processing |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/oracle.git
cd oracle
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
# Windows
copy .env.example .env
# Linux/macOS
cp .env.example .env
```

Edit `.env` with your API key and preferences:

```ini
# Model configuration
MODEL_ID=deepseek-v4-flash
MODEL_PRO_ID=deepseek-v4-pro
MODEL_TIER=auto               # auto | flash | pro
API_BASE_URL=https://api.deepseek.com/v1
API_KEY=your-api-key-here
MAX_TOKENS=16384
REQUEST_TIMEOUT=300

# Server configuration
HOST=0.0.0.0
PORT=8000
```

---

## Usage

### Web UI (default)

Start the server and open the browser:

```bash
# Windows (launcher)
oracle.bat

# Or directly
python coding_agent.py --port 8000
```

Then open `http://localhost:8000/ui` in your browser.

**Web UI features:**
- Real-time response streaming (SSE)
- Markdown rendering (code blocks, tables, lists, images)
- Visual tool activity panel with live status
- Model tier toggle (Auto / Flash / Pro)
- Session management with persistent history
- Stop button to interrupt responses

### Interactive CLI

```bash
# Windows
oracle.bat --cli

# Or directly
python cli.py
```

CLI features:
- Persistent command history (`.cli_history`)
- Multi-line paste detection (bracketed paste mode)
- Real-time response streaming
- Auto-detection of task complexity for model selection

### Single command

```bash
python cli.py "Create a README for this project"
```

### Model tier flags

```bash
# Force high-quality model for all tasks
python cli.py --pro "Refactor the authentication module"

# Force fast/cheap model
python cli.py --flash "What does this function do?"

# Default auto-detect mode
python cli.py "Hello"
```

### Launcher options (`oracle.bat`)

| Command | Effect |
|---------|--------|
| `oracle.bat` | Start Web UI (default) |
| `oracle.bat --cli` | Start interactive CLI |
| `oracle.bat --pro` | Use Pro model |
| `oracle.bat --flash` | Use Flash model |
| `oracle.bat --port 8080` | Web UI on port 8080 |
| `oracle.bat --help` | Show help |

### API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Non-streaming chat |
| `/api/chat/stream` | GET | Streaming chat (SSE) |
| `/api/chat/sessions` | GET | List recent sessions |
| `/api/model` | GET | Current model info |
| `/ui` | GET | Web chat interface |

---

## How It Works

1. **Model selection** — Oracle auto-detects task complexity based on keywords and message length, routing simple queries to the Flash model and complex tasks (refactoring, security analysis, research) to the Pro model.

2. **Tool execution** — Using Agno's `CodingTools` and `Workspace`, Oracle reads, writes, edits, searches, and executes code within your project directory, with real-time feedback through the web UI.

3. **Memory & context** — Conversations are persisted to SQLite (`coding_agent.db`). The last 3 runs are automatically injected into context. Agentic memory remembers user preferences across sessions.

4. **Tool creation** — If a required tool doesn't exist, Oracle builds it on the fly, registers it in the tool repository, and can reuse it in future sessions. File lifecycle management ensures temporary files are cleaned up automatically.

5. **Vector memory** — For semantic search across knowledge, code, and project data, Oracle uses ChromaDB with optional multimodal (text + image) encoding via CLIP.

---

## Project Components

### `coding_agent.py`
Core agent definition with FastAPI server. Sets up the AI model, tools, memory, and SSE streaming endpoints. Supports retry logic for connection errors.

### `cli.py`
Interactive command-line interface with persistent history, multi-line paste support, and model tier selection.

### `chat.html`
Single-file web chat UI (~900 lines of HTML/CSS/JS) with dark theme, Markdown rendering, tool activity panel, image card previews, and real-time streaming.

### `system_prompt.md`
Detailed system instructions defining Oracle's personality, behavior rules, software engineering workflow, code conventions, tool management protocols, and dual-mode communication style.

### `oracle.bat`
Windows batch launcher that checks for Python and `.env`, starts the server in a separate window, opens the browser, and handles cleanup on shutdown.

### `tools/vector_memory.py`
ChromaDB-based vector database for semantic similarity search. Supports text and image queries with CLIP encoding.

### `workspace/tool_repository.py` / `tool_lifecycle.py`
Tool registry for discovering, promoting, and reusing tools. Lifecycle manager handles auto-classification and cleanup of volatile vs. persistent files.

---

## Configuration

All settings are in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_ID` | `deepseek-v4-flash` | Fast model ID |
| `MODEL_PRO_ID` | `deepseek-v4-pro` | High-quality model ID |
| `MODEL_TIER` | `auto` | Model selection mode |
| `API_BASE_URL` | `https://api.deepseek.com/v1` | API endpoint |
| `API_KEY` | — | Your API key |
| `MAX_TOKENS` | `16384` | Max response tokens |
| `REQUEST_TIMEOUT` | `300` | Timeout in seconds |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

---

## Safety Notes

- Your **API key** is stored in `.env` — never commit or share it
- Oracle does not modify files outside the project directory
- Dangerous shell commands require confirmation
- The agent operates within configured timeouts and boundaries

---

## License

MIT — for legitimate research and development purposes.
