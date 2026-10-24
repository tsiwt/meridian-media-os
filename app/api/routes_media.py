"""Media Manager: inventory, yield, approvals, advertiser overview, packages, reports."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from .. import db
from ..domain import decisions
from ..domain.profile import zone_presence
from ..models import iso, parse_time
from . import serializers
from .http import Request, Response, Route, body_str, dispatch, json_response, q_str

PRICE_BASE = 38.0


def _inventory(req: Request) -> Response:
    date_value = q_str(req, "date") or req.now.date().isoformat()
    screen_id = q_str(req, "screenId")
    screens = [
        serializers.screen(row)
        for row in db.query(
            "SELECT s.*, z.name AS zone_name FROM screens s JOIN zones z ON z.id=s.zone_id ORDER BY s.id"
        )
    ]
    if screen_id:
        selected = next((screen for screen in screens if screen["id"] == screen_id), screens[0])
    else:
        selected = screens[0]
    zones = [serializers.zone(row) for row in db.query("SELECT * FROM zones ORDER BY id")]
    probe_day = parse_time(date_value + "T12:00:00Z") or req.now
    zoned = {}
    for zone in zones:
        points = {}
        for hour in (0, 4, 8, 12, 16, 20, 23):
            points[hour] = zone_presence(zone["id"], probe_day.replace(hour=hour))["crowd"]
        zoned[zone["id"]] = points
    booked = _booked_campaigns(date_value)
    cells = []
    for hour in range(24):
        for zone in zones:
            crowd = _interpolate(zoned[zone["id"]], hour)
            status = "available"
            owner = ""
            for campaign in booked:
                placement = campaign["placement"]
                if "*" in placement.get("zones", []) or zone["id"] in placement.get("zones", []):
                    start_hour = int(campaign["daypart"].get("startHour", 0))
                    end_hour = int(campaign["daypart"].get("endHour", 24))
                    if start_hour <= hour < end_hour:
                        status = "booked"
                        owner = campaign["name"]
                        break
            if status == "available" and crowd >= 240:
                status = "premium"
            cells.append(
                {
                    "zoneId": zone["id"],
                    "hour": hour,
                    "crowd": crowd,
                    "status": status,
                    "bookedBy": owner,
                    "price": round(PRICE_BASE + crowd * 0.11, 2),
                }
            )
    selected_cells = [
        cell for cell in cells if cell["zoneId"] == selected["zone_id"]
    ]
    total = len(cells)
    booked_count = sum(1 for cell in cells if cell["status"] == "booked")
    premium_count = sum(1 for cell in cells if cell["status"] == "premium")
    return json_response(
        {
            "date": date_value,
            "screen": selected,
            "screens": screens,
            "zones": zones,
            "cells": cells,
            "selectedCells": selected_cells,
            "summary": {
                "occupancyPct": round(100.0 * booked_count / max(1, total), 1),
                "premiumCells": premium_count,
                "revenueForecast": round(sum(cell["price"] for cell in cells if cell["status"] != "available") * 0.72, 2),
                "currency": req.settings.currency,
            },
        }
    )


def _interpolate(points: dict[int, int], hour: int) -> int:
    if hour in points:
        return points[hour]
    lower = max(key for key in points if key <= hour)
    upper = min(key for key in points if key >= hour)
    if lower == upper:
        return points[lower]
    ratio = (hour - lower) / (upper - lower)
    return int(points[lower] + (points[upper] - points[lower]) * ratio)


def _booked_campaigns(date_value: str) -> list[dict]:
    rows = db.query("SELECT * FROM campaigns WHERE status='approved'")
    result = []
    for row in rows:
        campaign = dict(row)
        start = parse_time(campaign["start"])
        end = parse_time(campaign["end"])
        target = parse_time(date_value + "T12:00:00Z")
        if start and end and target and not (start <= target <= end):
            continue
        result.append(
            {
                "name": campaign["name"],
                "placement": db.json_loads(campaign["placement_json"], {}),
                "daypart": db.json_loads(campaign["daypart_json"], {}),
            }
        )
    return result


def _yield(req: Request) -> Response:
    rows = db.query(
        "SELECT c.*, a.name AS advertiser_name FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
        "WHERE c.status='approved'"
    )
    zones = [serializers.zone(row) for row in db.query("SELECT * FROM zones ORDER BY id")]
    occupancy = {}
    for campaign in rows:
        placement = db.json_loads(campaign["placement_json"], {})
        for zone in placement.get("zones", []):
            occupancy[zone] = occupancy.get(zone, 0) + 1
    forecast = []
    for zone in zones:
        presence = zone_presence(zone["id"], req.now)
        price = round(PRICE_BASE + presence["crowd"] * 0.11, 2)
        booked = occupancy.get(zone["id"], 0)
        forecast.append(
            {
                "zoneId": zone["id"],
                "zoneName": zone["name"],
                "suggestedPrice": price,
                "occupancyPct": min(100, 22 + booked * 18),
                "crowdNow": presence["crowd"],
                "revenueNext7d": round(price * (18 + booked * 6) * 0.75, 2),
                "premium": presence["crowd"] >= 240,
            }
        )
    forecast.sort(key=lambda row: row["revenueNext7d"], reverse=True)
    history = db.query(
        "SELECT day, SUM(revenue) AS revenue, SUM(spend) AS spend FROM daily_stats "
        "GROUP BY day ORDER BY day DESC LIMIT 30"
    )
    return json_response(
        {
            "zones": forecast,
            "history": [dict(row) for row in reversed(history)],
            "currency": req.settings.currency,
            "model": "Price = base €38 + 0.11 × live ZonePresence passenger count",
        }
    )


def _approvals(req: Request) -> Response:
    if req.method == "GET":
        campaigns = db.query(
            "SELECT c.*, a.name AS advertiser_name, cr.name AS creative_name, cr.status AS creative_status, "
            "a.kind AS advertiser_kind FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
            "JOIN creatives cr ON cr.id=c.creative_id WHERE c.status='pending' ORDER BY c.id"
        )
        creatives = db.query(
            "SELECT cr.*, a.name AS advertiser_name FROM creatives cr JOIN advertisers a ON a.id=cr.advertiser_id "
            "WHERE cr.status='pending' ORDER BY cr.id"
        )
        return json_response(
            {
                "campaigns": [serializers.campaign(row) for row in campaigns],
                "creatives": [serializers.creative(row) for row in creatives],
                "checklist": [
                    "No real airport, airline or brand marks",
                    "Offer and price are truthful and unambiguous",
                    "Creative is legible at 9:16 and 16:9",
                    "Landing claim page is mobile ready",
                    "No alcohol/tobacco targeting minors",
                ],
            }
        )
    item_type = body_str(req.body, "type", "campaign", 20)
    item_id = body_str(req.body, "id", "", 30)
    decision = body_str(req.body, "decision", "", 20)
    checklist = req.body.get("checklist")
    if decision not in {"approve", "reject"}:
        return json_response({"error": "bad_request", "message": "decision must be approve or reject"}, status=400)
    if item_type == "campaign":
        row = db.query_one("SELECT * FROM campaigns WHERE id=?", (item_id,))
        if not row:
            return json_response({"error": "not_found", "message": "Campaign not found"}, status=404)
        if decision == "approve" and not isinstance(checklist, dict):
            return json_response({"error": "bad_request", "message": "Brand-safety checklist is required to approve"}, status=400)
        db.execute(
            "UPDATE campaigns SET status=?, notes=? WHERE id=?",
            ("approved" if decision == "approve" else "rejected", f"Media review {decision}d", item_id),
        )
    elif item_type == "creative":
        if decision == "approve" and not isinstance(checklist, dict):
            return json_response({"error": "bad_request", "message": "Brand-safety checklist is required to approve"}, status=400)
        row = db.query_one("SELECT * FROM creatives WHERE id=?", (item_id,))
        if not row:
            return json_response({"error": "not_found", "message": "Creative not found"}, status=404)
        db.execute("UPDATE creatives SET status=? WHERE id=?", ("approved" if decision == "approve" else "rejected", item_id))
    else:
        return json_response({"error": "bad_request", "message": "Unknown approval type"}, status=400)
    req.sim.bus.publish("approval", {"type": item_type, "id": item_id, "decision": decision})
    return json_response({"ok": True, "type": item_type, "id": item_id, "decision": decision})


def _advertisers(req: Request) -> Response:
    now = req.now
    rows = db.query(
        "SELECT a.id, a.name, a.kind, a.color, COUNT(c.id) AS campaigns, "
        "COALESCE(SUM(c.spend),0) AS spend, COALESCE(SUM(c.revenue),0) AS revenue, "
        "COALESCE(SUM(c.impressions),0) AS impressions, "
        "SUM(CASE WHEN c.status='approved' THEN 1 ELSE 0 END) AS running "
        "FROM advertisers a LEFT JOIN campaigns c ON c.advertiser_id=a.id "
        "WHERE a.kind IN ('retailer','brand','airline') GROUP BY a.id ORDER BY spend DESC"
    )
    today = now.date().isoformat()
    items = []
    for row in rows:
        item = dict(row)
        todays = db.query_one(
            "SELECT COALESCE(SUM(d.impressions),0) AS i, COALESCE(SUM(d.spend),0) AS s FROM daily_stats d "
            "JOIN campaigns c ON c.id=d.campaign_id WHERE c.advertiser_id=? AND d.day=?",
            (item["id"], today),
        )
        item["todayImpressions"] = int(todays["i"])
        item["todaySpend"] = round(float(todays["s"]), 2)
        item["underDelivering"] = item["todayImpressions"] < 4000 and item["running"] > 0
        item["roi"] = round((item["revenue"] - item["spend"]) / item["spend"], 3) if item["spend"] else 0.0
        items.append(item)
    return json_response({"items": items, "currency": req.settings.currency})


def _packages(req: Request) -> Response:
    if req.method == "GET":
        rows = db.query("SELECT * FROM packages ORDER BY id")
        items = []
        for row in rows:
            item = dict(row)
            item["screenIds"] = db.json_loads(item.pop("screen_ids_json"), [])
            items.append(item)
        return json_response({"items": items})
    name = body_str(req.body, "name", "", 120)
    screen_ids = req.body.get("screenIds") or []
    if not name or not isinstance(screen_ids, list):
        return json_response({"error": "bad_request", "message": "name and screenIds are required"}, status=400)
    next_id = db.query_one("SELECT COUNT(*) AS c FROM packages")["c"] + 1
    package_id = f"PKG-{next_id:02d}"
    db.execute(
        "INSERT INTO packages(id, name, screen_ids_json, price, description, created) VALUES (?,?,?,?,?,?)",
        (package_id, name, db.json_dumps([str(item)[:20] for item in screen_ids][:180]),
         float(req.body.get("price") or 5000), body_str(req.body, "description", "", 500), iso(req.now)),
    )
    return json_response({"ok": True, "id": package_id}, status=201)


def _report(req: Request) -> Response:
    advertiser_id = q_str(req, "advertiserId") or "ADV-01"
    payload = _report_payload(advertiser_id, req)
    return json_response(payload)


def _report_share(req: Request) -> Response:
    advertiser_id = body_str(req.body, "advertiserId", "ADV-01", 30)
    payload = _report_payload(advertiser_id, req)
    token = hashlib.sha256(f"{advertiser_id}:{req.now.timestamp()}".encode()).hexdigest()[:16]
    db.execute(
        "INSERT INTO reports(token, advertiser_id, payload_json, created) VALUES (?,?,?,?)",
        (token, advertiser_id, db.json_dumps(payload), iso(req.now)),
    )
    return json_response({"ok": True, "token": token, "url": f"/report/{token}"}, status=201)


def _report_payload(advertiser_id: str, req: Request) -> dict:
    advertiser = db.query_one("SELECT * FROM advertisers WHERE id=?", (advertiser_id,))
    if not advertiser:
        return {"error": "not_found"}
    campaigns = db.query("SELECT * FROM campaigns WHERE advertiser_id=? ORDER BY id", (advertiser_id,))
    daily = db.query(
        "SELECT d.day, SUM(d.impressions) AS impressions, SUM(d.scans) AS scans, "
        "SUM(d.redemptions) AS redemptions, SUM(d.revenue) AS revenue, SUM(d.spend) AS spend "
        "FROM daily_stats d JOIN campaigns c ON c.id=d.campaign_id WHERE c.advertiser_id=? "
        "GROUP BY d.day ORDER BY d.day",
        (advertiser_id,),
    )
    return {
        "advertiser": dict(advertiser),
        "generatedAt": iso(req.now),
        "campaigns": [
            {
                "id": row["id"], "name": row["name"], "status": row["status"],
                "impressions": row["impressions"], "scans": row["scans"],
                "redemptions": row["redemptions"], "revenue": round(float(row["revenue"]), 2),
                "spend": round(float(row["spend"]), 2),
            }
            for row in campaigns
        ],
        "daily": [dict(row) for row in daily],
        "currency": req.settings.currency,
        "brand": req.settings.product_name,
    }


def _report_public(req: Request) -> Response:
    row = db.query_one("SELECT * FROM reports WHERE token=?", (req.params["token"],))
    if not row:
        return json_response({"error": "not_found", "message": "Report not found"}, status=404)
    return json_response(serializers.report_row(row))


def _conflict(req: Request) -> Response:
    screen_id = q_str(req, "screenId") or "SCR-122"
    row = db.query_one(
        "SELECT * FROM decisions WHERE screen_id=? ORDER BY id DESC LIMIT 1", (screen_id,)
    )
    if not row:
        return json_response({"screenId": screen_id, "candidates": [], "reason": "No decision yet"})
    decision = decisions.decision_row(row)
    top = [candidate for candidate in decision["candidates"] if candidate.get("passed")][:3]
    return json_response(
        {
            "screenId": screen_id,
            "decidedAt": decision["decidedAt"],
            "winnerId": decision["winnerId"],
            "reason": decision["reason"],
            "candidates": top,
            "allCandidates": decision["candidates"],
            "profile": decision["profile"],
            "validation": decision["validation"],
            "explanation": _conflict_text(top),
        }
    )


def _conflict_text(top: list[dict]) -> str:
    if len(top) < 2:
        return "Only one campaign passed every hard rule for this slot."
    first, second = top[0], top[1]
    return (
        f"{first['name']} beat {second['name']} by {round(first['finalScore'] - second['finalScore'], 3)} "
        f"because its weighted audience match was {round(first['audienceMatch'] * 100)}% vs "
        f"{round(second['audienceMatch'] * 100)}%, with a {first['boost']:.2f}× business-rule boost."
    )


ROUTES: list[Route] = [
    ("GET", "/api/media/inventory", _inventory),
    ("GET", "/api/media/yield", _yield),
    ("GET", "/api/media/approvals", _approvals),
    ("POST", "/api/media/approvals", _approvals),
    ("GET", "/api/media/advertisers", _advertisers),
    ("GET", "/api/media/packages", _packages),
    ("POST", "/api/media/packages", _packages),
    ("GET", "/api/media/report", _report),
    ("POST", "/api/media/report/share", _report_share),
    ("GET", "/api/media/report/{token}", _report_public),
    ("GET", "/api/media/conflict", _conflict),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)