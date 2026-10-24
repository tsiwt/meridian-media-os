"""Tiny HTTP request/response primitives shared by all route modules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Settings
from ..domain.sim import Simulation

_ROUTE_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: dict[str, Any]
    headers: dict[str, str]
    settings: Settings
    sim: Simulation
    params: dict[str, str] = field(default_factory=dict)

    @property
    def now(self):
        return self.sim.now


@dataclass
class Response:
    status: int
    body: Any
    content_type: str = "application/json; charset=utf-8"

    def is_json(self) -> bool:
        return self.content_type.startswith("application/json")


def json_response(body: Any, status: int = 200) -> Response:
    return Response(status=status, body=body)


def text_response(body: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> Response:
    return Response(status=status, body=body, content_type=content_type)


def error(message: str, status: int = 400, code: str = "bad_request") -> Response:
    return Response(status=status, body={"error": code, "message": message})


def match_route(pattern: str, path: str) -> dict[str, str] | None:
    names = _ROUTE_RE.findall(pattern)
    regex = "^" + _ROUTE_RE.sub(r"([^/]+)", pattern) + "$"
    found = re.match(regex, path)
    if not found:
        return None
    return dict(zip(names, [value for value in found.groups()]))


Route = tuple[str, str, Callable[[Request], Response]]


def dispatch(table: list[Route], request: Request) -> Response | None:
    for method, pattern, handler in table:
        if method != request.method:
            continue
        params = match_route(pattern, request.path)
        if params is not None:
            request.params = params
            return handler(request)
    return None


def q_int(request: Request, name: str, default: int, minimum: int = 0, maximum: int = 500) -> int:
    try:
        value = int(request.query.get(name, default))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def q_str(request: Request, name: str, default: str = "") -> str:
    return str(request.query.get(name, default)).strip()[:200]


def body_str(body: dict, name: str, default: str = "", max_length: int = 500) -> str:
    value = body.get(name, default)
    if value is None:
        value = default
    return str(value).strip()[:max_length]


def body_float(body: dict, name: str, default: float = 0.0, minimum: float = 0.0, maximum: float = 1e9) -> float:
    try:
        value = float(body.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def body_int(body: dict, name: str, default: int = 0, minimum: int = 0, maximum: int = 1_000_000) -> int:
    try:
        value = int(body.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def body_bool(body: dict, name: str, default: bool = False) -> bool:
    value = body.get(name, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}