"""Build evidence-backed crowd profiles for a screen and time window."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..config import Settings
from ..models import CrowdProfile, EvidencePoint, iso, parse_time
from .presence import aggregate

PROFILE_WINDOW_MINUTES = 5


def screen_context(screen_id: str) -> dict[str, Any] | None:
    row = db.query_one(
        "SELECT s.*, z.name AS zone_name, z.kind AS zone_kind, z.gates_json, z.terminal_id "
        "FROM screens s JOIN zones z ON z.id = s.zone_id WHERE s.id = ?",
        (screen_id,),
    )
    if not row:
        return None
    screen = dict(row)
    screen["nearest_gates"] = db.json_loads(row["nearest_gates_json"], [])
    screen["zone_gates"] = db.json_loads(row["gates_json"], [])
    return screen


def _load_flights(gates: list[str], now: datetime) -> list[dict[str, Any]]:
    if not gates:
        return []
    placeholders = ",".join("?" for _ in gates)
    rows = db.query(
        "SELECT * FROM flights WHERE direction = 'D' AND gate IN ("
        + placeholders
        + ") AND std BETWEEN ? AND ?",
        (*gates, iso(now - timedelta(minutes=240)), iso(now + timedelta(hours=5))),
    )
    flights = []
    for row in rows:
        flight = dict(row)
        flight["_profile"] = db.json_loads(row["profile_json"], {})
        flights.append(flight)
    return flights


def _latest_queue(zone_id: str, now: datetime) -> dict[str, Any] | None:
    row = db.query_one(
        "SELECT * FROM queues WHERE zone_id = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (zone_id, iso(now)),
    )
    if not row:
        return None
    queue = dict(row)
    return queue


def feed_last(source: str, fallback: datetime) -> datetime:
    return parse_time(db.get_meta(f"feed_last_{source}")) or fallback


def build_profile(
    screen: dict[str, Any],
    now: datetime,
    settings: Settings,
    queue: dict[str, Any] | None = None,
) -> CrowdProfile:
    gates = screen["nearest_gates"] or screen["zone_gates"]
    flights = _load_flights(gates, now)
    if queue is None:
        queue = _latest_queue(screen["zone_id"], now)
    proximity = {str(gate): (1.0 if gate in screen["nearest_gates"] else 0.82) for gate in gates}
    raw = aggregate(flights, now, queue, proximity)
    window_start = now.replace(minute=now.minute - now.minute % PROFILE_WINDOW_MINUTES, second=0, microsecond=0)
    window_end = window_start + timedelta(minutes=PROFILE_WINDOW_MINUTES)
    evidence = _evidence(screen, flights, queue, now, settings)
    confidence = _confidence(raw, evidence, settings, now)
    return CrowdProfile(
        zone_id=screen["zone_id"],
        screen_id=screen["id"],
        window_start=window_start,
        window_end=window_end,
        crowd_size=raw["crowd"],
        international_share=raw["internationalShare"],
        median_dwell_minutes=raw["medianDwell"],
        delay_minutes=int(round(raw["delay"])),
        shares=raw["shares"],
        top_destinations=raw["destinations"],
        top_nationalities=raw["nationalities"],
        languages=raw["languages"],
        flights=raw["flightIds"],
        evidence=evidence,
        confidence=confidence,
        mode="measured",
    )


def zone_presence(zone_id: str, now: datetime) -> dict[str, Any]:
    zone = db.query_one("SELECT * FROM zones WHERE id = ?", (zone_id,))
    if not zone:
        return {"crowd": 0, "flights": 0, "internationalShare": 0}
    gates = db.json_loads(zone["gates_json"], [])
    flights = _load_flights(gates, now)
    raw = aggregate(flights, now, _latest_queue(zone_id, now))
    return {
        "crowd": raw["crowd"],
        "flights": len(raw["flights"]),
        "internationalShare": raw["internationalShare"],
        "delay": raw["delay"],
        "top": raw["destinations"][:3],
        "nationalities": raw["nationalities"],
        "languages": raw["languages"],
        "evidenceCount": len(raw["flightIds"]),
    }


def _evidence(
    screen: dict[str, Any],
    flights: list[dict[str, Any]],
    queue: dict[str, Any] | None,
    now: datetime,
    settings: Settings,
) -> list[EvidencePoint]:
    points: list[EvidencePoint] = []
    ranked = sorted(
        flights,
        key=lambda flight: parse_time(flight.get("updated")) or datetime.min,
        reverse=True,
    )[:6]
    for flight in ranked:
        observed = parse_time(flight.get("updated")) or now
        points.append(
            EvidencePoint(
                label=f"AODB leg {flight.get('airline')}{flight.get('flight_no')} · gate {flight.get('gate')}",
                source="AODB",
                observed_at=observed,
                value={
                    "pax": flight.get("pax"),
                    "status": flight.get("status"),
                    "destination": flight.get("destination"),
                },
            )
        )
    if flights:
        ids = [str(flight.get("flight_id")) for flight in flights]
        placeholders = ",".join("?" for _ in ids)
        event = db.query_one(
            f"SELECT * FROM flight_events WHERE flight_id IN ({placeholders}) ORDER BY ts DESC LIMIT 1",
            ids,
        )
        if event:
            points.append(
                EvidencePoint(
                    label=f"AIDX {event['type']} · {event['field']}",
                    source="IATA AIDX",
                    observed_at=parse_time(event["ts"]) or now,
                    value={"old": event["old"], "new": event["new"]},
                )
            )
    points.append(
        EvidencePoint(
            label="AODB feed heartbeat",
            source="AODB",
            observed_at=feed_last("aodb", now),
            value=settings.flight_source,
        )
    )
    if queue:
        points.append(
            EvidencePoint(
                label=f"ACRIS queue {queue.get('checkpoint')} · {queue.get('zone_id')}",
                source="ACRIS",
                observed_at=parse_time(queue.get("ts")) or now,
                value={"queue": queue.get("queue_len"), "waitMin": queue.get("wait_min")},
            )
        )
    points.append(
        EvidencePoint(
            label=f"Screen heartbeat {screen['id']}",
            source="Platform screen telemetry",
            observed_at=parse_time(screen.get("last_seen")) or now,
            value={"status": screen.get("status"), "latencyMs": screen.get("latency_ms")},
        )
    )
    for point in points:
        point.freshness_seconds = max(0, int((now - point.observed_at).total_seconds()))
    return points


def _confidence(
    raw: dict[str, Any], evidence: list[EvidencePoint], settings: Settings, now: datetime
) -> float:
    if raw["crowd"] <= 0:
        return 0.2
    fresh = 0
    for point in evidence:
        threshold = settings.aodb_fresh_seconds if point.source == "AODB" else settings.feed_fresh_seconds
        if (now - point.observed_at).total_seconds() <= threshold:
            fresh += 1
    freshness = fresh / max(1, len(evidence))
    coverage = raw.get("attributeCoverage", 0.0)
    return round(max(0.2, min(0.96, 0.35 + 0.4 * freshness + 0.2 * coverage)), 3)


def parse_queue(row: dict | None) -> dict | None:
    return dict(row) if row else None


def _iso(value: datetime) -> str:
    return value.astimezone().isoformat().replace("+00:00", "Z") if value.tzinfo else value.isoformat() + "Z"