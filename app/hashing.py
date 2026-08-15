"""Shared canonical-JSON + hashing helpers, used both for content-derived
event IDs (app/models/event.py) and mock blockchain block hashes
(app/engine/blockchain.py) - kept in one place so both use identical,
deterministic serialization.
"""
import hashlib
import json


def canonical_json(data):
    # Sorted, whitespace-free JSON so semantically-identical payloads always
    # hash the same way regardless of key order.
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(*parts):
    payload = "|".join(str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
