"""The trail catalogue: loads trails.json and shapes each trail for the API."""
from __future__ import annotations

import json
from pathlib import Path

DATA_FILE = Path(__file__).with_name("trails.json")


def load_trails() -> list[dict]:
    """Every trail as stored, in file order."""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def trail_view(trail: dict) -> dict:
    """One trail as GET /api/trails returns it. This dict is the contract the frontend reads."""
    return {
        "id": trail["id"],
        "name": trail["name"],
        "length_km": trail["length_km"],
        "climb_m": trail["climb_m"],
    }


def list_trails() -> list[dict]:
    return [trail_view(t) for t in load_trails()]
