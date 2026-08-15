"""Tests for the NFRs: determinism, idempotency, and replayability."""
from datetime import datetime, timedelta, timezone

from app import db
from app.engine.ingestion import ingest_event
from app.engine.reconciler import reconcile
from app.replay import replay_all, replay_event_payloads

VEH = "veh_replay"
T0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)

SENSOR_EVENT = {
    "source": "sensor",
    "vehicle_id": VEH,
    "timestamp": T0.isoformat(),
    "data": {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9, "status": "safe"},
}


def test_reconciling_twice_with_no_new_data_is_a_noop(mongo_db):
    ingest_event(SENSOR_EVENT)
    state1, audit1, created1 = reconcile(VEH, T0)
    state2, audit2, created2 = reconcile(VEH, T0)

    assert created1 is True
    assert created2 is False
    assert state1["version"] == state2["version"] == 1
    assert db.audit_trail_col().count_documents({"vehicle_id": VEH}) == 1


def test_reposting_the_same_event_does_not_duplicate_or_change_state(mongo_db):
    ingest_event(SENSOR_EVENT)
    reconcile(VEH, T0)

    _, is_duplicate = ingest_event(SENSOR_EVENT)  # exact repost
    assert is_duplicate is True

    _, _, created = reconcile(VEH, T0)
    assert created is False
    assert db.events_col().count_documents({"vehicle_id": VEH}) == 1
    assert db.vehicle_states_col().count_documents({"vehicle_id": VEH}) == 1
    assert db.audit_trail_col().count_documents({"vehicle_id": VEH}) == 1


def test_late_event_creates_new_version_without_duplicating(mongo_db):
    ingest_event(SENSOR_EVENT)
    reconcile(VEH, T0)

    # A genuinely new (late) AI event at the SAME timestamp changes the
    # inputs for that timepoint, so re-reconciling should now produce a
    # new version rather than being a no-op.
    ingest_event(
        {
            "source": "ai",
            "vehicle_id": VEH,
            "timestamp": T0.isoformat(),
            "data": {"alert": "potential_collision", "confidence": 0.95},
        }
    )
    state, audit, created = reconcile(VEH, T0)

    assert created is True
    assert state["version"] == 2
    assert db.audit_trail_col().count_documents({"vehicle_id": VEH}) == 2
    # the old version should now be marked superseded, not deleted
    old = db.vehicle_states_col().find_one({"vehicle_id": VEH, "version": 1})
    assert old["superseded"] is True


def test_replay_all_is_consistent(mongo_db):
    ingest_event(SENSOR_EVENT)
    reconcile(VEH, T0)

    report = replay_all()
    assert report["consistent"] is True
    assert report["unexpected_changes"] == []


def test_replay_event_payloads_reports_duplicates_on_second_pass(mongo_db):
    events = [SENSOR_EVENT]

    first = replay_event_payloads(events)
    assert first["new_events"] == 1
    assert first["duplicate_events"] == 0

    second = replay_event_payloads(events)
    assert second["new_events"] == 0
    assert second["duplicate_events"] == 1
    assert all(r["changed"] is False for r in second["reconciliations"])
