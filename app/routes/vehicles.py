from flask import Blueprint, jsonify

from app import db
from app.json_utils import to_json_safe

vehicles_bp = Blueprint("vehicles", __name__)


@vehicles_bp.get("/vehicles")
def list_vehicles():
    """Current (latest, non-superseded) safety state for every known vehicle."""
    pipeline = [
        {"$match": {"superseded": False}},
        {"$sort": {"vehicle_id": 1, "timestamp": -1}},
        {"$group": {"_id": "$vehicle_id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"vehicle_id": 1}},
    ]
    docs = list(db.vehicle_states_col().aggregate(pipeline))
    return jsonify([to_json_safe(d) for d in docs])


@vehicles_bp.get("/vehicles/<vehicle_id>")
def get_vehicle(vehicle_id):
    """Full reconciled state history for one vehicle (all versions, all
    timepoints), most recent first - lets the dashboard show how the
    vehicle's status evolved, including any superseded entries produced by
    late-arriving events."""
    docs = list(
        db.vehicle_states_col()
        .find({"vehicle_id": vehicle_id})
        .sort([("timestamp", -1), ("version", -1)])
    )
    if not docs:
        return jsonify({"error": f"no state found for vehicle_id {vehicle_id!r}"}), 404
    return jsonify([to_json_safe(d) for d in docs])
