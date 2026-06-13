import asyncio
import json
import logging
import os
import queue
import re
import sys
from pathlib import Path

from dotenv import load_dotenv


# ── Key words che attivano automaticamente il modello Pro ────────
_COMPLEXITY_KEYWORDS = {
    # OSINT / verifica
    "osint", "verifica", "verify", "scam", "truffa", "fraud",
    "cross-ref", "cross-reference", "fact-check", "factcheck",
    "confidence", "incongruity", "incongruenza", "pest",
    "triangulation", "triangolazione", "reputation",
    # Sicurezza
    "security", "vulnerability", "cve", "exploit", "threat",
    "malware", "phishing", "breach", "data leak",
    # Coding complesso
    "refactor", "architettura", "architecture", "design pattern",
    "multi-file", "codebase", "dependency", "migration",
    "optimization", "performance",
    # Analisi profonda
    "deep analysis", "approfondito", "comprehensive",
    "research", "ricerca", "investigation", "indagine",
    "report", "executive summary",
}

# ── Parole che indicano task semplice → rimani su Flash ──────────
_SIMPLE_KEYWORDS = {
    "hello", "hi", "ciao", "help", "aiuto",
    "typo", "format", "formatta",
}


def _detect_task_complexity(message: str) -> str:
    """Auto-detect: 'flash' o 'pro' in base al contenuto del messaggio."""
    msg_lower = message.lower()

    # Se ci sono keyword semplici E nessuna keyword complessa → flash
    has_simple = any(k in msg_lower for k in _SIMPLE_KEYWORDS)
    has_complex = any(k in msg_lower for k in _COMPLEXITY_KEYWORDS)

    if has_complex:
        return "pro"

    # Se il messaggio è molto lungo (>200 char) potrebbe essere complesso
    if len(message) > 200 and not has_simple:
        return "pro"

    return "flash"


class AgnoFilter(logging.Filter):
    """Mostra i log del framework, escludendo solo librerie rumorose."""
    def filter(self, record):
        name = record.name.lower()
        # Escludi solo librerie di rete/HTTP connesse
        noisy = ['httpx', 'uvicorn.access', 'httpcore', 'urllib3',
                 'charset_normalizer', 'asyncio']
        if any(n in name for n in noisy):
            return False
        msg = record.getMessage()
        # Escludi health check HTTP
        if '/health' in msg and 'HTTP' in msg:
            return False
        # Escludi messaggi di avvio uvicorn
        if 'uvicorn' in name and ('started' in msg.lower() or 'reload' in msg.lower()):
            return False
        return True


class SSELogHandler(logging.Handler):
    """Cattura i log del framework e li mette in coda per SSE."""
    def __init__(self, level=logging.INFO):
        super().__init__(level=level)
        self.log_queue = queue.Queue()
        self.addFilter(AgnoFilter())

    def emit(self, record):
        try:
            msg = self.format(record)
            if msg:
                self.log_queue.put_nowait(msg)
        except Exception:
            pass

    def get_pending(self):
        records = []
        while not self.log_queue.empty():
            try:
                records.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        return records

load_dotenv()

BASE_DIR = Path(__file__).parent.resolve()

# ── API Connectivity Check ──────────────────────────────────────
def _check_api_connectivity():
    api_key = os.getenv("API_KEY")
    base_url = os.getenv("API_BASE_URL", "https://api.deepseek.com/v1")
    model_id = os.getenv("MODEL_ID", "deepseek-v4-flash")

    if not api_key:
        print("[DIAG] API_KEY non impostata in .env — copia .env.example in .env")
        return

    import httpx
    print(f"[DIAG] Connessione a {base_url} ...", end=" ", flush=True)
    try:
        r = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
        )
        if r.status_code == 200:
            models = [m["id"] for m in r.json().get("data", [])]
            if model_id in models:
                print("OK")
            else:
                print(f"OK (modello '{model_id}' non in lista: {models[:3]})")
        else:
            print(f"HTTP {r.status_code}")
            msgs = {401: "API_KEY non valida o scaduta", 402: "Credito insufficiente",
                    404: "Endpoint errato, verifica API_BASE_URL"}
            print(f"      → {msgs.get(r.status_code, r.text[:120])}")
    except httpx.ConnectError:
        print("irraggiungibile")
        print(f"      → Verifica connessione Internet e API_BASE_URL in .env")
    except Exception as e:
        print(f"errore: {e}")


from agno.agent import Agent # type: ignore
from agno.models.openai import OpenAIChat # type: ignore
from agno.tools.coding import CodingTools # type: ignore
from agno.tools.workspace import Workspace # type: ignore
from agno.db.sqlite import SqliteDb # type: ignore
from agno.os import AgentOS # type: ignore

from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

# ── Tool Repository Bootstrap ─────────────────────────────────
try:
    sys.path.insert(0, str(BASE_DIR))
    from workspace.tool_repository import ToolRepository

    _tool_repo = ToolRepository()
    _repo_summary = _tool_repo.get_summary()
    if _repo_summary["total_tools"] > 0:
        print(f"[Oracle Bootstrap] Tool Repository: {_repo_summary['total_tools']} tool disponibili")
        _tool_repo.write_index()
except Exception as _e:
    print(f"[Oracle Bootstrap] Tool Repository init: {_e}")

# ── Tool Lifecycle Bootstrap ──────────────────────────────────
try:
    sys.path.insert(0, str(BASE_DIR))
    from workspace.tool_lifecycle import ToolLifecycleManager

    _lifecycle = ToolLifecycleManager()
    _orphans = _lifecycle.scan_and_register_orphans()
    if _orphans:
        print(f"[Oracle Bootstrap] Registrati {len(_orphans)} tool orfani (ex: {_orphans[0]})")
    _expired = _lifecycle.cleanup_expired()
    if _expired:
        print(f"[Oracle Bootstrap] Puliti {len(_expired)} tool scaduti")
except Exception as _e:
    print(f"[Oracle Bootstrap] Lifecycle init: {_e}")

import httpx

# ── HTTP Clients ────────────────────────────────────────────────
# Sync client per operazioni CLI (non usato per streaming)
_sync_http_client = httpx.Client(
    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=120.0),
    limits=httpx.Limits(max_keepalive_connections=3, max_connections=5),
)

# Async client per l'endpoint streaming SSE
_async_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(300.0, connect=60.0, read=300.0, write=120.0),
    limits=httpx.Limits(max_keepalive_connections=3, max_connections=5),
)

# ── Modello OpenAIChat ──────────────────────────────────────────
request_timeout = float(os.getenv("REQUEST_TIMEOUT", "300"))

_model_config = {
    "id": os.getenv("MODEL_ID", "deepseek-v4-flash"),
    "base_url": os.getenv("API_BASE_URL", "https://api.deepseek.com/v1"),
    "api_key": os.getenv("API_KEY"),
    "temperature": float(os.getenv("TEMPERATURE", "0.1")),
    "max_tokens": min(int(os.getenv("MAX_TOKENS", "16384")), 16384),
    "max_retries": int(os.getenv("MAX_RETRIES", "5")),
    "timeout": httpx.Timeout(request_timeout, connect=60.0, read=request_timeout, write=120.0),
    "http_client": _sync_http_client,
    "role_map": {"system": "system", "user": "user", "assistant": "assistant", "tool": "tool"},
}

model = OpenAIChat(**_model_config)

# ── Modello Pro per task complessi ──────────────────────────────
_model_pro_config = dict(_model_config)
_model_pro_config["id"] = os.getenv("MODEL_PRO_ID", "deepseek-v4-pro")
model_pro = OpenAIChat(**_model_pro_config)


def _select_model(tier: str, message: str = "") -> OpenAIChat:
    """Seleziona il modello in base al tier e al contenuto del messaggio.

    Args:
        tier: "flash", "pro", "auto" (default: da .env MODEL_TIER)
        message: testo della richiesta per auto-detection

    Returns:
        Istanza OpenAIChat appropriata.
    """
    effective_tier = tier or os.getenv("MODEL_TIER", "auto")

    if effective_tier == "pro":
        return model_pro
    if effective_tier == "flash":
        return model
    # auto: detection based on message content
    detected = _detect_task_complexity(message)
    return model_pro if detected == "pro" else model

# ── Diagnostic API ──────────────────────────────────────────────
_check_api_connectivity()

# ── Agent Factory ────────────────────────────────────────────────
_agent_kwargs = dict(
    description="Pure coding agent — reads, writes, edits, searches, and runs code.",
    instructions=(BASE_DIR / "system_prompt.md").read_text(encoding="utf-8").strip().split("\n"),
    tools=[
        CodingTools(
            base_dir=str(BASE_DIR),
            all=True,
            shell_timeout=120,
        ),
        Workspace(
            root=str(BASE_DIR),
            allowed=["read", "list", "search", "shell"],
        ),
    ],
    enable_agentic_memory=True,
    add_history_to_context=True,
    num_history_runs=3,
    markdown=True,
)

coding_agent = Agent(
    name="Oracle",
    model=model,
    db=SqliteDb(db_file=str(BASE_DIR / "coding_agent.db")),
    **_agent_kwargs,
)

coding_agent_pro = Agent(
    name="Oracle-Pro",
    model=model_pro,
    db=SqliteDb(db_file=str(BASE_DIR / "coding_agent.db")),
    **_agent_kwargs,
)


def _get_agent(tier: str = None, message: str = "") -> Agent:
    """Restituisce l'agente appropriato in base al tier e al messaggio."""
    selected = _select_model(tier, message)
    return coding_agent_pro if selected is model_pro else coding_agent

agent_os = AgentOS(
    agents=[coding_agent, coding_agent_pro],
    tracing=True,
)

app = agent_os.get_app()


# ── Model info ────────────────────────────────────────────────────
def _get_active_model_info(tier: str = None, message: str = "") -> dict:
    """Restituisce info sul modello attivo per una richiesta."""
    selected = _select_model(tier, message)
    is_pro = selected is model_pro
    model_id = os.getenv("MODEL_PRO_ID" if is_pro else "MODEL_ID", "deepseek-v4-flash")
    model_name = os.getenv("MODEL_PRO_NAME" if is_pro else "MODEL_NAME", "DeepSeek V4 Pro" if is_pro else "DeepSeek V4 Flash")
    effective_tier = tier or os.getenv("MODEL_TIER", "auto")
    return {
        "model_id": model_id,
        "model_name": model_name,
        "tier": "pro" if is_pro else "flash",
        "tier_mode": effective_tier,

    }


# ── Chat API Endpoints ─────────────────────────────────────────
@app.post("/api/chat")
async def chat_api(request: Request):
    """Endpoint chat non-streaming: POST {"message": "...", "session_id": "...", "model_tier": "auto|flash|pro"}"""
    body = await request.json()
    message = body.get("message", "")
    session_id = body.get("session_id", None)
    model_tier = body.get("model_tier", None)

    if not message.strip():
        return JSONResponse({"error": "Il messaggio non può essere vuoto"}, status_code=400)

    agent = _get_agent(model_tier, message)

    try:
        result = agent.run(message, session_id=session_id)
        return JSONResponse({
            "content": result.content if hasattr(result, "content") else str(result),
            "session_id": result.session_id if hasattr(result, "session_id") else session_id,
            "run_id": result.run_id if hasattr(result, "run_id") else None,
            "model": _get_active_model_info(model_tier, message),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/chat/stream")
async def chat_stream(message: str, session_id: str = None, model_tier: str = None, request: Request = None): # type: ignore
    """Endpoint chat con streaming SSE: GET /api/chat/stream?message=...&session_id=...&model_tier=auto|flash|pro"""

    async def event_generator():
        last_session_id = session_id
        last_run_id = None
        content_buffer = ""

        # Cattura i log del framework Agno via root logger + filtro
        # NOTA: il root logger ha default WARNING, ma i messaggi INFO dei tool
        # vengono emessi dai logger figli (che hanno livello proprio). Dobbiamo
        # abbassare il root logger a INFO per intercettarli.
        log_capture = SSELogHandler(logging.INFO)
        log_capture.setFormatter(logging.Formatter('%(message)s'))
        _root = logging.getLogger()
        _saved_root_level = _root.level
        _root.setLevel(logging.INFO)
        _root.addHandler(log_capture)

        def flush_logs():
            for rec in log_capture.get_pending():
                yield f"data: {json.dumps({'type': 'log', 'data': {'text': rec, 'type': 'info'}})}\n\n"

        # Seleziona il modello e invia info all'UI
        agent = _get_agent(model_tier, message)
        model_info = _get_active_model_info(model_tier, message)
        yield f"data: {json.dumps({'type': 'model', 'data': model_info})}\n\n"

        # Invia subito un evento start per far sparire i 3 puntini
        yield f"data: {json.dumps({'type': 'content', 'data': ''})}\n\n"

        try:
            stream = agent.arun(
                message,
                session_id=session_id,
                stream=True,
            )

            async for event in stream:
                if request and await request.is_disconnected():
                    break

                event_type = getattr(event, "event", "unknown")

                # Flush log del framework PRIMA di ogni evento
                for log_line in flush_logs():
                    yield log_line

                if event_type == "RunContent":
                    chunk = getattr(event, "content", "") or ""
                    if chunk:
                        content_buffer += chunk
                        yield f"data: {json.dumps({'type': 'content', 'data': chunk})}\n\n"

                elif event_type == "ToolCallStarted":
                    tool = getattr(event, "tool", None)
                    tool_name = tool.tool_name if tool else ""
                    if tool_name:
                        tool_args = ""
                        if tool:
                            raw_args = getattr(tool, "tool_args", None)
                            if raw_args:
                                tool_args = json.dumps(raw_args) if isinstance(raw_args, dict) else str(raw_args)
                            else:
                                tool_args = str(getattr(tool, "arguments", "") or getattr(tool, "args", "") or "")
                            if not tool_args:
                                tool_args = str(getattr(tool, "input", "") or getattr(tool, "query", "") or getattr(tool, "command", "") or "")
                        yield f"data: {json.dumps({'type': 'tool_start', 'data': {'name': tool_name, 'args': str(tool_args)[:500]}})}\n\n"
                        log_text = f"▶ {tool_name}"
                        log_detail = str(tool_args)[:200] if tool_args else ""
                        if log_detail:
                            log_text += f"  {log_detail}"
                        yield f"data: {json.dumps({'type': 'log', 'data': {'text': log_text, 'type': 'start'}})}\n\n"

                elif event_type == "ToolCallCompleted":
                    tool = getattr(event, "tool", None)
                    tool_name = tool.tool_name if tool else ""
                    if tool_name:
                        tool_result = ""
                        if tool:
                            tool_result = getattr(tool, "result", "") or getattr(tool, "output", "") or getattr(tool, "results", "") or ""
                            tool_result = str(tool_result)
                            if len(tool_result) > 300:
                                tool_result = tool_result[:300] + "..."
                        yield f"data: {json.dumps({'type': 'tool_end', 'data': {'name': tool_name, 'result': tool_result}})}\n\n"
                        log_text = f"✓ {tool_name}"
                        log_detail = tool_result[:200] if tool_result else ""
                        if log_detail:
                            log_text += f"  {log_detail}"
                        yield f"data: {json.dumps({'type': 'log', 'data': {'text': log_text, 'type': 'done'}})}\n\n"

                sid = getattr(event, "session_id", None)
                if sid:
                    last_session_id = sid
                rid = getattr(event, "run_id", None)
                if rid:
                    last_run_id = rid

                if event_type == "RunError":
                    error_msg = getattr(event, "content", "Errore sconosciuto") or "Errore sconosciuto"
                    yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
                    yield f"data: {json.dumps({'type': 'log', 'data': {'text': f'✗ {error_msg[:200]}', 'type': 'error'}})}\n\n"
                    break

                # Flush log anche DOPO ogni evento
                for log_line in flush_logs():
                    yield log_line

        except asyncio.CancelledError:
            pass
        except Exception as e:
            error_msg = str(e)
            yield f"data: {json.dumps({'type': 'log', 'data': {'text': f'⚠ {error_msg[:200]}', 'type': 'error'}})}\n\n"
            if "incomplete chunked read" in error_msg.lower() or "peer closed connection" in error_msg.lower():
                yield f"data: {json.dumps({'type': 'retry', 'data': 'Connessione interrotta, nuovo tentativo...'})}\n\n"
                try:
                    stream2 = agent.arun(message, session_id=session_id, stream=True)
                    async for event in stream2:
                        if request and await request.is_disconnected():
                            break
                        event_type = getattr(event, "event", "unknown")
                        for log_line in flush_logs():
                            yield log_line
                        if event_type == "RunContent":
                            chunk = getattr(event, "content", "") or ""
                            if chunk:
                                yield f"data: {json.dumps({'type': 'content', 'data': chunk})}\n\n"
                        elif event_type == "ToolCallStarted":
                            tool = getattr(event, "tool", None)
                            tool_name = tool.tool_name if tool else ""
                            if tool_name:
                                tool_args = ""
                                if tool:
                                    raw_args = getattr(tool, "tool_args", None)
                                    if raw_args:
                                        tool_args = json.dumps(raw_args) if isinstance(raw_args, dict) else str(raw_args)
                                    else:
                                        tool_args = str(getattr(tool, "arguments", "") or getattr(tool, "args", "") or "")
                                    if not tool_args:
                                        tool_args = str(getattr(tool, "input", "") or getattr(tool, "query", "") or getattr(tool, "command", "") or "")
                                yield f"data: {json.dumps({'type': 'tool_start', 'data': {'name': tool_name, 'args': str(tool_args)[:500]}})}\n\n"
                                log_text = f"▶ {tool_name}"
                                log_detail = str(tool_args)[:200] if tool_args else ""
                                if log_detail:
                                    log_text += f"  {log_detail}"
                                yield f"data: {json.dumps({'type': 'log', 'data': {'text': log_text, 'type': 'start'}})}\n\n"
                        elif event_type == "ToolCallCompleted":
                            tool = getattr(event, "tool", None)
                            tool_name = tool.tool_name if tool else ""
                            if tool_name:
                                tool_result = str(getattr(tool, "result", "") or getattr(tool, "output", "") or "")[:300]
                                yield f"data: {json.dumps({'type': 'tool_end', 'data': {'name': tool_name, 'result': tool_result}})}\n\n"
                                log_text = f"✓ {tool_name}"
                                log_detail = tool_result[:200] if tool_result else ""
                                if log_detail:
                                    log_text += f"  {log_detail}"
                                yield f"data: {json.dumps({'type': 'log', 'data': {'text': log_text, 'type': 'done'}})}\n\n"
                        elif event_type == "RunError":
                            error_msg2 = getattr(event, "content", "Errore sconosciuto") or "Errore sconosciuto"
                            yield f"data: {json.dumps({'type': 'error', 'data': error_msg2})}\n\n"
                            yield f"data: {json.dumps({'type': 'log', 'data': {'text': f'✗ {error_msg2[:200]}', 'type': 'error'}})}\n\n"
                            break
                        for log_line in flush_logs():
                            yield log_line
                        sid = getattr(event, "session_id", None)
                        if sid:
                            last_session_id = sid
                        rid = getattr(event, "run_id", None)
                        if rid:
                            last_run_id = rid
                except Exception as e2:
                    yield f"data: {json.dumps({'type': 'error', 'data': f'Errore dopo retry: {str(e2)}'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"
        finally:
            _root.removeHandler(log_capture)
            _root.setLevel(_saved_root_level)
            for log_line in flush_logs():
                yield log_line
            if last_session_id or last_run_id:
                yield f"data: {json.dumps({'type': 'done', 'session_id': last_session_id, 'run_id': last_run_id})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/model")
async def get_model_info():
    """Restituisce info sul modello corrente e sulla configurazione."""
    current_tier = os.getenv("MODEL_TIER", "auto")
    return JSONResponse({
        "flash": {
            "model_id": os.getenv("MODEL_ID", "deepseek-v4-flash"),
            "model_name": os.getenv("MODEL_NAME", "DeepSeek V4 Flash"),
            },
        "pro": {
            "model_id": os.getenv("MODEL_PRO_ID", "deepseek-v4-pro"),
            "model_name": os.getenv("MODEL_PRO_NAME", "DeepSeek V4 Pro"),
        },
        "current_tier": current_tier,
        "current": _get_active_model_info(),
    })


@app.get("/api/chat/sessions")
async def list_sessions(limit: int = 20):
    """Elenca le sessioni recenti."""
    try:
        sessions = coding_agent.get_sessions(limit=limit)
        result = []
        for s in (sessions or []):
            result.append({
                "session_id": getattr(s, "session_id", ""),
                "agent_id": getattr(s, "agent_id", ""),
                "created_at": str(getattr(s, "created_at", "")),
                "name": getattr(s, "name", ""),
            })
        return JSONResponse({"sessions": result})
    except Exception as e:
        return JSONResponse({"sessions": [], "error": str(e)})


# ─── Serve il file chat.html alla radice ────────────────────────
CHAT_HTML_PATH = BASE_DIR / "chat.html"


@app.get("/ui")
async def serve_chat_ui():
    if CHAT_HTML_PATH.exists():
        return FileResponse(str(CHAT_HTML_PATH))
    return JSONResponse({"error": "chat.html non trovato"}, status_code=404)


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Oracle - AI Coding Agent Server")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")),
                        help="Porta del server (default: %(default)s)")
    parser.add_argument("--host", type=str, default=os.getenv("HOST", "0.0.0.0"),
                        help="Host del server (default: %(default)s)")
    parser.add_argument("--model-tier", type=str, default=None,
                        choices=["auto", "flash", "pro"],
                        help="Forza un tier modello per tutte le richieste (default: dal .env)")
    parser.add_argument("--deep", action="store_true",
                        help="Scorciatoia per --model-tier=pro")
    args = parser.parse_args()

    if args.deep:
        args.model_tier = "pro"

    if args.model_tier:
        print(f"[Oracle] Model tier forzato: {args.model_tier}")
        os.environ["MODEL_TIER"] = args.model_tier

    uvicorn.run(app, host=args.host, port=args.port)
