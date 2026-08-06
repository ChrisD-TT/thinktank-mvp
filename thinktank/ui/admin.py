"""
ThinkTank UI — Admin tab.
System status, DB stats, Ollama health check, settings.
"""

import streamlit as st
from thinktank.engine import db
from thinktank.engine.ai import is_available
from thinktank.ui.components import card, section_header
from thinktank import config as cfg


def render():
    section_header("⚙️ Admin", "System status and settings")

    # ── Ollama health ─────────────────────────────────────────────────────────
    st.markdown("### 🤖 Ollama Status")
    col_check, _ = st.columns([1, 3])
    with col_check:
        check = st.button("Check Ollama", use_container_width=True)

    if check or st.session_state.get("ollama_checked"):
        st.session_state.ollama_checked = True
        ok, msg = is_available(cfg.OLLAMA_MODEL)
        if ok:
            st.success(f"✅ Ollama is running. Model `{cfg.OLLAMA_MODEL}` is ready.")
        else:
            st.error(f"❌ {msg}")
            st.code(f"ollama serve\nollama pull {cfg.OLLAMA_MODEL}", language="bash")

    # ── DB stats ──────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🗄 Database")
    ideas  = db.count_ideas()
    gates  = len(db.list_gate_history(limit=9999))
    chats  = len(db.chat_list(limit=9999))

    c1, c2, c3 = st.columns(3)
    c1.metric("Ideas stored",    ideas)
    c2.metric("Gate decisions",  gates)
    c3.metric("Chat threads",    chats)

    st.caption(f"DB path: `{cfg.DB_PATH}`")

    # ── Config summary ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 🔧 Config")
    with card():
        st.json({
            "model":            cfg.OLLAMA_MODEL,
            "ollama_url":       cfg.OLLAMA_BASE_URL,
            "db_path":          cfg.DB_PATH,
            "ask_max_turns":    cfg.ASK_MAX_TURNS,
            "gate_thresholds": {
                "abort_risk_≥":     cfg.GATE_ABORT_RISK_AT_OR_ABOVE,
                "proceed_impact_≥": cfg.GATE_PROCEED_MIN_IMPACT,
                "proceed_effort_≤": cfg.GATE_PROCEED_MAX_EFFORT,
                "proceed_risk_≤":   cfg.GATE_PROCEED_MAX_RISK,
                "caution_risk_≥":   cfg.GATE_CAUTION_RISK_AT_OR_ABOVE,
                "caution_effort_≥": cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE,
                "stop_impact_≤":    cfg.GATE_STOP_MAX_IMPACT,
            },
        })

    # ── All gate history ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📜 All Gate History")
    history = db.list_gate_history(limit=50)
    if history:
        for row in history:
            sig   = row["signal"]
            emoji = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(sig, "•")
            st.markdown(
                f"{emoji} **Gate #{row['id']}** — Idea #{row['idea_id']} | "
                f"{row['verdict']} | I{row['impact']}/E{row['effort']}/R{row['risk']}/N{row['novelty']} | "
                f"`{row['created_at']}`"
            )
            st.caption(f"Action: {row['recommended_action']}")
    else:
        st.caption("No gate history yet.")
