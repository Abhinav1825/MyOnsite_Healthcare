"""Posts every fixture JSON file in this directory to a running instance of
the API, in order, so the reconciliation edge cases they encode actually
get exercised end-to-end.

Usage:
    python fixtures/load_fixtures.py [base_url]

Defaults to http://localhost:5000 if no base_url is given. Running this
script twice in a row is a good manual smoke test of idempotency/replay:
the second run should report every event as a duplicate and every
reconciliation as unchanged.
"""
import json
import sys
from pathlib import Path

import requests

FIXTURES_DIR = Path(__file__).parent


def strip_notes(payload):
    return {k: v for k, v in payload.items() if k != "_note"}


def load_fixture_files():
    return sorted(FIXTURES_DIR.glob("*.json"))


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"

    for path in load_fixture_files():
        events = json.loads(path.read_text())
        print(f"\n== {path.name} ({len(events)} events) ==")
        for raw_event in events:
            event = strip_notes(raw_event)
            resp = requests.post(f"{base_url}/events", json=event, timeout=10)
            body = resp.json()
            tag = "DUPLICATE" if body.get("duplicate") else "NEW"
            state = (body.get("vehicle_state") or {}).get("safety_state", "?")
            reason = (body.get("vehicle_state") or {}).get("decision_reason", "?")
            print(
                f"  [{resp.status_code}] {tag:9s} {event['source']:10s} "
                f"{event['vehicle_id']} @ {event['timestamp']} -> {state} ({reason})"
            )


if __name__ == "__main__":
    main()
