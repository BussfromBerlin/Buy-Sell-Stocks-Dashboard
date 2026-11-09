"""Local Stocks server. Prices are fetched when the process starts."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stocks.dashboard import build

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "static" / "index.html"
HOST = "127.0.0.1"
PORT = 8765


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ready = False
        self.error: str | None = None
        self.phase = "starting"
        self.done = 0
        self.total = 0
        self.detail = ""
        self.payload: dict | None = None

    def set_progress(self, phase: str, done: int, total: int, detail: str) -> None:
        with self.lock:
            self.phase = phase
            self.done = done
            self.total = total
            self.detail = detail

    def status(self) -> dict:
        with self.lock:
            return {
                "ready": self.ready,
                "error": self.error,
                "phase": self.phase,
                "done": self.done,
                "total": self.total,
                "detail": self.detail,
            }


STATE = State()


def _build() -> None:
    try:
        payload = build(STATE.set_progress)
        with STATE.lock:
            STATE.payload = payload
            STATE.ready = True
            STATE.phase = "ready"
    except Exception as exc:
        with STATE.lock:
            STATE.error = str(exc)
            STATE.phase = "error"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            body = json.dumps(STATE.status()).encode()
            self._send(200, body, "application/json")
            return
        if path == "/api/dashboard":
            with STATE.lock:
                ready = STATE.ready
                error = STATE.error
                payload = STATE.payload
            if error and not ready:
                self._send(500, json.dumps({"error": error}).encode(), "application/json")
                return
            if not ready:
                self._send(202, json.dumps(STATE.status()).encode(), "application/json")
                return
            self._send(200, json.dumps(payload).encode(), "application/json")
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def main() -> None:
    threading.Thread(target=_build, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Stocks http://{HOST}:{PORT}", flush=True)
    server.serve_forever()
