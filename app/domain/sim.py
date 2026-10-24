"""Simulation clock, event injector, decision scheduler and SSE fan-out."""

from __future__ import annotations

import queue
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from .. import db
from ..adapters.aidx import AidxXmlSource, build_notification
from ..config import Settings
from ..models import iso, parse_time
from . import decisions, goodwill, scoring
from .profile import zone_presence


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def subscribe(self) -> tuple[int, queue.Queue]:
        with self._lock:
            token = self._next_id
            self._next_id += 1
            channel: queue.Queue = queue.Queue(maxsize=200)
            self._subscribers[token] = channel
            return token, channel

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subscribers.pop(token, None)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        with self._lock:
            tokens = list(self._subscribers.items())
        for token, channel in tokens:
            try:
                channel.put_nowait({"event": event, "data": data})
            except queue.Full:
                try:
                    channel.get_nowait()
                    channel.put_nowait({"event": event, "data": data})
                except queue.Empty:
                    pass
                except queue.Full:
                    pass


class Simulation:
    def __init__(self, settings: Settings, autostart: bool = True) -> None:
        self.settings = settings
        self.bus = EventBus()
        self._lock = threading.RLock()
        start = parse_time(db.get_meta("sim_start")) or settings.sim_start
        self._sim = start
        self._anchor_sim = start
        self._anchor_real = time.time()
        self.running = settings.sim_autoplay
        self.speed = float(settings.sim_speed)
        self._last_decision_sim = start - timedelta(seconds=60)
        self._last_queue_sim = start - timedelta(minutes=10)
        self._last_kpi_real = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._random = random.Random(settings.seed + 7)
        self.zone_presence: dict[str, dict] = {}
        self._feed_stale = False
        self._tick_count = 0
        self.started_at = datetime.utcnow()
        self.last_cycle_ms = 0.0
        self.last_cycle_at = ""
        self._set_feed_heartbeats(start)
        self._refresh_queues(start)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="simulation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # pragma: no cover - keeps the demo alive
                db.set_meta("last_sim_error", f"{type(exc).__name__}: {exc}")
                self.bus.publish("sim_error", {"message": str(exc)})
            self._stop.wait(1.0)

    # -- clock -------------------------------------------------------------
    @property
    def now(self) -> datetime:
        with self._lock:
            if not self.running:
                return self._sim
            return self._anchor_sim + timedelta(seconds=(time.time() - self._anchor_real) * self.speed)

    def _rebase(self) -> None:
        self._sim = self.now
        self._anchor_sim = self._sim
        self._anchor_real = time.time()

    def control(self, action: str, value: Any = None) -> dict[str, Any]:
        with self._lock:
            if action == "play":
                if not self.running:
                    self._anchor_sim = self._sim
                    self._anchor_real = time.time()
                    self.running = True
            elif action == "pause":
                if self.running:
                    self._sim = self.now
                    self.running = False
            elif action == "speed":
                self._sim = self.now
                self.speed = max(0.25, min(120.0, float(value or 1)))
                self._anchor_sim = self._sim
                self._anchor_real = time.time()
            elif action == "jump":
                target = parse_time(str(value)) if value else None
                if target:
                    self._sim = target
                    self._anchor_sim = target
                    self._anchor_real = time.time()
                    db.set_meta("sim_start", iso(target))
                    self._last_decision_sim = target - timedelta(seconds=60)
            elif action == "reset":
                self._sim = self.settings.sim_start
                self._anchor_sim = self._sim
                self._anchor_real = time.time()
                self._last_decision_sim = self._sim - timedelta(seconds=60)
            elif action == "inject":
                self._sim = self.now
                self._anchor_sim = self._sim
                self._anchor_real = time.time()
                return self.inject(value or {})
            elif action == "stale-feed":
                self._feed_stale = bool(value if value is not None else True)
                if not self._feed_stale:
                    self._set_feed_heartbeats(self.now)
                for screen in db.query("SELECT id FROM screens"):
                    self._decide_screen_safe(screen["id"], self.now)
            else:
                raise ValueError(f"Unknown simulation action: {action}")
        self.publish_state()
        return self.state()

    def state(self) -> dict[str, Any]:
        now = self.now
        return {
            "time": iso(now),
            "speed": self.speed,
            "running": self.running,
            "start": iso(self.settings.sim_start),
            "decisionInterval": self._decision_interval(),
            "feedStale": self._feed_stale,
            "tick": self._tick_count,
        }

    def _decision_interval(self) -> int:
        base = self.settings.decision_interval_sim_seconds
        if self.speed <= 2:
            return base
        if self.speed <= 10:
            return base * 2
        return base * 6

    # -- tick --------------------------------------------------------------
    def tick(self) -> None:
        now = self.now
        with self._lock:
            self._sim = now
            self._tick_count += 1
        self._set_feed_heartbeats(now)
        changed = self._advance_flights(now)
        if changed:
            self.bus.publish("flight", {"changed": changed[:8], "time": iso(now)})
        if (now - self._last_queue_sim).total_seconds() >= 60:
            self._refresh_queues(now)
            self._last_queue_sim = now
        rules = decisions.load_rules()
        if (now - self._last_decision_sim).total_seconds() >= self._decision_interval():
            self._decision_cycle(now, rules)
            self._last_decision_sim = now
        self._check_incidents(now)
        if time.time() - self._last_kpi_real >= 1.0:
            self.publish_state()
            self._last_kpi_real = time.time()

    def publish_state(self) -> None:
        self.bus.publish("sim", self.state())
        self.bus.publish("kpi", self.kpi())

    def kpi(self) -> dict[str, Any]:
        now = self.now
        today = now.date().isoformat()
        total = db.query_one("SELECT COUNT(*) AS c FROM screens")["c"]
        online = db.query_one("SELECT COUNT(*) AS c FROM screens WHERE status='online'")["c"]
        latency = db.query_one("SELECT AVG(latency_ms) AS l FROM screens")["l"]
        stats = db.query_one(
            "SELECT COALESCE(SUM(impressions),0) AS impressions, COALESCE(SUM(revenue),0) AS revenue "
            "FROM daily_stats WHERE day = ?",
            (today,),
        )
        active = db.query_one(
            "SELECT COUNT(*) AS c FROM campaigns WHERE status='approved' AND start <= ? AND end >= ?",
            (iso(now), iso(now)),
        )["c"]
        decisions_today = db.query_one(
            "SELECT COUNT(*) AS c FROM decisions WHERE ts >= ?", (today + "T00:00:00Z",)
        )["c"]
        return {
            "time": iso(now),
            "screensTotal": total,
            "screensOnlinePct": round(100.0 * online / max(1, total), 1),
            "playsToday": int(stats["impressions"]),
            "revenueToday": round(float(stats["revenue"]), 2),
            "activeCampaigns": active,
            "avgLatencyMs": round(float(latency or 0), 1),
            "decisionsToday": decisions_today,
            "currency": self.settings.currency,
            "fallbacksToday": db.query_one(
                "SELECT COUNT(*) AS c FROM decisions WHERE fallback = 1 AND ts >= ?",
                (today + "T00:00:00Z",),
            )["c"],
            "openIncidents": db.query_one(
                "SELECT COUNT(*) AS c FROM incidents WHERE status != 'resolved'"
            )["c"],
        }

    def _advance_flights(self, now: datetime) -> list[dict[str, Any]]:
        rows = db.query(
            "SELECT flight_id, direction, std, etd, eta, status, delay_codes FROM flights "
            "WHERE std BETWEEN ? AND ?",
            (iso(now - timedelta(minutes=60)), iso(now + timedelta(hours=4))),
        )
        changed = []
        updates = []
        for row in rows:
            status = row["status"]
            if status == "CNL":
                continue
            std = parse_time(row["std"])
            estimated = parse_time(row["etd"] or row["eta"]) or std
            if row["direction"] == "D":
                if estimated and now >= estimated + timedelta(minutes=5):
                    new_status = "DEP"
                elif std and now >= std - timedelta(minutes=40):
                    new_status = "BOD"
                elif estimated and estimated > std + timedelta(minutes=5):
                    new_status = "DEL"
                else:
                    new_status = "SCH"
            else:
                new_status = "ARR" if estimated and now >= estimated + timedelta(minutes=5) else "SCH"
            if new_status != status:
                updates.append((new_status, iso(now), row["flight_id"]))
                changed.append({"flightId": row["flight_id"], "status": new_status})
        if updates:
            with db.transaction() as conn:
                conn.executemany(
                    "UPDATE flights SET status = ?, updated = ? WHERE flight_id = ?", updates
                )
        return changed

    def _refresh_queues(self, now: datetime) -> None:
        last_rows = db.query(
            "SELECT q.* FROM queues q JOIN (SELECT zone_id, MAX(ts) AS ts FROM queues GROUP BY zone_id) m "
            "ON q.zone_id = m.zone_id AND q.ts = m.ts"
        )
        with db.transaction() as conn:
            for row in last_rows:
                base = int(row["queue_len"])
                jitter = self._random.randint(-3, 4)
                length = max(0, base + jitter)
                conn.execute(
                    "INSERT INTO queues(zone_id, checkpoint, queue_len, wait_min, ts, source) "
                    "VALUES (?,?,?,?,?,'ACRIS')",
                    (row["zone_id"], row["checkpoint"], length, round(length * 0.45, 1), iso(now)),
                )

    def _decision_cycle(self, now: datetime, rules: dict) -> None:
        started = time.perf_counter()
        campaigns = scoring.load_campaigns(now)
        screens = [dict(row) for row in db.query("SELECT id, zone_id FROM screens")]
        decided: list[dict] = []
        zones: set[str] = set()
        for screen in screens:
            decision = self._decide_screen(screen["id"], now, rules, campaigns)
            if decision:
                zones.add(screen["zone_id"])
                if decision.winner:
                    decided.append(
                        {
                            "screenId": decision.screen_id,
                            "campaignId": decision.winner.campaign_id,
                            "score": decision.winner.final_score,
                            "fallback": decision.fallback,
                        }
                    )
        self.zone_presence = {zone_id: zone_presence(zone_id, now) for zone_id in zones}
        self.last_cycle_ms = round((time.perf_counter() - started) * 1000, 1)
        self.last_cycle_at = iso(now)
        self.bus.publish("decisions", {"count": len(decided), "sample": decided[:20], "zonePresence": self.zone_presence, "time": iso(now)})
        self._check_incidents(now)

    def _decide_screen(self, screen_id: str, now: datetime, rules: dict | None = None, campaigns: list | None = None):
        return decisions.decide(
            screen_id,
            now,
            self.settings,
            rules or decisions.load_rules(),
            persist=True,
            campaigns=campaigns,
        )

    def _decide_screen_safe(self, screen_id: str, now: datetime) -> None:
        try:
            self._decide_screen(screen_id, now)
        except Exception as exc:  # pragma: no cover
            db.set_meta("last_decision_error", f"{type(exc).__name__}: {exc}")

    # -- event injection ---------------------------------------------------
    def inject(self, payload: dict[str, Any]) -> dict[str, Any]:
        kind = payload.get("kind")
        now = self.now
        if kind == "delay":
            return self._inject_delay(payload, now)
        if kind == "gate_change":
            return self._inject_gate_change(payload, now)
        if kind == "screen_offline":
            return self._inject_screen(payload, now, offline=True)
        if kind == "screen_online":
            return self._inject_screen(payload, now, offline=False)
        if kind == "spend":
            code = payload.get("code")
            if not code:
                raise ValueError("A promo code is required")
            from .promos import claim

            result = claim(code, now, channel="simulator")
            self.bus.publish("redemption", result)
            return result
        raise ValueError(f"Unknown inject kind: {kind}")

    def _flight(self, payload: dict[str, Any]) -> dict[str, Any]:
        flight_id = payload.get("flightId")
        flight = db.query_one("SELECT * FROM flights WHERE flight_id = ?", (str(flight_id),))
        if not flight:
            raise ValueError("Flight not found")
        return dict(flight)

    def _apply_aidx_events(self, events: list, now: datetime) -> list[dict[str, Any]]:
        applied = []
        with db.transaction() as conn:
            for event in events:
                row = conn.execute(
                    "SELECT * FROM flights WHERE flight_id = ?", (event.flight_id,)
                ).fetchone()
                if not row:
                    continue
                flight = dict(row)
                if event.field == "status":
                    conn.execute(
                        "UPDATE flights SET status = ?, updated = ? WHERE flight_id = ?",
                        (event.new_value, iso(now), event.flight_id),
                    )
                elif event.field in {"estimated", "actual"}:
                    column = "etd" if flight["direction"] == "D" else "eta"
                    # The column name is one of two constants chosen above; values are bound.
                    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    conn.execute(
                        f"UPDATE flights SET {column} = ?, updated = ? WHERE flight_id = ?",
                        (event.new_value, iso(now), event.flight_id),
                    )
                elif event.field == "gate":
                    conn.execute(
                        "UPDATE flights SET gate = ?, updated = ? WHERE flight_id = ?",
                        (event.new_value, iso(now), event.flight_id),
                    )
                elif event.field == "pax":
                    conn.execute(
                        "UPDATE flights SET pax = ?, updated = ? WHERE flight_id = ?",
                        (int(event.new_value), iso(now), event.flight_id),
                    )
                elif event.field == "seats":
                    conn.execute(
                        "UPDATE flights SET seats = ?, updated = ? WHERE flight_id = ?",
                        (int(event.new_value), iso(now), event.flight_id),
                    )
                conn.execute(
                    "INSERT INTO flight_events(flight_id, type, field, old, new, source, ts, payload_json) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (event.flight_id, event.event_type, event.field, event.old_value,
                     event.new_value, event.source, iso(now), db.json_dumps(event.payload)),
                )
                applied.append({"flightId": event.flight_id, "field": event.field, "new": event.new_value})
        db.set_meta("feed_last_aidx", iso(now))
        return applied

    def _inject_delay(self, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        flight_row = self._flight(payload)
        flight = _flight_model(flight_row)
        minutes = int(payload.get("minutes") or 45)
        current = parse_time(flight_row.get("etd") or flight_row.get("std"))
        estimated = (current or now) + timedelta(minutes=minutes)
        xml = build_notification(
            flight, status="DEL", estimated=estimated, reason=f"POC injected {minutes} min delay"
        )
        events = AidxXmlSource().parse(xml)
        applied = self._apply_aidx_events(events, now)
        with db.transaction() as conn:
            conn.execute(
                "UPDATE flights SET status = 'DEL', etd = ?, delay_codes = '11', updated = ? "
                "WHERE flight_id = ?",
                (iso(estimated), iso(now), flight_row["flight_id"]),
            )
        self._decide_zone(flight_row["gate"], now)
        goodwill_action = goodwill.maybe_auto(flight_row, int(flight_row.get("delay_minutes") or minutes), now)
        result = {
            "ok": True,
            "kind": "delay",
            "flightId": flight_row["flight_id"],
            "flight": f"{flight_row['airline']}{flight_row['flight_no']}",
            "minutes": minutes,
            "estimated": iso(estimated),
            "adapter": "IATA AIDX",
            "applied": applied,
            "goodwill": goodwill_action,
        }
        self.bus.publish("flight", result)
        if goodwill_action:
            self.bus.publish("goodwill", goodwill_action)
        self.bus.publish("incident", {"kind": "delay", "message": f"{result['flight']} delayed {minutes} min"})
        return result

    def _inject_gate_change(self, payload: dict[str, Any], now: datetime) -> dict[str, Any]:
        flight_row = self._flight(payload)
        flight = _flight_model(flight_row)
        gate = str(payload.get("gate") or "45")
        xml = build_notification(flight, gate=gate, reason="POC gate change")
        events = AidxXmlSource().parse(xml)
        applied = self._apply_aidx_events(events, now)
        with db.transaction() as conn:
            conn.execute(
                "UPDATE flights SET gate = ?, updated = ? WHERE flight_id = ?",
                (gate, iso(now), flight_row["flight_id"]),
            )
        self._decide_zone(flight_row["gate"], now)
        result = {
            "ok": True,
            "kind": "gate_change",
            "flightId": flight_row["flight_id"],
            "flight": f"{flight_row['airline']}{flight_row['flight_no']}",
            "gate": gate,
            "adapter": "IATA AIDX",
            "applied": applied,
        }
        self.bus.publish("flight", result)
        return result

    def _inject_screen(self, payload: dict[str, Any], now: datetime, offline: bool) -> dict[str, Any]:
        screen_id = str(payload.get("screenId") or "SCR-021")
        status = "offline" if offline else "online"
        last_seen = now - timedelta(minutes=8) if offline else now
        db.execute(
            "UPDATE screens SET status = ?, last_seen = ?, latency_ms = ? WHERE id = ?",
            (status, iso(last_seen), 0 if offline else 68, screen_id),
        )
        if offline:
            self._raise_incident(
                "screen_offline", "high", f"Screen {screen_id} offline",
                "Simulated outage injected by the operator. Playlist paused; fallback poster active.",
                {"screenId": screen_id},
            )
        else:
            with db.transaction() as conn:
                conn.execute(
                    "UPDATE incidents SET status = 'resolved', updated = ? "
                    "WHERE kind = 'screen_offline' AND status != 'resolved' AND meta_json LIKE ?",
                    (iso(now), f'%{screen_id}%'),
                )
        self.bus.publish("screen", {"screenId": screen_id, "status": status})
        return {"ok": True, "kind": "screen", "screenId": screen_id, "status": status}

    def _decide_zone(self, gate: str, now: datetime) -> None:
        row = db.query_one(
            "SELECT z.id FROM zones z JOIN gates g ON g.zone_id = z.id WHERE g.code = ?", (gate,)
        )
        if not row:
            return
        screens = db.query("SELECT id FROM screens WHERE zone_id = ?", (row["id"],))
        campaigns = scoring.load_campaigns(now)
        rules = decisions.load_rules()
        for screen in screens:
            self._decide_screen(screen["id"], now, rules, campaigns)
        self.zone_presence[row["id"]] = zone_presence(row["id"], now)

    # -- incidents & feeds -------------------------------------------------
    def _raise_incident(
        self,
        kind: str,
        severity: str,
        title: str,
        message: str,
        meta: dict,
        owner: str = "ops@mqi.example",
    ) -> None:
        now = self.now
        key = meta.get("screenId") or meta.get("feed") or meta.get("campaignId") or ""
        if key:
            existing = db.query_one(
                "SELECT id FROM incidents WHERE kind = ? AND status != 'resolved' AND meta_json LIKE ?",
                (kind, f"%{key}%"),
            )
            if existing:
                return
        db.execute(
            "INSERT INTO incidents(kind, severity, owner, status, title, message, created, updated, meta_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (kind, severity, owner, "open", title, message, iso(now), iso(now), db.json_dumps(meta)),
        )
        self.bus.publish("incident", {"kind": kind, "severity": severity, "title": title})

    def _check_incidents(self, now: datetime) -> None:
        for row in db.query("SELECT id, status, last_seen FROM screens WHERE status = 'offline'"):
            last_seen = parse_time(row["last_seen"])
            if last_seen and (now - last_seen).total_seconds() >= 300:
                self._raise_incident(
                    "screen_offline", "high", f"Screen {row['id']} offline",
                    "No heartbeat for more than 5 minutes. Playlist paused; fallback poster active.",
                    {"screenId": row["id"]},
                )
        for row in db.query("SELECT id, status, last_seen FROM screens WHERE status = 'degraded'"):
            last_seen = parse_time(row["last_seen"])
            if last_seen and (now - last_seen).total_seconds() >= 300:
                self._raise_incident(
                    "creative_failure", "medium", f"Creative render degraded on {row['id']}",
                    "Playlist fallback active after repeated creative render failures.",
                    {"screenId": row["id"]}, owner="media@mqi.example",
                )
        for feed, label in (("aodb", "AODB"), ("aidx", "AIDX"), ("acris", "ACRIS")):
            last = parse_time(db.get_meta(f"feed_last_{feed}"))
            if last and (now - last).total_seconds() >= 180:
                lag = int((now - last).total_seconds())
                self._raise_incident(
                    "feed_lag", "medium", f"{label} feed lag {lag}s",
                    f"No {label} message for {lag}s. Decisions will reject stale evidence and fall back.",
                    {"feed": feed}, owner="platform@mqi.example",
                )
        active = db.query(
            "SELECT id, kind, meta_json FROM incidents "
            "WHERE status != 'resolved' AND kind IN ('screen_offline','creative_failure','feed_lag')"
        )
        for incident in active:
            meta = db.json_loads(incident["meta_json"], {})
            if incident["kind"] == "feed_lag":
                last = parse_time(db.get_meta(f"feed_last_{meta.get('feed', '')}"))
                healthy = bool(last and (now - last).total_seconds() < 180)
            else:
                screen = db.query_one("SELECT status FROM screens WHERE id = ?", (meta.get("screenId"),))
                healthy = bool(screen and screen["status"] == "online")
            if healthy:
                db.execute(
                    "UPDATE incidents SET status='resolved', updated=? WHERE id=?",
                    (iso(now), incident["id"]),
                )

    def _set_feed_heartbeats(self, now: datetime) -> None:
        if self._feed_stale:
            return
        for feed in ("aodb", "aidx", "acris"):
            db.set_meta(f"feed_last_{feed}", iso(now))


def _flight_model(row: dict[str, Any]):
    from ..models import Flight

    return Flight(
        flight_id=row["flight_id"], linked_flight_id=row["linked_id"], direction=row["direction"],
        airline_iata=row["airline"], airline_icao="", flight_number=row["flight_no"],
        callsign=row["callsign"], service_type=row["service_type"], flight_nature=row["nature"],
        origin=row["origin"], destination=row["destination"], via=row["via"],
        terminal=row["terminal"], scheduled=parse_time(row["std"]), estimated=parse_time(row["etd"] or row["eta"]),
        estimated_landing=parse_time(row["eldt"]), estimated_takeoff=parse_time(row["etot"]),
        actual_landing=parse_time(row["aldt"]), actual_takeoff=parse_time(row["atot"]),
        aibt=parse_time(row["aibt"]), aobt=parse_time(row["aobt"]), tobt=parse_time(row["tobt"]),
        tsat=parse_time(row["tsat"]), stand=row["stand"], gate=row["gate"],
        checkin_counters=row["counters"], baggage_belt=row["belt"],
        aircraft_reg=row["registration"], aircraft_type_icao=row["aircraft_type"],
        seats=row["seats"], pax_total=row["pax"], status=row["status"],
        delay_codes=row["delay_codes"], codeshares=row["codeshares"], handler=row["handler"],
        last_update=parse_time(row["updated"]), profile={},
    )