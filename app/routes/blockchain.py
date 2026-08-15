from flask import Blueprint, jsonify, request

from app.engine.blockchain import submit_compliance_block, get_chain, verify_chain
from app.json_utils import to_json_safe
from app.models.event import ValidationError, parse_timestamp

blockchain_bp = Blueprint("blockchain", __name__)


@blockchain_bp.post("/blockchain/submit")
def post_blockchain_submit():
    """Submit a compliance record to the mock chain for one vehicle. Body:
    {"vehicle_id": str, "timestamp": ISO 8601, "data": {...compliance payload...}}
    Internally this both appends a chain block AND feeds the normal
    reconciliation pipeline (equivalent to POST /events with
    source="blockchain"), so the two stores never disagree."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    vehicle_id = payload.get("vehicle_id")
    if not isinstance(vehicle_id, str) or not vehicle_id.strip():
        return jsonify({"error": "vehicle_id must be a non-empty string"}), 400

    data = payload.get("data")
    if not isinstance(data, dict):
        return jsonify({"error": "data must be a JSON object"}), 400

    try:
        timestamp = parse_timestamp(payload.get("timestamp"))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    block_doc, state_doc, audit_doc, is_new_block = submit_compliance_block(vehicle_id, timestamp, data)

    return (
        jsonify(
            {
                "new_block": is_new_block,
                "block": to_json_safe(block_doc) if block_doc else None,
                "vehicle_state": to_json_safe(state_doc),
                "audit_entry": to_json_safe(audit_doc),
            }
        ),
        201 if is_new_block else 200,
    )


@blockchain_bp.get("/blockchain/<vehicle_id>")
def get_blockchain(vehicle_id):
    chain = get_chain(vehicle_id)
    if not chain:
        return jsonify({"error": f"no chain found for vehicle_id {vehicle_id!r}"}), 404
    return jsonify([to_json_safe(b) for b in chain])


@blockchain_bp.get("/blockchain/<vehicle_id>/verify")
def get_blockchain_verify(vehicle_id):
    return jsonify(verify_chain(vehicle_id))
