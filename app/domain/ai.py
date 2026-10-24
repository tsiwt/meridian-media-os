"""Pluggable AI provider.

Default: a deterministic, offline template provider.  It proposes a ranking and
citations, but the decision pipeline validates every claim against recorded
feeds before anything reaches a screen.  A real LLM can be plugged in by
implementing ``AIProvider``; the default never needs an API key.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Protocol

from ..config import Settings
from ..models import Candidate, CrowdProfile


class AIProvider(Protocol):
    name: str

    def rank(
        self, profile: CrowdProfile, candidates: list[Candidate], context: dict
    ) -> dict[str, Any]: ...

    def creative(self, brief: str, language: str) -> dict[str, Any]: ...


class MockAIProvider:
    """Offline evidence-aware ranker + template creative assistant."""

    def __init__(self, settings: Settings) -> None:
        self.name = settings.ai_model
        self.settings = settings

    def rank(
        self, profile: CrowdProfile, candidates: list[Candidate], context: dict
    ) -> dict[str, Any]:
        eligible = [candidate for candidate in candidates if candidate.passed]
        if not eligible:
            return {
                "model": self.name,
                "proposedCampaignId": None,
                "proposedScore": 0.0,
                "confidence": 0.0,
                "citations": [],
                "reason": "No campaign passed the hard rules.",
            }
        # The provider's own ordering is intentionally simple and auditable:
        # strongest segment overlap first, then bid.  It does not invent facts.
        ranked = sorted(
            eligible,
            key=lambda candidate: (candidate.audience_match, candidate.final_score, candidate.campaign_id),
            reverse=True,
        )
        winner = ranked[0]
        citations = [
            {"metric": "crowdSize", "value": profile.crowd_size, "source": "AODB"},
            {"metric": "internationalShare", "value": round(profile.international_share, 3), "source": "AODB"},
            {"metric": "medianDwellMinutes", "value": profile.median_dwell_minutes, "source": "AODB"},
            {"metric": "delayMinutes", "value": profile.delay_minutes, "source": "AODB"},
            {"metric": "zoneQueue", "value": (context.get("queue") or {}).get("queue_len", 0), "source": "ACRIS"},
        ]
        confidence = round(min(0.97, 0.55 + winner.audience_match * 0.35 + (0.08 if profile.delay_minutes >= 30 else 0)), 3)
        return {
            "model": self.name,
            "proposedCampaignId": winner.campaign_id,
            "proposedScore": winner.final_score,
            "confidence": confidence,
            "citations": citations,
            "alternatives": [candidate.campaign_id for candidate in ranked[1:4]],
            "reason": (
                f"{winner.name} best matches the measured crowd "
                f"({round(winner.audience_match * 100)}% weighted segment fit)."
            ),
        }

    def creative(self, brief: str, language: str) -> dict[str, Any]:
        text = (brief or "").strip()[:240]
        lowered = text.lower()
        theme = "aurora"
        if any(word in lowered for word in ("coffee", "café", "cafe", "food", "sweet")):
            theme = "wave"
        elif any(word in lowered for word in ("tech", "sim", "charger", "digital")):
            theme = "grid"
        elif any(word in lowered for word in ("luxury", "watch", "fashion", "perfume")):
            theme = "lumen"
        elif any(word in lowered for word in ("book", "guide", "market")):
            theme = "paper"
        seed = int(hashlib.sha256(text.encode()).hexdigest()[:6], 16)
        palettes = {
            "aurora": ["#38e8c8", "#8b7bff"],
            "wave": ["#ffb454", "#ff647c"],
            "grid": ["#60a5fa", "#38e8c8"],
            "lumen": ["#f4d35e", "#e879f9"],
            "paper": ["#a88beb", "#38e8c8"],
        }
        subject = _subject(text)
        if language == "zh":
            headline = f"{subject} · 机场限定"
            body = f"{text or '为途经 MQI 的旅客准备'}。现在在登机口附近即可领取。"
            cta = "立即领取"
        else:
            headline = f"{subject} · airport exclusive"
            body = f"{text or 'Made for travellers passing through MQI.'} Available near your gate now."
            cta = "Claim at the gate"
        return {
            "provider": self.name,
            "brief": text,
            "template": theme,
            "colors": palettes[theme],
            "language": language,
            "headline": headline,
            "body": body,
            "cta": cta,
            "variant": seed % 3,
            "offline": True,
        }


def _subject(text: str) -> str:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9'’\-]+", text)
    meaningful = [word for word in words if word.lower() not in {
        "the", "and", "for", "with", "off", "get", "our", "your", "a", "an", "to", "of",
    }]
    if not meaningful:
        return "A little more journey"
    return " ".join(meaningful[:4]).title()


def build_provider(settings: Settings) -> AIProvider:
    """Return the configured provider.

    ``AI_PROVIDER=openai`` is a documented extension point.  Without a key the
    app deliberately stays on the mock provider so the demo runs offline; the
    feed health/README surfaces the active provider.
    """
    return MockAIProvider(settings)