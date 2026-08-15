"""Event schema validation and normalization.

Validates the top-level `POST /events` envelope described in the PRD:

    {
      "source": "sensor|ai|blockchain",
      "vehicle_id": "string",
      "timestamp": "ISO 8601",
      "data": { ... }
    }

Deliberately does NOT enforce a rigid schema on `data` beyond "is an
object" - the PRD leaves the inner payload source-specific and open-ended.
Fields the conflict-resolution rules actually depend on (e.g. `confidence`)
are read defensively downstream in `app/engine/conflict.py`, with sane
defaults, rather than being force-required here.
"""
import hashlib
import json
from datetime import datetime, timezone

from dateutil import parser as dateutil_parser

from app import config


class ValidationError(Exception):
    """Raised when an incoming event payload fails validation."""


def _parse_timestamp(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise ValidationError("timestamp must be a non-empty ISO 8601 string")
    try:
        dt = dateutil_parser.isoparse(raw)
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"timestamp is not valid ISO 8601: {raw!r}")
    if dt.tzinfo is None:
        # Treat naive timestamps as UTC so comparisons are always well-defined.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _canonical_json(data):
    # Sorted, whitespace-free JSON so semantically-identical payloads always
    # hash to the same event_id regardless of key order.
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_id(source, vehicle_id, timestamp_dt, data):
    payload = f"{source}|{vehicle_id}|{timestamp_dt.isoformat()}|{_canonical_json(data)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_event(raw_payload):
    """Validate and normalize a raw event dict.

    Returns a normalized dict with keys:
        event_id, source, vehicle_id, timestamp (datetime, UTC), data
    Raises ValidationError with a human-readable reason on any failure.
    """
    if not isinstance(raw_payload, dict):
        raise ValidationError("request body must be a JSON object")

    missing = [f for f in ("source", "vehicle_id", "timestamp", "data") if f not in raw_payload]
    if missing:
        raise ValidationError(f"missing required field(s): {', '.join(missing)}")

    source = raw_payload["source"]
    if source not in config.VALID_SOURCES:
        raise ValidationError(
            f"invalid source {source!r}; must be one of {config.VALID_SOURCES}"
        )

    vehicle_id = raw_payload["vehicle_id"]
    if not isinstance(vehicle_id, str) or not vehicle_id.strip():
        raise ValidationError("vehicle_id must be a non-empty string")

    timestamp_dt = _parse_timestamp(raw_payload["timestamp"])

    data = raw_payload["data"]
    if not isinstance(data, dict):
        raise ValidationError("data must be a JSON object")

    event_id = compute_event_id(source, vehicle_id, timestamp_dt, data)

    return {
        "event_id": event_id,
        "source": source,
        "vehicle_id": vehicle_id,
        "timestamp": timestamp_dt,
        "data": data,
    }
