"""
ThinkTank UI — Analysis tab.
Refine / Score / Critique for a selected idea.
"""

import streamlit as st
from thinktank.engine import db, modes
from thinktank.ui.components import card, section_header


def render():
    section_header("🔬 Analysis", "Refine, score, and critique your selected idea")

    selected_id = st.session_state.get("selected_idea_id")
    if not selected_id:
        st.info("Create or select an idea from the Ideas tab first.")
        return

    idea = db.get_idea(selected_id)
    if not idea:
        st.warning("Selected idea not found.")
        return

    with card():
        st.markdown(f"**Working on Idea #{idea['id']}**")
        st.write(idea["text"])

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔧 Refine", use_container_width=True, type="primary"):
            with st.spinner("Refining…"):
                try:
                    result = modes.run_refine(selected_id)
                    st.session_state.refine_output = result.get("output", result.get("error"))
                except Exception as e:
                    st.session_state.refine_output = {"error": str(e)}

    with col2:
        if st.button("📊 Score", use_container_width=True, type="primary"):
            with st.spinner("Scoring…"):
                try:
                    result = modes.run_score(selected_id)
                    st.session_state.score_output = result.get("output", result.get("error"))
                except Exception as e:
                    st.session_state.score_output = {"error": str(e)}

    with col3:
        if st.button("⚔️ Critique", use_container_width=True, type="primary"):
            with st.spinner("Critiquing…"):
                try:
                    result = modes.run_critique(selected_id)
                    st.session_state.critique_output = result.get("output", result.get("error"))
                except Exception as e:
                    st.session_state.critique_output = {"error": str(e)}

    st.divider()

    left, right = st.columns(2)

    with left:
        _render_refine(st.session_state.get("refine_output"))
        _render_score(st.session_state.get("score_output"))

    with right:
        _render_critique(st.session_state.get("critique_output"))


def _render_refine(d):
    if d is None:
        return
    st.markdown("### 🔧 Refine")
    if not isinstance(d, dict) or "error" in d:
        st.error(str(d))
        return
    if "raw" in d:
        st.text(d["raw"])
        return
    with card():
        st.markdown(f"**Objective:** {d.get('objective', '—')}")
        st.markdown("**Milestones:**")
        for i, m in enumerate(d.get("milestones", []), 1):
            st.markdown(f"{i}. {m}")
        st.markdown("**Tasks:**")
        for t in d.get("tasks", []):
            st.markdown(f"- **{t.get('task', '')}** — Accept: {t.get('acceptance', '')}")
        st.markdown("**Risks:**")
        for r in d.get("risks", []):
            st.markdown(f"- {r}")
        st.markdown(f"**Next step:** {d.get('next_step', '—')}")


def _render_score(d):
    if d is None:
        return
    st.markdown("### 📊 Score")
    if not isinstance(d, dict) or "error" in d:
        st.error(str(d))
        return
    if "raw" in d:
        st.text(d["raw"])
        return
    with card():
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Impact",  f"{d.get('impact',  '?')}/5")
        c2.metric("Effort",  f"{d.get('effort',  '?')}/5")
        c3.metric("Risk",    f"{d.get('risk',    '?')}/5")
        c4.metric("Novelty", f"{d.get('novelty', '?')}/5")
        st.markdown(f"**Recommendation:** {d.get('recommendation', '—')}")
        rats = d.get("rationales", {})
        if rats:
            with st.expander("Rationales"):
                for k, v in rats.items():
                    st.markdown(f"**{k.capitalize()}:** {v}")


def _render_critique(d):
    if d is None:
        return
    st.markdown("### ⚔️ Critique")
    if not isinstance(d, dict) or "error" in d:
        st.error(str(d))
        return
    if "raw" in d:
        st.text(d["raw"])
        return
    with card():
        st.markdown("**Failure modes:**")
        for f in d.get("failure_modes", []):
            st.markdown(f"- {f}")
        st.markdown("**Missing assumptions:**")
        for a in d.get("missing_assumptions", []):
            st.markdown(f"- {a}")
        st.markdown("**Mitigations:**")
        for m in d.get("mitigations", []):
            st.markdown(f"- {m}")
        st.markdown(f"**Next step:** {d.get('next_step', '—')}")
