"""
ThinkTank — Central configuration.
All tunables live here. No secrets required (Ollama is local).
"""

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL    = "llama3.2"          # change to any model you have pulled
OLLAMA_TIMEOUT  = 300                 # seconds — increase for complex ideas

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = "./thinktank/thinktank.sqlite"

# ── Ask / chat memory ─────────────────────────────────────────────────────────
ASK_MAX_TURNS = 100000                # effectively unlimited — no cap on conversations

# ── Gate thresholds (1–5 scale) ───────────────────────────────────────────────
GATE_ABORT_RISK_AT_OR_ABOVE      = 4
GATE_PROCEED_MIN_IMPACT          = 4
GATE_PROCEED_MAX_EFFORT          = 3
GATE_PROCEED_MAX_RISK            = 2
GATE_CAUTION_RISK_AT_OR_ABOVE    = 3
GATE_CAUTION_EFFORT_AT_OR_ABOVE  = 4
GATE_STOP_MAX_IMPACT             = 2

# ── System persona (used by idea/refine/score/critique/gate modes) ────────────
SYSTEM_PROMPT = """
You are ThinkTank, a forward-thinking creative engineer and strategic sounding board.

North star:
Help ops users make decisions and take action faster, with less risk, in constrained environments.

Behaviors:
- Generate structured outputs exactly as instructed.
- Be concise and practical.
- Prefer experiments and measurable metrics.
- Never add commentary outside the requested structure.
- Always return valid JSON when JSON is requested.
""".strip()

# ── Ask / chat persona (conversational — plain prose, no JSON) ────────────────
ASK_SYSTEM_PROMPT = """
You are ThinkTank, a strategic advisor and creative thinking partner.

Respond in clear, friendly, conversational prose — never use JSON or code blocks unless the user explicitly asks for code.

Be concise, practical, and direct. Use bullet points or numbered lists when they help clarity.
Help the user think through decisions, ideas, risks, and next steps.
""".strip()
