"""Row → JSON serializers.  UI-facing field names are camelCase."""

from __future__ import annotations

from typing import Any

from .. import db
from ..models import parse_time


def load_json(row: Any, key: str, default: Any) -> Any:
    return db.json_loads(row[key] if key in row.keys() else None, default)


def screen(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["nearestGates"] = db.json_loads(item.pop("nearest_gates_json", "[]"), [])
    item["zoneName"] = item.pop("zone_name", item.get("zone_name", ""))
    return item


def campaign(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("segments", "filters", "placement", "triggers", "daypart"):
        item[key] = db.json_loads(item.pop(f"{key}_json", "null"), {})
    item["start"] = item.get("start")
    item["end"] = item.get("end")
    spend = float(item.get("spend") or 0)
    revenue = float(item.get("revenue") or 0)
    item["roi"] = round((revenue - spend) / spend, 3) if spend else 0.0
    item["ctr"] = round(float(item.get("scans") or 0) / item["impressions"], 4) if item.get("impressions") else 0.0
    item["advertiserName"] = item.pop("advertiser_name", item.get("advertiser_name", ""))
    item["creativeName"] = item.pop("creative_name", item.get("creative_name", ""))
    item["creativeStatus"] = item.pop("creative_status", item.get("creative_status", ""))
    item["advertiserKind"] = item.pop("advertiser_kind", item.get("advertiser_kind", ""))
    return item


def creative(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["colors"] = db.json_loads(item.pop("colors_json", "[]"), [])
    item["advertiserName"] = item.pop("advertiser_name", item.get("advertiser_name", ""))
    item["headlineEn"] = item.get("headline_en", "")
    item["headlineZh"] = item.get("headline_zh", "")
    item["bodyEn"] = item.get("body_en", "")
    item["bodyZh"] = item.get("body_zh", "")
    item["ctaEn"] = item.get("cta_en", "")
    item["ctaZh"] = item.get("cta_zh", "")
    return item


def flight(row: Any) -> dict[str, Any]:
    item = dict(row)
    seats = int(item.get("seats") or 0)
    item["loadFactor"] = round(float(item.get("pax") or 0) / seats, 3) if seats else 0.0
    item["display"] = f"{item.get('airline', '')}{item.get('flight_no', '')}"
    item["delayMinutes"] = _delay(item)
    item["scheduled"] = item.get("std")
    item["estimated"] = item.get("etd") or item.get("eta") or item.get("std")
    item["international"] = item.get("nature") == "I"
    return item


def _delay(item: dict[str, Any]) -> int:
    scheduled = parse_time(item.get("std"))
    estimated = parse_time(item.get("etd") or item.get("eta"))
    if not scheduled or not estimated:
        return 0
    return max(0, int((estimated - scheduled).total_seconds() // 60))


def advertiser(row: Any) -> dict[str, Any]:
    return dict(row)


def outlet(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["advertiserName"] = item.pop("advertiser_name", item.get("advertiser_name", ""))
    item["zoneName"] = item.pop("zone_name", item.get("zone_name", ""))
    return item


def incident(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["meta"] = db.json_loads(item.pop("meta_json", "{}"), {})
    item["createdAt"] = item.pop("created")
    item["updatedAt"] = item.pop("updated")
    return item


def decision_summary(row: Any) -> dict[str, Any]:
    candidates = db.json_loads(row["candidates_json"], [])
    return {
        "id": row["id"],
        "screenId": row["screen_id"],
        "zoneId": row["zone_id"],
        "decidedAt": row["ts"],
        "winnerId": row["winner_id"],
        "winnerName": next((item.get("name") for item in candidates if item.get("campaignId") == row["winner_id"]), row["winner_id"]),
        "winnerScore": row["winner_score"],
        "fallback": bool(row["fallback"]),
        "reason": row["reason"],
        "aiModel": row["ai_model"],
        "candidateCount": len(candidates),
    }


def zone(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["gates"] = db.json_loads(item.pop("gates_json", "[]"), [])
    item["terminalId"] = item.pop("terminal_id", "")
    return item


def airline(row: Any) -> dict[str, Any]:
    return dict(row)


def report_row(row: Any) -> dict[str, Any]:
    return {
        "token": row["token"],
        "advertiserId": row["advertiser_id"],
        "payload": db.json_loads(row["payload_json"], {}),
        "created": row["created"],
    }