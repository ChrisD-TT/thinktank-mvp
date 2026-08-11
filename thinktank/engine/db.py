"""
ThinkTank — SQLite persistence layer.
Handles: ideas, gate_history, chats, chat_messages, users, coins.
"""

import json
import hashlib
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

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    plan_tier     TEXT    NOT NULL DEFAULT 'free',
    promo_code    TEXT,
    promo_used    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
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

CREATE TABLE IF NOT EXISTS studio_content (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    platform     TEXT    NOT NULL,
    topic        TEXT    NOT NULL,
    tone         TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    content_type TEXT    NOT NULL,
    scheduled_for TEXT,
    released     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    minutes    INTEGER NOT NULL,
    coins_paid INTEGER NOT NULL,
    started_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_session_state (
    session_id  TEXT PRIMARY KEY,
    end_epoch   REAL NOT NULL,
    mins_total  INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS studio_coin_users (
    session_id TEXT    PRIMARY KEY,
    coins      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS studio_coin_transactions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    type           TEXT    NOT NULL,
    amount         INTEGER NOT NULL,
    stripe_session TEXT,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sale_promo_codes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT    NOT NULL UNIQUE,
    label          TEXT    NOT NULL,
    discount_pct   INTEGER NOT NULL DEFAULT 20,
    bonus_coins    INTEGER NOT NULL DEFAULT 0,
    max_uses       INTEGER NOT NULL DEFAULT 100,
    uses           INTEGER NOT NULL DEFAULT 0,
    active         INTEGER NOT NULL DEFAULT 1,
    expires_at     TEXT,
    created_at     TEXT    NOT NULL
);
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    import os
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
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


# ── Auth ──────────────────────────────────────────────────────────────────────

# ── Plan tiers ────────────────────────────────────────────────────────────────
# Tiers that get FREE edits (no coin charge)
FREE_EDIT_TIERS = {"studio_2week", "studio_max"}
# Tiers that get a promo code on purchase
PROMO_CODE_TIERS = {"studio_2week", "studio_max"}


def _gen_promo_code(email: str) -> str:
    """Generate a unique 35%-off promo code for this user."""
    import secrets
    suffix = secrets.token_hex(4).upper()
    prefix = email.split("@")[0][:6].upper().replace(".", "")
    return f"TT35-{prefix}-{suffix}"


def user_get_plan(email: str) -> dict:
    """Return plan_tier and promo_code for a user."""
    email = email.strip().lower()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT plan_tier, promo_code, promo_used FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return {"plan_tier": "free", "promo_code": None, "promo_used": False}
    return {"plan_tier": row[0], "promo_code": row[1], "promo_used": bool(row[2])}


def user_set_plan(email: str, tier: str) -> str | None:
    """Upgrade user to a plan tier. Returns promo code if applicable."""
    email = email.strip().lower()
    promo = None
    if tier in PROMO_CODE_TIERS:
        promo = _gen_promo_code(email)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE users SET plan_tier=?, promo_code=? WHERE email=?",
            (tier, promo, email),
        )
    return promo


def promo_validate(code: str) -> dict:
    """Check if a promo code is valid and unused. Returns discount info."""
    code = code.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT email, promo_used FROM users WHERE promo_code=?", (code,)
        ).fetchone()
    if not row:
        return {"valid": False, "error": "Invalid promo code."}
    if row[1]:
        return {"valid": False, "error": "This promo code has already been used."}
    return {"valid": True, "discount": 0.35, "email": row[0]}


def promo_apply(code: str) -> None:
    """Mark a promo code as used."""
    code = code.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE users SET promo_used=1 WHERE promo_code=?", (code,))


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def user_register(email: str, password: str) -> dict:
    """Register a new user. Returns {'ok': True, 'user_id': int} or {'ok': False, 'error': str}."""
    email = email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Invalid email address."}
    if len(password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters."}
    try:
        with sqlite3.connect(DB_PATH) as con:
            cur = con.execute(
                "INSERT INTO users(email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, _hash_pw(password), _utc()),
            )
            user_id = int(cur.lastrowid)
            # create coin wallet using email as session_id so it persists
            _ensure_coin_wallet(con, email)
            return {"ok": True, "user_id": user_id, "email": email}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "An account with that email already exists."}


def user_login(email: str, password: str) -> dict:
    """Verify credentials. Returns {'ok': True, 'user_id': int, 'email': str} or {'ok': False, 'error': str}."""
    email = email.strip().lower()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT id, password_hash FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row or row[1] != _hash_pw(password):
        return {"ok": False, "error": "Invalid email or password."}
    return {"ok": True, "user_id": row[0], "email": email}


def user_merge_session(email: str, anon_session_id: str) -> None:
    """Merge coins from an anonymous session into the user's account after login."""
    with sqlite3.connect(DB_PATH) as con:
        anon = con.execute(
            "SELECT coins FROM coin_users WHERE session_id=?", (anon_session_id,)
        ).fetchone()
        if anon and anon[0] > 0:
            # add anon coins to the user account
            con.execute(
                "UPDATE coin_users SET coins = coins + ? WHERE session_id=?",
                (anon[0], email),
            )
            con.execute(
                "INSERT INTO coin_transactions(session_id, type, amount, stripe_session, created_at) "
                "VALUES (?, 'merge', ?, ?, ?)",
                (email, anon[0], f"merge-{anon_session_id}", _utc()),
            )
            # zero out the anon session so it can't be merged again
            con.execute(
                "UPDATE coin_users SET coins=0 WHERE session_id=?", (anon_session_id,)
            )


def _ensure_coin_wallet(con, session_id: str) -> None:
    """Create coin wallet if it doesn't exist (used internally)."""
    con.execute(
        "INSERT OR IGNORE INTO coin_users(session_id, coins, created_at) VALUES (?, 0, ?)",
        (session_id, _utc()),
    )


# ── Coins ──────────────────────────────────────────────────────────────────────
WELCOME_COINS = 5  # Free coins every new user receives on first visit

def coin_get_or_create(session_id: str) -> int:
    """Return the coin balance for session_id, creating the row if needed.
    New users receive WELCOME_COINS for free — only once per session_id."""
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        if row:
            return row[0]
        # New session — grant welcome coins with a unique per-session key
        welcome_key = f"welcome-{session_id}"
        already = con.execute(
            "SELECT id FROM coin_transactions WHERE stripe_session=?", (welcome_key,)
        ).fetchone()
        if already:
            # Row somehow missing but transaction exists — restore with 0
            con.execute(
                "INSERT OR IGNORE INTO coin_users(session_id, coins, created_at) VALUES (?, 0, ?)",
                (session_id, _utc()),
            )
            return 0
        con.execute(
            "INSERT INTO coin_users(session_id, coins, created_at) VALUES (?, ?, ?)",
            (session_id, WELCOME_COINS, _utc()),
        )
        con.execute(
            "INSERT INTO coin_transactions(session_id, type, amount, stripe_session, created_at) "
            "VALUES (?, 'welcome', ?, ?, ?)",
            (session_id, WELCOME_COINS, welcome_key, _utc()),
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


# ── Content Studio ─────────────────────────────────────────────────────────────



# -- Studio Coins (separate inventory from AI coins) --

def studio_coin_get_or_create(session_id: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM studio_coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        if row:
            return row[0]
        con.execute(
            "INSERT INTO studio_coin_users(session_id, coins, created_at) VALUES (?, 0, ?)",
            (session_id, _utc()),
        )
        return 0


def studio_coin_balance(session_id: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM studio_coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        return row[0] if row else 0


def studio_coin_spend(session_id: str, amount: int = 1) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT coins FROM studio_coin_users WHERE session_id=?", (session_id,)
        ).fetchone()
        if not row or row[0] < amount:
            return False
        con.execute(
            "UPDATE studio_coin_users SET coins = coins - ? WHERE session_id=?",
            (amount, session_id),
        )
        con.execute(
            "INSERT INTO studio_coin_transactions(session_id, type, amount, created_at) "
            "VALUES (?, 'spend', ?, ?)",
            (session_id, -amount, _utc()),
        )
        return True


def studio_coin_credit(session_id: str, amount: int, stripe_session: str) -> None:
    with sqlite3.connect(DB_PATH) as con:
        already = con.execute(
            "SELECT id FROM studio_coin_transactions WHERE stripe_session=?", (stripe_session,)
        ).fetchone()
        if already:
            return
        studio_coin_get_or_create(session_id)
        con.execute(
            "UPDATE studio_coin_users SET coins = coins + ? WHERE session_id=?",
            (amount, session_id),
        )
        con.execute(
            "INSERT INTO studio_coin_transactions(session_id, type, amount, stripe_session, created_at) "
            "VALUES (?, 'purchase', ?, ?, ?)",
            (session_id, amount, stripe_session, _utc()),
        )


def studio_coin_merge_session(email: str, anon_sid: str) -> None:
    if not anon_sid or anon_sid == email:
        return
    with sqlite3.connect(DB_PATH) as con:
        anon_row = con.execute(
            "SELECT coins FROM studio_coin_users WHERE session_id=?", (anon_sid,)
        ).fetchone()
        if not anon_row or anon_row[0] == 0:
            return
        studio_coin_get_or_create(email)
        con.execute(
            "UPDATE studio_coin_users SET coins = coins + ? WHERE session_id=?",
            (anon_row[0], email),
        )
        con.execute(
            "INSERT INTO studio_coin_transactions(session_id, type, amount, created_at) "
            "VALUES (?, 'merge', ?, ?)",
            (email, anon_row[0], _utc()),
        )
        con.execute("DELETE FROM studio_coin_users WHERE session_id=?", (anon_sid,))
def studio_save(session_id: str, platform: str, topic: str, tone: str,
                content: str, content_type: str, scheduled_for: str = None) -> int:
    """Save a generated content piece. scheduled_for is ISO date string or None."""
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """INSERT INTO studio_content
               (session_id, platform, topic, tone, content, content_type, scheduled_for, released, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, platform, topic, tone, content, content_type,
             scheduled_for, 1 if scheduled_for is None else 0, _utc()),
        )
        return int(cur.lastrowid)


def studio_release_due(session_id: str, user_email: str = None) -> None:
    """Mark content as released if its scheduled_for date has passed, then email user."""
    today = datetime.now(timezone.utc).date().isoformat()
    with sqlite3.connect(DB_PATH) as con:
        # find items that are newly due
        due = con.execute(
            """SELECT id, platform, content FROM studio_content
               WHERE session_id=? AND released=0 AND scheduled_for<=?""",
            (session_id, today),
        ).fetchall()
        if due:
            con.execute(
                "UPDATE studio_content SET released=1 WHERE session_id=? AND released=0 AND scheduled_for<=?",
                (session_id, today),
            )
            if user_email:
                _send_daily_content_email(user_email, due)


def _send_daily_content_email(to_email: str, items: list) -> None:
    """Send today's unlocked content to the user via email."""
    import smtplib, os
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        return  # email not configured — skip silently
    body_parts = ["<h2>🧠 ThinkTank Content Studio — Today's Posts</h2>"]
    for item in items:
        body_parts.append(f"<h3>📱 {item[1]}</h3><pre style='white-space:pre-wrap'>{item[2]}</pre><hr>")
    body_parts.append("<p><a href='https://www.thinktankapp.net'>Open ThinkTank</a></p>")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "📱 Your ThinkTank content is ready for today"
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText("\n".join([i[2] for i in items]), "plain"))
    msg.attach(MIMEText("".join(body_parts), "html"))
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, to_email, msg.as_string())
    except Exception:
        pass  # fail silently — content still unlocks in the app


def studio_list(session_id: str, user_email: str = None) -> list[dict]:
    """Return all content for a session, releasing any due items first."""
    studio_release_due(session_id, user_email)
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT id, platform, topic, tone, content, content_type,
                      scheduled_for, released, created_at
               FROM studio_content WHERE session_id=?
               ORDER BY scheduled_for ASC, created_at ASC""",
            (session_id,),
        ).fetchall()
    return [_studio_row(r) for r in rows]


def studio_update(content_id: int, new_content: str) -> None:
    """Update content text after a paid edit."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE studio_content SET content=? WHERE id=?",
            (new_content, content_id),
        )


def studio_delete(content_id: int) -> None:
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM studio_content WHERE id=?", (content_id,))


def _studio_row(r) -> dict:
    return {
        "id": r[0], "platform": r[1], "topic": r[2], "tone": r[3],
        "content": r[4], "content_type": r[5], "scheduled_for": r[6],
        "released": bool(r[7]), "created_at": r[8],
    }


# ── Power Tool Sessions & Loyalty ─────────────────────────────────────────────

_LOYALTY_WINDOW_DAYS = 7    # rolling window
_LOYALTY_TRIGGER     = 5    # sessions needed for discount
_LOYALTY_DISCOUNT    = 0.10 # 10% off


def tool_session_record(session_id: str, minutes: int, coins_paid: int) -> None:
    """Record a completed power tool session for loyalty tracking."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO tool_sessions(session_id, minutes, coins_paid, started_at) VALUES (?, ?, ?, ?)",
            (session_id, minutes, coins_paid, _utc()),
        )


def tool_session_count_recent(session_id: str) -> int:
    """Count how many tool sessions this user has started in the past 7 days."""
    cutoff = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .__class__.fromisoformat(
            datetime.now(timezone.utc).isoformat()
        )
    )
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=_LOYALTY_WINDOW_DAYS)).isoformat()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT COUNT(*) FROM tool_sessions WHERE session_id=? AND started_at >= ?",
            (session_id, since),
        ).fetchone()
    return row[0] if row else 0


def tool_loyalty_discount(session_id: str) -> float:
    """
    Return the discount fraction (0.0 or 0.10) to apply to the next session cost.
    The 5th+ session in a rolling 7-day window gets 10% off.
    """
    count = tool_session_count_recent(session_id)
    if count >= _LOYALTY_TRIGGER - 1:   # about to start their 5th (0-indexed: 0,1,2,3 = 4 done)
        return _LOYALTY_DISCOUNT
    return 0.0


def tool_loyalty_status(session_id: str) -> dict:
    """Return loyalty progress info for display in the UI."""
    count = tool_session_count_recent(session_id)
    sessions_until = max(0, _LOYALTY_TRIGGER - 1 - count)
    return {
        "sessions_this_week": count,
        "sessions_until_discount": sessions_until,
        "discount_active": count >= _LOYALTY_TRIGGER - 1,
        "discount_pct": int(_LOYALTY_DISCOUNT * 100),
    }


# ── Persistent Power Tool Session State ───────────────────────────────────────
# Survives page reloads, logouts, and browser refreshes.

def tool_session_save(session_id: str, end_epoch: float, mins_total: int) -> None:
    """Upsert the active session end time to DB so it survives Streamlit reloads."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """INSERT INTO tool_session_state(session_id, end_epoch, mins_total, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                 end_epoch=excluded.end_epoch,
                 mins_total=excluded.mins_total,
                 updated_at=excluded.updated_at""",
            (session_id, end_epoch, mins_total, _utc()),
        )


def tool_session_load(session_id: str) -> dict | None:
    """
    Load a persisted session for this user.
    Returns None if no session exists or if it has already expired.
    """
    import time as _t
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT end_epoch, mins_total FROM tool_session_state WHERE session_id=?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    end_epoch, mins_total = row
    if _t.time() >= end_epoch:
        # expired — clean it up
        tool_session_clear(session_id)
        return None
    return {"end_epoch": end_epoch, "mins_total": mins_total}


def tool_session_clear(session_id: str) -> None:
    """Remove a session record (on expiry or explicit end)."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM tool_session_state WHERE session_id=?", (session_id,))


# ── Persistent Auth (survives server restarts / Railway redeploys) ────────────

def sid_save_auth(session_id: str, email: str) -> None:
    """Tie a logged-in email to a URL session ID so auth survives page reloads."""
    email = email.strip().lower()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sid_auth (
                session_id TEXT PRIMARY KEY,
                email      TEXT NOT NULL,
                saved_at   TEXT NOT NULL
            )"""
        )
        con.execute(
            """INSERT INTO sid_auth(session_id, email, saved_at) VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET email=excluded.email, saved_at=excluded.saved_at""",
            (session_id, email, _utc()),
        )


def sid_get_auth(session_id: str) -> str | None:
    """Return the email tied to this session ID, or None if not found."""
    with sqlite3.connect(DB_PATH) as con:
        # ensure table exists (handles first run before sid_save_auth is called)
        con.execute(
            """CREATE TABLE IF NOT EXISTS sid_auth (
                session_id TEXT PRIMARY KEY,
                email      TEXT NOT NULL,
                saved_at   TEXT NOT NULL
            )"""
        )
        row = con.execute(
            "SELECT email FROM sid_auth WHERE session_id=?", (session_id,)
        ).fetchone()
    return row[0] if row else None


def sid_clear_auth(session_id: str) -> None:
    """Remove the auth binding for this session (on explicit logout)."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM sid_auth WHERE session_id=?", (session_id,))


# -- Sale Promo Codes (admin-controlled, not per-user) ------------------------

def sale_promo_create(code: str, label: str, discount_pct: int = 20,
                      bonus_coins: int = 0, max_uses: int = 100,
                      expires_at: str = None) -> dict:
    """Create a new sale promo code. Returns error dict if code already exists."""
    code = code.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        existing = con.execute(
            "SELECT id FROM sale_promo_codes WHERE code=?", (code,)
        ).fetchone()
        if existing:
            return {"ok": False, "error": f"Code {code} already exists."}
        con.execute(
            """INSERT INTO sale_promo_codes
               (code, label, discount_pct, bonus_coins, max_uses, uses, active, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?)""",
            (code, label, discount_pct, bonus_coins, max_uses, expires_at, _utc()),
        )
    return {"ok": True, "code": code}


def sale_promo_validate(code: str) -> dict:
    """Validate a sale promo code. Returns discount info or error."""
    from datetime import datetime, timezone
    code = code.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            """SELECT id, label, discount_pct, bonus_coins, max_uses, uses, active, expires_at
               FROM sale_promo_codes WHERE code=?""",
            (code,)
        ).fetchone()
    if not row:
        return {"valid": False, "error": "Invalid promo code."}
    _id, label, disc, bonus, max_uses, uses, active, expires_at = row
    if not active:
        return {"valid": False, "error": "This promo code has been deactivated."}
    if max_uses > 0 and uses >= max_uses:
        return {"valid": False, "error": "This promo code has reached its usage limit."}
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at).replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return {"valid": False, "error": "This promo code has expired."}
        except Exception:
            pass
    return {
        "valid": True, "label": label,
        "discount_pct": disc, "bonus_coins": bonus,
        "uses_remaining": max_uses - uses if max_uses > 0 else "unlimited",
    }


def sale_promo_use(code: str) -> bool:
    """Increment usage count. Returns False if code no longer valid."""
    result = sale_promo_validate(code)
    if not result["valid"]:
        return False
    code = code.strip().upper()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE sale_promo_codes SET uses = uses + 1 WHERE code=?", (code,)
        )
    return True


def sale_promo_list() -> list:
    """Return all sale promo codes for admin view."""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            """SELECT id, code, label, discount_pct, bonus_coins, max_uses, uses, active, expires_at, created_at
               FROM sale_promo_codes ORDER BY id DESC"""
        ).fetchall()
    return [
        {"id": r[0], "code": r[1], "label": r[2], "discount_pct": r[3],
         "bonus_coins": r[4], "max_uses": r[5], "uses": r[6],
         "active": bool(r[7]), "expires_at": r[8], "created_at": r[9]}
        for r in rows
    ]


def sale_promo_toggle(code_id: int, active: bool) -> None:
    """Activate or deactivate a promo code."""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE sale_promo_codes SET active=? WHERE id=?",
            (1 if active else 0, code_id)
        )
