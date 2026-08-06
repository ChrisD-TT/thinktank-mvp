"""
ThinkTank — Streamlit UI entry point.
Run: streamlit run app.py
"""

import os
import streamlit as st
import thinktank_room as _room

os.makedirs("thinktank", exist_ok=True)

from thinktank.engine.db import (
    init_db, save_idea, get_idea, list_ideas, delete_idea,
    get_latest_gate_for_idea, add_gate_history, list_gate_history,
    list_gate_history_for_idea, chat_new, chat_list, chat_add_message,
    chat_get_messages, chat_delete,
)
from thinktank.engine.modes import (
    run_idea, run_refine, run_score, run_critique, run_gate,
    run_ask, ensure_default_chat,
)
from thinktank import config as cfg

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="ThinkTank", page_icon="🧠", layout="wide")

# Hide the Streamlit deploy button
st.markdown(
    "<style>div.stAppDeployButton { display: none !important; }</style>",
    unsafe_allow_html=True,
)

# ==============================================================================
# RENDER HELPERS
# ==============================================================================
def _fmt_ts(iso_str: str) -> str:
    """Format a UTC ISO timestamp into a readable short form."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except Exception:
        return iso_str


def _render_chat_message(content: str):
    """Render an Ask chat message as clean readable text."""
    import json as _json
    text = content.strip() if content else ""
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = _json.loads(text)
            st.json(parsed)
            return
        except Exception:
            pass
    st.markdown(text)


def _safe_parse(d):
    from thinktank.engine.modes import _parse_json
    if isinstance(d, dict) and list(d.keys()) == ["raw"]:
        try:
            return _parse_json(d["raw"])
        except Exception:
            pass
    return d


def _coerce_list(val):
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val.strip():
        import re
        items = re.split(r'(?<=[.!?])\s+|[;]\s*', val.strip())
        return [i.strip() for i in items if i.strip()]
    return []


def _render_refine(d):
    d = _safe_parse(d)
    if not isinstance(d, dict) or "raw" in d:
        st.text(d.get("raw", str(d)) if isinstance(d, dict) else str(d))
        return
    st.markdown(f"**Objective:** {d.get('objective', '—')}")
    milestones = d.get("milestones", [])
    if milestones:
        st.markdown("**Milestones:**")
        for i, m in enumerate(milestones, 1):
            st.markdown(f"{i}. {m}")
    tasks = d.get("tasks", [])
    if tasks:
        st.markdown("**Tasks:**")
        for t in tasks:
            if isinstance(t, dict):
                st.markdown(f"- **{t.get('task','—')}**  \n  ✔ {t.get('acceptance','—')}")
    risks = d.get("risks", [])
    if risks:
        st.markdown("**Risks:**")
        for r in risks:
            st.markdown(f"- ⚠️ {r}")
    st.markdown(f"**Next step:** {d.get('next_step', '—')}")


def _render_score(d):
    d = _safe_parse(d)
    if not isinstance(d, dict) or "raw" in d:
        st.text(d.get("raw", str(d)) if isinstance(d, dict) else str(d))
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Impact",  f"{d.get('impact','?')}/5")
    c2.metric("Effort",  f"{d.get('effort','?')}/5")
    c3.metric("Risk",    f"{d.get('risk','?')}/5")
    c4.metric("Novelty", f"{d.get('novelty','?')}/5")
    rec = d.get("recommendation", "")
    if rec:
        st.info(f"**Recommendation:** {rec}")
    rats = d.get("rationales", {})
    if rats and isinstance(rats, dict):
        with st.expander("Rationales"):
            for k, v in rats.items():
                st.markdown(f"**{k.capitalize()}:** {v}")


def _render_critique(d):
    d = _safe_parse(d)
    if not isinstance(d, dict) or "raw" in d:
        raw_text = d.get("raw", str(d)) if isinstance(d, dict) else str(d)
        import re
        clean = re.sub(r'^\{|\}$', '', raw_text.strip())
        clean = re.sub(r'"(\w+)":\s*', r'**\1:** ', clean)
        clean = re.sub(r'[\[\]"]', '', clean)
        st.markdown(clean)
        return
    failures    = _coerce_list(d.get("failure_modes", []))
    assumptions = _coerce_list(d.get("missing_assumptions", []))
    mitigations = _coerce_list(d.get("mitigations", []))
    if failures:
        st.markdown("**Failure Modes:**")
        for f in failures:
            st.error(f"❌ {f}")
    if assumptions:
        st.markdown("**Missing Assumptions:**")
        for a in assumptions:
            st.warning(f"⚠️ {a}")
    if mitigations:
        st.markdown("**Mitigations:**")
        for m in mitigations:
            st.success(f"✅ {m}")
    ns = d.get("next_step", "")
    if ns:
        st.markdown(f"**Next step:** {ns}")


def _render_bounce(d):
    if d is None:
        return
    if not isinstance(d, dict):
        st.text(str(d))
        return

    reframes = d.get("reframes", {})
    if isinstance(reframes, dict) and reframes:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**🔥 Wild**")
            st.info(reframes.get("wild", "—"))
        with c2:
            st.markdown("**⚖️ Balanced**")
            st.info(reframes.get("balanced", "—"))
        with c3:
            st.markdown("**🛡️ Conservative**")
            st.info(reframes.get("conservative", "—"))
    elif isinstance(reframes, list):
        cols = st.columns(len(reframes))
        labels = ["🔥 Wild", "⚖️ Balanced", "🛡️ Conservative"]
        for i, item in enumerate(reframes):
            with cols[i]:
                st.markdown(f"**{labels[i] if i < len(labels) else f'Reframe {i+1}'}**")
                text = str(item)
                if ":" in text:
                    text = text.split(":", 1)[1].strip()
                st.info(text)

    experiments = d.get("experiments", [])
    if experiments:
        st.markdown("#### 🧪 Experiments")
        for i, exp in enumerate(experiments, 1):
            if isinstance(exp, dict):
                hyp = exp.get("hypothesis", "")
                with st.expander(f"Experiment {i}: {hyp[:80]}"):
                    st.markdown(f"**Hypothesis:** {hyp or '—'}")
                    st.markdown(f"**Metric:** {exp.get('metric', '—')}")
                    col_val = exp.get("collection", "—")
                    if isinstance(col_val, list):
                        col_val = ", ".join(str(v) for v in col_val)
                    st.markdown(f"**How to collect:** {col_val}")

    feas = d.get("feasibility", {})
    if feas and isinstance(feas, dict):
        st.markdown("#### 🔍 Feasibility")
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown(f"**Assumptions:** {feas.get('assumptions', '—')}")
            st.markdown(f"**Risks:** {feas.get('risks', '—')}")
        with fc2:
            st.markdown(f"**Unknowns:** {feas.get('unknowns', '—')}")
            st.markdown(f"**Next step:** {feas.get('next_step', '—')}")


# ── Init ──────────────────────────────────────────────────────────────────────
init_db()

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "selected_idea_id":    None,
    "rapid_bounce_output": None,
    "refine_output":       None,
    "score_output":        None,
    "critique_output":     None,
    "gate_output":         None,
    "current_chat_id":     None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.current_chat_id is None:
    st.session_state.current_chat_id = ensure_default_chat()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 ThinkTank")
    st.caption("Powered by Ollama · " + cfg.OLLAMA_MODEL)
    st.divider()

    st.subheader("Recent Ideas")
    recent = list_ideas(limit=15)
    if recent:
        labels = [f"#{x['id']} - {x['text'][:40]}" for x in recent]
        id_map  = {f"#{x['id']} - {x['text'][:40]}": x["id"] for x in recent}
        cur     = st.session_state.selected_idea_id
        idx     = next((i for i, l in enumerate(labels) if id_map[l] == cur), 0)
        chosen  = st.selectbox("Select Idea", labels, index=idx)
        new_id  = id_map[chosen]
        if new_id != st.session_state.selected_idea_id:
            st.session_state.selected_idea_id    = new_id
            st.session_state.rapid_bounce_output = None
            st.session_state.refine_output       = None
            st.session_state.score_output        = None
            st.session_state.critique_output     = None
            st.session_state.gate_output         = None
            st.rerun()
    else:
        st.info("No ideas yet.")

    st.divider()
    st.subheader("Recent Gate History")
    gates = list_gate_history(limit=5)
    if gates:
        for g in gates:
            em = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(g["signal"], "❓")
            st.write(f"#{g['id']} | Idea#{g['idea_id']} | {em} {g['signal']} | "
                     f"I{g['impact']}/E{g['effort']}/R{g['risk']}/N{g['novelty']}")
    else:
        st.caption("No gate history yet.")

    st.divider()
    # Single, clean donation widget
    st.markdown(
        """
        <div style="text-align:center;padding:10px 0 4px;">
            <div style="font-size:0.78rem;color:#888;letter-spacing:0.08em;margin-bottom:8px;">
                SUPPORT THE CREATOR
            </div>
            <a href="https://paypal.me/CDovico" target="_blank" rel="noopener"
               style="display:inline-block;background:#003087;color:#fff;
                      text-decoration:none;font-size:0.8rem;font-weight:600;
                      padding:8px 20px;border-radius:4px;letter-spacing:0.06em;">
                &#x2665; Donate via PayPal
            </a>
            <div style="font-size:0.65rem;color:#555;margin-top:6px;">paypal.me/CDovico</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ask, tab_ideas, tab_analysis, tab_gate, tab_room, tab_admin = st.tabs(
    ["💬 Ask", "💡 Ideas", "📊 Analysis", "🚦 Gate", "🎲 Room", "⚙️ Admin"]
)

# ==============================================================================
# IDEAS TAB
# ==============================================================================
with tab_ideas:
    st.subheader("Create Idea")

    idea_text = st.text_area(
        "Enter a new idea", height=140,
        placeholder="Example: Standardize shift handoff intake with one lightweight template and ownership tracking."
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Save + Rapid Bounce", use_container_width=True, type="primary"):
            if idea_text.strip():
                with st.spinner("Running Rapid Bounce…"):
                    try:
                        result = run_idea(idea_text.strip())
                        st.session_state.selected_idea_id    = result["idea_id"]
                        st.session_state.rapid_bounce_output = result["output"]
                        st.success(f"✅ Saved as Idea #{result['idea_id']} — scroll down for output")
                    except Exception as e:
                        err = str(e)
                        if "Cannot reach Ollama" in err or "ollama" in err.lower():
                            st.error("🔌 Ollama is offline. Run `ollama serve` then try again.")
                        else:
                            st.error(f"Error: {err}")
            else:
                st.warning("Enter an idea first.")
    with col2:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    st.divider()
    st.subheader("Selected Idea")

    sel = st.session_state.selected_idea_id
    if sel:
        idea = get_idea(sel)
        if idea:
            st.markdown(f"**Idea #{idea['id']}**")
            st.write(idea["text"])
            st.caption(f"Created: {_fmt_ts(idea['created_at'])}")

            lg = get_latest_gate_for_idea(sel)
            if lg:
                em = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(lg["signal"], "❓")
                st.info(f"Latest Gate: {em} {lg['signal']} — {lg['verdict']} | "
                        f"I{lg['impact']}/E{lg['effort']}/R{lg['risk']}/N{lg['novelty']}")

            if st.button("🗑️ Delete Selected Idea"):
                if delete_idea(sel):
                    st.success(f"Deleted Idea #{sel}")
                    for k in ("selected_idea_id","rapid_bounce_output","refine_output",
                              "score_output","critique_output","gate_output"):
                        st.session_state[k] = None
                    st.rerun()
        else:
            st.warning("Selected idea not found.")
    else:
        st.info("No idea selected yet.")

    if st.session_state.rapid_bounce_output:
        st.divider()
        st.subheader("Rapid Bounce Output")
        _render_bounce(st.session_state.rapid_bounce_output)

# ==============================================================================
# ANALYSIS TAB
# ==============================================================================
with tab_analysis:
    st.subheader("Refine / Score / Critique")

    sel = st.session_state.selected_idea_id
    if not sel:
        st.info("Create or select an idea first.")
    else:
        idea = get_idea(sel)
        if idea:
            st.markdown(f"**Working on Idea #{idea['id']}**")
            st.write(idea["text"])

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("📝 Refine", use_container_width=True, type="primary"):
                    with st.spinner("Refining…"):
                        try:
                            r = run_refine(sel)
                            st.session_state.refine_output = r.get("output", r.get("error"))
                        except Exception as e:
                            err = str(e)
                            st.session_state.refine_output = "🔌 Ollama offline — run `ollama serve`" if "ollama" in err.lower() or "Cannot reach" in err else err
            with c2:
                if st.button("📈 Score", use_container_width=True, type="primary"):
                    with st.spinner("Scoring…"):
                        try:
                            r = run_score(sel)
                            st.session_state.score_output = r.get("output", r.get("error"))
                        except Exception as e:
                            err = str(e)
                            st.session_state.score_output = "🔌 Ollama offline — run `ollama serve`" if "ollama" in err.lower() or "Cannot reach" in err else err
            with c3:
                if st.button("🔍 Critique", use_container_width=True, type="primary"):
                    with st.spinner("Critiquing…"):
                        try:
                            r = run_critique(sel)
                            st.session_state.critique_output = r.get("output", r.get("error"))
                        except Exception as e:
                            err = str(e)
                            st.session_state.critique_output = "🔌 Ollama offline — run `ollama serve`" if "ollama" in err.lower() or "Cannot reach" in err else err

            left, right = st.columns(2)
            with left:
                if st.session_state.refine_output:
                    st.markdown("### 📝 Refine")
                    st.divider()
                    _render_refine(st.session_state.refine_output)
                if st.session_state.score_output:
                    st.divider()
                    st.markdown("### 📈 Score")
                    st.divider()
                    _render_score(st.session_state.score_output)
            with right:
                if st.session_state.critique_output:
                    st.markdown("### 🔍 Critique")
                    st.divider()
                    _render_critique(st.session_state.critique_output)
        else:
            st.warning("Selected idea not found.")

# ==============================================================================
# GATE TAB
# ==============================================================================
with tab_gate:
    st.subheader("Gate Decision")

    sel = st.session_state.selected_idea_id
    if not sel:
        st.info("Create or select an idea first.")
    else:
        idea = get_idea(sel)
        if idea:
            st.markdown(f"**Idea #{idea['id']}**")
            st.write(idea["text"])

            with st.expander("Current Thresholds"):
                st.json({
                    "abort_risk_>=":     cfg.GATE_ABORT_RISK_AT_OR_ABOVE,
                    "proceed_impact_>=": cfg.GATE_PROCEED_MIN_IMPACT,
                    "proceed_effort_<=": cfg.GATE_PROCEED_MAX_EFFORT,
                    "proceed_risk_<=":   cfg.GATE_PROCEED_MAX_RISK,
                    "caution_risk_>=":   cfg.GATE_CAUTION_RISK_AT_OR_ABOVE,
                    "caution_effort_>=": cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE,
                    "stop_impact_<=":    cfg.GATE_STOP_MAX_IMPACT,
                })

            if st.button("🚦 Run Gate", use_container_width=True, type="primary"):
                with st.spinner("Running Score + Critique + Gate…"):
                    try:
                        result = run_gate(sel)
                        st.session_state.gate_output = result
                    except Exception as e:
                        err = str(e)
                        if "Cannot reach Ollama" in err or "ollama" in err.lower():
                            st.error("🔌 Ollama is offline. Run `ollama serve` then try again.")
                        else:
                            st.error(f"Gate error: {err}")

            gs = st.session_state.gate_output
            if gs and gs.get("idea_id") == sel:
                gate = gs["gate"]
                sig  = gate["signal"]

                if sig == "OK":
                    st.success(f"{gate['signal_emoji']} {gate['verdict']}")
                elif sig == "CAUTION":
                    st.warning(f"{gate['signal_emoji']} {gate['verdict']}")
                else:
                    st.error(f"{gate['signal_emoji']} {gate['verdict']}")

                s = gate["score"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Impact",  s["impact"])
                c2.metric("Effort",  s["effort"])
                c3.metric("Risk",    s["risk"])
                c4.metric("Novelty", s["novelty"])

                st.markdown("### Why")
                for item in gate["rationale"]:
                    st.markdown(f"- {item}")

                st.divider()
                st.markdown("### Recommended Action")
                st.info(gate["recommended_action"])

                kr = gate.get("key_risks", {})
                failures = kr.get("failure_modes", [])
                missing  = kr.get("missing_assumptions", [])
                if failures or missing:
                    with st.expander("🔑 Key Risks Detail"):
                        if failures:
                            st.markdown("**Failure Modes:**")
                            for f in failures:
                                st.error(f"❌ {f}")
                        if missing:
                            st.markdown("**Missing Assumptions:**")
                            for a in missing:
                                st.warning(f"⚠️ {a}")

            st.divider()
            st.markdown("### Gate History for this Idea")
            history = list_gate_history_for_idea(sel, limit=20)
            if history:
                for row in history:
                    em = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(row["signal"], "❓")
                    with st.container(border=True):
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            st.markdown(f"{em} **{row['verdict']}** — Gate #{row['id']}")
                            st.caption(f"I{row['impact']}/E{row['effort']}/R{row['risk']}/N{row['novelty']}  ·  {_fmt_ts(row['created_at'])}")
                        with col_b:
                            st.caption(row["recommended_action"])
            else:
                st.caption("No gate decisions for this idea yet.")
        else:
            st.warning("Selected idea not found.")

# ==============================================================================
# ASK TAB
# ==============================================================================
with tab_ask:
    st.subheader("Ask / Chat")

    chats   = chat_list(limit=50)
    chat_id = st.session_state.current_chat_id

    if chats:
        labels  = [f"Chat#{c['id']} - {c['title']}" for c in chats]
        cid_map = {f"Chat#{c['id']} - {c['title']}": c["id"] for c in chats}
        cur_lbl = next((l for l, cid in cid_map.items() if cid == chat_id), labels[0])
        chosen  = st.selectbox("Choose Chat", labels, index=labels.index(cur_lbl))
        st.session_state.current_chat_id = cid_map[chosen]
        chat_id = cid_map[chosen]

    nc1, nc2 = st.columns([3, 1])
    with nc1:
        new_title = st.text_input("New Chat Title", placeholder="e.g. Strategy session")
    with nc2:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("➕ New Chat", use_container_width=True):
            if new_title.strip():
                new_id = chat_new(new_title.strip())
                st.session_state.current_chat_id = new_id
                st.success(f"Created Chat #{new_id}")
                st.rerun()
            else:
                st.warning("Enter a title.")

    if chat_id:
        dc1, dc2 = st.columns([1, 4])
        with dc1:
            if st.button("🗑️ Delete This Chat"):
                if chat_delete(chat_id):
                    st.success("Chat deleted.")
                    st.session_state.current_chat_id = ensure_default_chat()
                    st.rerun()
        with dc2:
            # Transcript download for this chat
            messages_all = chat_get_messages(chat_id, limit=100000) if chat_id else []
            if messages_all:
                lines = [f"ThinkTank Chat Transcript", "=" * 40, ""]
                for m in messages_all:
                    ts = _fmt_ts(m["created_at"])
                    lines.append(f"[{ts}] {m['role'].upper()}")
                    lines.append(m["content"])
                    lines.append("")
                lines.append(f"--- End ({len(messages_all)} messages) ---")
                transcript_txt = "\n".join(lines)
                st.download_button(
                    label="📄 Download Transcript",
                    data=transcript_txt.encode("utf-8"),
                    file_name=f"thinktank_chat_{chat_id}.txt",
                    mime="text/plain",
                )

    st.divider()

    messages = chat_get_messages(chat_id, limit=30) if chat_id else []
    if messages:
        for msg in messages:
            with st.chat_message(msg["role"]):
                _render_chat_message(msg["content"])
                st.caption(_fmt_ts(msg["created_at"]))
    else:
        st.caption("No messages yet — ask something below.")

    ask_text = st.text_area("Ask something", height=120, key="ask_input",
                            placeholder="Ask ThinkTank anything…")
    a1, a2, a3 = st.columns(3)

    with a1:
        if st.button("💬 Send", use_container_width=True, type="primary"):
            if ask_text.strip() and chat_id:
                with st.spinner("Thinking…"):
                    try:
                        run_ask(ask_text.strip(), chat_id)
                        st.rerun()
                    except Exception as e:
                        err = str(e)
                        if "Cannot reach Ollama" in err or "ollama" in err.lower():
                            st.error("🔌 Ollama is offline. Run `ollama serve` then try again.")
                        else:
                            st.error(err)
            else:
                st.warning("Enter a message first.")
    with a2:
        if st.button("📋 Save as User", use_container_width=True):
            if ask_text.strip() and chat_id:
                chat_add_message(chat_id, "user", ask_text.strip())
                st.success("Saved as user message.")
                st.rerun()
    with a3:
        if st.button("📋 Save as Assistant", use_container_width=True):
            if ask_text.strip() and chat_id:
                chat_add_message(chat_id, "assistant", ask_text.strip())
                st.success("Saved as assistant message.")
                st.rerun()

# ==============================================================================
# ROOM TAB
# ==============================================================================
with tab_room:
    _room.init_room_schema()
    _room.run_room_app()

# ==============================================================================
# ADMIN TAB
# ==============================================================================
with tab_admin:
    st.subheader("⚙️ Admin / Settings")

    from thinktank.engine.ai import is_available
    st.markdown("### 🔌 Ollama Status")
    if st.button("Check Ollama Connection", type="primary"):
        ok, msg = is_available(cfg.OLLAMA_MODEL)
        if ok:
            st.success(f"✅ Ollama is running · Model `{cfg.OLLAMA_MODEL}` is ready")
        else:
            st.error(f"❌ {msg}")
            st.code(f"ollama serve\nollama pull {cfg.OLLAMA_MODEL}", language="bash")

    st.divider()

    st.markdown("### 📝 Configuration")
    st.caption("Edit `thinktank/config.py` to change any of these settings.")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**AI Model**")
        with st.container(border=True):
            st.markdown(f"**Model:** `{cfg.OLLAMA_MODEL}`")
            st.markdown(f"**Ollama URL:** `{cfg.OLLAMA_BASE_URL}`")
            st.markdown(f"**Timeout:** `{cfg.OLLAMA_TIMEOUT}s`")

        st.markdown("**Storage**")
        with st.container(border=True):
            st.markdown(f"**DB Path:** `{cfg.DB_PATH}`")
            st.markdown(f"**Ask Memory:** Unlimited (`{cfg.ASK_MAX_TURNS:,}` turns max)")

    with col2:
        st.markdown("**Gate Thresholds** *(1–5 scale)*")
        with st.container(border=True):
            t = {
                "🔴 Abort if risk >=":      cfg.GATE_ABORT_RISK_AT_OR_ABOVE,
                "✅ Proceed if impact >=":  cfg.GATE_PROCEED_MIN_IMPACT,
                "✅ Proceed if effort <=":  cfg.GATE_PROCEED_MAX_EFFORT,
                "✅ Proceed if risk <=":    cfg.GATE_PROCEED_MAX_RISK,
                "⚠️ Caution if risk >=":   cfg.GATE_CAUTION_RISK_AT_OR_ABOVE,
                "⚠️ Caution if effort >=": cfg.GATE_CAUTION_EFFORT_AT_OR_ABOVE,
                "🔴 Stop if impact <=":    cfg.GATE_STOP_MAX_IMPACT,
            }
            for label, val in t.items():
                st.markdown(f"**{label}:** `{val}`")

    st.divider()

    st.markdown("### 📊 Database Stats")
    ideas_count = len(list_ideas(limit=99999))
    gates_count = len(list_gate_history(limit=99999))
    chats_count = len(chat_list(limit=99999))
    s1, s2, s3 = st.columns(3)
    s1.metric("Ideas stored",   ideas_count)
    s2.metric("Gate decisions", gates_count)
    s3.metric("Chat threads",   chats_count)

    st.divider()

    st.markdown("### ♥ Support the Creator")
    st.markdown(
        """
        <div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;
                    padding:24px 28px;text-align:center;max-width:480px;margin:0 auto;">
            <div style="font-size:1.05rem;font-weight:700;color:#f0f0f0;margin-bottom:6px;">
                Chris Dovico
            </div>
            <div style="font-size:0.85rem;color:#888;margin-bottom:18px;line-height:1.6;">
                ThinkTank is free and open-source. If it saves you time or helps your team
                make better decisions, consider buying me a coffee.
            </div>
            <a href="https://paypal.me/CDovico" target="_blank" rel="noopener"
               style="display:inline-block;background:#003087;color:#fff;
                      text-decoration:none;font-size:0.9rem;font-weight:700;
                      padding:12px 36px;border-radius:6px;letter-spacing:0.05em;">
                &#x2665;&nbsp; Donate via PayPal
            </a>
            <div style="font-size:0.72rem;color:#555;margin-top:10px;">
                paypal.me/CDovico &nbsp;&bull;&nbsp; Any amount is appreciated
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    st.markdown("### 📋 All Gate History")
    all_gates = list_gate_history(limit=50)
    if all_gates:
        for row in all_gates:
            em = {"OK": "✅", "CAUTION": "⚠️", "STOP": "❌"}.get(row["signal"], "❓")
            with st.container(border=True):
                ca, cb = st.columns([3, 1])
                with ca:
                    st.markdown(f"{em} **{row['verdict']}** — Idea #{row['idea_id']} · Gate #{row['id']}")
                    st.caption(f"I{row['impact']}/E{row['effort']}/R{row['risk']}/N{row['novelty']}  ·  {_fmt_ts(row['created_at'])}")
                with cb:
                    st.caption(row["recommended_action"])
    else:
        st.caption("No gate history yet.")
