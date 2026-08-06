"""
ThinkTank UI — Shared component helpers.
"""

from contextlib import contextmanager
import streamlit as st


@contextmanager
def card():
    """Render children inside a styled container."""
    with st.container(border=True):
        yield


def section_header(title: str, subtitle: str = ""):
    col, _ = st.columns([6, 1])
    with col:
        st.markdown(f"#### {title}")
        if subtitle:
            st.caption(subtitle)


def idea_badge(gate: dict):
    sig   = gate.get("signal", "")
    emoji = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(sig, "")
    verdict = gate.get("verdict", "")
    st.caption(f"Last gate: {emoji} {verdict}")
