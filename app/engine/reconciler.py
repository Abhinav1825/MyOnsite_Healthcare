"""Reconciler orchestration: ties reconstruction + conflict resolution
together into one deterministic decision per (vehicle_id, timestamp), and
persists both the resulting vehicle state and its audit trail entry.

Determinism & idempotency contract
-----------------------------------
`reconcile(vehicle_id, timestamp)` is defined so that calling it twice with
the same underlying event data is a true no-op: it recomputes the decision,
compares it against whatever is already stored for that exact
(vehicle_id, timestamp), and only writes a new version if the computed
result actually differs (i.e. a previously-unseen/late event changed the
input set). This is what satisfies the PRD's idempotency and replay
requirements without needing a separate "have I seen this before" flag.

Late-event handling scope: a late event triggers reconciliation of its OWN
timestamp only. State at other timepoints for the same vehicle is
recomputed lazily, the next time something touches them (e.g. a fresh
read or replay) - `state(vehicle, T) = f(events(vehicle, timestamp <= T))`
is a pure function, so this is always safe to recompute on demand.
"""
from datetime import datetime, timezone

from app import db
from app.engine.conflict import determine_safety_state
from app.engine.reconstruction import gather_relevant_events


def _event_ref(event):
    return None if event is None else event["event_id"]


def _compute_events_considered(gathered):
    ids = set()
    for key in ("sensor_event", "ai_event", "blockchain_event"):
        ref = _event_ref(gathered[key])
        if ref:
            ids.add(ref)
    ids.update(gathered.get("sensor_considered_ids") or [])
    return sorted(ids)


def reconcile(vehicle_id, timestamp):
    """Reconcile one (vehicle_id, timestamp) point. Returns
    (vehicle_state_doc, audit_doc, created: bool) - created is False when
    the computed result was identical to what was already stored (a
    replay / idempotent no-op)."""
    gathered = gather_relevant_events(vehicle_id, timestamp)

    final_status, source_of_truth, reason, conflicts_resolved = determine_safety_state(
        gathered["sensor_event"], gathered["ai_event"], gathered["blockchain_event"]
    )

    if gathered["sensor_conflicted"]:
        conflicts_resolved["sensor_vs_sensor"] = "resolved_by_highest_confidence"

    events_considered = _compute_events_considered(gathered)

    existing = list(
        db.vehicle_states_col()
        .find({"vehicle_id": vehicle_id, "timestamp": timestamp})
        .sort("version", -1)
        .limit(1)
    )
    previous = existing[0] if existing else None

    unchanged = (
        previous is not None
        and previous.get("safety_state") == final_status
        and previous.get("source_of_truth") == source_of_truth
        and previous.get("decision_reason") == reason
        and sorted(previous.get("events_considered", [])) == events_considered
    )

    if unchanged:
        audit_doc = db.audit_trail_col().find_one(
            {"vehicle_id": vehicle_id, "timestamp": timestamp, "version": previous["version"]}
        )
        return previous, audit_doc, False

    new_version = (previous["version"] + 1) if previous else 1

    if previous is not None:
        db.vehicle_states_col().update_one(
            {"_id": previous["_id"]}, {"$set": {"superseded": True}}
        )

    state_doc = {
        "vehicle_id": vehicle_id,
        "timestamp": timestamp,
        "version": new_version,
        "position": gathered["position"],
        "velocity": gathered["velocity"],
        "safety_state": final_status,
        "source_of_truth": source_of_truth,
        "decision_reason": reason,
        "superseded": False,
        "interpolated": gathered["interpolated"],
        "events_considered": events_considered,
        "reconciled_at": datetime.now(timezone.utc),
    }
    db.vehicle_states_col().insert_one(dict(state_doc))

    audit_doc = {
        "vehicle_id": vehicle_id,
        "timestamp": timestamp,
        "version": new_version,
        "events_considered": events_considered,
        "conflicts_resolved": conflicts_resolved,
        "final_state": final_status,
        "decision_reason": reason,
        "generated_at": datetime.now(timezone.utc),
    }
    db.audit_trail_col().insert_one(dict(audit_doc))

    return state_doc, audit_doc, True


def reconcile_event(normalized_event):
    """Convenience wrapper: reconcile the timepoint introduced by a single
    freshly-ingested (already deduplicated) event."""
    return reconcile(normalized_event["vehicle_id"], normalized_event["timestamp"])
