"""Adapter registry selected by configuration (one value per feed)."""

from __future__ import annotations

from pathlib import Path

from ..config import ROOT, Settings
from .acris import AcrisJsonSource
from .aidx import AidxXmlSource
from .aodb import AodbCsvSource, VendorFlightSource
from .base import AdapterNotConfigured

DATA = ROOT / "data"


class LiveAidxSource(AidxXmlSource):
    kind = "IATA AIDX live feed"
    configured = False

    def stream(self):  # type: ignore[override]
        raise AdapterNotConfigured(
            "AIDX live endpoint/token not configured. Use AIDX_SOURCE=mock-aidx for the POC."
        )


class LiveAcrisSource(AcrisJsonSource):
    kind = "ACI ACRIS live feed"
    configured = False

    def measurements(self, payload=None):  # type: ignore[override]
        raise AdapterNotConfigured(
            "ACRIS live endpoint not configured. Use ACRIS_SOURCE=mock-acris for the POC."
        )


def flight_source(settings: Settings):
    if settings.flight_source == "vendor-api":
        return VendorFlightSource()
    path = DATA / "aodb" / f"flights_{settings.sim_start.date().isoformat()}.csv"
    return AodbCsvSource(path)


def aidx_source(settings: Settings):
    if settings.aidx_source == "live-aidx":
        return LiveAidxSource()
    return AidxXmlSource()


def acris_source(settings: Settings):
    if settings.acris_source == "live-acris":
        return LiveAcrisSource()
    path = DATA / "acris" / "entities.json"
    return AcrisJsonSource(path)


def feed_health(settings: Settings) -> list[dict]:
    aodb = flight_source(settings)
    aidx = aidx_source(settings)
    acris = acris_source(settings)
    return [
        {
            "feed": "AODB",
            "adapter": aodb.kind,
            "mode": settings.flight_source,
            "configured": getattr(aodb, "configured", True),
            "contract": "FlightSource.snapshot() / stream()",
        },
        {
            "feed": "AIDX",
            "adapter": aidx.kind,
            "mode": settings.aidx_source,
            "configured": getattr(aidx, "configured", True),
            "contract": "FlightSource.stream(): FlightEvent",
        },
        {
            "feed": "ACRIS",
            "adapter": acris.kind,
            "mode": settings.acris_source,
            "configured": getattr(acris, "configured", True),
            "contract": "QueueSource.measurements()",
        },
    ]