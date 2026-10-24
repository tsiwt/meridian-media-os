import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DB_PATH", str(ROOT / "data" / "dev.db"))

from app import db  # noqa: E402

print("today stats", dict(db.query_one("SELECT COUNT(*) c, SUM(impressions) i, SUM(redemptions) r, SUM(revenue) rev FROM daily_stats WHERE day='2026-10-24'")))
print("decisions", db.query_one("SELECT COUNT(*) c FROM decisions")["c"])
print("fallback", [dict(r) for r in db.query("SELECT fallback, COUNT(*) c FROM decisions GROUP BY fallback")])
row = db.query_one("SELECT * FROM decisions ORDER BY id DESC LIMIT 1")
if row:
    validation = db.json_loads(row["validation_json"], {})
    print("last validation", json.dumps(validation, indent=2))
    print("last reason", row["reason"])
    print("last evidence", json.dumps(db.json_loads(row["evidence_json"], []), indent=2)[:1800])
print("campaign stats", [dict(r) for r in db.query("SELECT id, status, impressions, spend, revenue FROM campaigns ORDER BY id LIMIT 3")])
