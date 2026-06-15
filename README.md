# Oracle — AI Coding Agent Autonomo

**Oracle** e' un agente di coding autonomo basato su [Agno](https://github.com/agno-agi/agno), progettato per leggere, scrivere, modificare, cercare ed eseguire codice in modo automatico.

---

## Indice

1. [Panoramica](#panoramica)
2. [Architettura Base](#architettura-base)
3. [Installazione](#installazione)
4. [Configurazione](#configurazione)
5. [Utilizzo](#utilizzo)
6. [Componenti del Progetto](#componenti-del-progetto)
7. [Requisiti](#requisiti)
8. [Note sulla Sicurezza](#note-sulla-sicurezza)

---

## Panoramica

Oracle e' un agente AI che alla sua installazione base sa:

- **Leggere** qualsiasi file nel progetto
- **Scrivere e modificare** codice atomicamente
- **Cercare** file con glob patterns e contenuti con espressioni regolari
- **Eseguire** comandi shell arbitrari
- **Ricordare** preferenze utente e contesto tra piu' sessioni
- **Creare propri tool** durante l'uso, catalogarli e riutilizzarli
- **Lanciare sub-agenti** per ricerche complesse

Oracle puo costruire i tool necessari, che non possiede, per completare la richiesta dell'utente

---

## Architettura Base

Oracle e' composto solo dal framework Agno e da un sottile wrapper:

```
D:\Work\AGI\Oracle/
│
├── coding_agent.py        # Definizione agente + server FastAPI + API chat
├── cli.py                 # Interfaccia CLI interattiva
├── chat.html              # Interfaccia chatbot web (UI)
├── system_prompt.md       # Prompt di sistema dell'agente
├── oracle.bat             # Launcher Windows (CLI o UI)
├── .env                   # Configurazione (API key, modello, server)
├── .env.example           # Template per .env
├── requirements.txt       # Dipendenze Python
└── coding_agent.db        # SQLite: sessioni, memoria agente
```

### Cosa fornisce Agno (framework base)

| Componente | Descrizione |
|-----------|-------------|
| **`OpenAIChat`** | Integrazione con modelli OpenAI-compatible (DeepSeek, GPT, etc.) |
| **`CodingTools`** | Tool nativi: `read`, `write`, `edit`, `search`, `grep`, `shell`, `task` |
| **`Workspace`** | Tool nativi: `list`, `read`, `search`, `shell` su directory |
| **`Agent`** | Orchestratore: model + tools + memory + instructions |
| **`AgentOS`** | Server FastAPI + routing + tracing integrato |
| **`SqliteDb`** | Storage persistente per sessioni e memoria agente |
| **Agentic Memory** | Memoria cross-sessione per preferenze utente |

**In sintesi:** Agno fornisce il motore agente, i tool di coding fondamentali e l'infrastruttura server.

---

## Installazione

### 1. Clona il repository

```bash
git clone <url-del-repository>
cd D:\Work\AGI\Oracle
```

### 2. Crea un ambiente virtuale (consigliato)

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/Mac
```

### 3. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 4. Configura le variabili d'ambiente

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Linux/Mac
```

Modifica il file `.env` con i tuoi valori (vedi [Configurazione](#configurazione)).

---

## Configurazione

Il file `.env` contiene tutte le impostazioni:

```ini
# ── Modello AI ──
MODEL_ID=deepseek-v4-flash        # Modello da utilizzare
API_BASE_URL=https://api.deepseek.com/v1  # Endpoint API
API_KEY=your-api-key-here          # Chiave API DeepSeek
MAX_TOKENS=16384                   # Token massimi per risposta
REQUEST_TIMEOUT=120                # Timeout richiesta in secondi

# ── Server FastAPI ──
HOST=127.0.0.1                     # IP su cui ascoltare
PORT=8000                          # Porta del server
```

---

## Utilizzo

Oracle offre due interfacce: **Web UI** (default) e **CLI**.

### Web UI (Chatbot)

Interfaccia chatbot moderna con streaming in tempo reale. **Modalita' predefinita.**

```bash
oracle.bat
```

Cosa fa:
1. Avvia il server FastAPI in finestra separata
2. Apre automaticamente il browser su `http://localhost:8000/ui`
3. Premi Ctrl+C nella finestra batch per fermare il server

Puoi anche avviare manualmente:

```bash
python coding_agent.py --port 8000
```

E aprire il browser su `http://localhost:8000/ui`

**Caratteristiche dell'interfaccia web:**
- Streaming in tempo reale delle risposte (SSE)
- Markdown renderizzato (codice, tabelle, elenchi)
- Indicatori visivi durante le chiamate tool
- Gestione automatica delle sessioni
- Pulsante per nuova conversazione
- Interrompibile (pulsante stop / tasto Esc)

### CLI Interattiva

Avvia una sessione interattiva con cronologia comandi e supporto multi-riga:

```bash
oracle.bat --cli
```

Oppure direttamente:

```bash
python cli.py
```

Nella CLI:
- Digita un prompt e premi Invio
- **Incolla codice su piu' righe** — viene rilevato automaticamente (bracketed paste mode)
- `exit` o `quit` per uscire
- `Ctrl+C` per interrompere

### Singolo comando

```bash
python cli.py "Crea un file README per questo progetto"
```

### Server FastAPI (diretto)

```bash
python coding_agent.py --port 8080
```

**Opzioni:**
| Flag | Default | Descrizione |
|------|---------|-------------|
| `--port` | `8000` | Porta del server |
| `--host` | `0.0.0.0` | Indirizzo di ascolto |

### Launcher Windows (`oracle.bat`)

| Comando | Effetto |
|---------|---------|
| `oracle.bat` | Avvia Web UI (default) |
| `oracle.bat --cli` | Avvia CLI interattiva |
| `oracle.bat --port 8080` | Web UI su porta 8080 |
| `oracle.bat --help` | Mostra aiuto |

---

## Componenti del Progetto

### `coding_agent.py` — Agente + Server

Il cuore del progetto. Definisce l'agente Oracle con:

- **Modello AI**: DeepSeek (o qualsiasi modello OpenAI-compatible via `API_BASE_URL`)
- **Tool base (Agno)**: `CodingTools` (lettura, scrittura, modifica, shell, task) e `Workspace` (navigazione file)
- **Memoria**: SQLite persistente (`coding_agent.db`) + agentic memory
- **Storico**: ultime 3 conversazioni iniettate nel contesto
- **Server FastAPI**: esposto su endpoint `/api/chat`, `/api/chat/stream` (SSE), `/api/chat/sessions`
- **Retry logic**: gestione automatica di errori di connessione con secondo tentativo

### `cli.py` — Interfaccia a Riga di Comando

CLI interattiva con:
- **History persistente** (file `.cli_history`)
- **Multi-line input** con rilevamento automatico di paste (bracketed paste mode)
- **Streaming** delle risposte in tempo reale

### `oracle.bat` — Launcher Windows

Script batch che:
1. Verifica che Python sia installato
2. Controlla l'esistenza del file `.env`
3. Avvia la Web UI o CLI interattiva
4. Gestisce cleanup browser e server all'arresto

### `system_prompt.md` — Prompt di Sistema

Documento che definisce la personalita', le regole comportamentali e i protocolli operativi di Oracle. Include:
- Regole generali di comportamento
- Workflow di ingegneria del software
- Convenzioni di codice
- Protocolli di debugging e testing
- **Tool creation mandate**: Oracle non rifiuta mai un task per mancanza di strumenti — li costruisce da se'

---

## Requisiti

### Dipendenze Python (`requirements.txt`)

| Pacchetto | Versione | Scopo |
|-----------|----------|-------|
| `agno` | >=2.6.4 | Framework agente AI |
| `python-dotenv` | >=1.1.1 | Caricamento variabili d'ambiente |
| `httpx` | >=0.28.1 | Client HTTP con timeout configurabile |
| `uvicorn` | >=0.40.0 | Server ASGI per FastAPI |
| `openai` | >=1.0.0 | Client API OpenAI-compatible |
| `sqlalchemy` | >=2.0.0 | ORM per database |
| `aiosqlite` | >=0.19.0 | SQLite asincrono |
| `fastapi` | >=0.100.0 | Server web per API |

---

## Note sulla Sicurezza

- La **API key** e' memorizzata nel file `.env` — non condividerlo mai
- Oracle non modifica file fuori dalla directory del progetto
- I comandi shell potenzialmente pericolosi richiedono conferma

---

## Licenza

MIT — per scopi di ricerca e sviluppo legittimi.

---

*Generato con cura da Oracle*
