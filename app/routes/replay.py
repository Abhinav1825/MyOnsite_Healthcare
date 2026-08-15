from flask import Blueprint, jsonify, request

from app.json_utils import to_json_safe
from app.replay import replay_all, replay_event_payloads

replay_bp = Blueprint("replay", __name__)


@replay_bp.post("/replay")
def post_replay():
    """Re-reconcile every stored (vehicle_id, timestamp) pair and report
    whether anything unexpectedly changed (it shouldn't, if the system is
    deterministic)."""
    report = replay_all()
    return jsonify(to_json_safe(report))


@replay_bp.post("/replay/events")
def post_replay_events():
    """Re-POST a batch of raw event payloads (e.g. a fixture file's
    contents) through ingestion + reconciliation, to demonstrate
    idempotent replay of historical data."""
    payloads = request.get_json(silent=True)
    if not isinstance(payloads, list):
        return jsonify({"error": "request body must be a JSON array of event payloads"}), 400
    report = replay_event_payloads(payloads)
    return jsonify(to_json_safe(report))
