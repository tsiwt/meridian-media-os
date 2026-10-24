CREATE TABLE IF NOT EXISTS goodwill_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    airline TEXT NOT NULL,
    flight_id TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    partner TEXT NOT NULL,
    offer TEXT NOT NULL,
    code TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goodwill_airline ON goodwill_actions(airline, created);