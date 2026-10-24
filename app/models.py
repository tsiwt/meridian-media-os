"""Canonical internal model.

Adapters translate AODB, AIDX and ACRIS payloads into these objects.  Business
logic never imports an adapter and never reads a source-specific field name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class Flight:
    flight_id: str
    linked_flight_id: str
    direction: str
    airline_iata: str
    airline_icao: str
    flight_number: str
    callsign: str
    service_type: str
    flight_nature: str
    origin: str
    destination: str
    via: str
    terminal: str
    scheduled: datetime | None
    estimated: datetime | None
    estimated_landing: datetime | None
    estimated_takeoff: datetime | None
    actual_landing: datetime | None
    actual_takeoff: datetime | None
    aibt: datetime | None
    aobt: datetime | None
    tobt: datetime | None
    tsat: datetime | None
    stand: str
    gate: str
    checkin_counters: str
    baggage_belt: str
    aircraft_reg: str
    aircraft_type_icao: str
    seats: int
    pax_total: int
    status: str
    delay_codes: str
    codeshares: str
    handler: str
    last_update: datetime | None
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def is_departure(self) -> bool:
        return self.direction == "D"

    @property
    def is_international(self) -> bool:
        return self.flight_nature == "I"

    @property
    def delay_minutes(self) -> int:
        base = self.scheduled
        actual = self.estimated or self.estimated_takeoff
        if not base or not actual:
            return 0
        return max(0, int((actual - base).total_seconds() // 60))

    def to_row(self) -> dict[str, Any]:
        return {
            "flight_id": str(self.flight_id),
            "linked_id": str(self.linked_flight_id),
            "direction": self.direction,
            "airline": self.airline_iata,
            "flight_no": self.flight_number,
            "callsign": self.callsign,
            "service_type": self.service_type,
            "nature": self.flight_nature,
            "origin": self.origin,
            "destination": self.destination,
            "via": self.via,
            "terminal": self.terminal,
            "std": iso(self.scheduled),
            "eta": iso(self.estimated),
            "etd": iso(self.estimated),
            "eldt": iso(self.estimated_landing),
            "etot": iso(self.estimated_takeoff),
            "aldt": iso(self.actual_landing),
            "atot": iso(self.actual_takeoff),
            "aibt": iso(self.aibt),
            "aobt": iso(self.aobt),
            "tobt": iso(self.tobt),
            "tsat": iso(self.tsat),
            "stand": self.stand,
            "gate": self.gate,
            "counters": self.checkin_counters,
            "belt": self.baggage_belt,
            "registration": self.aircraft_reg,
            "aircraft_type": self.aircraft_type_icao,
            "seats": self.seats,
            "pax": self.pax_total,
            "status": self.status,
            "delay_codes": self.delay_codes,
            "codeshares": self.codeshares,
            "handler": self.handler,
            "updated": iso(self.last_update),
            "profile_json": self.profile,
        }


@dataclass
class FlightEvent:
    flight_id: str
    event_type: str
    field: str
    old_value: str
    new_value: str
    source: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "flight_id": str(self.flight_id),
            "type": self.event_type,
            "field": self.field,
            "old": self.old_value,
            "new": self.new_value,
            "source": self.source,
            "ts": iso(self.occurred_at),
            "payload_json": self.payload,
        }


@dataclass
class QueueMeasurement:
    zone_id: str
    checkpoint_id: str
    queue_length: int
    wait_minutes: float
    measured_at: datetime
    source: str = "acris"

    def to_row(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "checkpoint": self.checkpoint_id,
            "queue_len": self.queue_length,
            "wait_min": self.wait_minutes,
            "ts": iso(self.measured_at),
            "source": self.source,
        }


@dataclass
class EvidencePoint:
    label: str
    source: str
    observed_at: datetime
    value: Any
    freshness_seconds: int = 0

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        reference = now or utc_now()
        age = max(0, int((reference - self.observed_at).total_seconds()))
        return {
            "label": self.label,
            "source": self.source,
            "observedAt": iso(self.observed_at),
            "ageSeconds": age,
            "value": self.value,
        }


@dataclass
class CrowdProfile:
    zone_id: str
    screen_id: str
    window_start: datetime
    window_end: datetime
    crowd_size: int
    international_share: float
    median_dwell_minutes: int
    delay_minutes: int
    shares: dict[str, float]
    top_destinations: list[dict[str, Any]]
    top_nationalities: list[dict[str, Any]]
    languages: list[dict[str, Any]]
    flights: list[str]
    evidence: list[EvidencePoint]
    confidence: float = 0.8
    mode: str = "measured"

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        return {
            "zoneId": self.zone_id,
            "screenId": self.screen_id,
            "windowStart": iso(self.window_start),
            "windowEnd": iso(self.window_end),
            "crowdSize": self.crowd_size,
            "internationalShare": round(self.international_share, 3),
            "medianDwellMinutes": self.median_dwell_minutes,
            "delayMinutes": self.delay_minutes,
            "shares": {key: round(value, 3) for key, value in self.shares.items()},
            "topDestinations": self.top_destinations,
            "topNationalities": self.top_nationalities,
            "languages": self.languages,
            "flights": self.flights,
            "confidence": round(self.confidence, 3),
            "mode": self.mode,
            "evidence": [point.to_dict(now) for point in self.evidence],
        }


@dataclass
class Candidate:
    campaign_id: str
    name: str
    advertiser: str
    creative_id: str
    ai_score: float
    final_score: float
    audience_match: float
    boost: float
    passed: bool
    reasons: list[str] = field(default_factory=list)
    rejected_by: str = ""
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaignId": self.campaign_id,
            "name": self.name,
            "advertiser": self.advertiser,
            "creativeId": self.creative_id,
            "aiScore": round(self.ai_score, 3),
            "finalScore": round(self.final_score, 3),
            "audienceMatch": round(self.audience_match, 3),
            "boost": round(self.boost, 3),
            "passed": self.passed,
            "reasons": self.reasons,
            "rejectedBy": self.rejected_by,
            "category": self.category,
        }


@dataclass
class Decision:
    screen_id: str
    zone_id: str
    decided_at: datetime
    profile: CrowdProfile
    candidates: list[Candidate]
    winner: Candidate | None
    reason: str
    fallback: bool
    ai_model: str
    validation: dict[str, Any]
    evidence: list[dict[str, Any]]
    play_ms: int = 15000

    def to_dict(self, now: datetime | None = None) -> dict[str, Any]:
        return {
            "screenId": self.screen_id,
            "zoneId": self.zone_id,
            "decidedAt": iso(self.decided_at),
            "profile": self.profile.to_dict(now),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "winner": self.winner.to_dict() if self.winner else None,
            "winnerId": self.winner.campaign_id if self.winner else "",
            "winnerScore": round(self.winner.final_score, 6) if self.winner else 0.0,
            "reason": self.reason,
            "fallback": self.fallback,
            "aiModel": self.ai_model,
            "validation": self.validation,
            "evidence": self.evidence,
            "playMs": self.play_ms,
        }


@dataclass
class Promo:
    promo_id: str
    campaign_id: str
    code: str
    flight_id: str
    valid_from: datetime | None
    valid_until: datetime | None
    max_uses: int
    uses: int
    parent_code: str
    status: str
    label: str
    value: str

    def is_live(self, now: datetime) -> bool:
        if self.status != "active":
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        return self.uses < self.max_uses


class FlightSource(Protocol):
    def stream(self) -> Iterable[FlightEvent]:
        """Yield canonical flight events from the source."""

    def snapshot(self) -> Iterable[Flight]:
        """Return the initial canonical snapshot."""


class QueueSource(Protocol):
    def measurements(self) -> Iterable[QueueMeasurement]:
        """Yield canonical queue measurements."""


