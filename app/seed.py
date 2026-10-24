"""Seed the SQLite database and write adapter-shaped fixture files.

Run ``python -m app.seed --reset`` to rebuild deterministically.  The generator
creates 900 flights, 180 screens, 40 outlets, 22 advertisers (10 airlines),
25 campaigns and 30 days of campaign history for the fictional MQI airport.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone

from . import db
from .adapters.acris import build_entities
from .config import ROOT, settings
from .models import iso
from .seed_airport import airport_structure, build_screens, generate_flights, generate_queues
from .seed_business import build_business

DATA = ROOT / "data"
SEED_VERSION = "mqi-2026-10-24.5"

AODB_COLUMNS = [
    "aodb_flight_id", "linked_flight_id", "direction", "airline_iata", "airline_icao",
    "flight_number", "callsign", "service_type", "flight_nature", "origin",
    "destination", "via", "terminal", "STA_STD", "ETA_ETD", "ELDT_ETOT",
    "ALDT_ATOT", "AIBT_AOBT", "TOBT", "TSAT", "stand", "gate", "checkin_counters",
    "baggage_belt", "aircraft_reg", "aircraft_type_icao", "seats", "pax_total",
    "status", "delay_codes", "codeshares", "handler", "last_update_utc",
]


def build() -> dict:
    sim_day = settings.sim_start.date()
    rng = random.Random(settings.seed)
    terminals, zones, gates, airlines, aircraft = airport_structure()
    screens = build_screens(zones, gates, rng)
    flights, demo = generate_flights(sim_day, gates, rng)
    queues = generate_queues(sim_day, zones, rng)
    business = build_business(sim_day, zones, screens, flights, demo, rng)
    return {
        "terminals": terminals,
        "zones": zones,
        "gates": gates,
        "airlines": airlines,
        "aircraft": aircraft,
        "screens": screens,
        "flights": flights,
        "queues": queues,
        "demo": demo,
        **business,
    }


def write_fixtures(data: dict) -> None:
    sim_day = settings.sim_start.date().isoformat()
    aodb_path = DATA / "aodb" / f"flights_{sim_day}.csv"
    aodb_path.parent.mkdir(parents=True, exist_ok=True)
    with aodb_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AODB_COLUMNS)
        writer.writeheader()
        for flight in data["flights"]:
            writer.writerow(_aodb_row(flight))
    acris_path = DATA / "acris" / "entities.json"
    acris_path.parent.mkdir(parents=True, exist_ok=True)
    entities = build_entities(
        data["zones"],
        [
            {
                "zone_id": row["zone_id"],
                "checkpoint": row["checkpoint"],
                "queue_len": row["queue_len"],
                "wait_min": row["wait_min"],
                "ts": iso(row["ts"]),
            }
            for row in data["queues"]
        ],
    )
    acris_path.write_text(json.dumps(entities, ensure_ascii=False, indent=1), encoding="utf-8")
    aidx_dir = DATA / "aidx"
    aidx_dir.mkdir(parents=True, exist_ok=True)
    reference = ROOT / "samples" / "aidx_reference_arrival.xml"
    if reference.exists():
        (aidx_dir / "reference_arrival.xml").write_text(reference.read_text(encoding="utf-8"), encoding="utf-8")


def seed_all(force: bool = False) -> bool:
    db.migrate()
    if not force and db.get_meta("seed_version") == SEED_VERSION:
        return False
    if force:
        _clear()
    data = build()
    write_fixtures(data)
    _insert(data)
    db.set_meta("seed_version", SEED_VERSION)
    db.set_meta("seeded_at", iso(datetime.now(timezone.utc)))
    db.set_meta("sim_date", settings.sim_start.date().isoformat())
    db.set_meta("sim_start", iso(settings.sim_start))
    db.set_meta("airport_code", settings.airport_code)
    db.set_meta("demo_flight_dxb", data["demo"]["dxb"]["flight_id"])
    db.set_meta("demo_flight_beach", data["demo"]["beach"]["flight_id"])
    db.set_meta("demo_flight_gulf", data["demo"]["gulf"]["flight_id"])
    return True


def _clear() -> None:
    tables = [
        "decisions",
        "impressions", "redemptions", "promos", "daily_stats", "segment_stats",
        "incidents", "reports", "packages", "marketplace", "campaigns", "creatives",
        "outlets", "advertisers", "queues", "flight_events", "flights", "screens",
        "gates", "zones", "terminals", "airlines", "aircraft_types", "rules", "meta",
    ]
    with db.transaction() as conn:
        for table in tables:
            # `tables` is a closed static list declared above, never request input.
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query, python.lang.security.audit.formatted-sql-query.formatted-sql-query
            conn.execute(f"DELETE FROM {table}")


def _insert(data: dict) -> None:
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO airlines(iata, icao, name, market, color, is_partner) VALUES (?,?,?,?,?,1)",
            [(a["iata"], a["icao"], a["name"], a["market"], a["color"]) for a in data["airlines"]],
        )
        conn.executemany(
            "INSERT INTO aircraft_types(icao, name, seats, widebody) VALUES (?,?,?,?)",
            [(a[0], a[1], a[2], a[3]) for a in data["aircraft"]],
        )
        conn.executemany(
            "INSERT INTO terminals(id, name, concourses) VALUES (?,?,?)",
            [(t["id"], t["name"], t["concourses"]) for t in data["terminals"]],
        )
        conn.executemany(
            "INSERT INTO zones(id, terminal_id, name, concourse, kind, gates_json, x, y, w, h) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (z["id"], z["terminal_id"], z["name"], z["concourse"], z["kind"],
                 db.json_dumps(z["gates"]), z["x"], z["y"], z["w"], z["h"])
                for z in data["zones"]
            ],
        )
        conn.executemany(
            "INSERT INTO gates(code, zone_id, terminal_id, x, y) VALUES (?,?,?,?,?)",
            [(g["code"], g["zone_id"], g["terminal_id"], g["x"], g["y"]) for g in data["gates"]],
        )
        now = settings.sim_start
        conn.executemany(
            "INSERT INTO screens(id, name, zone_id, nearest_gates_json, aspect, orientation, "
            "size_inches, status, latency_ms, last_seen, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    screen["id"], screen["name"], screen["zone_id"],
                    db.json_dumps(screen["nearest_gates"]), screen["aspect"],
                    screen["orientation"], screen["size_inches"], screen["status"],
                    screen["latency_ms"],
                    iso(_last_seen(now, screen["status"], index)),
                    screen["category"],
                )
                for index, screen in enumerate(data["screens"])
            ],
        )
        conn.executemany(
            "INSERT INTO flights(flight_id, linked_id, direction, airline, flight_no, callsign, "
            "service_type, nature, origin, destination, via, terminal, std, eta, etd, eldt, "
            "etot, aldt, atot, aibt, aobt, tobt, tsat, stand, gate, counters, belt, "
            "registration, aircraft_type, seats, pax, status, delay_codes, codeshares, "
            "handler, updated, profile_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [_flight_values(f) for f in data["flights"]],
        )
        conn.executemany(
            "INSERT INTO queues(zone_id, checkpoint, queue_len, wait_min, ts, source) "
            "VALUES (?,?,?,?,?,'ACRIS')",
            [(q["zone_id"], q["checkpoint"], q["queue_len"], q["wait_min"], iso(q["ts"])) for q in data["queues"]],
        )
        conn.executemany(
            "INSERT INTO advertisers(id, name, kind, color, contact, created) VALUES (?,?,?,?,?,?)",
            [(a["id"], a["name"], a["kind"], a["color"], a["contact"], iso(a["created"])) for a in data["advertisers"]],
        )
        conn.executemany(
            "INSERT INTO outlets(id, advertiser_id, name, zone_id, category, stock_status, created) "
            "VALUES (?,?,?,?,?,?,?)",
            [(o["id"], o["advertiser_id"], o["name"], o["zone_id"], o["category"], o["stock_status"], iso(o["created"])) for o in data["outlets"]],
        )
        conn.executemany(
            "INSERT INTO creatives(id, advertiser_id, name, headline_en, headline_zh, body_en, "
            "body_zh, cta_en, cta_zh, template, colors_json, image, category, status, created) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (c["id"], c["advertiser_id"], c["name"], c["headline_en"], c["headline_zh"],
                 c["body_en"], c["body_zh"], c["cta_en"], c["cta_zh"], c["template"],
                 db.json_dumps(c["colors"]), c["image"], c["category"], c["status"], iso(c["created"]))
                for c in data["creatives"]
            ],
        )
        conn.executemany(
            "INSERT INTO campaigns(id, advertiser_id, creative_id, name, status, start, end, "
            "daypart_json, budget, daily_cap, freq_cap_min, bid, segments_json, filters_json, "
            "placement_json, triggers_json, spend, impressions, scans, redemptions, revenue, "
            "conversion, created, notes, priority, ab_group, category) VALUES (?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,0,0,0,0,0,0,?,?,?,?,?)",
            [
                (c["id"], c["advertiser_id"], c["creative_id"], c["name"], c["status"],
                 iso(c["start"]), iso(c["end"]), db.json_dumps(c["daypart"]), c["budget"],
                 c["daily_cap"], c["freq_cap_min"], c["bid"], db.json_dumps(c["segments"]),
                 db.json_dumps(c["filters"]), db.json_dumps(c["placement"]),
                 db.json_dumps(c["triggers"]), iso(c["created"]), c["notes"], c["priority"],
                 c["ab_group"], c["category"])
                for c in data["campaigns"]
            ],
        )
        conn.executemany(
            "INSERT INTO daily_stats(campaign_id, day, impressions, scans, redemptions, revenue, spend) "
            "VALUES (?,?,?,?,?,?,?)",
            data["daily_stats"],
        )
        conn.executemany(
            "INSERT INTO segment_stats(campaign_id, segment, impressions, scans, redemptions, revenue) "
            "VALUES (?,?,?,?,?,?)",
            data["segment_stats"],
        )
        conn.executemany(
            "INSERT INTO promos(id, campaign_id, code, flight_id, valid_from, valid_until, max_uses, "
            "uses, parent_code, status, label, value) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (p["id"], p["campaign_id"], p["code"], p["flight_id"], iso(p["valid_from"]),
                 iso(p["valid_until"]), p["max_uses"], p["uses"], p["parent_code"],
                 p["status"], p["label"], p["value"])
                for p in data["promos"]
            ],
        )
        conn.executemany(
            "INSERT INTO incidents(kind, severity, owner, status, title, message, created, updated, meta_json) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (i["kind"], i["severity"], i["owner"], i["status"], i["title"],
                 i["message"], iso(i["created"]), iso(i["updated"]), db.json_dumps(i["meta"]))
                for i in data["incidents"]
            ],
        )
        conn.executemany(
            "INSERT INTO rules(key, value_json, updated) VALUES (?,?,?)",
            [(key, db.json_dumps(value), iso(datetime.now(timezone.utc))) for key, value in data["rules"].items()],
        )
        conn.executemany(
            "INSERT INTO packages(id, name, screen_ids_json, price, description, created) "
            "VALUES (?,?,?,?,?,?)",
            [
                (p["id"], p["name"], db.json_dumps(p["screen_ids"]), p["price"],
                 p["description"], iso(p["created"]))
                for p in data["packages"]
            ],
        )
        conn.executemany(
            "INSERT INTO marketplace(id, retailer_id, airline, title, offer, status, created) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (m["id"], m["retailer_id"], m["airline"], m["title"], m["offer"],
                 m["status"], iso(m["created"]))
                for m in data["marketplace"]
            ],
        )


def _last_seen(now: datetime, status: str, index: int) -> datetime:
    if status == "offline":
        return now - timedelta(minutes=8 + index % 9)
    if status == "degraded":
        return now - timedelta(seconds=25 + index % 30)
    return now - timedelta(seconds=2 + index % 8)


def _aodb_row(flight: dict) -> dict:
    arrival = flight["direction"] == "A"
    estimate = flight.get("estimated") or flight["std"]
    movement = flight.get("actual") or estimate
    return {
        "aodb_flight_id": flight["flight_id"],
        "linked_flight_id": flight["linked_id"],
        "direction": flight["direction"],
        "airline_iata": flight["airline"],
        "airline_icao": _airline_icao(flight["airline"]),
        "flight_number": flight["flight_no"],
        "callsign": flight["callsign"],
        "service_type": flight["service_type"],
        "flight_nature": flight["nature"],
        "origin": flight["origin"],
        "destination": flight["destination"],
        "via": flight["via"],
        "terminal": flight["terminal"],
        "STA_STD": iso(flight["std"]),
        "ETA_ETD": iso(estimate),
        "ELDT_ETOT": iso(movement),
        "ALDT_ATOT": iso(flight.get("actual")),
        "AIBT_AOBT": iso(movement if not arrival else flight.get("actual")),
        "TOBT": iso(flight["std"] - timedelta(minutes=25)),
        "TSAT": iso(flight["std"] - timedelta(minutes=20)),
        "stand": flight["stand"],
        "gate": flight["gate"],
        "checkin_counters": flight["counters"],
        "baggage_belt": flight["belt"],
        "aircraft_reg": flight["registration"],
        "aircraft_type_icao": flight["aircraft_type"],
        "seats": flight["seats"],
        "pax_total": flight["pax"],
        "status": flight["status"],
        "delay_codes": flight["delay_codes"],
        "codeshares": flight["codeshares"],
        "handler": flight["handler"],
        "last_update_utc": iso(flight["updated"]),
    }


def _flight_values(flight: dict) -> tuple:
    arrival = flight["direction"] == "A"
    estimate = flight.get("estimated") or flight["std"]
    movement = estimate
    return (
        flight["flight_id"], flight["linked_id"], flight["direction"], flight["airline"],
        flight["flight_no"], flight["callsign"], flight["service_type"], flight["nature"],
        flight["origin"], flight["destination"], flight["via"], flight["terminal"],
        iso(flight["std"]), iso(estimate) if arrival else None, None if arrival else iso(estimate),
        iso(movement) if arrival else None, None if arrival else iso(movement),
        iso(flight.get("actual")) if arrival else None, None if arrival else iso(flight.get("actual")),
        iso(flight.get("actual")) if arrival else None, None if arrival else iso(flight.get("actual")),
        iso(flight["std"] - timedelta(minutes=25)), iso(flight["std"] - timedelta(minutes=20)),
        flight["stand"], flight["gate"], flight["counters"], flight["belt"],
        flight["registration"], flight["aircraft_type"], flight["seats"], flight["pax"],
        flight["status"], flight["delay_codes"], flight["codeshares"], flight["handler"],
        iso(flight["updated"]), db.json_dumps(flight["profile"]),
    )


def _airline_icao(iata: str) -> str:
    from .seed_airport import AIRLINES

    for airline in AIRLINES:
        if airline["iata"] == iata:
            return airline["icao"]
    return "MQI"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Meridian Media OS")
    parser.add_argument("--reset", action="store_true", help="clear and regenerate")
    args = parser.parse_args()
    changed = seed_all(force=args.reset)
    print("seeded" if changed else "already seeded", settings.db_path)


if __name__ == "__main__":
    main()