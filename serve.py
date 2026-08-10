"""
serve.py - Entrypoint for Railway web process.
Serves /sitemap.xml and /robots.txt as raw files.
All other requests are proxied to Streamlit on port 8502.
"""
import os
import sys
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request as _ureq

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_PORT   = int(os.environ.get("PORT", 8501))
STREAMLIT_PORT = 8502

SITEMAP = open(os.path.join(BASE, "sitemap.xml"), "rb").read()
ROBOTS  = open(os.path.join(BASE, "robots.txt"),  "rb").read()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/sitemap.xml":
            self._send(200, "application/xml; charset=utf-8", SITEMAP)
        elif path == "/robots.txt":
            self._send(200, "text/plain; charset=utf-8", ROBOTS)
        else:
            self._proxy()

    def do_POST(self):
        self._proxy()

    def _proxy(self):
        url = f"http://127.0.0.1:{STREAMLIT_PORT}{self.path}"
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in ("host", "content-length")}
        try:
            req  = _ureq.Request(url, data=body, headers=headers, method=self.command)
            resp = _ureq.urlopen(req, timeout=30)
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() in ("content-type", "content-length", "set-cookie"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def _send(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # suppress access logs


def start_streamlit():
    subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(STREAMLIT_PORT),
        "--server.address", "127.0.0.1",
        "--server.headless", "true",
    ])


if __name__ == "__main__":
    print(f"[serve] Starting Streamlit on internal port {STREAMLIT_PORT}")
    start_streamlit()
    print(f"[serve] Proxy listening on public port {PUBLIC_PORT}")
    HTTPServer(("0.0.0.0", PUBLIC_PORT), Handler).serve_forever()
