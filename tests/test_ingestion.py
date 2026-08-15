"""Tests for event validation + idempotent ingestion."""
import pytest

from app.engine.ingestion import ingest_event
from app.models.event import ValidationError

VALID_EVENT = {
    "source": "sensor",
    "vehicle_id": "veh_test",
    "timestamp": "2026-08-15T07:00:00Z",
    "data": {"position": {"x": 1, "y": 2}, "velocity": 10, "confidence": 0.9},
}


def test_valid_event_accepted(mongo_db):
    normalized, is_duplicate = ingest_event(VALID_EVENT)
    assert is_duplicate is False
    assert normalized["vehicle_id"] == "veh_test"
    assert normalized["source"] == "sensor"


def test_duplicate_event_detected(mongo_db):
    ingest_event(VALID_EVENT)
    _, is_duplicate = ingest_event(VALID_EVENT)
    assert is_duplicate is True


@pytest.mark.parametrize(
    "broken_field,broken_value",
    [
        ("source", "lidar"),  # invalid enum
        ("vehicle_id", ""),  # empty string
        ("timestamp", "not-a-date"),  # invalid ISO 8601
        ("data", "not-an-object"),  # wrong type
    ],
)
def test_malformed_event_rejected(mongo_db, broken_field, broken_value):
    payload = dict(VALID_EVENT)
    payload["data"] = dict(VALID_EVENT["data"])
    payload[broken_field] = broken_value
    with pytest.raises(ValidationError):
        ingest_event(payload)


def test_missing_field_rejected(mongo_db):
    payload = dict(VALID_EVENT)
    del payload["timestamp"]
    with pytest.raises(ValidationError):
        ingest_event(payload)


def test_naive_timestamp_treated_as_utc(mongo_db):
    payload = dict(VALID_EVENT)
    payload["data"] = dict(VALID_EVENT["data"])
    payload["timestamp"] = "2026-08-15T07:00:00"  # no timezone
    normalized, _ = ingest_event(payload)
    assert normalized["timestamp"].tzinfo is not None
