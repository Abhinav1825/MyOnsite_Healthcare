"""End-to-end tests via the Flask test client, including one test per
required fixture dataset (late events, conflicting sensor data, sensor vs
AI conflicts, blockchain vs sensor conflicts, duplicate replay)."""
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(name):
    events = json.loads((FIXTURES_DIR / name).read_text())
    return [{k: v for k, v in e.items() if k != "_note"} for e in events]


def post_all(client, events):
    responses = []
    for event in events:
        responses.append(client.post("/events", json=event))
    return responses


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_post_event_and_read_back(client):
    resp = client.post(
        "/events",
        json={
            "source": "sensor",
            "vehicle_id": "veh_api",
            "timestamp": "2026-08-15T07:00:00Z",
            "data": {"position": {"x": 0, "y": 0}, "velocity": 1, "confidence": 0.9, "status": "safe"},
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["vehicle_state"]["safety_state"] == "safe"

    vehicles = client.get("/vehicles").get_json()
    assert any(v["vehicle_id"] == "veh_api" for v in vehicles)

    detail = client.get("/vehicles/veh_api").get_json()
    assert len(detail) == 1

    audit = client.get("/audit/veh_api").get_json()
    assert len(audit) == 1


def test_malformed_event_returns_400(client):
    resp = client.post("/events", json={"source": "sensor"})  # missing fields
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_unknown_vehicle_returns_404(client):
    assert client.get("/vehicles/does_not_exist").status_code == 404
    assert client.get("/audit/does_not_exist").status_code == 404


class TestFixtureEdgeCases:
    def test_01_late_event(self, client):
        events = load_fixture("01_late_event.json")
        responses = post_all(client, events)
        assert all(r.status_code == 201 for r in responses)

        detail = client.get("/vehicles/veh_001").get_json()
        # 4 distinct timepoints: 07:00, 07:02 (late), 07:03:30 (ai/interp), 07:05
        timestamps = {d["timestamp"] for d in detail}
        assert len(timestamps) == 4

    def test_02_conflicting_sensor_updates(self, client):
        events = load_fixture("02_conflicting_sensor_updates.json")
        post_all(client, events)

        audit = client.get("/audit/veh_002").get_json()
        assert any(
            entry["conflicts_resolved"].get("sensor_vs_sensor") == "resolved_by_highest_confidence"
            for entry in audit
        )

    def test_03_sensor_vs_ai_conflict(self, client):
        events = load_fixture("03_sensor_vs_ai_conflict.json")
        post_all(client, events)

        detail = {d["timestamp"]: d for d in client.get("/vehicles/veh_003").get_json()}
        assert detail["2026-08-15T07:00:00+00:00"]["safety_state"] == "safe"  # sensor won
        assert detail["2026-08-15T07:10:00+00:00"]["safety_state"] == "danger"  # ai won

    def test_04_blockchain_vs_sensor_conflict(self, client):
        events = load_fixture("04_blockchain_vs_sensor_conflict.json")
        post_all(client, events)

        detail = {d["timestamp"]: d for d in client.get("/vehicles/veh_004").get_json()}
        assert detail["2026-08-15T07:01:00+00:00"]["safety_state"] == "alert"  # blockchain won (newer)
        assert detail["2026-08-15T07:10:00+00:00"]["safety_state"] == "safe"  # sensor won (blockchain stale)

    def test_05_duplicate_replay(self, client):
        events = load_fixture("05_duplicate_replay.json")
        responses = post_all(client, events)

        assert responses[0].status_code == 201
        assert responses[0].get_json()["duplicate"] is False
        assert responses[1].status_code == 200
        assert responses[1].get_json()["duplicate"] is True

        detail = client.get("/vehicles/veh_005").get_json()
        assert len(detail) == 1  # only one state version, no duplicate

        audit = client.get("/audit/veh_005").get_json()
        assert len(audit) == 1  # only one audit entry

    def test_06_multi_vehicle_proximity(self, client):
        events = load_fixture("06_multi_vehicle_proximity.json")
        responses = post_all(client, events)
        assert all(r.status_code == 201 for r in responses)

        alerts = client.get("/proximity").get_json()
        assert len(alerts) == 1
        assert {alerts[0]["vehicle_a"], alerts[0]["vehicle_b"]} == {"veh_006a", "veh_006b"}
        assert alerts[0]["severity"] == "danger"

        scoped = client.get("/proximity?vehicle_id=veh_006a").get_json()
        assert len(scoped) == 1


class TestProximityAndTrajectoriesRoutes:
    def test_proximity_empty_by_default(self, client):
        assert client.get("/proximity").get_json() == []

    def test_trajectories_endpoint(self, client):
        client.post(
            "/events",
            json={
                "source": "sensor",
                "vehicle_id": "veh_traj",
                "timestamp": "2026-08-15T07:00:00Z",
                "data": {"position": {"x": 1, "y": 2}, "velocity": 5, "confidence": 0.9},
            },
        )
        trajectories = client.get("/vehicles/trajectories").get_json()
        assert "veh_traj" in trajectories
        assert len(trajectories["veh_traj"]) == 1
        assert trajectories["veh_traj"][0]["position"] == {"x": 1, "y": 2}


class TestBlockchainRoutes:
    def test_submit_creates_genesis_block(self, client):
        resp = client.post(
            "/blockchain/submit",
            json={
                "vehicle_id": "veh_bc_api",
                "timestamp": "2026-08-15T07:00:00Z",
                "data": {"check_type": "emissions", "compliance_status": "pass"},
            },
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["new_block"] is True
        assert body["block"]["block_index"] == 0
        assert body["block"]["prev_hash"] == "GENESIS"

    def test_get_chain_and_verify(self, client):
        client.post(
            "/blockchain/submit",
            json={
                "vehicle_id": "veh_bc_api2",
                "timestamp": "2026-08-15T07:00:00Z",
                "data": {"check_type": "emissions", "compliance_status": "pass"},
            },
        )
        chain = client.get("/blockchain/veh_bc_api2").get_json()
        assert len(chain) == 1

        verify = client.get("/blockchain/veh_bc_api2/verify").get_json()
        assert verify["valid"] is True

    def test_duplicate_submission_returns_200_no_new_block(self, client):
        payload = {
            "vehicle_id": "veh_bc_dup",
            "timestamp": "2026-08-15T07:00:00Z",
            "data": {"check_type": "emissions", "compliance_status": "pass"},
        }
        first = client.post("/blockchain/submit", json=payload)
        second = client.post("/blockchain/submit", json=payload)
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.get_json()["new_block"] is False
        assert len(client.get("/blockchain/veh_bc_dup").get_json()) == 1

    def test_missing_chain_returns_404(self, client):
        assert client.get("/blockchain/no_such_vehicle").status_code == 404

    def test_malformed_submission_returns_400(self, client):
        resp = client.post("/blockchain/submit", json={"vehicle_id": "x"})  # missing data/timestamp
        assert resp.status_code == 400


def test_replay_endpoint_reports_consistency(client):
    events = load_fixture("03_sensor_vs_ai_conflict.json")
    post_all(client, events)

    resp = client.post("/replay")
    assert resp.status_code == 200
    assert resp.get_json()["consistent"] is True
