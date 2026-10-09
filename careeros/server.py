"""Local dashboard server: serves dashboard/index.html and a tiny JSON API over the SQLite store.

Binds to 127.0.0.1 only. The API mirrors the hosted dashboard's document model:
  GET    /api/health
  GET    /api/c/<collection>            -> {"docs": [{"id", "data", "version"}]}
  GET    /api/d/<collection>/<id>
  PUT    /api/d/<collection>/<id>       body: full document
  PATCH  /api/d/<collection>/<id>       body: partial document (deep merge; {"__delete__": true} removes a key)
  DELETE /api/d/<collection>/<id>
"""

from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .store import Store

COLLECTIONS = {"jobs", "runs", "settings", "brain"}
_DOC = re.compile(r"^/api/d/([a-z]+)/([A-Za-z0-9_.:@+~-]{1,200})$")
_COL = re.compile(r"^/api/c/([a-z]+)$")


def make_handler(store: Store, root: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"careeros/{__version__}"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def _json(self, code: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Body must be a JSON object")
            return data

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/health":
                return self._json(200, {"ok": True, "version": __version__})
            m = _COL.match(path)
            if m and m.group(1) in COLLECTIONS:
                return self._json(200, {"docs": store.list(m.group(1))})
            m = _DOC.match(path)
            if m and m.group(1) in COLLECTIONS:
                doc = store.get(m.group(1), m.group(2))
                return self._json(200, doc) if doc else self._json(404, {"error": "not found"})
            # static files
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (root / rel).resolve()
            if root.resolve() not in target.parents and target != root.resolve() / "index.html" or not target.is_file():
                return self._json(404, {"error": "not found"})
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _write(self, method: str):
            m = _DOC.match(self.path.split("?")[0])
            if not m or m.group(1) not in COLLECTIONS:
                return self._json(404, {"error": "unknown document"})
            col, doc_id = m.groups()
            try:
                if method == "DELETE":
                    store.delete(col, doc_id)
                    return self._json(200, {"ok": True})
                body = self._body()
                if method == "PUT":
                    return self._json(200, {"version": store.set(col, doc_id, body)})
                return self._json(200, {"version": store.update(col, doc_id, body)})
            except KeyError:
                return self._json(404, {"error": "not found"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})

        def do_PUT(self):
            self._write("PUT")

        def do_PATCH(self):
            self._write("PATCH")

        def do_DELETE(self):
            self._write("DELETE")

    return Handler


def serve(store: Store, root: Path, port: int = 8765) -> None:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store, root))
    print(f"CareerOS dashboard: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
