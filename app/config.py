"""Runtime configuration for Meridian Media OS.

Every value can be overridden with an environment variable so the same image
runs locally, in docker compose and on a hosted playground.  The application is
white-label: product name, airport identity, currency and second language are
configuration, not code.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    return value.strip() if value else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _parse_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime(2026, 10, 24, 13, 55, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def detect_lan_ip() -> str:
    """Return the best LAN address for QR claim links, without external calls."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            candidate = sock.getsockname()[0]
        if candidate and not ipaddress.ip_address(candidate).is_loopback:
            return candidate
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = info[4][0]
            if not ipaddress.ip_address(candidate).is_loopback:
                return candidate
    except OSError:
        pass
    return "127.0.0.1"


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("PORT", 7860))
    db_path: Path = field(
        default_factory=lambda: Path(_env("DB_PATH", str(ROOT / "data" / "meridian.db")))
    )
    product_name: str = field(default_factory=lambda: _env("PRODUCT_NAME", "Meridian Media OS"))
    product_short: str = field(default_factory=lambda: _env("PRODUCT_SHORT", "MMOS"))
    airport_code: str = field(default_factory=lambda: _env("AIRPORT_CODE", "MQI"))
    airport_name: str = field(
        default_factory=lambda: _env("AIRPORT_NAME", "Meridian International Airport")
    )
    currency: str = field(default_factory=lambda: _env("CURRENCY", "EUR"))
    locale: str = field(default_factory=lambda: _env("LOCALE", "en"))
    second_language: str = field(default_factory=lambda: _env("SECOND_LANGUAGE", "zh"))
    sim_start: datetime = field(
        default_factory=lambda: _parse_start(_env("SIM_START", "2026-10-24T13:55:00Z"))
    )
    sim_speed: float = field(default_factory=lambda: _env_float("SIM_SPEED", 1.0))
    sim_autoplay: bool = field(default_factory=lambda: _env("SIM_AUTOPLAY", "1") == "1")
    seed: int = field(default_factory=lambda: _env_int("SEED", 1024))
    seed_on_boot: bool = field(default_factory=lambda: _env("SEED_ON_BOOT", "1") == "1")
    flight_source: str = field(default_factory=lambda: _env("FLIGHT_SOURCE", "mock-aodb"))
    aidx_source: str = field(default_factory=lambda: _env("AIDX_SOURCE", "mock-aidx"))
    acris_source: str = field(default_factory=lambda: _env("ACRIS_SOURCE", "mock-acris"))
    ai_provider: str = field(default_factory=lambda: _env("AI_PROVIDER", "mock"))
    ai_model: str = field(default_factory=lambda: _env("AI_MODEL", "mock-evidence-v1"))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL", ""))
    lan_ip: str = field(default_factory=detect_lan_ip)
    decision_interval_sim_seconds: int = field(
        default_factory=lambda: _env_int(
            "DECISION_INTERVAL", 120 if _env("RENDER", "") else 15
        )
    )
    presence_window_minutes: int = field(default_factory=lambda: _env_int("PRESENCE_WINDOW", 30))
    feed_fresh_seconds: int = field(default_factory=lambda: _env_int("FEED_FRESH_SECONDS", 180))
    aodb_fresh_seconds: int = field(default_factory=lambda: _env_int("AODB_FRESH_SECONDS", 900))
    max_history_days: int = field(default_factory=lambda: _env_int("MAX_HISTORY_DAYS", 30))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    version: str = "1.0.0"
    challenge: str = "Airport Retail Media Platform · Rapid Development Match"

    @property
    def theme(self) -> dict:
        return {
            "productName": self.product_name,
            "productShort": self.product_short,
            "airportCode": self.airport_code,
            "airportName": self.airport_name,
            "currency": self.currency,
            "locale": self.locale,
            "secondLanguage": self.second_language,
            "version": self.version,
            "challenge": self.challenge,
            "colors": {
                "darkBg": "#070b14",
                "darkPanel": "#0d1526",
                "accent": "#38e8c8",
                "accent2": "#8b7bff",
                "lime": "#c9f45b",
                "warn": "#ffb454",
                "danger": "#ff647c",
            },
        }


settings = Settings()