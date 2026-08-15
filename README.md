# Real-Time Multi-Source Vehicle Safety Event Reconciliation System

A Flask + MongoDB backend (with a small vanilla JS/HTML/CSS dashboard) that ingests
asynchronous, possibly out-of-order safety events about vehicles from three sources —
**sensors** (V2V telemetry), **AI anomaly detection**, and **blockchain compliance logs** —
and reconciles them into one deterministic, auditable `safety_state` (`safe`/`alert`/`danger`)
per vehicle at each point in time. See [`prd.md`](prd.md) for the full spec.

## Architecture

```
POST /events → validate → events (immutable, deduped by event_id)
                              ↓
                 State Reconstruction (as-of lookups, interpolation,
                 sensor-conflict resolution)
                              ↓
                 Conflict Resolution (sensor vs AI, blockchain vs sensor)
                              ↓
        vehicle_states (versioned history)   audit_trail (decision log)
                              ↓
                 Dashboard (GET /vehicles, GET /audit)
```

**Key design decision:** `state(vehicle, T)` is always recomputed as a pure function of
`events(vehicle, timestamp ≤ T)`, never by "apply the newest event." This is what makes
late/out-of-order events, determinism, idempotency, and replay all fall out of the same
mechanism instead of needing separate special-case handling.

## Data-schema convention (resolves an ambiguity in the PRD)

The PRD leaves each source's `data` payload open-ended, but the reconciliation rules
("sensor vs AI disagree", "blockchain conflicts with sensor") require each event to carry
a comparable opinion. This implementation's convention:

- Every event's `data` MAY include a `status` field: `"safe" | "alert" | "danger"` — the
  source's own opinion of the vehicle's safety.
- If omitted, it's inferred:
  - **sensor** → `"safe"` (raw telemetry alone implies no verdict)
  - **ai** → derived from `data.alert`: no/`"none"` alert → `"safe"`; otherwise `"danger"`
    if `confidence ≥ 0.8` else `"alert"`
  - **blockchain** → derived from `data.compliance_status`: `"pass"` → `"safe"`,
    `"fail"` → `"alert"`
- `confidence` (0–1) comes from `data.confidence`, defaulting to `1.0` for sensor events
  and `0.5` for AI events if omitted. Blockchain logs are deterministic (pass/fail), not
  probabilistic.

**Resolution precedence** when multiple sources are present: sensor-vs-AI is resolved
first (interim decision); blockchain-vs-sensor is then checked — if blockchain conflicts
with the sensor reading and is newer, it overrides the interim decision outright;
otherwise the interim decision stands (and the audit trail still records that the
blockchain conflict was considered and rejected as stale).

## Project layout

```
app/
  config.py          tunable constants (0.8 confidence threshold, 10-min late window, ...)
  db.py               MongoDB connection + collection accessors + indexes
  models/             event validation, VehicleState value object
  routes/             POST /events, GET /vehicles(/<id>), GET /audit(/<id>), POST /replay
  engine/
    ingestion.py       validate + dedupe + store raw events
    reconstruction.py  as-of lookups, sensor-conflict resolution, interpolation
    conflict.py        pure sensor-vs-AI / blockchain-vs-sensor rules
    reconciler.py       orchestrates the above, writes vehicle_states + audit_trail
  replay.py            replay stored/re-posted events to verify consistency
static/                dashboard (index.html, app.js, style.css)
fixtures/               5 edge-case datasets + load_fixtures.py
tests/                  pytest suite (unit + integration, mongomock-backed)
```

## Running it

```bash
docker compose up -d --build
```

This starts MongoDB and the Flask app (http://localhost:5000). Open that URL for the
dashboard, or use the API directly:

```bash
curl -X POST http://localhost:5000/events \
  -H "Content-Type: application/json" \
  -d '{"source":"sensor","vehicle_id":"veh_1","timestamp":"2026-08-15T07:00:00Z",
       "data":{"position":{"x":1,"y":2},"velocity":10,"confidence":0.9,"status":"safe"}}'
```

### Loading the fixture datasets

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # once
python fixtures/load_fixtures.py http://localhost:5000
```

This POSTs all 5 fixture files (`fixtures/*.json`) through the real API in order. Run it
a second time and every event should report as `DUPLICATE` with unchanged states — a
quick manual proof of idempotency.

### Reading audit output

- `GET /audit` — all decision-log entries (optionally `?vehicle_id=...`)
- `GET /audit/<vehicle_id>` — one vehicle's full decision history, newest first
- `POST /replay` — re-reconciles every stored (vehicle_id, timestamp) pair and reports
  whether anything unexpectedly changed (it shouldn't, if the system is deterministic)
- Mongo collection: `audit_trail` in the `vehicle_safety` database

## Audit/decision-trace output files

`audit_output/` contains a static, committed snapshot of the audit trail and vehicle
states produced by loading the 5 fixtures — the literal "audit/decision-trace output
files" deliverable, so it can be inspected without running the system:

- `current_vehicle_states.json` — latest state per vehicle
- `audit_trail_full.json` — every decision-log entry, all vehicles
- `<vehicle_id>.json` — one file per vehicle with its full state history + audit trail

Regenerate it any time with:
```bash
python fixtures/load_fixtures.py
python fixtures/export_audit_output.py
```

## Performance

The Docker image runs the app under **gunicorn** (4 workers × 4 threads), not Flask's
single-threaded dev server — that distinction matters for the NFR target below. Verified
with a 300-event concurrent load test (`concurrency=40`) against the dockerized stack:

| Metric | Target | Measured |
|---|---|---|
| Throughput | ≥100 events/sec | **158.9 events/sec** |
| Latency (p95) | <500ms | **312ms** |
| Success rate | — | 100% (300/300) |

## Fixtures (edge cases)

| File | Scenario |
|---|---|
| `01_late_event.json` | A sensor reading arrives out of order, filling a gap between two existing readings; a later AI event has no exact sensor match and must be interpolated |
| `02_conflicting_sensor_updates.json` | Two sensor readings within 1s of each other; higher-confidence one is chosen deterministically |
| `03_sensor_vs_ai_conflict.json` | High-confidence sensor overrides AI; low-confidence sensor loses to AI |
| `04_blockchain_vs_sensor_conflict.json` | Newer blockchain log overrides a stale sensor reading; an even-newer sensor reading then overrides the now-stale blockchain log |
| `05_duplicate_replay.json` | The exact same event posted twice — must be detected as a duplicate, no new state version or audit entry |

## Tests

```bash
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pytest -q
```

53 tests covering: event validation, state reconstruction (as-of lookups, interpolation,
sensor-conflict resolution), all conflict-resolution rules (including confidence/timestamp
boundary cases), audit trail shape, replay/idempotency, and end-to-end API behavior
including all 5 fixtures. Tests run against an in-memory MongoDB (`mongomock`), no real
database required.

## Constraints honored

Python/Flask/JS/HTML/CSS/MongoDB/Git/Docker only; no Kafka/Redis/distributed
infrastructure; no ML/LLM components (the AI anomaly detector is treated as an external
black box whose already-computed alerts are consumed as input, never generated by this
system); blockchain compliance logs are simulated locally, not a real chain.
