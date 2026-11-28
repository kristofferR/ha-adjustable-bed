"""AR Connect's frozen native subset, with no BLE session or hardware assumptions."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec.linak import (
    control_frame,
    custom_speed_frame,
    parse_native_reference,
)
from custom_components.adjustable_bed.profiles.ar_connect import AR_CONNECT

VECTORS = json.loads((Path(__file__).parent / "fixtures/ar_connect_vectors.json").read_text())


@pytest.mark.parametrize("vector", VECTORS["transmit"], ids=lambda v: v["id"])
def test_frozen_transmit_literals(vector):
    inputs = vector["inputs"]
    if vector["action"] == "moveBed":
        frame = AR_CONNECT.movement(
            {axis: value == 0 for axis, value in inputs["motorsDirectionsMap"].items()},
            slow=inputs["slowMode"],
        )
    elif vector["action"].startswith("setCustomSpeed:"):
        frame = dict(AR_CONNECT.custom_speed(inputs["speedUp"], inputs["accelerationUp"]))[
            inputs["axis"].lower()
        ]
    else:
        opcode = {
            "WAKE_UP": AR_CONNECT.stop_bed_opcode,
            "AUX_1_TOGGLE": AR_CONNECT.light_toggle_opcode,
            "MEMORY_5": AR_CONNECT.recall_opcodes[4],
            "STORE_MEM_5": AR_CONNECT.save_opcodes[4],
        }[vector["action"]]
        frame = control_frame(opcode, slow=inputs["slowMode"])
    assert frame == bytes.fromhex(vector["expected_bytes"])


@pytest.mark.parametrize("row", VECTORS["movement"], ids=lambda row: row["name"])
def test_every_native_movement_input_map(row):
    for inputs in row["input_maps"]:
        directions = {axis: value == 0 for axis, value in inputs.items()}
        for slow, suffix in ((False, 0), (True, 0x40)):
            assert AR_CONNECT.movement(directions, slow=slow) == bytes((row["code"], suffix))


def test_native_configuration_order_and_head_skip():
    assert [axis for axis, _ in AR_CONNECT.custom_speed(100, 50)] == [
        "back",
        "legs",
        "feet",
        "base",
    ]
    assert AR_CONNECT.custom_speed_post_write_ms == 100


@pytest.mark.parametrize("vector", VECTORS["memory"])
def test_native_memory_index_literals(vector):
    opcodes = AR_CONNECT.save_opcodes if vector["store"] else AR_CONNECT.recall_opcodes
    expected = bytes.fromhex(vector["expected"])
    assert control_frame(opcodes[vector["index"]]) == expected
    if not vector["store"]:
        assert control_frame(opcodes[vector["index"]], slow=True) == expected[:1] + b"\x40"


def test_native_gatt_identity():
    for key, expected in VECTORS["transport"].items():
        assert getattr(AR_CONNECT, key) == expected
    assert dict(AR_CONNECT.references) == VECTORS["references"]


@pytest.mark.parametrize(
    "value,word",
    [(float("nan"), "0000"), (float("inf"), "ffff"), (-float("inf"), "0000"), (1e40, "ffff")],
)
def test_native_float_to_int_saturation(value, word):
    # These are conversion checks, never accepted hardware setting ranges.
    assert custom_speed_frame(0xDF, value, 0).hex() == "00df80" + word * 2 + "000000000000"


@pytest.mark.parametrize("vector", VECTORS["reference"], ids=lambda v: v["id"])
def test_native_reference_formula_checks(vector):
    state = parse_native_reference(bytes.fromhex(vector["data"]))
    assert {key: getattr(state, key) for key in vector["expected"]} == vector["expected"]


@pytest.mark.parametrize("data", [b"\x01", b"\x01\x02", b"\x01\x02\x03", b"\x00" * 5])
def test_invalid_reference_length_clears_native_state(data):
    assert parse_native_reference(data) == parse_native_reference(b"")
