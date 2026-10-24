"""IATA AIDX ``FlightLegNotifRQ`` adapter.

AIDX is the real-time flight-leg notification feed.  The parser is namespace
agnostic (local names only), rejects DTD/ENTITY payloads before parsing, and
translates status, timing, gate and cabin data into canonical ``FlightEvent``
objects.  ``build_notification`` produces a standards-shaped message used by
the simulation when a reviewer injects a delay or gate change, so the demo
exercises the same adapter path as a live feed.
"""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree

from ..models import Flight, FlightEvent, iso, parse_time
from .base import (
    AdapterError,
    children_named,
    local_name,
    parse_iso,
    safe_int,
    text_of,
)

MAX_MESSAGE_BYTES = 2_000_000


class AidxXmlSource:
    kind = "IATA AIDX XML"
    configured = True

    def __init__(self, path: str | None = None) -> None:
        self.path = path

    def parse(self, xml_text: str) -> list[FlightEvent]:
        if len(xml_text.encode("utf-8", "ignore")) > MAX_MESSAGE_BYTES:
            raise AdapterError("AIDX message exceeds the 2 MB safety limit")
        upper = xml_text.upper()
        if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
            raise AdapterError("AIDX payload must not contain DTD or ENTITY declarations")
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as exc:
            raise AdapterError(f"Malformed AIDX XML: {exc}") from exc
        if local_name(root.tag) != "IATA_AIDX_FlightLegNotifRQ":
            raise AdapterError("Unsupported AIDX root element")
        timestamp = parse_iso(root.attrib.get("TimeStamp")) or datetime.utcnow()
        events: list[FlightEvent] = []
        for leg in children_named(root, "FlightLeg"):
            events.extend(self._parse_leg(leg, timestamp))
        return events

    def parse_file(self, path: str | None = None) -> list[FlightEvent]:
        target = path or self.path
        if not target:
            raise AdapterError("No AIDX file supplied")
        with open(target, "r", encoding="utf-8") as handle:
            return self.parse(handle.read())

    def _parse_leg(self, leg: ElementTree.Element, timestamp: datetime) -> list[FlightEvent]:
        ident = next(iter(children_named(leg, "LegIdentifier")), None)
        airline = text_of(ident, "Airline").upper()
        number = text_of(ident, "FlightNumber")
        origin = text_of(ident, "DepartureAirport")
        destination = text_of(ident, "ArrivalAirport")
        origin_date = text_of(ident, "OriginDate")
        extension_id = text_of(ident, "FlightID")
        direction = "D" if origin and not destination else "A"
        payload = {
            "airline": airline,
            "flightNumber": number,
            "origin": origin,
            "destination": destination,
            "originDate": origin_date,
            "direction": direction,
        }
        resolved_id = extension_id or f"{airline}{number}:{origin}-{destination}:{origin_date}"
        events: list[FlightEvent] = []

        def emit(event_type: str, field: str, new_value: str) -> None:
            if not new_value:
                return
            events.append(
                FlightEvent(
                    flight_id=resolved_id,
                    event_type=event_type,
                    field=field,
                    old_value="",
                    new_value=new_value,
                    source="IATA AIDX",
                    occurred_at=timestamp,
                    payload=dict(payload),
                )
            )

        emit("STATUS", "status", text_of(leg, "PublicStatus"))
        emit("STATUS", "operationalStatus", text_of(leg, "OperationalStatus"))

        for node in children_named(leg, "OperationTime"):
            qualifier = node.attrib.get("OperationQualifier", "")
            time_type = node.attrib.get("TimeType", "")
            value = (node.text or "").strip()
            if not value:
                continue
            field = _time_field(qualifier, time_type)
            if field:
                emit("TIMING", field, value)

        for node in children_named(leg, "Resource"):
            position = text_of(node, "AircraftParkingPosition")
            terminal = text_of(node, "AircraftTerminal")
            if position:
                emit("RESOURCE", "gate", position)
                payload["stand"] = position
            if terminal:
                emit("RESOURCE", "terminal", terminal)

        seats = 0
        pax = 0
        for cabin in children_named(leg, "CabinClass"):
            seats += safe_int(text_of(cabin, "SeatCapacity"))
            pax += safe_int(text_of(cabin, "PaxCount"))
        if seats:
            emit("LOAD", "seats", str(seats))
        if pax:
            emit("LOAD", "pax", str(pax))
        return events

    def stream(self) -> list[FlightEvent]:
        return self.parse_file()


def _time_field(qualifier: str, time_type: str) -> str:
    qualifier = qualifier.upper()
    time_type = time_type.upper()
    if qualifier in {"TOBT", "TSAT", "AIBT", "AOBT"}:
        return qualifier.lower()
    if qualifier in {"ONB", "BOARDING"}:
        return "boarding"
    if qualifier in {"DEP", "ARR", "TDN"}:
        if time_type == "ACT":
            return "actual"
        if time_type in {"EST", "SCT"}:
            return "estimated"
    if time_type == "ACT":
        return "actual"
    return ""


def build_notification(
    flight: Flight,
    *,
    status: str | None = None,
    gate: str | None = None,
    estimated: datetime | None = None,
    reason: str = "POC event",
) -> str:
    """Build an AIDX-shaped message for the simulation event injector."""
    stamp = datetime.utcnow().replace(microsecond=0)
    direction = flight.direction
    airline = flight.airline_iata
    number = flight.flight_number
    origin = flight.origin
    destination = flight.destination
    qualifier = "DEP" if direction == "D" else "ARR"
    time_node = ""
    if estimated:
        time_node = (
            f'<OperationTime OperationQualifier="{qualifier}" CodeContext="9750" '
            f'TimeType="EST">{iso(estimated)}</OperationTime>'
        )
    resource = ""
    if gate:
        resource = (
            "<AirportResources Usage=\"Actual\"><Resource "
            f'DepartureOrArrival="{"Departure" if direction == "D" else "Arrival"}">'
            f"<AircraftParkingPosition>{gate}</AircraftParkingPosition>"
            "</Resource></AirportResources>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<IATA_AIDX_FlightLegNotifRQ xmlns="http://www.iata.org/IATA/2007/00" '
        f'Version="16.1" Target="POC" TimeStamp="{iso(stamp)}" '
        f'TransactionIdentifier="MQI-POC-{stamp.strftime("%H%M%S")}" SequenceNmbr="1">'
        f'<Originator CompanyShortName="MQI" Code="MQI" CodeContext="3"/>'
        f'<DeliveringSystem CompanyShortName="AODB"/>'
        f"<FlightLeg><LegIdentifier><FlightID>{flight.flight_id}</FlightID>"
        f"<Airline CodeContext=\"3\">{airline}</Airline>"
        f"<FlightNumber>{number}</FlightNumber>"
        f"<DepartureAirport CodeContext=\"3\">{origin}</DepartureAirport>"
        f"<ArrivalAirport CodeContext=\"3\">{destination}</ArrivalAirport>"
        f"<OriginDate>{(flight.scheduled or stamp).date().isoformat()}</OriginDate>"
        f"</LegIdentifier><LegData InternalDomesticIndicator=\""
        f'{"false" if flight.is_international else "true"}">'
        f"<PublicStatus>{status or flight.status}</PublicStatus>"
        f"<OperationalStatus>{reason}</OperationalStatus>"
        f"<ServiceType>{flight.service_type}</ServiceType>"
        f"{resource}{time_node}"
        f"<AircraftInfo><AircraftType>{flight.aircraft_type_icao}</AircraftType>"
        f"<Registration>{flight.aircraft_reg}</Registration></AircraftInfo>"
        f"</LegData></FlightLeg></IATA_AIDX_FlightLegNotifRQ>"
    )