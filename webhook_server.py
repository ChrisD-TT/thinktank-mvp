"""
ThinkTank — Stripe webhook receiver.
Runs as a separate process alongside Streamlit:
    python webhook_server.py

Stripe CLI forwards events here:
    stripe listen --forward-to localhost:4242/webhook
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

# Load secrets from .streamlit/secrets.toml if present
def _load_secrets():
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return {}
    path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}

_secrets = _load_secrets()

STRIPE_SECRET_KEY     = _secrets.get("STRIPE_SECRET_KEY", "") or os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = _secrets.get("STRIPE_WEBHOOK_SECRET", "") or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PORT = 4242


class WebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        sig = self.headers.get("Stripe-Signature", "")

        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(body, sig, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            print(f"[webhook] Signature error: {e}")
            self.send_response(400)
            self.end_headers()
            return

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            meta = session.get("metadata", {})
            session_id = meta.get("session_id")
            coins = int(meta.get("coins", 0))
            stripe_session_id = session.get("id", "")

            if session_id and coins:
                # Import ThinkTank DB and credit coins
                sys.path.insert(0, os.path.dirname(__file__))
                from thinktank.engine.db import init_db, coin_credit
                init_db()
                coin_credit(session_id, coins, stripe_session_id)
                print(f"[webhook] Credited {coins} coins to session {session_id}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received": true}')

    def log_message(self, format, *args):
        print(f"[webhook] {format % args}")


if __name__ == "__main__":
    if not STRIPE_WEBHOOK_SECRET:
        print("ERROR: STRIPE_WEBHOOK_SECRET not set in .streamlit/secrets.toml")
        sys.exit(1)
    print(f"[webhook] Stripe webhook server running on http://localhost:{PORT}/webhook")
    print(f"[webhook] Run in another terminal:")
    print(f'[webhook]   stripe listen --forward-to localhost:{PORT}/webhook')
    HTTPServer(("localhost", PORT), WebhookHandler).serve_forever()
