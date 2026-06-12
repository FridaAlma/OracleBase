#!/usr/bin/env python3
"""
Tool Repository — Catalogo Evolutivo di Tool Riutilizzabili.

L'agente Oracle consulta questo repository PRIMA di scrivere codice.
Se esiste già un tool adatto, lo riusa. Se no, ne crea uno e può
promuoverlo nel repository per le sessioni future.

Architettura:
  /tools/              ← directory fisica dei tool registrati
  coding_agent.db      ← tabella `tool_catalog` con metadati (stesso db)

Flusso:
  1. CERCA  → python workspace/tool_repository.py search "webcam photo"
  2. TROVATO? → leggi /tools/{name} ed esegui
  3. NON TROVATO? → crea script, poi decidi se promuoverlo
  4. PROMUOVI → python workspace/tool_repository.py promote ...
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent.resolve()
DB_PATH = BASE_DIR / "coding_agent.db"
TOOLS_DIR = BASE_DIR / "tools"


# ──────────────────────────────────────────────
# Data Model
# ──────────────────────────────────────────────

TOOL_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_catalog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    tool_path   TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    params      TEXT NOT NULL DEFAULT '[]',
    example     TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    usage_count INTEGER NOT NULL DEFAULT 0,
    purpose     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    last_used   REAL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active','deprecated','removed'))
);
CREATE INDEX IF NOT EXISTS idx_tool_catalog_name ON tool_catalog(name);
CREATE INDEX IF NOT EXISTS idx_tool_catalog_status ON tool_catalog(status);
"""


# ──────────────────────────────────────────────
# Tool Repository Manager
# ──────────────────────────────────────────────

class ToolRepository:
    """
    Catalogo dei tool riutilizzabili.

    Ogni tool è un file Python (o script) in /tools/ con metadati
    associati nel database. Supporta ricerca, registrazione,
    promozione da volatile, e tracciamento d'uso.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
        # Assicura che /tools/ esista
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        (TOOLS_DIR / "__init__.py").touch(exist_ok=True)

    # ────── Database ──────

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Crea la tabella tool_catalog se non esiste."""
        conn = self._get_conn()
        # Esegue ogni statement separatamente
        for stmt in TOOL_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt + ";")
        conn.commit()
        conn.close()

    # ────── Search ──────

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """
        Cerca tool per nome, descrizione, tags, purpose.

        Usa matching case-insensitive su tutti i campi testuali.
        I risultati sono ordinati per rilevanza:
          - match nel nome > match nei tags > match in description/purpose
        """
        if not query.strip():
            return self.list_tools(limit=limit)

        words = query.lower().split()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM tool_catalog WHERE status = 'active'"
        ).fetchall()
        conn.close()

        scored: list[tuple[dict, int]] = []

        for row in rows:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            d["tags"] = json.loads(d["tags"])

            text = (
                d["name"].lower() + " " +
                d["description"].lower() + " " +
                d["purpose"].lower() + " " +
                " ".join(d["tags"]).lower()
            )

            score = 0
            for word in words:
                if word in text:
                    score += 1
                    # Bonus per match nel nome
                    if word in d["name"].lower():
                        score += 3
                    # Bonus per match nei tags
                    if word in [t.lower() for t in d["tags"]]:
                        score += 2

            if score > 0:
                scored.append((d, score))

        # Ordina per punteggio decrescente, poi per usage_count decrescente
        scored.sort(key=lambda x: (-x[1], -x[0]["usage_count"]))
        return [d for d, _ in scored[:limit]]

    # ────── Registration ──────

    def register(
        self,
        name: str,
        source_path: str,
        description: str,
        purpose: str = "",
        params: Optional[list] = None,
        example: str = "",
        tags: Optional[list] = None,
        copy_to_tools: bool = True,
    ) -> dict:
        """
        Registra un tool nel catalogo.

        Args:
            name: Nome unico del tool (es. "take_webcam_shot")
            source_path: Path del file sorgente (verrà copiato in /tools/name.py)
            description: Descrizione di cosa fa il tool
            purpose: A cosa serve, che problema risolve
            params: Lista di parametri [{name, type, required, description}]
            example: Esempio d'uso da riga di comando
            tags: Lista di parole chiave per la ricerca
            copy_to_tools: Se True, copia il file in /tools/ (default: True)

        Returns: dict con i dati del tool registrato
        """
        params = params or []
        tags = tags or []
        now = time.time()

        # Determina il path finale in /tools/
        src_path = Path(source_path)
        ext = src_path.suffix if src_path.suffix else ".py"
        tool_filename = f"{name}{ext}"
        tool_path = TOOLS_DIR / tool_filename

        # Copia in /tools/ se richiesto
        if copy_to_tools:
            if not src_path.exists():
                raise FileNotFoundError(f"Source file non trovato: {source_path}")
            shutil.copy2(str(src_path), str(tool_path))
            print(f"[ToolRepository] Copiato {source_path} -> {tool_path}")

        rel_tool_path = str(tool_path.relative_to(BASE_DIR))

        # Inserisce/aggiorna nel DB
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO tool_catalog
                   (name, tool_path, description, params, example, tags,
                    usage_count, purpose, created_at, last_used, status)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 'active')""",
                (
                    name,
                    rel_tool_path,
                    description,
                    json.dumps(params),
                    example,
                    json.dumps(tags),
                    purpose,
                    now,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.close()
            raise ValueError(f"Tool '{name}' già registrato. Usa remove() prima.") from e
        conn.close()

        record = {
            "name": name,
            "tool_path": rel_tool_path,
            "description": description,
            "params": params,
            "example": example,
            "tags": tags,
            "usage_count": 0,
            "purpose": purpose,
            "created_at": now,
            "last_used": None,
            "status": "active",
        }

        print(f"[ToolRepository] OK Registrato '{name}' -> {rel_tool_path}")
        return record

    # ────── Promotion (volatile → tool registrato) ──────

    def promote(
        self,
        name: str,
        source_path: str,
        description: str,
        purpose: str = "",
        params: Optional[list] = None,
        example: str = "",
        tags: Optional[list] = None,
        cleanup_source: bool = False,
    ) -> dict:
        """
        Promuove uno script volatile a tool registrato.

        Differenza da register():
        - Marca automaticamente la sorgente come 'completed' nel ToolLifecycle
        - Opzionalmente elimina la sorgente volatile (cleanup_source=True)
        - Suggerisce il nome basato sul filename se non specificato

        Args:
            name: Nome del tool
            source_path: Path dello script volatile da promuovere
            description: Descrizione
            purpose: Scopo
            params: Parametri
            example: Esempio
            tags: Tags
            cleanup_source: Se True, elimina il file sorgente dopo la copia

        Returns: record del tool registrato
        """
        record = self.register(
            name=name,
            source_path=source_path,
            description=description,
            purpose=purpose,
            params=params,
            example=example,
            tags=tags,
            copy_to_tools=True,
        )

        # Marca la sorgente come completata nel ToolLifecycle (se disponibile)
        try:
            from workspace.tool_lifecycle import ToolLifecycleManager
            lifecycle = ToolLifecycleManager()
            lifecycle.mark_completed(Path(source_path).name)
        except Exception:
            pass  # ToolLifecycle non disponibile, nessun problema

        # Cleanup opzionale della sorgente volatile
        if cleanup_source:
            src = Path(source_path)
            if src.exists():
                src.unlink()
                print(f"[ToolRepository] Rimosso sorgente volatile: {source_path}")

        print(f"[ToolRepository] OK Promosso '{name}' da volatile a tool registrato")
        return record

    # ────── Query ──────

    def list_tools(
        self,
        status: Optional[str] = "active",
        limit: int = 50,
    ) -> list[dict]:
        """Elenca i tool nel catalogo."""
        query = "SELECT * FROM tool_catalog WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY usage_count DESC, created_at DESC"
        if limit:
            query += f" LIMIT {limit}"

        conn = self._get_conn()
        rows = conn.execute(query, params).fetchall()
        conn.close()

        results = []
        for row in rows:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            d["tags"] = json.loads(d["tags"])
            d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
            if d["last_used"]:
                d["last_used_str"] = datetime.fromtimestamp(d["last_used"]).isoformat()
            else:
                d["last_used_str"] = None
            results.append(d)

        return results

    def get_tool(self, name: str) -> Optional[dict]:
        """Ottiene i dettagli di un tool per nome."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM tool_catalog WHERE name = ? AND status = 'active'",
            (name,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["params"] = json.loads(d["params"])
        d["tags"] = json.loads(d["tags"])
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).isoformat()
        if d["last_used"]:
            d["last_used_str"] = datetime.fromtimestamp(d["last_used"]).isoformat()
        else:
            d["last_used_str"] = None
        return d

    def increment_usage(self, name: str) -> bool:
        """Incrementa il contatore d'uso di un tool."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE tool_catalog SET usage_count = usage_count + 1, last_used = ? WHERE name = ?",
            (time.time(), name),
        )
        conn.commit()
        affected = cur.rowcount > 0
        conn.close()
        if affected:
            print(f"[ToolRepository] OK '{name}' usage_count++")
        return affected

    # ────── Removal ──────

    def remove(self, name: str, delete_file: bool = False) -> bool:
        """
        Rimuove un tool dal catalogo.

        Args:
            name: Nome del tool
            delete_file: Se True, elimina anche il file fisico in /tools/

        Returns: True se rimosso
        """
        tool = self.get_tool(name)
        if not tool:
            # Prova anche tra i non-attivi
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM tool_catalog WHERE name = ?", (name,)
            ).fetchone()
            conn.close()
            if not row:
                print(f"[ToolRepository] Tool '{name}' non trovato")
                return False
            tool = dict(row)

        conn = self._get_conn()
        conn.execute("DELETE FROM tool_catalog WHERE name = ?", (name,))
        conn.commit()
        conn.close()

        if delete_file:
            tool_path = BASE_DIR / tool["tool_path"]
            if tool_path.exists():
                tool_path.unlink()
                print(f"[ToolRepository] Eliminato file: {tool_path}")

        print(f"[ToolRepository] OK Rimosso '{name}' dal catalogo")
        return True

    def deprecate(self, name: str) -> bool:
        """Marca un tool come deprecato (rimane nel catalogo ma non nei search)."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE tool_catalog SET status = 'deprecated' WHERE name = ? AND status = 'active'",
            (name,),
        )
        conn.commit()
        affected = cur.rowcount > 0
        conn.close()
        if affected:
            print(f"[ToolRepository] OK '{name}' -> deprecated")
        return affected

    # ────── Utility ──────

    def get_summary(self) -> dict:
        """Resoconto sintetico del catalogo."""
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) as c FROM tool_catalog").fetchone()["c"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as c FROM tool_catalog GROUP BY status"
        ).fetchall()
        most_used = conn.execute(
            "SELECT name, usage_count FROM tool_catalog WHERE status = 'active' ORDER BY usage_count DESC LIMIT 5"
        ).fetchall()
        conn.close()

        return {
            "total_tools": total,
            "by_status": {r["status"]: r["c"] for r in by_status},
            "most_used": [{"name": r["name"], "uses": r["usage_count"]} for r in most_used],
        }

    def generate_index(self) -> str:
        """Genera un indice Markdown di tutti i tool attivi."""
        tools = self.list_tools(status="active")
        if not tools:
            return "# Tool Repository\n\n*(vuoto — nessun tool registrato)*\n"

        lines = [
            "# Tool Repository",
            "",
            f"Totale: {len(tools)} tool attivi",
            "",
            "| Nome | Descrizione | Usi | Tags |",
            "|------|-------------|-----|------|",
        ]

        for t in tools:
            tags_str = ", ".join(t["tags"][:3]) if t["tags"] else "-"
            lines.append(
                f"| `{t['name']}` | {t['description'][:60]} | {t['usage_count']} | {tags_str} |"
            )

        lines.extend(["", "---", "Generato automaticamente dal Tool Repository", ""])
        return "\n".join(lines)

    def write_index(self):
        """Scrive l'indice Markdown in /tools/TOOL_REGISTRY.md."""
        index_path = TOOLS_DIR / "TOOL_REGISTRY.md"
        index_path.write_text(self.generate_index(), encoding="utf-8")
        print(f"[ToolRepository] Indice aggiornato: {index_path}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Tool Repository — Catalogo Evolutivo di Tool Riutilizzabili",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Esempi:
              # Cerca tool per keyword
              python workspace/tool_repository.py search webcam

              # Registra un nuovo tool
              python workspace/tool_repository.py register \\
                  --name take_webcam_shot \\
                  --source capture_webcam.py \\
                  --description "Cattura una foto dalla webcam" \\
                  --purpose "Fotografia da webcam" \\
                  --tags "webcam,photo,capture"

              # Promuovi uno script volatile a tool
              python workspace/tool_repository.py promote \\
                  --name take_webcam_shot \\
                  --source ./tmp_webcam_test.py \\
                  --description "..." \\
                  --tags "webcam" --cleanup

              # Elenca tutti i tool
              python workspace/tool_repository.py list

              # Mostra dettagli di un tool
              python workspace/tool_repository.py get take_webcam_shot

              # Incrementa contatore d'uso
              python workspace/tool_repository.py use take_webcam_shot

              # Rimuovi un tool
              python workspace/tool_repository.py remove take_webcam_shot

              # Mostra riepilogo
              python workspace/tool_repository.py summary
        """),
    )

    sub = parser.add_subparsers(dest="action", help="Azione")

    # search
    p_search = sub.add_parser("search", help="Cerca tool per keyword")
    p_search.add_argument("query", help="Parole chiave da cercare")
    p_search.add_argument("--limit", type=int, default=10, help="Max risultati")
    p_search.add_argument("--json", action="store_true", help="Output JSON")

    # register
    p_reg = sub.add_parser("register", help="Registra un nuovo tool")
    p_reg.add_argument("--name", required=True, help="Nome unico del tool")
    p_reg.add_argument("--source", required=True, help="Path del file sorgente")
    p_reg.add_argument("--description", required=True, help="Descrizione")
    p_reg.add_argument("--purpose", default="", help="Scopo")
    p_reg.add_argument("--params", default="", help="Parametri in JSON")
    p_reg.add_argument("--example", default="", help="Esempio d'uso")
    p_reg.add_argument("--tags", default="", help="Tags separati da virgola")
    p_reg.add_argument("--no-copy", action="store_true", help="Non copiare in /tools/")

    # promote
    p_prom = sub.add_parser("promote", help="Promuovi volatile → tool registrato")
    p_prom.add_argument("--name", required=True, help="Nome del tool")
    p_prom.add_argument("--source", required=True, help="Path sorgente volatile")
    p_prom.add_argument("--description", required=True, help="Descrizione")
    p_prom.add_argument("--purpose", default="", help="Scopo")
    p_prom.add_argument("--params", default="", help="Parametri in JSON")
    p_prom.add_argument("--example", default="", help="Esempio d'uso")
    p_prom.add_argument("--tags", default="", help="Tags separati da virgola")
    p_prom.add_argument("--cleanup", action="store_true", help="Elimina sorgente dopo copia")

    # list
    p_list = sub.add_parser("list", help="Elenca tutti i tool attivi")
    p_list.add_argument("--json", action="store_true", help="Output JSON")
    p_list_all = sub.add_parser("list-all", help="Elenca tutti i tool (anche deprecati)")
    p_list_all.add_argument("--json", action="store_true", help="Output JSON")

    # get
    p_get = sub.add_parser("get", help="Mostra dettagli di un tool")
    p_get.add_argument("name", help="Nome del tool")

    # use
    p_use = sub.add_parser("use", help="Incrementa contatore d'uso")
    p_use.add_argument("name", help="Nome del tool")

    # remove
    p_rem = sub.add_parser("remove", help="Rimuovi un tool dal catalogo")
    p_rem.add_argument("name", help="Nome del tool")
    p_rem.add_argument("--delete-file", action="store_true", help="Elimina anche il file")

    # deprecate
    p_dep = sub.add_parser("deprecate", help="Marca un tool come deprecato")
    p_dep.add_argument("name", help="Nome del tool")

    # summary
    sub.add_parser("summary", help="Resoconto del catalogo")

    # index
    sub.add_parser("index", help="Genera TOOL_REGISTRY.md")

    args = parser.parse_args()
    repo = ToolRepository()

    if args.action == "search":
        results = repo.search(args.query, limit=args.limit)
        if not results:
            if getattr(args, 'json', False):
                print(json.dumps({"found": False, "query": args.query, "results": []}))
            else:
                print(f"Nessun tool trovato per '{args.query}'.")
            return
        if getattr(args, 'json', False):
            print(json.dumps({"found": True, "query": args.query, "results": results}, default=str, indent=2))
            return
        print(f"\n{'='*60}")
        print(f"  Tool Repository — Ricerca: '{args.query}'")
        print(f"{'='*60}\n")
        for r in results:
            tags_str = ", ".join(r["tags"]) if r["tags"] else "-"
            print(f"  [TOOL] {r['name']}")
            print(f"     {r['description'][:80]}")
            print(f"     Path: {r['tool_path']}")
            print(f"     Usi: {r['usage_count']}  |  Tags: {tags_str}")
            if r["example"]:
                print(f"     Es: {r['example'][:80]}")
            print()

    elif args.action == "register":
        try:
            params = json.loads(args.params) if args.params else None
        except json.JSONDecodeError:
            print("ERRORE: --params deve essere JSON valido")
            sys.exit(1)
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        repo.register(
            name=args.name,
            source_path=args.source,
            description=args.description,
            purpose=args.purpose,
            params=params,
            example=args.example,
            tags=tags,
            copy_to_tools=not args.no_copy,
        )
        repo.write_index()

    elif args.action == "promote":
        try:
            params = json.loads(args.params) if args.params else None
        except json.JSONDecodeError:
            print("ERRORE: --params deve essere JSON valido")
            sys.exit(1)
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
        repo.promote(
            name=args.name,
            source_path=args.source,
            description=args.description,
            purpose=args.purpose,
            params=params,
            example=args.example,
            tags=tags,
            cleanup_source=args.cleanup,
        )
        repo.write_index()

    elif args.action == "list":
        tools = repo.list_tools(status="active")
        if getattr(args, 'json', False):
            print(json.dumps({"tools": tools}, default=str, indent=2))
        else:
            _print_tool_list(tools)

    elif args.action == "list-all":
        tools = repo.list_tools(status=None)
        if getattr(args, 'json', False):
            print(json.dumps({"tools": tools, "include_deprecated": True}, default=str, indent=2))
        else:
            _print_tool_list(tools)

    elif args.action == "get":
        tool = repo.get_tool(args.name)
        if not tool:
            print(f"Tool '{args.name}' non trovato.")
            return
        _print_tool_detail(tool)

    elif args.action == "use":
        if repo.increment_usage(args.name):
            print(f"OK: usage_count incrementato per '{args.name}'")
        else:
            print(f"Tool '{args.name}' non trovato.")

    elif args.action == "remove":
        if repo.remove(args.name, delete_file=args.delete_file):
            repo.write_index()
        else:
            sys.exit(1)

    elif args.action == "deprecate":
        repo.deprecate(args.name)

    elif args.action == "summary":
        s = repo.get_summary()
        print(f"\n{'='*60}")
        print("  TOOL REPOSITORY — Riepilogo")
        print(f"{'='*60}")
        print(f"  Totale tool:     {s['total_tools']}")
        for status, count in s["by_status"].items():
            print(f"  {status.capitalize():15s} {count}")
        if s["most_used"]:
            print(f"  {'='*30}")
            print("  Più usati:")
            for m in s["most_used"]:
                print(f"    {m['name']:25s} ({m['uses']} usi)")
        print()

    elif args.action == "index":
        repo.write_index()

    else:
        parser.print_help()


def _print_tool_list(tools: list[dict]):
    if not tools:
        print("Nessun tool nel catalogo.")
        return
    print(f"\n{'='*60}")
    print(f"  TOOL REPOSITORY — Tool disponibili ({len(tools)})")
    print(f"{'='*60}\n")
    print(f"  {'Nome':25s} {'Usi':5s} {'Stato':10s} {'Descrizione'}")
    print(f"  {'-'*25} {'-'*5} {'-'*10} {'-'*30}")
    for t in tools:
        print(f"  {t['name']:25s} {t['usage_count']:5d} {t['status']:10s} {t['description'][:50]}")
    print()


def _print_tool_detail(tool: dict):
    print(f"\n{'='*60}")
    print(f"  [TOOL] {tool['name']}")
    print(f"{'='*60}")
    print(f"  Path:     {tool['tool_path']}")
    print(f"  Stato:    {tool['status']}")
    print(f"  Usi:      {tool['usage_count']}")
    print(f"  Creato:   {tool['created_at_str']}")
    if tool.get("last_used_str"):
        print(f"  Ultimo:   {tool['last_used_str']}")
    print()
    print(f"  Descrizione:")
    print(f"    {tool['description']}")
    if tool["purpose"]:
        print(f"  Scopo:")
        print(f"    {tool['purpose']}")
    if tool["params"]:
        print(f"  Parametri:")
        for p in tool["params"]:
            req = "[req]" if p.get("required") else "[opt]"
            print(f"    {p['name']:20s} ({p.get('type','str'):8s}) [{req}]  {p.get('description','')}")
    if tool["tags"]:
        print(f"  Tags:     {', '.join(tool['tags'])}")
    if tool["example"]:
        print(f"  Esempio:")
        print(f"    {tool['example']}")
    print()


if __name__ == "__main__":
    main()