"""Adapter contracts and shared parsing helpers.

The app core only sees the canonical objects in ``app.models``.  A new source is
added by implementing these protocols and registering it in ``registry.py``;
no route, scoring rule or UI component needs to change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree


class AdapterError(RuntimeError):
    """Raised when a source payload cannot be translated."""


class AdapterNotConfigured(AdapterError):
    """Raised by a live stub until credentials/endpoint are configured."""


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text_of(element: ElementTree.Element | None, name: str, default: str = "") -> str:
    if element is None:
        return default
    for child in element:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    for child in element.iter():
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return default


def children_named(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element.iter() if local_name(child.tag) == name]


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def normalize_status(value: str) -> str:
    mapping = {
        "ARR": "ARR",
        "ARRIVED": "ARR",
        "DEP": "DEP",
        "DEPARTED": "DEP",
        "CNL": "CNL",
        "CANCELLED": "CNL",
        "CANCELED": "CNL",
        "DEL": "DEL",
        "DELAYED": "DEL",
        "BOD": "BOD",
        "BOARDING": "BOD",
        "GCL": "GCL",
        "GATE_CLOSED": "GCL",
        "SCH": "SCH",
        "ON TIME": "SCH",
    }
    return mapping.get((value or "").strip().upper(), (value or "SCH").strip().upper())