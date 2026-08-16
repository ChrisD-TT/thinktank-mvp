"""
ThinkTank — Email delivery via SendGrid.
Falls back gracefully if SENDGRID_API_KEY is not set.

Usage:
    from thinktank.engine.email import send_email
    send_email(
        to="user@example.com",
        subject="Welcome to ThinkTank",
        html_body="<p>Hi there!</p>",
    )
"""

import os
import json
import urllib.request as _ureq
import urllib.error as _uerr


FROM_EMAIL = "Chris@ThinkTankApp.Net"
FROM_NAME  = "ThinkTank"


def _get_api_key() -> str:
    key = os.environ.get("SENDGRID_API_KEY", "")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("SENDGRID_API_KEY", "") or ""
    except Exception:
        return ""


def send_email(to: str, subject: str, html_body: str, plain_body: str = "") -> dict:
    """
    Send a transactional email via SendGrid.
    Returns {"ok": True} or {"ok": False, "error": str}.
    Silently skips if SENDGRID_API_KEY is not configured.
    """
    api_key = _get_api_key()
    if not api_key:
        print(f"[email] SENDGRID_API_KEY not set — skipping email to {to}")
        return {"ok": False, "error": "SENDGRID_API_KEY not configured"}

    if not plain_body:
        # Strip basic HTML tags for plain text fallback
        import re
        plain_body = re.sub(r"<[^>]+>", "", html_body).strip()

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": FROM_EMAIL, "name": FROM_NAME},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_body},
            {"type": "text/html",  "value": html_body},
        ],
    }

    data = json.dumps(payload).encode("utf-8")
    req = _ureq.Request(
        "https://api.sendgrid.com/v3/mail/send",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with _ureq.urlopen(req, timeout=15) as resp:
            # SendGrid returns 202 Accepted on success (no body)
            print(f"[email] Sent '{subject}' to {to} — HTTP {resp.status}")
            return {"ok": True}
    except _uerr.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[email] SendGrid error {e.code}: {body}")
        return {"ok": False, "error": f"SendGrid {e.code}: {body}"}
    except Exception as e:
        print(f"[email] Unexpected error: {e}")
        return {"ok": False, "error": str(e)}


# ── Email templates ───────────────────────────────────────────────────────────

def email_welcome(email: str, coins: int) -> dict:
    """Send welcome email to a new registrant."""
    subject = "Welcome to ThinkTank 🧠"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#0a1628;color:#dce9ff;border-radius:12px;">
      <h1 style="color:#7eb8f7;font-size:1.6rem;margin-bottom:8px;">Welcome to ThinkTank 🧠</h1>
      <p style="color:#b8d0ee;font-size:1rem;line-height:1.7;">
        Your account is live. You've been given <strong style="color:#7eb8f7;">{coins} free AI coins</strong> to get started.
      </p>
      <h3 style="color:#7eb8f7;margin-top:28px;">3 things to try first:</h3>
      <ol style="color:#b8d0ee;line-height:2;">
        <li><strong>💬 Ask</strong> — ask ThinkTank anything. Strategy, content ideas, business decisions.</li>
        <li><strong>💡 Ideas</strong> — drop a business idea and run it through the Gate for a full analysis.</li>
        <li><strong>📱 Content Studio</strong> — generate social posts for any platform in seconds.</li>
      </ol>
      <p style="margin-top:28px;">
        <a href="https://www.thinktankapp.net" style="background:#7eb8f7;color:#0a1628;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;display:inline-block;">
          Open ThinkTank →
        </a>
      </p>
      <p style="color:#5f728d;font-size:0.78rem;margin-top:32px;">
        ThinkTank · thinktankapp.net · Reply to this email anytime.
      </p>
    </div>
    """
    return send_email(email, subject, html)


def email_purchase_confirmation(email: str, plan_label: str, coins: int) -> dict:
    """Send purchase confirmation for any coin pack or studio plan."""
    subject = f"ThinkTank — {plan_label} confirmed 🎉"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#0a1628;color:#dce9ff;border-radius:12px;">
      <h1 style="color:#7eb8f7;font-size:1.5rem;margin-bottom:8px;">Purchase confirmed 🎉</h1>
      <p style="color:#b8d0ee;font-size:1rem;line-height:1.7;">
        Your <strong style="color:#7eb8f7;">{plan_label}</strong> has been activated.
        <strong style="color:#7eb8f7;">{coins} coins</strong> have been added to your wallet.
      </p>
      <p style="color:#b8d0ee;line-height:1.7;">
        Coins never expire. Use them across Ask, Ideas, Analysis, Gate, and Content Studio.
      </p>
      <p style="margin-top:28px;">
        <a href="https://www.thinktankapp.net" style="background:#7eb8f7;color:#0a1628;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;display:inline-block;">
          Go to ThinkTank →
        </a>
      </p>
      <p style="color:#5f728d;font-size:0.78rem;margin-top:32px;">
        ThinkTank · thinktankapp.net · Questions? Reply to this email.
      </p>
    </div>
    """
    return send_email(email, subject, html)


def email_studio_week_welcome(email: str, plan_label: str, coins: int) -> dict:
    """Welcome email for Studio Week 1 and Studio 2-Week plans — explains daily delivery."""
    subject = f"ThinkTank Studio — Your {plan_label} is live 📱"
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#0a1628;color:#dce9ff;border-radius:12px;">
      <h1 style="color:#7eb8f7;font-size:1.5rem;margin-bottom:8px;">Your {plan_label} is live 📱</h1>
      <p style="color:#b8d0ee;font-size:1rem;line-height:1.7;">
        <strong style="color:#7eb8f7;">{coins} Studio coins</strong> have been added to your Content Studio wallet.
      </p>
      <h3 style="color:#7eb8f7;margin-top:24px;">What's included:</h3>
      <ul style="color:#b8d0ee;line-height:2;">
        <li>Generate posts, scripts, and hashtags for any platform</li>
        <li>Daily content ideas delivered to this email every morning</li>
        <li>Edit any post for 3 coins — FREE edits while your coins last</li>
        <li>Download your full content library anytime</li>
      </ul>
      <p style="color:#b8d0ee;margin-top:16px;line-height:1.7;">
        Your first daily content email will arrive tomorrow morning. We'll send 3 post ideas
        tailored to your niche — just reply to this email with your niche and we'll personalise it.
      </p>
      <p style="margin-top:28px;">
        <a href="https://www.thinktankapp.net" style="background:#7eb8f7;color:#0a1628;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;display:inline-block;">
          Open Content Studio →
        </a>
      </p>
      <p style="color:#5f728d;font-size:0.78rem;margin-top:32px;">
        ThinkTank · thinktankapp.net · Reply anytime to set your niche or ask a question.
      </p>
    </div>
    """
    return send_email(email, subject, html)


def email_daily_content_ideas(email: str, ideas: list[str], niche: str = "your niche") -> dict:
    """Daily content idea email for studio_week1 and studio_2week subscribers."""
    from datetime import datetime
    day = datetime.now().strftime("%A, %B %d")
    subject = f"ThinkTank — 3 content ideas for {day} 💡"
    ideas_html = "".join(
        f"<li style='margin-bottom:12px;color:#b8d0ee;line-height:1.6;'>{idea}</li>"
        for idea in ideas
    )
    html = f"""
    <div style="font-family:Segoe UI,sans-serif;max-width:560px;margin:0 auto;padding:32px 24px;background:#0a1628;color:#dce9ff;border-radius:12px;">
      <h1 style="color:#7eb8f7;font-size:1.4rem;margin-bottom:4px;">Your content ideas for {day} 💡</h1>
      <p style="color:#5f728d;font-size:0.85rem;margin-bottom:20px;">Niche: {niche}</p>
      <ol style="padding-left:20px;">{ideas_html}</ol>
      <p style="margin-top:28px;">
        <a href="https://www.thinktankapp.net" style="background:#7eb8f7;color:#0a1628;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;display:inline-block;">
          Generate these posts →
        </a>
      </p>
      <p style="color:#5f728d;font-size:0.78rem;margin-top:32px;">
        ThinkTank · thinktankapp.net · Reply to update your niche or pause these emails.
      </p>
    </div>
    """
    return send_email(email, subject, html)
