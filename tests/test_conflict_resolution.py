"""Unit tests for the pure conflict-resolution rules (no DB required)."""
from datetime import datetime, timezone

from app.engine.conflict import (
    determine_safety_state,
    extract_confidence,
    extract_status,
    resolve_blockchain_vs_sensor,
    resolve_sensor_vs_ai,
)

T0 = datetime(2026, 8, 15, 7, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 15, 7, 1, 0, tzinfo=timezone.utc)


def sensor_event(confidence=0.9, status="safe", timestamp=T0):
    return {
        "event_id": "sensor1",
        "source": "sensor",
        "vehicle_id": "v1",
        "timestamp": timestamp,
        "data": {"position": {"x": 0, "y": 0}, "velocity": 10, "confidence": confidence, "status": status},
    }


def ai_event(confidence=0.9, alert="potential_collision", timestamp=T0):
    return {
        "event_id": "ai1",
        "source": "ai",
        "vehicle_id": "v1",
        "timestamp": timestamp,
        "data": {"alert": alert, "confidence": confidence},
    }


def blockchain_event(compliance_status="fail", timestamp=T0):
    return {
        "event_id": "bc1",
        "source": "blockchain",
        "vehicle_id": "v1",
        "timestamp": timestamp,
        "data": {"check_type": "emissions", "compliance_status": compliance_status},
    }


class TestExtractStatus:
    def test_explicit_status_wins(self):
        assert extract_status(sensor_event(status="danger")) == "danger"

    def test_sensor_default_is_safe(self):
        e = sensor_event()
        del e["data"]["status"]
        assert extract_status(e) == "safe"

    def test_ai_no_alert_is_safe(self):
        assert extract_status(ai_event(alert="none")) == "safe"

    def test_ai_high_confidence_alert_is_danger(self):
        assert extract_status(ai_event(alert="potential_collision", confidence=0.9)) == "danger"

    def test_ai_low_confidence_alert_is_alert(self):
        assert extract_status(ai_event(alert="potential_collision", confidence=0.3)) == "alert"

    def test_blockchain_pass_is_safe(self):
        assert extract_status(blockchain_event(compliance_status="pass")) == "safe"

    def test_blockchain_fail_is_alert(self):
        assert extract_status(blockchain_event(compliance_status="fail")) == "alert"


class TestExtractConfidence:
    def test_sensor_defaults_to_1(self):
        e = sensor_event()
        del e["data"]["confidence"]
        assert extract_confidence(e) == 1.0

    def test_ai_defaults_to_0_5(self):
        e = ai_event()
        del e["data"]["confidence"]
        assert extract_confidence(e) == 0.5


class TestResolveSensorVsAi:
    def test_agreement_uses_sensor(self):
        s = sensor_event(status="danger", confidence=0.4)
        a = ai_event(alert="potential_collision", confidence=0.9)  # ai status also danger
        status, source, reason = resolve_sensor_vs_ai(s, a)
        assert status == "danger"
        assert source == "sensor"
        assert "agree" in reason

    def test_sensor_wins_above_threshold(self):
        s = sensor_event(status="safe", confidence=0.95)
        a = ai_event(alert="potential_collision", confidence=0.99)
        status, source, reason = resolve_sensor_vs_ai(s, a)
        assert status == "safe"
        assert source == "sensor"

    def test_sensor_wins_at_exact_threshold_boundary(self):
        s = sensor_event(status="safe", confidence=0.8)
        a = ai_event(alert="potential_collision", confidence=0.99)
        status, source, _ = resolve_sensor_vs_ai(s, a)
        assert status == "safe"
        assert source == "sensor"

    def test_ai_wins_below_threshold(self):
        s = sensor_event(status="safe", confidence=0.79)
        a = ai_event(alert="potential_collision", confidence=0.9)
        status, source, reason = resolve_sensor_vs_ai(s, a)
        assert status == "danger"
        assert source == "ai"


class TestResolveBlockchainVsSensor:
    def test_agreement(self):
        bc = blockchain_event(compliance_status="pass", timestamp=T1)
        s = sensor_event(status="safe", timestamp=T0)
        status, source, reason = resolve_blockchain_vs_sensor(bc, s)
        assert status == "safe"
        assert "agree" in reason

    def test_blockchain_wins_when_newer(self):
        bc = blockchain_event(compliance_status="fail", timestamp=T1)  # newer
        s = sensor_event(status="safe", timestamp=T0)
        status, source, _ = resolve_blockchain_vs_sensor(bc, s)
        assert status == "alert"
        assert source == "blockchain"

    def test_sensor_wins_when_blockchain_stale(self):
        bc = blockchain_event(compliance_status="fail", timestamp=T0)  # older
        s = sensor_event(status="safe", timestamp=T1)
        status, source, _ = resolve_blockchain_vs_sensor(bc, s)
        assert status == "safe"
        assert source == "sensor"

    def test_sensor_wins_on_equal_timestamps(self):
        bc = blockchain_event(compliance_status="fail", timestamp=T0)
        s = sensor_event(status="safe", timestamp=T0)  # equal, not "newer"
        status, source, _ = resolve_blockchain_vs_sensor(bc, s)
        assert status == "safe"
        assert source == "sensor"


class TestDetermineSafetyState:
    def test_all_three_agree(self):
        s = sensor_event(status="safe")
        a = ai_event(alert="none")
        bc = blockchain_event(compliance_status="pass")
        status, source, reason, conflicts = determine_safety_state(s, a, bc)
        assert status == "safe"
        assert conflicts == {}

    def test_sensor_only(self):
        status, source, reason, conflicts = determine_safety_state(sensor_event(status="alert"), None, None)
        assert status == "alert"
        assert source == "sensor"
        assert conflicts == {}

    def test_no_events(self):
        status, source, reason, conflicts = determine_safety_state(None, None, None)
        assert status == "safe"
        assert source == "none"

    def test_blockchain_overrides_after_sensor_ai_resolution(self):
        s = sensor_event(status="safe", confidence=0.95, timestamp=T0)
        a = ai_event(alert="potential_collision", confidence=0.99, timestamp=T0)  # sensor wins interim -> safe
        bc = blockchain_event(compliance_status="fail", timestamp=T1)  # newer than sensor, conflicts
        status, source, reason, conflicts = determine_safety_state(s, a, bc)
        assert status == "alert"
        assert source == "blockchain"
        assert conflicts["sensor_vs_ai"] == "used_sensor"
        assert conflicts["blockchain_vs_sensor"] == "used_blockchain"
