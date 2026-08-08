"""
ThinkTank — SQLite persistence layer.
Handles: ideas, gate_history, chats, chat_messages.
"""

import json
import sqlite3
from datetime import datetime, timezone
from thinktank.config import DB_PATH

# ── Schema ────────────────────────────────────────────────────────────────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_history (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_id            INTEGER NOT NULL,
    verdict            TEXT    NOT NULL,
    signal             TEXT    NOT NULL,
    impact             INTEGER,
    effort             INTEGER,
    risk               INTEGER,
    novelty            INTEGER,
    rationale_json     TEXT    NOT NULL,
    recommended_action TEXT    NOT NULL,
    created_at         TEXT    NOT NULL,
    FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE TABLE IF NOT EXISTS chats (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

CREATE TABLE IF NOT EXISTS coin_users (
    session_id TEXT    PRIMARY KEY,
    coins      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS coin_transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    type           TEXT    NOT NULL,
    amount         INTEGER NOT NULL,
    stripe_session TEXT,
    created_at     TEXT    NOT NULL
);
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(_SCHEMA)


# ── Ideas ─────────────────────────────────────────────────────────────────────
def save_idea(text: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO ideas(text, created_at) VALUES (?, ?)",
            (text, _utc()),
        )
        return int(cur.lastrowid)


def get_idea(idea_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT id, text, created_at FROM ideas WHERE id=?", (idea_id,)
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "text": row[1], "created_at": row[2]}


def list_ideas(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT id, text, created_at FROM ideas ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]


def delete_idea(idea_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM ideas WHERE id=?", (idea_id,))
        return cur.rowcount > 0


def count_ideas() -> int:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT COUNT(*) FROM ideas").fetchone()
    return int(row[0]) if row else 0


# ── Gate history ──────────────────────────────────────────────────────────────
def add_gate_history(
    idea_id: int,
    verdict: str,
    signal: str,
    score: dict,
    rationale: list,
    recommended_action: str,
) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            INSERT INTO gate_history(
                idea_id, verdict, signal, impact, effort, risk, novelty,
                rationale_json, recommended_action, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                idea_id,
                verdict,
                signal,
                score.get("impact"),
                score.get("effort"),
                score.get("risk"),
                score.get("novelty"),
                json.dumps(rationale),
                recommended_action,
                _utc(),
            ),
        )
        return int(cur.lastrowid)


def list_gate_history(limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty,
                      recommended_action, created_at
               FROM gate_history ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [_gate_row(r) for r in rows]


def list_gate_history_for_idea(idea_id: int, limit: int = 20) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty,
                      recommended_action, created_at
               FROM gate_history WHERE idea_id=? ORDER BY id DESC LIMIT ?""",
            (idea_id, limit),
        ).fetchall()
    return [_gate_row(r) for r in rows]


def get_latest_gate_for_idea(idea_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            """SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty,
                      recommended_action, created_at
               FROM gate_history WHERE idea_id=? ORDER BY id DESC LIMIT 1""",
            (idea_id,),
        ).fetchone()
    return _gate_row(row) if row else None


def _gate_row(r) -> dict:
    return {
        "id": r[0], "idea_id": r[1], "verdict": r[2], "signal": r[3],
        "impact": r[4], "effort": r[5], "risk": r[6], "novelty": r[7],
        "recommended_action": r[8], "created_at": r[9],
    }


# ── Chats ─────────────────────────────────────────────────────────────────────
def chat_new(title: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO chats(title, created_at) VALUES (?, ?)",
            (title, _utc()),
        )
        return int(cur.lastrowid)


def chat_list(limit: int = 50) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT id, title, created_at FROM chats ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]


def chat_exists(chat_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        return con.execute(
            "SELECT 1 FROM chats WHERE id=? LIMIT 1", (chat_id,)
        ).fetchone() is not None


def chat_add_message(chat_id: int, role: str, content: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO chat_messages(chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, _utc()),
        )
        return int(cur.lastrowid)


def chat_get_messages(chat_id: int, limit: int = 40) -> list[dict]:
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT role, content, created_at FROM chat_messages
               WHERE chat_id=? ORDER BY id DESC LIMIT ?""",
            (chat_id, limit),
        ).fetchall()
    return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in reversed(rows)]


def chat_delete(chat_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM chat_messages WHERE chat_id=?", (chat_id,))
        cur = con.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return cur.rowcount > 0


# ── Coins ──────────────────────────────────────────────────────────────────────
WELCOME_COINS = 5  # Free coins every new user receives on first visit

def coin_get_or_create(session_id: str) -> int:
    """Return the coin balance for session_id, creating the row if needed.
    New users receive WELCOME_COINS for free."""
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        if row:
            return row[0]
        con.execute(
            "INSERT INTO coin_users(session_id, coins, created_at) VALUES (?, ?, ?)",
            (session_id, WELCOME_COINS, _utc()),
        )
        con.execute(
            "INSERT INTO coin_transactions(session_id, type, amount, stripe_session, created_at) "
            "VALUES (?, 'welcome', ?, 'welcome-bonus', ?)",
            (session_id, WELCOME_COINS, _utc()),
        )
        return WELCOME_COINS


def coin_balance(session_id: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        return row[0] if row else 0


def coin_spend(session_id: str, amount: int = 1) -> bool:
    """Deduct coins. Returns False if insufficient balance."""
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        if not row or row[0] < amount:
            return False
        con.execute(
            "UPDATE coin_users SET coins = coins - ? WHERE session_id=?",
            (amount, session_id),
        )
        con.execute(
            "INSERT INTO coin_transactions(session_id, type, amount, created_at) VALUES (?, 'spend', ?, ?)",
            (session_id, -amount, _utc()),
        )
        return True


def coin_credit(session_id: str, amount: int, stripe_session: str) -> None:
    """Credit coins after a confirmed Stripe payment. Idempotent."""
    with sqlite3.connect(DB_PATH) as con:
        already = con.execute(
            "SELECT id FROM coin_transactions WHERE stripe_session=?", (stripe_session,)
        ).fetchone()
        if already:
            return
        coin_get_or_create(session_id)
        con.execute(
            "UPDATE coin_users SET coins = coins + ? WHERE session_id=?",
            (amount, session_id),
        )
        con.execute(
            "INSERT INTO coin_transactions(session_id, type, amount, stripe_session, created_at) "
            "VALUES (?, 'purchase', ?, ?, ?)",
            (session_id, amount, stripe_session, _utc()),
        )
