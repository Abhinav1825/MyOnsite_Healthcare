"""Exports the current audit trail and vehicle state history from a running
instance of the API into static JSON files under `audit_output/`.

This produces the literal "audit/decision-trace output files" deliverable
the PRD calls for, as a snapshot you can commit and hand to a reviewer
without them needing to run the system themselves to see the results.

Usage:
    python fixtures/load_fixtures.py            # populate the DB first
    python fixtures/export_audit_output.py       # then export it

    python fixtures/export_audit_output.py [base_url] [output_dir]
"""
import json
import sys
from pathlib import Path

import requests

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "audit_output"


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)

    vehicles = requests.get(f"{base_url}/vehicles", timeout=10).json()
    (output_dir / "current_vehicle_states.json").write_text(json.dumps(vehicles, indent=2))
    print(f"Wrote {len(vehicles)} current vehicle states -> {output_dir / 'current_vehicle_states.json'}")

    all_audit = requests.get(f"{base_url}/audit", timeout=10).json()
    (output_dir / "audit_trail_full.json").write_text(json.dumps(all_audit, indent=2))
    print(f"Wrote {len(all_audit)} audit trail entries -> {output_dir / 'audit_trail_full.json'}")

    proximity = requests.get(f"{base_url}/proximity", timeout=10).json()
    (output_dir / "proximity_alerts.json").write_text(json.dumps(proximity, indent=2))
    print(f"Wrote {len(proximity)} proximity alerts -> {output_dir / 'proximity_alerts.json'}")

    vehicle_ids = sorted({v["vehicle_id"] for v in vehicles})
    blockchain_ledgers = {}
    for vehicle_id in vehicle_ids:
        chain_resp = requests.get(f"{base_url}/blockchain/{vehicle_id}", timeout=10)
        if chain_resp.status_code == 200:
            verify_resp = requests.get(f"{base_url}/blockchain/{vehicle_id}/verify", timeout=10).json()
            blockchain_ledgers[vehicle_id] = {"chain": chain_resp.json(), "verify": verify_resp}
    if blockchain_ledgers:
        (output_dir / "blockchain_ledgers.json").write_text(json.dumps(blockchain_ledgers, indent=2))
        print(f"Wrote {len(blockchain_ledgers)} blockchain ledger(s) -> {output_dir / 'blockchain_ledgers.json'}")

    for vehicle_id in vehicle_ids:
        history = requests.get(f"{base_url}/vehicles/{vehicle_id}", timeout=10).json()
        audit = requests.get(f"{base_url}/audit/{vehicle_id}", timeout=10).json()
        payload = {"vehicle_id": vehicle_id, "state_history": history, "audit_trail": audit}
        path = output_dir / f"{vehicle_id}.json"
        path.write_text(json.dumps(payload, indent=2))
        print(f"Wrote per-vehicle decision trace -> {path}")


if __name__ == "__main__":
    main()
