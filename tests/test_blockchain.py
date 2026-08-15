"""Tests for the mock blockchain hash-chained ledger (bonus scope)."""
from datetime import datetime, timedelta, timezone

from app import db
from app.engine.blockchain import get_chain, submit_compliance_block, verify_chain

VEH = "veh_chain"
T0 = datetime(2026, 8, 15, 8, 0, 0, tzinfo=timezone.utc)


def test_first_submission_creates_genesis_block(mongo_db):
    block, state, audit, is_new = submit_compliance_block(
        VEH, T0, {"check_type": "emissions", "compliance_status": "pass"}
    )
    assert is_new is True
    assert block["block_index"] == 0
    assert block["prev_hash"] == "GENESIS"
    assert state["safety_state"] == "safe"


def test_chain_grows_and_links_correctly(mongo_db):
    submit_compliance_block(VEH, T0, {"check_type": "emissions", "compliance_status": "pass"})
    t1 = T0 + timedelta(minutes=1)
    block2, _, _, is_new = submit_compliance_block(
        VEH, t1, {"check_type": "safety_inspection", "compliance_status": "fail"}
    )

    chain = get_chain(VEH)
    assert len(chain) == 2
    assert is_new is True
    assert block2["block_index"] == 1
    assert block2["prev_hash"] == chain[0]["hash"]


def test_duplicate_submission_does_not_append_a_block(mongo_db):
    data = {"check_type": "emissions", "compliance_status": "pass"}
    submit_compliance_block(VEH, T0, data)
    block, _, _, is_new = submit_compliance_block(VEH, T0, data)  # exact repost

    assert is_new is False
    assert block is None
    assert len(get_chain(VEH)) == 1


def test_verify_chain_valid_on_untampered_chain(mongo_db):
    submit_compliance_block(VEH, T0, {"check_type": "emissions", "compliance_status": "pass"})
    submit_compliance_block(
        VEH, T0 + timedelta(minutes=1), {"check_type": "safety_inspection", "compliance_status": "pass"}
    )
    result = verify_chain(VEH)
    assert result == {"valid": True, "blocks_checked": 2, "first_invalid_index": None}


def test_verify_chain_detects_tampering(mongo_db):
    submit_compliance_block(VEH, T0, {"check_type": "emissions", "compliance_status": "pass"})
    submit_compliance_block(
        VEH, T0 + timedelta(minutes=1), {"check_type": "safety_inspection", "compliance_status": "pass"}
    )

    # Simulate tampering: directly mutate a stored block's data without
    # recomputing its hash (exactly what an attacker editing the DB would do).
    db.mock_blockchain_col().update_one(
        {"vehicle_id": VEH, "block_index": 0},
        {"$set": {"data.compliance_status": "fail"}},
    )

    result = verify_chain(VEH)
    assert result["valid"] is False
    assert result["first_invalid_index"] == 0


def test_verify_empty_chain_is_trivially_valid(mongo_db):
    result = verify_chain("no_such_vehicle")
    assert result == {"valid": True, "blocks_checked": 0, "first_invalid_index": None}


def test_submission_feeds_the_normal_reconciliation_pipeline(mongo_db):
    """A blockchain submission should be indistinguishable, from the
    reconciliation engine's point of view, from POST /events with
    source='blockchain' - same audit trail, same vehicle_states writes."""
    _, state, audit, _ = submit_compliance_block(
        VEH, T0, {"check_type": "safety_inspection", "compliance_status": "fail"}
    )
    assert state["safety_state"] == "alert"  # compliance_status=fail -> alert
    assert audit["final_state"] == "alert"
    assert db.events_col().count_documents({"vehicle_id": VEH, "source": "blockchain"}) == 1
