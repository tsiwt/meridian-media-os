"""Promo-code lifecycle, share-to-family codes and redemption accounting."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..models import iso, parse_time

AOV = {
    "perfume": 74, "toys": 38, "lounge": 42, "coffee": 8, "beach": 46,
    "sweets": 19, "watches": 310, "books": 22, "wellness": 58, "tech": 96,
    "forex": 30, "pharmacy": 17, "sports": 62, "fashion": 88, "bakery": 9,
    "hotel": 140, "cosmetics": 54, "house": 0, "airline": 120,
}


def _base_query() -> str:
    return (
        "SELECT p.*, c.name AS campaign_name, c.category AS campaign_category, "
        "c.creative_id, c.status AS campaign_status, a.name AS advertiser_name, "
        "cr.headline_en, cr.headline_zh, cr.body_en, cr.body_zh, cr.cta_en, cr.cta_zh, "
        "cr.template, cr.colors_json "
        "FROM promos p JOIN campaigns c ON c.id = p.campaign_id "
        "JOIN advertisers a ON a.id = c.advertiser_id "
        "JOIN creatives cr ON cr.id = c.creative_id "
    )


def present(row: Any, now: datetime) -> dict[str, Any]:
    promo = dict(row)
    valid_until = parse_time(promo["valid_until"])
    remaining = int((valid_until - now).total_seconds()) if valid_until else 0
    live = promo["status"] == "active" and remaining > 0 and promo["uses"] < promo["max_uses"]
    if promo["status"] == "active" and remaining <= 0:
        live = False
    promo.update(
        {
            "validUntil": promo.pop("valid_until"),
            "validFrom": promo.pop("valid_from"),
            "remainingSeconds": max(0, remaining),
            "live": live,
            "colors": db.json_loads(promo.pop("colors_json"), []),
        }
    )
    return promo


def list_promos(campaign_id: str | None, now: datetime) -> list[dict[str, Any]]:
    if campaign_id:
        rows = db.query(_base_query() + "WHERE p.campaign_id = ? ORDER BY p.id", (campaign_id,))
    else:
        rows = db.query(_base_query() + "ORDER BY p.id")
    return [present(row, now) for row in rows]


def get_by_code(code: str, now: datetime) -> dict[str, Any] | None:
    row = db.query_one(_base_query() + "WHERE p.code = ?", (code.upper(),))
    return present(row, now) if row else None


def _flight(flight_id: str) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM flights WHERE flight_id = ?", (flight_id,))
    return dict(row) if row else None


def _code_for(campaign_id: str, seed: str) -> str:
    digest = hashlib.sha256(f"{campaign_id}:{seed}".encode()).hexdigest().upper()
    return "MQI-" + digest[:5]


def create(
    campaign_id: str,
    flight_id: str,
    now: datetime,
    label: str = "Gate offer",
    value: str = "10%",
    minutes: int = 30,
    parent_code: str = "",
) -> dict[str, Any]:
    flight = _flight(flight_id)
    if not flight:
        raise ValueError("Flight not found")
    estimated = parse_time(flight.get("etd") or flight.get("std"))
    valid_until = max(now + timedelta(minutes=5), (estimated or now) - timedelta(minutes=10))
    child = bool(parent_code)
    code = _code_for(campaign_id, f"{flight_id}:{now.timestamp()}:{parent_code}:{label}")
    suffix = 0
    while db.query_one("SELECT 1 FROM promos WHERE code = ?", (code,)):
        suffix += 1
        code = _code_for(campaign_id, f"{flight_id}:{now.timestamp()}:{parent_code}:{suffix}")
    promo_id = "PRM-" + hashlib.sha256(code.encode()).hexdigest()[:8].upper()
    db.execute(
        "INSERT INTO promos(id, campaign_id, code, flight_id, valid_from, valid_until, max_uses, "
        "uses, parent_code, status, label, value) VALUES (?,?,?,?,?,?,?,0,?,?,?,?)",
        (
            promo_id, campaign_id, code, flight_id, iso(now), iso(valid_until),
            100 if not child else 50, parent_code, "active", label, value,
        ),
    )
    return get_by_code(code, now) or {}


def share(code: str, now: datetime) -> dict[str, Any]:
    parent = get_by_code(code, now)
    if not parent:
        raise ValueError("Promo code not found")
    if parent["parent_code"]:
        raise ValueError("A shared code cannot be shared again")
    return create(
        parent["campaign_id"],
        parent["flight_id"],
        now,
        label=parent["label"] + " · family share",
        value=parent["value"],
        parent_code=parent["code"],
    )


def record_scan(code: str, now: datetime) -> dict[str, Any]:
    row = db.query_one("SELECT * FROM promos WHERE code = ?", (code.upper(),))
    if not row:
        raise ValueError("Promo code not found")
    with db.transaction() as conn:
        conn.execute("UPDATE campaigns SET scans = scans + 1 WHERE id = ?", (row["campaign_id"],))
        conn.execute(
            "INSERT INTO daily_stats(campaign_id, day, impressions, scans, redemptions, revenue, spend) "
            "VALUES (?,?,0,1,0,0,0) ON CONFLICT(campaign_id, day) DO UPDATE SET "
            "scans = scans + 1",
            (row["campaign_id"], now.date().isoformat()),
        )
    return get_by_code(code, now) or {}


def claim(code: str, now: datetime, channel: str = "mobile") -> dict[str, Any]:
    row = db.query_one("SELECT * FROM promos WHERE code = ?", (code.upper(),))
    if not row:
        raise ValueError("Promo code not found")
    valid_until = parse_time(row["valid_until"])
    if row["status"] != "active" or (valid_until and now > valid_until) or row["uses"] >= row["max_uses"]:
        raise ValueError("This offer has expired or reached its limit")
    flight = _flight(row["flight_id"])
    campaign = db.query_one("SELECT * FROM campaigns WHERE id = ?", (row["campaign_id"],))
    if not campaign:
        raise ValueError("Campaign not found")
    segment = _segment_for(campaign, flight)
    value = float(AOV.get(campaign["category"], 25))
    with db.transaction() as conn:
        conn.execute("UPDATE promos SET uses = uses + 1 WHERE code = ?", (code.upper(),))
        conn.execute(
            "INSERT INTO redemptions(promo_id, campaign_id, ts, channel, value, flight_id, segment) "
            "VALUES (?,?,?,?,?,?,?)",
            (row["id"], row["campaign_id"], iso(now), channel, value, row["flight_id"], segment),
        )
        conn.execute(
            "UPDATE campaigns SET redemptions = redemptions + 1, revenue = revenue + ?, "
            "conversion = CASE WHEN scans > 0 THEN (redemptions + 1.0) / scans ELSE 0 END "
            "WHERE id = ?",
            (value, row["campaign_id"]),
        )
        conn.execute(
            "INSERT INTO daily_stats(campaign_id, day, impressions, scans, redemptions, revenue, spend) "
            "VALUES (?,?,0,0,1,?,0) ON CONFLICT(campaign_id, day) DO UPDATE SET "
            "redemptions = redemptions + 1, revenue = revenue + excluded.revenue",
            (row["campaign_id"], now.date().isoformat(), value),
        )
        conn.execute(
            "INSERT INTO segment_stats(campaign_id, segment, impressions, scans, redemptions, revenue) "
            "VALUES (?,?,0,0,1,?) ON CONFLICT(campaign_id, segment) DO UPDATE SET "
            "redemptions = redemptions + 1, revenue = revenue + excluded.revenue",
            (row["campaign_id"], segment, value),
        )
    return {
        "ok": True,
        "code": code.upper(),
        "campaignId": row["campaign_id"],
        "campaign": campaign["name"],
        "value": value,
        "segment": segment,
        "flight": f"{flight['airline']}{flight['flight_no']}" if flight else "",
        "destination": flight["destination"] if flight else "",
        "claimedAt": iso(now),
    }


def _segment_for(campaign: Any, flight: dict | None) -> str:
    segments = db.json_loads(campaign["segments_json"], {})
    if not segments:
        return "unknown"
    profile = db.json_loads((flight or {}).get("profile_json"), {}) if flight else {}
    shares = profile.get("shares") or {}
    best = ("unknown", -1.0)
    for segment, weight in segments.items():
        value = float(weight) * float(shares.get(segment, 0.4))
        if value > best[1]:
            best = (segment, value)
    return best[0]


def promo_for_campaign(campaign_id: str, now: datetime) -> dict[str, Any] | None:
    rows = list_promos(campaign_id, now)
    live = [promo for promo in rows if promo["live"]]
    return live[0] if live else (rows[0] if rows else None)