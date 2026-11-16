"""The trail catalogue: loads trails.json and shapes each trail for the API."""
from __future__ import annotations

import json
from pathlib import Path

DATA_FILE = Path(__file__).with_name("trails.json")

# Effort score = kilometres + metres of climb / 100. Below the first bound is easy, below the second
# is moderate, anything else is hard.
MODERATE_FROM = 8
HARD_FROM = 15


def load_trails() -> list[dict]:
    """Every trail as stored, in file order."""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def difficulty(length_km: float, climb_m: float) -> str:
    score = length_km + climb_m / 100
    if score < MODERATE_FROM:
        return "easy"
    if score < HARD_FROM:
        return "moderate"
    return "hard"


def trail_view(trail: dict) -> dict:
    """One trail as GET /api/trails returns it. This dict is the contract the frontend reads."""
    return {
        "id": trail["id"],
        "name": trail["name"],
        "length_km": trail["length_km"],
        "climb_m": trail["climb_m"],
        "difficulty": difficulty(trail["length_km"], trail["climb_m"]),
    }


def list_trails() -> list[dict]:
    return [trail_view(t) for t in load_trails()]
