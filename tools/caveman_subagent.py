#!/usr/bin/env python3
"""
🪨 Caveman Sub-Agent — Task() helper per ragionamento compresso.

Invocato via Task() per delegare analisi, pianificazione e debugging
in modalità ultra-terse. Risparmia ~70% token rispetto a ragionamento verboso.

Utilizzo (da system prompt Oracle):
    Task("analyze X", agent=caveman_subagent()) → output compresso
    Task("plan Y", agent=caveman_subagent())   → output compresso

Registrato in Tool Repository come 'caveman_subagent'.
"""

def caveman_instructions(task: str = "") -> str:
    """Restituisce le istruzioni per un sub-agente in modalità caveman."""
    return f"""You are a compressed reasoning sub-agent. Respond ULTRA-TERSE.

RULES:
- Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/happy to), hedging.
- Fragments OK. Short synonyms (big not extensive, fix not "implement a solution for").
- One line per finding. Pattern: `[thing] [action] [reason].`
- Code, paths, API names, error strings: EXACT, never alter.
- No "Let me", "I think", "I'll", "First I need to".
- No markdown formatting unless returning code.

EXAMPLES:
  Task: "Analyze error in fetch_user()"
  -> Error at line 42. user null after .find(). Missing guard.

  Task: "Plan wiki page structure for data_poisoning"
  -> 3 sections: intro / attack_vectors / mitigation. 
    Sources: arXiv:2507.06252, NIST AI 100-2.

  Task: "Debug why PostgreSQL connection failed"
  -> Pool exhausted. 15 conn open, 5 idle. Max_pool=10. 
    Fix: increase pool or close leaked conn.

TASK: {task}

Output only your findings. No greetings. No summary."""


def create_caveman_config():
    """Restituisce configurazione per agno Agent in modalità caveman.
    
    Utilizzo diretto (se si usa il framework agno):
        from workspace.caveman_subagent import create_caveman_config
        cfg = create_caveman_config()
        
    Utilizzo via Task() nella system prompt:
        Task("analyze X", agent=caveman_subagent)
    """
    return {
        "name": "CavemanReasoner",
        "instructions": caveman_instructions(),
        "markdown": False,
        "temperature": 0.05,  # Bassa temperatura = output più deterministico e compresso
        "add_history_to_context": False,
        "num_history_runs": 0,
    }


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "analyze"
    print("=== CAVEMAN INSTRUCTIONS ===")
    print(caveman_instructions(task))
    print("\n=== CONFIG ===")
    import json
    print(json.dumps(create_caveman_config(), indent=2, ensure_ascii=False))