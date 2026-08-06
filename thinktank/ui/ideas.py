"""
ThinkTank UI — Ideas tab.
Create ideas, view selected idea, run Rapid Bounce.
"""

import streamlit as st
from thinktank.engine import db, modes
from thinktank.ui.components import card, section_header, idea_badge


def render():
    section_header("💡 Ideas", "Create and explore your ideas")

    # ── Create new idea ───────────────────────────────────────────────────────
    st.markdown("#### New Idea")
    idea_text = st.text_area(
        "idea_input",
        height=100,
        placeholder="e.g. Standardise shift handoff intake with one lightweight template and ownership tracking.",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        run_btn  = st.button("💾 Save + Rapid Bounce", use_container_width=True, type="primary")
    with col2:
        save_btn = st.button("Save Only", use_container_width=True)

    if run_btn:
        if not idea_text.strip():
            st.warning("Enter an idea first.")
        else:
            with st.spinner("Running Rapid Bounce…"):
                try:
                    result = modes.run_idea(idea_text.strip())
                    st.session_state.selected_idea_id    = result["idea_id"]
                    st.session_state.rapid_bounce_output = result["output"]
                    st.success(f"✅ Saved as Idea #{result['idea_id']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    if save_btn:
        if not idea_text.strip():
            st.warning("Enter an idea first.")
        else:
            idea_id = db.save_idea(idea_text.strip())
            st.session_state.selected_idea_id = idea_id
            st.success(f"✅ Saved as Idea #{idea_id}")
            st.rerun()

    st.divider()

    # ── Selected idea detail ──────────────────────────────────────────────────
    selected_id = st.session_state.get("selected_idea_id")
    if not selected_id:
        st.info("No idea selected yet. Create one above or pick one from the sidebar.")
        return

    idea = db.get_idea(selected_id)
    if not idea:
        st.warning("Selected idea not found.")
        return

    with card():
        st.markdown(f"**Idea #{idea['id']}**")
        st.write(idea["text"])
        st.caption(f"Created: {idea['created_at']}")
        latest_gate = db.get_latest_gate_for_idea(selected_id)
        if latest_gate:
            idea_badge(latest_gate)
        if st.button("🗑 Delete This Idea", key="delete_idea"):
            if db.delete_idea(selected_id):
                for key in ("selected_idea_id", "rapid_bounce_output",
                            "refine_output", "score_output",
                            "critique_output", "gate_output"):
                    st.session_state.pop(key, None)
                st.success("Idea deleted.")
                st.rerun()

    # ── Rapid Bounce output ───────────────────────────────────────────────────
    rb = st.session_state.get("rapid_bounce_output")
    if rb:
        st.divider()
        st.markdown("**Rapid Bounce**")
        _render_rapid_bounce(rb)


def _render_rapid_bounce(d):
    from thinktank.engine.modes import _parse_json

    # Case 1: raw string (old session state or parse never ran)
    if isinstance(d, str):
        try:
            d = _parse_json(d)
        except Exception:
            st.warning("Could not parse AI response. Raw output:")
            st.code(d, language="json")
            return

    # Case 2: {"raw": "..."} — parse failed silently earlier, retry now
    if isinstance(d, dict) and "raw" in d and len(d) == 1:
        try:
            d = _parse_json(d["raw"])
        except Exception:
            st.warning("Could not parse AI response. Raw output:")
            st.code(d["raw"], language="json")
            return

    if not isinstance(d, dict):
        st.warning("Unexpected output format.")
        st.code(str(d), language="json")
        return

    # ── Reframes ──────────────────────────────────────────────────────────────
    reframes = d.get("reframes", {})
    # Handle both dict and list formats from the model
    if isinstance(reframes, list):
        labels = ["🌪 Wild", "⚖️ Balanced", "🛡 Conservative"]
        cols = st.columns(len(reframes))
        for i, item in enumerate(reframes):
            with cols[i]:
                with card():
                    st.markdown(f"**{labels[i] if i < len(labels) else f'Reframe {i+1}'}**")
                    # Item may be "Wild: some text" or just "some text"
                    text = str(item)
                    if ":" in text:
                        text = text.split(":", 1)[1].strip()
                    st.write(text)
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            with card():
                st.markdown("**🌪 Wild**")
                st.write(reframes.get("wild", "—"))
        with c2:
            with card():
                st.markdown("**⚖️ Balanced**")
                st.write(reframes.get("balanced", "—"))
        with c3:
            with card():
                st.markdown("**🛡 Conservative**")
                st.write(reframes.get("conservative", "—"))

    # ── Experiments ───────────────────────────────────────────────────────────
    experiments = d.get("experiments", [])
    if experiments:
        st.markdown("#### 🧪 Experiments")
        for i, exp in enumerate(experiments, 1):
            if isinstance(exp, dict):
                hyp = exp.get("hypothesis", "")
                with st.expander(f"Experiment {i}: {hyp[:80]}{'…' if len(hyp) > 80 else ''}"):
                    st.markdown(f"**Hypothesis:** {hyp or '—'}")
                    st.markdown(f"**Metric:** {exp.get('metric', '—')}")
                    col_val = exp.get("collection", "—")
                    # collection might be a list
                    if isinstance(col_val, list):
                        col_val = ", ".join(str(v) for v in col_val)
                    st.markdown(f"**How to collect:** {col_val}")
            else:
                with st.expander(f"Experiment {i}"):
                    st.write(str(exp))

    # ── Feasibility ───────────────────────────────────────────────────────────
    feas = d.get("feasibility", {})
    if feas:
        st.markdown("#### 📋 Feasibility")
        if isinstance(feas, dict):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Assumptions:** {feas.get('assumptions', '—')}")
                st.markdown(f"**Risks:** {feas.get('risks', '—')}")
            with c2:
                st.markdown(f"**Unknowns:** {feas.get('unknowns', '—')}")
                st.markdown(f"**Next step:** {feas.get('next_step', '—')}")
        else:
            st.write(str(feas))
