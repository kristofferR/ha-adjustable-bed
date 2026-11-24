"""The accepted Maxprime 1.0.7 command literals, including layout-dependent getters."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.maxprime_commands import gesture
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.receive import (
    MalformedFrame,
    ReceiveState,
)
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.profiles import maxprime

VECTORS = Path(__file__).with_name("fixtures") / "maxprime" / "commands.json.gz"


def test_catalog_reproduces_all_bed_command_rows_at_each_layout_mode():
    models = load_catalog(maxprime.APP).models
    assert set(models) == set(maxprime.LAYOUTS)
    packets = defaultdict(set)
    for layout, model in models.items():
        for wire in ("RAW", "FRAMED"):
            for hold in (False, True):
                for flag in ("53", "54", "55") if layout == "U3RM" else ("53",):
                    sel = replace(Selection(hold=hold), press_flag=flag)
                    for c in model.controls:
                        for long in (False, True):
                            g = gesture(c, layout, wire, sel, long=long)
                            if g is None:
                                continue
                            modes = model.modes if wire == "FRAMED" else (0,)
                            for mode in modes:
                                packets[wire, layout, mode].add(
                                    p.control(g.payload, wire, mode).hex()
                                )

    rows = json.loads(gzip.decompress(VECTORS.read_bytes()))
    assert len(rows) == 441
    expected_packets = defaultdict(set)
    for protocol, _action, _mode, _gesture, _raw, expected, variants in rows:
        wire = "RAW" if protocol == "P1" else "FRAMED"
        for layout in variants:
            for mode in models[layout].modes if wire == "FRAMED" else (0,):
                packet = expected[str(mode)]
                expected_packets[wire, layout, mode].add(packet)
    assert dict(packets) == dict(expected_packets)


def test_explicit_settings_and_full_resource_frames_use_the_existing_codec():
    assert p.control(bytes.fromhex("476e01"), "RAW").hex() == "476e01"
    assert p.control(bytes.fromhex("476e01"), "FRAMED", 1).hex() == "6e010147b7"
    assert p.control(b"\x24", "FRAMED", 2).hex() == "6e01022495"
    assert p.release("FRAMED").hex() == "6e01006edd"
    assert p.INITIALIZE.hex() == "6e02010071"
    assert p.ALARM_QUERY.hex() == "6e08010178"
    assert p.LAMP_QUERY.hex() == "6e0a000179"
    assert p.AROMA_QUERY.hex() == "6e1a000088"
    assert b"".join(p.alarm(1440, 70)).hex() == "6e05a000136e060546bf"
    assert b"".join(p.alarm(0, 0)).hex() == "6e050000736e06000074"
    assert richmat.rgb(18, 52, 86).hex() == "6e0cff128b6e0d345605"
    assert richmat.light_timer(1, 44).hex() == "6e0b012ca6"
    assert p.aroma(0x1B, 60).hex() == "6e1b003cc5"
    assert p.massage_timer("D1RM", 0).hex() == "6e01005ecd"
    assert p.massage_timer("D9RM", 0).hex() == "6e01008bfa"
    assert p.massage_popup("15").hex() == p.massage_timer("D1RM", 2).hex() == "6e01005fce"


def test_stream_dispatched_capabilities_follow_the_wider_lookup_first():
    receive = ReceiveState()

    def feed(payload: str) -> None:
        receive.feed(
            bytes.fromhex(payload),
            app=maxprime.APP,
            layout="YFRM",
            desk_bound=False,
            table_controls_bound=False,
        )

    feed("6e0e00037f00fe")
    assert not receive.light_capable and receive.buffer == ""
    feed("aa6e0e00")
    feed("037f")
    assert receive.light_capable and receive.last_value == "6e0e00037f"
    feed("6e1a00028a")
    assert not receive.aroma_capable and receive.last_value == "6e1a00028a"
    with pytest.raises(MalformedFrame):
        feed("6e09010079")
    assert not receive.alarm_capable
