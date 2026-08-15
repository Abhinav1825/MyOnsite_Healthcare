from flask import Blueprint, jsonify, request

from app.engine.ingestion import ingest_event
from app.engine.reconciler import reconcile
from app.json_utils import to_json_safe
from app.models.event import ValidationError

events_bp = Blueprint("events", __name__)


@events_bp.post("/events")
def post_event():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "request body must be valid JSON"}), 400

    try:
        normalized, is_duplicate = ingest_event(payload)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    state_doc, audit_doc, created = reconcile(normalized["vehicle_id"], normalized["timestamp"])

    return (
        jsonify(
            {
                "event_id": normalized["event_id"],
                "duplicate": is_duplicate,
                "reconciliation_changed": created,
                "vehicle_state": to_json_safe(state_doc),
                "audit_entry": to_json_safe(audit_doc),
            }
        ),
        200 if is_duplicate else 201,
    )
