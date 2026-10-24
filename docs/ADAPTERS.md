# Adapter guide

Meridian Media OS isolates every external source behind an adapter. The domain, scoring, decision pipeline, API and UI only ever see the canonical objects in `app/models.py`. Going live means adding or configuring one adapter — not changing routes, rules or views.

## Contract

Defined in `app/adapters/base.py` and implemented by the source classes:

| Source role | Interface | Mock implementation | Live implementation |
|---|---|---|---|
| Flight movements | `FlightSource.snapshot() -> Iterable[Flight]`, `FlightSource.stream() -> Iterable[FlightEvent]` | `AodbCsvSource` (`app/adapters/aodb.py`) | `VendorFlightSource` stub, selected by `FLIGHT_SOURCE=vendor-api` |
| Flight-leg updates | `stream() -> Iterable[FlightEvent]` | `AidxXmlSource` (`app/adapters/aidx.py`) | `LiveAidxSource` stub, selected by `AIDX_SOURCE=live-aidx` |
| Queues / zones | `QueueSource.measurements() -> Iterable[QueueMeasurement]`, `zones()` | `AcrisJsonSource` (`app/adapters/acris.py`) | `LiveAcrisSource` stub, selected by `ACRIS_SOURCE=live-acris` |

Selection happens only in `app/adapters/registry.py` (`flight_source`, `aidx_source`, `acris_source`, `feed_health`). Live stubs implement the same interface and raise `AdapterNotConfigured`; `GET /api/health` and `GET /api/meta` then report the feed as not configured rather than pretending it is live.

Canonical entities: `Flight`, `GateAssignment`, `AircraftType`, `FlightEvent`, `Terminal`, `Zone`, `Checkpoint`, `QueueMeasurement`, plus platform-owned `Screen`, `Advertiser`, `Outlet`, `Campaign`, `Creative`, `PromoCode`, `Impression`, `Redemption`.

## AODB CSV — 33 columns

One row per flight leg. Arrival/departure pairs are linked by `linked_flight_id`; paired time columns hold the arrival value on `direction=A` and the departure value on `direction=D`.

| Source column | Canonical field | Notes |
|---|---|---|
| `aodb_flight_id` / `linked_flight_id` | `Flight.flight_id` / `linked_flight_id` | Primary and paired-leg key |
| `direction` | `Flight.direction` | `A` / `D` |
| `airline_iata`, `airline_icao` | `Flight.airline_iata`, `airline_icao` | Upper-cased |
| `flight_number`, `callsign`, `service_type` | `Flight.flight_number`, `callsign`, `service_type` | |
| `flight_nature` | `Flight.flight_nature` | `D` domestic / `I` international |
| `origin`, `destination`, `via` | `Flight.origin`, `destination`, `via` | ISO airport codes |
| `terminal` | `Flight.terminal` | |
| `STA_STD` | `Flight.scheduled` | ISO 8601 UTC |
| `ETA_ETD` | `Flight.estimated` | |
| `ELDT_ETOT` | `estimated_landing` / `estimated_takeoff` | Split by direction |
| `ALDT_ATOT` | `actual_landing` / `actual_takeoff` | Split by direction |
| `AIBT_AOBT` | `Flight.aibt` / `aobt` | A-CDM in-block / off-block |
| `TOBT`, `TSAT` | `Flight.tobt`, `tsat` | A-CDM target times |
| `stand`, `gate` | `Flight.stand`, `gate` | Gate feeds proximity weighting |
| `checkin_counters`, `baggage_belt` | `Flight.checkin_counters`, `baggage_belt` | Display/ops data |
| `aircraft_reg`, `aircraft_type_icao` | `Flight.aircraft_reg`, `aircraft_type_icao` | ICAO type designators |
| `seats`, `pax_total` | `Flight.seats`, `pax_total` | Pax load drives presence |
| `status` | `Flight.status` | Normalised to `SCH/DEL/BOD/GCL/DEP/ARR/CNL` |
| `delay_codes` | `Flight.delay_codes` | IATA codes, `/` separated |
| `codeshares` | `Flight.codeshares` | `|` separated marketing carriers |
| `handler` | `Flight.handler` | Ground handler |
| `last_update_utc` | `Flight.last_update` | Drives evidence age/freshness |

The adapter validates that all 33 required columns exist (`EXPECTED_COLUMNS`) and fails with `AdapterError` if not. It is stateless and also usable as a fixture reader for tests. Sample: `samples/aodb_reference_2026-10-14.csv` (320 legs). Generated fixture: `data/aodb/flights_<sim-date>.csv` (900 legs).

## IATA AIDX XML

`AidxXmlSource.parse(xml_text)` accepts `IATA_AIDX_FlightLegNotifRQ`, is namespace-agnostic (local names), limits messages to 2 MB and rejects `<!DOCTYPE` / `<!ENTITY` before parsing. Each `FlightLeg` becomes one or more `FlightEvent` records:

| AIDX element | Event field | Canonical effect |
|---|---|---|
| `LegIdentifier/Airline`, `FlightNumber`, `DepartureAirport`, `ArrivalAirport`, `OriginDate`, optional `FlightID` | identity | Resolves `flight_id`; falls back to `airline+number:origin-destination:date` |
| `PublicStatus`, `OperationalStatus` | `status` | Status change event |
| `OperationTime` (estimated/actual) | `estimated` / `actual` | Timing update |
| Gate/stand/terminal elements | `gate` | Gate-change event, re-plans gate screens |
| Cabin/pax elements where present | `pax` / `seats` | Load update |
| Message `TimeStamp` | `occurred_at` | Evidence timestamp |

The simulation's **inject delay** and **inject gate change** actions build a standards-shaped AIDX notification and push it through this same parser (`Simulation._inject_delay`, `_inject_gate_change`), so the demo exercises the real adapter path. Sample: `samples/aidx_reference_arrival.xml`.

## ACI ACRIS / FIWARE NGSI-LD

`AcrisJsonSource.load()` accepts a single entity, a list, or an `@graph`. Properties are read as NGSI-LD `{ "value": ... }`; relationships as `{ "object": ... }`.

| Entity / property | Canonical output |
|---|---|
| `type` in `QueueMeasurement`, `PassengerQueue`, `Queue` | `QueueMeasurement` |
| `refZone` / `refPassengerProcessArea` | `zone_id` |
| `refCheckpoint` or entity id | `checkpoint_id` |
| `queueLength` | `queue_length` |
| `waitTimeMinutes` | `wait_minutes` |
| `observedAt` | `measured_at` (evidence freshness) |
| `Zone`, `Concourse`, `Terminal`, `Checkpoint`, `PassengerProcessArea` | infrastructure metadata via `zones()` |

Generated fixture: `data/acris/entities.json`. Only queue entities feed the presence/profile calculation; infrastructure entities remain available to the master-data layer.

## Passenger presence and freshness

`app/domain/presence.py` computes expected passengers per flight from `pax_total`, status, scheduled/estimated time and gate proximity. `app/domain/profile.py` rolls contributions up per screen and 5-minute window, adds the latest ACRIS queue, and records an `EvidencePoint` for every input:

- up to 6 AODB flight legs (source `AODB`, observed at `last_update_utc`);
- the latest AIDX event (source `IATA AIDX`, observed at event `ts`);
- AODB feed heartbeat (source `AODB`);
- latest ACRIS queue (source `ACRIS`, observed at `observedAt`/`ts`);
- screen heartbeat/latency (source `Platform screen telemetry`).

Freshness thresholds: `AODB_FRESH_SECONDS` (default 900 s) and `FEED_FRESH_SECONDS` (default 180 s for ACRIS/AIDX). The decision validator (`app/domain/decisions.py::_validate_citations`) requires citations to reference a trusted source present in the profile, requires fresh AODB **and** ACRIS evidence, and rejects stale or untraceable claims. If validation fails, the AI choice is rejected and a deterministic rule default (or house campaign) plays.

## Add a new source

1. Implement the relevant protocol (`FlightSource`, `FlightSource.stream`, or `QueueSource`) in `app/adapters/`.
2. Translate the vendor payload into canonical objects only. Keep vendor field names, auth and retry logic inside the adapter.
3. Set `kind`, `configured` and raise `AdapterNotConfigured` until credentials/endpoints are supplied.
4. Register the selection in `app/adapters/registry.py` and expose the mode through `feed_health`.
5. Add a fixture under `samples/` or `data/` and a small parse test/tool.
6. No changes to `app/domain/`, `app/api/` or `web/` should be necessary.

Example:

```python
class MyVendorFlightSource:
    kind = "MyVendor REST"
    configured = True

    def snapshot(self):
        for row in self._fetch():
            yield self._to_flight(row)   # canonical Flight

    def stream(self):
        for message in self._subscribe():
            yield self._to_event(message)  # canonical FlightEvent
```

Then:

```python
def flight_source(settings):
    if settings.flight_source == "myvendor":
        return MyVendorFlightSource()
    ...
```

## Configuration switch

```bash
FLIGHT_SOURCE=mock-aodb     # or vendor-api / your adapter mode
AIDX_SOURCE=mock-aidx       # or live-aidx
ACRIS_SOURCE=mock-acris     # or live-acris
```

`GET /api/meta` returns each feed's adapter, mode, configured flag, contract and last message; the Admin feed-health panel renders the same data. The mock path always remains available for demos and tests.
