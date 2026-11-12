"""All 94 + 102 accepted row084 fixtures, independent of sibling protocols."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.profiles.comfy import (
    COMFYDS_COMMANDS,
    KOMFYD_COMMANDS,
    comfy_advertisement,
    signed32,
    wire_target,
)

VECTORS = {
    key: json.loads((Path(__file__).parent / f"fixtures/{key}_row084_vectors.json").read_text())
    for key in ("komfyd", "comfyds")
}
FROZEN_PAYLOADS = {
    key: frozenset(
        bytes.fromhex(row["expected_bytes"])[10:].hex()
        for row in rows
        if "opcode" in row["inputs"] and row["inputs"]["opcode"] != 69
    )
    for key, rows in VECTORS.items()
}


@pytest.mark.parametrize(
    ("app", "row"),
    [(app, row) for app, rows in VECTORS.items() for row in rows],
    ids=lambda r: r if isinstance(r, str) else r["id"],
)
def test_every_frozen_literal(app, row):
    args = row["inputs"]
    kind = args.get("builder", row.get("kind"))
    expected = bytes.fromhex(row["expected_bytes"])
    if "opcode" in args:
        target = signed32(args.get("target", args.get("destination")))
        actual = codec.control(wire_target(target), args["own"], args["opcode"])
    elif kind in ("auth", "authenticate", "membership", "enroll", "ping"):
        builder = {
            "auth": codec.join,
            "authenticate": codec.join,
            "membership": codec.enroll,
            "enroll": codec.enroll,
            "ping": codec.ping,
        }[kind]
        actual = builder(args["own"] if kind == "ping" else args["room"])
    elif kind == "advertisement":
        ad = comfy_advertisement({0xFFFF: expected})
        assert ad is not None
        state = row["expected_state"]
        assert (ad.product_id, ad.sofa_type, ad.room_id or 0, ad.vaddr or 0, ad.sofa_acu_no) == (
            state["product"],
            state["type"],
            state["room"],
            state["virtual"],
            state["capability_word"],
        )
        return
    else:
        parsed = codec.parse_notification(expected)
        assert parsed is not None
        state = row["expected_state"]
        if state["kind"] == "online":
            assert isinstance(parsed, codec.PingReply)
            assert (parsed.node, parsed.signed_vaddr or -2) == (state["mac"], state["virtual"])
        elif state["kind"] == "memory_reply":
            assert isinstance(parsed, codec.ControlReply) and 37 <= parsed.command <= 60
        else:
            assert isinstance(parsed, codec.ControlReply)
            assert (parsed.command, parsed.value) == (70, state["lock"])
        return
    assert actual == expected


@pytest.mark.parametrize(
    ("key", "commands"), [("komfyd", KOMFYD_COMMANDS), ("comfyds", COMFYDS_COMMANDS)]
)
def test_complete_command_census(key, commands):
    opcodes = {op for codes in commands.values() for op in codes}
    assert len(opcodes) == 90
    assert 69 not in opcodes
    assert FROZEN_PAYLOADS[key] == {codec.payload(op).hex() for op in opcodes}
    assert len(VECTORS[key]) == {"komfyd": 94, "comfyds": 102}[key]
