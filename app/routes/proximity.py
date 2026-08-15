from flask import Blueprint, jsonify, request

from app import db
from app.json_utils import to_json_safe

proximity_bp = Blueprint("proximity", __name__)


@proximity_bp.get("/proximity")
def list_proximity_alerts():
    """All proximity alerts, optionally filtered to those involving one
    vehicle (?vehicle_id=...), newest first."""
    query = {}
    vehicle_id = request.args.get("vehicle_id")
    if vehicle_id:
        query["$or"] = [{"vehicle_a": vehicle_id}, {"vehicle_b": vehicle_id}]

    docs = list(db.proximity_alerts_col().find(query).sort("timestamp", -1))
    return jsonify([to_json_safe(d) for d in docs])
