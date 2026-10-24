-- Schema v1: canonical entities + platform-owned tables.
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS airlines (
    iata TEXT PRIMARY KEY,
    icao TEXT NOT NULL,
    name TEXT NOT NULL,
    market TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#38e8c8',
    is_partner INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS aircraft_types (
    icao TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    seats INTEGER NOT NULL,
    widebody INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS terminals (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    concourses TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS zones (
    id TEXT PRIMARY KEY,
    terminal_id TEXT NOT NULL,
    name TEXT NOT NULL,
    concourse TEXT NOT NULL,
    kind TEXT NOT NULL,
    gates_json TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL NOT NULL,
    h REAL NOT NULL,
    FOREIGN KEY (terminal_id) REFERENCES terminals(id)
);

CREATE TABLE IF NOT EXISTS gates (
    code TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    terminal_id TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    FOREIGN KEY (zone_id) REFERENCES zones(id)
);

CREATE TABLE IF NOT EXISTS screens (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    nearest_gates_json TEXT NOT NULL,
    aspect TEXT NOT NULL,
    orientation TEXT NOT NULL,
    size_inches INTEGER NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    last_seen TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'gate',
    FOREIGN KEY (zone_id) REFERENCES zones(id)
);
CREATE INDEX IF NOT EXISTS idx_screens_zone ON screens(zone_id);

CREATE TABLE IF NOT EXISTS flights (
    flight_id TEXT PRIMARY KEY,
    linked_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    airline TEXT NOT NULL,
    flight_no TEXT NOT NULL,
    callsign TEXT NOT NULL,
    service_type TEXT NOT NULL,
    nature TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    via TEXT NOT NULL,
    terminal TEXT NOT NULL,
    std TEXT,
    eta TEXT,
    etd TEXT,
    eldt TEXT,
    etot TEXT,
    aldt TEXT,
    atot TEXT,
    aibt TEXT,
    aobt TEXT,
    tobt TEXT,
    tsat TEXT,
    stand TEXT,
    gate TEXT,
    counters TEXT,
    belt TEXT,
    registration TEXT,
    aircraft_type TEXT,
    seats INTEGER NOT NULL DEFAULT 0,
    pax INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    delay_codes TEXT,
    codeshares TEXT,
    handler TEXT,
    updated TEXT,
    profile_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (airline) REFERENCES airlines(iata)
);
CREATE INDEX IF NOT EXISTS idx_flights_std ON flights(std);
CREATE INDEX IF NOT EXISTS idx_flights_gate ON flights(gate);
CREATE INDEX IF NOT EXISTS idx_flights_airline ON flights(airline);

CREATE TABLE IF NOT EXISTS flight_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_id TEXT NOT NULL,
    type TEXT NOT NULL,
    field TEXT NOT NULL,
    old TEXT,
    new TEXT,
    source TEXT NOT NULL,
    ts TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON flight_events(ts);

CREATE TABLE IF NOT EXISTS queues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL,
    checkpoint TEXT NOT NULL,
    queue_len INTEGER NOT NULL,
    wait_min REAL NOT NULL,
    ts TEXT NOT NULL,
    source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queues_zone_ts ON queues(zone_id, ts);

CREATE TABLE IF NOT EXISTS advertisers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    color TEXT NOT NULL,
    contact TEXT NOT NULL,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outlets (
    id TEXT PRIMARY KEY,
    advertiser_id TEXT NOT NULL,
    name TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    category TEXT NOT NULL,
    stock_status TEXT NOT NULL DEFAULT 'in_stock',
    created TEXT NOT NULL,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
);

CREATE TABLE IF NOT EXISTS creatives (
    id TEXT PRIMARY KEY,
    advertiser_id TEXT NOT NULL,
    name TEXT NOT NULL,
    headline_en TEXT NOT NULL,
    headline_zh TEXT NOT NULL,
    body_en TEXT NOT NULL,
    body_zh TEXT NOT NULL,
    cta_en TEXT NOT NULL,
    cta_zh TEXT NOT NULL,
    template TEXT NOT NULL,
    colors_json TEXT NOT NULL,
    image TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    created TEXT NOT NULL,
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    advertiser_id TEXT NOT NULL,
    creative_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    daypart_json TEXT NOT NULL,
    budget REAL NOT NULL,
    daily_cap REAL NOT NULL,
    freq_cap_min INTEGER NOT NULL,
    bid REAL NOT NULL,
    segments_json TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    placement_json TEXT NOT NULL,
    triggers_json TEXT NOT NULL,
    spend REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    scans INTEGER NOT NULL DEFAULT 0,
    redemptions INTEGER NOT NULL DEFAULT 0,
    revenue REAL NOT NULL DEFAULT 0,
    conversion REAL NOT NULL DEFAULT 0,
    created TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 0,
    ab_group TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'general',
    FOREIGN KEY (advertiser_id) REFERENCES advertisers(id),
    FOREIGN KEY (creative_id) REFERENCES creatives(id)
);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_adv ON campaigns(advertiser_id);

CREATE TABLE IF NOT EXISTS promos (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    flight_id TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    max_uses INTEGER NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0,
    parent_code TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);
CREATE INDEX IF NOT EXISTS idx_promos_campaign ON promos(campaign_id);

CREATE TABLE IF NOT EXISTS impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    decision_id INTEGER,
    profile_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_impressions_ts ON impressions(ts);
CREATE INDEX IF NOT EXISTS idx_impressions_campaign ON impressions(campaign_id, ts);

CREATE TABLE IF NOT EXISTS redemptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    promo_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    channel TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    flight_id TEXT NOT NULL DEFAULT '',
    segment TEXT NOT NULL DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_redemptions_campaign ON redemptions(campaign_id, ts);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screen_id TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    candidates_json TEXT NOT NULL,
    winner_id TEXT NOT NULL,
    winner_score REAL NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    fallback INTEGER NOT NULL DEFAULT 0,
    ai_model TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    play_ms INTEGER NOT NULL DEFAULT 15000
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_decisions_screen ON decisions(screen_id, ts);
CREATE INDEX IF NOT EXISTS idx_decisions_campaign ON decisions(winner_id, ts);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    owner TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, created);

CREATE TABLE IF NOT EXISTS rules (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_stats (
    campaign_id TEXT NOT NULL,
    day TEXT NOT NULL,
    impressions INTEGER NOT NULL,
    scans INTEGER NOT NULL,
    redemptions INTEGER NOT NULL,
    revenue REAL NOT NULL,
    spend REAL NOT NULL,
    PRIMARY KEY (campaign_id, day)
);

CREATE TABLE IF NOT EXISTS segment_stats (
    campaign_id TEXT NOT NULL,
    segment TEXT NOT NULL,
    impressions INTEGER NOT NULL,
    scans INTEGER NOT NULL,
    redemptions INTEGER NOT NULL,
    revenue REAL NOT NULL,
    PRIMARY KEY (campaign_id, segment)
);

CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    screen_ids_json TEXT NOT NULL,
    price REAL NOT NULL,
    description TEXT NOT NULL,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marketplace (
    id TEXT PRIMARY KEY,
    retailer_id TEXT NOT NULL,
    airline TEXT NOT NULL,
    title TEXT NOT NULL,
    offer TEXT NOT NULL,
    status TEXT NOT NULL,
    created TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    token TEXT PRIMARY KEY,
    advertiser_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created TEXT NOT NULL
);