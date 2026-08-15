from flask import Blueprint, jsonify, request

from app import db
from app.json_utils import to_json_safe

audit_bp = Blueprint("audit", __name__)


@audit_bp.get("/audit")
def list_audit():
    """All audit entries, optionally filtered by ?vehicle_id=, newest first."""
    query = {}
    vehicle_id = request.args.get("vehicle_id")
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    docs = list(db.audit_trail_col().find(query).sort([("timestamp", -1), ("version", -1)]))
    return jsonify([to_json_safe(d) for d in docs])


@audit_bp.get("/audit/<vehicle_id>")
def get_vehicle_audit(vehicle_id):
    docs = list(
        db.audit_trail_col()
        .find({"vehicle_id": vehicle_id})
        .sort([("timestamp", -1), ("version", -1)])
    )
    if not docs:
        return jsonify({"error": f"no audit entries for vehicle_id {vehicle_id!r}"}), 404
    return jsonify([to_json_safe(d) for d in docs])
