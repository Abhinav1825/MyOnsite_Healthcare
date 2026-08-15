"""Mock blockchain API (bonus scope): a real hash-chained ledger, not just
another way to post a `source=blockchain` event.

Each vehicle has its own chain of blocks. Every block's hash covers its own
content AND the previous block's hash (`prev_hash`), so altering any
historical block's data breaks the hash chain from that point forward -
the actual property that makes a blockchain useful for compliance logs
(tamper-evidence), which `verify_chain` can prove on demand.

Submitting a block also feeds the SAME reconciliation pipeline used by
`POST /events` (source="blockchain") - this is a ledger layered on top of
the existing event/reconciliation system, not a fork of it. Chain-level
replay protection follows directly from the event-level idempotency
already built: if ingestion reports a duplicate, no new block is appended.
"""
from datetime import datetime, timezone

from app import db
from app.engine.ingestion import ingest_event
from app.engine.reconciler import reconcile
from app.hashing import canonical_json, sha256_hex

GENESIS_HASH = "GENESIS"


def _latest_block(vehicle_id):
    return db.mock_blockchain_col().find_one(
        {"vehicle_id": vehicle_id}, sort=[("block_index", -1)]
    )


def compute_block_hash(vehicle_id, block_index, timestamp, data, prev_hash):
    return sha256_hex(vehicle_id, block_index, timestamp.isoformat(), canonical_json(data), prev_hash)


def submit_compliance_block(vehicle_id, timestamp, data):
    """Submit a compliance payload to the mock chain for `vehicle_id`.

    Returns (block_doc_or_None, state_doc, audit_doc, is_new_block: bool).
    block_doc is None only if this exact submission was a duplicate (chain
    unchanged) - the reconciliation result is still returned since it's
    still a valid idempotent no-op read of the current state.
    """
    normalized, is_duplicate = ingest_event(
        {
            "source": "blockchain",
            "vehicle_id": vehicle_id,
            "timestamp": timestamp.isoformat(),
            "data": data,
        }
    )
    state_doc, audit_doc, _ = reconcile(vehicle_id, normalized["timestamp"])

    if is_duplicate:
        return None, state_doc, audit_doc, False

    prev = _latest_block(vehicle_id)
    prev_hash = prev["hash"] if prev else GENESIS_HASH
    block_index = (prev["block_index"] + 1) if prev else 0

    block_hash = compute_block_hash(vehicle_id, block_index, normalized["timestamp"], data, prev_hash)
    block_doc = {
        "vehicle_id": vehicle_id,
        "block_index": block_index,
        "timestamp": normalized["timestamp"],
        "data": data,
        "prev_hash": prev_hash,
        "hash": block_hash,
        "created_at": datetime.now(timezone.utc),
    }
    db.mock_blockchain_col().insert_one(dict(block_doc))

    return block_doc, state_doc, audit_doc, True


def get_chain(vehicle_id):
    return list(
        db.mock_blockchain_col().find({"vehicle_id": vehicle_id}).sort("block_index", 1)
    )


def verify_chain(vehicle_id):
    """Recompute every block's hash and confirm the prev_hash linkage is
    unbroken. Returns {valid, blocks_checked, first_invalid_index}."""
    blocks = get_chain(vehicle_id)
    expected_prev_hash = GENESIS_HASH

    for block in blocks:
        recomputed = compute_block_hash(
            block["vehicle_id"], block["block_index"], block["timestamp"], block["data"], block["prev_hash"]
        )
        if block["prev_hash"] != expected_prev_hash or recomputed != block["hash"]:
            return {"valid": False, "blocks_checked": len(blocks), "first_invalid_index": block["block_index"]}
        expected_prev_hash = block["hash"]

    return {"valid": True, "blocks_checked": len(blocks), "first_invalid_index": None}
