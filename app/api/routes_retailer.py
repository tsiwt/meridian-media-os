"""Retailer: live dashboard, footfall, campaign builder, creatives, promos, history."""

from __future__ import annotations

from datetime import datetime, timedelta

from .. import db
from ..domain.ai import build_provider
from ..domain.profile import build_profile, screen_context, zone_presence
from ..domain.promos import create as create_promo
from ..domain.promos import list_promos, share
from ..models import iso, parse_time
from . import serializers
from .http import Request, Response, Route, body_float, body_int, body_str, dispatch, json_response, q_str

DEFAULT_ADVERTISER = "ADV-01"


def _advertiser_id(req: Request) -> str:
    return q_str(req, "advertiserId") or body_str(req.body, "advertiserId", DEFAULT_ADVERTISER, 30)


def _outlets(req: Request) -> Response:
    company = _company(req)
    rows = db.query(
        "SELECT o.*, a.name AS advertiser_name, z.name AS zone_name FROM outlets o "
        "JOIN advertisers a ON a.id=o.advertiser_id JOIN zones z ON z.id=o.zone_id "
        "WHERE o.advertiser_id=? ORDER BY o.id",
        (company["id"],),
    )
    return json_response({"items": [serializers.outlet(row) for row in rows]})


def _company(req: Request) -> dict:
    advertiser_id = _advertiser_id(req)
    row = db.query_one("SELECT * FROM advertisers WHERE id = ?", (advertiser_id,))
    if not row:
        row = db.query_one("SELECT * FROM advertisers WHERE kind = 'retailer' ORDER BY id LIMIT 1")
    return dict(row) if row else {"id": DEFAULT_ADVERTISER, "name": "Meridian Duty Free"}


def _companies(_: Request) -> Response:
    rows = db.query(
        "SELECT a.*, COUNT(o.id) AS outlets FROM advertisers a LEFT JOIN outlets o "
        "ON o.advertiser_id = a.id WHERE a.kind IN ('retailer','brand','house') "
        "GROUP BY a.id ORDER BY a.id"
    )
    return json_response({"items": [serializers.advertiser(row) for row in rows]})


def _dashboard(req: Request) -> Response:
    company = _company(req)
    now = req.now
    today = now.date().isoformat()
    outlet_id = q_str(req, "outletId")
    outlet = None
    if outlet_id:
        row = db.query_one(
            "SELECT o.*, z.name AS zone_name FROM outlets o JOIN zones z ON z.id=o.zone_id WHERE o.id=?",
            (outlet_id,),
        )
        outlet = serializers.outlet(row) if row else None
    stats = db.query_one(
        "SELECT COALESCE(SUM(d.impressions),0) AS impressions, COALESCE(SUM(d.scans),0) AS scans, "
        "COALESCE(SUM(d.redemptions),0) AS redemptions, COALESCE(SUM(d.revenue),0) AS revenue "
        "FROM daily_stats d JOIN campaigns c ON c.id = d.campaign_id "
        "WHERE c.advertiser_id = ? AND d.day = ?",
        (company["id"], today),
    )
    campaigns = [
        serializers.campaign(row)
        for row in db.query(
            "SELECT c.*, a.name AS advertiser_name, cr.name AS creative_name, cr.status AS creative_status, "
            "a.kind AS advertiser_kind FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
            "JOIN creatives cr ON cr.id=c.creative_id WHERE c.advertiser_id=? ORDER BY c.id",
            (company["id"],),
        )
    ]
    segments = [
        dict(row)
        for row in db.query(
            "SELECT s.segment, SUM(s.impressions) AS impressions, SUM(s.scans) AS scans, "
            "SUM(s.redemptions) AS redemptions, SUM(s.revenue) AS revenue FROM segment_stats s "
            "JOIN campaigns c ON c.id=s.campaign_id WHERE c.advertiser_id=? GROUP BY s.segment "
            "ORDER BY redemptions DESC",
            (company["id"],),
        )
    ]
    redemptions = [
        dict(row)
        for row in db.query(
            "SELECT r.*, c.name AS campaign_name, f.flight_no, f.destination FROM redemptions r "
            "JOIN campaigns c ON c.id=r.campaign_id LEFT JOIN flights f ON f.flight_id=r.flight_id "
            "WHERE c.advertiser_id=? ORDER BY r.id DESC LIMIT 12",
            (company["id"],),
        )
    ]
    live = [
        serializers.decision_summary(row)
        for row in db.query(
            "SELECT d.* FROM decisions d JOIN campaigns c ON c.id=d.winner_id "
            "WHERE c.advertiser_id=? ORDER BY d.id DESC LIMIT 8",
            (company["id"],),
        )
    ]
    promos = [
        promo
        for campaign in campaigns
        for promo in list_promos(campaign["id"], now)
    ]
    impressions = int(stats["impressions"])
    redemptions_count = int(stats["redemptions"])
    scans = int(stats["scans"])
    suggestion = _suggestion(segments)
    return json_response(
        {
            "company": company,
            "outlet": outlet,
            "kpi": {
                "impressions": impressions,
                "scans": scans,
                "redemptions": redemptions_count,
                "conversion": round(redemptions_count / scans, 4) if scans else 0.0,
                "revenue": round(float(stats["revenue"]), 2),
                "currency": req.settings.currency,
                "activeCampaigns": sum(1 for campaign in campaigns if campaign["status"] == "approved"),
                "livePromos": sum(1 for promo in promos if promo["live"]),
            },
            "campaigns": campaigns,
            "segments": segments,
            "redemptions": redemptions,
            "live": live,
            "promos": promos[:40],
            "suggestion": suggestion,
            "now": iso(now),
        }
    )


def _suggestion(segments: list[dict]) -> dict:
    if not segments:
        return {"text": "No segment data yet."}
    best = max(segments, key=lambda row: row["redemptions"])
    rate = best["redemptions"] / best["scans"] if best["scans"] else 0
    return {
        "segment": best["segment"],
        "redemptionRate": round(rate, 3),
        "text": f"{best['segment'].title()} travellers redeemed at {round(rate * 100)}%; "
                f"suggest raising the {best['segment']} weight by 0.1 next run.",
    }


def _flow(req: Request) -> Response:
    outlet_id = q_str(req, "outletId")
    row = db.query_one("SELECT * FROM outlets WHERE id = ?", (outlet_id,)) if outlet_id else None
    if not row:
        row = db.query_one("SELECT * FROM outlets ORDER BY id LIMIT 1")
    zone_id = row["zone_id"] if row else "T2-F"
    now = req.now
    series = []
    for index in range(8):
        moment = now + timedelta(minutes=15 * index)
        presence = zone_presence(zone_id, moment)
        series.append(
            {
                "time": iso(moment),
                "crowd": presence["crowd"],
                "internationalShare": presence["internationalShare"],
                "flights": presence["flights"],
            }
        )
    current = zone_presence(zone_id, now)
    next60 = round(sum(point["crowd"] for point in series[:4]) / 4)
    return json_response(
        {
            "zoneId": zone_id,
            "zoneName": row["zone_id"] if row else zone_id,
            "series": series,
            "next60": next60,
            "internationalShare": current["internationalShare"],
            "topDestinations": current["top"],
            "nationalities": current.get("nationalities", []),
            "languages": current.get("languages", []),
            "flights": current["flights"],
            "evidenceCount": current["evidenceCount"],
        }
    )


def _campaigns(req: Request) -> Response:
    company = _company(req)
    rows = db.query(
        "SELECT c.*, a.name AS advertiser_name, cr.name AS creative_name, cr.status AS creative_status, "
        "a.kind AS advertiser_kind FROM campaigns c JOIN advertisers a ON a.id=c.advertiser_id "
        "JOIN creatives cr ON cr.id=c.creative_id WHERE c.advertiser_id=? ORDER BY c.id",
        (company["id"],),
    )
    return json_response({"items": [serializers.campaign(row) for row in rows]})


def _campaign_create(req: Request) -> Response:
    company = _company(req)
    body = req.body
    name = body_str(body, "name", "", 160)
    creative_id = body_str(body, "creativeId", "", 30)
    creative = db.query_one("SELECT * FROM creatives WHERE id = ? AND advertiser_id = ?", (creative_id, company["id"]))
    if not name or not creative:
        return json_response({"error": "bad_request", "message": "name and a creative owned by this advertiser are required"}, status=400)
    now = req.now
    next_id = db.query_one("SELECT COUNT(*) AS c FROM campaigns")["c"] + 1
    campaign_id = f"CMP-{next_id:02d}"
    start = _datetime(body.get("start"), now)
    end = _datetime(body.get("end"), now + timedelta(days=14))
    if end <= start:
        return json_response({"error": "bad_request", "message": "end must be after start"}, status=400)
    db.execute(
        "INSERT INTO campaigns(id, advertiser_id, creative_id, name, status, start, end, daypart_json, "
        "budget, daily_cap, freq_cap_min, bid, segments_json, filters_json, placement_json, "
        "triggers_json, spend, impressions, scans, redemptions, revenue, conversion, created, notes, "
        "priority, ab_group, category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,0,0,?,?,?,?,?)",
        (
            campaign_id, company["id"], creative_id, name, "pending", iso(start), iso(end),
            db.json_dumps({"preset": body_str(body, "daypart", "all_day", 20), "startHour": 0, "endHour": 24}),
            body_float(body, "budget", 5000, 0, 1_000_000),
            body_float(body, "dailyCap", 400, 0, 100_000),
            body_int(body, "freqCapMin", 20, 1, 1440),
            body_float(body, "bid", 2.5, 0, 100),
            db.json_dumps(_segments(body.get("segments"))),
            db.json_dumps(_filters(body.get("filters"))),
            db.json_dumps(_placement(body.get("placement"))),
            db.json_dumps(body.get("triggers") if isinstance(body.get("triggers"), dict) else {}),
            iso(now), body_str(body, "notes", "Created in retailer campaign builder.", 500),
            body_int(body, "priority", 1, 0, 5), "A" if next_id % 2 else "B",
            creative["category"],
        ),
    )
    preview = _campaign_preview(req, campaign_id)
    return json_response({"ok": True, "campaignId": campaign_id, "preview": preview.get("body", {})}, status=201)


def _segments(value) -> dict:
    default = {"holiday": 0.7, "family": 0.5, "international": 0.6}
    if not isinstance(value, dict):
        return default
    clean = {}
    for key, weight in value.items():
        if isinstance(weight, (int, float)) and 0 <= float(weight) <= 1:
            clean[str(key)[:30]] = float(weight)
    return clean or default


def _filters(value) -> dict:
    if not isinstance(value, dict):
        return {}
    output = {}
    for key in ("internationalOnly", "domesticOnly", "airline"):
        if key in value:
            output[key] = value[key]
    for key in ("minDwell", "minCrowd"):
        if key in value:
            output[key] = body_int(value, key, 0, 0, 100000)
    destinations = value.get("destinations")
    if isinstance(destinations, list):
        output["destinations"] = [str(item)[:5] for item in destinations][:20]
    return output


def _placement(value) -> dict:
    if not isinstance(value, dict):
        return {"zones": ["*"]}
    return {
        "zones": [str(item)[:30] for item in value.get("zones", [])][:20],
        "gates": [str(item)[:5] for item in value.get("gates", [])][:20],
        "screens": [str(item)[:20] for item in value.get("screens", [])][:20],
    }


def _datetime(value, default: datetime) -> datetime:
    parsed = parse_time(str(value)) if value else None
    return parsed or default


def _campaign_preview(req: Request, campaign_id: str) -> Response:
    row = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not row:
        return json_response({"error": "not_found"}, status=404)
    campaign = dict(row)
    placement = db.json_loads(campaign["placement_json"], {})
    zones = placement.get("zones") or ["T2-F"]
    if zones == ["*"]:
        zones = ["T2-F", "T2-DUTY"]
    now = req.now
    crowd = sum(zone_presence(zone, now + timedelta(minutes=15))["crowd"] for zone in zones[:2])
    today_impressions = db.query_one(
        "SELECT COALESCE(SUM(impressions),0) AS i FROM daily_stats WHERE campaign_id=? AND day=?",
        (campaign_id, now.date().isoformat()),
    )["i"]
    impressions = max(0, int(crowd * 0.42))
    return json_response(
        {
            "campaignId": campaign_id,
            "matches": min(96, max(12, int(crowd / 18))),
            "expectedImpressions": impressions,
            "expectedRedemptions": int(impressions * 0.031),
            "window": "next scheduled slot",
            "zones": zones[:2],
            "todayImpressions": int(today_impressions),
            "basis": "Live ZonePresence now + 15 minutes",
        }
    )


def _preview(req: Request) -> Response:
    campaign_id = q_str(req, "campaignId") or body_str(req.body, "campaignId", "", 30)
    if campaign_id:
        return _campaign_preview(req, campaign_id)
    placement = _placement(req.body.get("placement"))
    zones = placement.get("zones") or ["T2-F"]
    if zones == ["*"]:
        zones = ["T2-F", "T2-DUTY"]
    segments = _segments(req.body.get("segments"))
    total_weight = sum(segments.values()) or 1.0
    matches = []
    crowds = []
    for zone in zones[:3]:
        row = db.query_one(
            "SELECT id FROM screens WHERE zone_id=? AND status='online' ORDER BY id LIMIT 1", (zone,)
        )
        screen = screen_context(row["id"]) if row else None
        if not screen:
            continue
        profile = build_profile(screen, req.now, req.settings)
        crowds.append(profile.crowd_size)
        score = sum(weight * float(profile.shares.get(segment, 0.0)) for segment, weight in segments.items()) / total_weight
        matches.append(score)
    match = sum(matches) / len(matches) if matches else 0.0
    crowd = int(sum(crowds) / len(crowds)) if crowds else 0
    impressions = int(crowd * 0.42)
    return json_response(
        {
            "matches": min(97, max(5, int(match * 100))),
            "expectedImpressions": impressions,
            "expectedRedemptions": int(impressions * 0.031),
            "window": "next scheduled slot",
            "zones": zones[:2],
            "audienceMatch": round(match, 3),
            "crowd": crowd,
            "basis": "Live ZonePresence now + 15 minutes",
        }
    )


def _campaign_copy(req: Request, rerun: bool) -> Response:
    row = db.query_one("SELECT * FROM campaigns WHERE id = ?", (req.params["id"],))
    if not row:
        return json_response({"error": "not_found", "message": "Campaign not found"}, status=404)
    campaign = dict(row)
    now = req.now
    next_id = db.query_one("SELECT COUNT(*) AS c FROM campaigns")["c"] + 1
    campaign_id = f"CMP-{next_id:02d}"
    start = now if rerun else now + timedelta(days=1)
    end = start + timedelta(days=14)
    db.execute(
        "INSERT INTO campaigns(id, advertiser_id, creative_id, name, status, start, end, daypart_json, "
        "budget, daily_cap, freq_cap_min, bid, segments_json, filters_json, placement_json, triggers_json, "
        "spend, impressions, scans, redemptions, revenue, conversion, created, notes, priority, ab_group, category) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,0,0,0,?,?,?,?,?)",
        (
            campaign_id, campaign["advertiser_id"], campaign["creative_id"],
            (campaign["name"] + (" · rerun" if rerun else " · copy"))[:160], "pending",
            iso(start), iso(end), campaign["daypart_json"], campaign["budget"], campaign["daily_cap"],
            campaign["freq_cap_min"], campaign["bid"], campaign["segments_json"],
            campaign["filters_json"], campaign["placement_json"], campaign["triggers_json"],
            iso(now), "Duplicated from " + campaign["id"], campaign["priority"],
            "B" if campaign["ab_group"] == "A" else "A", campaign["category"],
        ),
    )
    return json_response({"ok": True, "campaignId": campaign_id, "source": campaign["id"]}, status=201)


def _creatives(req: Request) -> Response:
    company = _company(req)
    if req.method == "GET":
        rows = db.query(
            "SELECT cr.*, a.name AS advertiser_name FROM creatives cr JOIN advertisers a ON a.id=cr.advertiser_id "
            "WHERE cr.advertiser_id=? ORDER BY cr.id",
            (company["id"],),
        )
        return json_response({"items": [serializers.creative(row) for row in rows]})
    body = req.body
    name = body_str(body, "name", "", 120)
    headline_en = body_str(body, "headlineEn", "", 120)
    if not name or not headline_en:
        return json_response({"error": "bad_request", "message": "name and headlineEn are required"}, status=400)
    next_id = db.query_one("SELECT COUNT(*) AS c FROM creatives")["c"] + 1
    creative_id = f"CRE-{next_id:02d}"
    image = body_str(body, "image", "", 400_000)
    db.execute(
        "INSERT INTO creatives(id, advertiser_id, name, headline_en, headline_zh, body_en, body_zh, "
        "cta_en, cta_zh, template, colors_json, image, category, status, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            creative_id, company["id"], name, headline_en,
            body_str(body, "headlineZh", headline_en, 120), body_str(body, "bodyEn", "", 400),
            body_str(body, "bodyZh", "", 400), body_str(body, "ctaEn", "Learn more", 40),
            body_str(body, "ctaZh", "了解更多", 40), body_str(body, "template", "aurora", 20),
            db.json_dumps(body.get("colors") if isinstance(body.get("colors"), list) else ["#38e8c8", "#8b7bff"]),
            image, body_str(body, "category", "retail", 40), "pending", iso(req.now),
        ),
    )
    return json_response({"ok": True, "id": creative_id}, status=201)


def _generate_creative(req: Request) -> Response:
    brief = body_str(req.body, "brief", "", 240)
    language = body_str(req.body, "language", req.settings.second_language, 5)
    provider = build_provider(req.settings)
    result = provider.creative(brief, language)
    result["also"] = provider.creative(brief, "en" if language != "en" else "zh")
    return json_response(result)


def _promos(req: Request) -> Response:
    company = _company(req)
    campaign_id = q_str(req, "campaignId")
    if req.method == "GET":
        if campaign_id:
            return json_response({"items": list_promos(campaign_id, req.now)})
        rows = db.query(
            "SELECT p.campaign_id FROM promos p JOIN campaigns c ON c.id=p.campaign_id "
            "WHERE c.advertiser_id=? GROUP BY p.campaign_id",
            (company["id"],),
        )
        items = [promo for row in rows for promo in list_promos(row["campaign_id"], req.now)]
        return json_response({"items": items})
    campaign_id = body_str(req.body, "campaignId", "", 30)
    campaign = db.query_one("SELECT * FROM campaigns WHERE id=? AND advertiser_id=?", (campaign_id, company["id"]))
    if not campaign:
        return json_response({"error": "bad_request", "message": "Campaign not found for this company"}, status=400)
    flight_id = body_str(req.body, "flightId", "", 30)
    if not flight_id:
        flight = db.query_one(
            "SELECT f.flight_id FROM flights f JOIN gates g ON g.code=f.gate JOIN zones z ON z.id=g.zone_id "
            "WHERE f.direction='D' AND f.status != 'CNL' ORDER BY ABS(strftime('%s', f.std) - strftime('%s', ?)) LIMIT 1",
            (iso(req.now),),
        )
        flight_id = flight["flight_id"] if flight else ""
    try:
        promo = create_promo(
            campaign_id, flight_id, req.now,
            label=body_str(req.body, "label", "Gate offer", 120),
            value=body_str(req.body, "value", "10%", 40),
            minutes=body_int(req.body, "minutes", 30, 5, 240),
        )
    except ValueError as exc:
        return json_response({"error": "promo_error", "message": str(exc)}, status=400)
    return json_response({"ok": True, "promo": promo}, status=201)


def _promo_share(req: Request) -> Response:
    try:
        promo = share(req.params["code"], req.now)
    except ValueError as exc:
        return json_response({"error": "promo_error", "message": str(exc)}, status=409)
    return json_response({"ok": True, "promo": promo})


def _triggers(req: Request) -> Response:
    company = _company(req)
    if req.method == "GET":
        rows = db.query(
            "SELECT id, name, triggers_json, status FROM campaigns WHERE advertiser_id=? AND triggers_json != '{}'",
            (company["id"],),
        )
        return json_response({"items": [{"campaignId": row["id"], "name": row["name"], "status": row["status"], "triggers": db.json_loads(row["triggers_json"], {})} for row in rows]})
    campaign_id = body_str(req.body, "campaignId", "", 30)
    campaign = db.query_one("SELECT * FROM campaigns WHERE id=? AND advertiser_id=?", (campaign_id, company["id"]))
    if not campaign:
        return json_response({"error": "not_found", "message": "Campaign not found"}, status=404)
    triggers = req.body.get("triggers") if isinstance(req.body.get("triggers"), dict) else {}
    db.execute("UPDATE campaigns SET triggers_json=? WHERE id=?", (db.json_dumps(triggers), campaign_id))
    return json_response({"ok": True, "campaignId": campaign_id, "triggers": triggers})


def _stock(req: Request) -> Response:
    outlet_id = req.params["id"]
    row = db.query_one("SELECT * FROM outlets WHERE id=?", (outlet_id,))
    if not row:
        return json_response({"error": "not_found", "message": "Outlet not found"}, status=404)
    status = body_str(req.body, "status", "out_of_stock" if row["stock_status"] == "in_stock" else "in_stock", 20)
    if status not in {"in_stock", "out_of_stock"}:
        return json_response({"error": "bad_request", "message": "Invalid stock status"}, status=400)
    db.execute("UPDATE outlets SET stock_status=? WHERE id=?", (status, outlet_id))
    return json_response({"ok": True, "outletId": outlet_id, "status": status})


def _recommendations(req: Request) -> Response:
    campaign_id = q_str(req, "campaignId") or body_str(req.body, "campaignId", "", 30)
    row = db.query_one("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
    if not row:
        return json_response({"error": "not_found", "message": "Campaign not found"}, status=404)
    campaign = dict(row)
    placement = db.json_loads(campaign["placement_json"], {})
    zones = placement.get("zones") or ["T2-F"]
    if zones == ["*"]:
        zones = ["T2-F", "T2-DUTY"]
    now = req.now
    slots = [(8, 10), (12, 14), (16, 18), (19, 21)]
    results = []
    for start_hour, end_hour in slots:
        probe = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        crowd = sum(zone_presence(zone, probe)["crowd"] for zone in zones[:2])
        impressions = int(crowd * (end_hour - start_hour) * 6)
        results.append(
            {
                "slot": f"{start_hour:02d}:00–{end_hour:02d}:00",
                "startHour": start_hour,
                "predictedCrowd": crowd,
                "predictedImpressions": impressions,
                "predictedRedemptions": int(impressions * 0.028),
                "zones": zones[:2],
            }
        )
    results.sort(key=lambda item: item["predictedImpressions"], reverse=True)
    return json_response(
        {
            "campaignId": campaign_id,
            "date": (now + timedelta(days=1)).date().isoformat(),
            "best": results[:3],
            "basis": "Repeating weekday schedule + 30-day segment conversion",
        }
    )


ROUTES: list[Route] = [
    ("GET", "/api/retailer/companies", _companies),
    ("GET", "/api/retailer/outlets", _outlets),
    ("GET", "/api/retailer/dashboard", _dashboard),
    ("GET", "/api/retailer/flow", _flow),
    ("GET", "/api/retailer/campaigns", _campaigns),
    ("POST", "/api/retailer/campaigns", _campaign_create),
    ("POST", "/api/retailer/campaigns/{id}/rerun", lambda req: _campaign_copy(req, True)),
    ("POST", "/api/retailer/campaigns/{id}/duplicate", lambda req: _campaign_copy(req, False)),
    ("POST", "/api/retailer/campaigns/preview", _preview),
    ("GET", "/api/retailer/creatives", _creatives),
    ("POST", "/api/retailer/creatives", _creatives),
    ("POST", "/api/retailer/creatives/generate", _generate_creative),
    ("GET", "/api/retailer/promos", _promos),
    ("POST", "/api/retailer/promos", _promos),
    ("POST", "/api/retailer/promos/{code}/share", _promo_share),
    ("GET", "/api/retailer/triggers", _triggers),
    ("POST", "/api/retailer/triggers", _triggers),
    ("POST", "/api/retailer/outlets/{id}/stock", _stock),
    ("GET", "/api/retailer/recommendations", _recommendations),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)