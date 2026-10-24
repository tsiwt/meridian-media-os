"""Deterministic campaign filtering and scoring.

The AI provider proposes a ranking, but every score is recomputed here from
logged inputs.  A candidate is ``passed`` only when all hard rules succeed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from .. import db
from ..models import Candidate, CrowdProfile, parse_time

SEGMENT_KEYS = [
    "international", "domestic", "holiday", "business", "vfr", "student",
    "religious", "family", "couple", "solo", "group", "young", "senior",
    "luxury", "value", "gourmet", "wellness", "tech", "beach", "shopper",
]


def load_campaigns(now: datetime) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT c.*, a.name AS advertiser_name, a.kind AS advertiser_kind, "
        "cr.status AS creative_status, cr.name AS creative_name, cr.category AS creative_category "
        "FROM campaigns c JOIN advertisers a ON a.id = c.advertiser_id "
        "JOIN creatives cr ON cr.id = c.creative_id "
        "WHERE c.status IN ('approved','pending','paused') ORDER BY c.id"
    )
    campaigns = []
    for row in rows:
        campaign = dict(row)
        for key in ("segments", "filters", "placement", "triggers", "daypart"):
            campaign[key] = db.json_loads(row[f"{key}_json"], {})
        campaign["spend"] = float(row["spend"] or 0)
        campaign["today_spend"] = _today_spend(campaign["id"], now)
        campaign["segment_conversion"] = _segment_conversion(campaign["id"])
        campaigns.append(campaign)
    return campaigns


def _segment_conversion(campaign_id: str) -> dict[str, float]:
    rows = db.query(
        "SELECT segment, SUM(redemptions) AS redemptions, SUM(impressions) AS impressions "
        "FROM segment_stats WHERE campaign_id = ? GROUP BY segment",
        (campaign_id,),
    )
    result = {}
    for row in rows:
        impressions = float(row["impressions"] or 0)
        result[row["segment"]] = float(row["redemptions"] or 0) / impressions if impressions else 0.0
    return result


def _learning(campaign: dict[str, Any], shares: dict[str, float]) -> float:
    conversions = campaign.get("segment_conversion") or {}
    weights = campaign.get("segments") or {}
    if not conversions or not weights:
        return 0.0
    total = sum(float(weight) for weight in weights.values()) or 1.0
    expected = 0.0
    for segment, weight in weights.items():
        expected += float(weight) * float(conversions.get(segment, 0.0))
    expected /= total
    return round(min(0.08, expected * 2.4), 6)


def _today_spend(campaign_id: str, now: datetime) -> float:
    row = db.query_one(
        "SELECT COALESCE(SUM(spend),0) AS spend FROM daily_stats WHERE campaign_id = ? AND day = ?",
        (campaign_id, now.date().isoformat()),
    )
    return float(row["spend"]) if row else 0.0


def evaluate(
    profile: CrowdProfile,
    screen: dict[str, Any],
    now: datetime,
    campaigns: list[dict[str, Any]],
    rules: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> list[Candidate]:
    context = context or {}
    candidates: list[Candidate] = []
    for campaign in campaigns:
        passed, reason, code = _hard_filter(campaign, profile, screen, now, rules, context)
        match = _audience_match(campaign["segments"], profile.shares)
        boost, boost_reasons, trigger_hit = _boost(campaign, profile, screen, now, rules, context, match)
        exploration = _exploration(campaign["id"], screen["id"], profile.window_start, rules)
        if exploration:
            boost += 0.08
            boost_reasons.append("Exploration slot (5%)")
        context_fit = 1.0 if trigger_hit else (0.72 if campaign.get("priority", 0) >= 2 else 0.5)
        bid_norm = min(1.0, float(campaign.get("bid") or 0) / 5.0)
        priority_norm = min(1.0, float(campaign.get("priority") or 0) / 2.0)
        ai_score = 0.72 * match + 0.14 * context_fit + 0.08 * bid_norm + 0.06 * priority_norm
        final = min(1.0, ai_score * boost)
        reasons = [f"Audience match {round(match * 100)}%"] + boost_reasons
        if not passed:
            reasons.append(reason)
        candidates.append(
            Candidate(
                campaign_id=campaign["id"],
                name=campaign["name"],
                advertiser=campaign["advertiser_name"],
                creative_id=campaign["creative_id"],
                ai_score=round(ai_score, 6),
                final_score=round(final, 6),
                audience_match=round(match, 6),
                boost=round(boost, 6),
                passed=passed,
                reasons=reasons,
                rejected_by=code,
                category=campaign.get("category", ""),
            )
        )
    candidates.sort(key=lambda c: (c.passed, c.final_score, c.campaign_id), reverse=True)
    return candidates


def _hard_filter(
    campaign: dict[str, Any],
    profile: CrowdProfile,
    screen: dict[str, Any],
    now: datetime,
    rules: dict[str, Any],
    context: dict[str, Any],
) -> tuple[bool, str, str]:
    if campaign["status"] != "approved":
        return False, f"Campaign status {campaign['status']} is not approved", "status"
    if campaign.get("creative_status") != "approved":
        return False, "Creative is awaiting brand-safety approval", "creative_approval"
    start = parse_time(campaign.get("start"))
    end = parse_time(campaign.get("end"))
    if (start and now < start) or (end and now > end):
        return False, "Outside campaign schedule", "schedule"
    if not _daypart_ok(campaign.get("daypart") or {}, now):
        return False, "Outside daypart", "daypart"
    filters = campaign.get("filters") or {}
    if filters.get("internationalOnly") and profile.international_share < 0.5:
        return False, "Requires an international audience", "domestic"
    if filters.get("domesticOnly") and profile.international_share >= 0.5:
        return False, "Requires a domestic audience", "international"
    destinations = filters.get("destinations") or []
    if destinations:
        observed = {item["code"] for item in profile.top_destinations} | set(context.get("destinations", []))
        if not observed.intersection(destinations):
            return False, "Destination filter not met", "destination"
    if profile.median_dwell_minutes < int(filters.get("minDwell") or 0):
        return False, "Dwell below campaign minimum", "dwell"
    if profile.crowd_size < int(filters.get("minCrowd") or 0):
        return False, "Crowd below campaign minimum", "crowd"
    airline = filters.get("airline")
    if airline and airline not in context.get("airlines", []):
        return False, f"Requires {airline} flights in the catchment", "airline"
    if not _placement_ok(campaign.get("placement") or {}, screen):
        return False, "Screen is outside the campaign placement", "placement"
    budget = float(campaign.get("budget") or 0)
    if budget and float(campaign.get("spend") or 0) >= budget:
        return False, "Campaign budget exhausted", "budget"
    daily_cap = float(campaign.get("daily_cap") or 0)
    if daily_cap and float(campaign.get("today_spend") or 0) >= daily_cap:
        return False, "Daily cap reached", "daily_cap"
    return True, "All hard rules passed", ""


def _audience_match(weights: dict[str, float], shares: dict[str, float]) -> float:
    total = 0.0
    matched = 0.0
    for key, weight in weights.items():
        normalized = _segment_value(key, shares)
        total += float(weight)
        matched += float(weight) * normalized
    return max(0.0, min(1.0, matched / total)) if total else 0.0


def _segment_value(key: str, shares: dict[str, float]) -> float:
    if key in shares:
        return float(shares[key])
    aliases = {
        "shopper": "shopper",
        "luxury": "luxury",
        "beach": "beach",
    }
    return float(shares.get(aliases.get(key, key), 0.0))


def _boost(
    campaign: dict[str, Any],
    profile: CrowdProfile,
    screen: dict[str, Any],
    now: datetime,
    rules: dict[str, Any],
    context: dict[str, Any],
    match: float,
) -> tuple[float, list[str], bool]:
    triggers = campaign.get("triggers") or {}
    boost = 1.0
    reasons: list[str] = []
    hit = False
    delay_trigger = int(triggers.get("delayOver") or 0)
    if delay_trigger and profile.delay_minutes >= delay_trigger:
        boost *= 1.4
        hit = True
        reasons.append(f"Delay {profile.delay_minutes} min ≥ {delay_trigger} min trigger ×1.4")
    if triggers.get("gateChange") and context.get("gate_change"):
        boost *= 1.15
        hit = True
        reasons.append("Gate-change trigger ×1.15")
    if triggers.get("boarding") and context.get("boarding"):
        boost *= 1.12
        hit = True
        reasons.append("Boarding-window trigger ×1.12")
    if triggers.get("festival") and context.get("festival"):
        boost *= 1.15
        hit = True
        reasons.append("Holiday-period trigger ×1.15")
    airline = (campaign.get("filters") or {}).get("airline")
    if airline and airline in context.get("airlines", []):
        boost *= 1.2
        hit = True
        reasons.append(f"Airline priority for {airline} in its own boarding window ×1.2")
    if float(campaign.get("priority") or 0) >= 2 and match >= 0.5:
        boost *= 1.05
        reasons.append("Premium inventory priority ×1.05")
    return min(1.7, boost), reasons, hit


def _exploration(
    campaign_id: str, screen_id: str, window: datetime, rules: dict[str, Any]
) -> bool:
    pct = float(rules.get("explorationPct") or 0)
    if pct <= 0:
        return False
    digest = hashlib.sha256(f"{campaign_id}:{screen_id}:{window.isoformat()}".encode()).hexdigest()
    return int(digest[:6], 16) % 10000 < int(pct * 100)


def _placement_ok(placement: dict[str, Any], screen: dict[str, Any]) -> bool:
    zones = placement.get("zones") or []
    gates = placement.get("gates") or []
    screens = placement.get("screens") or []
    if not zones and not gates and not screens:
        return True
    if "*" in zones or screen["zone_id"] in zones:
        return True
    if gates and set(map(str, gates)).intersection(set(map(str, screen.get("nearest_gates", [])))):
        return True
    if screens and screen["id"] in screens:
        return True
    return False


def _daypart_ok(daypart: dict[str, Any], now: datetime) -> bool:
    start = int(daypart.get("startHour", 0))
    end = int(daypart.get("endHour", 24))
    if start == 0 and end == 24:
        return True
    return start <= now.hour < end


def audit_score(candidate: Candidate, campaign: dict[str, Any], profile: CrowdProfile, screen: dict[str, Any], now: datetime, rules: dict[str, Any], context: dict[str, Any]) -> float:
    """Recompute one candidate's score for the deterministic evidence check."""
    match = _audience_match(campaign["segments"], profile.shares)
    boost, _, trigger_hit = _boost(campaign, profile, screen, now, rules, context, match)
    if _exploration(campaign["id"], screen["id"], profile.window_start, rules):
        boost += 0.08
    context_fit = 1.0 if trigger_hit else (0.72 if campaign.get("priority", 0) >= 2 else 0.5)
    bid_norm = min(1.0, float(campaign.get("bid") or 0) / 5.0)
    priority_norm = min(1.0, float(campaign.get("priority") or 0) / 2.0)
    ai_score = 0.72 * match + 0.14 * context_fit + 0.08 * bid_norm + 0.06 * priority_norm
    return round(min(1.0, ai_score * boost), 6)