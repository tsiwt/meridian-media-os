"""Executable acceptance checks for the POC (Python stdlib unittest)."""

from __future__ import annotations

import os
import random
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMP = Path(tempfile.mkdtemp(prefix="mmos-tests-"))
os.environ["DB_PATH"] = str(TEMP / "test.db")
os.environ["SEED_ON_BOOT"] = "0"

from app import db  # noqa: E402
from app.adapters.acris import AcrisJsonSource, build_entities  # noqa: E402
from app.adapters.aidx import AidxXmlSource, build_notification  # noqa: E402
from app.adapters.aodb import AodbCsvSource  # noqa: E402
from app.api.http import match_route  # noqa: E402
from app.config import settings  # noqa: E402
from app.domain import decisions, promos  # noqa: E402
from app.domain.profile import build_profile, screen_context  # noqa: E402
from app.domain.sim import Simulation  # noqa: E402
from app.models import iso  # noqa: E402
from app.qr import encode, encode_svg  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.seed_airport import make_profile  # noqa: E402


def setUpModule() -> None:
    db.migrate()
    seed_all(force=True)


class AdapterTests(unittest.TestCase):
    def test_aodb_reference_has_33_columns_and_320_rows(self):
        source = AodbCsvSource(ROOT / "samples" / "aodb_reference_2026-10-14.csv")
        flights = list(source.snapshot())
        self.assertEqual(len(flights), 320)
        self.assertEqual(flights[0].flight_id, "100112")
        self.assertEqual(flights[0].direction, "A")

    def test_aidx_reference_parses_status_and_times(self):
        source = AidxXmlSource(ROOT / "samples" / "aidx_reference_arrival.xml")
        events = source.parse_file()
        fields = {event.field for event in events}
        self.assertIn("status", fields)
        self.assertTrue({"actual", "boarding", "estimated"} & fields)
        self.assertTrue(all(event.source == "IATA AIDX" for event in events))
        status = next(event for event in events if event.field == "status")
        self.assertEqual(status.new_value, "ARR")

    def test_aidx_built_message_round_trip(self):
        flight = db.query_one("SELECT * FROM flights WHERE flight_no='501' AND direction='D'")
        source = AidxXmlSource()
        demo = _flight_model(flight)
        events = source.parse(build_notification(demo, status="DEL", estimated=settings.sim_start, gate="42"))
        self.assertTrue(any(event.flight_id == demo.flight_id for event in events))
        fields = {event.field for event in events}
        self.assertIn("gate", fields)
        self.assertTrue({"actual", "boarding", "estimated"} & fields)

    def test_acris_ngsi_ld_round_trip(self):
        document = build_entities(
            [{"id": "T2-F", "name": "Concourse F", "terminal_id": "T2", "x": 1, "y": 2}],
            [{"zone_id": "T2-F", "checkpoint": "GATE", "queue_len": 12, "wait_min": 4.2, "ts": iso(settings.sim_start)}],
        )
        measurements = list(AcrisJsonSource().measurements(document))
        self.assertEqual(len(measurements), 1)
        self.assertEqual(measurements[0].queue_length, 12)
        self.assertEqual(measurements[0].zone_id, "T2-F")


class ProfileTests(unittest.TestCase):
    def test_monday_morning_domestic_skews_business(self):
        profile = make_profile(
            "D", "ADN", "XD",
            datetime(2026, 10, 19, 7, 0, tzinfo=timezone.utc),
            189, 150, random.Random(11),
        )
        self.assertGreater(profile["shares"]["business"], profile["shares"]["holiday"])
        self.assertGreater(profile["shares"]["business"], 0.4)

    def test_friday_evening_beach_skews_holiday_and_family(self):
        profile = make_profile(
            "I", "SCJ", "YU",
            datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc),
            189, 165, random.Random(12),
        )
        self.assertGreater(profile["shares"]["holiday"], 0.4)
        self.assertGreater(profile["shares"]["family"], 0.25)
        self.assertGreater(profile["shares"]["holiday"], profile["shares"]["business"])

    def test_profile_is_evidence_backed(self):
        sim = Simulation(settings, autostart=False)
        screen = screen_context("SCR-122")
        profile = build_profile(screen, sim.now, settings)
        self.assertGreater(profile.crowd_size, 0)
        sources = {point.source for point in profile.evidence}
        self.assertIn("AODB", sources)
        self.assertIn("ACRIS", sources)
        self.assertGreater(profile.confidence, 0.5)
        self.assertTrue(profile.top_destinations)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.sim = Simulation(settings, autostart=False)
        db.set_meta("feed_last_aodb", iso(self.sim.now))
        db.set_meta("feed_last_acris", iso(self.sim.now))

    def test_decision_has_candidates_and_reproducible_audit(self):
        decision = decisions.decide("SCR-122", self.sim.now, settings, persist=False)
        self.assertIsNotNone(decision)
        self.assertIsNotNone(decision.winner)
        self.assertTrue(decision.candidates)
        checks = {check["check"]: check["ok"] for check in decision.validation["checks"]}
        self.assertIn("score_reproducible", checks)
        self.assertIn("citations_traceable", checks)
        self.assertTrue(decision.reason)

    def test_stale_aodb_forces_rule_fallback(self):
        db.set_meta("feed_last_aodb", iso(self.sim.now.replace(year=2020)))
        decision = decisions.decide("SCR-122", self.sim.now, settings, persist=False)
        self.assertIsNotNone(decision)
        self.assertTrue(decision.fallback)
        self.assertEqual(decision.validation["executed"], "rule_default")
        db.set_meta("feed_last_aodb", iso(self.sim.now))


class PromoTests(unittest.TestCase):
    def test_create_share_and_claim(self):
        flight = db.query_one("SELECT * FROM flights WHERE flight_no='501' AND direction='D'")
        promo = promos.create("CMP-01", flight["flight_id"], settings.sim_start, label="Test gate offer", value="15%", minutes=60)
        self.assertTrue(promo["code"].startswith("MQI-"))
        shared = promos.share(promo["code"], settings.sim_start)
        self.assertEqual(shared["parent_code"], promo["code"])
        self.assertNotEqual(shared["code"], promo["code"])
        result = promos.claim(promo["code"], settings.sim_start)
        self.assertTrue(result["ok"])
        self.assertEqual(result["campaignId"], "CMP-01")
        after = promos.get_by_code(promo["code"], settings.sim_start)
        self.assertGreaterEqual(after["uses"], 1)

    def test_expired_code_is_rejected(self):
        flight = db.query_one("SELECT * FROM flights WHERE flight_no='501' AND direction='D'")
        promo = promos.create("CMP-02", flight["flight_id"], settings.sim_start, label="Expiry test", value="10%", minutes=5)
        row = db.query_one("SELECT * FROM promos WHERE code=?", (promo["code"],))
        db.execute("UPDATE promos SET valid_until=? WHERE code=?", (iso(settings.sim_start.replace(year=2020)), promo["code"]))
        with self.assertRaises(ValueError):
            promos.claim(promo["code"], settings.sim_start)


class QrAndRouteTests(unittest.TestCase):
    def test_qr_matrix_is_well_formed(self):
        matrix = encode("https://configuring-maker-clean-understanding.trycloudflare.com/claim/MQI-TEST")
        self.assertIn(len(matrix), {21, 25, 29, 33, 37, 41})
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(any(any(row) for row in matrix))
        svg = encode_svg("https://example.com/claim/MQI-TEST")
        self.assertIn("<svg", svg)
        self.assertIn("Promo QR", svg)

    def test_router_pattern_matching(self):
        self.assertEqual(match_route("/api/admin/incidents/{id}", "/api/admin/incidents/7"), {"id": "7"})
        self.assertEqual(match_route("/api/passenger/screens/{id}", "/api/passenger/screens/SCR-122"), {"id": "SCR-122"})
        self.assertIsNone(match_route("/api/admin/incidents/{id}", "/api/admin/incidents"))


class SeedTests(unittest.TestCase):
    def test_full_scale_counts(self):
        self.assertEqual(db.table_count("flights"), 900)
        self.assertEqual(db.table_count("screens"), 180)
        self.assertEqual(db.table_count("outlets"), 40)
        self.assertEqual(db.table_count("airlines"), 10)
        self.assertEqual(db.table_count("campaigns"), 25)
        self.assertEqual(db.table_count("creatives"), 25)
        self.assertGreaterEqual(db.query_one("SELECT COUNT(DISTINCT day) c FROM daily_stats")["c"], 30)

    def test_demo_flights_exist_at_gate_42(self):
        row = db.query_one("SELECT * FROM flights WHERE flight_no='501' AND direction='D'")
        self.assertIsNotNone(row)
        self.assertEqual(row["gate"], "42")
        self.assertEqual(row["destination"], "DXB")
        self.assertEqual(row["airline"], "ZO")


def _flight_model(row):
    from app.models import Flight, parse_time

    return Flight(
        flight_id=row["flight_id"], linked_flight_id=row["linked_id"], direction=row["direction"],
        airline_iata=row["airline"], airline_icao="", flight_number=row["flight_no"],
        callsign=row["callsign"], service_type=row["service_type"], flight_nature=row["nature"],
        origin=row["origin"], destination=row["destination"], via=row["via"], terminal=row["terminal"],
        scheduled=parse_time(row["std"]), estimated=parse_time(row["etd"] or row["eta"]),
        estimated_landing=parse_time(row["eldt"]), estimated_takeoff=parse_time(row["etot"]),
        actual_landing=parse_time(row["aldt"]), actual_takeoff=parse_time(row["atot"]),
        aibt=parse_time(row["aibt"]), aobt=parse_time(row["aobt"]), tobt=parse_time(row["tobt"]),
        tsat=parse_time(row["tsat"]), stand=row["stand"], gate=row["gate"],
        checkin_counters=row["counters"], baggage_belt=row["belt"], aircraft_reg=row["registration"],
        aircraft_type_icao=row["aircraft_type"], seats=row["seats"], pax_total=row["pax"],
        status=row["status"], delay_codes=row["delay_codes"], codeshares=row["codeshares"],
        handler=row["handler"], last_update=parse_time(row["updated"]), profile={},
    )


if __name__ == "__main__":
    unittest.main(verbosity=2)