import os
import re
import sys
import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ==========================================================
# ThinkTank2.0 - Enterprise-Ready (Single-File Merged Build)
# ==========================================================
#
# Features:
# - Offline-first decision engine + memory (SQLite)
# - Optional REST "brain" backend
# - Text/JSON output modes
# - Dynamic Gate decision from Score + Critique + thresholds
# - Gate history / audit trail
# - Ask multi-turn memory via local chat threads (SQLite)
# - Manual Paste commands for human-in-the-loop workflows
# - OpenAPI v2 spec printing for Copilot Studio REST tool import
# - Streamlit UI + preserved CLI
#
# Run as CLI:
#   python thinktank2.py
#
# Run as Streamlit:
#   streamlit run thinktank2.py
# ==========================================================


# --------------------------
# CONFIG
# --------------------------
BACKEND_MODE = "rest"   # mock|rest
OUTPUT_MODE = "json"    # text|text

REST_ENDPOINT = "http://127.0.0.1:8000/generate"
REST_AUTH_BEARER = ""   # local server does not require bearer by default

DB_PATH = "./thinktank2.sqlite"

# Ask multi-turn memory
ASK_MAX_TURNS = 10
CURRENT_CHAT_ID = None

DB_PATH = "./thinktank2.sqlite"

# Ask multi-turn memory
ASK_MAX_TURNS = 10
CURRENT_CHAT_ID = None


# --------------------------
# Gate thresholds (tunable)
# --------------------------
GATE_ABORT_RISK_AT_OR_ABOVE = 4
GATE_PROCEED_MIN_IMPACT = 4
GATE_PROCEED_MAX_EFFORT = 3
GATE_PROCEED_MAX_RISK = 2
GATE_CAUTION_RISK_AT_OR_ABOVE = 3
GATE_CAUTION_EFFORT_AT_OR_ABOVE = 4
GATE_STOP_MAX_IMPACT = 2

# --------------------------
# SYSTEM PROMPT
# --------------------------
SYSTEM_PROMPT_BASE = """
You are ThinkTank2.0, a forward thinking creative engineer and strategic sounding board.

North star:
Help ops users make decisions and take action faster, with less risk, in constrained environments.

Behaviors:
- Generate structured outputs.
- Be concise and practical.
- Prefer experiments and measurable metrics.
- No web browsing.
""".strip()

RAPID_BOUNCE_FORMAT = """
Return EXACTLY this structure:

Reframes:
- Wild: ...
- Balanced: ...
- Conservative: ...

Experiments:
- Experiment 1:
  - Hypothesis: ...
  - Metric: ...
  - How to collect (offline): ...
- Experiment 2:
  - Hypothesis: ...
  - Metric: ...
  - How to collect (offline): ...

Feasibility:
- Assumptions: ...
- Risks: ...
- Unknowns: ...
- Next step: ... (one line)
""".strip()

INTENT_DESCRIPTIONS = {
    "idea": "Generate structured ideation output with reframes, experiments, and feasibility.",
    "refine": "Turn an idea into milestones, tasks, and acceptance criteria.",
    "critique": "Provide an adversarial review identifying risks, gaps, and mitigations.",
    "score": "Score an idea across impact, effort, risk, and novelty with a recommendation.",
    "gate": "Return a go/no-go verdict derived from score and critique with thresholds and a recommended next action.",
    "ask": "Free-form multi-turn assistant. Uses conversation history for context.",
}


# ==========================================================
# STREAMLIT LOADING / DETECTION
# ==========================================================
def get_streamlit():
    """Lazy import Streamlit only when needed."""
    try:
        import streamlit as st
        return st
    except Exception:
        return None


def is_running_in_streamlit():
    """
    Best-effort Streamlit detection without calling get_script_run_ctx(),
    which can emit warnings in bare CLI mode.
    """
    # Common env vars present in Streamlit runs
    if os.environ.get("STREAMLIT_SERVER_PORT"):
        return True
    if os.environ.get("STREAMLIT_BROWSER_GATHER_USAGE_STATS") is not None:
        return True

    # Fallback: check for Streamlit runtime flag if available
    st = get_streamlit()
    if st is not None:
        try:
            if getattr(st, "_is_running_with_streamlit", False):
                return True
        except Exception:
            pass

    return False


# ==========================================================
# PROMPT / SPEC HELPERS
# ==========================================================
def build_system_prompt(mode: str) -> str:
    if mode == "idea":
        return (SYSTEM_PROMPT_BASE + "\n\n" + RAPID_BOUNCE_FORMAT).strip()
    return SYSTEM_PROMPT_BASE


OPENAPI_V2_SPEC = """\
swagger: "2.0"
info:
  title: ThinkTank2 Gateway
  version: "2.1"
  description: ThinkTank2 agent gateway. Supports text/json output and multi-turn Ask with messages.
host: your-gateway.company.com
basePath: /thinktank2
schemes:
  - https
paths:
  /generate:
    post:
      summary: Generate ThinkTank2 response
      description: Returns output for a given mode. For Ask, pass messages and conversation_id.
      consumes:
        - application/json
      produces:
        - application/json
      parameters:
        - in: body
          name: body
          required: true
          schema:
            type: object
            required: [mode, output_format]
            properties:
              mode:
                type: string
                description: One of idea|refine|critique|score|gate|ask
              output_format:
                type: string
                description: text|json
              system:
                type: string
                description: Optional system instruction (recommended for ask)
              user:
                type: string
                description: Optional user text (used for simple modes)
              conversation_id:
                type: string
                description: Optional conversation identifier for multi-turn ask
              messages:
                type: array
                description: Optional list of chat messages for ask (role/content)
                items:
                  type: object
                  required: [role, content]
                  properties:
                    role:
                      type: string
                      description: system|user|assistant
                    content:
                      type: string
      responses:
        200:
          description: OK
          schema:
            type: object
            properties:
              output_format:
                type: string
              output:
                type: string
"""


# ==========================================================
# DATABASE
# ==========================================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gate_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idea_id INTEGER NOT NULL,
  verdict TEXT NOT NULL,
  signal TEXT NOT NULL,
  impact INTEGER,
  effort INTEGER,
  risk INTEGER,
  novelty INTEGER,
  rationale_json TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (idea_id) REFERENCES ideas(id)
);

CREATE TABLE IF NOT EXISTS chats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (chat_id) REFERENCES chats(id)
);
"""


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA)


def count_rows(table_name: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(f"SELECT COUNT(*) FROM {table_name}")
        row = cur.fetchone()
    return int(row[0]) if row else 0


# --------------------------
# ideas
# --------------------------
def save_idea(text: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO ideas(text, created_at) VALUES (?, ?)",
            (text, utc_now_iso()),
        )
        return int(cur.lastrowid)


def get_idea(idea_id: int):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT id, text, created_at FROM ideas WHERE id=?", (idea_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "text": row[1], "created_at": row[2]}


def list_ideas(limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "SELECT id, text, created_at FROM ideas ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]


def delete_idea(idea_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("DELETE FROM ideas WHERE id=?", (idea_id,))
        return cur.rowcount > 0


# --------------------------
# gate history
# --------------------------
def add_gate_history(
    idea_id: int,
    verdict: str,
    signal: str,
    score: dict,
    rationale: list,
    recommended_action: str
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
                utc_now_iso(),
            ),
        )
        return int(cur.lastrowid)


def list_gate_history(limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty, recommended_action, created_at
            FROM gate_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "idea_id": r[1],
            "verdict": r[2],
            "signal": r[3],
            "impact": r[4],
            "effort": r[5],
            "risk": r[6],
            "novelty": r[7],
            "recommended_action": r[8],
            "created_at": r[9]
        }
        for r in rows
    ]


def list_gate_history_for_idea(idea_id: int, limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty, recommended_action, created_at
            FROM gate_history
            WHERE idea_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (idea_id, limit),
        )
        rows = cur.fetchall()

    return [
        {
            "id": r[0],
            "idea_id": r[1],
            "verdict": r[2],
            "signal": r[3],
            "impact": r[4],
            "effort": r[5],
            "risk": r[6],
            "novelty": r[7],
            "recommended_action": r[8],
            "created_at": r[9],
        }
        for r in rows
    ]


def get_latest_gate_for_idea(idea_id: int):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            SELECT id, idea_id, verdict, signal, impact, effort, risk, novelty, recommended_action, created_at
            FROM gate_history
            WHERE idea_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (idea_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "idea_id": row[1],
        "verdict": row[2],
        "signal": row[3],
        "impact": row[4],
        "effort": row[5],
        "risk": row[6],
        "novelty": row[7],
        "recommended_action": row[8],
        "created_at": row[9],
    }


# --------------------------
# chats
# --------------------------
def chat_new(title: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO chats(title, created_at) VALUES (?, ?)",
            (title, utc_now_iso()),
        )
        return int(cur.lastrowid)


def chat_list(limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "SELECT id, title, created_at FROM chats ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]


def chat_exists(chat_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT 1 FROM chats WHERE id=? LIMIT 1", (chat_id,))
        row = cur.fetchone()
    return row is not None


def chat_add_message(chat_id: int, role: str, content: str) -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "INSERT INTO chat_messages(chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, utc_now_iso()),
        )
        return int(cur.lastrowid)


def chat_get_recent_messages(chat_id: int, max_pairs: int):
    max_msgs = max_pairs * 2 + 10
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE chat_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, max_msgs),
        )
        rows = cur.fetchall()
    rows = list(reversed(rows))
    return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]


def chat_show(chat_id: int, limit: int = 20):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE chat_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        )
        rows = cur.fetchall()
    rows = list(reversed(rows))
    return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]


def ensure_default_chat():
    global CURRENT_CHAT_ID
    if CURRENT_CHAT_ID is not None and chat_exists(CURRENT_CHAT_ID):
        return
    existing = chat_list(limit=1)
    if existing:
        CURRENT_CHAT_ID = existing[0]["id"]
    else:
        CURRENT_CHAT_ID = chat_new("Default Ask Thread")


# ==========================================================
# DETERMINISTIC MOCK BUILDERS
# ==========================================================
def idea_json():
    return {
        "reframes": {
            "wild": "Treat ops planning like an air-traffic control problem with live capacity signals.",
            "balanced": "Standardize intake, prioritize work, and automate handoffs with lightweight templates.",
            "conservative": "Add a consistent checklist and ownership tracking to reduce missed steps.",
        },
        "experiments": [
            {
                "hypothesis": "A single intake format reduces rework.",
                "metric": "Rework rate / clarifying questions per request.",
                "collection": "Track in a spreadsheet for one week.",
            },
            {
                "hypothesis": "Explicit owners reduce delays.",
                "metric": "Time from request to first action.",
                "collection": "Timestamp 10 requests before and after owner assignment.",
            },
        ],
        "feasibility": {
            "assumptions": "Team will adopt a lightweight template.",
            "risks": "Tool fatigue or resistance to change.",
            "unknowns": "Where data should live (SharePoint, local, ticketing).",
            "next_step": "Pilot with one shift and measure rework and time-to-first-action.",
        },
    }


def refine_json():
    return {
        "objective": "Create a local-first planning agent that standardizes ops intake, prioritization, and execution handoffs.",
        "milestones": [
            "Define intake + backlog schema",
            "Build command interface (Idea/Refine/Critique/Score/List/Gate/Ask)",
            "Add scoring and prioritization rules",
            "Add reporting (daily summary, weekly review)",
            "Package for enterprise (Copilot Studio REST tool)",
        ],
        "tasks": [
            {"task": "Create intake template", "acceptance": "10 requests captured consistently with no missing fields"},
            {"task": "Implement SQLite tables", "acceptance": "Ideas can be saved, listed, recalled, deleted"},
            {"task": "Implement Gate thresholds", "acceptance": "Gate verdict is explainable and consistent across runs"},
        ],
        "risks": [
            "Too much structure reduces adoption",
            "Missing integration points (tickets/SharePoint) in restricted environments",
        ],
        "next_step": "Pick one operational workflow to pilot (shift handoff or intake triage).",
    }


def score_json():
    return {
        "impact": 4,
        "effort": 3,
        "risk": 3,
        "novelty": 2,
        "recommendation": "Proceed with a small pilot; prioritize adoption and measurable outcomes.",
        "rationales": {
            "impact": "Directly reduces delays and rework in ops workflows.",
            "effort": "Moderate build; integrations can be phased.",
            "risk": "Adoption risk; constrained environment limits integrations.",
            "novelty": "Execution-focused, not novel tech; good for ops.",
        },
    }


def critique_json():
    return {
        "failure_modes": [
            "Agent becomes a template generator without real operational impact",
            "Inputs are incomplete; outputs feel generic",
            "Users ignore the process because it adds friction",
        ],
        "missing_assumptions": [
            "Where backlog will live long term (ticketing vs SharePoint vs local DB)",
            "Who owns updates and enforcement",
        ],
        "mitigations": [
            "Keep required fields minimal (3-5 fields max)",
            "Make outputs immediately actionable (one next step always)",
            "Pilot with one workflow and track measurable metrics",
        ],
        "next_step": "Define success metrics for the pilot (time-to-first-action, rework rate, missed handoffs).",
    }


# ==========================================================
# GATE COMPUTATION
# ==========================================================
def compute_gate(score: dict, critique: dict) -> dict:
    impact = int(score.get("impact", 0))
    effort = int(score.get("effort", 0))
    risk = int(score.get("risk", 0))
    novelty = int(score.get("novelty", 0))

    failure_modes = critique.get("failure_modes", [])
    missing_assumptions = critique.get("missing_assumptions", [])

    rationale = []
    recommended_action = ""

    if risk >= GATE_ABORT_RISK_AT_OR_ABOVE:
        verdict = "DO NOT PROCEED"
        signal_emoji = "❌"
        signal = "STOP"
        rationale.append(f"Risk is too high (risk={risk} >= {GATE_ABORT_RISK_AT_OR_ABOVE}).")
        if failure_modes:
            rationale.append("Failure modes: " + "; ".join(failure_modes[:2]) + ("..." if len(failure_modes) > 2 else ""))
        recommended_action = "Reduce risk before proceeding: narrow scope, add controls, then re-score."
    else:
        if impact <= GATE_STOP_MAX_IMPACT:
            verdict = "DO NOT PROCEED"
            signal_emoji = "❌"
            signal = "STOP"
            rationale.append(f"Impact is too low (impact={impact} <= {GATE_STOP_MAX_IMPACT}).")
            recommended_action = "Park this or reframe to increase operational impact."
        elif (impact >= GATE_PROCEED_MIN_IMPACT) and (effort <= GATE_PROCEED_MAX_EFFORT) and (risk <= GATE_PROCEED_MAX_RISK):
            verdict = "PROCEED"
            signal_emoji = "✅"
            signal = "OK"
            rationale.append("High impact with manageable effort and risk.")
            recommended_action = "Proceed with a small pilot and track metrics for one week."
        else:
            verdict = "PROCEED WITH CAUTION"
            signal_emoji = "⚠️"
            signal = "CAUTION"
            if risk >= GATE_CAUTION_RISK_AT_OR_ABOVE:
                rationale.append(f"Risk is elevated (risk={risk} >= {GATE_CAUTION_RISK_AT_OR_ABOVE}).")
            if effort >= GATE_CAUTION_EFFORT_AT_OR_ABOVE:
                rationale.append(f"Effort is high (effort={effort} >= {GATE_CAUTION_EFFORT_AT_OR_ABOVE}).")
            if missing_assumptions:
                rationale.append("Missing assumptions: " + "; ".join(missing_assumptions[:2]) + ("..." if len(missing_assumptions) > 2 else ""))
            if not rationale:
                rationale.append("Tradeoffs are mixed; proceed in a controlled way.")
            recommended_action = "Run a limited pilot, validate assumptions, then re-score."

    return {
        "verdict": verdict,
        "signal": signal,
        "signal_emoji": signal_emoji,
        "score": {"impact": impact, "effort": effort, "risk": risk, "novelty": novelty},
        "key_risks": {
            "failure_modes": failure_modes[:5],
            "missing_assumptions": missing_assumptions[:5],
        },
        "thresholds": {
            "abort_risk_at_or_above": GATE_ABORT_RISK_AT_OR_ABOVE,
            "proceed_min_impact": GATE_PROCEED_MIN_IMPACT,
            "proceed_max_effort": GATE_PROCEED_MAX_EFFORT,
            "proceed_max_risk": GATE_PROCEED_MAX_RISK,
            "caution_risk_at_or_above": GATE_CAUTION_RISK_AT_OR_ABOVE,
            "caution_effort_at_or_above": GATE_CAUTION_EFFORT_AT_OR_ABOVE,
            "stop_max_impact": GATE_STOP_MAX_IMPACT,
        },
        "rationale": rationale,
        "recommended_action": recommended_action,
    }


# ==========================================================
# FORMATTERS
# ==========================================================
def format_idea_text(d: dict) -> str:
    return f"""Reframes:
- Wild: {d['reframes']['wild']}
- Balanced: {d['reframes']['balanced']}
- Conservative: {d['reframes']['conservative']}

Experiments:
- Experiment 1:
  - Hypothesis: {d['experiments'][0]['hypothesis']}
  - Metric: {d['experiments'][0]['metric']}
  - How to collect (offline): {d['experiments'][0]['collection']}
- Experiment 2:
  - Hypothesis: {d['experiments'][1]['hypothesis']}
  - Metric: {d['experiments'][1]['metric']}
  - How to collect (offline): {d['experiments'][1]['collection']}

Feasibility:
- Assumptions: {d['feasibility']['assumptions']}
- Risks: {d['feasibility']['risks']}
- Unknowns: {d['feasibility']['unknowns']}
- Next step: {d['feasibility']['next_step']}
""".strip()


def format_refine_text(d: dict) -> str:
    ms = "\n".join([f"{i+1}) {m}" for i, m in enumerate(d["milestones"])])
    tasks = "\n".join([f"- {t['task']}\n  - Accept: {t['acceptance']}" for t in d["tasks"]])
    risks = "\n".join([f"- {r}" for r in d["risks"]])
    return f"""Objective (one line):
{d['objective']}

Milestones:
{ms}

Tasks + acceptance:
{tasks}

Risks:
{risks}

Next step:
{d['next_step']}
""".strip()


def format_score_text(d: dict) -> str:
    r = d["rationales"]
    return f"""Impact: {d['impact']}/5 ({r['impact']})
Effort: {d['effort']}/5 ({r['effort']})
Risk: {d['risk']}/5 ({r['risk']})
Novelty: {d['novelty']}/5 ({r['novelty']})

Recommendation:
{d['recommendation']}
""".strip()


def format_critique_text(d: dict) -> str:
    fm = "\n".join([f"- {x}" for x in d["failure_modes"]])
    ma = "\n".join([f"- {x}" for x in d["missing_assumptions"]])
    mit = "\n".join([f"- {x}" for x in d["mitigations"]])
    return f"""Potential failure modes:
{fm}

Key missing assumptions:
{ma}

Mitigations:
{mit}

Next step:
{d['next_step']}
""".strip()


def format_gate_text(g: dict) -> str:
    why = "\n".join([f"- {x}" for x in g["rationale"]])
    s = g["score"]
    return f"""Gate Decision: {g['signal_emoji']} {g['verdict']}

Score:
- Impact: {s['impact']}/5
- Effort: {s['effort']}/5
- Risk: {s['risk']}/5
- Novelty: {s['novelty']}/5

Why:
{why}

Recommended action:
{g['recommended_action']}
""".strip()


# ==========================================================
# BACKEND CALLS
# ==========================================================
def call_rest(system_prompt: str, mode: str, user: str = "", messages=None, conversation_id: str = "") -> str:
    if not REST_ENDPOINT:
        return "REST backend selected but REST_ENDPOINT is empty. Set REST_ENDPOINT at top of the file or via RestEndpoint command."

    payload = {
        "mode": mode,
        "output_format": OUTPUT_MODE,
        "system": system_prompt,
        "user": user or "",
    }
    if conversation_id:
        payload["conversation_id"] = str(conversation_id)
    if messages is not None:
        payload["messages"] = messages

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        REST_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if REST_AUTH_BEARER:
        req.add_header("Authorization", f"Bearer {REST_AUTH_BEARER}")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            obj = json.loads(body)
            return obj.get("output", body)
    except urllib.error.HTTPError as e:
        try:
            details = e.read().decode("utf-8")
        except Exception:
            details = str(e)
        return f"REST HTTPError {e.code}: {details}"
    except urllib.error.URLError as e:
        return f"REST URLError: {e}"
    except Exception as e:
        return f"REST Error: {e}"


def call_mock(mode: str, user_text: str) -> str:
    if mode == "idea":
        d = idea_json()
        return json.dumps(d, indent=2) if OUTPUT_MODE == "json" else format_idea_text(d)
    if mode == "refine":
        d = refine_json()
        return json.dumps(d, indent=2) if OUTPUT_MODE == "json" else format_refine_text(d)
    if mode == "score":
        d = score_json()
        return json.dumps(d, indent=2) if OUTPUT_MODE == "json" else format_score_text(d)
    if mode == "critique":
        d = critique_json()
        return json.dumps(d, indent=2) if OUTPUT_MODE == "json" else format_critique_text(d)
    if mode == "gate":
        g = compute_gate(score_json(), critique_json())
        return json.dumps(g, indent=2) if OUTPUT_MODE == "json" else format_gate_text(g)
    if mode == "ask":
        if OUTPUT_MODE == "json":
            return json.dumps({"answer": "Ask requires Mode: rest + REST_ENDPOINT to compute novel responses."}, indent=2)
        return "Ask requires Mode: rest and a configured REST_ENDPOINT to compute novel responses."
    return "Unsupported mode."


def call_backend(mode: str, user_text: str, messages=None, conversation_id: str = "") -> str:
    if BACKEND_MODE == "mock":
        return call_mock(mode, user_text)
    if BACKEND_MODE == "rest":
        system = build_system_prompt(mode)
        return call_rest(system_prompt=system, mode=mode, user=user_text, messages=messages, conversation_id=conversation_id)
    return "Unknown BACKEND_MODE. Use Mode: mock or Mode: rest."


# ==========================================================
# ASK / CHAT LOGIC
# ==========================================================
def ask_with_memory(question: str) -> str:
    ensure_default_chat()
    chat_id = CURRENT_CHAT_ID

    history = chat_get_recent_messages(chat_id, max_pairs=ASK_MAX_TURNS)

    system = build_system_prompt("ask")
    messages = [{"role": "system", "content": system}]

    for m in history:
        role = m["role"]
        if role not in ("user", "assistant", "system"):
            role = "user"
        messages.append({"role": role, "content": m["content"]})

    messages.append({"role": "user", "content": question})

    response = call_backend(mode="ask", user_text=question, messages=messages, conversation_id=str(chat_id))

    chat_add_message(chat_id, "user", question)
    chat_add_message(chat_id, "assistant", response)

    return response


# ==========================================================
# SERVICE LAYER (SHARED BY CLI + STREAMLIT)
# ==========================================================
def set_runtime_modes(backend_mode: str = None, output_mode: str = None): ...
def set_rest_config(endpoint: str = None, bearer: str = None): ...
def run_idea(idea_text: str): ...
def run_refine(idea_id: int): ...
def run_score(idea_id: int): ...
def run_critique_for_idea(idea_id: int): ...
def run_gate(idea_id: int): ...
def list_gate_history_for_idea(idea_id: int, limit: int = 20): ...

def set_rest_config(endpoint: str = None, bearer: str = None):
    global REST_ENDPOINT, REST_AUTH_BEARER
    if endpoint is not None:
        REST_ENDPOINT = endpoint.strip()
    if bearer is not None:
        REST_AUTH_BEARER = bearer.strip()


def try_parse_json(text: str, fallback=None):
    try:
        return json.loads(text)
    except Exception:
        return fallback


def render_output_for_mode(raw_output: str):
    if OUTPUT_MODE == "json":
        return try_parse_json(raw_output, raw_output)
    return raw_output


def run_idea(idea_text: str):
    idea_id = save_idea(idea_text)
    output = call_backend(mode="idea", user_text=idea_text)
    return {
        "idea_id": idea_id,
        "idea_text": idea_text,
        "output": output,
        "rendered": render_output_for_mode(output),
        "output_mode": OUTPUT_MODE,
    }


def run_refine(idea_id: int):
    it = get_idea(idea_id)
    if not it:
        return {"error": f"No idea found for id {idea_id}"}
    output = call_backend(mode="refine", user_text=it["text"])
    return {
        "idea_id": idea_id,
        "idea_text": it["text"],
        "output": output,
        "rendered": render_output_for_mode(output),
        "output_mode": OUTPUT_MODE,
    }


def run_score(idea_id: int):
    it = get_idea(idea_id)
    if not it:
        return {"error": f"No idea found for id {idea_id}"}
    output = call_backend(mode="score", user_text=it["text"])
    return {
        "idea_id": idea_id,
        "idea_text": it["text"],
        "output": output,
        "rendered": render_output_for_mode(output),
        "output_mode": OUTPUT_MODE,
    }


def run_critique_for_text(text: str):
    output = call_backend(mode="critique", user_text=text)
    return {
        "input_text": text,
        "output": output,
        "rendered": render_output_for_mode(output),
        "output_mode": OUTPUT_MODE,
    }


def run_critique_for_idea(idea_id: int):
    it = get_idea(idea_id)
    if not it:
        return {"error": f"No idea found for id {idea_id}"}
    output = call_backend(mode="critique", user_text=it["text"])
    return {
        "idea_id": idea_id,
        "idea_text": it["text"],
        "output": output,
        "rendered": render_output_for_mode(output),
        "output_mode": OUTPUT_MODE,
    }


def fetch_score_and_critique_json_for_idea(idea_text: str):
    global OUTPUT_MODE

    if BACKEND_MODE == "mock":
        return score_json(), critique_json()

    old_output = OUTPUT_MODE
    OUTPUT_MODE = "json"
    try:
        score_raw = call_backend(mode="score", user_text=idea_text)
        critique_raw = call_backend(mode="critique", user_text=idea_text)
    finally:
        OUTPUT_MODE = old_output

    score_obj = try_parse_json(score_raw, {})
    critique_obj = try_parse_json(critique_raw, {})
    return score_obj, critique_obj


def run_gate(idea_id: int):
    it = get_idea(idea_id)
    if not it:
        return {"error": f"No idea found for id {idea_id}"}

    score_obj, critique_obj = fetch_score_and_critique_json_for_idea(it["text"])
    gate = compute_gate(score_obj, critique_obj)

    hist_id = add_gate_history(
        idea_id=idea_id,
        verdict=gate["verdict"],
        signal=gate["signal"],
        score=gate["score"],
        rationale=gate["rationale"],
        recommended_action=gate["recommended_action"],
    )

    return {
        "idea_id": idea_id,
        "idea_text": it["text"],
        "gate_history_id": hist_id,
        "gate": gate,
    }


# ==========================================================
# COMMAND PARSING (CLI)
# ==========================================================
PAT_IDEA = re.compile(r"^\s*Idea:\s*(.+)\s*$", re.IGNORECASE)
PAT_REFINE = re.compile(r"^\s*Refine\s+(\d+)\s*$", re.IGNORECASE)
PAT_SCORE = re.compile(r"^\s*Score\s+(\d+)\s*$", re.IGNORECASE)
PAT_GATE = re.compile(r"^\s*Gate\s+(\d+)\s*$", re.IGNORECASE)
PAT_CRITIQUE = re.compile(r"^\s*Critique:\s*(.+)\s*$", re.IGNORECASE)
PAT_ASK = re.compile(r"^\s*Ask:\s*(.+)\s*$", re.IGNORECASE)

PAT_LIST = re.compile(r"^\s*List(\s+(\d+))?\s*$", re.IGNORECASE)
PAT_DELETE = re.compile(r"^\s*Delete\s+(\d+)\s*$", re.IGNORECASE)
PAT_OPENAPI = re.compile(r"^\s*OpenAPI\s*$", re.IGNORECASE)
PAT_HELP = re.compile(r"^\s*Help\s*$", re.IGNORECASE)
PAT_MODE = re.compile(r"^\s*Mode:\s*(mock|rest)\s*$", re.IGNORECASE)
PAT_OUTPUT = re.compile(r"^\s*Output:\s*(text|json)\s*$", re.IGNORECASE)
PAT_GATEHIST = re.compile(r"^\s*GateHistory(\s+(\d+))?\s*$", re.IGNORECASE)

# Chat commands
PAT_CHATNEW = re.compile(r"^\s*ChatNew:\s*(.+)\s*$", re.IGNORECASE)
PAT_CHATUSE = re.compile(r"^\s*ChatUse\s+(\d+)\s*$", re.IGNORECASE)
PAT_CHATLIST = re.compile(r"^\s*ChatList(\s+(\d+))?\s*$", re.IGNORECASE)
PAT_CHATSHOW = re.compile(r"^\s*ChatShow(\s+(\d+))?\s*$", re.IGNORECASE)

# Manual ingestion commands
PAT_PASTE_USER = re.compile(r"^\s*PasteUser:\s*(.+)\s*$", re.IGNORECASE)
PAT_PASTE_ASSISTANT = re.compile(r"^\s*PasteAssistant:\s*(.+)\s*$", re.IGNORECASE)

# REST settings
PAT_REST_ENDPOINT = re.compile(r"^\s*RestEndpoint:\s*(.+)\s*$", re.IGNORECASE)
PAT_REST_BEARER = re.compile(r"^\s*RestBearer:\s*(.+)\s*$", re.IGNORECASE)

HELP_TEXT = """
ThinkTank2.0 (Enterprise-Ready)

Core commands:
- Idea: <text>             -> store idea + Rapid Bounce
- Refine <id>              -> milestones/tasks for an idea
- Score <id>               -> impact/effort/risk/novelty (text or json)
- Critique: <text>         -> adversarial review
- Gate <id>                -> ✅ / ⚠️ / ❌ derived from Score + Critique + thresholds (records history)
- GateHistory [n]          -> show last n Gate decisions (default 20)

Free-form compute (multi-turn):
- Ask: <text>              -> multi-turn assistant using chat memory (requires Mode: rest for novel responses)

Chat memory controls:
- ChatNew: <title>         -> start a new Ask conversation and switch to it
- ChatUse <id>             -> switch active Ask conversation
- ChatList [n]             -> list conversations (default 20)
- ChatShow [n]             -> show recent messages in active chat (default 20)

Manual ingestion (when APIs are blocked):
- PasteUser: <text>        -> store a user turn into active Ask chat
- PasteAssistant: <text>   -> store an assistant turn into active Ask chat

Utilities:
- List [n]                 -> list last n ideas (default 20)
- Delete <id>              -> delete an idea
- OpenAPI                  -> print OpenAPI v2 spec for Copilot Studio REST tool import
- Mode: mock|rest          -> switch backend (session only)
- Output: text|json        -> switch output format (session only)
- RestEndpoint: <url>      -> set REST endpoint (session only)
- RestBearer: <token>      -> set REST bearer token (session only)
- Help                     -> show this help
""".strip()


# ==========================================================
# STREAMLIT UI
# ==========================================================
def streamlit_render_output(st, title: str, value):
    st.markdown(f"### {title}")
    if value is None or value == "":
        st.caption("No output yet.")
        return
    if isinstance(value, (dict, list)):
        st.json(value)
    else:
        st.text(str(value))


def run_streamlit_app():
    st = get_streamlit()
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install with: pip install streamlit")

    global CURRENT_CHAT_ID

    st.set_page_config(page_title="ThinkTank2", layout="wide")
    init_db()
    ensure_default_chat()

    # Session state
    if "selected_idea_id" not in st.session_state:
        ideas = list_ideas(limit=1)
        st.session_state.selected_idea_id = ideas[0]["id"] if ideas else None

    if "rapid_bounce_output" not in st.session_state:
        st.session_state.rapid_bounce_output = None

    if "refine_output" not in st.session_state:
        st.session_state.refine_output = None

    if "score_output" not in st.session_state:
        st.session_state.score_output = None

    if "critique_output" not in st.session_state:
        st.session_state.critique_output = None

    if "gate_output" not in st.session_state:
        st.session_state.gate_output = None

    st.title("ThinkTank2")
    st.caption("Idea compiler / analyzer / store + gate engine with local memory and optional REST brain")

    # Sidebar
    st.sidebar.header("Session Controls")

    backend_mode = st.sidebar.selectbox(
        "Backend Mode",
        ["mock", "rest"],
        index=0 if BACKEND_MODE == "mock" else 1
    )

    output_mode = st.sidebar.selectbox(
        "Output Mode",
        ["text", "json"],
        index=0 if OUTPUT_MODE == "text" else 1
    )

    set_runtime_modes(backend_mode=backend_mode, output_mode=output_mode)

    rest_endpoint = st.sidebar.text_input(
        "REST Endpoint",
        value=REST_ENDPOINT,
        placeholder="https://your-gateway.company.com/thinktank2/generate"
    )
    rest_bearer = st.sidebar.text_input("REST Bearer Token", value=REST_AUTH_BEARER, type="password")
    set_rest_config(endpoint=rest_endpoint, bearer=rest_bearer)

    st.sidebar.markdown(f"**Active Ask Chat:** `{CURRENT_CHAT_ID}`")

    st.sidebar.divider()
    st.sidebar.subheader("Recent Ideas")
    recent_ideas = list_ideas(limit=15)

    if recent_ideas:
        option_labels = [f"#{x['id']} - {x['text'][:40]}" for x in recent_ideas]
        option_to_id = {f"#{x['id']} - {x['text'][:40]}": x["id"] for x in recent_ideas}

        default_idx = 0
        if st.session_state.selected_idea_id is not None:
            for i, label in enumerate(option_labels):
                if option_to_id[label] == st.session_state.selected_idea_id:
                    default_idx = i
                    break

        selected_label = st.sidebar.selectbox("Select Idea", option_labels, index=default_idx)
        st.session_state.selected_idea_id = option_to_id[selected_label]
    else:
        st.sidebar.info("No ideas yet.")

    st.sidebar.divider()
    st.sidebar.subheader("Recent Gate History")
    recent_gates = list_gate_history(limit=5)
    if recent_gates:
        for g in recent_gates:
            st.sidebar.write(
                f"#{g['id']} | Idea#{g['idea_id']} | {g['signal']} | "
                f"I{g['impact']}/E{g['effort']}/R{g['risk']}/N{g['novelty']}"
            )
    else:
        st.sidebar.caption("No gate history yet.")

    tab_ideas, tab_analysis, tab_gate, tab_ask, tab_admin = st.tabs(
        ["Ideas", "Analysis", "Gate", "Ask", "Admin"]
    )

    # Ideas Tab
    with tab_ideas:
        st.subheader("Create Idea")

        idea_text = st.text_area(
            "Enter a new idea",
            height=140,
            placeholder="Example: Standardize shift handoff intake with one lightweight template and ownership tracking."
        )

        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("Save + Rapid Bounce", use_container_width=True):
                if idea_text.strip():
                    result = run_idea(idea_text.strip())
                    st.session_state.selected_idea_id = result["idea_id"]
                    st.session_state.rapid_bounce_output = result["rendered"]
                    st.success(f"Saved as Idea #{result['idea_id']}")
                else:
                    st.warning("Enter an idea first.")

        with col2:
            if st.button("Refresh Ideas", use_container_width=True):
                st.rerun()

        st.divider()
        st.subheader("Selected Idea")

        selected_id = st.session_state.selected_idea_id
        if selected_id:
            idea = get_idea(selected_id)
            if idea:
                st.markdown(f"**Idea #{idea['id']}**")
                st.write(idea["text"])
                st.caption(f"Created: {idea['created_at']}")

                latest_gate = get_latest_gate_for_idea(selected_id)
                if latest_gate:
                    st.info(
                        f"Latest Gate: {latest_gate['signal']} {latest_gate['verdict']} | "
                        f"I{latest_gate['impact']}/E{latest_gate['effort']}/R{latest_gate['risk']}/N{latest_gate['novelty']}"
                    )

                if st.button("Delete Selected Idea"):
                    if delete_idea(selected_id):
                        st.success(f"Deleted Idea #{selected_id}")
                        st.session_state.selected_idea_id = None
                        st.session_state.rapid_bounce_output = None
                        st.session_state.refine_output = None
                        st.session_state.score_output = None
                        st.session_state.critique_output = None
                        st.session_state.gate_output = None
                        st.rerun()
                    else:
                        st.warning("Could not delete selected idea.")
            else:
                st.warning("Selected idea not found.")
        else:
            st.info("No idea selected yet.")

        if st.session_state.rapid_bounce_output is not None:
            st.divider()
            streamlit_render_output(st, "Rapid Bounce Output", st.session_state.rapid_bounce_output)

    # Analysis Tab
    with tab_analysis:
        st.subheader("Refine / Score / Critique")

        selected_id = st.session_state.selected_idea_id
        if not selected_id:
            st.info("Create or select an idea first.")
        else:
            idea = get_idea(selected_id)
            if idea:
                st.markdown(f"**Working on Idea #{idea['id']}**")
                st.write(idea["text"])

                c1, c2, c3 = st.columns(3)

                with c1:
                    if st.button("Refine", use_container_width=True):
                        result = run_refine(selected_id)
                        st.session_state.refine_output = result.get("rendered", result.get("error", ""))

                with c2:
                    if st.button("Score", use_container_width=True):
                        result = run_score(selected_id)
                        st.session_state.score_output = result.get("rendered", result.get("error", ""))

                with c3:
                    if st.button("Critique", use_container_width=True):
                        result = run_critique_for_idea(selected_id)
                        st.session_state.critique_output = result.get("rendered", result.get("error", ""))

                col_left, col_right = st.columns(2)

                with col_left:
                    streamlit_render_output(st, "Refine Output", st.session_state.refine_output)
                    streamlit_render_output(st, "Score Output", st.session_state.score_output)

                with col_right:
                    streamlit_render_output(st, "Critique Output", st.session_state.critique_output)
            else:
                st.warning("Selected idea not found.")

    # Gate Tab
    with tab_gate:
        st.subheader("Gate Decision")

        selected_id = st.session_state.selected_idea_id
        if not selected_id:
            st.info("Create or select an idea first.")
        else:
            idea = get_idea(selected_id)
            if idea:
                st.markdown(f"**Idea #{idea['id']}**")
                st.write(idea["text"])

                with st.expander("Current Thresholds", expanded=False):
                    st.write({
                        "abort_risk_at_or_above": GATE_ABORT_RISK_AT_OR_ABOVE,
                        "proceed_min_impact": GATE_PROCEED_MIN_IMPACT,
                        "proceed_max_effort": GATE_PROCEED_MAX_EFFORT,
                        "proceed_max_risk": GATE_PROCEED_MAX_RISK,
                        "caution_risk_at_or_above": GATE_CAUTION_RISK_AT_OR_ABOVE,
                        "caution_effort_at_or_above": GATE_CAUTION_EFFORT_AT_OR_ABOVE,
                        "stop_max_impact": GATE_STOP_MAX_IMPACT,
                    })

                if st.button("Run Gate", use_container_width=True):
                    result = run_gate(selected_id)
                    st.session_state.gate_output = result

                gate_state = st.session_state.gate_output
                if gate_state and gate_state.get("idea_id") == selected_id:
                    gate = gate_state["gate"]

                    if gate["signal"] == "OK":
                        st.success(f"{gate['signal_emoji']} {gate['verdict']}")
                    elif gate["signal"] == "CAUTION":
                        st.warning(f"{gate['signal_emoji']} {gate['verdict']}")
                    else:
                        st.error(f"{gate['signal_emoji']} {gate['verdict']}")

                    s = gate["score"]
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Impact", s["impact"])
                    c2.metric("Effort", s["effort"])
                    c3.metric("Risk", s["risk"])
                    c4.metric("Novelty", s["novelty"])

                    st.markdown("### Why")
                    for item in gate["rationale"]:
                        st.write(f"- {item}")

                    st.markdown("### Recommended Action")
                    st.write(gate["recommended_action"])

                    with st.expander("Full Gate Object"):
                        st.json(gate)

                st.divider()
                st.markdown("### Gate History for this Idea")
                history = list_gate_history_for_idea(selected_id, limit=20)
                if history:
                    for row in history:
                        st.write(
                            f"Gate#{row['id']} | {row['signal']} {row['verdict']} | "
                            f"I{row['impact']}/E{row['effort']}/R{row['risk']}/N{row['novelty']} | {row['created_at']}"
                        )
                        st.caption(f"Action: {row['recommended_action']}")
                else:
                    st.caption("No gate decisions for this idea yet.")
            else:
                st.warning("Selected idea not found.")

    # Ask Tab
    with tab_ask:
        st.subheader("Ask / Chat")

        chats = chat_list(limit=50)
        if chats:
            chat_labels = [f"Chat#{c['id']} - {c['title']}" for c in chats]
            chat_map = {f"Chat#{c['id']} - {c['title']}": c["id"] for c in chats}

            current_label = None
            for label, cid in chat_map.items():
                if cid == CURRENT_CHAT_ID:
                    current_label = label
                    break

            default_idx = 0
            if current_label in chat_labels:
                default_idx = chat_labels.index(current_label)

            selected_chat_label = st.selectbox("Choose Chat", chat_labels, index=default_idx)
            CURRENT_CHAT_ID = chat_map[selected_chat_label]

        new_chat_title = st.text_input("New Chat Title")
        if st.button("Create New Chat"):
            if new_chat_title.strip():
                CURRENT_CHAT_ID = chat_new(new_chat_title.strip())
                st.success(f"Created Chat #{CURRENT_CHAT_ID}")
                st.rerun()
            else:
                st.warning("Enter a title.")

        st.markdown(f"**Active Chat:** `{CURRENT_CHAT_ID}`")

        messages = chat_show(CURRENT_CHAT_ID, limit=30)
        if messages:
            for msg in messages:
                role = msg["role"].capitalize()
                with st.container():
                    st.markdown(f"**{role}** — {msg['created_at']}")
                    st.write(msg["content"])
                    st.divider()
        else:
            st.caption("No messages yet.")

        ask_text = st.text_area("Ask something", height=120)

        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("Send to Ask", use_container_width=True):
                if ask_text.strip():
                    response = ask_with_memory(ask_text.strip())
                    if response.startswith("REST backend selected but REST_ENDPOINT is empty"):
                        st.warning(response)
                    else:
                        st.success("Response added to chat.")
                    st.rerun()
                else:
                    st.warning("Enter a message first.")

        with c2:
            if st.button("PasteUser", use_container_width=True):
                if ask_text.strip():
                    chat_add_message(CURRENT_CHAT_ID, "user", ask_text.strip())
                    st.success("Saved as user message.")
                    st.rerun()
                else:
                    st.warning("Enter text first.")

        with c3:
            if st.button("PasteAssistant", use_container_width=True):
                if ask_text.strip():
                    chat_add_message(CURRENT_CHAT_ID, "assistant", ask_text.strip())
                    st.success("Saved as assistant message.")
                    st.rerun()
                else:
                    st.warning("Enter text first.")

    # Admin Tab
    with tab_admin:
        st.subheader("Admin / Settings")

        st.markdown("### Runtime State")
        st.write({
            "backend_mode": BACKEND_MODE,
            "output_mode": OUTPUT_MODE,
            "active_chat_id": CURRENT_CHAT_ID,
            "selected_idea_id": st.session_state.selected_idea_id,
            "db_path": DB_PATH,
            "rest_endpoint": REST_ENDPOINT,
            "rest_bearer_configured": bool(REST_AUTH_BEARER),
        })

        st.markdown("### Database Stats")
        st.write({
            "ideas_count": count_rows("ideas"),
            "chat_count": count_rows("chats"),
            "gate_history_count": count_rows("gate_history"),
        })

        st.markdown("### Intent Modes")
        st.write(INTENT_DESCRIPTIONS)

        st.markdown("### OpenAPI v2 Spec")
        st.code(OPENAPI_V2_SPEC, language="yaml")


# ==========================================================
# CLI HELPERS
# ==========================================================
def print_idea_list(items):
    if not items:
        print("No ideas saved yet.")
        return
    for it in items:
        short = it["text"].replace("\n", " ")
        if len(short) > 80:
            short = short[:77] + "..."
        print(f"- #{it['id']} [{it['created_at']}] {short}")


def print_gate_history_rows(rows):
    if not rows:
        print("No Gate decisions recorded yet.")
        return
    for r in rows:
        print(
            f"- Gate#{r['id']} Idea#{r['idea_id']} {r['signal']} {r['verdict']} "
            f"(I{r['impact']}/E{r['effort']}/R{r['risk']}/N{r['novelty']}) [{r['created_at']}]"
        )
        print(f"  Action: {r['recommended_action']}")


def print_chat_list(chats):
    if not chats:
        print("No chats found.")
        return
    for c in chats:
        print(f"- Chat#{c['id']} [{c['created_at']}] {c['title']}")


def print_chat_messages(messages):
    if not messages:
        print("No messages in this chat yet.")
        return
    for mm in messages:
        print(f"[{mm['created_at']}] {mm['role']}: {mm['content']}")


def print_output_block(title: str, content: str):
    print(f"\n=== {title} ===\n")
    print(content)


# ==========================================================
# CLI MAIN LOOP
# ==========================================================
def main_cli():
    global BACKEND_MODE, OUTPUT_MODE, CURRENT_CHAT_ID, REST_ENDPOINT, REST_AUTH_BEARER

    init_db()
    ensure_default_chat()

    print(HELP_TEXT)
    print("\nBackend mode:", BACKEND_MODE)
    print("Output mode:", OUTPUT_MODE)
    print("Active Ask chat:", CURRENT_CHAT_ID)
    print("REST endpoint set:", bool(REST_ENDPOINT))
    print("REST bearer set:", bool(REST_AUTH_BEARER))

    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting ThinkTank2.")
            break

        if not text:
            continue

        if PAT_HELP.match(text):
            print(HELP_TEXT)
            continue

        m = PAT_MODE.match(text)
        if m:
            BACKEND_MODE = m.group(1).lower()
            print("Backend mode set to:", BACKEND_MODE)
            continue

        m = PAT_OUTPUT.match(text)
        if m:
            OUTPUT_MODE = m.group(1).lower()
            print("Output mode set to:", OUTPUT_MODE)
            continue

        m = PAT_REST_ENDPOINT.match(text)
        if m:
            REST_ENDPOINT = m.group(1).strip()
            print("REST endpoint updated.")
            continue

        m = PAT_REST_BEARER.match(text)
        if m:
            REST_AUTH_BEARER = m.group(1).strip()
            print("REST bearer updated.")
            continue

        if PAT_OPENAPI.match(text):
            print("\n=== OpenAPI v2 Spec (Copilot Studio REST Tool Import) ===\n")
            print(OPENAPI_V2_SPEC)
            print("\nNote: Update host/basePath to match your internal gateway.")
            continue

        # Manual ingestion
        m = PAT_PASTE_USER.match(text)
        if m:
            ensure_default_chat()
            msg = m.group(1).strip()
            chat_add_message(CURRENT_CHAT_ID, "user", msg)
            print(f"Saved to chat #{CURRENT_CHAT_ID} as user.")
            continue

        m = PAT_PASTE_ASSISTANT.match(text)
        if m:
            ensure_default_chat()
            msg = m.group(1).strip()
            chat_add_message(CURRENT_CHAT_ID, "assistant", msg)
            print(f"Saved to chat #{CURRENT_CHAT_ID} as assistant.")
            continue

        # Chat controls
        m = PAT_CHATNEW.match(text)
        if m:
            title = m.group(1).strip()
            CURRENT_CHAT_ID = chat_new(title)
            print("New chat created. Active Ask chat:", CURRENT_CHAT_ID)
            continue

        m = PAT_CHATUSE.match(text)
        if m:
            desired_chat_id = int(m.group(1))
            if not chat_exists(desired_chat_id):
                print(f"No chat found for id {desired_chat_id}")
                continue
            CURRENT_CHAT_ID = desired_chat_id
            print("Active Ask chat set to:", CURRENT_CHAT_ID)
            continue

        m = PAT_CHATLIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            chats = chat_list(limit=n)
            print_chat_list(chats)
            continue

        m = PAT_CHATSHOW.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            msgs = chat_show(CURRENT_CHAT_ID, limit=n)
            print_chat_messages(msgs)
            continue

        # Idea list
        m = PAT_LIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            items = list_ideas(limit=n)
            print_idea_list(items)
            continue

        m = PAT_DELETE.match(text)
        if m:
            idea_id = int(m.group(1))
            ok = delete_idea(idea_id)
            print(f"Deleted idea #{idea_id}" if ok else f"No idea found for id {idea_id}")
            continue

        # Gate history
        m = PAT_GATEHIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            rows = list_gate_history(limit=n)
            print_gate_history_rows(rows)
            continue

        # Ask
        m = PAT_ASK.match(text)
        if m:
            question = m.group(1).strip()
            out = ask_with_memory(question)
            print_output_block("Ask", out)
            continue

        # Idea
        m = PAT_IDEA.match(text)
        if m:
            idea_text = m.group(1).strip()
            result = run_idea(idea_text)
            print_output_block(f"Rapid Bounce #{result['idea_id']}", result["output"])
            continue

        # Refine
        m = PAT_REFINE.match(text)
        if m:
            idea_id = int(m.group(1))
            result = run_refine(idea_id)
            if "error" in result:
                print(result["error"])
            else:
                print_output_block(f"Refine #{idea_id}", result["output"])
            continue

        # Score
        m = PAT_SCORE.match(text)
        if m:
            idea_id = int(m.group(1))
            result = run_score(idea_id)
            if "error" in result:
                print(result["error"])
            else:
                print_output_block(f"Score #{idea_id}", result["output"])
            continue

        # Critique
        m = PAT_CRITIQUE.match(text)
        if m:
            critique_text = m.group(1).strip()
            result = run_critique_for_text(critique_text)
            print_output_block("Critique", result["output"])
            continue

        # Gate
        m = PAT_GATE.match(text)
        if m:
            idea_id = int(m.group(1))
            result = run_gate(idea_id)
            if "error" in result:
                print(result["error"])
                continue

            gate = result["gate"]
            hist_id = result["gate_history_id"]

            print(f"\n=== Gate #{idea_id} (history #{hist_id}) ===\n")
            if OUTPUT_MODE == "json":
                gate_out = dict(gate)
                gate_out["idea_id"] = idea_id
                gate_out["gate_history_id"] = hist_id
                print(json.dumps(gate_out, indent=2))
            else:
                print(format_gate_text(gate))
            continue

        print("Unrecognized command. Type Help for options.")


# ==========================================================
# ENTRY POINT
# ==========================================================
if __name__ == "__main__":
    init_db()
    if is_running_in_streamlit():
        run_streamlit_app()
    else:
        main_cli()