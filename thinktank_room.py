"""
ThinkTank Room — Layers 1, 2 & 3
==================================
Collaborative room with password protection, rules board, group gate voting.
"""

import sqlite3
import html as _html
from datetime import datetime, timezone

from thinktank import config as cfg
from thinktank.engine.gate import compute_gate
from thinktank.engine.ai import chat as ollama_chat

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH     = cfg.DB_PATH
MAX_SEATS   = 5
DEALER_NAME = "ThinkTank AI"

DEALER_SYSTEM_PROMPT = """
You are ThinkTank AI — the dealer at a creative design table.

Your role:
- You are a silent facilitator, not a participant.
- Track every idea posted to this room.
- When 3 or more distinct paths are open and unresolved, surface them clearly
  and ask the team to converge before opening new ones.
- When the team seems stuck or inactive, offer a structured summary of what
  is on the table and ask: "Keep exploring, or are we ready to score?"
- Never pick a winning idea. Never vote. Never override a team decision.
- Every response you give must end with exactly this structure:
    Reason: [why you are saying this]
    Action: [what you are doing]
    Outcome: [what the team should do next]

Rules:
- Be concise. The table is busy.
- One dealer move at a time.
- If the team is converging, stay quiet.
""".strip()

# ── Room schema ───────────────────────────────────────────────────────────────
ROOM_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    topic       TEXT    NOT NULL,
    password    TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'open',
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS room_seats (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id          INTEGER NOT NULL,
    participant_name TEXT    NOT NULL,
    joined_at        TEXT    NOT NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS room_posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id     INTEGER NOT NULL,
    author      TEXT    NOT NULL,
    post_type   TEXT    NOT NULL DEFAULT 'message',
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS room_votes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id          INTEGER NOT NULL,
    post_id          INTEGER NOT NULL,
    participant_name TEXT    NOT NULL,
    impact           INTEGER,
    effort           INTEGER,
    risk             INTEGER,
    novelty          INTEGER,
    voted_at         TEXT    NOT NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (post_id) REFERENCES room_posts(id)
);
"""

# ── DB helpers ────────────────────────────────────────────────────────────────
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_room_schema():
    with get_con() as con:
        con.executescript(ROOM_SCHEMA)
        # migrate existing rooms table if password column missing
        try:
            con.execute("ALTER TABLE rooms ADD COLUMN password TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass  # column already exists


# ── Rooms ─────────────────────────────────────────────────────────────────────
def create_room(name: str, topic: str, password: str = "") -> int:
    with get_con() as con:
        cur = con.execute(
            "INSERT INTO rooms(name, topic, password, status, created_at) VALUES (?,?,?,?,?)",
            (name.strip(), topic.strip(), password.strip(), "open", utc_now()),
        )
        return int(cur.lastrowid)


def list_rooms(limit: int = 30):
    with get_con() as con:
        cur = con.execute(
            "SELECT id, name, topic, password, status, created_at FROM rooms ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


def get_room(room_id: int):
    with get_con() as con:
        cur = con.execute(
            "SELECT id, name, topic, password, status, created_at FROM rooms WHERE id=?",
            (room_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def close_room(room_id: int):
    with get_con() as con:
        con.execute("UPDATE rooms SET status='closed' WHERE id=?", (room_id,))


# ── Seats ─────────────────────────────────────────────────────────────────────
def get_seats(room_id: int):
    with get_con() as con:
        cur = con.execute(
            "SELECT id, participant_name, joined_at FROM room_seats WHERE room_id=? ORDER BY id",
            (room_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def join_room(room_id: int, name: str, password: str = "") -> tuple[bool, str]:
    name = name.strip()
    if not name:
        return False, "Name cannot be empty."
    if name.lower() == DEALER_NAME.lower():
        return False, f'"{DEALER_NAME}" is reserved for the AI dealer.'
    room = get_room(room_id)
    if not room:
        return False, "Room not found."
    # password check
    room_pw = (room.get("password") or "").strip()
    if room_pw and password.strip() != room_pw:
        return False, "Incorrect password. Ask the host for the room password."
    existing = get_seats(room_id)
    for s in existing:
        if s["participant_name"].lower() == name.lower():
            return True, f"Welcome back, {name}."
    if len(existing) >= MAX_SEATS:
        return False, f"Room is full ({MAX_SEATS} seats taken)."
    with get_con() as con:
        con.execute(
            "INSERT INTO room_seats(room_id, participant_name, joined_at) VALUES (?,?,?)",
            (room_id, name, utc_now()),
        )
    return True, f"{name} joined the room."


# ── Posts ─────────────────────────────────────────────────────────────────────
def add_post(room_id: int, author: str, content: str, post_type: str = "message") -> int:
    with get_con() as con:
        cur = con.execute(
            "INSERT INTO room_posts(room_id, author, post_type, content, created_at) VALUES (?,?,?,?,?)",
            (room_id, author, post_type, content.strip(), utc_now()),
        )
        return int(cur.lastrowid)


def get_posts(room_id: int, since_id: int = 0):
    with get_con() as con:
        cur = con.execute(
            """SELECT id, author, post_type, content, created_at
               FROM room_posts WHERE room_id=? AND id > ? ORDER BY id ASC""",
            (room_id, since_id),
        )
        return [dict(r) for r in cur.fetchall()]


def get_post_count(room_id: int) -> int:
    with get_con() as con:
        cur = con.execute("SELECT COUNT(*) FROM room_posts WHERE room_id=?", (room_id,))
        return cur.fetchone()[0]


def build_transcript(room: dict, posts: list) -> str:
    """Build a plain-text transcript of all posts for download."""
    lines = [
        f"ThinkTank Room Transcript",
        f"=" * 40,
        f"Room:    {room['name']}",
        f"Topic:   {room['topic']}",
        f"Status:  {room['status']}",
        f"Created: {room['created_at']}",
        f"=" * 40,
        "",
    ]
    for p in posts:
        ts = p["created_at"][11:16]
        date = p["created_at"][:10]
        lines.append(f"[{date} {ts}] [{p['post_type'].upper()}] {p['author']}")
        lines.append(p["content"])
        lines.append("")
    lines.append(f"--- End of transcript ({len(posts)} posts) ---")
    return "\n".join(lines)


def get_idea_posts(room_id: int):
    with get_con() as con:
        cur = con.execute(
            """SELECT id, author, content, created_at FROM room_posts
               WHERE room_id=? AND post_type='idea' ORDER BY id""",
            (room_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Group Gate ────────────────────────────────────────────────────────────────
def cast_vote(room_id: int, post_id: int, participant_name: str,
              impact: int, effort: int, risk: int, novelty: int):
    with get_con() as con:
        con.execute(
            "DELETE FROM room_votes WHERE room_id=? AND post_id=? AND participant_name=?",
            (room_id, post_id, participant_name),
        )
        con.execute(
            """INSERT INTO room_votes(room_id, post_id, participant_name,
               impact, effort, risk, novelty, voted_at) VALUES (?,?,?,?,?,?,?,?)""",
            (room_id, post_id, participant_name, impact, effort, risk, novelty, utc_now()),
        )


def get_votes_for_post(room_id: int, post_id: int):
    with get_con() as con:
        cur = con.execute(
            """SELECT participant_name, impact, effort, risk, novelty, voted_at
               FROM room_votes WHERE room_id=? AND post_id=? ORDER BY voted_at""",
            (room_id, post_id),
        )
        return [dict(r) for r in cur.fetchall()]


def _avg(values: list) -> float:
    return round(sum(values) / len(values), 1) if values else 0.0


def aggregate_votes(votes: list) -> dict:
    if not votes:
        return {}
    impact  = round(_avg([v["impact"]  for v in votes]))
    effort  = round(_avg([v["effort"]  for v in votes]))
    risk    = round(_avg([v["risk"]    for v in votes]))
    novelty = round(_avg([v["novelty"] for v in votes]))
    return {
        "impact": impact, "effort": effort, "risk": risk, "novelty": novelty,
        "raw_averages": {
            "impact":  _avg([v["impact"]  for v in votes]),
            "effort":  _avg([v["effort"]  for v in votes]),
            "risk":    _avg([v["risk"]    for v in votes]),
            "novelty": _avg([v["novelty"] for v in votes]),
        },
        "voter_count": len(votes),
        "voters": [v["participant_name"] for v in votes],
    }


def fire_group_gate(room_id: int, post_id: int) -> dict:
    votes = get_votes_for_post(room_id, post_id)
    if not votes:
        return {"error": "No votes cast yet."}
    agg   = aggregate_votes(votes)
    score = {"impact": agg["impact"], "effort": agg["effort"],
             "risk": agg["risk"],    "novelty": agg["novelty"]}
    gate  = compute_gate(score, {})
    s     = gate["score"]
    raw   = agg["raw_averages"]
    voters_str = ", ".join(agg["voters"])
    verdict_text = (
        f"GROUP GATE — {gate['signal_emoji']} {gate['verdict']}\n\n"
        f"Averaged scores ({agg['voter_count']} voters: {voters_str})\n"
        f"  Impact:  {raw['impact']} -> {s['impact']}/5\n"
        f"  Effort:  {raw['effort']} -> {s['effort']}/5\n"
        f"  Risk:    {raw['risk']} -> {s['risk']}/5\n"
        f"  Novelty: {raw['novelty']} -> {s['novelty']}/5\n\n"
        f"Why: {' '.join(gate['rationale'])}\n\n"
        f"Recommended action: {gate['recommended_action']}\n\n"
        f"Reason: All seated participants voted.\n"
        f"Action: Gate verdict computed from averaged group scores.\n"
        f"Outcome: {gate['recommended_action']}"
    )
    add_post(room_id, DEALER_NAME, verdict_text, post_type="gate")
    gate["aggregated"] = agg
    return gate


# ── Dealer AI ─────────────────────────────────────────────────────────────────
def dealer_respond(room_id: int, trigger: str) -> str:
    posts = get_posts(room_id)
    history_text = "\n".join(
        f"[{p['author']} — {p['post_type']}] {p['content']}" for p in posts[-30:]
    )
    room = get_room(room_id)
    prompt = (
        f"Current room topic: {room['topic']}\n\n"
        f"Recent room activity:\n{history_text}\n\n"
        f"Trigger: {trigger}\n\nRespond as the dealer."
    )
    try:
        return ollama_chat([
            {"role": "system", "content": DEALER_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ])
    except Exception as e:
        return (
            f"Dealer summary — {len(get_idea_posts(room_id))} idea(s) on the table.\n\n"
            f"Reason: AI backend unavailable ({e}).\n"
            f"Action: Showing manual summary.\n"
            f"Outcome: Make sure Ollama is running (`ollama serve`) then refresh."
        )


# ── Invite link helpers ───────────────────────────────────────────────────────
def _make_invite_url(room_id: int) -> str:
    """Return a shareable URL pre-filled with the room ID."""
    try:
        import streamlit as st
        # st.query_params is a dict-like; build a URL from the current page
        base = "http://localhost:8501"
        return f"{base}/?room={room_id}"
    except Exception:
        return f"?room={room_id}"


# ── Streamlit UI ──────────────────────────────────────────────────────────────
def run_room_app():
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not installed. Run: pip install streamlit")
        return

    try:
        st.set_page_config(page_title="ThinkTank Room", layout="wide", page_icon="🎲")
    except Exception:
        pass

    init_room_schema()

    for key, default in [
        ("room_id", None),
        ("participant_name", ""),
        ("seated", False),
        ("last_post_id", 0),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Auto-join from invite link (?room=<id>) ───────────────────────────────
    # If the user arrives via a shareable link, pre-select the room in session
    # state so the join panel opens directly on that room. We only do this once
    # (when room_id is still None) to avoid overwriting an active session.
    if st.session_state.room_id is None:
        try:
            qp = st.query_params
            invited_room = qp.get("room", None)
            if invited_room:
                rid = int(invited_room)
                room_check = get_room(rid)
                if room_check and room_check["status"] == "open":
                    st.session_state["_invite_room_id"] = rid
        except Exception:
            pass

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("## 🎲 ThinkTank Room")
    st.caption("Collaborative design session — 5 seats + 1 AI dealer")

    # ── Rules expander ────────────────────────────────────────────────────────
    with st.expander("📋  Rules to the ThinkTank Group Messaging Board", expanded=False):
        st.markdown(
            """
            <div style="padding:4px 0 8px;">
                <div style="font-size:0.95rem;font-weight:700;color:#f0f0f0;margin-bottom:16px;">
                    How to use the ThinkTank Group Room
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;">
                    <div style="background:#1f6feb;color:#fff;font-weight:700;font-size:0.8rem;
                                border-radius:50%;min-width:26px;height:26px;display:flex;
                                align-items:center;justify-content:center;">1</div>
                    <div style="color:#c9d1d9;font-size:0.88rem;line-height:1.7;">
                        <strong style="color:#f0f0f0;">Every room needs a host.</strong>
                        The host creates the room by filling out the room name, session topic,
                        a room password, and their name. Share the room name and password
                        with your team so they can join.
                    </div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;">
                    <div style="background:#1f6feb;color:#fff;font-weight:700;font-size:0.8rem;
                                border-radius:50%;min-width:26px;height:26px;display:flex;
                                align-items:center;justify-content:center;">2</div>
                    <div style="color:#c9d1d9;font-size:0.88rem;line-height:1.7;">
                        <strong style="color:#f0f0f0;">Members joining</strong> select the existing
                        room from the list, enter their name, and enter the room password
                        provided by the host to take a seat at the table.
                    </div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;">
                    <div style="background:#1f6feb;color:#fff;font-weight:700;font-size:0.8rem;
                                border-radius:50%;min-width:26px;height:26px;display:flex;
                                align-items:center;justify-content:center;">3</div>
                    <div style="color:#c9d1d9;font-size:0.88rem;line-height:1.7;">
                        <strong style="color:#f0f0f0;">Enjoy a creative space</strong> where multiple
                        people focus on the same conversation with ThinkTank — so nobody branches
                        away from the main idea path. Post messages, ideas, and questions in real time.
                    </div>
                </div>
                <div style="display:flex;gap:12px;align-items:flex-start;">
                    <div style="background:#e3b341;color:#0d1117;font-weight:700;font-size:0.8rem;
                                border-radius:50%;min-width:26px;height:26px;display:flex;
                                align-items:center;justify-content:center;">4</div>
                    <div style="color:#c9d1d9;font-size:0.88rem;line-height:1.7;">
                        <strong style="color:#e3b341;">&#x26A0;&#xFE0F; Important Rule — Room limit is 5 members.</strong>
                        ThinkTank AI is always seat 6 — your silent Creative Idea Dealer.
                        It tracks every idea, surfaces converging paths, and fires the Gate
                        verdict once all members have voted. It never picks sides.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Lobby ─────────────────────────────────────────────────────────────────
    if st.session_state.room_id is None:
        st.divider()
        col_new, col_join = st.columns(2)

        with col_new:
            st.subheader("Start a new room")
            room_name     = st.text_input("Room name", placeholder="Energy Containment Sprint 1")
            room_topic    = st.text_area("Session topic",
                                         placeholder="What problem are we solving today?",
                                         height=90)
            room_password = st.text_input("Room password",
                                          placeholder="Set a password — share with your team",
                                          type="password")
            host_name     = st.text_input("Your name (host)", placeholder="Chris")
            if st.button("Create Room", use_container_width=True):
                if room_name.strip() and room_topic.strip() and host_name.strip():
                    if not room_password.strip():
                        st.warning("Set a room password so only your team can join.")
                    else:
                        rid = create_room(room_name, room_topic, room_password)
                        ok, msg = join_room(rid, host_name, room_password)
                        if ok:
                                st.session_state.room_id = rid
                                st.session_state.participant_name = host_name.strip()
                                st.session_state.seated = True
                                add_post(rid, DEALER_NAME,
                                         f'Room opened: "{room_name}". Topic: {room_topic}',
                                         post_type="dealer")
                                invite_url = _make_invite_url(rid)
                                st.success(
                                    f"✅ Room **{room_name}** created!"
                                )
                                st.markdown(
                                    f"**🔑 Room password:** `{room_password}`  \n"
                                    f"**🔗 Invite link:** `{invite_url}`  \n"
                                    f"Share both with your team."
                                )
                                st.rerun()
                        else:
                            st.error(msg)
                else:
                    st.warning("Fill in room name, topic, and your name.")

        with col_join:
            st.subheader("Join an existing room")
            rooms      = list_rooms()
            open_rooms = [r for r in rooms if r["status"] == "open"]
            if not open_rooms:
                st.info("No open rooms yet. Create one on the left.")
            else:
                labels    = [f"#{r['id']} — {r['name']}" for r in open_rooms]
                id_map    = {f"#{r['id']} — {r['name']}": r["id"] for r in open_rooms}
                # Pre-select room from invite link if present
                _invite_id = st.session_state.get("_invite_room_id")
                _invite_idx = 0
                if _invite_id:
                    _invite_idx = next(
                        (i for i, r in enumerate(open_rooms) if r["id"] == _invite_id), 0
                    )
                sel       = st.selectbox("Select room", labels, index=_invite_idx)
                join_name = st.text_input("Your name", placeholder="Mentor",
                                          key="join_name_input")
                join_pw   = st.text_input("Room password",
                                          placeholder="Enter the password the host shared",
                                          type="password", key="join_password_input")
                if st.button("Join Room", use_container_width=True):
                    if sel and join_name.strip():
                        rid = id_map[sel]
                        ok, msg = join_room(rid, join_name, join_pw)
                        if ok:
                            st.session_state.room_id = rid
                            st.session_state.participant_name = join_name.strip()
                            st.session_state.seated = True
                            add_post(rid, DEALER_NAME,
                                     f"{join_name.strip()} joined the table.",
                                     post_type="dealer")
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Select a room and enter your name.")
        return

    # ── Room UI ───────────────────────────────────────────────────────────────
    room = get_room(st.session_state.room_id)
    if not room:
        st.error("Room not found.")
        st.session_state.room_id = None
        st.rerun()
        return

    seats = get_seats(room["id"])
    me    = st.session_state.participant_name

    top_left, top_right = st.columns([3, 1])
    with top_left:
        status_badge = "🟢 OPEN" if room["status"] == "open" else "🔴 CLOSED"
        st.markdown(
            f"### {room['name']} &nbsp;"
            f"<span style='font-size:0.75rem;color:#57606a'>{status_badge}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"Topic: {room['topic']}")
    with top_right:
        st.caption("Seated")
        for s in seats:
            st.markdown(f"👤 **{s['participant_name']}**")
        st.markdown(f"🤖 *{DEALER_NAME} (dealer)*")
        remaining = MAX_SEATS - len(seats)
        if remaining > 0:
            st.caption(f"{remaining} seat{'s' if remaining != 1 else ''} open")

    st.divider()
    board_col, post_col = st.columns([2, 1])

    with board_col:
        # ── Sliding window: show last 15, archive the rest ──────────────
        WINDOW    = 15
        all_posts = get_posts(room["id"])
        total     = len(all_posts)
        archived  = max(0, total - WINDOW)
        visible   = all_posts[-WINDOW:] if total > WINDOW else all_posts

        tb_left, tb_right = st.columns([3, 1])
        with tb_left:
            st.subheader("Table")
            if archived > 0:
                st.caption(f"📦 {archived} earlier post{'s' if archived != 1 else ''} archived — download transcript to view all")
        with tb_right:
            if total > 0:
                transcript = build_transcript(room, all_posts)
                fname = f"thinktank_{room['name'].replace(' ','_')}_{room['created_at'][:10]}.txt"
                st.download_button(
                    label="📄 Transcript",
                    data=transcript.encode("utf-8"),
                    file_name=fname,
                    mime="text/plain",
                    use_container_width=True,
                )

        posts = visible
        for p in posts:
            is_dealer = p["author"] == DEALER_NAME
            is_idea   = p["post_type"] == "idea"
            is_gate   = p["post_type"] == "gate"
            is_vote   = p["post_type"] == "vote"
            is_ask    = p["post_type"] == "ask"
            if is_dealer or is_gate:
                bg, border = "#1e1433", "#7c5cd8"
            elif is_idea:
                bg, border = "#0d2318", "#2da44e"
            elif is_vote:
                bg, border = "#1a2030", "#3b82d4"
            elif is_ask:
                bg, border = "#1a2030", "#e3b341"
            else:
                bg, border = "#1a1a1a", "#444444"
            icon = ("🤖" if is_dealer else
                    "🚦" if is_gate else
                    "💡" if is_idea else
                    "🗳️" if is_vote else
                    "❓" if is_ask else "💬")
            ts           = p["created_at"][11:16]
            safe_content = _html.escape(p["content"]).replace("\n", "<br>")
            safe_author  = _html.escape(p["author"])
            st.markdown(
                f"""<div style="background:{bg};border-left:3px solid {border};
                    padding:0.75rem 1rem;border-radius:0 6px 6px 0;margin-bottom:0.6rem;">
                    <div style="font-size:0.72rem;color:#aaaaaa;font-weight:600;margin-bottom:0.3rem;">
                    {icon} {safe_author} &middot; {p['post_type']} &middot; {ts}
                    </div>
                    <div style="font-size:0.9rem;color:#f0f0f0;line-height:1.6;">
                    {safe_content}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
        if not posts:
            st.info("The table is empty. Post an idea to start.")
        # Auto-refresh every 8 seconds when inside a room
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=3000, limit=None, key="room_autorefresh")
        except ImportError:
            pass  # optional dependency — falls back to manual refresh

        if st.button("🔄 Refresh table"):
            st.rerun()

    with post_col:
        st.subheader(f"Your move, {me}")
        if room["status"] != "open":
            st.warning("This room is closed. No new posts allowed.")
        else:
            post_type = st.radio(
                "Post type",
                ["message", "idea", "ask"],
                horizontal=True,
                help=(
                    "message = chat with teammates, no AI  |  "
                    "idea = propose something, AI comments  |  "
                    "ask = question for the AI dealer"
                ),
            )

            # Contextual placeholder per type
            placeholder = {
                "message": "Reply to the team… (no AI)",
                "idea":    "Propose your idea… AI will comment",
                "ask":     "Ask the dealer anything… AI will respond",
            }[post_type]

            content = st.text_input(
                "What do you want to put on the table?",
                key="post_content",
                placeholder=placeholder,
            )
            do_post = st.button("Post  ↵", use_container_width=True, type="primary")

            # Fire on Enter OR button click
            _last = st.session_state.get("_last_post", "")
            if (content.strip() and content != _last) or do_post:
                if content.strip():
                    st.session_state["_last_post"] = content
                    add_post(room["id"], me, content, post_type=post_type)

                    # ── AI response rules ──────────────────────────────────
                    if post_type == "idea":
                        idea_count = len(get_idea_posts(room["id"]))
                        trigger = (
                            f'New idea from {me}: "{content}". '
                            f'There are now {idea_count} idea(s) on the table. '
                            f'Comment briefly on this idea, then note any convergence '
                            f'or divergence with other ideas already on the table.'
                        )
                        with st.spinner("Dealer is reviewing the idea…"):
                            dealer_text = dealer_respond(room["id"], trigger)
                        add_post(room["id"], DEALER_NAME, dealer_text, post_type="dealer")

                    elif post_type == "ask":
                        trigger = f'{me} asked: "{content}"'
                        with st.spinner("Dealer is thinking…"):
                            dealer_text = dealer_respond(room["id"], trigger)
                        add_post(room["id"], DEALER_NAME, dealer_text, post_type="dealer")

                    # message type — no AI, just posts to the board
                    st.rerun()
                else:
                    st.warning("Nothing to post.")

            st.divider()
            ideas = get_idea_posts(room["id"])
            if ideas:
                st.subheader(f"Ideas on table ({len(ideas)})")
                for i, idea in enumerate(ideas, 1):
                    short = idea["content"][:80] + ("…" if len(idea["content"]) > 80 else "")
                    st.markdown(f"**{i}.** _{idea['author']}_ — {short}")

                st.divider()
                st.subheader("🗳️ Cast your vote")
                st.caption("Score the idea you want to gate. When all seated participants vote, the dealer fires the verdict.")
                vote_labels    = [f"#{idea['id']} — {idea['content'][:50]}…" for idea in ideas]
                vote_id_map    = {f"#{idea['id']} — {idea['content'][:50]}…": idea["id"] for idea in ideas}
                sel_idea_label = st.selectbox("Select idea to vote on", vote_labels, key="vote_idea_sel")
                sel_post_id    = vote_id_map[sel_idea_label]
                vcol1, vcol2 = st.columns(2)
                with vcol1:
                    v_impact = st.slider("Impact  (1=low → 5=high)", 1, 5, 3, key="v_impact")
                    v_effort = st.slider("Effort  (1=easy → 5=hard)", 1, 5, 3, key="v_effort")
                with vcol2:
                    v_risk    = st.slider("Risk    (1=low → 5=high)", 1, 5, 3, key="v_risk")
                    v_novelty = st.slider("Novelty (1=low → 5=high)", 1, 5, 3, key="v_novelty")
                if st.button("Submit Vote", use_container_width=True):
                    cast_vote(room["id"], sel_post_id, me, v_impact, v_effort, v_risk, v_novelty)
                    existing_votes = get_votes_for_post(room["id"], sel_post_id)
                    seated_count   = len(seats)
                    vote_count     = len(existing_votes)
                    add_post(room["id"], me,
                             f"Voted on idea #{sel_post_id} — Impact:{v_impact} Effort:{v_effort} Risk:{v_risk} Novelty:{v_novelty}",
                             post_type="vote")
                    if vote_count >= seated_count:
                        fire_group_gate(room["id"], sel_post_id)
                    else:
                        remaining = seated_count - vote_count
                        add_post(room["id"], DEALER_NAME,
                                 f"Vote recorded for {me}. {vote_count}/{seated_count} votes in. "
                                 f"Waiting on {remaining} more before the gate fires.\n\n"
                                 f"Reason: Tracking group vote progress.\n"
                                 f"Action: Holding gate until all seats have voted.\n"
                                 f"Outcome: Remaining participants should cast their vote.",
                                 post_type="dealer")
                    st.rerun()
                current_votes = get_votes_for_post(room["id"], sel_post_id)
                if current_votes:
                    st.caption(f"Votes in: {len(current_votes)}/{len(seats)}")
                    for v in current_votes:
                        st.caption(f"  · {v['participant_name']}: I{v['impact']} E{v['effort']} R{v['risk']} N{v['novelty']}")

            if seats and seats[0]["participant_name"] == me:
                st.divider()
                st.subheader("Host controls")
                invite_url = _make_invite_url(room["id"])
                st.markdown(f"**🔗 Invite link:**")
                st.code(invite_url, language=None)
                st.caption("Share this link + the room password with your team.")
                if room["status"] == "open":
                    if st.button("Close & Archive Room", use_container_width=True):
                        close_room(room["id"])
                        add_post(room["id"], DEALER_NAME,
                                 "Room closed by host. Session archived.", post_type="dealer")
                        st.rerun()

            st.divider()
            if st.button("← Leave room (back to lobby)", use_container_width=True):
                st.session_state.room_id = None
                st.session_state.participant_name = ""
                st.session_state.seated = False
                st.session_state.last_post_id = 0
                st.rerun()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_room_schema()
    run_room_app()
