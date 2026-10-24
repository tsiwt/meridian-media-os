"""ACI ACRIS / FIWARE Smart Data Models adapter.

ACRIS entities arrive as NGSI-LD JSON (``id``, ``type``, properties with a
``value`` field, relationships with ``object``).  The adapter turns queue and
passenger-process entities into canonical ``QueueMeasurement`` objects and
keeps terminal/zone/checkpoint entities available to the infrastructure layer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..models import QueueMeasurement, parse_time
from .base import AdapterError, safe_float, safe_int

QUEUE_TYPES = {"QueueMeasurement", "PassengerQueue", "Queue", "QueueMeasurementEntity"}
ZONE_TYPES = {"Zone", "Concourse", "Terminal", "Checkpoint", "PassengerProcessArea"}


def _value(entity: dict[str, Any], name: str, default: Any = None) -> Any:
    node = entity.get(name)
    if isinstance(node, dict):
        return node.get("value", default)
    if node is None:
        return default
    return node


def _relation(entity: dict[str, Any], name: str) -> str:
    node = entity.get(name)
    if isinstance(node, dict):
        return str(node.get("object", ""))
    return str(node or "")


def _entity_id(entity: dict[str, Any]) -> str:
    return str(entity.get("id", "")).rsplit(":", 1)[-1]


class AcrisJsonSource:
    kind = "ACI ACRIS NGSI-LD"
    configured = True

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None

    def load(self, payload: Any | None = None) -> list[dict[str, Any]]:
        if payload is None:
            if not self.path or not self.path.exists():
                raise AdapterError(f"ACRIS file not found: {self.path}")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "@graph" in payload:
            payload = payload["@graph"]
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise AdapterError("ACRIS payload must be an entity, a list or an @graph")
        return [item for item in payload if isinstance(item, dict)]

    def measurements(self, payload: Any | None = None) -> Iterable[QueueMeasurement]:
        for entity in self.load(payload):
            if str(entity.get("type", "")) not in QUEUE_TYPES:
                continue
            observed = parse_time(str(entity.get("observedAt", ""))) or datetime.now(timezone.utc)
            zone = _relation(entity, "refZone") or _relation(entity, "refPassengerProcessArea")
            checkpoint = _relation(entity, "refCheckpoint") or _entity_id(entity)
            yield QueueMeasurement(
                zone_id=zone.rsplit(":", 1)[-1] or "unknown",
                checkpoint_id=checkpoint.rsplit(":", 1)[-1] or "unknown",
                queue_length=safe_int(_value(entity, "queueLength", 0)),
                wait_minutes=safe_float(_value(entity, "waitTimeMinutes", 0.0)),
                measured_at=observed,
                source="ACRIS",
            )

    def zones(self, payload: Any | None = None) -> Iterable[dict[str, Any]]:
        for entity in self.load(payload):
            entity_type = str(entity.get("type", ""))
            if entity_type not in ZONE_TYPES:
                continue
            yield {
                "id": _entity_id(entity),
                "type": entity_type,
                "name": _value(entity, "name", _entity_id(entity)),
                "terminal": _value(entity, "refTerminal", ""),
                "queueLength": safe_int(_value(entity, "queueLength", 0)),
                "waitTimeMinutes": safe_float(_value(entity, "waitTimeMinutes", 0.0)),
                "observedAt": entity.get("observedAt", ""),
            }


def build_entities(zones: list[dict[str, Any]], queues: list[dict[str, Any]]) -> dict[str, Any]:
    """Create an NGSI-LD document used by the mock ACRIS feed."""
    graph: list[dict[str, Any]] = []
    for zone in zones:
        graph.append(
            {
                "id": f"urn:ngsi-ld:Zone:MQI:{zone['id']}",
                "type": "Zone",
                "name": {"type": "Property", "value": zone["name"]},
                "refTerminal": {"type": "Relationship", "object": f"urn:ngsi-ld:Terminal:MQI:{zone['terminal_id']}"},
                "location": {
                    "type": "GeoProperty",
                    "value": {"type": "Point", "coordinates": [zone.get("x", 0), zone.get("y", 0)]},
                },
            }
        )
    for queue in queues:
        graph.append(
            {
                "id": f"urn:ngsi-ld:QueueMeasurement:MQI:{queue['zone_id']}:{queue['ts']}",
                "type": "QueueMeasurement",
                "observedAt": queue["ts"],
                "queueLength": {"type": "Property", "value": queue["queue_len"]},
                "waitTimeMinutes": {"type": "Property", "value": queue["wait_min"]},
                "refZone": {"type": "Relationship", "object": f"urn:ngsi-ld:Zone:MQI:{queue['zone_id']}"},
                "refCheckpoint": {
                    "type": "Relationship",
                    "object": f"urn:ngsi-ld:Checkpoint:MQI:{queue['checkpoint']}",
                },
            }
        )
    return {
        "@context": [
            "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld",
            {"name": "http://schema.org/name"},
        ],
        "@graph": graph,
    }