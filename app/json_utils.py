"""Recursively converts datetime objects (and Mongo's ObjectId) into JSON-safe
values so route handlers can pass raw Mongo documents straight to jsonify().
"""
from datetime import datetime

from bson import ObjectId


def to_json_safe(value):
    if isinstance(value, dict):
        return {k: to_json_safe(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [to_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    return value
