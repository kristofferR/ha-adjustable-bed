"""Base Remote 1.0.1 frozen resource literals, not hardware captures."""

import gzip
import json
from pathlib import Path

from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.protocol import control
from custom_components.adjustable_bed.codec import richmat as codec


def test_all_frozen_base_remote_commands_fit_existing_codec_and_getters():
    rows = json.loads(
        gzip.decompress(
            (Path(__file__).parent / "fixtures/baseremote/commands.json.gz").read_bytes()
        )
    )
    assert len(rows) == 19142
    models = load_catalog("baseremote").models
    checked = 0
    for protocol, layout, node, event, operand, expected, runtime, dynamic in rows:
        button = next(c for c in models[layout].controls if c.node == node)
        wire = "RAW" if protocol == "P1" else "FRAMED"
        if dynamic:
            continue  # Both branches are exercised separately below.
        if operand is None:
            continue
        value = selected_operand(
            button, wire, 3 if "long" in event else 1 if button.status == 1 else 2, Selection()
        )
        if runtime:
            # These frozen rows change the worker state, not the loaded getter.
            value = bytes.fromhex(operand)
        assert value == bytes.fromhex(operand), (protocol, layout, node, event)
        assert control(value, wire).hex() == expected.lower(), (protocol, layout, node, event)
        checked += 1
    assert checked > 19000


def test_base_remote_direct_literals_and_new_group_encoder():
    assert codec.command(0x24) == bytes.fromhex("6e01002493")
    assert codec.encode("nordic", 0x34) == b"4"
    assert codec.rgb(0x98, 0xCB, 0) == bytes.fromhex("6e0cff98116e0dcb0046")
    assert b"".join(codec.countdown(1440, 0x2E)) == bytes.fromhex("6e05a000136e06052ea7")
    assert codec.rgb(0x12, 0x34, 0x56) == bytes.fromhex("6e0cff128b6e0d345605")
    assert codec.countdown(300, 0x81) == (bytes.fromhex("6e052c009f"), bytes.fromhex("6e060181f6"))
    assert codec.local_group(None) == bytes.fromhex("41542b524542494e440d0a")
    assert codec.local_group("1234") == b"AT+GROUP1234\r\n"


def test_every_frozen_dynamic_operand_keeps_its_real_null_and_selector_branches():
    rows = json.loads(
        gzip.decompress(
            (Path(__file__).parent / "fixtures/baseremote/commands.json.gz").read_bytes()
        )
    )
    models = load_catalog("baseremote").models
    checked = 0
    for protocol, layout, node, _event, _operand, _expected, _runtime, dynamic in rows:
        if not dynamic:
            continue
        button = next(c for c in models[layout].controls if c.node == node)
        wire = "RAW" if protocol == "P1" else "FRAMED"
        for condition, value in dynamic.items():
            if condition == "null_reason":
                continue
            selection = (
                Selection(head=condition == "tagBool_true")
                if condition.startswith("tagBool")
                else Selection(
                    press_flag=condition.removeprefix("pressFlag")
                    if condition.startswith("pressFlag")
                    else "unknown"
                )
            )
            actual = selected_operand(button, wire, 1, selection)
            assert actual == (bytes.fromhex(value) if value else None), (
                layout,
                node,
                wire,
                condition,
            )
            checked += 1
    assert checked == 36
