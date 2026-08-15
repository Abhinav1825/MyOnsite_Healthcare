"""Event ingestion: validate, deduplicate, and durably store raw events.

This is the only place events are written to the `events` collection. The
unique index on `event_id` (see app/db.py) is what makes re-POSTing the
exact same event a no-op rather than a duplicate - the source of the
system's idempotency guarantee.
"""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app import db
from app.models.event import validate_event


def ingest_event(raw_payload):
    """Validate and store one raw event payload.

    Returns a tuple (normalized_event: dict, is_duplicate: bool).
    Raises app.models.event.ValidationError on malformed input - callers
    are expected to turn that into a 400 response.
    """
    normalized = validate_event(raw_payload)
    document = dict(normalized)
    document["received_at"] = datetime.now(timezone.utc)

    try:
        db.events_col().insert_one(document)
        is_duplicate = False
    except DuplicateKeyError:
        is_duplicate = True

    return normalized, is_duplicate
