#!/usr/bin/env bash
# Oracle - AI Coding Agent  (macOS / Linux)
set -o nounset

ORACLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ORACLE_DIR" || exit 1

# ─── Detect OS ────────────────────────────────────────────────────
case "$(uname -s)" in
    Darwin) BROWSER_CMD="open"  ;;
    Linux)  BROWSER_CMD="xdg-open" ;;
    *)
        echo "[ERRORE] OS non supportato: $(uname -s)" >&2
        exit 1
        ;;
esac

# ─── Parse arguments ──────────────────────────────────────────────
MODE="ui"
PORT=8000
MODEL_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cli)   MODE="cli"; shift ;;
        --ui)    MODE="ui"; shift ;;
        --port)  PORT="$2"; shift 2 ;;
        --deep)  MODEL_FLAG="--deep"; shift ;;
        --pro)   MODEL_FLAG="--model-tier pro"; shift ;;
        --flash) MODEL_FLAG="--model-tier flash"; shift ;;
        --help)  MODE="help"; shift ;;
        *)       shift ;;
    esac
done

# ─── Help ─────────────────────────────────────────────────────────
if [[ "$MODE" == "help" ]]; then
    echo "Oracle - AI Coding Agent"
    echo ""
    echo "Utilizzo:  ./oracle.sh [opzioni]"
    echo ""
    echo "Opzioni:"
    echo "  --cli          Avvia l'interfaccia a riga di comando (CLI)"
    echo "  --ui           Avvia l'interfaccia web (default)"
    echo "  --deep, --pro  Usa DeepSeek V4 Pro (massima qualita')"
    echo "  --flash        Usa DeepSeek V4 Flash (economico, default)"
    echo "  --port PORT    Usa una porta specifica (default: 8000)"
    echo "  --help         Mostra questo messaggio"
    echo ""
    echo "Esempi:"
    echo "  ./oracle.sh                  Avvia interfaccia web (Auto mode)"
    echo "  ./oracle.sh --deep           Avvia con DeepSeek V4 Pro"
    echo "  ./oracle.sh --cli --deep     Avvia CLI con DeepSeek V4 Pro"
    echo "  ./oracle.sh --port 8080      Avvia su porta 8080"
    exit 0
fi

# ─── Check Python ─────────────────────────────────────────────────
if ! command -v python &>/dev/null; then
    echo "[ERRORE] Python non trovato. Assicurati di aver installato Python e che sia nel PATH." >&2
    echo "         Scarica Python da: https://www.python.org/downloads/" >&2
    exit 1
fi

# ─── Check .env ───────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    echo "[AVVISO] File .env non trovato."
    echo "         Copia .env.example in .env e configura la tua API key."
    echo ""
    read -r -n1 -p "[C]ontinua comunque o [N]on uscire? (C/N) " answer
    echo >&2
    if [[ "${answer^^}" != "C" ]]; then
        exit 1
    fi
fi

# ─── CLI Mode ─────────────────────────────────────────────────────
if [[ "$MODE" == "cli" ]]; then
    echo ""
    echo "  |  Oracle CLI - AI Coding Agent"
    if [[ "$MODEL_FLAG" == "--deep" ]]; then
        echo "  |  Modalita' PRO (DeepSeek V4 Pro)"
    fi
    echo "  |  Scrivi 'exit' o premi Ctrl+C per uscire"
    echo ""
    # shellcheck disable=SC2086
    python cli.py $MODEL_FLAG
    EXIT_CODE=$?
    if [[ $EXIT_CODE -ne 0 ]]; then
        echo ""
        echo "[ERRORE] Oracle si e' chiuso con codice $EXIT_CODE" >&2
    fi
    exit "$EXIT_CODE"
fi

# ─── UI Mode ──────────────────────────────────────────────────────
echo ""
echo "  |  Oracle - AI Coding Agent"
if [[ "$MODEL_FLAG" == "--deep" ]]; then
    echo "  |  Modalita' PRO (DeepSeek V4 Pro)"
fi
echo "  |  Server in avvio su http://localhost:$PORT"
echo "  |  Premi Ctrl+C per fermare tutto"
echo ""

# Installa dipendenze mancanti per il modulo chat (solo primo avvio)
pip install httpx fastapi uvicorn python-multipart -q 2>/dev/null || true

# ─── Cleanup handler ──────────────────────────────────────────────
SERVER_PID=""

cleanup() {
    echo ""
    echo "Arresto in corso..."

    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "Fermo il server..."
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        echo "Server arrestato."
    fi

    exit 0
}

trap cleanup SIGINT SIGTERM

# Avvia il server in background
# shellcheck disable=SC2086
python coding_agent.py --port "$PORT" $MODEL_FLAG &
SERVER_PID=$!

# Aspetta che il server sia pronto
echo "Attendendo l'avvio del server..."
while true; do
    sleep 2
    python -c "import urllib.request; urllib.request.urlopen('http://localhost:$PORT/health')" 2>/dev/null && break
    echo ". Server non ancora pronto, aspetto..."
done

# Apri il browser
echo "Server pronto! Apro il browser..."
$BROWSER_CMD "http://localhost:$PORT/ui" 2>/dev/null || true

echo ""
echo " ┌─────────────────────────────────────────────────────────────┐"
echo " │  Oracle e' in esecuzione su http://localhost:$PORT/ui          │"
if [[ "$MODEL_FLAG" == "--deep" ]]; then
    echo " │  MODALITA' PRO ATTIVA                                           │"
fi
echo " │  Premi Ctrl+C per fermare tutto...                         │"
echo " └─────────────────────────────────────────────────────────────┘"
echo ""

# Resta in esecuzione finche' l'utente non preme Ctrl+C
while true; do
    sleep 1
done