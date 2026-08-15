"""Tests for state reconstruction: as-of lookups, sensor-conflict
resolution, and interpolation."""
from datetime import datetime, timedelta, timezone

from app import db
from app.engine.reconstruction import (
    gather_relevant_events,
    interpolate_position_velocity,
    latest_event_at_or_before,
    resolve_conflicting_sensor_updates,
)
from app.engine.ingestion import ingest_event

VEH = "veh_recon"


def post(source, timestamp, data):
    ingest_event(
        {
            "source": source,
            "vehicle_id": VEH,
            "timestamp": timestamp.isoformat(),
            "data": data,
        }
    )


def test_latest_event_at_or_before_picks_most_recent_not_future(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)
    t2 = t0 + timedelta(minutes=10)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9})
    post("sensor", t2, {"position": {"x": 10, "y": 0}, "velocity": 2, "confidence": 0.9})

    found = latest_event_at_or_before(VEH, "sensor", t1)
    assert found["timestamp"] == t0  # t2 is in the future relative to t1


def test_late_event_is_visible_once_inserted(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    t_late = t0 + timedelta(minutes=2)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9})

    assert latest_event_at_or_before(VEH, "sensor", t_late)["timestamp"] == t0

    post("sensor", t_late, {"position": {"x": 5, "y": 0}, "velocity": 3, "confidence": 0.9})
    assert latest_event_at_or_before(VEH, "sensor", t_late)["timestamp"] == t_late


def test_conflicting_sensor_updates_picks_higher_confidence(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.6})
    post("sensor", t1, {"position": {"x": 1, "y": 1}, "velocity": 2, "confidence": 0.9})

    chosen, conflicted, considered = resolve_conflicting_sensor_updates(VEH, t0)
    assert conflicted is True
    assert chosen["data"]["confidence"] == 0.9
    assert len(considered) == 2


def test_no_conflict_when_readings_far_apart(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=5)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.6})
    post("sensor", t1, {"position": {"x": 1, "y": 1}, "velocity": 2, "confidence": 0.9})

    chosen, conflicted, considered = resolve_conflicting_sensor_updates(VEH, t0)
    assert conflicted is False
    assert len(considered) == 1


def test_interpolation_between_two_sensor_readings(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=10)
    mid = t0 + timedelta(minutes=5)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 10, "confidence": 0.9})
    post("sensor", t1, {"position": {"x": 100, "y": 0}, "velocity": 20, "confidence": 0.9})

    sensor_event = latest_event_at_or_before(VEH, "sensor", mid)
    position, velocity, interpolated = interpolate_position_velocity(VEH, mid, sensor_event)

    assert interpolated is True
    assert position["x"] == 50.0
    assert velocity == 15.0


def test_gather_relevant_events_combines_all_sources(mongo_db):
    t0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
    post("sensor", t0, {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9, "status": "safe"})
    post("ai", t0, {"alert": "none", "confidence": 0.5})
    post("blockchain", t0, {"compliance_status": "pass"})

    result = gather_relevant_events(VEH, t0)
    assert result["sensor_event"] is not None
    assert result["ai_event"] is not None
    assert result["blockchain_event"] is not None
