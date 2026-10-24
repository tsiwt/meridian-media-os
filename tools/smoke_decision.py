"""Developer smoke test: build one decision and print the audit trail."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DB_PATH", str(ROOT / "data" / "smoke.db"))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.domain import decisions  # noqa: E402
from app.models import iso  # noqa: E402
from app.seed import seed_all  # noqa: E402

seed_all(force=True)
now = settings.sim_start
db.set_meta("feed_last_aodb", iso(now))
db.set_meta("feed_last_aidx", iso(now))
db.set_meta("feed_last_acris", iso(now))
row = db.query_one("SELECT id FROM screens WHERE zone_id='T2-F' ORDER BY id LIMIT 1")
decision = decisions.decide(row["id"], now, settings, persist=True)
print(json.dumps(decision.to_dict(now), indent=2)[:6000])
print("--- winner:", decision.winner.name if decision.winner else None)
print("--- fallback:", decision.fallback)
print("--- validation:", json.dumps(decision.validation, indent=2))