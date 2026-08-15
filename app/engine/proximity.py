"""Multi-vehicle proximity alerts (bonus scope).

Compares each vehicle's most recently reconciled position against every
other vehicle's, within a time window, and flags pairs that are both close
together AND closing distance quickly - a lightweight collision-risk
signal built entirely from data the system already has (no new sensor
fields required).

Velocity vectors aren't part of the event schema (sensor events only carry
a scalar `velocity`), so "closing speed" is estimated empirically from each
vehicle's own last two reconciled positions - the vehicle's observed
trajectory - rather than trusting a self-reported heading.
"""
import math
from datetime import timedelta

from app import config, db


def estimate_velocity_vector(vehicle_id, at_timestamp):
    """(vx, vy) estimated from the two most recent positioned states for
    `vehicle_id` at or before `at_timestamp`, or None if fewer than two
    such states exist."""
    docs = list(
        db.vehicle_states_col()
        .find(
            {
                "vehicle_id": vehicle_id,
                "timestamp": {"$lte": at_timestamp},
                "position": {"$ne": None},
            }
        )
        .sort("timestamp", -1)
        .limit(2)
    )
    if len(docs) < 2:
        return None

    newer, older = docs[0], docs[1]
    dt = (newer["timestamp"] - older["timestamp"]).total_seconds()
    if dt <= 0:
        return None

    p_new, p_old = newer["position"], older["position"]
    if not isinstance(p_new, dict) or not isinstance(p_old, dict):
        return None

    axes = set(p_new) & set(p_old)
    if not axes:
        return None
    return {axis: (p_new[axis] - p_old[axis]) / dt for axis in axes}


def _distance(pos_a, pos_b):
    axes = set(pos_a) & set(pos_b)
    if not axes:
        return None
    return math.sqrt(sum((pos_a[axis] - pos_b[axis]) ** 2 for axis in axes))


def compute_proximity(vehicle_a_id, position_a, timestamp_a, vehicle_b_id, position_b, timestamp_b):
    """Pure function: given two vehicles' positions (+ timestamps used only
    to estimate their velocity vectors), return a proximity assessment or
    None if a distance can't be computed."""
    distance = _distance(position_a, position_b)
    if distance is None:
        return None

    # Cheap check first: distance is pure arithmetic on positions we
    # already have in hand. Only pay for velocity estimation (2 extra
    # MongoDB round-trips) when a pair is actually close enough to matter -
    # otherwise every reconciliation would do O(other vehicles) DB queries
    # even for vehicles nowhere near each other, which is the N+1 pattern
    # that showed up as a real latency regression under load.
    if distance >= config.PROXIMITY_DISTANCE_THRESHOLD:
        return {"distance": distance, "closing_speed": None, "severity": None, "reason": None}

    vel_a = estimate_velocity_vector(vehicle_a_id, timestamp_a)
    vel_b = estimate_velocity_vector(vehicle_b_id, timestamp_b)

    closing_speed = None
    if vel_a is not None and vel_b is not None and distance > 0:
        axes = set(position_a) & set(position_b) & set(vel_a) & set(vel_b)
        if axes:
            rel_pos = {axis: position_b[axis] - position_a[axis] for axis in axes}
            rel_vel = {axis: vel_b[axis] - vel_a[axis] for axis in axes}
            range_rate = sum(rel_pos[axis] * rel_vel[axis] for axis in axes) / distance
            closing_speed = -range_rate  # positive = approaching

    if closing_speed is not None and closing_speed > config.PROXIMITY_CLOSING_SPEED_THRESHOLD:
        severity = "danger"
        reason = f"distance_{distance:.2f}_closing_speed_{closing_speed:.2f}"
    else:
        severity = "alert"
        reason = f"distance_{distance:.2f}_within_threshold"

    return {"distance": distance, "closing_speed": closing_speed, "severity": severity, "reason": reason}


def check_proximity_for_vehicle(vehicle_id, timestamp, position):
    """Compare `vehicle_id`'s state at `timestamp` against every other
    vehicle's recent state, upserting a proximity_alerts doc for any pair
    within the distance threshold. Returns the list of alert docs written
    (empty if none)."""
    if not isinstance(position, dict):
        return []

    window = timedelta(seconds=config.PROXIMITY_TIME_WINDOW_SECONDS)
    candidates_pipeline = [
        {
            "$match": {
                "vehicle_id": {"$ne": vehicle_id},
                "superseded": False,
                "position": {"$ne": None},
                "timestamp": {"$gte": timestamp - window, "$lte": timestamp + window},
            }
        },
        {"$sort": {"vehicle_id": 1, "timestamp": -1}},
        {"$group": {"_id": "$vehicle_id", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]
    others = list(db.vehicle_states_col().aggregate(candidates_pipeline))

    written = []
    for other in others:
        result = compute_proximity(
            vehicle_id, position, timestamp, other["vehicle_id"], other["position"], other["timestamp"]
        )
        if result is None or result["severity"] is None:
            continue

        vehicle_a, vehicle_b = sorted([vehicle_id, other["vehicle_id"]])
        alert_timestamp = max(timestamp, other["timestamp"])
        doc = {
            "vehicle_a": vehicle_a,
            "vehicle_b": vehicle_b,
            "timestamp": alert_timestamp,
            "distance": result["distance"],
            "closing_speed": result["closing_speed"],
            "severity": result["severity"],
            "reason": result["reason"],
        }
        db.proximity_alerts_col().update_one(
            {"vehicle_a": vehicle_a, "vehicle_b": vehicle_b, "timestamp": alert_timestamp},
            {"$set": doc},
            upsert=True,
        )
        written.append(doc)

    return written
