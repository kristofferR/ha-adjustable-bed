"""Unchanged Tempur Relax Control 6.1.3 frozen literals, not hardware captures."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.linak.protocol import (
    LINAK_ALARM_ACTIONS_BY_OPCODE,
    LinakAlarmStep,
    build_timer_event,
    build_timer_recurrence,
)
from custom_components.adjustable_bed.codec.linak import (
    configuration_frame,
    control_frame,
    massage_selection_frames,
    selected_directions_frame,
)

ROOT = Path(__file__).parent / "fixtures/tempur_relax"
ORIGINAL = json.loads((ROOT / "test-vectors.json").read_text())
REPAIR = json.loads((ROOT / "repair-test-vectors.json").read_text())
LITERALS = json.loads((ROOT / "lin-code-literals.json").read_text())


@pytest.mark.parametrize("vector", ORIGINAL + REPAIR, ids=lambda v: v["id"])
def test_frozen_frames(vector):
    args = vector["inputs"]
    match vector["builder"]:
        case "lin":
            frames = (
                control_frame(
                    LITERALS[args["code"]],
                    side=args.get("side", 0),
                    modifier=args.get("modifier", False),
                ),
            )
        case "config":
            frames = (
                configuration_frame(
                    args["code"],
                    bytes.fromhex(args.get("data", "")),
                    write=args.get("write", False),
                    prefix=args.get("prefix", 127),
                ),
            )
        case "timer":
            steps = tuple(
                LinakAlarmStep(LINAK_ALARM_ACTIONS_BY_OPCODE[op], life, pause)
                for op, life, pause in args["actions"]
            )
            frames = (build_timer_event(args["seconds"], steps),)
        case "recurrence":
            frames = (build_timer_recurrence(args["count"], args["minutes"]),)
        case "selector":
            frames = (
                selected_directions_frame(
                    {
                        axis.lower(): direction == "UP"
                        for axis, direction in args["directions"].items()
                    },
                    modifier=args["modifier"],
                ),
            )
        case "massage_sequence":
            frames = massage_selection_frames(
                frozenset(axis.lower() for axis in args["sections"]), enabled=args["enabled"]
            )
        case _:
            pytest.fail(vector["builder"])
    assert " | ".join(frame.hex(" ") for frame in frames) == vector["expected_bytes"]
