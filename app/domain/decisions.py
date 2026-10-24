"""Evidence-first decision pipeline.

AI proposes → deterministic validation → execute or fall back.  Every decision
stores the crowd profile, all candidates and scores, the winning reason, and
the evidence trail, so any role can audit why an ad played.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..config import Settings
from ..models import Candidate, CrowdProfile, Decision, iso, parse_time
from . import scoring
from .ai import build_provider
from .profile import build_profile, screen_context

TRUSTED_SOURCES = {"AODB", "IATA AIDX", "ACRIS", "AODB feed status", "Platform screen telemetry", "Platform"}


def load_rules() -> dict[str, Any]:
    rules = {}
    for row in db.query("SELECT key, value_json FROM rules"):
        rules[row["key"]] = db.json_loads(row["value_json"], {})
    return rules


def decide(
    screen_id: str,
    now: datetime,
    settings: Settings,
    rules: dict[str, Any] | None = None,
    persist: bool = True,
    campaigns: list[dict[str, Any]] | None = None,
) -> Decision | None:
    screen = screen_context(screen_id)
    if not screen:
        return None
    rules = rules or load_rules()
    queue_row = db.query_one(
        "SELECT * FROM queues WHERE zone_id = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
        (screen["zone_id"], iso(now)),
    )
    queue = dict(queue_row) if queue_row else None
    profile = build_profile(screen, now, settings, queue)
    context = _context(profile, screen, now, queue)
    campaigns = campaigns if campaigns is not None else scoring.load_campaigns(now)
    candidates = scoring.evaluate(profile, screen, now, campaigns, rules, context)
    candidates = _apply_business_rules(candidates, screen, now, rules)
    provider = build_provider(settings)
    ai = provider.rank(profile, candidates, {**context, "queue": queue or {}})
    winner, validation, fallback, reason = _validate_and_choose(
        ai, candidates, profile, screen, now, rules, context, campaigns, settings
    )
    decision = Decision(
        screen_id=screen["id"],
        zone_id=screen["zone_id"],
        decided_at=now,
        profile=profile,
        candidates=candidates,
        winner=winner,
        reason=reason,
        fallback=fallback,
        ai_model=getattr(provider, "name", settings.ai_model),
        validation=validation,
        evidence=[point.to_dict(now) for point in profile.evidence],
    )
    if persist:
        _persist(decision, now, campaigns, screen, settings)
    return decision


def _context(
    profile: CrowdProfile, screen: dict[str, Any], now: datetime, queue: dict | None
) -> dict[str, Any]:
    flights: list[dict] = []
    if profile.flights:
        placeholders = ",".join("?" for _ in profile.flights)
        rows = db.query(
            f"SELECT * FROM flights WHERE flight_id IN ({placeholders})", profile.flights
        )
        flights = [dict(row) for row in rows]
    airlines = sorted({flight["airline"] for flight in flights})
    destinations = sorted({flight["destination"] for flight in flights})
    boarding = any(
        flight["status"] in {"BOD", "GCL"}
        or (
            parse_time(flight["std"]) is not None
            and parse_time(flight["std"]) - timedelta(minutes=40) <= now <= parse_time(flight["std"])
        )
        for flight in flights
    )
    gate_change = False
    if profile.flights:
        placeholders = ",".join("?" for _ in profile.flights)
        row = db.query_one(
            f"SELECT COUNT(*) AS c FROM flight_events WHERE field = 'gate' "
            f"AND flight_id IN ({placeholders}) AND ts >= ?",
            (*profile.flights, iso(now - timedelta(minutes=20))),
        )
        gate_change = bool(row and row["c"] > 0)
    return {
        "airlines": airlines,
        "destinations": destinations,
        "boarding": boarding,
        "gate_change": gate_change,
        "festival": now.date().isoformat() in {"2026-10-24", "2026-10-25", "2026-10-26"},
        "queue": queue or {},
        "flightCount": len(flights),
    }


def _apply_business_rules(
    candidates: list[Candidate], screen: dict[str, Any], now: datetime, rules: dict[str, Any]
) -> list[Candidate]:
    separation = int(rules.get("competitorSeparationMin") or 0)
    freq_cap = int(rules.get("frequencyCapMin") or 0)
    recent_rows = db.query(
        "SELECT c.category, i.campaign_id FROM impressions i JOIN campaigns c "
        "ON c.id = i.campaign_id WHERE i.screen_id = ? AND i.ts >= ?",
        (screen["id"], iso(now - timedelta(minutes=max(separation, freq_cap)))),
    )
    recent_categories = {row["category"] for row in recent_rows if row["category"] not in {"house", "airline"}}
    recent_counts: dict[str, int] = {}
    for row in recent_rows:
        recent_counts[row["campaign_id"]] = recent_counts.get(row["campaign_id"], 0) + 1
    originally_passed = [candidate for candidate in candidates if candidate.passed]
    for candidate in candidates:
        if not candidate.passed:
            continue
        if freq_cap and recent_counts.get(candidate.campaign_id, 0) >= 1:
            candidate.passed = False
            candidate.rejected_by = "frequency_cap"
            candidate.reasons.append(f"Frequency cap: played on this screen in the last {freq_cap} min")
            continue
        if separation and candidate.category in recent_categories:
            candidate.passed = False
            candidate.rejected_by = "competitor_separation"
            candidate.reasons.append(
                f"Competitor separation: another {candidate.category} ad played within {separation} min"
            )
    if originally_passed and not any(candidate.passed for candidate in candidates):
        relaxed = max(originally_passed, key=lambda candidate: candidate.final_score)
        relaxed.passed = True
        relaxed.rejected_by = ""
        relaxed.reasons.append("Business guard relaxed: no alternative campaign was eligible for this slot")
    candidates.sort(key=lambda c: (c.passed, c.final_score, c.campaign_id), reverse=True)
    return candidates


def _validate_and_choose(
    ai: dict[str, Any],
    candidates: list[Candidate],
    profile: CrowdProfile,
    screen: dict[str, Any],
    now: datetime,
    rules: dict[str, Any],
    context: dict[str, Any],
    campaigns: list[dict[str, Any]],
    settings: Settings,
) -> tuple[Candidate | None, dict[str, Any], bool, str]:
    by_id = {campaign["id"]: campaign for campaign in campaigns}
    passed = [candidate for candidate in candidates if candidate.passed]
    proposed = next((c for c in passed if c.campaign_id == ai.get("proposedCampaignId")), None)
    checks: list[dict[str, Any]] = []
    citation_ok, citation_reason = _validate_citations(ai.get("citations") or [], profile, context, now, settings)
    checks.append({"check": "citations_traceable", "ok": citation_ok, "detail": citation_reason})
    checks.append(
        {
            "check": "hard_rules",
            "ok": proposed is not None,
            "detail": "Proposed campaign passed all deterministic hard rules" if proposed else "AI winner failed hard rules or was filtered",
        }
    )
    score_ok = False
    expected = 0.0
    recomputed = 0.0
    if proposed:
        campaign = by_id[proposed.campaign_id]
        expected = proposed.final_score
        recomputed = scoring.audit_score(proposed, campaign, profile, screen, now, rules, context)
        score_ok = abs(expected - recomputed) < 1e-6
    checks.append(
        {"check": "score_reproducible", "ok": score_ok, "expected": expected, "recomputed": recomputed}
    )
    confidence = float(ai.get("confidence") or 0)
    min_conf = float(rules.get("minEvidenceConfidence") or 0.6)
    checks.append(
        {
            "check": "confidence",
            "ok": confidence >= min_conf,
            "confidence": confidence,
            "minimum": min_conf,
        }
    )
    validation_ok = all(check["ok"] for check in checks)
    validation = {
        "aiModel": ai.get("model"),
        "aiProposed": ai.get("proposedCampaignId"),
        "aiReason": ai.get("reason"),
        "confidence": confidence,
        "checks": checks,
        "passed": validation_ok,
        "executed": "",
    }
    if validation_ok and proposed:
        validation["executed"] = "ai"
        reason = (
            f"{proposed.name} won: {round(proposed.audience_match * 100)}% audience match, "
            f"score {proposed.final_score:.2f}, {proposed.boost:.2f}× boost. "
            + (proposed.reasons[1] if len(proposed.reasons) > 1 else "All hard rules passed.")
        )
        return proposed, validation, False, reason
    if passed:
        winner = passed[0]
        validation["executed"] = "rule_default"
        failed = [check["check"] for check in checks if not check["ok"]]
        reason = (
            f"AI choice rejected ({', '.join(failed)}); rule-based default "
            f"{winner.name} with score {winner.final_score:.2f}."
        )
        return winner, validation, True, reason
    house = _house_candidate(now, campaigns)
    validation["executed"] = "house_fallback"
    validation["passed"] = False
    if house:
        return house, validation, True, "No campaign passed the rules; playing house campaign CMP-18."
    return None, validation, True, "No campaign passed the rules and no house creative is available."


def _validate_citations(
    citations: list[dict],
    profile: CrowdProfile,
    context: dict[str, Any],
    now: datetime,
    settings: Settings,
) -> tuple[bool, str]:
    if not citations:
        return False, "AI provided no citations"
    sources = {point.source for point in profile.evidence}
    observed = {
        "crowdSize": profile.crowd_size,
        "internationalShare": round(profile.international_share, 3),
        "medianDwellMinutes": profile.median_dwell_minutes,
        "delayMinutes": profile.delay_minutes,
        "zoneQueue": (context.get("queue") or {}).get("queue_len", 0),
    }
    for citation in citations:
        source = citation.get("source")
        metric = citation.get("metric")
        if source not in TRUSTED_SOURCES or source not in sources:
            return False, f"Citation source {source} is not present in a trusted feed"
        if metric in observed:
            value = citation.get("value")
            if isinstance(observed[metric], int) and isinstance(value, (int, float)):
                if abs(float(value) - float(observed[metric])) > 0.01:
                    return False, f"Citation {metric} does not match the recorded profile"
            elif str(value) != str(observed[metric]):
                return False, f"Citation {metric} does not match the recorded profile"
    for source, threshold in (("AODB", settings.aodb_fresh_seconds), ("ACRIS", settings.feed_fresh_seconds)):
        source_points = [point for point in profile.evidence if point.source == source]
        if not source_points:
            return False, f"No {source} evidence was recorded for this decision"
        if not any((now - point.observed_at).total_seconds() <= threshold for point in source_points):
            return False, f"{source} evidence is stale (older than {threshold}s)"
    return True, f"{len(citations)} citations trace to fresh AODB/ACRIS evidence"


def _house_candidate(now: datetime, campaigns: list[dict[str, Any]]) -> Candidate | None:
    house = next((campaign for campaign in campaigns if campaign["id"] == "CMP-18"), None)
    if not house:
        return None
    return Candidate(
        campaign_id=house["id"],
        name=house["name"],
        advertiser=house.get("advertiser_name", "Meridian"),
        creative_id=house["creative_id"],
        ai_score=0.1,
        final_score=0.1,
        audience_match=0.0,
        boost=1.0,
        passed=True,
        reasons=["House fallback: flight information and airport map"],
        category="house",
    )


def _persist(
    decision: Decision,
    now: datetime,
    campaigns: list[dict[str, Any]],
    screen: dict[str, Any],
    settings: Settings,
) -> None:
    candidates_json = [candidate.to_dict() for candidate in decision.candidates]
    winner = decision.winner
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO decisions(screen_id, zone_id, ts, profile_json, candidates_json, winner_id, "
            "winner_score, reason, evidence_json, fallback, ai_model, validation_json, play_ms) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision.screen_id,
                decision.zone_id,
                iso(now),
                db.json_dumps(decision.profile.to_dict(now)),
                db.json_dumps(candidates_json),
                winner.campaign_id if winner else "",
                winner.final_score if winner else 0.0,
                decision.reason,
                db.json_dumps(decision.evidence),
                1 if decision.fallback else 0,
                decision.ai_model,
                db.json_dumps(decision.validation),
                decision.play_ms,
            ),
        )
        decision_id = cursor.lastrowid
        if not winner:
            return
        impressions = max(1, min(40, decision.profile.crowd_size // 6))
        spend = round(float(_campaign_bid(winner.campaign_id, campaigns)) * impressions / 1000, 4)
        segment = _top_segment(winner.campaign_id, decision.profile, campaigns)
        conn.execute(
            "INSERT INTO impressions(screen_id, campaign_id, ts, decision_id, profile_key) "
            "VALUES (?,?,?,?,?)",
            (decision.screen_id, winner.campaign_id, iso(now), decision_id, segment),
        )
        conn.execute(
            "UPDATE campaigns SET impressions = impressions + ?, spend = spend + ? WHERE id = ?",
            (impressions, spend, winner.campaign_id),
        )
        conn.execute(
            "INSERT INTO daily_stats(campaign_id, day, impressions, scans, redemptions, revenue, spend) "
            "VALUES (?,?,?,0,0,0,?) ON CONFLICT(campaign_id, day) DO UPDATE SET "
            "impressions = impressions + excluded.impressions, spend = spend + excluded.spend",
            (winner.campaign_id, now.date().isoformat(), impressions, spend),
        )
        conn.execute(
            "INSERT INTO segment_stats(campaign_id, segment, impressions, scans, redemptions, revenue) "
            "VALUES (?,?,?,0,0,0) ON CONFLICT(campaign_id, segment) DO UPDATE SET "
            "impressions = impressions + excluded.impressions",
            (winner.campaign_id, segment, impressions),
        )


def _campaign_bid(campaign_id: str, campaigns: list[dict[str, Any]]) -> float:
    campaign = next((item for item in campaigns if item["id"] == campaign_id), None)
    return float(campaign.get("bid", 0)) if campaign else 0.0


def _top_segment(campaign_id: str, profile: CrowdProfile, campaigns: list[dict]) -> str:
    campaign = next((item for item in campaigns if item["id"] == campaign_id), None)
    weights = (campaign or {}).get("segments") or {}
    best = ("unknown", 0.0)
    for segment, weight in weights.items():
        value = float(weight) * float(profile.shares.get(segment, 0.0))
        if value > best[1]:
            best = (segment, value)
    return best[0]


def why(decision_id: int) -> dict[str, Any] | None:
    row = db.query_one("SELECT * FROM decisions WHERE id = ?", (decision_id,))
    if not row:
        return None
    return decision_row(row)


def decision_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "screenId": row["screen_id"],
        "zoneId": row["zone_id"],
        "decidedAt": row["ts"],
        "profile": db.json_loads(row["profile_json"], {}),
        "candidates": db.json_loads(row["candidates_json"], []),
        "winnerId": row["winner_id"],
        "winnerScore": row["winner_score"],
        "reason": row["reason"],
        "evidence": db.json_loads(row["evidence_json"], []),
        "fallback": bool(row["fallback"]),
        "aiModel": row["ai_model"],
        "validation": db.json_loads(row["validation_json"], {}),
        "playMs": row["play_ms"],
    }


def latest_decision(screen_id: str) -> dict[str, Any] | None:
    row = db.query_one(
        "SELECT * FROM decisions WHERE screen_id = ? ORDER BY ts DESC, id DESC LIMIT 1",
        (screen_id,),
    )
    return decision_row(row) if row else None