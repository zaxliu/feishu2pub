"""Local state shared by both targets: .env location, out/ dir and state.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state.json"
OUT = ROOT / "out"


def load_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.is_file() else {"docs": {}, "images": {}}


def save_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(STATE)
