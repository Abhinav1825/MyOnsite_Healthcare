"""Tests for multi-vehicle proximity alerts (bonus scope)."""
from datetime import datetime, timedelta, timezone

from app import db
from app.engine.ingestion import ingest_event
from app.engine.proximity import compute_proximity, estimate_velocity_vector
from app.engine.reconciler import reconcile

T0 = datetime(2026, 8, 15, 8, 0, 0, tzinfo=timezone.utc)


def post_sensor(vehicle_id, timestamp, x, y, velocity=10.0):
    ingest_event(
        {
            "source": "sensor",
            "vehicle_id": vehicle_id,
            "timestamp": timestamp.isoformat(),
            "data": {"position": {"x": x, "y": y}, "velocity": velocity, "confidence": 0.9, "status": "safe"},
        }
    )
    return reconcile(vehicle_id, timestamp)


class TestEstimateVelocityVector:
    def test_none_with_fewer_than_two_points(self, mongo_db):
        post_sensor("veh_v1", T0, 0, 0)
        assert estimate_velocity_vector("veh_v1", T0) is None

    def test_computed_from_last_two_points(self, mongo_db):
        post_sensor("veh_v1", T0, 0, 0)
        post_sensor("veh_v1", T0 + timedelta(seconds=5), 10, 0)
        vel = estimate_velocity_vector("veh_v1", T0 + timedelta(seconds=5))
        assert vel == {"x": 2.0, "y": 0.0}


class TestComputeProximity:
    def test_far_apart_no_alert(self, mongo_db):
        result = compute_proximity("a", {"x": 0, "y": 0}, T0, "b", {"x": 1000, "y": 0}, T0)
        assert result["severity"] is None

    def test_close_but_no_velocity_history_is_alert_not_danger(self, mongo_db):
        result = compute_proximity("a", {"x": 0, "y": 0}, T0, "b", {"x": 5, "y": 0}, T0)
        assert result["severity"] == "alert"  # can't compute closing_speed -> not escalated

    def test_close_and_closing_fast_is_danger(self, mongo_db):
        t1 = T0 + timedelta(seconds=5)
        post_sensor("veh_a", T0, 0, 0)
        post_sensor("veh_a", t1, 20, 0)  # moving toward b at 4 units/sec
        post_sensor("veh_b", T0, 100, 0)
        post_sensor("veh_b", t1, 26, 0)  # moving toward a fast

        result = compute_proximity("veh_a", {"x": 20, "y": 0}, t1, "veh_b", {"x": 26, "y": 0}, t1)
        assert result["distance"] == 6
        assert result["closing_speed"] > 0
        assert result["severity"] == "danger"

    def test_close_but_separating_is_alert_not_danger(self, mongo_db):
        t1 = T0 + timedelta(seconds=5)
        post_sensor("veh_a", T0, 0, 0)
        post_sensor("veh_a", t1, -3, 0)  # moving in -x, away from b
        post_sensor("veh_b", T0, 0, 0)
        post_sensor("veh_b", t1, 3, 0)  # moving in +x, away from a

        result = compute_proximity("veh_a", {"x": -3, "y": 0}, t1, "veh_b", {"x": 3, "y": 0}, t1)
        assert result["distance"] == 6  # within the 10.0 threshold
        assert result["closing_speed"] < 0  # negative = separating
        assert result["severity"] == "alert"  # within distance, but not escalated to danger


class TestCheckProximityIntegration:
    def test_converging_vehicles_produce_proximity_alert(self, mongo_db):
        t0, t1 = T0, T0 + timedelta(seconds=5)
        post_sensor("veh_006a", t0, 0, 0)
        post_sensor("veh_006b", t0, 100, 0)
        post_sensor("veh_006a", t1, 20, 0)
        post_sensor("veh_006b", t1, 26, 0)  # this reconciliation triggers the proximity check

        alerts = list(db.proximity_alerts_col().find({}))
        assert len(alerts) == 1
        alert = alerts[0]
        assert {alert["vehicle_a"], alert["vehicle_b"]} == {"veh_006a", "veh_006b"}
        assert alert["severity"] == "danger"

    def test_distant_vehicles_produce_no_alert(self, mongo_db):
        post_sensor("veh_x", T0, 0, 0)
        post_sensor("veh_y", T0, 5000, 0)
        assert db.proximity_alerts_col().count_documents({}) == 0

    def test_reconciling_same_pair_twice_does_not_duplicate_alert(self, mongo_db):
        t0, t1 = T0, T0 + timedelta(seconds=5)
        post_sensor("veh_006a", t0, 0, 0)
        post_sensor("veh_006b", t0, 100, 0)
        post_sensor("veh_006a", t1, 20, 0)
        post_sensor("veh_006b", t1, 26, 0)
        # re-reconcile the same timepoint again (idempotent no-op upstream,
        # but proximity check would still run if it were re-triggered)
        reconcile("veh_006b", t1)
        assert db.proximity_alerts_col().count_documents({}) == 1
