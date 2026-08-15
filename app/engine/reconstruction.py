"""State reconstruction: gathers the events relevant to a single
(vehicle_id, timestamp) reconciliation point and derives position/velocity,
including interpolation for gaps and deterministic handling of near-
simultaneous conflicting sensor updates.

All lookups are "as of" queries (timestamp <= T), which is what lets a late
event be folded into history simply by re-running reconciliation for its
own timestamp: state(vehicle, T) is always a pure function of
events(vehicle, timestamp <= T), never of arrival order.
"""
from datetime import timedelta

from app import config, db

_SOURCE_ORDER = {"sensor": 0, "ai": 1, "blockchain": 2}


def _sort_key(event):
    # Deterministic total order: timestamp desc (most recent first), then a
    # fixed tie-break on event_id so identical timestamps never depend on
    # insertion/arrival order.
    return (event["timestamp"], event["event_id"])


def latest_event_at_or_before(vehicle_id, source, timestamp):
    """Most recent event of `source` for `vehicle_id` with timestamp <= T.
    Ties (identical timestamp) are broken deterministically by event_id."""
    candidates = list(
        db.events_col().find(
            {"vehicle_id": vehicle_id, "source": source, "timestamp": {"$lte": timestamp}}
        )
    )
    if not candidates:
        return None
    candidates.sort(key=_sort_key, reverse=True)
    return candidates[0]


def _next_sensor_event_after(vehicle_id, timestamp, within):
    candidates = list(
        db.events_col().find(
            {
                "vehicle_id": vehicle_id,
                "source": "sensor",
                "timestamp": {"$gt": timestamp, "$lte": timestamp + within},
            }
        )
    )
    if not candidates:
        return None
    candidates.sort(key=lambda e: (e["timestamp"], e["event_id"]))
    return candidates[0]


def resolve_conflicting_sensor_updates(vehicle_id, timestamp):
    """Two sensor position reports at near-identical timestamps are treated
    as a conflict. Deterministic resolution: prefer the higher-confidence
    reading; tie-break by event_id. Returns (chosen_event, conflicted: bool,
    considered_event_ids: list)."""
    window = timedelta(seconds=config.SENSOR_CONFLICT_WINDOW_SECONDS)
    candidates = list(
        db.events_col().find(
            {
                "vehicle_id": vehicle_id,
                "source": "sensor",
                "timestamp": {
                    "$gte": timestamp - window,
                    "$lte": timestamp + window,
                },
            }
        )
    )
    if not candidates:
        return None, False, []

    from app.engine.conflict import extract_confidence

    candidates.sort(
        key=lambda e: (extract_confidence(e), e["timestamp"], e["event_id"]), reverse=True
    )
    chosen = candidates[0]
    considered_ids = [c["event_id"] for c in candidates]
    conflicted = len(candidates) > 1
    return chosen, conflicted, considered_ids


def interpolate_position_velocity(vehicle_id, timestamp, chosen_sensor_event):
    """Return (position, velocity, interpolated: bool) for `timestamp`.

    If the chosen sensor reading's own timestamp already matches T exactly,
    its raw values are used as-is. Otherwise, if a sensor reading exists
    both before and after T (within the late-event window), position and
    velocity are linearly interpolated between them.
    """
    if chosen_sensor_event is None:
        return None, None, False

    data = chosen_sensor_event.get("data", {}) or {}
    position = data.get("position")
    velocity = data.get("velocity")

    if chosen_sensor_event["timestamp"] == timestamp:
        return position, velocity, False

    window = timedelta(minutes=config.LATE_EVENT_WINDOW_MINUTES)
    after_event = _next_sensor_event_after(vehicle_id, chosen_sensor_event["timestamp"], window)
    if after_event is None or timestamp <= chosen_sensor_event["timestamp"]:
        # Nothing to interpolate against - use the last known reading as-is.
        return position, velocity, False

    t0 = chosen_sensor_event["timestamp"]
    t1 = after_event["timestamp"]
    span = (t1 - t0).total_seconds()
    if span <= 0:
        return position, velocity, False

    frac = (timestamp - t0).total_seconds() / span
    frac = max(0.0, min(1.0, frac))

    after_data = after_event.get("data", {}) or {}
    interp_position = None
    p0, p1 = position, after_data.get("position")
    if isinstance(p0, dict) and isinstance(p1, dict):
        interp_position = {
            axis: p0.get(axis, 0) + (p1.get(axis, 0) - p0.get(axis, 0)) * frac
            for axis in set(p0) | set(p1)
        }

    interp_velocity = velocity
    v0, v1 = velocity, after_data.get("velocity")
    if isinstance(v0, (int, float)) and isinstance(v1, (int, float)):
        interp_velocity = v0 + (v1 - v0) * frac

    return interp_position, interp_velocity, True


def gather_relevant_events(vehicle_id, timestamp):
    """Assemble the (sensor, ai, blockchain) events relevant to reconciling
    `vehicle_id` at `timestamp`, plus interpolation + sensor-conflict
    metadata. Any of the three may be None if that source has no event at
    or before `timestamp`."""
    sensor_event, sensor_conflicted, sensor_considered_ids = resolve_conflicting_sensor_updates(
        vehicle_id, timestamp
    )
    if sensor_event is None:
        sensor_event = latest_event_at_or_before(vehicle_id, "sensor", timestamp)

    ai_event = latest_event_at_or_before(vehicle_id, "ai", timestamp)
    blockchain_event = latest_event_at_or_before(vehicle_id, "blockchain", timestamp)

    position, velocity, interpolated = interpolate_position_velocity(
        vehicle_id, timestamp, sensor_event
    )

    return {
        "sensor_event": sensor_event,
        "ai_event": ai_event,
        "blockchain_event": blockchain_event,
        "position": position,
        "velocity": velocity,
        "interpolated": interpolated,
        "sensor_conflicted": sensor_conflicted,
        "sensor_considered_ids": sensor_considered_ids,
    }
