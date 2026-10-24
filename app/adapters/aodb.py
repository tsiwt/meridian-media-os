"""AODB CSV adapter.

The source layout is the 33-column airport operational database extract shipped
with the challenge (one row per flight leg; paired arrival/departure rows linked
by ``linked_flight_id``).  The adapter is deliberately stateless: it translates
rows into canonical ``Flight`` objects and can also emit a stream of timing
events for a live vendor implementation.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ..models import Flight, FlightEvent, parse_time
from .base import AdapterError, AdapterNotConfigured, normalize_status, safe_int

EXPECTED_COLUMNS = (
    "aodb_flight_id,linked_flight_id,direction,airline_iata,airline_icao,"
    "flight_number,callsign,service_type,flight_nature,origin,destination,via,"
    "terminal,STA_STD,ETA_ETD,ELDT_ETOT,ALDT_ATOT,AIBT_AOBT,TOBT,TSAT,stand,gate,"
    "checkin_counters,baggage_belt,aircraft_reg,aircraft_type_icao,seats,pax_total,"
    "status,delay_codes,codeshares,handler,last_update_utc"
).split(",")


class AodbCsvSource:
    kind = "AODB CSV"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise AdapterError(f"AODB file not found: {self.path}")

    def _rows(self) -> Iterable[dict[str, str]]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = [name for name in EXPECTED_COLUMNS if name not in (reader.fieldnames or [])]
            if missing:
                raise AdapterError(
                    "AODB payload is missing required columns: " + ", ".join(missing)
                )
            for row in reader:
                yield row

    def snapshot(self) -> Iterable[Flight]:
        for row in self._rows():
            yield self._to_flight(row)

    def stream(self) -> Iterable[FlightEvent]:
        """The batch extract has no incremental feed; AIDX covers that path."""
        return iter(())

    @staticmethod
    def _to_flight(row: dict[str, str]) -> Flight:
        direction = (row.get("direction") or "").strip().upper()
        arrival = direction == "A"
        scheduled = parse_time(row.get("STA_STD"))
        estimate = parse_time(row.get("ETA_ETD"))
        movement = parse_time(row.get("ELDT_ETOT"))
        actual = parse_time(row.get("ALDT_ATOT"))
        return Flight(
            flight_id=(row.get("aodb_flight_id") or "").strip(),
            linked_flight_id=(row.get("linked_flight_id") or "").strip(),
            direction=direction or "D",
            airline_iata=(row.get("airline_iata") or "").strip().upper(),
            airline_icao=(row.get("airline_icao") or "").strip().upper(),
            flight_number=(row.get("flight_number") or "").strip(),
            callsign=(row.get("callsign") or "").strip(),
            service_type=(row.get("service_type") or "J").strip(),
            flight_nature=(row.get("flight_nature") or "D").strip().upper(),
            origin=(row.get("origin") or "").strip(),
            destination=(row.get("destination") or "").strip(),
            via=(row.get("via") or "").strip(),
            terminal=(row.get("terminal") or "").strip(),
            scheduled=scheduled,
            estimated=estimate,
            estimated_landing=movement if arrival else None,
            estimated_takeoff=None if arrival else movement,
            actual_landing=actual if arrival else None,
            actual_takeoff=None if arrival else actual,
            aibt=parse_time(row.get("AIBT_AOBT")),
            aobt=None if arrival else parse_time(row.get("AIBT_AOBT")),
            tobt=parse_time(row.get("TOBT")),
            tsat=parse_time(row.get("TSAT")),
            stand=(row.get("stand") or "").strip(),
            gate=(row.get("gate") or "").strip(),
            checkin_counters=(row.get("checkin_counters") or "").strip(),
            baggage_belt=(row.get("baggage_belt") or "").strip(),
            aircraft_reg=(row.get("aircraft_reg") or "").strip(),
            aircraft_type_icao=(row.get("aircraft_type_icao") or "").strip(),
            seats=safe_int(row.get("seats")),
            pax_total=safe_int(row.get("pax_total")),
            status=normalize_status(row.get("status", "")),
            delay_codes=(row.get("delay_codes") or "").strip(),
            codeshares=(row.get("codeshares") or "").strip(),
            handler=(row.get("handler") or "").strip(),
            last_update=parse_time(row.get("last_update_utc")),
            profile={},
        )


class VendorFlightSource:
    """Live AODB vendor API stub.

    Selecting ``FLIGHT_SOURCE=vendor-api`` proves that the switch is a single
    config value.  Without credentials the feed health endpoint reports
    ``not_configured`` instead of crashing the demo.
    """

    kind = "AODB vendor API (live)"
    configured = False

    def snapshot(self) -> Iterable[Flight]:
        raise AdapterNotConfigured(
            "Vendor AODB credentials are not configured. Set FLIGHT_SOURCE=mock-aodb "
            "for the POC feed, or implement VendorFlightSource.snapshot()."
        )

    def stream(self) -> Iterable[FlightEvent]:
        return iter(())
