"""Passenger presence and crowd-profile aggregation.

All values are aggregates over flights and zones.  The engine never stores or
uses per-passenger data: the smallest unit is a flight leg, and every screen
decision is computed from weighted flight loads plus ACRIS queue readings.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from ..models import parse_time


def flight_presence(flight: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """Estimate how many passengers from one departure are near the screen."""
    if flight.get("direction") != "D" or flight.get("status") in {"CNL"}:
        return None
    scheduled = parse_time(flight.get("std"))
    estimated = parse_time(flight.get("etd") or flight.get("std")) or scheduled
    if not scheduled or not estimated:
        return None
    if flight.get("status") == "DEP" and now > estimated + timedelta(minutes=20):
        return None
    boarding_start = scheduled - timedelta(minutes=40)
    boarding_close = estimated - timedelta(minutes=10)
    if now < scheduled - timedelta(minutes=210) or now > estimated + timedelta(minutes=25):
        return None
    if now < boarding_start:
        minutes = (boarding_start - now).total_seconds() / 60
        weight = 0.42 + 0.52 * math.exp(-max(0.0, minutes - 20) / 110)
    elif now <= boarding_close:
        weight = 0.94
    elif now <= estimated + timedelta(minutes=10):
        weight = 0.4
    else:
        weight = 0.12
    delay = max(0, int((estimated - scheduled).total_seconds() // 60))
    pax = int(flight.get("pax") or 0)
    expected = max(0.0, pax * weight)
    dwell = int(max(5, min(180, (estimated - now).total_seconds() / 60 + delay * 0.35)))
    return {
        "flightId": str(flight.get("flight_id")),
        "flightNo": f"{flight.get('airline')}{flight.get('flight_no')}",
        "destination": flight.get("destination"),
        "gate": flight.get("gate"),
        "expectedPax": round(expected, 1),
        "pax": pax,
        "delayMinutes": delay,
        "dwellMinutes": dwell,
        "status": flight.get("status"),
        "scheduled": flight.get("std"),
        "estimated": flight.get("etd") or flight.get("std"),
        "updated": flight.get("updated"),
        "profile": flight.get("_profile") or {},
    }


def aggregate(
    flights: list[dict[str, Any]],
    now: datetime,
    queue: dict[str, Any] | None = None,
    proximity: dict[str, float] | None = None,
) -> dict[str, Any]:
    contributions: list[dict[str, Any]] = []
    for flight in flights:
        presence = flight_presence(flight, now)
        if not presence:
            continue
        factor = (proximity or {}).get(str(flight.get("gate")), 1.0)
        presence["expectedPax"] = round(presence["expectedPax"] * factor, 2)
        if presence["expectedPax"] > 0.5:
            contributions.append(presence)
    if not contributions:
        return _empty(queue)
    total = sum(item["expectedPax"] for item in contributions) or 1.0
    shares: dict[str, float] = {}
    attribute_keys = {
        "purpose": "purpose",
        "party": "party",
        "age": "age",
        "gender": "gender",
        "cabin": "cabin",
        "spendTier": "spend",
        "nationality": "nat",
        "language": "lang",
    }
    for prefix, profile_key in attribute_keys.items():
        bucket: dict[str, float] = {}
        for item in contributions:
            profile = item["profile"]
            values = profile.get(profile_key) or {}
            for key, value in values.items():
                bucket[key] = bucket.get(key, 0.0) + float(value) * item["expectedPax"]
        for key, value in bucket.items():
            shares[f"{prefix}.{key}"] = round(value / total, 4)
    base_keys = {
        "international": "international",
        "holiday": "holiday",
        "business": "business",
        "vfr": "vfr",
        "student": "student",
        "religious": "religious",
        "family": "family",
        "couple": "couple",
        "solo": "solo",
        "group": "group",
        "young": "young",
        "senior": "senior",
        "luxury": "luxury",
        "value": "value",
        "gourmet": "gourmet",
        "wellness": "wellness",
        "tech": "tech",
        "beach": "beach",
        "shopper": "shopper",
    }
    for score_key, profile_key in base_keys.items():
        value = 0.0
        for item in contributions:
            value += float((item["profile"].get("shares") or {}).get(profile_key, 0.0)) * item["expectedPax"]
        shares[score_key] = round(value / total, 4)
    shares["domestic"] = round(max(0.0, 1.0 - shares.get("international", 0.0)), 4)
    shares["ff.high"] = round(
        sum(float((i["profile"].get("ffShare") or 0)) * i["expectedPax"] for i in contributions) / total,
        4,
    )

    destinations = _top_dimension(contributions, "destination", "destinationCity", total)
    nationalities = _top_profile_dimension(contributions, "nationality", total)
    languages = _top_profile_dimension(contributions, "language", total)
    dwells = sorted(item["dwellMinutes"] for item in contributions)
    median_dwell = dwells[len(dwells) // 2] if dwells else 0
    delay = round(
        sum(item["delayMinutes"] * item["expectedPax"] for item in contributions) / total, 1
    )
    queue_boost = 0.0
    if queue:
        queue_boost = min(40.0, float(queue.get("queue_len") or 0) * 0.25)
    crowd = int(round(total + queue_boost))
    return {
        "crowd": crowd,
        "internationalShare": shares.get("international", 0.0),
        "medianDwell": median_dwell,
        "delay": delay,
        "shares": shares,
        "destinations": destinations,
        "nationalities": nationalities,
        "languages": languages,
        "flights": [
            {key: item[key] for key in (
                "flightId", "flightNo", "destination", "gate", "expectedPax",
                "pax", "delayMinutes", "dwellMinutes", "status", "scheduled", "estimated",
            )}
            for item in sorted(contributions, key=lambda row: row["expectedPax"], reverse=True)
        ],
        "flightIds": [item["flightId"] for item in contributions],
        "queue": queue or {},
        "attributeCoverage": _attribute_coverage(contributions),
    }


def _top_dimension(contributions: list[dict], key: str, city_key: str, total: float) -> list[dict]:
    bucket: dict[str, dict] = {}
    for item in contributions:
        code = str(item.get(key) or "?")
        entry = bucket.setdefault(code, {"code": code, "city": (item.get("profile") or {}).get(city_key, ""), "weight": 0.0})
        entry["weight"] += item["expectedPax"]
    ranked = sorted(bucket.values(), key=lambda entry: entry["weight"], reverse=True)[:5]
    return [
        {"code": entry["code"], "city": entry["city"], "share": round(entry["weight"] / total, 3)}
        for entry in ranked
    ]


def _top_profile_dimension(contributions: list[dict], key: str, total: float) -> list[dict]:
    bucket: dict[str, float] = {}
    for item in contributions:
        for code, share in ((item.get("profile") or {}).get(key) or {}).items():
            bucket[code] = bucket.get(code, 0.0) + float(share) * item["expectedPax"]
    ranked = sorted(bucket.items(), key=lambda pair: pair[1], reverse=True)[:3]
    return [{"code": code, "share": round(value / total, 3)} for code, value in ranked]


def _attribute_coverage(contributions: list[dict]) -> float:
    with_profiles = sum(1 for item in contributions if item.get("profile"))
    return round(with_profiles / len(contributions), 3) if contributions else 0.0


def _empty(queue: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "crowd": int(float((queue or {}).get("queue_len") or 0) * 0.25),
        "internationalShare": 0.0,
        "medianDwell": 0,
        "delay": 0,
        "shares": {},
        "destinations": [],
        "nationalities": [],
        "languages": [],
        "flights": [],
        "flightIds": [],
        "queue": queue or {},
        "attributeCoverage": 0.0,
    }