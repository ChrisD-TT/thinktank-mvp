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
import thinktank.engine.db as _gdb_mod

# sid lives in the URL (?sid=...) so it survives refresh and tab switching.
# session_state is secondary cache only.
# ==============================================================================
import uuid as _uuid_mod
_gdb_mod.init_db()

# 1. URL param is the source of truth
_url_sid = st.query_params.get("sid", "")
if _url_sid:
    # Valid sid in URL — always use it
    st.session_state.coin_session_id = _url_sid
elif "coin_session_id" in st.session_state:
    # No URL sid but session_state has one — write it to URL
    _url_sid = st.session_state.coin_session_id
    st.query_params["sid"] = _url_sid
else:
    # Brand new visitor — create sid and put it in URL immediately
    _url_sid = str(_uuid_mod.uuid4())
    st.session_state.coin_session_id = _url_sid
    st.query_params["sid"] = _url_sid

# Ensure DB row exists (grants welcome coins exactly once)
_GLOBAL_SID = _url_sid
_gdb_mod.coin_get_or_create(_GLOBAL_SID)

# ── Persistent auth restore ───────────────────────────────────────────────────
# If session_state lost auth_user (server restart / Railway redeploy),
# restore it from DB using the sid. This prevents idle logouts.
if "auth_user" not in st.session_state:
    st.session_state.auth_user = None
if not st.session_state.auth_user:
    _persisted_email = _gdb_mod.sid_get_auth(_GLOBAL_SID)
    if _persisted_email:
        st.session_state.auth_user = _persisted_email


def _get_coin_session():
    """Return (sid, db) — always uses the globally resolved session."""
    import thinktank.engine.db as _gdb
    return _GLOBAL_SID, _gdb


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="ThinkTank", page_icon="🧠", layout="wide")

st.markdown(
    """
    <style>
    /* Hide deploy button */
    div.stAppDeployButton { display: none !important; }

    /* Hide the top decoration bar */
    div[data-testid="stDecoration"] { display: none !important; }

    /* Stop the entire app from dimming/fading when Streamlit reruns */
    [data-testid="stApp"],
    [data-testid="stApp"] * {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
    }

    /* Hide the status/running widget in the bottom-right corner */
    [data-testid="stStatusWidget"] { display: none !important; }
    </style>
    """,
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

# ── GDPR / CCPA Consent Banner ────────────────────────────────────────────────
# Shown once per browser session until accepted. Stored in session_state only —
# no tracking cookie needed since Streamlit is server-side.
if "consent_given" not in st.session_state:
    st.session_state.consent_given = False

if not st.session_state.consent_given:
    _cb = st.container()
    with _cb:
        st.markdown(
            """
            <div style="
                position:fixed;bottom:0;left:0;right:0;z-index:9999;
                background:#1a1a2e;border-top:2px solid #3b82d4;
                padding:14px 24px;display:flex;align-items:center;
                justify-content:space-between;flex-wrap:wrap;gap:10px;
            ">
                <span style="color:#e0e0e0;font-size:0.85rem;max-width:780px;line-height:1.5;">
                    🍪 ThinkTank collects your email and usage data to run your account and improve the service.
                    We do not sell your data. Payments are handled by Stripe.
                    By continuing you agree to our
                    <a href="?page=legal" style="color:#60a5fa;">Terms of Service</a> and
                    <a href="?page=legal" style="color:#60a5fa;">Privacy Policy</a>.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Spacer so the fixed banner doesn't cover page content
        st.markdown("<div style='height:60px'></div>", unsafe_allow_html=True)
        _accept_col, _ = st.columns([1, 4])
        with _accept_col:
            if st.button("✅ Got it, I agree", type="primary", use_container_width=True, key="consent_btn"):
                st.session_state.consent_given = True
                st.rerun()

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
# ── Auth helpers ──────────────────────────────────────────────────────────────
from thinktank.engine.db import user_register, user_login, user_merge_session

if "auth_user" not in st.session_state:
    st.session_state.auth_user = None   # None = logged out, str = email

def _auth_sid():
    """Return the session ID to use for coins — email if logged in, anon sid otherwise."""
    return st.session_state.auth_user if st.session_state.auth_user else st.session_state.get("_GLOBAL_SID", "anon")

with st.sidebar:
    st.title("🧠 ThinkTank")
    st.caption("Powered by OpenAI · gpt-4o-mini")
    st.divider()

    # ── Login / Register ───────────────────────────────────────────────────
    if st.session_state.auth_user:
        st.success(f"👤 {st.session_state.auth_user}")
        if st.button("Log out", key="sidebar_logout", use_container_width=True):
            _gdb_mod.sid_clear_auth(_GLOBAL_SID)
            st.session_state.auth_user = None
            st.rerun()
    else:
        with st.expander("🔑 Log in / Register", expanded=False):
            _auth_tab = st.radio("", ["Log in", "Register"], horizontal=True, key="auth_mode", label_visibility="collapsed")
            _auth_email = st.text_input("Email", key="auth_email", placeholder="you@example.com")
            _auth_pw    = st.text_input("Password", key="auth_pw", type="password", placeholder="Min 6 characters")
            if _auth_tab == "Log in":
                if st.button("Log in", key="do_login", type="primary", use_container_width=True):
                    _res = user_login(_auth_email, _auth_pw)
                    if _res["ok"]:
                        # merge any anon coins into the account
                        _anon = st.session_state.get("_GLOBAL_SID", "")
                        if _anon:
                            user_merge_session(_res["email"], _anon)
                        _gdb_mod.sid_save_auth(_GLOBAL_SID, _res["email"])
                        st.session_state.auth_user = _res["email"]
                        st.success("Welcome back!")
                        st.rerun()
                    else:
                        st.error(_res["error"])
            else:
                if st.button("Create account", key="do_register", type="primary", use_container_width=True):
                    _res = user_register(_auth_email, _auth_pw)
                    if _res["ok"]:
                        _anon = st.session_state.get("_GLOBAL_SID", "")
                        if _anon:
                            user_merge_session(_res["email"], _anon)
                        _gdb_mod.sid_save_auth(_GLOBAL_SID, _res["email"])
                        st.session_state.auth_user = _res["email"]
                        st.success("Account created! Welcome 🎉")
                        st.rerun()
                    else:
                        st.error(_res["error"])
            st.caption("Your coins are saved to your account across all browsers.")

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
    st.markdown(
        """
        <div style="background:#fff8f0;border:1px solid #f5a623;border-radius:8px;
                    padding:14px 12px;text-align:center;margin:4px 0;">
            <div style="font-size:0.8rem;font-weight:700;color:#c05c00;margin-bottom:4px;">
                ☕ Support ThinkTank
            </div>
            <div style="font-size:0.72rem;color:#7a5000;margin-bottom:10px;line-height:1.5;">
                Built by one person. If it helps you think better, consider buying a coffee.
            </div>
            <a href="https://paypal.me/CDovico" target="_blank" rel="noopener"
               style="display:inline-block;background:#003087;color:#fff;
                      text-decoration:none;font-size:0.82rem;font-weight:700;
                      padding:9px 22px;border-radius:5px;">
                ♥ Donate via PayPal
            </a>
            <div style="font-size:0.62rem;color:#aaa;margin-top:6px;">Any amount is appreciated</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    import urllib.parse as _sp
    _share_url  = "https://www.thinktankapp.net"
    _share_text = "Just tried ThinkTank — an AI-powered decision engine that helps you think faster and take action with less risk. Check it out"
    _tw = "https://twitter.com/intent/tweet?text=" + _sp.quote(_share_text) + "&url=" + _sp.quote(_share_url)
    _li = "https://www.linkedin.com/sharing/share-offsite/?url=" + _sp.quote(_share_url)
    _wa = "https://wa.me/?text=" + _sp.quote(_share_text + " " + _share_url)
    st.markdown("**Share ThinkTank**", help="Spread the word!")
    st.markdown(
        '<a href="' + _tw + '" target="_blank" rel="noopener" style="display:inline-block;background:#000;color:#fff;text-decoration:none;font-size:0.78rem;font-weight:700;padding:7px 16px;border-radius:5px;margin:3px 2px;">𝕏 Twitter</a>'
        '<a href="' + _li + '" target="_blank" rel="noopener" style="display:inline-block;background:#0a66c2;color:#fff;text-decoration:none;font-size:0.78rem;font-weight:700;padding:7px 16px;border-radius:5px;margin:3px 2px;">in LinkedIn</a>'
        '<a href="' + _wa + '" target="_blank" rel="noopener" style="display:inline-block;background:#25d366;color:#fff;text-decoration:none;font-size:0.78rem;font-weight:700;padding:7px 16px;border-radius:5px;margin:3px 2px;">💬 WhatsApp</a>',
        unsafe_allow_html=True,
    )
    st.caption("🔗 " + _share_url)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ask, tab_ideas, tab_analysis, tab_gate, tab_room, tab_studio, tab_coins, tab_admin, tab_legal = st.tabs(
    ["💬 Ask", "💡 Ideas", "📊 Analysis", "🚦 Gate", "🎲 Room", "📱 Content Studio", "💳 Buy Coins", "⚙️ Admin", "📄 Legal"]
)

# ==============================================================================
# GLOBAL SESSION — resolved once at top of every page load

_g_qp = st.query_params
if _g_qp.get("purchase") == "success":
    _g_sid, _g_db = _get_coin_session()
    _g_coins   = int(_g_qp.get("coins", "0"))
    _g_ret_sid = _g_qp.get("session", _g_sid)
    if _g_coins > 0:
        # credit once to the session tied to the purchase (idempotent — safe to replay)
        _effective_sid = _g_ret_sid if _g_ret_sid else _g_sid
        _g_db.coin_credit(_effective_sid, _g_coins, f"url-{_effective_sid}-{_g_coins}")
    _g_bal = _g_db.coin_get_or_create(_g_sid)
    st.success(f"✅ Payment confirmed! You now have **{_g_bal} coins**. Head to 💬 Ask to use them.")
    # Keep sid in URL — only clear the purchase params
    st.query_params["sid"] = _g_sid
    if "purchase" in st.query_params: del st.query_params["purchase"]
    if "coins"    in st.query_params: del st.query_params["coins"]
    if "session"  in st.query_params: del st.query_params["session"]
elif _g_qp.get("purchase") == "cancelled":
    st.warning("Purchase cancelled — no charge was made.")
    _g_sid, _ = _get_coin_session()
    st.query_params["sid"] = _g_sid
    if "purchase" in st.query_params: del st.query_params["purchase"]

# ── Helper: coin gate used by Ideas, Analysis, Gate tabs ─────────────────────
def _require_coins(amount: int, action: str):
    """Deduct coins. Shows error and returns False if insufficient."""
    sid, db = _get_coin_session()
    if not db.coin_spend(sid, amount):
        bal = db.coin_balance(sid)
        st.error(f"🪙 Not enough coins — **{action}** costs {amount} coin{'s' if amount > 1 else ''}. You have {bal}. Go to 💳 Buy Coins to top up.")
        return False
    return True

def _refund_coins(amount: int, reason: str = ""):
    """Refund coins on AI failure."""
    sid, db = _get_coin_session()
    db.coin_credit(sid, amount, f"refund-{sid}-{reason}")

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
        if st.button("💾 Save + Rapid Bounce  🪙 1 coin", use_container_width=True, type="primary"):
                if idea_text.strip():
                    if _require_coins(1, "Rapid Bounce"):
                        with st.spinner("Running Rapid Bounce…"):
                            try:
                                result = run_idea(idea_text.strip())
                                st.session_state.selected_idea_id    = result["idea_id"]
                                st.session_state.rapid_bounce_output = result["output"]
                                st.success(f"✅ Saved as Idea #{result['idea_id']} — scroll down for output")
                            except Exception as e:
                                _refund_coins(1, "idea")
                                st.error(f"Error: {e}")
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
                if st.button("📝 Refine  🪙 2", use_container_width=True, type="primary"):
                    if _require_coins(2, "Refine"):
                        with st.spinner("Refining…"):
                            try:
                                r = run_refine(sel)
                                st.session_state.refine_output = r.get("output", r.get("error"))
                            except Exception as e:
                                _refund_coins(2, "refine")
                                st.session_state.refine_output = f"Error: {e}"
            with c2:
                if st.button("📈 Score  🪙 2", use_container_width=True, type="primary"):
                    if _require_coins(2, "Score"):
                        with st.spinner("Scoring…"):
                            try:
                                r = run_score(sel)
                                st.session_state.score_output = r.get("output", r.get("error"))
                            except Exception as e:
                                _refund_coins(2, "score")
                                st.session_state.score_output = f"Error: {e}"
            with c3:
                if st.button("🔍 Critique  🪙 2", use_container_width=True, type="primary"):
                    if _require_coins(2, "Critique"):
                        with st.spinner("Critiquing…"):
                            try:
                                r = run_critique(sel)
                                st.session_state.critique_output = r.get("output", r.get("error"))
                            except Exception as e:
                                _refund_coins(2, "critique")
                                st.session_state.critique_output = f"Error: {e}"

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

            if st.button("🚦 Run Gate  🪙 2 coins", use_container_width=True, type="primary"):
                if _require_coins(2, "Run Gate"):
                    with st.spinner("Running Score + Critique + Gate…"):
                        try:
                            result = run_gate(sel)
                            st.session_state.gate_output = result
                        except Exception as e:
                            _refund_coins(2, "gate")
                            st.error(f"Gate error: {e}")

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
    # ── Use global session ────────────────────────────────────────────────────
    import thinktank.engine.db as _askdb
    _ask_sid = _GLOBAL_SID
    _ask_bal = _askdb.coin_balance(_ask_sid)

    _bal_col, _buy_col = st.columns([3, 1])
    with _bal_col:
        st.subheader("Ask / Chat")
    with _buy_col:
        if _ask_bal > 0:
            st.success(f"🪙 {_ask_bal} coins")
        else:
            st.warning("🪙 0 coins — go to 💳 Buy Coins tab")

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
    _chat_box = st.container(height=480, border=False)
    with _chat_box:
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
                # Check + deduct coin before calling AI
                _has_coin = _askdb.coin_spend(_ask_sid, 1)
                if not _has_coin:
                    st.error("🪙 No coins remaining. Go to the **💳 Buy Coins** tab to top up.")
                else:
                    with st.spinner("Thinking…"):
                        try:
                            run_ask(ask_text.strip(), chat_id)
                            st.rerun()
                        except Exception as e:
                            # Refund coin if AI call failed
                            _askdb.coin_credit(_ask_sid, 1, f"refund-{_ask_sid}-{id(e)}")
                            st.error(f"AI error: {e}")
            else:
                st.warning("Enter a message and select a chat first.")
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
# BUY COINS TAB
# ==============================================================================
# ==============================================================================
# CONTENT STUDIO TAB
# ==============================================================================
with tab_studio:
    from thinktank.engine.db import studio_save, studio_list, studio_update, studio_delete
    from datetime import datetime as _dt, timedelta as _td

    # ── Coin costs ────────────────────────────────────────────────────────────
    _STUDIO_COSTS = {
        "single":       7,   # single platform post
        "post_hook":    12,  # post + hashtags + hook (per platform)
        "tiktok":       18,  # TikTok/Reel script
        "week_one":     350, # full week 1 platform
        "week_all":     500, # full week all platforms
        "edit":         3,   # edit existing content
    }
    _MULTI_DISC = 0.85  # 15% off when selecting multiple platforms

    _PLATFORMS = ["Twitter/X", "LinkedIn", "TikTok", "Instagram", "Reddit", "Facebook", "YouTube", "Threads"]
    _TONES     = ["Professional", "Casual", "Viral", "Informative", "Bold"]

    _studio_sid = _auth_sid()
    import thinktank.engine.db as _sdb
    _studio_bal = _sdb.coin_balance(_studio_sid)
    # check if user has free edits based on plan tier
    from thinktank.engine.db import user_get_plan, FREE_EDIT_TIERS
    _user_plan = user_get_plan(st.session_state.auth_user) if st.session_state.auth_user else {"plan_tier": "free"}
    _free_edits = _user_plan["plan_tier"] in FREE_EDIT_TIERS

    st.subheader("📱 Content Studio")
    st.caption("AI-generated social media content. Coins are charged per generation.")

    # ── Coin balance indicator ────────────────────────────────────────────────
    _scol1, _scol2 = st.columns([3,1])
    with _scol2:
        st.metric("🪙 Coins", _studio_bal)

    st.divider()

    # ── Generator ─────────────────────────────────────────────────────────────
    st.markdown("### ✍️ Generate Content")

    _gen_type = st.selectbox("Content Type", [
        "🎯 Single Post  —  7 coins",
        "🪝 Post + Hashtags + Hook  —  12 coins per platform",
        "🎬 TikTok / Reel Script  —  18 coins",
        "📅 Full Week — 1 Platform  —  350 coins",
        "🚀 Full Week — ALL Platforms  —  500 coins",
    ], key="studio_gen_type")

    # platform selector
    if "ALL Platforms" in _gen_type:
        _sel_platforms = _PLATFORMS
        st.info("📢 All 5 platforms selected — full week of content for every channel.")
    elif "TikTok" in _gen_type:
        _sel_platforms = ["TikTok"]
    else:
        _sel_platforms = st.multiselect(
            "Platform(s)", _PLATFORMS, default=["Twitter/X"], key="studio_platforms"
        )
        # multi-platform 15% discount
        if len(_sel_platforms) > 1 and "Full Week" not in _gen_type:
            _base = _STUDIO_COSTS["post_hook"] if "Hashtags" in _gen_type else _STUDIO_COSTS["single"]
            _full_price = _base * len(_sel_platforms)
            _disc_price = max(1, round(_full_price * _MULTI_DISC))
            _saved = _full_price - _disc_price
            st.success(f"🎁 Multi-platform discount! {len(_sel_platforms)} platforms × {_base} coins = ~~{_full_price}~~ **{_disc_price} coins** (15% off — you save {_saved} coins)")

    _topic = st.text_area("Topic / Brief", placeholder="e.g. Launching ThinkTank — AI decision engine for entrepreneurs", key="studio_topic", height=80)
    _tone  = st.selectbox("Tone", _TONES, key="studio_tone")

    # week schedule toggle + email
    _schedule_week = False
    if "Full Week" in _gen_type:
        _schedule_week = st.toggle("📅 Schedule daily release (Mon–Sun unlocks day by day)", value=True, key="studio_schedule")
        if _schedule_week:
            st.info("✉️ Each day's content will unlock at 12:01 AM and be emailed to you automatically — ready every morning.")

    # calculate coin cost
    def _studio_cost(gen_type, platforms):
        if "ALL Platforms" in gen_type:   return _STUDIO_COSTS["week_all"]
        if "Full Week" in gen_type:        return _STUDIO_COSTS["week_one"]
        if "TikTok" in gen_type:           return _STUDIO_COSTS["tiktok"]
        if "Hashtags" in gen_type:
            base = _STUDIO_COSTS["post_hook"] * len(platforms)
            if len(platforms) > 1: base = max(1, round(base * _MULTI_DISC))
            return base
        base = _STUDIO_COSTS["single"] * len(platforms)
        if len(platforms) > 1: base = max(1, round(base * _MULTI_DISC))
        return base

    _cost = _studio_cost(_gen_type, _sel_platforms if "ALL Platforms" not in _gen_type else _PLATFORMS)
    st.markdown(f"**Cost: {_cost} coins**")

    if st.button("🚀 Generate Content", key="studio_generate", type="primary", use_container_width=True):
        if not st.session_state.auth_user:
            st.error("🔑 Please log in first — use the sidebar to log in or register.")
        elif not _topic.strip():
            st.error("Please enter a topic or brief.")
        elif not _sel_platforms:
            st.error("Please select at least one platform.")
        elif _studio_bal < _cost:
            st.error(f"🪙 Not enough coins. This costs {_cost} coins — you have {_studio_bal}. Go to 💳 Buy Coins to top up.")
        else:
            # deduct coins
            _sdb.coin_spend(_studio_sid, _cost)

            # build prompt per platform — uses STUDIO_SYSTEM_PROMPT for elite content quality
            import thinktank.engine.ai as _sai
            from thinktank.config import STUDIO_SYSTEM_PROMPT as _STUDIO_SYS
            _generated = []
            _days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            _today = _dt.now().date()

            # Platform-specific style instructions
            def _plt_style(plt):
                return {
                    "Twitter/X":  "Under 280 characters. One sharp idea — hot take, story hook, or punchy insight. No corporate speak. No 'Excited to share.' Punchy and direct.",
                    "LinkedIn":   "150-300 words. Open with a bold statement or 1-sentence story. Add a blank line between every paragraph. No jargon. End with a question or clear CTA.",
                    "TikTok":     "Spoken word script, 45-60 seconds when read aloud. Line 1 MUST stop the scroll — make it a hook, not an intro. Short choppy sentences. Hook → value → CTA.",
                    "Instagram":  "Emotion-first caption. Short punchy opener. Use line breaks for breathing room. Hashtags on the LAST line only, not in the caption body. 3-5 relevant hashtags.",
                    "Reddit":     "Genuinely helpful, conversational tone. Zero self-promotion or 'check this out' energy. Lead with value. Write like you're helping a friend, not advertising.",
                    "Facebook":   "Warm, community-first. 100-200 words. Ask a question that invites comments. Share a story, not a statement. Feel like a post from a real person, not a brand.",
                    "YouTube":    "Video description: Start with exactly what the viewer gets from watching. Keywords naturally in first 2 sentences. Include timestamps placeholder [0:00] if relevant. CTA at end.",
                    "Threads":    "Raw, casual, personal. Under 500 chars. Like texting your audience. No hashtags needed. One real thought.",
                }.get(plt, "Engaging, platform-appropriate post. Write for a real human audience.")

            for _plt in (_PLATFORMS if "ALL Platforms" in _gen_type else _sel_platforms):
                if "Full Week" in _gen_type:
                    for _di, _day in enumerate(_days):
                        _prompt = f"""Write a {_tone.lower()} {_plt} post for {_day} about: {_topic}

This is Day {_di+1} of 7. Vary the angle from other days — don't repeat the same framing.
{"Also include: 3-5 targeted hashtags AND a scroll-stopping hook line (labeled 'HOOK:') before the post." if "Hashtags" in _gen_type else ""}

Platform requirements: {_plt_style(_plt)}

Return ONLY the final post content, ready to copy-paste and publish. No explanations, no labels, no metadata."""
                        _resp = _sai.chat([
                            {"role": "system", "content": _STUDIO_SYS},
                            {"role": "user",   "content": _prompt},
                        ])
                        _sched = (_today + _td(days=_di)).isoformat() if _schedule_week else None
                        _sid_val = _sdb.studio_save(_studio_sid, _plt, _topic, _tone, _resp, "week_post", _sched)
                        _generated.append({"platform":_plt,"day":_day,"content":_resp,"id":_sid_val,"released": not _schedule_week})
                else:
                    _ctype = "tiktok_script" if "TikTok" in _gen_type else "post_hook" if "Hashtags" in _gen_type else "single_post"
                    if "TikTok" in _gen_type:
                        _prompt = f"""Write a TikTok/Reel video script about: {_topic}
Tone: {_tone}

Structure:
HOOK (first 2 seconds — must stop the scroll, spoken out loud):
[write hook here]

BODY (the value, 30-45 seconds spoken):
[write body here — short sentences, rhythm, conversational]

CTA (last 5 seconds):
[write CTA here — specific action, not generic "follow me"]

Platform requirements: {_plt_style("TikTok")}

Return ONLY the script with the HOOK / BODY / CTA labels. Ready to read on camera."""
                    elif "Hashtags" in _gen_type:
                        _prompt = f"""Write a {_tone.lower()} {_plt} post about: {_topic}

Include:
1. A HOOK line (scroll-stopping opener, labeled "HOOK:")
2. The full post body
3. 5 targeted hashtags (labeled "HASHTAGS:") on the final line

Platform requirements: {_plt_style(_plt)}

Return ONLY the hook, post, and hashtags — ready to publish."""
                    else:
                        _prompt = f"""Write a {_tone.lower()} {_plt} post about: {_topic}

Platform requirements: {_plt_style(_plt)}

Return ONLY the post — ready to copy-paste and publish. No explanations."""
                    _resp = _sai.chat([
                        {"role": "system", "content": _STUDIO_SYS},
                        {"role": "user",   "content": _prompt},
                    ])
                    _sid_val = _sdb.studio_save(_studio_sid, _plt, _topic, _tone, _resp, _ctype, None)
                    _generated.append({"platform":_plt,"day":None,"content":_resp,"id":_sid_val,"released":True})

            st.session_state["studio_generated"] = _generated
            st.session_state["studio_cost_paid"] = _cost
            st.rerun()

    # ── Show just-generated content ───────────────────────────────────────────
    if st.session_state.get("studio_generated"):
        st.divider()
        st.success(f"✅ Content generated! {st.session_state.get('studio_cost_paid',0)} coins used.")
        for _item in st.session_state["studio_generated"]:
            _lbl = f"📱 {_item['platform']}" + (f" — {_item['day']}" if _item.get('day') else "")
            if _item.get("released", True):
                with st.expander(_lbl, expanded=True):
                    st.markdown(_item["content"])
                    st.caption(f"ID #{_item['id']} · saved to your schedule")
            else:
                st.info(f"🔒 {_lbl} — scheduled, unlocks on its release date")

    st.divider()

    # ── Content Schedule (Mon–Sun viewer) ─────────────────────────────────────
    st.markdown("### 📅 Your Content Schedule")
    _all_content = studio_list(_studio_sid, user_email=st.session_state.auth_user)

    if not _all_content:
        st.caption("No content generated yet. Use the generator above to create your first post.")
    else:
        _day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday","—"]
        _by_day = {}
        for _c in _all_content:
            if _c["scheduled_for"]:
                try:
                    _wd = _dt.fromisoformat(_c["scheduled_for"]).strftime("%A")
                except Exception:
                    _wd = "—"
            else:
                _wd = "—"
            _by_day.setdefault(_wd, []).append(_c)

        for _day in _day_order:
            if _day not in _by_day:
                continue
            st.markdown(f"**{_day}**")
            for _c in _by_day[_day]:
                _plat_icon = {"Twitter/X":"🐦","LinkedIn":"💼","TikTok":"🎵","Instagram":"📸","Reddit":"👽","Facebook":"📘","YouTube":"▶️","Threads":"🧵"}.get(_c["platform"],"📱")
                if not _c["released"]:
                    st.markdown(f"{_plat_icon} **{_c['platform']}** 🔒 *Unlocks {_c['scheduled_for']}*")
                else:
                    with st.expander(f"{_plat_icon} {_c['platform']} · {_c['tone']} · {_c['content_type']}", expanded=False):
                        # editable text
                        _edit_key = f"edit_{_c['id']}"
                        _edited = st.text_area("Content", value=_c["content"], key=_edit_key, height=120)
                        _ecol1, _ecol2 = st.columns(2)
                        with _ecol1:
                            _edit_label = "💾 Save Edit (FREE)" if _free_edits else "💾 Save Edit (3 coins)"
                            if st.button(_edit_label, key=f"save_{_c['id']}"):
                                if _edited.strip() == _c["content"].strip():
                                    st.warning("No changes detected.")
                                elif not _free_edits and _studio_bal < 3:
                                    st.error("Not enough coins to save edit. Go to 💳 Buy Coins to top up.")
                                else:
                                    if not _free_edits:
                                        _sdb.coin_spend(_studio_sid, 3)
                                    studio_update(_c["id"], _edited.strip())
                                    st.success("✅ Saved!")
                                    st.rerun()
                        with _ecol2:
                            if st.button(f"🗑 Delete", key=f"del_{_c['id']}"):
                                studio_delete(_c["id"])
                                st.rerun()


    # ==============================================================================
    # CREATOR POWER TOOLS
    # ==============================================================================
    # DOWNLOAD PROJECT PACKAGE
    # ==============================================================================
    st.divider()
    st.markdown("### 📦 Download Your Work")
    st.caption("Everything you've generated is saved to your account. Download it all as a text file anytime.")

    if st.session_state.auth_user:
        import thinktank.engine.db as _dldb
        _all_power = [r for r in _dldb.studio_list(_studio_sid)
                      if r["content_type"] in ("hook_generator", "repurpose_engine", "brand_voice_builder")]
        _all_studio = [r for r in _dldb.studio_list(_studio_sid)
                       if r["content_type"] in ("single_post", "post_hook", "tiktok_script", "week_post")]

        _total_items = len(_all_power) + len(_all_studio)
        if _total_items == 0:
            st.caption("Nothing saved yet — generate some content first.")
        else:
            st.markdown(f"**{_total_items} saved items** ready to download — {len(_all_power)} Power Tool outputs + {len(_all_studio)} Studio posts")

            # build the text bundle
            from datetime import datetime as _dldt
            _lines = []
            _lines.append("=" * 60)
            _lines.append("THINKTANK CONTENT PACKAGE")
            _lines.append(f"Account: {st.session_state.auth_user}")
            _lines.append(f"Generated: {_dldt.now().strftime('%B %d, %Y %I:%M %p')}")
            _lines.append("=" * 60)

            if _all_power:
                _lines.append("\n\n── CREATOR POWER TOOLS ──────────────────────────────────")
                for _item in _all_power:
                    _type_label = {"hook_generator": "🪝 HOOKS", "repurpose_engine": "♻️ REPURPOSED CONTENT", "brand_voice_builder": "🎙️ BRAND VOICE PROFILE"}.get(_item["content_type"], _item["content_type"].upper())
                    _lines.append(f"\n{_type_label}")
                    _lines.append(f"Topic: {_item['topic']}  |  Platform: {_item['platform']}  |  Date: {_item['created_at'][:10]}")
                    _lines.append("-" * 40)
                    _lines.append(_item["content"])

            if _all_studio:
                _lines.append("\n\n── CONTENT STUDIO POSTS ─────────────────────────────────")
                for _item in _all_studio:
                    _lines.append(f"\n📱 {_item['platform'].upper()}  |  {_item['tone']}  |  {_item['created_at'][:10]}")
                    if _item.get("scheduled_for"):
                        _lines.append(f"Scheduled: {_item['scheduled_for']}")
                    _lines.append("-" * 40)
                    _lines.append(_item["content"])

            _lines.append("\n\n" + "=" * 60)
            _lines.append("Made with ThinkTank · www.thinktankapp.net")
            _lines.append("=" * 60)

            _bundle_text = "\n".join(_lines)
            _filename = f"thinktank_content_{_dldt.now().strftime('%Y%m%d_%H%M')}.txt"

            st.download_button(
                label="📥 Download Full Content Package (.txt)",
                data=_bundle_text.encode("utf-8"),
                file_name=_filename,
                mime="text/plain",
                type="primary",
                use_container_width=True,
            )
            st.caption("Your content is also permanently saved in your account — this download is just a copy you can keep locally.")
    else:
        st.info("🔑 Log in to download your saved content.")

    # ==============================================================================
    # CREATOR POWER TOOLS — TIMED SESSION ACCESS
    # ==============================================================================
    import time as _time
    from thinktank.config import STUDIO_SYSTEM_PROMPT as _STUDIO_SYS

    st.divider()
    st.markdown("### 🔧 Creator Power Tools")

    # ── Timed Session constants ───────────────────────────────────────────────
    _TOOL_SESSIONS = {
        "10 min  —  15 coins  (~$3)":  {"minutes": 10,  "coins": 15},
        "20 min  —  25 coins  (~$5)":  {"minutes": 20,  "coins": 25},
        "45 min  —  50 coins  (~$10)": {"minutes": 45,  "coins": 50},
        "90 min  —  90 coins  (~$18)": {"minutes": 90,  "coins": 90},
    }
    _WARN_SECS = 180  # warn when 3 minutes remain

    # ── Session state defaults ────────────────────────────────────────────────
    for _k, _v in {
        "tool_session_active":    False,
        "tool_session_end":       0.0,
        "tool_session_mins":      0,
        "tool_warned":            False,
        "tool_session_recorded":  False,
    }.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    def _tool_seconds_left() -> int:
        return max(0, int(st.session_state.tool_session_end - _time.time()))

    def _tool_fmt(secs: int) -> str:
        m, s = divmod(secs, 60)
        return f"{m}:{s:02d}"

    # ── Gate: must be logged in ───────────────────────────────────────────────
    if not st.session_state.auth_user:
        st.info("🔑 Log in to access Creator Power Tools.")
    else:
        # ── Restore session from DB on every page load / login ───────────────
        # This is the key fix — session end time lives in DB, not session_state.
        # If Streamlit reloads, logs out, or refreshes, the session is restored.
        from thinktank.engine.db import tool_session_load, tool_session_save, tool_session_clear
        if not st.session_state.tool_session_active:
            _db_sess = tool_session_load(_studio_sid)
            if _db_sess:
                st.session_state.tool_session_active = True
                st.session_state.tool_session_end    = _db_sess["end_epoch"]
                st.session_state.tool_session_mins   = _db_sess["mins_total"]
                st.session_state.tool_warned         = False

        # ── Active session display ────────────────────────────────────────────
        if st.session_state.tool_session_active:
            _secs_left = _tool_seconds_left()

            if _secs_left <= 0:
                st.session_state.tool_session_active = False
                st.session_state.tool_warned = False
                tool_session_clear(_studio_sid)
                st.error("⏱️ **Your Power Tools session has ended.** Select a new session below to continue.")
            else:
                # ── Timer display (NO full page reload — that was logging people out) ──
                # We show the timer as a metric. It updates whenever the user
                # interacts with the page. No automatic reload = no forced logout.
                if _secs_left <= _WARN_SECS:
                    st.warning(
                        f"⚠️ **{_tool_fmt(_secs_left)} remaining** — extend now to keep working."
                    )
                    st.session_state.tool_warned = True
                else:
                    _pct = int((_secs_left / (st.session_state.tool_session_mins * 60)) * 100)
                    st.success(
                        f"✅ Session active — **{_tool_fmt(_secs_left)} remaining** "
                        f"({_pct}% of your time left) · Timer pauses when you leave this tab."
                    )

                # Extend session inline
                with st.expander("⏳ Extend my session", expanded=st.session_state.tool_warned):
                    _ext_choice = st.selectbox("Add time", list(_TOOL_SESSIONS.keys()), key="extend_choice")
                    _ext_data = _TOOL_SESSIONS[_ext_choice]
                    _ext_cost = _ext_data["coins"]
                    _ext_mins = _ext_data["minutes"]
                    st.caption(f"Adds **{_ext_mins} min** · **{_ext_cost} coins** · you have **{_studio_bal} coins**")
                    if st.button(f"⏳ Add {_ext_mins} min ({_ext_cost} coins)", key="extend_session", type="primary"):
                        if _studio_bal < _ext_cost:
                            st.error(f"💰 Need {_ext_cost} coins — you have {_studio_bal}. Go to 💳 Buy Coins.")
                        else:
                            _sdb.coin_spend(_studio_sid, _ext_cost)
                            st.session_state.tool_session_end  += _ext_mins * 60
                            st.session_state.tool_session_mins += _ext_mins
                            st.session_state.tool_warned = False
                            # persist the new end time to DB
                            tool_session_save(_studio_sid,
                                              st.session_state.tool_session_end,
                                              st.session_state.tool_session_mins)
                            st.success(f"✅ Session extended by {_ext_mins} minutes!")
                            st.rerun()

                st.divider()

                # ── The actual tools (only visible during active session) ─────
                _tool_tab1, _tool_tab2, _tool_tab3 = st.tabs(["🪝 Hook Generator", "♻️ Repurpose Engine", "🎙️ Brand Voice Builder"])

                # ── Hook Generator ────────────────────────────────────────────
                with _tool_tab1:
                    st.markdown("**5 scroll-stopping hooks** — the opening line that makes people stop and watch.")
                    _hook_topic    = st.text_area("What is your video/post about?", key="hook_topic", height=80,
                                                   placeholder="e.g. How I built a $10k/month business in 90 days")
                    _hook_platform = st.selectbox("Platform", ["TikTok", "Instagram Reels", "YouTube Shorts", "Twitter/X", "LinkedIn"], key="hook_platform")
                    _hook_tone     = st.selectbox("Tone", _TONES, key="hook_tone")

                    if st.button("🪝 Generate Hooks", key="gen_hooks", type="primary", use_container_width=True):
                        if not _hook_topic.strip():
                            st.error("Enter a topic first.")
                        else:
                            import thinktank.engine.ai as _hai
                            _hook_prompt = f"""You are a viral content psychologist. Your job is to engineer the exact moment someone STOPS SCROLLING.

Platform: {_hook_platform}
Tone: {_hook_tone}
Topic: {_hook_topic}

Generate 5 hooks that exploit human psychology. Each hook is the FIRST LINE the audience reads or hears — it decides everything.

The 5 psychological triggers to use (one per hook):
1. **Pattern Interrupt** — violate an expectation, challenge a sacred cow, flip a common belief on its head
2. **Curiosity Gap** — open a loop the brain MUST close ("The reason nobody talks about X is..." / "I did X for 30 days and...")
3. **Immediate Relatability** — "If you've ever felt [specific pain], this is why..." Make them feel SEEN instantly
4. **Shock Value / Numbers** — a number so surprising it doesn't compute ("I made $X in Y" / "X% of people don't know...")
5. **Story Drop-In** — Start mid-action, mid-conflict, mid-emotion ("I was 10 seconds away from..." / "The call came at 2 AM and...")

Rules:
- Be radically specific to THIS topic — generic hooks fail
- No clichés: "Have you ever wondered" / "What if I told you" / "This one trick" are dead
- Trigger emotion fast: fear, curiosity, FOMO, validation, surprise
- Make every word earn its place — no filler

Return numbered hooks 1-5, ready to use."""
                            with st.spinner("Generating hooks..."):
                                _hook_result = _hai.chat([
                                    {"role": "system", "content": _STUDIO_SYS},
                                    {"role": "user",   "content": _hook_prompt},
                                ])
                            # save to DB permanently under this user's account
                            _sdb.studio_save(_studio_sid, _hook_platform, _hook_topic,
                                             _hook_tone, _hook_result, "hook_generator")

                    # load all saved hooks for this user from DB
                    _saved_hooks = [r for r in _sdb.studio_list(_studio_sid)
                                    if r["content_type"] == "hook_generator"]
                    if _saved_hooks:
                        st.success(f"✅ {len(_saved_hooks)} hook set(s) saved to your account")
                        for _h in reversed(_saved_hooks):
                            with st.expander(f"🪝 {_h['platform']} — {_h['topic'][:50]} · {_h['created_at'][:10]}", expanded=(_h == _saved_hooks[-1])):
                                st.markdown(_h["content"])
                                if st.button("🗑 Delete", key=f"del_hook_{_h['id']}"):
                                    _sdb.studio_delete(_h["id"])
                                    st.rerun()

                # ── Repurpose Engine ──────────────────────────────────────────
                with _tool_tab2:
                    st.markdown("**Write once, post everywhere** — one piece of content remixed for every platform.")
                    _repurpose_src = st.text_area("Paste your original content here", key="repurpose_src", height=150,
                                                   placeholder="Paste a blog post, tweet, video script, caption — anything.")
                    _repurpose_platforms = st.multiselect(
                        "Repurpose for these platforms",
                        ["Twitter/X", "LinkedIn", "TikTok Script", "Instagram Caption", "Facebook", "YouTube Description", "Threads", "Reddit"],
                        default=["Twitter/X", "LinkedIn", "Instagram Caption"],
                        key="repurpose_platforms",
                    )
                    _repurpose_tone = st.selectbox("Tone", _TONES, key="repurpose_tone")

                    if st.button("♻️ Repurpose Content", key="gen_repurpose", type="primary", use_container_width=True):
                        if not _repurpose_src.strip():
                            st.error("Paste some content to repurpose.")
                        elif not _repurpose_platforms:
                            st.error("Select at least one platform.")
                        else:
                            import thinktank.engine.ai as _rai
                            _plat_list = ", ".join(_repurpose_platforms)
                            _repurpose_prompt = f"""You are a content transformation specialist. Your job is not to translate — it's to REIMAGINE this content for each platform's culture, psychology, and audience behaviour.

Tone: {_repurpose_tone}
Platforms: {_plat_list}

ORIGINAL CONTENT:
{_repurpose_src}

For each platform, don't just reformat — extract the CORE IDEA and rebuild it from scratch using that platform's native language. Ask yourself: "What would a top creator on this platform say about this same idea?"

Platform transformation rules:
- **Twitter/X**: Strip to the bone. One insight, max 280 chars. Sound like a person, not a brand. Opinions > announcements.
- **LinkedIn**: Lead with a career or business insight. Use line breaks. Start with a hook sentence. End with a question that makes professionals think. No hashtag spam.
- **TikTok Script**: Write for the ear, not the eye. Hook in line 1 (spoken out loud it must stop scrolling). Short punchy sentences. Rhythm matters — read it aloud. 45-60 seconds.
- **Instagram Caption**: Open with one emotion-hitting line. Use whitespace. Tell a micro-story. Hashtags ONLY on the final line, grouped.
- **Facebook**: Warmth and community. Share something that makes people feel less alone. Ask a real question at the end. 100-200 words.
- **YouTube Description**: Open with the viewer's benefit ("In this video you'll learn..."). Pack keywords naturally into first 2 lines. Include [timestamp] placeholders. CTA at end.
- **Threads**: Raw thoughts, no polish. Under 500 chars. Like you're thinking out loud to people who get it.
- **Reddit**: Provide genuine value with zero promotional energy. Be humble, be helpful, be specific. If it sounds like marketing, start over.

Format each with "## [Platform]" as a header. Every version must feel native — like it was written FOR that platform, not adapted TO it."""
                            with st.spinner(f"Repurposing for {len(_repurpose_platforms)} platforms..."):
                                _repurpose_result = _rai.chat([
                                    {"role": "system", "content": _STUDIO_SYS},
                                    {"role": "user",   "content": _repurpose_prompt},
                                ])
                            # save to DB permanently
                            _sdb.studio_save(_studio_sid, ", ".join(_repurpose_platforms),
                                             _repurpose_src[:80], _repurpose_tone,
                                             _repurpose_result, "repurpose_engine")

                    # load all saved repurpose outputs from DB
                    _saved_repurpose = [r for r in _sdb.studio_list(_studio_sid)
                                        if r["content_type"] == "repurpose_engine"]
                    if _saved_repurpose:
                        st.success(f"✅ {len(_saved_repurpose)} repurpose project(s) saved to your account")
                        for _rp in reversed(_saved_repurpose):
                            with st.expander(f"♻️ {_rp['platform']} — {_rp['topic'][:50]} · {_rp['created_at'][:10]}", expanded=(_rp == _saved_repurpose[-1])):
                                st.markdown(_rp["content"])
                                if st.button("🗑 Delete", key=f"del_repurpose_{_rp['id']}"):
                                    _sdb.studio_delete(_rp["id"])
                                    st.rerun()

                # ── Brand Voice Builder ───────────────────────────────────────
                with _tool_tab3:
                    st.markdown("**Your Brand Voice Profile** — so every future post sounds like YOU, not generic AI.")
                    _bv_name     = st.text_input("Your name / brand name", key="bv_name",
                                                  placeholder="e.g. Stellarick / ThinkTank")
                    _bv_niche    = st.text_input("Your niche / industry", key="bv_niche",
                                                  placeholder="e.g. Entrepreneur, Music Producer, Fitness Coach")
                    _bv_audience = st.text_input("Your target audience", key="bv_audience",
                                                  placeholder="e.g. Young entrepreneurs, 18-35, want financial freedom")
                    _bv_examples = st.text_area("Paste 2-3 examples of your best posts (optional but strongly recommended)",
                                                 key="bv_examples", height=120,
                                                 placeholder="Paste captions, tweets, or anything you've written that sounds most like you...")
                    _bv_words    = st.text_input("3 words that describe your vibe", key="bv_words",
                                                  placeholder="e.g. Bold, Authentic, Motivational")

                    if st.button("🎙️ Build My Brand Voice", key="gen_brand_voice", type="primary", use_container_width=True):
                        if not _bv_name.strip() or not _bv_niche.strip():
                            st.error("Enter your name and niche at minimum.")
                        else:
                            import thinktank.engine.ai as _bai
                            _bv_prompt = f"""You are a brand identity architect and voice coach. You help creators and entrepreneurs sound unmistakably like themselves — not like a template.

CREATOR INFO:
Name/Brand: {_bv_name}
Niche: {_bv_niche}
Audience: {_bv_audience or "not specified"}
Energy/Vibe: {_bv_words or "not specified"}
{"Their actual writing samples:\n" + _bv_examples if _bv_examples.strip() else "No samples provided — infer from their niche and vibe."}

Your job: Build a Brand Voice Profile so detailed and specific that ANY piece of content generated from it sounds like it could ONLY come from {_bv_name}. Not "a professional." Not "an entrepreneur." THEM.

## 🎙️ Brand Voice DNA
3 sentences max. Capture the essence — the feeling someone gets reading their content. What emotion does it trigger? What world does it invite people into?

## ✅ 10 Voice Rules — Specific, Not Generic
These must be operational instructions, not vibes. Bad: "Be authentic." Good: "Start with the word 'Look,' when making a strong point. End posts with a single-sentence gut punch. Use em-dashes — like this — to add weight mid-sentence."
Write 10 rules like that.

## ❌ 5 Things That Kill This Voice
Specific phrases, sentence structures, or tones that would make this brand sound like everyone else. Not "avoid jargon" — name the ACTUAL jargon.

## 💬 10 Signature Phrases & Sentence Starters
Ready-to-steal phrase templates that feel native to this voice. Include sentence starters, closers, and mid-post pivots. These should feel like something only {_bv_name} would say.

## 📱 Platform Personalities
How {_bv_name}'s voice shifts — not changes — across:
- **Twitter/X**: same person, sharper edge
- **LinkedIn**: same person, earned authority tone
- **TikTok**: same person, speaking out loud to a crowd
- **Instagram**: same person, more visual/emotional storytelling

## 🚀 Your Master AI Content Prompt
A single reusable prompt they paste into any AI tool to generate on-brand content every time. Must include [TOPIC], [PLATFORM], [TONE], and embed their voice instructions directly. This prompt should make AI output sound like {_bv_name}, not a robot."""
                            with st.spinner("Building your Brand Voice Profile..."):
                                _bv_result = _bai.chat([
                                    {"role": "system", "content": _STUDIO_SYS},
                                    {"role": "user",   "content": _bv_prompt},
                                ])
                            # save to DB permanently
                            _sdb.studio_save(_studio_sid, "Brand Voice",
                                             _bv_name, _bv_words or "custom",
                                             _bv_result, "brand_voice_builder")

                    # load all saved brand voice profiles from DB
                    _saved_bv = [r for r in _sdb.studio_list(_studio_sid)
                                 if r["content_type"] == "brand_voice_builder"]
                    if _saved_bv:
                        st.success(f"✅ {len(_saved_bv)} Brand Voice Profile(s) saved to your account")
                        for _bvs in reversed(_saved_bv):
                            with st.expander(f"🎙️ {_bvs['topic']} · {_bvs['created_at'][:10]}", expanded=(_bvs == _saved_bv[-1])):
                                st.markdown(_bvs["content"])
                                st.info("💡 Copy this entire profile and paste it into any AI tool as your starting context.")
                                if st.button("🗑 Delete", key=f"del_bv_{_bvs['id']}"):
                                    _sdb.studio_delete(_bvs["id"])
                                    st.rerun()

        # ── No active session — show session picker ───────────────────────────
        if not st.session_state.tool_session_active or _tool_seconds_left() <= 0:

            # load loyalty status
            from thinktank.engine.db import tool_loyalty_status, tool_loyalty_discount, tool_session_record
            _loyalty = tool_loyalty_status(_studio_sid)

            # loyalty badge
            if _loyalty["discount_active"]:
                st.success(f"🎉 **Power User discount active!** You get **{_loyalty['discount_pct']}% off** your next session — you've used the tools {_loyalty['sessions_this_week']} times this week.")
            elif _loyalty["sessions_this_week"] > 0:
                _remaining = _loyalty["sessions_until_discount"]
                st.info(f"⚡ **{_loyalty['sessions_this_week']} sessions this week** — {_remaining} more session{'s' if _remaining != 1 else ''} to unlock your **{_loyalty['discount_pct']}% loyalty discount**!")

            st.markdown(
                "**Creator Power Tools** give you timed studio access — like renting professional equipment. "
                "Pick a session length, spend your coins, and the tools unlock for that window."
            )
            st.caption("⏱️ Your timer only runs while this tab is open. Coins are spent when you start the session.")

            _loyalty_disc = tool_loyalty_discount(_studio_sid)

            _session_cols = st.columns(2)
            _session_items = list(_TOOL_SESSIONS.items())
            for _si, (_slabel, _sdata) in enumerate(_session_items):
                with _session_cols[_si % 2]:
                    with st.container(border=True):
                        _sm, _sc = _sdata["minutes"], _sdata["coins"]
                        # apply loyalty discount if earned
                        _sc_final = max(1, round(_sc * (1 - _loyalty_disc)))
                        _disc_label = f" ~~{_sc}~~ **{_sc_final}** coins 🎉 10% off" if _loyalty_disc > 0 else f"**{_sc_final} coins**"
                        st.markdown(f"### ⏱️ {_sm} Minutes")
                        st.markdown(f"{_disc_label} · ~${_sc_final * 0.20:.0f} value")
                        _per_min = round(_sc_final / _sm, 1)
                        st.caption(f"{_per_min} coins/min · {'Best value' if _sm >= 45 else 'Quick session'}")
                        if st.button(f"Unlock {_sm} min", key=f"start_session_{_sm}", type="primary", use_container_width=True):
                            if _studio_bal < _sc_final:
                                st.error(f"💰 Need {_sc_final} coins — you have {_studio_bal}. Go to 💳 Buy Coins to top up.")
                            else:
                                _sdb.coin_spend(_studio_sid, _sc_final)
                                tool_session_record(_studio_sid, _sm, _sc_final)
                                _now  = _time.time()
                                _end  = _now + (_sm * 60)
                                # save to DB FIRST — survives any reload or logout
                                tool_session_save(_studio_sid, _end, _sm)
                                st.session_state.tool_session_active   = True
                                st.session_state.tool_session_end      = _end
                                st.session_state.tool_session_mins     = _sm
                                st.session_state.tool_warned           = False
                                st.session_state.tool_session_recorded = True
                                st.rerun()


with tab_coins:
    try:
        import uuid as _uuid
        import urllib.request as _ureq
        import urllib.parse as _uparse
        import json as _json

        def _sec(k):
            import os
            # Railway env vars always win — prevents secrets.toml from overriding live keys
            env_val = os.environ.get(k, "")
            if env_val:
                return env_val
            try:
                return st.secrets.get(k, "") or ""
            except Exception:
                return ""

        # ── Session + balance (must come before any use of _bal) ─────────────
        # If logged in, use email as the persistent wallet ID
        if "coin_session_id" not in st.session_state:
            import uuid as _uuid2
            st.session_state.coin_session_id = str(_uuid2.uuid4())
        _sid_early = _auth_sid() if st.session_state.auth_user else st.session_state.coin_session_id
        import thinktank.engine.db as _earlydb
        _bal = _earlydb.coin_get_or_create(_sid_early)

        st.subheader("💳 Buy Coins")
        st.caption("Coins power your ThinkTank AI sessions. Buy once, use anytime — coins never expire.")
        if _bal == 5 and not st.session_state.get("welcome_shown"):
            st.success("🎁 Welcome! You've been given **5 free coins** to try ThinkTank. Head to the 💬 Ask tab to use them.")
            st.session_state.welcome_shown = True

        _stripe_key = _sec("STRIPE_SECRET_KEY").encode("ascii", errors="ignore").decode("ascii").strip()

        def _stripe_checkout(price_id, coins, session_id, api_key):
            """Call Stripe Checkout API directly — no SDK, no encoding issues."""
            import base64, urllib.error as _uerr
            # Strip any non-ASCII / whitespace characters that may have crept in
            api_key   = api_key.encode("ascii",   errors="ignore").decode("ascii").strip()
            price_id  = price_id.encode("ascii",  errors="ignore").decode("ascii").strip()
            base = "https://www.thinktankapp.net"
            body = _uparse.urlencode({
                "mode": "payment",
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "success_url": f"{base}?sid={session_id}&purchase=success&coins={coins}&session={session_id}",
                "cancel_url":  f"{base}?sid={session_id}&purchase=cancelled",
                "metadata[session_id]": session_id,
                "metadata[coins]": str(coins),
            })
            token = base64.b64encode(f"{api_key}:".encode("ascii")).decode("ascii")
            req = _ureq.Request(
                "https://api.stripe.com/v1/checkout/sessions",
                data=body.encode("ascii"),
                headers={
                    "Authorization": f"Basic {token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            try:
                with _ureq.urlopen(req, timeout=30) as resp:
                    return _json.loads(resp.read().decode("utf-8"))
            except _uerr.HTTPError as http_err:
                err_body = http_err.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Stripe {http_err.code}: {err_body}") from None

        # ── Session ID ────────────────────────────────────────────────────────
        # _sid and _bal already set above — just alias for clarity
        _sid    = _sid_early
        _coindb = _earlydb

        # ── Packages ──────────────────────────────────────────────────────────
        _PKGS = [
            # ── ThinkTank AI Packs ────────────────────────────────────────────
            {"id": "starter",         "label": "Starter",          "coins": 25,  "price": "$4.99",  "tier": None,            "price_id": _sec("STRIPE_PRICE_STARTER"),         "desc": "Try all ThinkTank AI tools"},
            {"id": "standard",        "label": "Standard",         "coins": 60,  "price": "$9.99",  "tier": None,            "price_id": _sec("STRIPE_PRICE_STANDARD"),        "desc": "Heavy AI usage + content posts"},
            {"id": "pro",             "label": "Pro",               "coins": 150, "price": "$19.99", "tier": None,            "price_id": _sec("STRIPE_PRICE_PRO"),             "desc": "Full AI suite + 2 weeks of content"},
            # ── Content Studio Plans ──────────────────────────────────────────
            {"id": "studio_starter",  "label": "Studio Starter",   "coins": 20,  "price": "$15",    "tier": "studio_starter","price_id": _sec("STRIPE_PRICE_STUDIO_STARTER"),  "desc": "📱 Posts · Hashtags · TikTok scripts · 15% multi-platform"},
            {"id": "studio_pro",      "label": "Studio Pro",        "coins": 85,  "price": "$65",    "tier": "studio_pro",    "price_id": _sec("STRIPE_PRICE_STUDIO_PRO"),      "desc": "📱 All Starter features + 3-coin edits"},
            {"id": "studio_week1",    "label": "Studio Week 1",     "coins": 110, "price": "$200",   "tier": "studio_week1",  "price_id": _sec("STRIPE_PRICE_STUDIO_WEEK1"),    "desc": "📱 Up to 3 platforms · Full week · Daily email 12:01 AM · 3-coin edits"},
            {"id": "studio_2week",    "label": "Studio 2-Week",     "coins": 250, "price": "$425",   "tier": "studio_2week",  "price_id": _sec("STRIPE_PRICE_STUDIO_2WEEK"),    "desc": "📱 All 5 platforms · 2 weeks · FREE edits · Daily email · 35% promo code"},
            {"id": "studio_max",      "label": "Studio Max",        "coins": 700, "price": "$700",   "tier": "studio_max",    "price_id": _sec("STRIPE_PRICE_STUDIO_MAX"),      "desc": "📱 Unlimited Studio · Permanent FREE edits · 700 coins · 35% promo code"},
        ]

        # hold checkout URL in session_state so it survives Streamlit reruns
        if "checkout_url" not in st.session_state:
            st.session_state.checkout_url = None
        if "checkout_error" not in st.session_state:
            st.session_state.checkout_error = None

        # ── helper: buy button logic ──────────────────────────────────────────
        from thinktank.engine.db import user_set_plan, user_get_plan, FREE_EDIT_TIERS

        def _do_buy(pkg):
            if not st.session_state.auth_user:
                st.session_state.checkout_error = None
                st.session_state.checkout_url   = None
                st.session_state["show_login_gate"] = True
            elif not _stripe_key:
                st.session_state.checkout_error = "Stripe not configured."
            elif not pkg["price_id"]:
                st.session_state.checkout_error = f"Price ID for {pkg['label']} not set — add to Railway variables."
            else:
                st.session_state["show_login_gate"] = False
                try:
                    _co = _stripe_checkout(pkg["price_id"], pkg["coins"], _sid, _stripe_key)
                    st.session_state.checkout_url   = _co["url"]
                    st.session_state.checkout_error = None
                    # upgrade plan tier on click (confirmed on return)
                    st.session_state["pending_tier"] = pkg.get("tier")
                except Exception as _e:
                    st.session_state.checkout_url   = None
                    st.session_state.checkout_error = f"Payment error: {_e}"

        # ── Login gate — rendered FIRST so it's impossible to miss ───────────
        # When a buy button is clicked while logged out, this renders at the
        # TOP of the purchase area before the packages, forcing the user to
        # register/login before they can scroll past to buy anything.
        if st.session_state.get("show_login_gate"):
            st.error("🔑 **You need a free account to purchase** — your coins are tied to your account so they're never lost.")
            with st.container(border=True):
                st.markdown("#### Log in or Create a Free Account")
                _gt = st.radio("", ["Register (new)", "Log in (existing)"], horizontal=True,
                               key="gate_auth_mode", label_visibility="collapsed")
                _gcol1, _gcol2 = st.columns(2)
                with _gcol1:
                    _ge = st.text_input("Email", key="gate_email", placeholder="you@example.com")
                with _gcol2:
                    _gp = st.text_input("Password", key="gate_pw", type="password",
                                        placeholder="Min 6 characters")
                if _gt == "Register (new)":
                    if st.button("✅ Create account & continue to payment", key="gate_register",
                                 type="primary", use_container_width=True):
                        _gr = user_register(_ge, _gp)
                        if _gr["ok"]:
                            _anon = st.session_state.get("_GLOBAL_SID", "")
                            if _anon:
                                user_merge_session(_gr["email"], _anon)
                            _gdb_mod.sid_save_auth(_GLOBAL_SID, _gr["email"])
                            st.session_state.auth_user = _gr["email"]
                            st.session_state["show_login_gate"] = False
                            st.rerun()
                        else:
                            st.error(_gr["error"])
                else:
                    if st.button("✅ Log in & continue to payment", key="gate_login",
                                 type="primary", use_container_width=True):
                        _gr = user_login(_ge, _gp)
                        if _gr["ok"]:
                            _anon = st.session_state.get("_GLOBAL_SID", "")
                            if _anon:
                                user_merge_session(_gr["email"], _anon)
                            _gdb_mod.sid_save_auth(_GLOBAL_SID, _gr["email"])
                            st.session_state.auth_user = _gr["email"]
                            st.session_state["show_login_gate"] = False
                            st.rerun()
                        else:
                            st.error(_gr["error"])
            st.divider()

        # ── ThinkTank AI Coins ────────────────────────────────────────────────
        st.markdown("#### 🧠 ThinkTank AI Coins")
        st.caption("Power the decision engine — Ask, Ideas, Analysis, Gate, Room.")
        _c1, _c2, _c3 = st.columns(3)
        for _col, _pkg in zip([_c1, _c2, _c3], _PKGS[:3]):
            with _col:
                with st.container(border=True):
                    st.markdown(f"### {_pkg['label']}")
                    st.markdown(f"**{_pkg['coins']} coins**")
                    st.markdown(f"**{_pkg['price']}** one-time")
                    st.caption(_pkg.get("desc", ""))
                    if st.button(f"Buy {_pkg['label']}", key=f"buy_{_pkg['id']}", type="primary", use_container_width=True):
                        _do_buy(_pkg)

        # ── Content Studio Coins ──────────────────────────────────────────────
        st.divider()
        st.markdown("#### 📱 Content Studio Coins")
        st.caption("Power the Content Studio — posts, TikTok scripts, full-week content, Creator Power Tools.")
        # row 1: Studio Starter + Studio Pro
        _sr1, _sr2 = st.columns(2)
        for _scol, _spkg in zip([_sr1, _sr2], _PKGS[3:5]):
            with _scol:
                with st.container(border=True):
                    st.markdown(f"### {_spkg['label']}")
                    st.markdown(f"**{_spkg['coins']} coins · {_spkg['price']}**")
                    st.caption(_spkg.get("desc", ""))
                    if st.button(f"Buy {_spkg['label']}", key=f"buy_{_spkg['id']}", type="primary", use_container_width=True):
                        _do_buy(_spkg)
        # row 2: Week 1 + 2-Week + Max (full width cards)
        for _spkg in _PKGS[5:]:
            with st.container(border=True):
                _pa, _pb = st.columns([3,1])
                with _pa:
                    st.markdown(f"### {_spkg['label']} — {_spkg['price']}")
                    st.caption(_spkg.get("desc", ""))
                    st.markdown(f"**{_spkg['coins']} coins included**")
                with _pb:
                    if st.button(f"Buy {_spkg['label']}", key=f"buy_{_spkg['id']}", type="primary", use_container_width=True):
                        _do_buy(_spkg)

        # ── Checkout area — anchor for auto-scroll ────────────────────────────
        st.markdown('<div id="checkout-anchor"></div>', unsafe_allow_html=True)
        if st.session_state.checkout_error:
            st.error(st.session_state.checkout_error)
        if st.session_state.checkout_url:
            # auto-scroll to checkout the moment the URL appears
            import streamlit.components.v1 as _pay_components
            _pay_components.html(
                "<script>"
                "window.parent.document.getElementById('checkout-anchor')"
                ".scrollIntoView({behavior:'smooth',block:'center'});"
                "</script>",
                height=0,
            )
            st.success("✅ Checkout ready — click below to complete your purchase!")
            st.link_button("👉 Complete Payment on Stripe", st.session_state.checkout_url, type="primary", use_container_width=True)
            st.info("After payment, return here — your coins load automatically.")
            st.caption("💡 Checkout loads slowly in Firefox? Try Chrome or Edge — it's the browser, not your connection.")
            if st.button("✖ Cancel", key="cancel_checkout"):
                st.session_state.checkout_url = None
                st.rerun()

        st.divider()
        st.metric("Your Coin Balance", f"{_bal} coins")
        st.divider()

        # ── Handle return from Stripe ─────────────────────────────────────────
        _qp = st.query_params
        if _qp.get("purchase") == "success":
            _return_coins = int(_qp.get("coins", "0"))
            _return_sid   = _qp.get("session", _sid)
            if _return_coins > 0:
                _coindb.coin_credit(_return_sid, _return_coins, f"url-credit-{_return_sid}-{_return_coins}")
                if _return_sid != _sid:
                    _coindb.coin_credit(_sid, _return_coins, f"url-credit-{_sid}-{_return_coins}")
            # upgrade plan tier if a studio plan was purchased
            _pending_tier = st.session_state.pop("pending_tier", None)
            _promo_earned = None
            if _pending_tier and st.session_state.auth_user:
                _promo_earned = user_set_plan(st.session_state.auth_user, _pending_tier)
            _bal_now = _coindb.coin_get_or_create(_sid)
            st.success(f"✅ Payment confirmed! **{_bal_now} coins** are ready to use.")
            if _promo_earned:
                st.balloons()
                st.info(f"🎉 Your exclusive 35% off promo code: **`{_promo_earned}`** — use it on your next purchase. Save it now!")
            if st.button("🔄 Continue"):
                st.query_params.clear()
                st.rerun()
        elif _qp.get("purchase") == "cancelled":
            st.warning("Purchase cancelled. No charge was made.")
            st.query_params.clear()

        # ── Promo code redemption ──────────────────────────────────────────────
        st.divider()
        st.markdown("#### 🎟 Have a Promo Code?")
        from thinktank.engine.db import promo_validate, promo_apply
        _promo_input = st.text_input("Enter promo code", placeholder="TT35-XXXXX-XXXX", key="promo_input")
        if st.button("Apply Code", key="apply_promo"):
            if not st.session_state.auth_user:
                st.error("Log in first to apply a promo code.")
            elif not _promo_input.strip():
                st.error("Please enter a promo code.")
            else:
                _pv = promo_validate(_promo_input.strip())
                if not _pv["valid"]:
                    st.error(_pv["error"])
                else:
                    promo_apply(_promo_input.strip())
                    st.session_state["promo_discount"] = 0.35
                    st.success("✅ Promo code applied! You'll get 35% off your next purchase. Select a pack above to buy.")

        # ── Show current plan + promo if logged in ────────────────────────────
        if st.session_state.auth_user:
            _up = user_get_plan(st.session_state.auth_user)
            if _up["plan_tier"] != "free":
                st.divider()
                st.markdown(f"**Your Plan:** `{_up['plan_tier'].replace('_',' ').title()}`")
            if _up["promo_code"] and not _up["promo_used"]:
                st.info(f"🎟 Your promo code: **`{_up['promo_code']}`** (35% off next purchase — unused)")

    except Exception as _coins_err:
        st.error(f"Buy Coins error: {_coins_err}")
        import traceback
        st.code(traceback.format_exc())

    # ── Donate nudge at bottom of Buy Coins ───────────────────────────────────
    st.divider()
    st.markdown(
        """
        <div style="background:#fff8f0;border:1px solid #f5a623;border-radius:8px;
                    padding:16px 20px;text-align:center;max-width:480px;margin:0 auto;">
            <div style="font-size:1rem;font-weight:700;color:#c05c00;margin-bottom:6px;">
                ☕ Love ThinkTank?
            </div>
            <div style="font-size:0.85rem;color:#7a5000;margin-bottom:14px;line-height:1.6;">
                Coins keep the AI running. But if ThinkTank has genuinely helped you think,
                a small donation means the world.
            </div>
            <a href="https://paypal.me/CDovico" target="_blank" rel="noopener"
               style="display:inline-block;background:#003087;color:#fff;
                      text-decoration:none;font-size:0.9rem;font-weight:700;
                      padding:11px 32px;border-radius:6px;">
                ♥ Donate via PayPal
            </a>
            <div style="font-size:0.7rem;color:#aaa;margin-top:8px;">paypal.me/CDovico &nbsp;·&nbsp; Any amount is appreciated</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ==============================================================================
# ADMIN TAB
# ==============================================================================
with tab_admin:
    # ── Password gate ─────────────────────────────────────────────────────────
    def _get_admin_secret(k):
        import os
        try:
            v = st.secrets.get(k, "") or ""
            return v if v else os.environ.get(k, "")
        except Exception:
            return os.environ.get(k, "")

    _admin_pw = _get_admin_secret("ADMIN_PASSWORD") or "thinktank-admin"
    if "admin_unlocked" not in st.session_state:
        st.session_state.admin_unlocked = False

    if not st.session_state.admin_unlocked:
        st.subheader("⚙️ Admin / Settings")
        _pw_input = st.text_input("Enter admin password", type="password", key="admin_pw_input")
        if st.button("Unlock", type="primary"):
            if _pw_input == _admin_pw:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect password.")
        st.stop()

    st.subheader("⚙️ Admin / Settings")

    from thinktank.engine.ai import is_available, chat as ai_chat

    def _get_secret(key):
        import os
        try:
            val = st.secrets.get(key, "") or ""
            return val if val else os.environ.get(key, "")
        except Exception:
            return os.environ.get(key, "")

    # ── AI Backend Status ─────────────────────────────────────────────────────
    st.markdown("### 🤖 AI Backend Status")

    openai_key = _get_secret("OPENAI_API_KEY")
    if openai_key:
        st.info("🟢 **Active provider: OpenAI (gpt-4o-mini)** — Ollama is available as fallback")
    else:
        st.info("🟡 **Active provider: Ollama** — Add OPENAI_API_KEY to secrets/env to use OpenAI")

    col_ai1, col_ai2 = st.columns(2)

    with col_ai1:
        st.markdown("**OpenAI (gpt-4o-mini)**")
        if st.button("Check OpenAI Connection", type="primary"):
            if not openai_key:
                st.warning("⚠️ No OPENAI_API_KEY found")
            else:
                try:
                    ai_chat([{"role": "user", "content": "ping"}])
                    st.success("✅ OpenAI is connected · Active AI provider")
                except Exception as e:
                    st.error(f"❌ OpenAI error: {e}")

    with col_ai2:
        st.markdown("**Ollama (Local Fallback)**")
        if st.button("Check Ollama Connection"):
            ok, msg = is_available(cfg.OLLAMA_MODEL)
            if ok:
                st.success(f"✅ Ollama running · Model `{cfg.OLLAMA_MODEL}` ready")
            else:
                st.warning(f"⚠️ {msg}")
                st.code(f"ollama serve\nollama pull {cfg.OLLAMA_MODEL}", language="bash")

    st.divider()

    # ── Grant Coins (admin tool) ──────────────────────────────────────────────
    st.markdown("### 🪙 Grant Coins to User")
    _gc1, _gc2, _gc3 = st.columns([3, 1, 1])
    with _gc1:
        _grant_email = st.text_input("Email address", key="grant_email", placeholder="user@example.com")
    with _gc2:
        _grant_amount = st.number_input("Coins", min_value=1, max_value=10000, value=200, key="grant_amount")
    with _gc3:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("✅ Grant", type="primary", use_container_width=True, key="do_grant_coins"):
            if not _grant_email.strip():
                st.error("Enter an email.")
            else:
                import thinktank.engine.db as _gcdb
                _gcdb.coin_get_or_create(_grant_email.strip().lower())
                _gcdb.coin_credit(_grant_email.strip().lower(), int(_grant_amount),
                                  f"admin-grant-{_grant_email.strip().lower()}-{_grant_amount}")
                _new_bal = _gcdb.coin_balance(_grant_email.strip().lower())
                st.success(f"✅ Granted {_grant_amount} coins to **{_grant_email}** — new balance: **{_new_bal} coins**")

    st.divider()

    # ── Database Health Check ─────────────────────────────────────────────────
    st.markdown("### 🗄️ Database Health")
    from thinktank.config import DB_PATH as _ADMIN_DB_PATH
    import os as _admin_os

    _db_col1, _db_col2 = st.columns(2)
    with _db_col1:
        with st.container(border=True):
            st.markdown("**Active DB Path**")
            st.code(_ADMIN_DB_PATH)
            _on_volume = _ADMIN_DB_PATH.startswith("/data")
            if _on_volume:
                st.success("✅ On Railway persistent volume — accounts survive redeploys")
            else:
                st.error("❌ NOT on volume — container disk resets on every redeploy!")
            if _admin_os.path.exists(_ADMIN_DB_PATH):
                _db_size = _admin_os.path.getsize(_ADMIN_DB_PATH)
                st.caption(f"File exists · {_db_size:,} bytes")
            else:
                st.warning("⚠️ DB file not found at this path yet")
    with _db_col2:
        with st.container(border=True):
            st.markdown("**Resolution chain**")
            import os as _o2
            from thinktank.config import _clean_path as _cp
            _env_raw    = _o2.environ.get("DB_PATH", "")
            _env_val    = _cp(_env_raw)
            _secret_val = ""
            try:
                _secret_val = _cp(st.secrets.get("DB_PATH", "") or "")
            except Exception:
                pass
            # show the cleaned value so it's clear what's actually being used
            st.markdown(f"1. Railway env var: `{'✅ ' + _env_val if _env_val else '❌ not set'}`")
            if _env_raw and _env_raw != _env_val:
                st.caption(f"⚠️ Raw value had key prefix — auto-stripped to: `{_env_val}`")
            st.markdown(f"2. secrets.toml:    `{'✅ ' + _secret_val if _secret_val else '❌ not set'}`")
            st.markdown(f"3. Fallback:        `./thinktank/thinktank.sqlite`")
            if not _on_volume:
                st.error("Go to Railway → Variables → set `DB_PATH` value to `/data/thinktank.sqlite` (no prefix)")

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

# ==============================================================================
# LEGAL TAB
# ==============================================================================
with tab_legal:
    st.subheader("📄 Legal")
    _legal_choice = st.radio("", ["📋 Terms of Service", "🔒 Privacy Policy"],
                             horizontal=True, key="legal_choice", label_visibility="collapsed")
    st.divider()

    if _legal_choice == "📋 Terms of Service":
        st.markdown("""
## Terms of Service

**Effective Date:** August 1, 2025

Welcome to **ThinkTank**, operated by Chris Dovico at **www.thinktankapp.net**.
By accessing or using ThinkTank you agree to be bound by these Terms.
If you do not agree, do not use the Service.

---

### 1. Acceptance

By creating an account or purchasing coins you confirm you are at least 18 years old
and accept these Terms in full.

---

### 2. The Service

ThinkTank provides AI-assisted decision-making tools, social media content generation,
and creator tools accessed through a virtual coin system.

---

### 3. Accounts

You must provide a valid email to register. You are responsible for all activity
under your account and for keeping your password confidential.
We may terminate accounts that violate these Terms.

---

### 4. Coins & Payments

- Coins are a virtual currency used solely within ThinkTank.
- All purchases are processed by Stripe, our third-party payment provider.
- **All coin purchases are final and non-refundable** except where required by law.
- Coins carry no cash value and cannot be transferred or redeemed for money.
- Coins do not expire while your account is active.
- We reserve the right to adjust pricing with reasonable notice.

---

### 5. Timed Sessions

- Creator Power Tool sessions are time-limited windows purchased with coins.
- Coins spent on sessions are non-refundable regardless of whether the session was fully used.
- Remaining session time is stored and can be resumed after a disconnect or logout.

---

### 6. AI-Generated Content

- ThinkTank uses OpenAI's API to generate content.
- AI outputs are provided **"as is"** with no guarantees of accuracy or fitness for purpose.
- You are solely responsible for reviewing and using any AI-generated content before publishing.
- ThinkTank is not liable for any consequences arising from use of AI-generated content.
- You retain ownership of content you generate, subject to OpenAI's usage policies.

---

### 7. Acceptable Use

You agree not to use ThinkTank to generate illegal, defamatory, or harmful content;
to reverse-engineer or scrape the platform; or to resell AI outputs as your own service.

---

### 8. Intellectual Property

ThinkTank's code, design, branding, and systems are owned by Chris Dovico and protected
by copyright. The name "ThinkTank" and associated branding are proprietary.
You may not copy or create derivative works without written permission.

---

### 9. Disclaimer of Warranties

THE SERVICE IS PROVIDED "AS IS" WITHOUT WARRANTIES OF ANY KIND.
WE DO NOT WARRANT UNINTERRUPTED OR ERROR-FREE OPERATION.

---

### 10. Limitation of Liability

TO THE FULLEST EXTENT PERMITTED BY LAW, THINKTANK AND ITS OPERATORS SHALL NOT
BE LIABLE FOR ANY INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES ARISING FROM
YOUR USE OF THE SERVICE.

---

### 11. Changes

We may update these Terms at any time. The "Effective Date" above will reflect the
most recent revision. Continued use constitutes acceptance.

---

### 12. Governing Law

These Terms are governed by the laws of the United States.

---

### 13. Contact

**chris@thinktankapp.net** · www.thinktankapp.net
        """)

    elif _legal_choice == "🔒 Privacy Policy":
        st.markdown("""
## Privacy Policy

**Effective Date:** August 1, 2025

ThinkTank ("we," "us," "our") operates **www.thinktankapp.net**.
This Policy explains what data we collect, how we use it, and your rights.

---

### 1. Information We Collect

**You provide:**
- Email address and hashed password when registering
- Text inputs (topics, briefs, content examples) used to generate AI outputs

**We collect automatically:**
- Coin purchase and usage records tied to your account
- AI-generated content saved to your account
- Power Tool session records for loyalty tracking

**We do not collect:**
- Credit card numbers or billing data — all payments are handled by Stripe

---

### 2. How We Use Your Information

- To create and manage your account
- To process purchases and maintain your coin balance
- To save and retrieve your generated content
- To track session usage for loyalty discounts
- To provide customer support and improve the Service

We do **not** sell or share your personal data with third parties for marketing.

---

### 3. Data Storage & Security

- Data is stored in a secure database on Railway's infrastructure.
- Passwords are hashed using SHA-256 — never stored in plain text.
- All data in transit is encrypted via HTTPS/TLS.

---

### 4. Third-Party Services

| Service | Purpose |
|---|---|
| OpenAI | AI content generation |
| Stripe | Payment processing |
| Railway | App hosting and database |

Your content inputs are sent to OpenAI's API to generate responses.
Please review [OpenAI's Privacy Policy](https://openai.com/privacy) for details.
Payment data is handled solely by [Stripe](https://stripe.com/privacy).

---

### 5. Data Retention

Your data is retained while your account is active.
To delete your account and all associated data, email **chris@thinktankapp.net**.

---

### 6. Your Rights

You may request to access, correct, or delete your personal data at any time.
You can export your generated content using the Download button in Content Studio.
Contact us at **chris@thinktankapp.net** to exercise these rights.

---

### 7. Cookies

ThinkTank does not use tracking or advertising cookies.
Session management is handled server-side.

---

### 8. Children

ThinkTank is not directed to children under 13 and we do not knowingly collect
data from minors.

---

### 9. Changes

We may update this Policy at any time. The "Effective Date" above reflects
the most recent revision.

---

### 10. Contact

**chris@thinktankapp.net** · www.thinktankapp.net
        """)
