"""Ridgeline's backend: a JSON API under /api/ and the frontend's static files at /.

Run from the project root:  python backend/server.py            (http://127.0.0.1:8000)
                            python backend/server.py --port 8123
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from trails import list_trails

FRONTEND = (Path(__file__).resolve().parent.parent / "frontend").resolve()
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self.send_json(200, {"ok": True})
        elif path == "/api/trails":
            self.send_json(200, {"trails": list_trails()})
        elif path.startswith("/api/"):
            self.send_error_json(404, "not_found", f"No API route at {path}.")
        else:
            self.send_static(path)

    def send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, code: str, message: str) -> None:
        """The error envelope: callers branch on `code`; `message` is prose for people."""
        self.send_json(status, {"error": {"code": code, "message": message}})

    def send_static(self, path: str) -> None:
        name = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (FRONTEND / name).resolve()
        inside = FRONTEND in target.parents
        if not inside or not target.is_file() or target.suffix not in CONTENT_TYPES:
            self.send_error_json(404, "not_found", f"No file at {path}.")
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES[target.suffix])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - the base class names it so
        sys.stderr.write(f"{self.address_string()} {format % args}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ridgeline backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Ridgeline on http://{args.host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
