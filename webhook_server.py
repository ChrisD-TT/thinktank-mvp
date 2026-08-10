"""
ThinkTank - Stripe webhook receiver + static file server.
Runs as a separate process alongside Streamlit.
Serves: /sitemap.xml, /robots.txt, /webhook (POST)
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

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
PORT = int(os.environ.get("WEBHOOK_PORT", 4242))

_BASE = os.path.dirname(os.path.abspath(__file__))

SITEMAP_XML = open(os.path.join(_BASE, "sitemap.xml"), "rb").read()
ROBOTS_TXT  = open(os.path.join(_BASE, "robots.txt"),  "rb").read()


class WebhookHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/sitemap.xml":
            self._respond(200, "application/xml", SITEMAP_XML)
        elif self.path in ("/robots.txt", "/robots"):
            self._respond(200, "text/plain", ROBOTS_TXT)
        else:
            self._respond(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, "text/plain", b"Not found")
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
            self._respond(400, "text/plain", b"Bad signature")
            return

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            meta = session.get("metadata", {})
            session_id = meta.get("session_id")
            coins = int(meta.get("coins", 0))
            stripe_session_id = session.get("id", "")

            if session_id and coins:
                sys.path.insert(0, os.path.dirname(__file__))
                from thinktank.engine.db import init_db, coin_credit
                init_db()
                coin_credit(session_id, coins, stripe_session_id)
                print(f"[webhook] Credited {coins} coins to session {session_id}")

        self._respond(200, "application/json", b'{"received": true}')

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[webhook] {format % args}")


if __name__ == "__main__":
    print(f"[webhook] Server running on port {PORT}")
    print(f"[webhook] Serving /sitemap.xml and /robots.txt")
    HTTPServer(("0.0.0.0", PORT), WebhookHandler).serve_forever()
