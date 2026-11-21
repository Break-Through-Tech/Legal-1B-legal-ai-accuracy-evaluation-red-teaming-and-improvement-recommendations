"""Local web frontend for the hallucination detector.

Serves a single-page UI (app/static/) and one JSON endpoint:

    POST /api/check   body = raw .docx bytes, header X-Filename: <name>
                      or JSON {"text": "...", "filename": "pasted.docx"} with
                      Content-Type: application/json (pasted text is wrapped in
                      an in-memory .docx, one paragraph per line, so it runs
                      through exactly the same pipeline as an upload)

Usage:
    .venv/bin/python app/server.py [--port 8000] [--host 127.0.0.1]

Uses only the standard library plus python-docx (already a dependency).
Uploads are processed in memory and never written to disk.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import docx  # noqa: E402

from src.detect import Detector  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000

log = logging.getLogger("detector-app")
DETECTOR: Detector | None = None


def text_to_docx(text: str) -> bytes:
    """Wrap pasted text in a .docx, one paragraph per line."""
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        log.info("%s %s", self.address_string(), fmt % args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(HTTPStatus.OK, {"ok": True, "setup_ms": DETECTOR.setup_ms})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/check":
            return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "Empty request body."})
        if length > MAX_UPLOAD_BYTES:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                              {"error": f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."})
        body = self.rfile.read(length)

        if self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                payload = json.loads(body)
                text = str(payload.get("text", ""))
            except (ValueError, AttributeError):
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON."})
            if not text.strip():
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "No text provided."})
            if len(text) > MAX_TEXT_CHARS:
                return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Text is too long."})
            filename = str(payload.get("filename") or "pasted-text.docx")
            data = text_to_docx(text)
        else:
            filename = unquote(self.headers.get("X-Filename", "upload.docx"))
            data = body

        report = DETECTOR.check(data, filename=filename)
        return self._json(HTTPStatus.OK, report)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    global DETECTOR
    DETECTOR = Detector()
    log.info("Detector ready (%s)", DETECTOR.setup_ms)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("Serving on http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
