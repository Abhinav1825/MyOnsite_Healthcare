"""Central configuration and tunable constants.

All values can be overridden via environment variables so the same code
works locally, in Docker, and in tests.
"""
import os

# --- MongoDB ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "vehicle_safety")

# --- Reconciliation rules (from the PRD) ---
# Sensor data is trusted over an AI alert only when the sensor's own
# reported confidence is at/above this threshold. Below it, the AI alert
# wins instead.
SENSOR_CONFIDENCE_THRESHOLD = float(os.environ.get("SENSOR_CONFIDENCE_THRESHOLD", "0.8"))

# A blockchain compliance log overrides a sensor-derived state only when
# the blockchain event's timestamp is strictly newer than the sensor
# event's timestamp; otherwise the sensor value stands.
# (No extra constant needed - it's a direct timestamp comparison.)

# --- Late event handling ---
# Events may arrive up to this many minutes after their own timestamp and
# must still be correctly folded into history ("late/out-of-order events").
LATE_EVENT_WINDOW_MINUTES = int(os.environ.get("LATE_EVENT_WINDOW_MINUTES", "10"))

# --- Conflicting-update window ---
# Two sensor readings for the same vehicle within this many seconds of each
# other are treated as "near-identical timestamps" needing conflict
# handling rather than two independent readings.
SENSOR_CONFLICT_WINDOW_SECONDS = int(os.environ.get("SENSOR_CONFLICT_WINDOW_SECONDS", "2"))

VALID_SOURCES = ("sensor", "ai", "blockchain")
VALID_SAFETY_STATES = ("safe", "alert", "danger")

# --- Multi-vehicle proximity (bonus scope) ---
# Two vehicles closer than this are flagged with a proximity alert.
PROXIMITY_DISTANCE_THRESHOLD = float(os.environ.get("PROXIMITY_DISTANCE_THRESHOLD", "10.0"))

# Only vehicles with a reconciled state within this many seconds of each
# other are compared - stale positions from long ago shouldn't be treated
# as "currently near" one another.
PROXIMITY_TIME_WINDOW_SECONDS = int(os.environ.get("PROXIMITY_TIME_WINDOW_SECONDS", "30"))

# If two vehicles are within PROXIMITY_DISTANCE_THRESHOLD AND closing at
# more than this speed (position units/sec, estimated from trajectory),
# the alert is escalated from "alert" to "danger".
PROXIMITY_CLOSING_SPEED_THRESHOLD = float(
    os.environ.get("PROXIMITY_CLOSING_SPEED_THRESHOLD", "0.5")
)
