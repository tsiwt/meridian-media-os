import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from app import db
row = db.query_one("SELECT * FROM decisions ORDER BY id DESC LIMIT 1")
cands = db.json_loads(row["candidates_json"], [])
for c in cands[:12]:
    print(c["campaignId"], c["passed"], c["rejectedBy"], "|", "; ".join(c["reasons"][-2:]))
print("profile zone", db.json_loads(row["profile_json"], {}).get("zoneId"), "crowd", db.json_loads(row["profile_json"], {}).get("crowdSize"))
print("today spend CMP-18", db.query_one("SELECT SUM(spend) s FROM daily_stats WHERE campaign_id='CMP-18' AND day='2026-10-24'"))
print("CMP-18", dict(db.query_one("SELECT status, budget, daily_cap, start, end FROM campaigns WHERE id='CMP-18'")))
print("today spend CMP-04", db.query_one("SELECT SUM(spend) s FROM daily_stats WHERE campaign_id='CMP-04' AND day='2026-10-24'"))
