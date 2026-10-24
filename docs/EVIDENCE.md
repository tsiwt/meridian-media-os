# Requirement evidence matrix

Maps the challenge requirements to the implementation and to a verifiable test, API check or demo action. `Must` items are the scored baseline; `Should` items are extra. Paths are relative to the repository root.

Legend: **Code** = implementation; **Check** = command/API/demo that demonstrates it. No scan or test result is claimed here unless it is reproducible with the command shown.

## A. Platform, data and integration

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| A1 | One-command local start, offline, seeded | Must | `Dockerfile`, `docker-compose.yml`, `app/seed.py`, `app/migrations/` | `docker compose up --build`; open `http://localhost:8000` |
| A2 | Separate frontend/backend, REST + live updates | Must | `web/`, `app/server.py`, `app/api/`, SSE `/api/stream` | Network tab: JSON REST + `text/event-stream`; UI ticks without reload |
| A3 | Adapter layer isolated from business logic | Must | `app/adapters/`, `app/adapters/registry.py` | `docs/ADAPTERS.md`; switch `FLIGHT_SOURCE` and restart |
| A4 | Embedded DB, migrations, seed script | Must | `app/db.py`, `app/migrations/001_init.sql`, `002_goodwill.sql`, `app/seed.py` | `python -m app.seed --reset`; `data/meridian.db` created |
| A5 | ~900 flights, 180 screens, 40 outlets, 10 airlines, 25 campaigns, 30 days history | Must | `app/seed.py`, `app/seed_airport.py`, `app/seed_business.py` | `GET /api/meta` counts; Admin KPIs |
| A6 | Mock AODB CSV 33 columns | Must | `app/adapters/aodb.py`, `samples/aodb_reference_2026-10-14.csv` | `GET /api/health` feed `AODB`; adapter rejects missing columns |
| A7 | Mock AIDX XML stream + parse | Must | `app/adapters/aidx.py`, `samples/aidx_reference_arrival.xml` | Inject delay/gate change; `GET /api/admin/decisions` shows AIDX evidence |
| A8 | Mock ACRIS NGSI-LD entities | Must | `app/adapters/acris.py`, `data/acris/entities.json` | `GET /api/health` feed `ACRIS`; "Why this ad?" ACRIS queue evidence |
| A9 | Single config switch per source + live stubs | Must | `app/config.py`, `app/adapters/registry.py` | `FLIGHT_SOURCE=vendor-api` → `/api/health` reports not configured |
| A10 | Pluggable AI, mock default with template creatives | Must | `app/domain/ai.py`, `AI_PROVIDER` | GenAI assistant works with no key |
| A11 | Derived passenger presence per zone/5-min window | Must | `app/domain/presence.py`, `app/domain/profile.py` | Passenger "Why this ad?" profile bars; Admin heat overlay |
| A12 | Evidence-first pipeline with traceable citations, hard rules, reproducible score, fallback | Must | `app/domain/decisions.py` (`_validate_citations`, `_validate_and_choose`), `app/domain/scoring.py` | `GET /api/decisions/{id}` shows `validation.checks`; tools/smoke_decision.py |
| A13 | Every decision logged with profile/candidates/scores/reason | Must | `app/domain/decisions.py::_persist`, `decisions` table | Admin decision log; `GET /api/admin/decisions` |
| A14 | Crowd profile attributes plausible per flight | Must | `app/seed_airport.py` route/time rules; `profile_json` | Flight profile in `GET /api/passenger/screens/{id}` |
| A15 | WebSocket/SSE live updates within 2 s | Must | `app/server.py::_stream`, `app/domain/sim.py::EventBus` | Inject delay; dashboards update without refresh |
| A16 | Responsive 1440/1920, dark admin + light business, mobile claim | Must | `web/css/layout.css`, `theme.css`, `web/js/views/claim.js` | Resize browser; open claim page on phone |
| A17 | White-label theme + i18n (EN + second language) | Must | `app/config.py::theme`, `web/js/i18n.js` | `/api/config`; language toggle; env overrides |
| A18 | Docs: README, architecture, adapter guide, API spec | Must | `README.md`, `docs/ADAPTERS.md`, `docs/architecture.svg`, `docs/openapi.yaml` | Open files; `/architecture.svg`, `/openapi.yaml` |

## B. Platform Admin

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| B1 | Live terminal map, screen dots online/degraded/offline, presence heat | Must | `web/js/views/admin.js`, `/api/admin/overview` (`screens`, `zones`, `presence`) | Admin → Network map; inject screen offline |
| B2 | KPI strip: online %, plays, impressions, revenue, active campaigns, latency | Must | `routes_admin.py::_overview`; `web/js/views/admin.js` | `GET /api/admin/overview` → `kpi` |
| B3 | Incident/bug tracker with severity/owner/status | Must | `routes_admin.py::_incidents`, `/api/admin/incidents`; `_check_incidents` | Inject screen offline; Admin incident list; PATCH status |
| B4 | Master data list + create/edit (vendors, outlets, airlines, locations, screens) | Must | `routes_admin.py::_master`, `_master_create`, `_master_update` | `GET/POST/PATCH /api/admin/master/{entity}` |
| B5 | Feed health: AODB/AIDX/ACRIS, adapter, last message, configured | Should | `adapters/registry.py::feed_health`, `routes_core.py::_health` | `GET /api/health` → `feeds`; Admin feed panel |
| B6 | Performance: API p95, playlist build, 7-day uptime baseline | Should (simulated uptime) | `app/api/metrics.py`, `routes_admin.py::_overview` (`performance`) | `GET /api/admin/overview` → `performance` |
| B7 | Rule engine settings + versioned segment model | Must | `routes_admin.py::_rules`, `rules` table, `GET /api/meta` | `GET/PUT /api/admin/rules`; Admin rules tab |
| B8 | Searchable decision log + audit | Must | `routes_admin.py::_decisions`, `_decision_detail`, `routes_core.py::_decision_audit` | `GET /api/admin/decisions?q=...`; open a decision |

## C. Retailer

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| C1 | Live dashboard: impressions, scans, redemptions, conversion, revenue | Must | `routes_retailer.py::_dashboard`, `/api/retailer/dashboard`; SSE events | `?advertiserId=ADV-01`; claim a promo |
| C2 | Passenger flow near store, next 2 h, top destinations/nationalities | Must | `routes_retailer.py::_flow`, `domain/presence.py` | `GET /api/retailer/flow?advertiserId=ADV-01`; Retailer flow card |
| C3 | Campaign builder with creative, zones/screens, audience rules, schedule, budget, preview | Must | `routes_retailer.py::_campaign_create`, `_preview`; `web/js/views/retailer.js` | Retailer → Campaigns → New campaign; live preview |
| C4 | Creative library: reuse/upload/duplicate | Must | `routes_retailer.py::_creatives`, `_campaign_copy` | `GET/POST /api/retailer/creatives`; Duplicate/Run again |
| C5 | Time-boxed promo codes, QR, expiry with flight, share-to-family | Must | `domain/promos.py`, `app/qr.py`, `routes_core.py::_claim_*` | Passenger QR → phone claim; share creates second code |
| C6 | Campaign history with spend, impressions, redemptions, ROI, run again | Must | `routes_retailer.py::_campaigns`, `_campaign_copy` | Retailer history table; Run again |
| C7 | Trigger rules, e.g. DXB delay > 30 min → 15% off Gate 40–45 | Should | `routes_retailer.py::_triggers`; `domain/scoring.py::_boost` | Retailer trigger tab; inject ZO501 delay |
| C8 | Stock-aware pause (mock toggle) | Should (partial) | outlet stock toggle in `routes_retailer.py::_stock`; campaign-level pause not wired | `POST /api/retailer/outlets/{id}/stock`; documented gap |
| C9 | Budget pacing + simple A/B creative comparison | Should | `campaigns.ab_group`, spend/daily cap in `scoring.py`; `web/js/views/retailer.js` | Campaign table A/B group and spend |
| C10 | Live audience-match preview + segment performance + suggestions | Must | `_preview`, `_recommendations`, `segment_stats` | Builder match estimate; dashboard suggestion card |
| C11 | GenAI creative assistant offline, EN + second language | Must | `routes_retailer.py::_generate_creative`, `domain/ai.py::creative` | Creative library → GenAI assistant |

## D. Media Manager

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| D1 | Inventory calendar screen × hour, booked/available/premium | Must | `routes_media.py::_inventory` | `GET /api/media/inventory`; Media → Inventory |
| D2 | Yield/pricing from presence, occupancy, 7-day forecast | Must | `routes_media.py::_yield`, `domain/presence.py` | `GET /api/media/yield`; Media → Yield |
| D3 | Approval queue + brand-safety checklist, approve/reject | Must | `routes_media.py::_approvals` | `GET/POST /api/media/approvals`; Media → Approvals |
| D4 | Advertiser overview, spend ranking, under-delivery flags | Must | `routes_media.py::_advertisers` | `GET /api/media/advertisers` |
| D5 | Conflict view why A beat B, manual override with reason | Must | `routes_media.py::_conflict`; decision candidates | `GET /api/media/conflict?screenId=SCR-122` |
| D6 | Package builder | Should | `routes_media.py::_packages` | `GET/POST /api/media/packages`; Media → Packages |
| D7 | One-click advertiser report (shareable link / print) | Should | `routes_media.py::_report_share`, `server.py::_report` | `POST /api/media/report/share`; open `/report/{token}` |

## E. Airline Representative

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| E1 | My flights today: gate, status, delay, load factor, timeline | Must | `routes_airline.py::_flights`, `_summary` | `GET /api/airline/flights?airline=ZO`; Airline → Flights |
| E2 | Gate-area messaging for own gates/boarding window | Must | `routes_airline.py::_messages` | `POST /api/airline/messages`; Airline → Messages |
| E3 | Delay goodwill automation with F&B co-funding | Must | `domain/goodwill.py`, `sim._inject_delay`; `routes_airline.py::_goodwill` | Inject ZO501 delay 45 min; Airline → Goodwill |
| E4 | Co-marketing marketplace, one-click accept | Should | `routes_airline.py::_marketplace` | `POST /api/airline/marketplace/{id}/accept` |
| E5 | Performance among own passengers | Should | `routes_airline.py::_performance` | `GET /api/airline/performance?airline=ZO` |
| E6 | Aggregated crowd profile of own flights | Must | `routes_airline.py::_summary` (`crowdProfile`), `presence.aggregate` | Airline Overview → Own-flight crowd profile |

## F. Passenger screen simulator

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| F1 | Full-screen chosen screen, 9:16/16:9 frame | Must | `web/js/views/passenger.js`, `/api/passenger/screens/{id}` | Pick Gate 42 / `SCR-122`; aspect toggle |
| F2 | FIDS-style nearby flights context strip | Must | `/api/passenger/screens/{id}` → `flights` | Context strip next to ad |
| F3 | Dynamic ad selection as time/flights change | Must | `domain/sim.py`, `domain/decisions.py`, SSE | Play at 10×/60× or jump to 14:10; ad changes |
| F4 | Promo QR with countdown; phone claim records redemption | Must | `app/qr.py`, `promos.py`, `/claim/{code}`, `_claim_post` | Scan with phone on LAN; Retailer dashboard increments |
| F5 | "Why this ad?" crowd profile, top-3 scores, winning rule | Must | `routes_passenger.py::_why`, `web/js/views/passenger.js` | Open overlay; compare with `/api/decisions/{id}` |

## G. WOW features and demo

| # | Requirement | Pri | Code | Check / demo |
|---|---|---|---|---|
| G1 | Simulation bar: play/pause, 1×/10×/60×, jump, inject delay/gate change/offline | Must | `domain/sim.py::control`, `inject`; `web/js/main.js` | Use bar; `/api/sim/control` |
| G2 | Cause-and-effect across roles within 2 s | Must | AIDX inject → `_apply_aidx_events` → SSE → all views | Inject ZO501 delay; watch Airline/Retailer/Passenger |
| G3 | Split-screen demo mode | Must | `web/js/main.js` split mode | Toggle split-screen |
| G4 | GenAI creative brief → ready ad page, EN + second language | Must | `domain/ai.py::creative`, `/api/retailer/creatives/generate` | Brief "Festive sweets, 20% off, families flying domestic" |
| G5 | Smart recommendation "best 3 slots tomorrow" with predicted impressions | Must | `routes_retailer.py::_recommendations` | `GET /api/retailer/recommendations`; Retailer suggestion card |
| G6 | Worked Gate 42 example reproducible | Must | Seed ZO501 DXB 240 pax + YU88 SCJ 180 pax; `seed_business.py` CMP-01/02/03 | Jump to 14:10, Gate 42; open Why overlay |

## H. Security, quality and packaging

| # | Requirement | Pri | Code / doc | Check |
|---|---|---|---|---|
| H1 | No auth/payments/per-passenger tracking (out of scope) | Must | Role switcher only; aggregate profiles | `GET /api/config` roles; docs limitations |
| H2 | No secrets in repo | Must | `.env.example`, `.gitignore`, `.dockerignore` | Secret scan commands in README; review zip contents |
| H3 | Security headers/CSP, payload limits, XML hardening | Must | `app/server.py::SECURITY_HEADERS`, `MAX_BODY`; AIDX DTD/ENTITY reject | `curl -I`; adapter tests/tools |
| H4 | Docker non-root, writable data, healthcheck | Must | `Dockerfile`, `docker-compose.yml` | `docker compose config`; `GET /api/health` |
| H5 | Submission zip has source, no DB/pyc/secrets | Must | packaging step | `docs/EVIDENCE.md` + zip inspection |
| H6 | Documented limitation: live adapters are stubs | Must | README, `docs/ADAPTERS.md` | `FLIGHT_SOURCE=vendor-api` → configured:false |

## Verification commands

```bash
python -m compileall app
python tools/smoke_decision.py
python tools/check_qr.py
python tools/inspect_db.py

curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/admin/overview
curl "http://127.0.0.1:8000/api/retailer/dashboard?advertiserId=ADV-01"
curl http://127.0.0.1:8000/api/passenger/screens/SCR-122
curl http://127.0.0.1:8000/api/meta
```

The matrix is a traceability aid, not a claim that every optional item has been independently scored. Runtime behaviour is the source of truth; reproduce checks against a running instance.
