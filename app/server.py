"""HTTP server: static UI, JSON API, SSE stream, claim page and public report."""

from __future__ import annotations

import html
import json
import mimetypes
import queue
import sys
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import db
from .api import router
from .api.http import Request
from .api.metrics import metrics
from .config import ROOT, settings
from .domain.sim import Simulation
from .seed import seed_all

WEB = ROOT / "web"
DOCS = ROOT / "docs"
MAX_BODY = 1_500_000
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'self'"
    ),
}


class Application:
    def __init__(self) -> None:
        db.migrate()
        if settings.seed_on_boot:
            seed_all()
        self.sim = Simulation(settings)
        self.sim.start()


APP: Application | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "MeridianMediaOS/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle("HEAD")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain", extra={"Allow": "GET, POST, PUT, PATCH, DELETE, OPTIONS"})

    # -- dispatch ----------------------------------------------------------
    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/stream" and method == "GET":
                self._stream()
                return
            if path.startswith("/api/"):
                response = self._api(method, path, parsed.query)
                self._send_response(response.status, response.body, response.content_type)
                return
            if path.startswith("/report/") and method in {"GET", "HEAD"}:
                self._report(path.rsplit("/", 1)[-1])
                return
            if path in {"/", "/index.html"} or path.startswith("/claim/"):
                self._static(WEB / "index.html", method)
                return
            if path == "/openapi.yaml":
                self._static(DOCS / "openapi.yaml", method)
                return
            if path == "/architecture.svg":
                self._static(DOCS / "architecture.svg", method)
                return
            self._static_asset(path, method)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception:
            traceback.print_exc()
            metrics.record_error()
            try:
                self._send_response(
                    500, {"error": "internal_error", "message": "Unexpected server error"}, "application/json; charset=utf-8"
                )
            except OSError:
                pass

    def _api(self, method: str, path: str, query: str):
        metrics_start = time.perf_counter()
        body = self._body()
        if isinstance(body, tuple):
            return body[0]
        request = Request(
            method=method,
            path=path,
            query={key: values[-1] for key, values in parse_qs(query).items()},
            body=body,
            headers={key.lower(): value for key, value in self.headers.items()},
            settings=settings,
            sim=APP.sim,  # type: ignore[union-attr]
        )
        response = router.handle(request)
        metrics.record((time.perf_counter() - metrics_start) * 1000)
        return response

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return (router_error(413, "Request body too large"),)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return (router_error(400, "Request body must be valid JSON"),)
        if not isinstance(payload, dict):
            return (router_error(400, "Request body must be a JSON object"),)
        return payload

    # -- static ------------------------------------------------------------
    def _static_asset(self, path: str, method: str) -> None:
        relative = path.lstrip("/")
        candidate = (WEB / relative).resolve()
        try:
            candidate.relative_to(WEB.resolve())
        except ValueError:
            self._send(404, b"Not found", "text/plain")
            return
        if not candidate.is_file():
            self._send(404, b"Not found", "text/plain")
            return
        self._static(candidate, method)

    def _static(self, path: Path, method: str) -> None:
        if not path.is_file():
            self._send(404, b"Not found", "text/plain")
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        data = path.read_bytes()
        if method == "HEAD":
            self._send(200, b"", content_type, extra={"Content-Length": str(len(data))})
            return
        self._send(200, data, content_type)

    def _report(self, token: str) -> None:
        row = db.query_one("SELECT * FROM reports WHERE token = ?", (token,))
        if not row:
            self._send(404, b"Report not found", "text/plain; charset=utf-8")
            return
        payload = db.json_loads(row["payload_json"], {})
        self._send(200, _report_html(payload).encode("utf-8"), "text/html; charset=utf-8")

    # -- SSE ---------------------------------------------------------------
    def _stream(self) -> None:
        sim = APP.sim  # type: ignore[union-attr]
        token, channel = sim.bus.subscribe()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()
        self.close_connection = False
        try:
            self.wfile.write(b"retry: 3000\n\n")
            self._sse("sim", sim.state())
            self._sse("kpi", sim.kpi())
            while True:
                try:
                    message = channel.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self._sse(message["event"], message["data"])
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            sim.bus.unsubscribe(token)
            self.close_connection = True

    def _sse(self, event: str, data: dict) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()

    # -- responses ---------------------------------------------------------
    def _send_response(self, status: int, body, content_type: str) -> None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self._send(status, data, content_type)

    def _send(self, status: int, data: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        if settings.log_level.upper() == "DEBUG":
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def router_error(status: int, message: str):
    from .api.http import error

    return error(message, status=status)


def _report_html(payload: dict) -> str:
    advertiser = payload.get("advertiser", {})
    campaigns = payload.get("campaigns", [])
    daily = payload.get("daily", [])
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('name', '')))}</td>"
        f"<td>{html.escape(str(item.get('status', '')))}</td>"
        f"<td>{int(item.get('impressions', 0)):,}</td>"
        f"<td>{int(item.get('scans', 0)):,}</td>"
        f"<td>{int(item.get('redemptions', 0)):,}</td>"
        f"<td>{float(item.get('spend', 0)):,.2f}</td>"
        f"<td>{float(item.get('revenue', 0)):,.2f}</td></tr>"
        for item in campaigns
    )
    daily_rows = "".join(
        f"<tr><td>{html.escape(str(item.get('day', '')))}</td>"
        f"<td>{int(item.get('impressions', 0)):,}</td>"
        f"<td>{int(item.get('redemptions', 0)):,}</td>"
        f"<td>{float(item.get('revenue', 0)):,.2f}</td></tr>"
        for item in daily[-14:]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(str(advertiser.get('name', 'Advertiser')))} · campaign report</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:#f5f8fc;color:#13202f}}
main{{max-width:960px;margin:0 auto;padding:40px 24px}}
.card{{background:#fff;border:1px solid #dce6f2;border-radius:16px;padding:24px;margin-bottom:20px;box-shadow:0 10px 30px rgba(19,32,47,.06)}}
h1{{font-size:26px;margin:0 0 6px}}h2{{font-size:16px;margin:0 0 14px;letter-spacing:.08em;text-transform:uppercase;color:#4d647e}}
table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:left;padding:9px 8px;border-bottom:1px solid #e7eef7}}th{{color:#5b7189;font-weight:600}}
.badge{{display:inline-block;padding:3px 9px;border-radius:999px;background:#e6fbf6;color:#047857;font-size:11px}}
@media print{{body{{background:#fff}}.card{{box-shadow:none}}}}
</style></head><body><main>
<div class="card"><div class="badge">MQI · Media OS</div><h1>{html.escape(str(advertiser.get('name', '')))}</h1>
<p>Advertiser report generated {html.escape(str(payload.get('generatedAt', '')))} · currency {html.escape(str(payload.get('currency', 'EUR')))}</p></div>
<div class="card"><h2>Campaigns</h2><table><thead><tr><th>Campaign</th><th>Status</th><th>Impressions</th><th>Scans</th><th>Redemptions</th><th>Spend</th><th>Revenue</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="card"><h2>Last 14 days</h2><table><thead><tr><th>Day</th><th>Impressions</th><th>Redemptions</th><th>Revenue</th></tr></thead><tbody>{daily_rows}</tbody></table></div>
<p style="color:#6b7f95;font-size:12px">Generated by {html.escape(str(payload.get('brand', 'Meridian Media OS')))}. All airport, airline and brand names are fictional.</p>
</main></body></html>"""


def main() -> None:
    global APP
    APP = Application()
    server = ThreadingHTTPServer((settings.host, settings.port), Handler)
    server.daemon_threads = True
    print(f"{settings.product_name} listening on http://localhost:{settings.port}")
    print(f"LAN claim pages: http://{settings.lan_ip}:{settings.port}/claim/<code>")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        APP.sim.stop()
        server.server_close()


if __name__ == "__main__":
    main()