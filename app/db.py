"""MongoDB connection and collection accessors.

A single module-level client is used in normal (Flask/Docker) operation.
Tests can inject an in-memory `mongomock` database instead by calling
`set_db()` directly - this keeps the rest of the codebase agnostic to
which backend is in use, since both expose the same pymongo-compatible API.
"""
from pymongo import ASCENDING

from app import config

_db = None  # lazily initialized real/mock database handle


def _build_real_client():
    from pymongo import MongoClient
    # tz_aware=True: pymongo returns naive (UTC-implied) datetimes by
    # default, which breaks comparisons against our own tz-aware datetimes.
    # Keeping everything explicitly UTC-aware end to end avoids that class
    # of bug entirely.
    client = MongoClient(config.MONGO_URI, tz_aware=True)
    return client[config.MONGO_DB_NAME]


def set_db(database):
    """Explicitly set the active database (used by tests to inject mongomock)."""
    global _db
    _db = database
    _ensure_indexes(_db)


def get_db():
    global _db
    if _db is None:
        _db = _build_real_client()
        _ensure_indexes(_db)
    return _db


def _ensure_indexes(database):
    # events: append-only log, deduplicated by content-derived event_id
    database.events.create_index([("event_id", ASCENDING)], unique=True, name="uniq_event_id")
    database.events.create_index(
        [("vehicle_id", ASCENDING), ("timestamp", ASCENDING)], name="vehicle_timestamp"
    )

    # vehicle_states: time-ordered, versioned history per vehicle
    database.vehicle_states.create_index(
        [("vehicle_id", ASCENDING), ("timestamp", ASCENDING), ("version", ASCENDING)],
        name="vehicle_timestamp_version",
    )

    # audit_trail: one decision record per reconciliation
    database.audit_trail.create_index(
        [("vehicle_id", ASCENDING), ("timestamp", ASCENDING)], name="vehicle_timestamp"
    )
    database.audit_trail.create_index(
        [("vehicle_id", ASCENDING), ("timestamp", ASCENDING), ("version", ASCENDING)],
        unique=True,
        name="uniq_decision",
    )


def events_col():
    return get_db().events


def vehicle_states_col():
    return get_db().vehicle_states


def audit_trail_col():
    return get_db().audit_trail


def reset_db():
    """Test helper: drop all collections and re-create indexes."""
    database = get_db()
    database.events.delete_many({})
    database.vehicle_states.delete_many({})
    database.audit_trail.delete_many({})
