"""
Tool Lifecycle Manager — "Volatile or Persistent?"

Gestisce il ciclo di vita degli script/tool creati dall'agente Oracle.
Classifica ogni artefatto come:

    VOLATILE  (.tmp, __tmp__, o creato in root) → auto-cleanup a obiettivo raggiunto
    PERSISTENT (workspace/ con nome stabile)    → archiviato per riuso futuro

Il registry è un database SQLite (collegato allo stesso db dell'agente)
che traccia: nome, path, tipo, purpose, session_id, stato, dipendenze.
"""

import json
import os
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "coding_agent.db"
WORKSPACE_DIR = BASE_DIR / "workspace"

# ──────────────────────────────────────────────
# Data model
# ──────────────────────────────────────────────

@dataclass
class ToolRecord:
    """Representa un tool nel registro di ciclo di vita."""
    name: str                     # nome breve (es. "capture_webcam.py")
    file_path: str                # path relativo a BASE_DIR
    tool_type: str                # "volatile" | "persistent" | "generated_artifact"
    purpose: str                  # descrizione dello scopo
    session_id: str               # sessione che lo ha creato
    created_at: float             # Unix timestamp
    status: str = "active"        # active | completed | archived | deleted
    depends_on: list = field(default_factory=list)  # lista di nomi di tool da cui dipende
    ttl_seconds: Optional[int] = None  # None = vive per sempre, altrimenti auto-cleanup dopo N secondi


# ──────────────────────────────────────────────
# Lifecycle Manager
# ──────────────────────────────────────────────

class ToolLifecycleManager:
    """
    Registry + Lifecycle Manager per i tool creati dall'agente.

    Usa `coding_agent.db` per persistenza, stessa connessione dell'agente
    ma con tabella dedicata `tool_lifecycle`.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    # ────── Database ──────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_lifecycle (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                file_path   TEXT NOT NULL,
                tool_type   TEXT NOT NULL CHECK(tool_type IN ('volatile','persistent','generated_artifact')),
                purpose     TEXT NOT NULL DEFAULT '',
                session_id  TEXT NOT NULL DEFAULT '',
                created_at  REAL NOT NULL,
                status      TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','archived','deleted')),
                depends_on  TEXT NOT NULL DEFAULT '[]',
                ttl_seconds REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_lifecycle_status ON tool_lifecycle(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_lifecycle_type ON tool_lifecycle(tool_type)
        """)
        conn.commit()
        conn.close()

    # ────── Registration ──────

    def register(
        self,
        file_path: str,
        purpose: str,
        tool_type: Optional[str] = None,
        session_id: str = "",
        ttl_seconds: Optional[int] = None,
        depends_on: Optional[list] = None,
    ) -> ToolRecord:
        """
        Registra un tool nel ciclo di vita.

        - Se tool_type non specificato, viene **autoclassificato**:
            "volatile"  → se path contiene .tmp, __tmp__, o è nella root
            "persistent" → se è dentro workspace/ (e non è temporaneo)
            "generated_artifact" → se è un file di output (jpg, png, pdf, ...)
        """
        path = Path(file_path)
        name = path.name
        rel_path = str(path.relative_to(BASE_DIR)) if path.is_absolute() else file_path

        # Autoclassificazione se non specificata
        if tool_type is None:
            tool_type = self._classify(file_path, name)

        # Determina TTL di default
        if ttl_seconds is None:
            ttl_seconds = self._default_ttl(tool_type)

        depends_on = depends_on or []
        now = time.time()

        record = ToolRecord(
            name=name,
            file_path=rel_path,
            tool_type=tool_type,
            purpose=purpose,
            session_id=session_id,
            created_at=now,
            status="active",
            depends_on=depends_on,
            ttl_seconds=ttl_seconds,
        )

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO tool_lifecycle
               (name, file_path, tool_type, purpose, session_id, created_at, status, depends_on, ttl_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.name,
                record.file_path,
                record.tool_type,
                record.purpose,
                record.session_id,
                record.created_at,
                record.status,
                json.dumps(record.depends_on),
                record.ttl_seconds,
            ),
        )
        conn.commit()
        conn.close()

        print(f"[ToolLifecycle] OK Registrato '{name}' come <{tool_type}> -- {purpose}")
        return record

    @staticmethod
    def _classify(file_path: str, name: str) -> str:
        """Autoclassificazione basata su path e nome file."""
        # Artefatti generati (output)
        if re.search(r'\.(jpg|jpeg|png|gif|bmp|mp4|avi|mov|pdf|csv|xlsx?|json|xml|zip|tar|gz)$', name, re.I):
            return "generated_artifact"
        # Temporanei espliciti
        if '.tmp' in name or '__tmp__' in name or name.startswith('tmp_'):
            return "volatile"
        path_lower = file_path.lower()
        # Nella root (fuori workspace/) → volatile
        if 'workspace' not in path_lower:
            return "volatile"
        # Dentro workspace/ → persistente
        if 'workspace' in path_lower and '.tmp' not in name:
            return "persistent"
        return "volatile"

    @staticmethod
    def _default_ttl(tool_type: str) -> Optional[int]:
        """TTL di default per tipo."""
        if tool_type == "volatile":
            return 3600  # 1 ora
        if tool_type == "generated_artifact":
            return 1800  # 30 minuti
        return None  # persistente: vive per sempre

    # ────── Status transitions ──────

    def mark_completed(self, name: str) -> bool:
        """Marca un tool come 'completed' (task raggiunto)."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE tool_lifecycle SET status = 'completed' WHERE name = ? AND status = 'active'",
            (name,),
        )
        conn.commit()
        affected = cur.rowcount > 0
        conn.close()
        if affected:
            print(f"[ToolLifecycle] OK '{name}' -> completed")
        return affected

    def mark_archived(self, name: str) -> bool:
        """Marca un tool persistente come archiviato (mantenuto)."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE tool_lifecycle SET status = 'archived' WHERE name = ? AND tool_type = 'persistent'",
            (name,),
        )
        conn.commit()
        affected = cur.rowcount > 0
        conn.close()
        if affected:
            print(f"[ToolLifecycle] OK '{name}' -> archived")
        return affected

    def mark_deleted(self, name: str) -> bool:
        """Marca un tool come deleted (rimosso fisicamente)."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE tool_lifecycle SET status = 'deleted' WHERE name = ?",
            (name,),
        )
        conn.commit()
        affected = cur.rowcount > 0
        conn.close()
        if affected:
            print(f"[ToolLifecycle] OK '{name}' -> deleted")
        return affected

    # ────── Cleanup ──────

    def cleanup_volatile(self, age_threshold: Optional[float] = None) -> list[str]:
        """
        Elimina fisicamente i tool volatili che hanno completato il loro scopo
        o che hanno superato il TTL.

        Args:
            age_threshold: timestamp UNIX; se None, usa il TTL registrato.

        Returns: lista di file eliminati.
        """
        deleted = []
        now = time.time()

        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, name, file_path, tool_type, status, created_at, ttl_seconds FROM tool_lifecycle"
        ).fetchall()
        conn.close()

        for row in rows:
            should_delete = False

            # Caso 1: volatile completato → cleanup immediato
            if row["tool_type"] in ("volatile", "generated_artifact") and row["status"] == "completed":
                should_delete = True

            # Caso 2: TTL scaduto
            if row["status"] == "active" and row["ttl_seconds"] is not None:
                expires_at = row["created_at"] + row["ttl_seconds"]
                if now > expires_at:
                    should_delete = True

            if should_delete:
                full_path = BASE_DIR / row["file_path"]
                if full_path.exists():
                    if full_path.is_file():
                        full_path.unlink()
                    elif full_path.is_dir():
                        shutil.rmtree(str(full_path))
                    deleted.append(row["file_path"])
                    print(f"[ToolLifecycle] DEL Eliminato '{row['name']}' (<{row['tool_type']}>)")

                # Marca come deleted nel DB
                conn2 = self._get_conn()
                conn2.execute("UPDATE tool_lifecycle SET status = 'deleted' WHERE id = ?", (row["id"],))
                conn2.commit()
                conn2.close()

        return deleted

    def cleanup_all_completed(self) -> list[str]:
        """Elimina tutti i tool completati (volatili + artifact)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT name, file_path, tool_type FROM tool_lifecycle WHERE status = 'completed'"
        ).fetchall()
        conn.close()

        deleted = []
        for row in rows:
            full_path = BASE_DIR / row["file_path"]
            if full_path.exists():
                if full_path.is_file():
                    full_path.unlink()
                elif full_path.is_dir():
                    shutil.rmtree(str(full_path))
                deleted.append(row["file_path"])
                print(f"[ToolLifecycle] DEL Cleanup finale: '{row['name']}'")

        if deleted:
            conn2 = self._get_conn()
            conn2.executemany(
                "UPDATE tool_lifecycle SET status = 'deleted' WHERE name = ?",
                [(d,) for d in deleted],
            )
            conn2.commit()
            conn2.close()

        return deleted

    def cleanup_expired(self) -> list[str]:
        """Elimina solo i tool con TTL scaduto."""
        return self.cleanup_volatile()

    # ────── Query ──────

    def list_tools(
        self,
        status: Optional[str] = None,
        tool_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """Lista dei tool registrati, con filtri opzionali."""
        query = "SELECT * FROM tool_lifecycle WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if tool_type:
            query += " AND tool_type = ?"
            params.append(tool_type)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY created_at DESC"

        conn = self._get_conn()
        rows = conn.execute(query, params).fetchall()
        conn.close()

        result = []
        for row in rows:
            d = dict(row)
            d["depends_on"] = json.loads(d["depends_on"])
            d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
            result.append(d)
        return result

    def get_tool(self, name: str) -> Optional[dict]:
        """Cerca un tool per nome."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tool_lifecycle WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            d["depends_on"] = json.loads(d["depends_on"])
            return d
        return None

    def get_summary(self) -> dict:
        """Resoconto sintetico dello stato del ciclo di vita."""
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT tool_type, status, COUNT(*) as count
            FROM tool_lifecycle
            GROUP BY tool_type, status
            ORDER BY tool_type, status
        """)
        rows = cur.fetchall()

        total = conn.execute("SELECT COUNT(*) as c FROM tool_lifecycle").fetchone()["c"]
        expired_count = conn.execute(
            "SELECT COUNT(*) as c FROM tool_lifecycle WHERE ttl_seconds IS NOT NULL AND (created_at + ttl_seconds) < ?",
            (time.time(),),
        ).fetchone()["c"]
        conn.close()

        breakdown = {}
        for r in rows:
            key = f"{r['tool_type']}/{r['status']}"
            breakdown[key] = r["count"]

        return {
            "total_tracked": total,
            "expired_pending_cleanup": expired_count,
            "breakdown": breakdown,
        }

    # ────── Display ──────

    def print_status(self):
        """Stampa una tabella dello stato corrente."""
        summary = self.get_summary()
        print(f"\n{'='*60}")
        print(f"  TOOL LIFECYCLE - Stato attuale")
        print(f"{'='*60}")
        print(f"  Totale tracciati:        {summary['total_tracked']}")
        print(f"  Scaduti (da cleanup):    {summary['expired_pending_cleanup']}")
        print(f"  {'='*30}")
        for key, count in sorted(summary["breakdown"].items()):
            print(f"  {key:30s} {count}")
        print(f"{'='*60}\n")

        tools = self.list_tools()
        if not tools:
            print("  (nessun tool registrato)\n")
            return

        print(f"  {'Nome':25s} {'Tipo':15s} {'Status':12s} {'Creato':22s}")
        print(f"  {'-'*25} {'-'*15} {'-'*12} {'-'*22}")
        for t in tools:
            created = datetime.fromtimestamp(t["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  {t['name']:25s} {t['tool_type']:15s} {t['status']:12s} {created:22s}")
        print()

    def scan_and_register_orphans(self) -> list[str]:
        """
        Scansione workspace/ e root per trovare file non registrati.
        Li registra automaticamente come 'persistent' (workspace) o 'volatile' (root).
        """
        registered_names = {t["name"] for t in self.list_tools()}
        orphans = []

        # Scansiona root (volatili)
        for f in BASE_DIR.iterdir():
            if f.is_file() and f.suffix in (".py", ".sh", ".bat", ".ps1", ".js", ".ts"):
                if f.name not in registered_names and f.name not in (
                    "coding_agent.py", "cli.py", "system_prompt.md",
                    ".env", ".env.example", "coding_agent.db",
                ):
                    self.register(
                        file_path=str(f),
                        purpose="[auto-scansione] script in root",
                        session_id="system",
                    )
                    orphans.append(f.name)

        # Scansiona workspace/ (persistenti)
        if WORKSPACE_DIR.exists():
            for f in WORKSPACE_DIR.rglob("*"):
                if f.is_file() and f.suffix in (".py", ".sh", ".bat", ".ps1", ".js", ".ts", ".md"):
                    if f.name not in registered_names:
                        self.register(
                            file_path=str(f),
                            purpose="[auto-scansione] tool in workspace",
                            session_id="system",
                        )
                        orphans.append(str(f.relative_to(BASE_DIR)))

        return orphans


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

def main():
    """CLI per interagire con il Tool Lifecycle Manager."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Tool Lifecycle Manager - Ciclo di Vita degli Script"
    )
    parser.add_argument("action", nargs="?", default="status", help=(
        "status | list | cleanup | scan | register | delete | archive"
    ))
    parser.add_argument("name", nargs="?", help="Nome del tool")
    parser.add_argument("--type", dest="tool_type", help="Tipo: volatile|persistent|generated_artifact")
    parser.add_argument("--purpose", help="Scopo del tool")
    parser.add_argument("--session", help="Session ID")
    parser.add_argument("--status-filter", help="Filtro per status (active|completed|archived|deleted)")
    parser.add_argument("--type-filter", help="Filtro per tipo (volatile|persistent|generated_artifact)")

    args = parser.parse_args()
    mgr = ToolLifecycleManager()

    if args.action == "status":
        mgr.cleanup_expired()  # auto-pulizia prima di mostrare
        mgr.print_status()

    elif args.action == "list":
        tools = mgr.list_tools(
            status=args.status_filter,
            tool_type=args.type_filter,
            session_id=args.session,
        )
        if not tools:
            print("Nessun tool trovato.")
            return
        for t in tools:
            created = datetime.fromtimestamp(t["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  [{t['status']:10s}] {t['name']:25s} <{t['tool_type']:20s}> -> {t['purpose'][:50]:50s} ({created})")

    elif args.action == "cleanup":
        deleted = mgr.cleanup_all_completed()
        expired = mgr.cleanup_expired()
        all_deleted = set(deleted + expired)
        if all_deleted:
            print(f"Puliti {len(all_deleted)} file: {', '.join(all_deleted)}")
        else:
            print("Niente da pulire.")

    elif args.action == "scan":
        orphans = mgr.scan_and_register_orphans()
        if orphans:
            print(f"Registrati {len(orphans)} tool orfani:")
            for o in orphans:
                print(f"  * {o}")
        else:
            print("Nessun orfano trovato.")

    elif args.action == "register":
        if not args.name:
            print("ERRORE: specifica --name per registrare un tool")
            return
        mgr.register(
            file_path=args.name,
            purpose=args.purpose or "registrazione manuale",
            tool_type=args.tool_type,
            session_id=args.session or "manual",
        )

    elif args.action == "delete":
        if not args.name:
            print("ERRORE: specifica --name per eliminare un tool")
            return
        mgr.mark_deleted(args.name)

    elif args.action == "archive":
        if not args.name:
            print("ERRORE: specifica --name per archiviare un tool")
            return
        mgr.mark_archived(args.name)

    else:
        print(f"Azione sconosciuta: {args.action}")
        parser.print_help()


if __name__ == "__main__":
    main()