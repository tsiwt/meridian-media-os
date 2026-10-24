"""Passenger screen simulator and 'Why this ad?' explanation."""

from __future__ import annotations

from datetime import timedelta

from .. import db
from ..domain import decisions
from ..domain.promos import create as create_promo
from ..domain.promos import promo_for_campaign
from ..models import iso
from . import serializers
from .http import Request, Response, Route, dispatch, json_response


def _screens(req: Request) -> Response:
    rows = db.query(
        "SELECT s.*, z.name AS zone_name FROM screens s JOIN zones z ON z.id=s.zone_id ORDER BY s.id"
    )
    items = []
    for row in rows:
        screen = serializers.screen(row)
        items.append(
            {
                "id": screen["id"],
                "name": screen["name"],
                "zoneId": screen["zone_id"],
"zoneName": screen["zoneName"],
                "status": screen["status"],
                "aspect": screen["aspect"],
                "nearestGates": screen["nearestGates"],
            }
        )
    return json_response({"items": items, "default": "SCR-122"})


def _screen(req: Request) -> Response:
    screen_id = req.params["id"]
    screen = db.query_one(
        "SELECT s.*, z.name AS zone_name, z.gates_json FROM screens s JOIN zones z ON z.id=s.zone_id WHERE s.id=?",
        (screen_id,),
    )
    if not screen:
        return json_response({"error": "not_found", "message": "Screen not found"}, status=404)
    decision = _ensure_decision(screen_id, req)
    if not decision:
        return json_response({"error": "no_decision", "message": "No decision available"}, status=503)
    payload = _payload(screen, decision, req)
    return json_response(payload)


def _force_decision(req: Request) -> Response:
    screen_id = req.params["id"]
    screen = db.query_one("SELECT * FROM screens WHERE id=?", (screen_id,))
    if not screen:
        return json_response({"error": "not_found", "message": "Screen not found"}, status=404)
    decision = decisions.decide(screen_id, req.now, req.settings, persist=True)
    if not decision:
        return json_response({"error": "no_decision"}, status=503)
    return json_response(_payload(screen, decision.to_dict(req.now), req))


def _ensure_decision(screen_id: str, req: Request) -> dict | None:
    latest = decisions.latest_decision(screen_id)
    if latest:
        return latest
    decision = decisions.decide(screen_id, req.now, req.settings, persist=True)
    return decision.to_dict(req.now) if decision else None


def _payload(screen, decision: dict, req: Request) -> dict:
    now = req.now
    winner_id = decision.get("winnerId") or ""
    winner_campaign = db.query_one(
        "SELECT c.*, a.name AS advertiser_name FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id WHERE c.id=?",
        (winner_id,),
    )
    creative = None
    promo = None
    claim_url = ""
    if winner_campaign:
        creative_row = db.query_one("SELECT * FROM creatives WHERE id=?", (winner_campaign["creative_id"],))
        creative = serializers.creative(creative_row) if creative_row else None
        promo = promo_for_campaign(winner_id, now)
        if not promo:
            flight = _nearest_flight(screen, now)
            if flight:
                try:
                    promo = create_promo(winner_id, flight["flight_id"], now, label="On-screen offer", value="10%", minutes=45)
                except ValueError:
                    promo = None
        if promo:
            claim_url = f"{_claim_base(req)}/claim/{promo['code']}"
    playlist = []
    for candidate in (decision.get("candidates") or [])[:6]:
        if not candidate.get("passed"):
            continue
        candidate_creative = db.query_one("SELECT * FROM creatives WHERE id=?", (candidate["creativeId"],))
        if not candidate_creative:
            continue
        playlist.append(
            {
                "campaignId": candidate["campaignId"],
                "name": candidate["name"],
                "score": candidate["finalScore"],
                "audienceMatch": candidate["audienceMatch"],
                "creative": serializers.creative(candidate_creative),
                "reason": candidate["reasons"][0] if candidate["reasons"] else "",
            }
        )
    flights = _nearby_flights(screen, now)
    return {
        "screen": {
            "id": screen["id"],
            "name": screen["name"],
            "zoneId": screen["zone_id"],
            "status": screen["status"],
            "aspect": screen["aspect"],
            "zoneName": screen["zone_name"],
        },
        "decision": decision,
        "campaign": serializers.campaign(winner_campaign) if winner_campaign else None,
        "creative": creative,
        "promo": promo,
        "claimUrl": claim_url,
        "playlist": playlist,
        "flights": flights,
        "now": iso(now),
        "claimBase": _claim_base(req),
    }


def _nearby_flights(screen, now) -> list[dict]:
    gates = db.json_loads(screen["nearest_gates_json"], []) if "nearest_gates_json" in screen.keys() else []
    if not gates:
        zone = db.query_one("SELECT gates_json FROM zones WHERE id=?", (screen["zone_id"],))
        gates = db.json_loads(zone["gates_json"], []) if zone else []
    if not gates:
        return []
    placeholders = ",".join("?" for _ in gates)
    rows = db.query(
        f"SELECT * FROM flights WHERE direction='D' AND gate IN ({placeholders}) "
        f"AND std BETWEEN ? AND ? ORDER BY std LIMIT 8",
        (*gates, iso(now - timedelta(minutes=45)), iso(now + timedelta(hours=4))),
    )
    return [serializers.flight(row) for row in rows]


def _nearest_flight(screen, now) -> dict | None:
    flights = _nearby_flights(screen, now)
    return flights[0] if flights else None


def _why(req: Request) -> Response:
    row = decisions.why(int(req.params["id"]))
    if not row:
        return json_response({"error": "not_found", "message": "Decision not found"}, status=404)
    winner = db.query_one(
        "SELECT c.*, a.name AS advertiser_name FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id WHERE c.id=?",
        (row.get("winnerId"),),
    )
    creative = None
    if winner:
        creative_row = db.query_one("SELECT * FROM creatives WHERE id=?", (winner["creative_id"],))
        creative = serializers.creative(creative_row) if creative_row else None
    return json_response({"decision": row, "campaign": serializers.campaign(winner) if winner else None, "creative": creative})


def _airport(req: Request) -> Response:
    return json_response(
        {
            "airport": req.settings.airport_name,
            "code": req.settings.airport_code,
            "claimBase": _claim_base(req),
            "now": iso(req.now),
        }
    )


def _claim_base(req: Request) -> str:
    if req.settings.public_base_url:
        return req.settings.public_base_url.rstrip("/")
    host = req.headers.get("host", f"localhost:{req.settings.port}")
    proto = req.headers.get("x-forwarded-proto", "http")
    if host.startswith("localhost") or host.startswith("127.0.0.1"):
        host = f"{req.settings.lan_ip}:{req.settings.port}"
    return f"{proto}://{host}"


ROUTES: list[Route] = [
    ("GET", "/api/passenger/screens", _screens),
    ("GET", "/api/passenger/screens/{id}", _screen),
    ("POST", "/api/passenger/screens/{id}/decide", _force_decision),
    ("GET", "/api/passenger/why/{id}", _why),
    ("GET", "/api/passenger/airport", _airport),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)