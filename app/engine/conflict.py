"""Deterministic conflict-resolution rules.

These are pure functions: given normalized event dicts, they return a
decision plus a human-readable reason string. No I/O, no randomness, no
wall-clock reads - which is what makes the reconciler as a whole
deterministic and safely replayable.

--- Data-schema convention used by this implementation -----------------
The PRD leaves each source's `data` payload open-ended. To make "sensor
and AI disagree" or "blockchain conflicts with sensor" concretely
computable, this implementation adopts one small, explicit convention
(documented here and in the README):

  * Every event's `data` MAY carry a `status` field, one of
    "safe" | "alert" | "danger" - the source's own opinion of the
    vehicle's safety at that moment.
  * If `status` is omitted, it is inferred per-source:
      - sensor:      "safe" (raw telemetry alone implies no verdict)
      - ai:          derived from `data.alert` - a falsy/missing/"none"
                     alert means "safe"; otherwise "danger" if
                     confidence >= SENSOR_CONFIDENCE_THRESHOLD else "alert"
      - blockchain:  derived from `data.compliance_status` - "pass" means
                     "safe", "fail" means "alert"
  * `confidence` (0-1) is read from `data.confidence`, defaulting to 1.0
    for sensor events and 0.5 for AI events if omitted. Blockchain logs
    are treated as deterministic (pass/fail), not probabilistic.
--------------------------------------------------------------------------
"""
from app import config

_STATUS_RANK = {"safe": 0, "alert": 1, "danger": 2}


def extract_status(event):
    data = event.get("data", {}) or {}
    status = data.get("status")
    if status in config.VALID_SAFETY_STATES:
        return status

    source = event["source"]
    if source == "sensor":
        return "safe"
    if source == "ai":
        alert = data.get("alert")
        if not alert or str(alert).lower() == "none":
            return "safe"
        confidence = extract_confidence(event)
        return "danger" if confidence >= config.SENSOR_CONFIDENCE_THRESHOLD else "alert"
    if source == "blockchain":
        compliance_status = str(data.get("compliance_status", "pass")).lower()
        return "safe" if compliance_status == "pass" else "alert"
    return "safe"


def extract_confidence(event):
    data = event.get("data", {}) or {}
    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)):
        return float(confidence)
    return 1.0 if event["source"] == "sensor" else 0.5


def resolve_sensor_vs_ai(sensor_event, ai_event):
    """Rule: if sensor and AI disagree, use sensor if confidence >= threshold,
    otherwise use AI. Returns (status, source_of_truth, reason)."""
    sensor_status = extract_status(sensor_event)
    ai_status = extract_status(ai_event)

    if sensor_status == ai_status:
        return sensor_status, "sensor", f"sensor_and_ai_agree_{sensor_status}"

    sensor_confidence = extract_confidence(sensor_event)
    if sensor_confidence >= config.SENSOR_CONFIDENCE_THRESHOLD:
        return sensor_status, "sensor", f"sensor_confidence_{sensor_confidence:.2f}"

    ai_confidence = extract_confidence(ai_event)
    return (
        ai_status,
        "ai",
        f"sensor_confidence_{sensor_confidence:.2f}_below_threshold_used_ai_confidence_{ai_confidence:.2f}",
    )


def resolve_blockchain_vs_sensor(blockchain_event, sensor_event):
    """Rule: if blockchain log conflicts with sensor, use blockchain if its
    timestamp is newer, otherwise use sensor. Returns (status, source_of_truth, reason)."""
    blockchain_status = extract_status(blockchain_event)
    sensor_status = extract_status(sensor_event)

    if blockchain_status == sensor_status:
        return blockchain_status, "blockchain", f"blockchain_and_sensor_agree_{blockchain_status}"

    if blockchain_event["timestamp"] > sensor_event["timestamp"]:
        return blockchain_status, "blockchain", "blockchain_newer_than_sensor"

    return sensor_status, "sensor", "blockchain_stale_used_sensor"


def determine_safety_state(sensor_event, ai_event, blockchain_event):
    """Combine whichever of the three source events are present (any may be
    None) into one final decision, applying the PRD's two pairwise rules in
    a fixed, documented precedence:

      1. sensor vs ai        -> interim decision
      2. blockchain vs sensor -> may override the interim decision, but only
         when a sensor event exists to compare against (per the PRD's rule,
         which is phrased specifically as "blockchain conflicts with
         sensor"). If blockchain conflicts with sensor and is newer, it
         wins outright; if it conflicts but is stale, the interim decision
         from step 1 stands unchanged.

    Returns (final_status, source_of_truth, reason, conflicts_resolved: dict).
    """
    conflicts_resolved = {}

    if sensor_event and ai_event:
        interim_status, interim_source, interim_reason = resolve_sensor_vs_ai(sensor_event, ai_event)
        if extract_status(sensor_event) != extract_status(ai_event):
            conflicts_resolved["sensor_vs_ai"] = f"used_{interim_source}"
    elif sensor_event:
        interim_status, interim_source, interim_reason = (
            extract_status(sensor_event),
            "sensor",
            "sensor_only_source",
        )
    elif ai_event:
        interim_status, interim_source, interim_reason = (
            extract_status(ai_event),
            "ai",
            "ai_only_source",
        )
    else:
        interim_status, interim_source, interim_reason = "safe", "none", "no_sensor_or_ai_data"

    final_status, final_source, final_reason = interim_status, interim_source, interim_reason

    if blockchain_event and sensor_event:
        bc_status, bc_source, bc_reason = resolve_blockchain_vs_sensor(blockchain_event, sensor_event)
        if extract_status(blockchain_event) != extract_status(sensor_event):
            conflicts_resolved["blockchain_vs_sensor"] = f"used_{bc_source}"
            if bc_source == "blockchain":
                # Blockchain is newer than sensor and disagrees - it overrides
                # the interim decision outright.
                final_status, final_source, final_reason = bc_status, bc_source, bc_reason
            else:
                # Blockchain was stale - the interim decision (which may
                # already have favored AI over sensor) stands, but the
                # reason is annotated so the audit trail doesn't silently
                # hide that a blockchain conflict was considered and
                # rejected.
                final_reason = f"{interim_reason}_blockchain_conflict_ignored_stale"
    elif blockchain_event and not sensor_event:
        final_status, final_source, final_reason = (
            extract_status(blockchain_event),
            "blockchain",
            "blockchain_only_source",
        )

    return final_status, final_source, final_reason, conflicts_resolved
