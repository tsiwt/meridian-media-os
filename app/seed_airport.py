"""Deterministic airport fixture generator.

Produces one operating day at the fictional Meridian International (MQI) with
the same shapes as the challenge reference data: 33-column AODB legs, AIDX
messages and ACRIS NGSI-LD entities.  Profiles are generated per flight with
plausible, route/time based mixes (the challenge explicitly asks for this).
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

TERMINALS = [
    {"id": "T1", "name": "Terminal 1 · Domestic", "concourses": "A,B"},
    {"id": "T2", "name": "Terminal 2 · International", "concourses": "D,E,F"},
]

ZONES: list[dict[str, Any]] = [
    {"id": "T1-A", "terminal_id": "T1", "name": "Concourse A · Gates 1–8", "concourse": "A", "kind": "gate", "gates": [str(i) for i in range(1, 9)], "x": 80, "y": 110, "w": 140, "h": 160},
    {"id": "T1-B", "terminal_id": "T1", "name": "Concourse B · Gates 9–16", "concourse": "B", "kind": "gate", "gates": [str(i) for i in range(9, 17)], "x": 230, "y": 110, "w": 140, "h": 160},
    {"id": "T1-C", "terminal_id": "T1", "name": "Concourse C · Gates 17–24", "concourse": "C", "kind": "gate", "gates": [str(i) for i in range(17, 25)], "x": 380, "y": 110, "w": 140, "h": 160},
    {"id": "T1-RETAIL", "terminal_id": "T1", "name": "Market Lane", "concourse": "A", "kind": "retail", "gates": [str(i) for i in range(1, 25)], "x": 80, "y": 290, "w": 200, "h": 80},
    {"id": "T1-FOOD", "terminal_id": "T1", "name": "Harbour Food Court", "concourse": "B", "kind": "food", "gates": [str(i) for i in range(1, 25)], "x": 290, "y": 290, "w": 150, "h": 80},
    {"id": "T1-SEC", "terminal_id": "T1", "name": "Central Security", "concourse": "B", "kind": "security", "gates": [str(i) for i in range(1, 25)], "x": 80, "y": 390, "w": 200, "h": 60},
    {"id": "T1-LOUNGE", "terminal_id": "T1", "name": "Northgate Lounge", "concourse": "C", "kind": "lounge", "gates": [str(i) for i in range(17, 25)], "x": 290, "y": 390, "w": 150, "h": 60},
    {"id": "T2-D", "terminal_id": "T2", "name": "Concourse D · Gates 25–32", "concourse": "D", "kind": "gate", "gates": [str(i) for i in range(25, 33)], "x": 640, "y": 110, "w": 150, "h": 160},
    {"id": "T2-E", "terminal_id": "T2", "name": "Concourse E · Gates 33–39", "concourse": "E", "kind": "gate", "gates": [str(i) for i in range(33, 40)], "x": 800, "y": 110, "w": 150, "h": 160},
    {"id": "T2-F", "terminal_id": "T2", "name": "Concourse F · Gates 40–48", "concourse": "F", "kind": "gate", "gates": [str(i) for i in range(40, 49)], "x": 960, "y": 110, "w": 160, "h": 160},
    {"id": "T2-DUTY", "terminal_id": "T2", "name": "Duty Free Boulevard", "concourse": "F", "kind": "retail", "gates": [str(i) for i in range(40, 49)], "x": 640, "y": 290, "w": 220, "h": 80},
    {"id": "T2-FOOD", "terminal_id": "T2", "name": "Skyline Food Court", "concourse": "E", "kind": "food", "gates": [str(i) for i in range(33, 49)], "x": 870, "y": 290, "w": 150, "h": 80},
    {"id": "T2-SEC", "terminal_id": "T2", "name": "International Security", "concourse": "D", "kind": "security", "gates": [str(i) for i in range(25, 49)], "x": 640, "y": 390, "w": 200, "h": 60},
    {"id": "T2-LOUNGE", "terminal_id": "T2", "name": "Meridian Sky Lounge", "concourse": "F", "kind": "lounge", "gates": [str(i) for i in range(40, 49)], "x": 870, "y": 390, "w": 150, "h": 60},
    {"id": "ARRIVALS", "terminal_id": "T2", "name": "Arrivals Hall", "concourse": "F", "kind": "arrivals", "gates": [str(i) for i in range(25, 49)], "x": 1040, "y": 290, "w": 80, "h": 160},
]

AIRLINES = [
    {"iata": "XD", "icao": "SKJ", "name": "Skylark Air", "market": "Domestic low-cost", "color": "#38e8c8"},
    {"iata": "YA", "icao": "AUQ", "name": "Aurora National Airlines", "market": "Domestic full-service", "color": "#8b7bff"},
    {"iata": "YN", "icao": "KSQ", "name": "Kestrel Air", "market": "Domestic low-cost", "color": "#c9f45b"},
    {"iata": "XU", "icao": "CWQ", "name": "Coralwing Express", "market": "Domestic low-cost", "color": "#4cc9f0"},
    {"iata": "YF", "icao": "SVZ", "name": "Sunvale Airlines", "market": "Domestic low-cost", "color": "#ffb454"},
    {"iata": "ZO", "icao": "SLQ", "name": "Solano Airways", "market": "International", "color": "#ff647c"},
    {"iata": "XH", "icao": "HCZ", "name": "Halcyon Airways", "market": "International", "color": "#f4d35e"},
    {"iata": "YG", "icao": "ACZ", "name": "Alpine Continental", "market": "International", "color": "#60a5fa"},
    {"iata": "XI", "icao": "CRU", "name": "Crescent Airways", "market": "International", "color": "#34d399"},
    {"iata": "YU", "icao": "LPZ", "name": "Lumen Pacific Airlines", "market": "International", "color": "#e879f9"},
]

AIRCRAFT = [
    ("A359", "Airbus A350-900", 283, 1),
    ("B38M", "Boeing 737 MAX 8", 189, 0),
    ("A320", "Airbus A320neo", 180, 0),
    ("A21N", "Airbus A321neo", 220, 0),
    ("B748", "Boeing 747-8", 364, 1),
    ("B789", "Boeing 787-9", 290, 1),
    ("A333", "Airbus A330-300", 300, 1),
    ("E195", "Embraer E195", 120, 0),
    ("ATR7", "ATR 72-600", 70, 0),
]

CITIES = {
    "ADN": ("Aldmere", "Domestic", "domestic", "en", "GB", 0),
    "BWZ": ("Brightwater", "Domestic", "domestic", "en", "GB", 0),
    "CBP": ("Calder Bay", "Domestic", "coast", "en", "GB", 1),
    "CPZ": ("Coralport", "Domestic", "coast", "en", "GB", 1),
    "DMQ": ("Dunmore", "Domestic", "domestic", "en", "GB", 0),
    "EHQ": ("Eastholm", "Domestic", "domestic", "en", "GB", 0),
    "FHQ": ("Fairhaven", "Domestic", "domestic", "en", "GB", 0),
    "GRH": ("Glenrock", "Domestic", "domestic", "en", "GB", 0),
    "GSZ": ("Goldsand", "Domestic", "coast", "en", "GB", 1),
    "HCX": ("Highcliff", "Domestic", "domestic", "en", "GB", 0),
    "IVQ": ("Ironvale", "Domestic", "domestic", "en", "GB", 0),
    "JFQ": ("Juniper Falls", "Domestic", "domestic", "en", "GB", 0),
    "LMW": ("Lakemont", "Domestic", "domestic", "en", "GB", 0),
    "NGV": ("Northgate", "Domestic", "domestic", "en", "GB", 0),
    "OKZ": ("Oakridge", "Domestic", "domestic", "en", "GB", 0),
    "BVQ": ("Belvista", "Europe", "city", "es", "ES", 0),
    "KST": ("Kastell", "Europe", "city", "de", "DE", 0),
    "NVQ": ("Novaterra", "Europe", "city", "it", "IT", 0),
    "PVQ": ("Port Valen", "Europe", "city", "fr", "FR", 0),
    "SCJ": ("Santa Corvina", "Europe", "beach", "es", "ES", 1),
    "SMG": ("Solmara", "Gulf", "city", "ar", "AE", 0),
    "ZHQ": ("Zarhan", "Gulf", "city", "ar", "SA", 0),
    "DXB": ("Dubai", "Gulf", "city", "ar", "AE", 0),
    "LHR": ("London", "Europe", "city", "en", "GB", 0),
    "SIN": ("Singapore", "Asia", "city", "zh", "SG", 0),
    "IST": ("Istanbul", "Europe", "city", "tr", "TR", 0),
    "JFK": ("New York", "Americas", "city", "en", "US", 0),
    "BCN": ("Barcelona", "Europe", "beach", "es", "ES", 1),
}

DOMESTIC = [code for code, info in CITIES.items() if info[2] in {"domestic", "coast"}]
INTERNATIONAL = [code for code, info in CITIES.items() if info[2] not in {"domestic", "coast"}]
BEACH = {code for code, info in CITIES.items() if info[5]}

SCREEN_STATUS_OFFLINE = {21, 77, 129, 171}
SCREEN_STATUS_DEGRADED = {7, 53, 111}


def airport_structure() -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    gates: list[dict] = []
    for zone in ZONES:
        if zone["kind"] != "gate":
            continue
        width = zone["w"] / max(1, len(zone["gates"]))
        for index, code in enumerate(zone["gates"]):
            gates.append(
                {
                    "code": code,
                    "zone_id": zone["id"],
                    "terminal_id": zone["terminal_id"],
                    "x": round(zone["x"] + width * (index + 0.5), 1),
                    "y": round(zone["y"] + zone["h"] - 18, 1),
                }
            )
    return TERMINALS, ZONES, gates, AIRLINES, AIRCRAFT


def build_screens(zones: list[dict], gates: list[dict], rng: random.Random) -> list[dict]:
    gate_by_zone: dict[str, list[str]] = {}
    for gate in gates:
        gate_by_zone.setdefault(gate["zone_id"], []).append(gate["code"])
    screens: list[dict] = []
    plan = {
        "gate": 16,
        "retail": 22,
        "food": 12,
        "lounge": 5,
        "security": 2,
        "arrivals": 2,
    }
    counter = 1
    for zone in zones:
        count = plan.get(zone["kind"], 4)
        zone_gates = gate_by_zone.get(zone["id"]) or zone["gates"]
        for index in range(count):
            screen_id = f"SCR-{counter:03d}"
            nearest = _nearest_gates(zone_gates, index, min(3, len(zone_gates)))
            aspect = "9:16" if zone["kind"] in {"retail", "lounge"} else "16:9"
            status = "online"
            if counter in SCREEN_STATUS_OFFLINE:
                status = "offline"
            elif counter in SCREEN_STATUS_DEGRADED:
                status = "degraded"
            screens.append(
                {
                    "id": screen_id,
                    "name": f"{zone['id']} · {zone['name']} · S{index + 1:02d}",
                    "zone_id": zone["id"],
                    "nearest_gates": nearest,
                    "aspect": aspect,
                    "orientation": "portrait" if aspect == "9:16" else "landscape",
                    "size_inches": rng.choice([43, 49, 55, 65, 75]),
                    "status": status,
                    "latency_ms": rng.randint(90, 320) if status == "degraded" else rng.randint(28, 140),
                    "category": zone["kind"],
                }
            )
            counter += 1
    return screens


def _nearest_gates(zone_gates: list[str], index: int, count: int) -> list[str]:
    if not zone_gates:
        return []
    rotated = zone_gates[index % len(zone_gates):] + zone_gates[: index % len(zone_gates)]
    return rotated[:count]


def generate_flights(
    sim_day: date,
    gates: list[dict],
    rng: random.Random,
    total: int = 900,
) -> tuple[list[dict], dict[str, dict]]:
    """Return canonical flight rows plus the three demo flights keyed by role."""
    gate_codes = [gate["code"] for gate in gates]
    gate_zone = {gate["code"]: gate["zone_id"] for gate in gates}
    day_start = datetime.combine(sim_day, time(0, 0), tzinfo=timezone.utc)
    sim_start = datetime.combine(sim_day, time(13, 55), tzinfo=timezone.utc)
    departures: list[dict] = []
    demo: dict[str, dict] = {}

    def add_departure(
        airline: str,
        number: str,
        destination: str,
        scheduled: datetime,
        gate: str,
        pax: int,
        *,
        delay: int = 0,
        status: str | None = None,
        seats: int | None = None,
        link_id: str | None = None,
        demo_key: str | None = None,
        aircraft: str | None = None,
    ) -> dict:
        nature = "I" if destination in INTERNATIONAL else "D"
        info = CITIES[destination]
        seats = seats or _seats_for(rng, nature)
        flight = {
            "flight_id": link_id or str(300000 + len(departures) * 2),
            "linked_id": str(int(link_id or str(300000 + len(departures) * 2)) + 1),
            "direction": "D",
            "airline": airline,
            "flight_no": number,
            "callsign": f"{_icao(airline)}{number}",
            "service_type": "J",
            "nature": nature,
            "origin": "MQI",
            "destination": destination,
            "via": "",
            "terminal": "T2" if nature == "I" else "T1",
            "std": scheduled,
            "estimated": scheduled + timedelta(minutes=delay) if delay else scheduled,
            "gate": gate,
            "zone_id": gate_zone.get(gate, "T2-F"),
            "seats": seats,
            "pax": pax,
            "status": status or ("DEL" if delay else "SCH"),
            "delay_codes": "11" if delay else "",
            "aircraft_type": aircraft or _aircraft_for(rng, nature),
            "registration": f"Q{rng.choice('ABCDEFGH')}-{rng.choice('ABCDEFGH')}{rng.choice('ABCDEFGH')}",
            "handler": rng.choice(["Meridian Ground Services", "Harbor Aviation Services", "Compass Ground Handling", "Skylark self-handling"]),
            "stand": f"{rng.choice('ABCDEFGH')}{rng.randint(1, 20)}",
            "counters": f"{rng.randint(10, 90)}-{rng.randint(91, 99)}",
            "belt": str(rng.randint(1, 12)),
            "codeshares": "",
            "updated": sim_start - timedelta(seconds=rng.randint(20, 240)),
            "profile": make_profile(nature, destination, airline, scheduled, seats, pax, rng),
            "arrival_destination": info[0],
        }
        departures.append(flight)
        if demo_key:
            demo[demo_key] = flight
        return flight

    add_departure("ZO", "501", "DXB", day_start + timedelta(hours=14, minutes=20), "42", 240, delay=45, seats=283, aircraft="A359", demo_key="dxb")
    add_departure("YU", "88", "SCJ", day_start + timedelta(hours=14, minutes=40), "41", 180, seats=189, aircraft="B38M", demo_key="beach")
    add_departure("XH", "960", "ZHQ", day_start + timedelta(hours=14, minutes=35), "43", 224, seats=283, aircraft="A359", demo_key="gulf")

    used_numbers: set[tuple[str, str]] = {("ZO", "501"), ("YU", "88"), ("XH", "960")}
    gate_slots: dict[str, list[tuple[datetime, datetime]]] = {}
    for flight in departures:
        gate_slots.setdefault(flight["gate"], []).append(
            (flight["std"] - timedelta(minutes=25), flight["std"] + timedelta(minutes=35))
        )
    peak_hours = [6, 7, 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21]
    while len(departures) < total // 2:
        if rng.random() < 0.62:
            hour = rng.choice(peak_hours)
        else:
            hour = rng.randrange(0, 24)
        scheduled = day_start + timedelta(
            hours=hour, minutes=rng.randrange(0, 60), seconds=0
        )
        nature = "I" if rng.random() < 0.46 else "D"
        airline = rng.choice([a["iata"] for a in AIRLINES if (a["market"].startswith("International")) == (nature == "I")])
        number = f"{rng.randint(100, 989)}"
        if (airline, number) in used_numbers:
            continue
        used_numbers.add((airline, number))
        destination = rng.choice(INTERNATIONAL if nature == "I" else DOMESTIC)
        terminal_gates = [g for g in gate_codes if (int(g) >= 25) == (nature == "I")]
        gate = _pick_gate(terminal_gates, scheduled, gate_slots, rng)
        delay = 0
        if rng.random() < 0.11:
            delay = rng.choice([15, 20, 25, 30, 40, 45, 55, 75, 95])
        status = None
        if rng.random() < 0.008:
            status = "CNL"
        pax = 0 if status == "CNL" else int(_seats_for(rng, nature) * rng.uniform(0.55, 0.98))
        add_departure(
            airline,
            number,
            destination,
            scheduled,
            gate,
            pax,
            delay=delay,
            status=status,
        )

    arrivals: list[dict] = []
    for departure in departures:
        block = rng.randint(85, 230) if departure["nature"] == "I" else rng.randint(50, 120)
        arrival_std = departure["std"] - timedelta(minutes=block)
        info = CITIES[departure["destination"]]
        arrival = dict(departure)
        arrival.update(
            {
                "flight_id": departure["linked_id"],
                "linked_id": departure["flight_id"],
                "direction": "A",
                "origin": departure["destination"],
                "destination": "MQI",
                "std": arrival_std,
                "estimated": arrival_std + timedelta(minutes=departure.get("delay_minutes", 0)),
                "status": "ARR" if arrival_std < sim_start else "SCH",
                "pax": int(departure["seats"] * rng.uniform(0.5, 0.96)),
                "profile": {},
            }
        )
        arrivals.append(arrival)

    flights = departures + arrivals
    for flight in flights:
        if not isinstance(flight.get("std"), datetime):
            raise ValueError("seed clock error")
        if flight["direction"] == "D":
            flight["delay_minutes"] = int(
                ((flight["estimated"] or flight["std"]) - flight["std"]).total_seconds() // 60
            )
        else:
            flight["delay_minutes"] = 0
    _apply_live_status(flights, sim_start, rng)
    return flights, demo


def _apply_live_status(flights: list[dict], sim_start: datetime, rng: random.Random) -> None:
    for flight in flights:
        scheduled = flight["std"]
        if flight["status"] == "CNL":
            continue
        if flight["direction"] == "D":
            if scheduled <= sim_start - timedelta(minutes=25):
                flight["status"] = "DEP"
                flight["actual"] = (flight["estimated"] or scheduled) + timedelta(minutes=rng.randint(1, 8))
            elif scheduled <= sim_start:
                flight["status"] = "BOD"
            elif flight.get("delay_minutes", 0) > 0:
                flight["status"] = "DEL"
            else:
                flight["status"] = "SCH"
        else:
            if scheduled <= sim_start - timedelta(minutes=10):
                flight["status"] = "ARR"
                flight["actual"] = (flight["estimated"] or scheduled) + timedelta(minutes=rng.randint(1, 6))
            else:
                flight["status"] = "SCH"


def _pick_gate(
    candidates: list[str],
    scheduled: datetime,
    slots: dict[str, list[tuple[datetime, datetime]]],
    rng: random.Random,
) -> str:
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    for gate in shuffled:
        busy = any(
            start - timedelta(minutes=15) <= scheduled <= end + timedelta(minutes=15)
            for start, end in slots.get(gate, [])
        )
        if not busy:
            slots.setdefault(gate, []).append(
                (scheduled - timedelta(minutes=25), scheduled + timedelta(minutes=35))
            )
            return gate
    gate = rng.choice(candidates)
    slots.setdefault(gate, []).append((scheduled - timedelta(minutes=25), scheduled + timedelta(minutes=35)))
    return gate


def _seats_for(rng: random.Random, nature: str) -> int:
    if nature == "I":
        return rng.choice([283, 290, 300, 364, 220, 189])
    return rng.choice([189, 180, 220, 120, 70, 189])


def _aircraft_for(rng: random.Random, nature: str) -> str:
    choices = [item[0] for item in AIRCRAFT if (item[3] == 1) == (nature == "I")]
    return rng.choice(choices)


def _icao(iata: str) -> str:
    for airline in AIRLINES:
        if airline["iata"] == iata:
            return airline["icao"]
    return "MQI"


def make_profile(
    nature: str,
    destination: str,
    airline: str,
    scheduled: datetime,
    seats: int,
    pax: int,
    rng: random.Random,
) -> dict[str, Any]:
    info = CITIES[destination]
    weekday = scheduled.weekday()
    hour = scheduled.hour
    beach = destination in BEACH
    purpose = {"business": 0.18, "holiday": 0.24, "vfr": 0.26, "student": 0.12, "religious": 0.06}
    if nature == "D" and weekday < 5 and 6 <= hour <= 9:
        purpose = {"business": 0.55, "holiday": 0.08, "vfr": 0.22, "student": 0.12, "religious": 0.03}
    elif beach and (weekday >= 4 or hour >= 16):
        purpose = {"business": 0.06, "holiday": 0.62, "vfr": 0.16, "student": 0.12, "religious": 0.04}
    elif weekday >= 5:
        purpose = {"business": 0.09, "holiday": 0.40, "vfr": 0.31, "student": 0.14, "religious": 0.06}
    if info[1] == "Gulf":
        purpose["religious"] += 0.07
        purpose["vfr"] += 0.05
    purpose = _normalize(purpose)

    holiday = purpose["holiday"]
    family_share = 0.12 + holiday * 0.55 + (0.08 if beach else 0)
    party = {
        "solo": max(0.06, 0.34 - holiday * 0.2),
        "couple": 0.28 + (0.06 if holiday > 0.4 else 0),
        "family": min(0.58, family_share),
        "group": max(0.04, purpose["student"] * 0.8 + purpose["vfr"] * 0.12),
    }
    party = _normalize(party)

    business = purpose["business"]
    young = purpose["student"] + party["solo"] * 0.25
    age = {
        "under12": party["family"] * 0.42,
        "12_17": party["family"] * 0.18,
        "18_24": 0.09 + young * 0.25,
        "25_34": 0.17 + business * 0.16,
        "35_44": 0.17 + business * 0.20 + party["family"] * 0.12,
        "45_54": 0.14 + business * 0.22,
        "55plus": 0.11 + purpose["vfr"] * 0.14 + (0.06 if weekday < 5 else 0),
    }
    age = _normalize(age)
    female = 0.48 + holiday * 0.04 + (0.01 if beach else 0)
    gender = {"female": min(0.58, female), "male": 1 - min(0.58, female)}

    widebody = seats >= 280
    business_cabin = (0.16 if widebody and nature == "I" else 0.02) + business * 0.10
    premium = (0.07 if widebody and nature == "I" else 0.02) + business * 0.05
    cabin = {"economy": 1 - business_cabin - premium, "premium": premium, "business": business_cabin}
    cabin = _normalize(cabin)

    nationality = {info[4]: 0.52 if nature == "I" else 0.78, "GB": 0.24 if nature == "I" else 0.16}
    if info[1] == "Gulf":
        nationality["AE"] = 0.12
        nationality["SA"] = 0.08
    elif info[1] == "Europe":
        nationality["FR"] = 0.06
        nationality["DE"] = 0.06
    else:
        nationality["US"] = 0.05
    nationality = _normalize(nationality)
    language = {info[3]: 0.62 if nature == "I" else 0.82, "en": 0.30 if nature == "I" else 0.16}
    language = _normalize(language)

    luxury = min(1.0, cabin["business"] * 2.2 + cabin["premium"] * 0.9 + (0.08 if info[1] == "Gulf" else 0))
    shares = {
        "international": 1.0 if nature == "I" else 0.0,
        "domestic": 0.0 if nature == "I" else 1.0,
        "holiday": holiday,
        "business": business,
        "vfr": purpose["vfr"],
        "student": purpose["student"],
        "religious": purpose["religious"],
        "family": party["family"],
        "couple": party["couple"],
        "solo": party["solo"],
        "group": party["group"],
        "young": age["18_24"] + age["25_34"] + age["under12"] * 0.2,
        "senior": age["55plus"],
        "luxury": luxury,
        "value": max(0.0, 1 - luxury) * 0.8 + party["family"] * 0.2,
        "gourmet": min(1.0, holiday * 0.35 + party["couple"] * 0.3 + luxury * 0.3),
        "wellness": min(1.0, purpose["vfr"] * 0.25 + age["55plus"] * 0.5 + holiday * 0.15),
        "tech": min(1.0, business * 0.6 + purpose["student"] * 0.5 + 0.18),
        "beach": 0.75 if beach else 0.12,
        "shopper": min(1.0, holiday * 0.5 + party["family"] * 0.25 + luxury * 0.30),
    }
    return {
        "flightKey": f"{airline}{destination}{scheduled.strftime('%H%M')}",
        "routeType": "international" if nature == "I" else "domestic",
        "destinationCity": info[0],
        "destinationCountry": info[1],
        "purpose": purpose,
        "party": party,
        "age": age,
        "gender": gender,
        "cabin": cabin,
        "nationality": nationality,
        "language": language,
        "spendTier": {"high": luxury, "mid": 0.55, "value": max(0.0, 1 - luxury - 0.1)},
        "ffShare": round(0.12 + business * 0.45 + luxury * 0.18, 3),
        "shares": {key: round(value, 4) for key, value in shares.items()},
        "dwellBias": 18 if nature == "D" else 34,
        "generatedFrom": "AODB route/time rules v3",
    }


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in values.values()) or 1.0
    return {key: round(max(0.0, value) / total, 4) for key, value in values.items()}


def generate_queues(sim_day: date, zones: list[dict], rng: random.Random) -> list[dict]:
    day_start = datetime.combine(sim_day, time(0, 0), tzinfo=timezone.utc)
    rows: list[dict] = []
    checkpoint = {"security": "SEC", "gate": "GATE", "retail": "RTL", "food": "FOD", "lounge": "LNG", "arrivals": "ARR"}
    for zone in zones:
        base = 14 if zone["kind"] == "security" else 5
        for slot in range(96):
            moment = day_start + timedelta(minutes=slot * 15)
            curve = 1.0 + 0.9 * (1 if 5 <= moment.hour <= 9 else 0) + 0.7 * (1 if 15 <= moment.hour <= 19 else 0)
            length = max(0, int(base * curve * rng.uniform(0.55, 1.65)))
            rows.append(
                {
                    "zone_id": zone["id"],
                    "checkpoint": checkpoint.get(zone["kind"], "GEN"),
                    "queue_len": length,
                    "wait_min": round(length * (0.7 if zone["kind"] == "security" else 0.35), 1),
                    "ts": moment,
                }
            )
    return rows