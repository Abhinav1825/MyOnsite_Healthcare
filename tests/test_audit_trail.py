"""Tests that the audit trail is generated with the shape/fields the PRD
requires, and that it captures the actual decision made."""
from datetime import datetime, timedelta, timezone

from app.engine.ingestion import ingest_event
from app.engine.reconciler import reconcile

VEH = "veh_audit"
T0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)

REQUIRED_AUDIT_FIELDS = {
    "vehicle_id",
    "timestamp",
    "events_considered",
    "conflicts_resolved",
    "final_state",
    "decision_reason",
    "version",
}


def test_audit_entry_has_required_shape(mongo_db):
    ingest_event(
        {
            "source": "sensor",
            "vehicle_id": VEH,
            "timestamp": T0.isoformat(),
            "data": {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9, "status": "safe"},
        }
    )
    _, audit_doc, created = reconcile(VEH, T0)

    assert created is True
    assert REQUIRED_AUDIT_FIELDS.issubset(audit_doc.keys())
    assert audit_doc["vehicle_id"] == VEH
    assert audit_doc["final_state"] == "safe"


def test_audit_entry_records_conflict_resolution(mongo_db):
    ingest_event(
        {
            "source": "sensor",
            "vehicle_id": VEH,
            "timestamp": T0.isoformat(),
            "data": {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.3, "status": "safe"},
        }
    )
    ingest_event(
        {
            "source": "ai",
            "vehicle_id": VEH,
            "timestamp": T0.isoformat(),
            "data": {"alert": "potential_collision", "confidence": 0.9},
        }
    )
    _, audit_doc, _ = reconcile(VEH, T0)

    assert audit_doc["final_state"] == "danger"
    assert audit_doc["conflicts_resolved"]["sensor_vs_ai"] == "used_ai"
    assert "confidence" in audit_doc["decision_reason"]


def test_every_reconciliation_produces_an_audit_entry_even_without_conflict(mongo_db):
    ingest_event(
        {
            "source": "sensor",
            "vehicle_id": VEH,
            "timestamp": T0.isoformat(),
            "data": {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9, "status": "safe"},
        }
    )
    _, audit_doc, _ = reconcile(VEH, T0)
    assert audit_doc["conflicts_resolved"] == {}
