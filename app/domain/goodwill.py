"""Airline delay-goodwill automation.

When a flight is delayed past the airline's threshold, the platform pushes a
co-funded voucher from the airline and an F&B/retail partner to the gate
screens.  The action is recorded with its promo code so the demo can show the
cause-and-effect chain end to end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import db
from ..models import iso
from . import promos

DEFAULTS = {
    "enabled": True,
    "threshold": 30,
    "partner": "ADV-02",
    "offer": "€10 meal voucher",
    "campaignId": "",
}
CAMPAIGN_BY_AIRLINE = {"XH": "CMP-19", "ZO": "CMP-20", "YU": "CMP-21", "XD": "CMP-22"}
FALLBACK_CAMPAIGN = "CMP-04"


def settings_for(airline: str) -> dict[str, Any]:
    row = db.query_one("SELECT value_json FROM rules WHERE key = ?", (f"goodwill_{airline}",))
    stored = db.json_loads(row["value_json"], {}) if row else {}
    merged = dict(DEFAULTS)
    merged.update(stored if isinstance(stored, dict) else {})
    return merged


def set_settings(airline: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = settings_for(airline)
    for key in ("enabled", "threshold", "partner", "offer", "campaignId"):
        if key in payload:
            current[key] = payload[key]
    current["enabled"] = bool(current["enabled"])
    try:
        current["threshold"] = max(5, min(240, int(current["threshold"])))
    except (TypeError, ValueError):
        current["threshold"] = 30
    current["partner"] = str(current["partner"])[:30]
    current["offer"] = str(current["offer"])[:120]
    current["campaignId"] = str(current["campaignId"])[:30]
    db.execute(
        "INSERT INTO rules(key, value_json, updated) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated=excluded.updated",
        (f"goodwill_{airline}", db.json_dumps(current), iso(datetime.utcnow())),
    )
    return current


def maybe_auto(flight: dict[str, Any], minutes: int, now: datetime) -> dict[str, Any] | None:
    airline = flight["airline"]
    config = settings_for(airline)
    if not config["enabled"] or minutes < int(config["threshold"]):
        return None
    campaign_id = config.get("campaignId") or CAMPAIGN_BY_AIRLINE.get(airline) or FALLBACK_CAMPAIGN
    campaign = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not campaign or campaign["status"] != "approved":
        campaign_id = FALLBACK_CAMPAIGN
        campaign = db.query_one("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    if not campaign:
        return None
    partner = db.query_one("SELECT * FROM advertisers WHERE id = ?", (config["partner"],))
    partner_name = partner["name"] if partner else "Airport partner"
    try:
        promo = promos.create(
            campaign_id,
            flight["flight_id"],
            now,
            label=f"Delay goodwill · {partner_name}",
            value=config["offer"],
            minutes=90,
        )
    except ValueError:
        return None
    db.execute(
        "INSERT INTO goodwill_actions(airline, flight_id, minutes, partner, offer, code, campaign_id, created) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (airline, flight["flight_id"], minutes, partner_name, config["offer"], promo["code"], campaign_id, iso(now)),
    )
    return {
        "airline": airline,
        "flightId": flight["flight_id"],
        "flight": f"{airline}{flight['flight_no']}",
        "minutes": minutes,
        "partner": partner_name,
        "offer": config["offer"],
        "code": promo["code"],
        "campaignId": campaign_id,
        "coFunded": True,
    }


def recent(airline: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT * FROM goodwill_actions WHERE airline = ? ORDER BY id DESC LIMIT ?", (airline, limit)
    )
    return [dict(row) for row in rows]