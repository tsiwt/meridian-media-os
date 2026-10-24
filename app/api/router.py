"""Route table composition.  Each module owns one role's endpoints."""

from __future__ import annotations

from . import routes_admin, routes_airline, routes_core, routes_media, routes_passenger, routes_retailer
from .http import Request, Response, error

MODULES = [routes_core, routes_retailer, routes_media, routes_airline, routes_admin, routes_passenger]


def handle(request: Request) -> Response:
    for module in MODULES:
        response = module.handle(request)
        if response is not None:
            return response
    return error("Endpoint not found", status=404, code="not_found")