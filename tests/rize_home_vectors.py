"""Unit163's original literals, retained independently of the production profile."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent / "fixtures/rize_home"
VECTORS = json.loads((ROOT / "command_vectors.json").read_text())
FRAMES = frozenset(row["expected_bytes"].replace(" ", "") for row in VECTORS)
FROZEN_FRAMES = {"rize_home_remedy_iii": FRAMES, "rize_home_contempo_iv": FRAMES}
# Each frozen app method maps to the user-facing action, not its ordinal or icon.
ACTIONS = {
    "motionSensorOff": "motion_off",
    "motionSensorOn": "motion_on",
    "underbedLighting": "light",
    "massageHeadAndFootMinus": "massage_down",
    "massageHeadAndFoot": "massage_up",
    "massageFootMinus": "massage_foot_down",
    "massageFoot": "massage_foot_up",
    "massageHeadMinus": "massage_head_down",
    "massageHead": "massage_head_up",
    "massageOff": "massage_off",
    "massageOn": "massage_on",
    "reading": "reading",
    "m5": "memory",
    "flat": "flat",
    "antiSnore": "anti_snore",
    "zeroGravity": "zero_g",
    "leisure": "leisure",
    "stopCommand": "stop",
    "elevateDown": "elevate_down",
    "elevateUp": "elevate_up",
    "lumbarDown": "lumbar_down",
    "lumbarUp": "lumbar_up",
    "footDown": "foot_down",
    "footUp": "foot_up",
    "headDown": "head_down",
    "headUp": "head_up",
    "headTiltDown": "head_tilt_down",
    "headTiltUp": "head_tilt_up",
    "confirmationResponse": "query",
    "massageOpen": "massage_toggle",
    "massageMode": "massage_mode",
    "massageTimer": "massage_timer",
    "flatAndZg": "reset_memories",
}
