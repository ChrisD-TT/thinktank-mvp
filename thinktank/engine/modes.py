"""
ThinkTank — Mode service layer.
Each public function is the single source of truth for one ThinkTank mode.
All AI calls go through engine.ai.chat(); all DB writes go through engine.db.
"""

import json
from thinktank.config import SYSTEM_PROMPT, ASK_SYSTEM_PROMPT, ASK_MAX_TURNS
from thinktank.engine import ai, db
from thinktank.engine.gate import compute_gate

# ── Prompt templates ──────────────────────────────────────────────────────────

_IDEA_PROMPT = """You are an idea analysis assistant. Analyse the idea below and respond with ONLY a JSON object using these exact top-level keys: "reframes", "experiments", "feasibility".

- "reframes" must be an object with keys "wild", "balanced", "conservative" — each a single sentence.
- "experiments" must be an array of 2 objects, each with keys "hypothesis", "metric", "collection".
- "feasibility" must be an object with keys "assumptions", "risks", "unknowns", "next_step".

Do not nest experiments inside reframes. Do not add any other text outside the JSON.

Idea: {idea}"""

_REFINE_PROMPT = """You are a planning assistant. Turn the idea below into an actionable plan. Respond with ONLY a JSON object using these exact top-level keys: "objective", "milestones", "tasks", "risks", "next_step".

- "objective": one line string
- "milestones": array of 3 strings
- "tasks": array of 3 objects each with "task" and "acceptance" keys
- "risks": array of 2 strings
- "next_step": one line string

Do not add any other text outside the JSON.

Idea: {idea}"""

_SCORE_PROMPT = """You are a scoring assistant. Score the idea below. Respond with ONLY a JSON object using these exact top-level keys: "impact", "effort", "risk", "novelty", "recommendation", "rationales".

- "impact", "effort", "risk", "novelty": integers 1-5
- "recommendation": one sentence string
- "rationales": object with keys "impact", "effort", "risk", "novelty" — each a short explanation

Higher effort = harder to build. Higher risk = more likely to fail. Do not add any text outside the JSON.

Idea: {idea}"""

_CRITIQUE_PROMPT = """You are a critical reviewer. Adversarially review the idea below. Respond with ONLY a JSON object using these exact top-level keys: "failure_modes", "missing_assumptions", "mitigations", "next_step".

- "failure_modes": array of 3 strings
- "missing_assumptions": array of 2 strings
- "mitigations": array of 3 strings
- "next_step": one line string

Do not add any other text outside the JSON.

Idea: {idea}"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ask_ai(user_content: str, extra_system: str = "") -> str:
    system = SYSTEM_PROMPT + ("\n\n" + extra_system if extra_system else "")
    return ai.chat([
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ])


def _parse_json(raw: str) -> dict:
    """
    Extract and parse a JSON object from a model response.
    Handles leading/trailing prose, markdown fences, truncated JSON,
    and split objects from llama3.2 (merges all top-level dicts found).
    """
    text = raw.strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")

    candidate = text[start:]
    candidate = _auto_close(candidate)

    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    objects = []
    i = 0
    while i < len(candidate):
        if candidate[i] == "{":
            for end in range(len(candidate) - 1, i, -1):
                if candidate[end] == "}":
                    try:
                        obj = json.loads(candidate[i:end + 1])
                        if isinstance(obj, dict):
                            objects.append(obj)
                            i = end + 1
                            break
                    except Exception:
                        continue
            else:
                i += 1
        else:
            i += 1

    if not objects:
        raise ValueError("Could not parse any JSON from response")

    merged = {}
    for obj in objects:
        merged.update(obj)
    return merged


def _auto_close(text: str) -> str:
    """Add missing closing braces/brackets to truncated JSON."""
    stack  = []
    in_str = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    return text + "".join(reversed(stack))


# ── Public mode functions ─────────────────────────────────────────────────────

def run_idea(idea_text: str) -> dict:
    idea_id = db.save_idea(idea_text)
    raw     = _ask_ai(_IDEA_PROMPT.format(idea=idea_text))
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = {"raw": raw}
    return {"idea_id": idea_id, "idea_text": idea_text, "output": parsed}


def run_refine(idea_id: int) -> dict:
    it = db.get_idea(idea_id)
    if not it:
        return {"error": f"No idea found with id {idea_id}"}
    raw = _ask_ai(_REFINE_PROMPT.format(idea=it["text"]))
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = {"raw": raw}
    return {"idea_id": idea_id, "idea_text": it["text"], "output": parsed}


def run_score(idea_id: int) -> dict:
    it = db.get_idea(idea_id)
    if not it:
        return {"error": f"No idea found with id {idea_id}"}
    raw = _ask_ai(_SCORE_PROMPT.format(idea=it["text"]))
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = {"raw": raw}
    return {"idea_id": idea_id, "idea_text": it["text"], "output": parsed}


def run_critique(idea_id: int) -> dict:
    it = db.get_idea(idea_id)
    if not it:
        return {"error": f"No idea found with id {idea_id}"}
    raw = _ask_ai(_CRITIQUE_PROMPT.format(idea=it["text"]))
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = {"raw": raw}
    return {"idea_id": idea_id, "idea_text": it["text"], "output": parsed}


def run_gate(idea_id: int) -> dict:
    it = db.get_idea(idea_id)
    if not it:
        return {"error": f"No idea found with id {idea_id}"}

    score_raw    = _ask_ai(_SCORE_PROMPT.format(idea=it["text"]))
    critique_raw = _ask_ai(_CRITIQUE_PROMPT.format(idea=it["text"]))

    try:
        score_obj = _parse_json(score_raw)
    except Exception:
        score_obj = {}

    try:
        critique_obj = _parse_json(critique_raw)
    except Exception:
        critique_obj = {}

    gate = compute_gate(score_obj, critique_obj)

    hist_id = db.add_gate_history(
        idea_id=idea_id,
        verdict=gate["verdict"],
        signal=gate["signal"],
        score=gate["score"],
        rationale=gate["rationale"],
        recommended_action=gate["recommended_action"],
    )

    return {
        "idea_id":         idea_id,
        "idea_text":       it["text"],
        "gate_history_id": hist_id,
        "gate":            gate,
    }


def run_ask(question: str, chat_id: int) -> str:
    """Multi-turn Ask using SQLite chat memory."""
    history  = db.chat_get_messages(chat_id, limit=ASK_MAX_TURNS * 2)
    messages = [{"role": "system", "content": ASK_SYSTEM_PROMPT}]

    for m in history:
        role = m["role"] if m["role"] in ("user", "assistant") else "user"
        messages.append({"role": role, "content": m["content"]})

    messages.append({"role": "user", "content": question})

    response = ai.chat(messages)

    db.chat_add_message(chat_id, "user",      question)
    db.chat_add_message(chat_id, "assistant", response)

    return response


def ensure_default_chat() -> int:
    """Return the most recent chat id, creating a default one if none exist."""
    chats = db.chat_list(limit=1)
    if chats:
        return chats[0]["id"]
    return db.chat_new("Default Chat")
