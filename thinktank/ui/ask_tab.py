"""
ThinkTank UI — Ask tab.
Multi-turn chat with Ollama-backed memory stored in SQLite.
"""

import streamlit as st
from thinktank.engine import db, modes
from thinktank.ui.components import section_header


def render():
    section_header("💬 Ask", "Multi-turn assistant with persistent memory")

    # ── Chat selector / creator ───────────────────────────────────────────────
    chats = db.chat_list(limit=50)

    col_select, col_new_title, col_new_btn = st.columns([3, 3, 1])

    with col_select:
        if chats:
            labels   = [f"#{c['id']} — {c['title']}" for c in chats]
            chat_map = {f"#{c['id']} — {c['title']}": c["id"] for c in chats}
            current_chat_id = st.session_state.get("current_chat_id", chats[0]["id"])
            current_label   = next(
                (l for l, cid in chat_map.items() if cid == current_chat_id),
                labels[0],
            )
            chosen = st.selectbox("Active chat", labels,
                                  index=labels.index(current_label),
                                  label_visibility="collapsed")
            st.session_state.current_chat_id = chat_map[chosen]
        else:
            st.info("No chats yet. Create one →")
            st.session_state.current_chat_id = None

    with col_new_title:
        new_title = st.text_input("New chat title", placeholder="Chat title…",
                                   label_visibility="collapsed")
    with col_new_btn:
        if st.button("＋", use_container_width=True):
            title = new_title.strip() or "New Chat"
            cid   = db.chat_new(title)
            st.session_state.current_chat_id = cid
            st.rerun()

    chat_id = st.session_state.get("current_chat_id")
    if not chat_id:
        return

    # ── Message history ───────────────────────────────────────────────────────
    messages = db.chat_get_messages(chat_id, limit=60)

    chat_container = st.container(height=460, border=True)
    with chat_container:
        if not messages:
            st.caption("No messages yet. Ask something below.")
        for msg in messages:
            role    = msg["role"]
            content = msg["content"]
            with st.chat_message(role):
                st.markdown(content)

    # ── Input row ─────────────────────────────────────────────────────────────
    user_input = st.chat_input("Ask ThinkTank anything…")

    if user_input:
        # Optimistically render the user bubble
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)

        with st.spinner("Thinking…"):
            try:
                response = modes.run_ask(user_input, chat_id)
            except Exception as e:
                response = f"⚠️ {e}"

        with chat_container:
            with st.chat_message("assistant"):
                st.markdown(response)

        st.rerun()

    # ── Manual paste helpers ──────────────────────────────────────────────────
    with st.expander("✂️ Manual paste (when AI is unavailable)"):
        paste_text = st.text_area("Paste text", height=80, key="paste_text")
        p1, p2 = st.columns(2)
        with p1:
            if st.button("Save as User message"):
                if paste_text.strip():
                    db.chat_add_message(chat_id, "user", paste_text.strip())
                    st.rerun()
        with p2:
            if st.button("Save as Assistant message"):
                if paste_text.strip():
                    db.chat_add_message(chat_id, "assistant", paste_text.strip())
                    st.rerun()
