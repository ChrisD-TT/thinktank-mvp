import re
import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ==========================================================
# ThinkTank2.0 - Enterprise-Ready (Copilot integration-ready)
#
# Goals:
# - Offline-first decision engine + memory (SQLite)
# - Optional "brain" via REST (when allowed)
# - JSON output mode for machine consumption
# - Gate command derived dynamically from Score + Critique with thresholds
# - Gate history (audit trail)
# - Ask: multi-turn memory via local chat threads (SQLite)
# - Manual "Paste" commands for human-in-the-loop Copilot usage when APIs are blocked
# - OpenAPI v2 spec printing for Copilot Studio REST Tool import
# ==========================================================

# --------------------------
# CONFIG
# --------------------------
BACKEND_MODE = "mock"   # mock|rest
OUTPUT_MODE = "text"    # text|json

REST_ENDPOINT = ""      # e.g., https://your-gateway.company.com/thinktank2/generate
REST_AUTH_BEARER = ""   # optional bearer token; leave blank if not needed

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
# SYSTEM PROMPT (ASCII-safe)
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

def build_system_prompt(mode: str) -> str:
    if mode == "idea":
        return (SYSTEM_PROMPT_BASE + "\n\n" + RAPID_BOUNCE_FORMAT).strip()
    return SYSTEM_PROMPT_BASE

# --------------------------
# OpenAPI v2 Spec (Copilot Studio REST Tool Import)
# --------------------------
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

# --------------------------
# SQLite schema
# --------------------------
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

# ---- ideas
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

# ---- gate history
def add_gate_history(idea_id: int, verdict: str, signal: str, score: dict, rationale: list, recommended_action: str) -> int:
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
            "id": r[0], "idea_id": r[1], "verdict": r[2], "signal": r[3],
            "impact": r[4], "effort": r[5], "risk": r[6], "novelty": r[7],
            "recommended_action": r[8], "created_at": r[9]
        }
        for r in rows
    ]

# ---- chat memory for Ask:
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
    if CURRENT_CHAT_ID is not None:
        return
    existing = chat_list(limit=1)
    if existing:
        CURRENT_CHAT_ID = existing[0]["id"]
    else:
        CURRENT_CHAT_ID = chat_new("Default Ask Thread")

# --------------------------
# Deterministic JSON builders (mock)
# --------------------------
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

# --------------------------
# Gate computation (dynamic)
# --------------------------
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

# --------------------------
# Text formatters
# --------------------------
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

# --------------------------
# REST backend call
# --------------------------
def call_rest(system_prompt: str, mode: str, user: str = "", messages=None, conversation_id: str = "") -> str:
    if not REST_ENDPOINT:
        return "REST backend selected but REST_ENDPOINT is empty. Set REST_ENDPOINT at top of the file."

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

# --------------------------
# MOCK backend call (deterministic)
# --------------------------
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
        # mock cannot generate novel responses; store turns anyway (via Paste commands if needed)
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

# --------------------------
# Ask multi-turn logic
# --------------------------
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

# --------------------------
# Command parsing
# --------------------------
PAT_IDEA = re.compile(r"^\s*Idea:\s*(.+)\s*$", re.IGNORECASE)
PAT_REFINE = re.compile(r"^\s*Refine\s+(\d+)\s*$", re.IGNORECASE)
PAT_SCORE = re.compile(r"^\s*Score\s+(\d+)\s*$", re.IGNORECASE)
PAT_GATE = re.compile(r"^\s*Gate\s+(\d+)\s*$", re.IGNORECASE)
PAT_CRITIQUE = re.compile(r"^\s*Critique:\s*(.+)\s*$", re.IGNORECASE)
PAT_ASK = re.compile(r"^\s*Ask:\s*(.+)\s*$", re.IGNORECASE)

PAT_LIST = re.compile(r"^\s*List(\s+(\d+))?\s*$", re.IGNORECASE)
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

# Manual ingestion commands (human-in-the-loop)
PAT_PASTE_USER = re.compile(r"^\s*PasteUser:\s*(.+)\s*$", re.IGNORECASE)
PAT_PASTE_ASSISTANT = re.compile(r"^\s*PasteAssistant:\s*(.+)\s*$", re.IGNORECASE)

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
- OpenAPI                  -> print OpenAPI v2 spec for Copilot Studio REST tool import
- Mode: mock|rest          -> switch backend (session only)
- Output: text|json        -> switch output format (session only)
- Help                     -> show this help
""".strip()

# --------------------------
# Main loop
# --------------------------
def main():
    global BACKEND_MODE, OUTPUT_MODE, CURRENT_CHAT_ID
    init_db()
    ensure_default_chat()

    print(HELP_TEXT)
    print("\nBackend mode:", BACKEND_MODE)
    print("Output mode:", OUTPUT_MODE)
    print("Active Ask chat:", CURRENT_CHAT_ID)

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
            CURRENT_CHAT_ID = int(m.group(1))
            print("Active Ask chat set to:", CURRENT_CHAT_ID)
            continue

        m = PAT_CHATLIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            chats = chat_list(limit=n)
            if not chats:
                print("No chats found.")
            else:
                for c in chats:
                    print(f"- Chat#{c['id']} [{c['created_at']}] {c['title']}")
            continue

        m = PAT_CHATSHOW.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            msgs = chat_show(CURRENT_CHAT_ID, limit=n)
            if not msgs:
                print("No messages in this chat yet.")
            else:
                for mm in msgs:
                    print(f"[{mm['created_at']}] {mm['role']}: {mm['content']}")
            continue

        # Idea list
        m = PAT_LIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            items = list_ideas(limit=n)
            if not items:
                print("No ideas saved yet.")
            else:
                for it in items:
                    short = it["text"].replace("\n", " ")
                    if len(short) > 80:
                        short = short[:77] + "..."
                    print(f"- #{it['id']} [{it['created_at']}] {short}")
            continue

        # Gate history
        m = PAT_GATEHIST.match(text)
        if m:
            n = int(m.group(2)) if m.group(2) else 20
            rows = list_gate_history(limit=n)
            if not rows:
                print("No Gate decisions recorded yet.")
            else:
                for r in rows:
                    print(f"- Gate#{r['id']} Idea#{r['idea_id']} {r['signal']} {r['verdict']} "
                          f"(I{r['impact']}/E{r['effort']}/R{r['risk']}/N{r['novelty']}) [{r['created_at']}]")
                    print(f"  Action: {r['recommended_action']}")
            continue

        # Ask (multi-turn)
        m = PAT_ASK.match(text)
        if m:
            question = m.group(1).strip()
            out = ask_with_memory(question)
            print("\n=== Ask ===\n")
            print(out)
            continue

        # Idea
        m = PAT_IDEA.match(text)
        if m:
            idea_text = m.group(1).strip()
            idea_id = save_idea(idea_text)
            out = call_backend(mode="idea", user_text=idea_text)
            print(f"\n=== Rapid Bounce #{idea_id} ===\n")
            print(out)
            continue

        # Refine
        m = PAT_REFINE.match(text)
        if m:
            idea_id = int(m.group(1))
            it = get_idea(idea_id)
            if not it:
                print(f"No idea found for id {idea_id}")
                continue
            out = call_backend(mode="refine", user_text=it["text"])
            print(f"\n=== Refine #{idea_id} ===\n")
            print(out)
            continue

        # Score
        m = PAT_SCORE.match(text)
        if m:
            idea_id = int(m.group(1))
            it = get_idea(idea_id)
            if not it:
                print(f"No idea found for id {idea_id}")
                continue
            out = call_backend(mode="score", user_text=it["text"])
            print(f"\n=== Score #{idea_id} ===\n")
            print(out)
            continue

        # Critique
        m = PAT_CRITIQUE.match(text)
        if m:
            critique_text = m.group(1).strip()
            out = call_backend(mode="critique", user_text=critique_text)
            print("\n=== Critique ===\n")
            print(out)
            continue

        # Gate (dynamic)
        m = PAT_GATE.match(text)
        if m:
            idea_id = int(m.group(1))
            it = get_idea(idea_id)
            if not it:
                print(f"No idea found for id {idea_id}")
                continue

            if BACKEND_MODE == "mock":
                score_obj = score_json()
                critique_obj = critique_json()
            else:
                old = OUTPUT_MODE
                OUTPUT_MODE = "json"
                score_raw = call_backend(mode="score", user_text=it["text"])
                crit_raw = call_backend(mode="critique", user_text=it["text"])
                OUTPUT_MODE = old
                try:
                    score_obj = json.loads(score_raw)
                except Exception:
                    score_obj = {}
                try:
                    critique_obj = json.loads(crit_raw)
                except Exception:
                    critique_obj = {}

            gate = compute_gate(score_obj, critique_obj)
            hist_id = add_gate_history(
                idea_id=idea_id,
                verdict=gate["verdict"],
                signal=gate["signal"],
                score=gate["score"],
                rationale=gate["rationale"],
                recommended_action=gate["recommended_action"],
            )

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

if __name__ == "__main__":
    main()