"""Platform Admin: network map, KPIs, incidents, master data, rules, audit log."""

from __future__ import annotations

from .. import db
from ..adapters.registry import feed_health
from ..domain import decisions
from ..domain.profile import zone_presence
from ..models import iso, parse_time
from . import serializers
from .http import Request, Response, Route, body_bool, body_int, body_str, dispatch, json_response, q_int, q_str
from .metrics import metrics


def _overview(req: Request) -> Response:
    zones = [serializers.zone(row) for row in db.query("SELECT * FROM zones ORDER BY id")]
    presence = req.sim.zone_presence or {zone["id"]: zone_presence(zone["id"], req.now) for zone in zones}
    screens = [
        serializers.screen(row)
        for row in db.query(
            "SELECT s.*, z.name AS zone_name FROM screens s JOIN zones z ON z.id = s.zone_id ORDER BY s.id"
        )
    ]
    incidents = [
        serializers.incident(row)
        for row in db.query("SELECT * FROM incidents ORDER BY status='resolved', created DESC LIMIT 12")
    ]
    feeds = _feeds(req)
    stats = metrics.stats()
    return json_response(
        {
            "kpi": req.sim.kpi(),
            "zones": zones,
            "screens": screens,
            "presence": presence,
            "terminals": [dict(row) for row in db.query("SELECT * FROM terminals ORDER BY id")],
            "incidents": incidents,
            "feeds": feeds,
            "performance": {
                **stats,
                "playlistBuildMs": req.sim.last_cycle_ms or stats["playlistBuildMs"],
                "playlistBuildAt": req.sim.last_cycle_at or stats["playlistBuildAt"],
                "decisionInterval": req.sim.state()["decisionInterval"],
            },
            "decisions": [
                serializers.decision_summary(row)
                for row in db.query("SELECT * FROM decisions ORDER BY id DESC LIMIT 8")
            ],
        }
    )


def _feeds(req: Request) -> list[dict]:
    output = []
    now = req.now
    for feed in feed_health(req.settings):
        key = feed["feed"].lower()
        last = parse_time(db.get_meta(f"feed_last_{key}"))
        messages = db.query_one(
            "SELECT COUNT(*) AS c FROM flight_events WHERE ts >= ?",
            (iso(now.replace(second=0, microsecond=0)),),
        )["c"]
        output.append(
            {
                **feed,
                "lastMessageAt": iso(last) if last else None,
                "lagSeconds": int((now - last).total_seconds()) if last else None,
                "messagesPerMinute": int(messages),
                "status": "live" if last and (now - last).total_seconds() <= 180 else "lagging",
            }
        )
    queue = db.query_one(
        "SELECT COUNT(*) AS c, MAX(ts) AS last FROM queues WHERE ts >= ?",
        (iso(now.replace(second=0, microsecond=0)),),
    )
    output.append(
        {
            "feed": "Queue measurements",
            "adapter": req.settings.acris_source,
            "mode": req.settings.acris_source,
            "configured": True,
            "contract": "QueueSource.measurements()",
            "lastMessageAt": queue["last"],
            "lagSeconds": 0,
            "messagesPerMinute": int(queue["c"]),
            "status": "live",
        }
    )
    return output


def _incidents(req: Request) -> Response:
    status = q_str(req, "status")
    if status:
        rows = db.query("SELECT * FROM incidents WHERE status = ? ORDER BY created DESC LIMIT 100", (status,))
    else:
        rows = db.query("SELECT * FROM incidents ORDER BY status='resolved', created DESC LIMIT 100")
    return json_response({"items": [serializers.incident(row) for row in rows]})


def _incident_create(req: Request) -> Response:
    now = req.now
    kind = body_str(req.body, "kind", "manual", 40)
    severity = body_str(req.body, "severity", "medium", 20)
    title = body_str(req.body, "title", "Manual incident", 160)
    message = body_str(req.body, "message", "", 1000)
    if severity not in {"low", "medium", "high", "critical"}:
        return json_response({"error": "bad_request", "message": "Invalid severity"}, status=400)
    incident_id = db.execute(
        "INSERT INTO incidents(kind, severity, owner, status, title, message, created, updated, meta_json) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (kind, severity, body_str(req.body, "owner", "ops@mqi.example", 120), "open",
         title, message, iso(now), iso(now), "{}"),
    )
    row = db.query_one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    return json_response({"ok": True, "incident": serializers.incident(row)}, status=201)


def _incident_update(req: Request) -> Response:
    incident_id = int(req.params["id"])
    row = db.query_one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if not row:
        return json_response({"error": "not_found", "message": "Incident not found"}, status=404)
    status = body_str(req.body, "status", row["status"], 20)
    owner = body_str(req.body, "owner", row["owner"], 120)
    severity = body_str(req.body, "severity", row["severity"], 20)
    if status not in {"open", "investigating", "resolved"}:
        return json_response({"error": "bad_request", "message": "Invalid status"}, status=400)
    db.execute(
        "UPDATE incidents SET status=?, owner=?, severity=?, updated=? WHERE id=?",
        (status, owner, severity, iso(req.now), incident_id),
    )
    updated = db.query_one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    return json_response({"ok": True, "incident": serializers.incident(updated)})


def _master(req: Request) -> Response:
    entity = req.params["entity"]
    items = _master_items(entity)
    if items is None:
        return json_response({"error": "not_found", "message": "Unknown master entity"}, status=404)
    return json_response({"entity": entity, "items": items})


def _master_items(entity: str) -> list[dict] | None:
    if entity == "vendors":
        rows = db.query(
            "SELECT a.*, COUNT(o.id) AS outlets FROM advertisers a "
            "LEFT JOIN outlets o ON o.advertiser_id = a.id GROUP BY a.id ORDER BY a.id"
        )
        return [serializers.advertiser(row) for row in rows]
    if entity == "outlets":
        rows = db.query(
            "SELECT o.*, a.name AS advertiser_name, z.name AS zone_name FROM outlets o "
            "JOIN advertisers a ON a.id = o.advertiser_id JOIN zones z ON z.id = o.zone_id ORDER BY o.id"
        )
        return [serializers.outlet(row) for row in rows]
    if entity == "airlines":
        return [dict(row) for row in db.query("SELECT * FROM airlines ORDER BY iata")]
    if entity == "screens":
        rows = db.query(
            "SELECT s.*, z.name AS zone_name FROM screens s JOIN zones z ON z.id = s.zone_id ORDER BY s.id"
        )
        return [serializers.screen(row) for row in rows]
    if entity == "locations":
        return [serializers.zone(row) for row in db.query("SELECT * FROM zones ORDER BY id")]
    return None


def _master_create(req: Request) -> Response:
    entity = req.params["entity"]
    now = req.now
    body = req.body
    if entity == "vendors":
        name = body_str(body, "name", "", 160)
        if not name:
            return json_response({"error": "bad_request", "message": "name is required"}, status=400)
        next_id = db.query_one("SELECT COUNT(*) AS c FROM advertisers")["c"] + 1
        vendor_id = f"ADV-{next_id:03d}"
        db.execute(
            "INSERT INTO advertisers(id, name, kind, color, contact, created) VALUES (?,?,?,?,?,?)",
            (vendor_id, name, body_str(body, "kind", "retailer", 20),
             body_str(body, "color", "#38e8c8", 20), body_str(body, "contact", "", 160), iso(now)),
        )
        return json_response({"ok": True, "id": vendor_id}, status=201)
    if entity == "outlets":
        name = body_str(body, "name", "", 160)
        advertiser_id = body_str(body, "advertiserId", "", 30)
        zone_id = body_str(body, "zoneId", "", 30)
        if not name or not advertiser_id or not zone_id:
            return json_response({"error": "bad_request", "message": "name, advertiserId and zoneId are required"}, status=400)
        next_id = db.query_one("SELECT COUNT(*) AS c FROM outlets")["c"] + 1
        outlet_id = f"OUT-{next_id:03d}"
        db.execute(
            "INSERT INTO outlets(id, advertiser_id, name, zone_id, category, stock_status, created) "
            "VALUES (?,?,?,?,?,?,?)",
            (outlet_id, advertiser_id, name, zone_id, body_str(body, "category", "retail", 40),
             "in_stock", iso(now)),
        )
        return json_response({"ok": True, "id": outlet_id}, status=201)
    if entity == "screens":
        zone_id = body_str(body, "zoneId", "", 30)
        if not zone_id:
            return json_response({"error": "bad_request", "message": "zoneId is required"}, status=400)
        next_id = db.query_one("SELECT COUNT(*) AS c FROM screens")["c"] + 1
        screen_id = f"SCR-{next_id:03d}"
        gates = body.get("nearestGates") or []
        gates = [str(gate)[:5] for gate in gates][:4]
        aspect = body_str(body, "aspect", "16:9", 10)
        db.execute(
            "INSERT INTO screens(id, name, zone_id, nearest_gates_json, aspect, orientation, size_inches, "
            "status, latency_ms, last_seen, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (screen_id, body_str(body, "name", f"New screen {screen_id}", 160), zone_id,
             db.json_dumps(gates), aspect, "portrait" if aspect == "9:16" else "landscape",
             body_int(body, "sizeInches", 55, 10, 200), "online", body_int(body, "latencyMs", 70, 1, 5000),
             iso(now), body_str(body, "category", "gate", 30)),
        )
        return json_response({"ok": True, "id": screen_id}, status=201)
    if entity == "airlines":
        iata = body_str(body, "iata", "", 2).upper()
        if len(iata) != 2:
            return json_response({"error": "bad_request", "message": "iata must be two letters"}, status=400)
        db.execute(
            "INSERT INTO airlines(iata, icao, name, market, color, is_partner) VALUES (?,?,?,?,?,1)",
            (iata, body_str(body, "icao", "", 3).upper(), body_str(body, "name", iata, 120),
             body_str(body, "market", "International", 60), body_str(body, "color", "#38e8c8", 20)),
        )
        return json_response({"ok": True, "id": iata}, status=201)
    if entity == "locations":
        kind = body_str(body, "kind", "zone", 20)
        if kind == "zone":
            zone_id = body_str(body, "id", "", 30).upper()
            if not zone_id:
                return json_response({"error": "bad_request", "message": "id is required"}, status=400)
            db.execute(
                "INSERT INTO zones(id, terminal_id, name, concourse, kind, gates_json, x, y, w, h) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (zone_id, body_str(body, "terminalId", "T1", 4), body_str(body, "name", zone_id, 120),
                 body_str(body, "concourse", "A", 4), body_str(body, "zoneKind", "gate", 20),
                 db.json_dumps([str(gate)[:5] for gate in (body.get("gates") or [])]),
                 body_int(body, "x", 100, 0, 2000), body_int(body, "y", 100, 0, 1000),
                 body_int(body, "w", 100, 20, 1000), body_int(body, "h", 80, 20, 1000)),
            )
            return json_response({"ok": True, "id": zone_id}, status=201)
        if kind == "gate":
            code = body_str(body, "code", "", 5)
            zone_id = body_str(body, "zoneId", "", 30)
            if not code or not zone_id:
                return json_response({"error": "bad_request", "message": "code and zoneId are required"}, status=400)
            db.execute(
                "INSERT INTO gates(code, zone_id, terminal_id, x, y) VALUES (?,?,?,?,?)",
                (code, zone_id, body_str(body, "terminalId", "T1", 4),
                 body_int(body, "x", 100, 0, 2000), body_int(body, "y", 100, 0, 1000)),
            )
            return json_response({"ok": True, "id": code}, status=201)
    return json_response({"error": "not_found", "message": "Unknown master entity"}, status=404)


def _master_update(req: Request) -> Response:
    entity = req.params["entity"]
    item_id = req.params["id"]
    body = req.body
    table, allowed = _update_target(entity)
    if not table:
        return json_response({"error": "not_found", "message": "Unknown master entity"}, status=404)
    updates, values = [], []
    for field in allowed:
        if field in body:
            value = body[field]
            if isinstance(value, (list, dict)):
                value = db.json_dumps(value)
            if isinstance(value, bool):
                value = int(value)
            updates.append(f"{field} = ?")
            values.append(value)
    if not updates:
        return json_response({"error": "bad_request", "message": "No updatable fields supplied"}, status=400)
    values.append(item_id)
    with db.transaction() as conn:
        # Table, column and id names come only from the _update_target()/entity whitelist;
        # values remain bound parameters, so this is not injectable input.
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
        conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE {_id_column(entity)} = ?", values)
    return json_response({"ok": True, "id": item_id})


def _update_target(entity: str) -> tuple[str, list[str]]:
    return {
        "vendors": ("advertisers", ["name", "kind", "color", "contact"]),
        "outlets": ("outlets", ["name", "zone_id", "category", "stock_status"]),
        "airlines": ("airlines", ["name", "icao", "market", "color"]),
        "screens": ("screens", ["name", "zone_id", "status", "latency_ms", "aspect"]),
    }.get(entity, ("", []))


def _id_column(entity: str) -> str:
    return "iata" if entity == "airlines" else "id"


def _rules(req: Request) -> Response:
    if req.method == "GET":
        rules = decisions.load_rules()
        rules["segmentModelVersion"] = "seg-2026.10-v3"
        return json_response(rules)
    updates = req.body or {}
    if not isinstance(updates, dict):
        return json_response({"error": "bad_request", "message": "Rules payload must be an object"}, status=400)
    numeric = {"explorationPct": 0.0, "frequencyCapMin": 1.0, "competitorSeparationMin": 0.0, "delayThresholdMin": 0.0}
    clean = {}
    for key, value in updates.items():
        if key not in {
            "globalWeights", "explorationPct", "frequencyCapMin", "competitorSeparationMin",
            "delayThresholdMin", "segmentModel", "pacing", "houseCampaignId", "minEvidenceConfidence",
        }:
            continue
        if key in numeric:
            try:
                clean[key] = max(0.0, min(100.0, float(value)))
            except (TypeError, ValueError):
                continue
        elif key == "globalWeights" and isinstance(value, dict):
            clean[key] = {str(k)[:30]: max(0.0, min(1.0, float(v))) for k, v in value.items() if isinstance(v, (int, float))}
        else:
            clean[key] = str(value)[:40]
    with db.transaction() as conn:
        for key, value in clean.items():
            conn.execute(
                "INSERT INTO rules(key, value_json, updated) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated=excluded.updated",
                (key, db.json_dumps(value), iso(req.now)),
            )
    return json_response({"ok": True, "rules": decisions.load_rules()})


def _decisions(req: Request) -> Response:
    clauses, params = [], []
    screen = q_str(req, "screenId")
    campaign = q_str(req, "campaignId")
    search = q_str(req, "q")
    fallback = q_str(req, "fallback")
    if screen:
        clauses.append("screen_id = ?")
        params.append(screen)
    if campaign:
        clauses.append("winner_id = ?")
        params.append(campaign)
    if search:
        clauses.append("(screen_id LIKE ? OR winner_id LIKE ? OR reason LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if fallback in {"0", "1"}:
        clauses.append("fallback = ?")
        params.append(int(fallback))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = db.query_one("SELECT COUNT(*) AS c FROM decisions" + where, params)["c"]
    limit = q_int(req, "limit", 30, 1, 200)
    offset = q_int(req, "offset", 0, 0, 100000)
    rows = db.query(
        "SELECT * FROM decisions" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )
    return json_response(
        {
            "total": total,
            "items": [serializers.decision_summary(row) for row in rows],
            "limit": limit,
            "offset": offset,
        }
    )


def _decision_detail(req: Request) -> Response:
    row = decisions.why(int(req.params["id"]))
    if not row:
        return json_response({"error": "not_found", "message": "Decision not found"}, status=404)
    return json_response(row)


def _screens(req: Request) -> Response:
    rows = db.query(
        "SELECT s.*, z.name AS zone_name FROM screens s JOIN zones z ON z.id = s.zone_id ORDER BY s.id"
    )
    return json_response({"items": [serializers.screen(row) for row in rows]})


ROUTES: list[Route] = [
    ("GET", "/api/admin/overview", _overview),
    ("GET", "/api/admin/incidents", _incidents),
    ("POST", "/api/admin/incidents", _incident_create),
    ("PATCH", "/api/admin/incidents/{id}", _incident_update),
    ("GET", "/api/admin/master/{entity}", _master),
    ("POST", "/api/admin/master/{entity}", _master_create),
    ("PATCH", "/api/admin/master/{entity}/{id}", _master_update),
    ("GET", "/api/admin/rules", _rules),
    ("PUT", "/api/admin/rules", _rules),
    ("GET", "/api/admin/decisions", _decisions),
    ("GET", "/api/admin/decisions/{id}", _decision_detail),
    ("GET", "/api/admin/screens", _screens),
]


def handle(request: Request) -> Response | None:
    return dispatch(ROUTES, request)