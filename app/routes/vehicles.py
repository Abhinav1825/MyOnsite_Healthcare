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


@vehicles_bp.get("/vehicles/trajectories")
def list_trajectories():
    """Every vehicle's full position-over-time history in one call (all
    versions, oldest first per vehicle) - built for the 2D trajectory plot
    so the dashboard doesn't need one request per vehicle. Note: this
    route is registered before /vehicles/<vehicle_id> - Flask/Werkzeug
    matches static path segments before variable ones regardless of
    registration order, so "trajectories" is never captured as a
    vehicle_id."""
    docs = list(
        db.vehicle_states_col()
        .find({"position": {"$ne": None}}, {"vehicle_id": 1, "timestamp": 1, "position": 1, "safety_state": 1, "superseded": 1})
        .sort([("vehicle_id", 1), ("timestamp", 1)])
    )
    by_vehicle = {}
    for d in docs:
        by_vehicle.setdefault(d["vehicle_id"], []).append(to_json_safe(d))
    return jsonify(by_vehicle)


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
