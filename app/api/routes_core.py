"""Health, configuration, simulation control and public decision audit."""

from __future__ import annotations

from datetime import timedelta

from .. import db
from ..adapters.registry import feed_health
from ..domain import decisions
from ..domain.promos import claim, get_by_code, record_scan, share
from ..models import iso
from . import serializers
from ..qr import encode_svg
from .http import Request, Response, Route, body_str, dispatch, json_response, q_str, text_response

ROLES = [
    {"id": "admin", "label": "Platform Admin", "theme": "dark"},
    {"id": "retailer", "label": "Retailer", "theme": "light"},
    {"id": "media", "label": "Media Manager", "theme": "light"},
    {"id": "airline", "label": "Airline Representative", "theme": "light"},
    {"id": "passenger", "label": "Passenger Screen", "theme": "dark"},
]


def _config(req: Request) -> Response:
    counts = {
        "flights": db.table_count("flights"),
        "screens": db.table_count("screens"),
        "outlets": db.table_count("outlets"),
        "advertisers": db.table_count("advertisers"),
        "campaigns": db.table_count("campaigns"),
        "creatives": db.table_count("creatives"),
        "decisions": db.table_count("decisions"),
    }
    return json_response(
        {
            "theme": req.settings.theme,
            "sim": req.sim.state(),
            "roles": ROLES,
            "sources": {
                "flight": req.settings.flight_source,
                "aidx": req.settings.aidx_source,
                "acris": req.settings.acris_source,
                "ai": req.settings.ai_provider,
            },
            "counts": counts,
            "claimBase": _claim_base(req),
            "languages": ["en", req.settings.second_language],
            "docs": {"openapi": "/openapi.yaml", "readme": "/api/meta/readme"},
        }
    )


def _health(req: Request) -> Response:
    try:
        seeded = db.get_meta("seed_version")
        return json_response(
            {
                "status": "ok",
                "version": req.settings.version,
                "seed": seeded,
                "sim": req.sim.state(),
                "counts": {
                    "flights": db.table_count("flights"),
                    "screens": db.table_count("screens"),
                    "decisions": db.table_count("decisions"),
                },
                "feeds": [
                    {key: value for key, value in feed.items() if key != "contract"}
                    for feed in feed_health(req.settings)
                ],
            }
        )
    except Exception as exc:
        return json_response({"status": "degraded", "error": str(exc)}, status=503)


def _meta(req: Request) -> Response:
    return json_response(
        {
            "seedVersion": db.get_meta("seed_version"),
            "seededAt": db.get_meta("seeded_at"),
            "simStart": db.get_meta("sim_start"),
            "counts": {
                table: db.table_count(table)
                for table in (
                    "flights", "screens", "outlets", "airlines", "campaigns",
                    "creatives", "promos", "impressions", "redemptions", "decisions",
                    "incidents", "daily_stats", "segment_stats",
                )
            },
            "sources": feed_health(req.settings),
            "aiProvider": req.settings.ai_provider,
            "evidence": {
                "decisionLog": "GET /api/admin/decisions",
                "audit": "GET /api/decisions/{id}",
                "dailyStatsDays": 30,
                "segmentModel": db.get_meta("segment_model") or "seg-2026.10-v3",
            },
        }
    )


def _sim_state(req: Request) -> Response:
    return json_response(req.sim.state())


def _sim_control(req: Request) -> Response:
    action = body_str(req.body, "action", "pause", 30)
    value = req.body.get("value")
    try:
        result = req.sim.control(action, value)
    except ValueError as exc:
        return json_response({"error": "invalid_event", "message": str(exc)}, status=400)
    return json_response({"ok": True, "state": result, "action": action})


def _decision_audit(req: Request) -> Response:
    row = decisions.why(int(req.params["id"]))
    if not row:
        return json_response({"error": "not_found", "message": "Decision not found"}, status=404)
    return json_response(row)


def _claim_page(req: Request) -> Response:
    promo = get_by_code(req.params["code"], req.now)
    if not promo:
        return json_response({"error": "not_found", "message": "Promo code not found"}, status=404)
    flight = db.query_one("SELECT * FROM flights WHERE flight_id = ?", (promo.get("flight_id"),))
    flight_payload = None
    if flight:
        flight_payload = {
            "display": f"{flight['airline']}{flight['flight_no']}",
            "destination": flight["destination"],
            "gate": flight["gate"],
            "estimated": flight["etd"] or flight["eta"],
        }
    state = req.sim.state()
    return json_response(
        {
            "promo": promo,
            "flight": flight_payload,
            "claimBase": _claim_base(req),
            "now": state["time"],
            "speed": state["speed"],
            "running": state["running"],
        }
    )


def _claim_post(req: Request) -> Response:
    try:
        result = claim(req.params["code"], req.now, channel=body_str(req.body, "channel", "mobile", 20))
    except ValueError as exc:
        return json_response({"error": "promo_error", "message": str(exc)}, status=409)
    req.sim.bus.publish("redemption", result)
    return json_response(result)


def _claim_scan(req: Request) -> Response:
    try:
        promo = record_scan(req.params["code"], req.now)
    except ValueError as exc:
        return json_response({"error": "promo_error", "message": str(exc)}, status=404)
    req.sim.bus.publish("scan", {"code": req.params["code"], "campaignId": promo.get("campaign_id")})
    return json_response({"ok": True, "promo": promo})


def _claim_share(req: Request) -> Response:
    try:
        promo = share(req.params["code"], req.now)
    except ValueError as exc:
        return json_response({"error": "promo_error", "message": str(exc)}, status=409)
    return json_response({"ok": True, "promo": promo, "claimBase": _claim_base(req)})


def _claim_base(req: Request) -> str:
    if req.settings.public_base_url:
        return req.settings.public_base_url.rstrip("/")
    host = req.headers.get("host", f"localhost:{req.settings.port}")
    proto = req.headers.get("x-forwarded-proto", "http")
    if host.startswith("localhost") or host.startswith("127.0.0.1"):
        host = f"{req.settings.lan_ip}:{req.settings.port}"
    return f"{proto}://{host}"


def _qrcode(req: Request) -> Response:
    code = q_str(req, "code")
    if not code:
        return json_response({"error": "bad_request", "message": "code is required"}, status=400)
    return json_response({"code": code, "url": f"{_claim_base(req)}/claim/{code}"})


def _qr_svg(req: Request) -> Response:
    data = q_str(req, "data") or q_str(req, "url")
    if not data or len(data) > 200:
        return text_response("QR payload missing or too long", status=400)
    return text_response(encode_svg(data), content_type="image/svg+xml; charset=utf-8")


def _flights(req: Request) -> Response:
    query = q_str(req, "q").upper()
    rows = db.query(
        "SELECT * FROM flights WHERE direction='D' AND std BETWEEN ? AND ? ORDER BY std LIMIT 200",
        (iso(req.now - timedelta(hours=1)), iso(req.now + timedelta(hours=16))),
    )
    items = []
    for row in rows:
        item = serializers.flight(row)
        if query and query not in f"{item['display']} {item['destination']} {item['gate']}".upper():
            continue
        items.append(item)
    return json_response({"items": items[:100], "now": iso(req.now)})


def _readme(req: Request) -> Response:
    path = req.settings.db_path.parent.parent / "README.md"
    if not path.exists():
        return text_response("README not found", status=404)
    return text_response(path.read_text(encoding="utf-8"), content_type="text/markdown; charset=utf-8")


ROUTES: list[Route] = [
    ("GET", "/api/config", _config),
    ("GET", "/api/health", _health),
    ("GET", "/healthz", _health),
    ("GET", "/api/meta", _meta),
    ("GET", "/api/sim", _sim_state),
    ("POST", "/api/sim/control", _sim_control),
    ("GET", "/api/decisions/{id}", _decision_audit),
    ("GET", "/api/claim/{code}", _claim_page),
    ("POST", "/api/claim/{code}", _claim_post),
    ("POST", "/api/claim/{code}/scan", _claim_scan),
    ("POST", "/api/claim/{code}/share", _claim_share),
    ("GET", "/api/qr", _qrcode),
    ("GET", "/api/qr.svg", _qr_svg),
    ("GET", "/api/meta/readme", _readme),
    ("GET", "/api/flights", _flights),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)