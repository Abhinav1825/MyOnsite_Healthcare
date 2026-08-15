"""Replay: re-run reconciliation over already-stored (or freshly re-posted)
events to verify the system's determinism/idempotency guarantees hold.

Because `reconcile()` is a pure function of stored events, "replaying"
simply means calling it again for every (vehicle_id, timestamp) pair that
already has events, and checking that nothing changes.
"""
from app import db
from app.engine.ingestion import ingest_event
from app.engine.reconciler import reconcile


def distinct_vehicle_timestamps():
    """All (vehicle_id, timestamp) pairs that currently have at least one
    stored event - i.e. every timepoint that has ever been reconciled."""
    pipeline = [
        {"$group": {"_id": {"vehicle_id": "$vehicle_id", "timestamp": "$timestamp"}}},
        {"$sort": {"_id.vehicle_id": 1, "_id.timestamp": 1}},
    ]
    return [(doc["_id"]["vehicle_id"], doc["_id"]["timestamp"]) for doc in db.events_col().aggregate(pipeline)]


def replay_all():
    """Re-reconcile every known (vehicle_id, timestamp) pair. Returns a
    report dict: total pairs checked, and any pairs where reconciliation
    unexpectedly produced a new version (which would indicate a
    determinism bug, since no new events were introduced)."""
    checked = 0
    changed = []
    for vehicle_id, timestamp in distinct_vehicle_timestamps():
        _, _, created = reconcile(vehicle_id, timestamp)
        checked += 1
        if created:
            changed.append({"vehicle_id": vehicle_id, "timestamp": timestamp})
    return {"checked": checked, "unexpected_changes": changed, "consistent": not changed}


def replay_event_payloads(raw_payloads):
    """Re-POST a list of raw event payloads (e.g. loaded from a fixture
    file) through the normal ingestion + reconciliation path. Existing
    events are detected as duplicates (idempotent no-op); the report shows
    how many were new vs duplicate, and whether reconciliation for the
    affected timepoints changed anything."""
    new_count = 0
    duplicate_count = 0
    reconciled = []
    for raw in raw_payloads:
        normalized, is_duplicate = ingest_event(raw)
        if is_duplicate:
            duplicate_count += 1
        else:
            new_count += 1
        _, _, created = reconcile(normalized["vehicle_id"], normalized["timestamp"])
        reconciled.append(
            {
                "vehicle_id": normalized["vehicle_id"],
                "timestamp": normalized["timestamp"],
                "changed": created,
            }
        )
    return {
        "new_events": new_count,
        "duplicate_events": duplicate_count,
        "reconciliations": reconciled,
    }
