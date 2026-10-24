"""Airline Representative: flights, gate messaging, goodwill, marketplace."""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import db
from ..domain import goodwill
from ..domain.presence import aggregate
from ..domain.promos import create as create_promo
from ..models import iso
from . import serializers
from .http import Request, Response, Route, body_int, body_str, dispatch, json_response, q_str

DEFAULT_AIRLINE = "ZO"
CREATIVE_BY_AIRLINE = {"XH": "CRE-19", "ZO": "CRE-20", "YU": "CRE-21", "XD": "CRE-22"}
CAMPAIGN_BY_AIRLINE = {"XH": "CMP-19", "ZO": "CMP-20", "YU": "CMP-21", "XD": "CMP-22"}
PROMO_CAMPAIGN = {"MKT-01": "CMP-01", "MKT-02": "CMP-04", "MKT-03": "CMP-02", "MKT-04": "CMP-03"}


def _code(req: Request) -> str:
    return (q_str(req, "airline") or body_str(req.body, "airline", DEFAULT_AIRLINE, 2)).upper()


def _companies(_: Request) -> Response:
    rows = db.query("SELECT * FROM airlines ORDER BY iata")
    items = []
    for row in rows:
        count = db.query_one(
            "SELECT COUNT(*) AS c FROM campaigns WHERE advertiser_id = ?", (f"ADV-AIR-{row['iata']}",)
        )["c"]
        items.append({**serializers.airline(row), "campaigns": count})
    return json_response({"items": items, "default": DEFAULT_AIRLINE})


def _flights(req: Request) -> Response:
    code = _code(req)
    now = req.now
    rows = db.query(
        "SELECT * FROM flights WHERE airline=? AND direction='D' AND std BETWEEN ? AND ? ORDER BY std",
        (code, iso(now - timedelta(hours=4)), iso(now + timedelta(hours=14))),
    )
    return json_response(
        {
            "airline": code,
            "items": [serializers.flight(row) for row in rows],
            "now": iso(now),
        }
    )


def _summary(req: Request) -> Response:
    code = _code(req)
    airline = db.query_one("SELECT * FROM airlines WHERE iata=?", (code,))
    if not airline:
        return json_response({"error": "not_found", "message": "Airline not found"}, status=404)
    now = req.now
    flights = [
        serializers.flight(row)
        for row in db.query(
            "SELECT * FROM flights WHERE airline=? AND direction='D' AND std BETWEEN ? AND ? ORDER BY std",
            (code, iso(now - timedelta(hours=2)), iso(now + timedelta(hours=12))),
        )
    ]
    delayed = [flight for flight in flights if flight["delayMinutes"] >= 30]
    reach = sum(int(flight["pax"] * (1 + min(0.6, flight["delayMinutes"] / 120))) for flight in flights)
    today = now.date().isoformat()
    campaign_ids = [
        row["id"]
        for row in db.query(
            "SELECT id FROM campaigns WHERE advertiser_id=? OR filters_json LIKE ?",
            (f"ADV-AIR-{code}", f'%"airline":"{code}"%'),
        )
    ]
    placeholders = ",".join("?" for _ in campaign_ids) or "''"
    stats = db.query_one(
        f"SELECT COALESCE(SUM(impressions),0) AS impressions, COALESCE(SUM(redemptions),0) AS redemptions, "
        f"COALESCE(SUM(revenue),0) AS revenue FROM daily_stats WHERE day=? AND campaign_id IN ({placeholders})",
        (today, *campaign_ids),
    ) if campaign_ids else {"impressions": 0, "redemptions": 0, "revenue": 0}
    campaigns = db.query(
        "SELECT c.*, a.name AS advertiser_name, cr.name AS creative_name, cr.status AS creative_status, "
        "a.kind AS advertiser_kind FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
        "JOIN creatives cr ON cr.id=c.creative_id WHERE c.id IN (" + (placeholders) + ") ORDER BY c.id",
        tuple(campaign_ids),
    ) if campaign_ids else []
    raw_flights = []
    for row in db.query(
        "SELECT * FROM flights WHERE airline=? AND direction='D' AND std BETWEEN ? AND ?",
        (code, iso(now - timedelta(hours=2)), iso(now + timedelta(hours=12))),
    ):
        item = dict(row)
        item["_profile"] = db.json_loads(row["profile_json"], {})
        raw_flights.append(item)
    crowd = aggregate(raw_flights, now)
    return json_response(
        {
            "airline": serializers.airline(airline),
            "kpi": {
                "flightsToday": len(flights),
                "delayed30": len(delayed),
                "passengersReached": int(reach),
                "avgLoadFactor": round(sum(item["loadFactor"] for item in flights) / max(1, len(flights)), 3),
                "impressionsToday": int(stats["impressions"]),
                "redemptionsToday": int(stats["redemptions"]),
                "revenueToday": round(float(stats["revenue"]), 2),
            },
            "flights": flights[:12],
            "campaigns": [serializers.campaign(row) for row in campaigns],
            "crowdProfile": {
                "crowd": crowd["crowd"],
                "shares": crowd["shares"],
                "topDestinations": crowd["destinations"],
                "nationalities": crowd["nationalities"],
                "languages": crowd["languages"],
                "medianDwellMinutes": crowd["medianDwell"],
                "flights": len(crowd["flights"]),
            },
            "goodwill": {
                "settings": goodwill.settings_for(code),
                "recent": goodwill.recent(code),
            },
            "now": iso(now),
        }
    )


def _messages(req: Request) -> Response:
    code = _code(req)
    if req.method == "GET":
        rows = db.query(
            "SELECT c.*, a.name AS advertiser_name, cr.name AS creative_name, cr.status AS creative_status, "
            "a.kind AS advertiser_kind FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
            "JOIN creatives cr ON cr.id=c.creative_id WHERE a.id=? ORDER BY c.id DESC",
            (f"ADV-AIR-{code}",),
        )
        return json_response({"items": [serializers.campaign(row) for row in rows]})
    name = body_str(req.body, "name", "", 160)
    if not name:
        return json_response({"error": "bad_request", "message": "name is required"}, status=400)
    advertiser_id = f"ADV-AIR-{code}"
    advertiser = db.query_one("SELECT * FROM advertisers WHERE id=?", (advertiser_id,))
    if not advertiser:
        db.execute(
            "INSERT INTO advertisers(id, name, kind, color, contact, created) VALUES (?,?,?,?,?,?)",
            (advertiser_id, db.query_one("SELECT name FROM airlines WHERE iata=?", (code,))["name"],
             "airline", "#38e8c8", "brand@airline.example", iso(req.now)),
        )
    creative_id = body_str(req.body, "creativeId", CREATIVE_BY_AIRLINE.get(code, ""), 30)
    creative = db.query_one("SELECT * FROM creatives WHERE id=?", (creative_id,))
    if not creative:
        next_id = db.query_one("SELECT COUNT(*) AS c FROM creatives")["c"] + 1
        creative_id = f"CRE-{next_id:02d}"
        db.execute(
            "INSERT INTO creatives(id, advertiser_id, name, headline_en, headline_zh, body_en, body_zh, "
            "cta_en, cta_zh, template, colors_json, image, category, status, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (creative_id, advertiser_id, f"{name} creative", name, name, "", "", "Learn more", "了解更多",
             "aurora", db.json_dumps(["#38e8c8", "#8b7bff"]), "", "airline", "approved", iso(req.now)),
        )
    now = req.now
    gates = [str(gate)[:5] for gate in (req.body.get("gates") or _own_gates(code, now))][:12]
    next_id = db.query_one("SELECT COUNT(*) AS c FROM campaigns")["c"] + 1
    campaign_id = f"CMP-{next_id:02d}"
    start = now
    end = now + timedelta(hours=body_int(req.body, "hours", 3, 1, 72))
    db.execute(
        "INSERT INTO campaigns(id, advertiser_id, creative_id, name, status, start, end, daypart_json, "
        "budget, daily_cap, freq_cap_min, bid, segments_json, filters_json, placement_json, triggers_json, "
        "spend, impressions, scans, redemptions, revenue, conversion, created, notes, priority, ab_group, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,0,0,?,?,?,?,?)",
        (
            campaign_id, advertiser_id, creative_id, name, "approved", iso(start), iso(end),
            db.json_dumps({"preset": "all_day", "startHour": 0, "endHour": 24}),
            body_int(req.body, "budget", 3000, 0, 1_000_000),
            body_int(req.body, "dailyCap", 400, 0, 100_000),
            body_int(req.body, "freqCapMin", 15, 1, 1440),
            body_int(req.body, "bid", 3, 0, 100),
            db.json_dumps({"business": 0.7, "holiday": 0.6, "international": 0.7}),
            db.json_dumps({"airline": code}),
            db.json_dumps({"zones": [], "gates": gates, "screens": []}),
            db.json_dumps({"boarding": True}),
            iso(now), "Airline gate-area message", 2, "A", "airline",
        ),
    )
    return json_response({"ok": True, "campaignId": campaign_id, "gates": gates}, status=201)


def _own_gates(code: str, now: datetime) -> list[str]:
    rows = db.query(
        "SELECT DISTINCT gate FROM flights WHERE airline=? AND direction='D' AND std BETWEEN ? AND ?",
        (code, iso(now - timedelta(hours=2)), iso(now + timedelta(hours=6))),
    )
    return [row["gate"] for row in rows if row["gate"]]


def _goodwill(req: Request) -> Response:
    code = _code(req)
    if req.method == "GET":
        return json_response({"settings": goodwill.settings_for(code), "recent": goodwill.recent(code)})
    payload = req.body or {}
    settings = goodwill.set_settings(code, payload)
    return json_response({"ok": True, "settings": settings, "recent": goodwill.recent(code)})


def _marketplace(req: Request) -> Response:
    code = _code(req)
    if req.method == "GET":
        rows = db.query(
            "SELECT m.*, a.name AS retailer_name FROM marketplace m JOIN advertisers a ON a.id=m.retailer_id "
            "WHERE m.airline=? ORDER BY m.id",
            (code,),
        )
        return json_response({"items": [dict(row) for row in rows]})
    offer_id = req.params["id"]
    row = db.query_one("SELECT * FROM marketplace WHERE id=?", (offer_id,))
    if not row:
        return json_response({"error": "not_found", "message": "Offer not found"}, status=404)
    db.execute("UPDATE marketplace SET status='accepted' WHERE id=?", (offer_id,))
    promo = None
    campaign_id = PROMO_CAMPAIGN.get(offer_id)
    flight = db.query_one(
        "SELECT * FROM flights WHERE airline=? AND direction='D' AND status != 'CNL' "
        "ORDER BY ABS(strftime('%s', std) - strftime('%s', ?)) LIMIT 1",
        (code, iso(req.now)),
    )
    if campaign_id and flight:
        try:
            promo = create_promo(
                campaign_id, flight["flight_id"], req.now,
                label=f"{row['title']} · airline accepted", value="10%", minutes=120,
            )
        except ValueError:
            promo = None
    req.sim.bus.publish("marketplace", {"id": offer_id, "airline": code, "status": "accepted"})
    return json_response({"ok": True, "id": offer_id, "status": "accepted", "promo": promo})


def _performance(req: Request) -> Response:
    code = _code(req)
    today = req.now.date().isoformat()
    campaign_ids = [
        row["id"]
        for row in db.query(
            "SELECT id FROM campaigns WHERE advertiser_id=? OR filters_json LIKE ?",
            (f"ADV-AIR-{code}", f'%"airline":"{code}"%'),
        )
    ]
    placeholders = ",".join("?" for _ in campaign_ids) or "''"
    daily = db.query(
        f"SELECT day, SUM(impressions) AS impressions, SUM(redemptions) AS redemptions, "
        f"SUM(revenue) AS revenue FROM daily_stats WHERE campaign_id IN ({placeholders}) "
        f"GROUP BY day ORDER BY day DESC LIMIT 14",
        tuple(campaign_ids),
    ) if campaign_ids else []
    overall = db.query_one(
        f"SELECT COALESCE(SUM(impressions),0) AS impressions, COALESCE(SUM(redemptions),0) AS redemptions, "
        f"COALESCE(SUM(revenue),0) AS revenue FROM daily_stats WHERE campaign_id IN ({placeholders})",
        tuple(campaign_ids),
    ) if campaign_ids else {"impressions": 0, "redemptions": 0, "revenue": 0}
    flights = db.query(
        "SELECT COUNT(*) AS c, COALESCE(SUM(pax),0) AS pax, COALESCE(AVG(pax*1.0/NULLIF(seats,0)),0) AS load "
        "FROM flights WHERE airline=? AND direction='D' AND std >= ?",
        (code, today + "T00:00:00Z"),
    )
    return json_response(
        {
            "airline": code,
            "overall": {
                "impressions": int(overall["impressions"]),
                "redemptions": int(overall["redemptions"]),
                "revenue": round(float(overall["revenue"]), 2),
                "flights": int(flights["c"]),
                "passengers": int(flights["pax"]),
                "avgLoadFactor": round(float(flights["load"]), 3),
                "redemptionRate": round(float(overall["redemptions"]) / max(1, float(overall["impressions"])) * 100, 2),
            },
            "daily": [dict(row) for row in reversed(daily)],
        }
    )


ROUTES: list[Route] = [
    ("GET", "/api/airline/companies", _companies),
    ("GET", "/api/airline/summary", _summary),
    ("GET", "/api/airline/flights", _flights),
    ("GET", "/api/airline/messages", _messages),
    ("POST", "/api/airline/messages", _messages),
    ("GET", "/api/airline/goodwill", _goodwill),
    ("PUT", "/api/airline/goodwill", _goodwill),
    ("GET", "/api/airline/marketplace", _marketplace),
    ("POST", "/api/airline/marketplace/{id}/accept", _marketplace),
    ("GET", "/api/airline/performance", _performance),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)