"""
ThinkTank UI — Gate tab.
Run Gate decision and view gate history for selected idea.
"""

import streamlit as st
from thinktank.engine import db, modes
from thinktank.ui.components import card, section_header


def render():
    section_header("🚦 Gate", "Go / No-Go decision engine")

    selected_id = st.session_state.get("selected_idea_id")
    if not selected_id:
        st.info("Create or select an idea from the Ideas tab first.")
        return

    idea = db.get_idea(selected_id)
    if not idea:
        st.warning("Selected idea not found.")
        return

    with card():
        st.markdown(f"**Idea #{idea['id']}**")
        st.write(idea["text"])

    col_btn, col_thresh = st.columns([1, 1])
    with col_btn:
        run_gate = st.button("🚦 Run Gate", use_container_width=True, type="primary")
    with col_thresh:
        with st.expander("⚙️ Thresholds"):
            from thinktank import config as cfg
            st.caption("Edit `thinktank/config.py` to change these permanently.")
            st.json({
                "abort_risk_≥":     cfg.GATE_ABORT_RISK_AT_OR_ABOVE,
                "proceed_impact_≥": cfg.GATE_PROCEED_MIN_IMPACT,
                "proceed_effort_≤": cfg.GATE_PROCEED_MAX_EFFORT,
                "proceed_risk_≤":   cfg.GATE_PROCEED_MAX_RISK,
                "caution_risk_≥":   cfg.GATE_CAUTION_RISK_AT_OR_ABOVE,
                "caution_effort_≥": cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE,
                "stop_impact_≤":    cfg.GATE_STOP_MAX_IMPACT,
            })

    if run_gate:
        with st.spinner("Running Score + Critique + Gate…"):
            try:
                result = modes.run_gate(selected_id)
                st.session_state.gate_output = result
            except Exception as e:
                st.error(f"Gate error: {e}")

    gate_state = st.session_state.get("gate_output")
    if gate_state and gate_state.get("idea_id") == selected_id:
        _render_gate_result(gate_state["gate"])

    st.divider()
    st.markdown("### 📜 Gate History")
    history = db.list_gate_history_for_idea(selected_id, limit=20)
    if history:
        for row in history:
            sig = row["signal"]
            color = {"OK": "🟢", "CAUTION": "🟡", "STOP": "🔴"}.get(sig, "⚪")
            with st.expander(
                f"{color} Gate #{row['id']} — {row['verdict']} | "
                f"I{row['impact']}/E{row['effort']}/R{row['risk']}/N{row['novelty']} | {row['created_at']}"
            ):
                st.caption(f"Recommended action: {row['recommended_action']}")
    else:
        st.caption("No gate decisions for this idea yet.")


def _render_gate_result(gate: dict):
    sig = gate["signal"]

    if sig == "OK":
        st.success(f"{gate['signal_emoji']}  {gate['verdict']}")
    elif sig == "CAUTION":
        st.warning(f"{gate['signal_emoji']}  {gate['verdict']}")
    else:
        st.error(f"{gate['signal_emoji']}  {gate['verdict']}")

    s = gate["score"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Impact",  f"{s['impact']}/5")
    c2.metric("Effort",  f"{s['effort']}/5")
    c3.metric("Risk",    f"{s['risk']}/5")
    c4.metric("Novelty", f"{s['novelty']}/5")

    with card():
        st.markdown("**Why:**")
        for item in gate["rationale"]:
            st.markdown(f"- {item}")
        st.markdown(f"**Recommended action:** {gate['recommended_action']}")

    with st.expander("Full Gate JSON"):
        st.json(gate)
