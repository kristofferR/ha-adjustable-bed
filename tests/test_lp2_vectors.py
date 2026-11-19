"""Literal command inputs from L&P Adjustable Base 2.3.25."""

import gzip
import json
from pathlib import Path

from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.protocol import control
from custom_components.adjustable_bed.codec import richmat as codec

ROOT = Path(__file__).parent / "fixtures" / "lp2"


def vectors(name):
    return json.loads(gzip.decompress((ROOT / (name + ".json.gz")).read_bytes()))


def test_all_resource_literals_fit_existing_codec():
    for opcode, raw, framed in vectors("frames"):
        assert codec.encode("nordic", int(opcode, 16)).hex() == raw.lower()
        for mode, expected in framed.items():
            assert codec.command(int(opcode, 16), int(mode)).hex() == expected.lower()


def test_runtime_getters_reproduce_literal_control_states():
    catalog = load_catalog("lp2")
    for layout, node, status, route, mode, event, head, flag, expected in vectors(
        "controls"
    ):
        if route == "LOCAL":
            assert expected is None
            continue
        button = next(c for c in catalog.models[layout].controls if c.node == node)
        wire = "RAW" if route == "P1_RAW_OPCODE" else "FRAMED"
        argument = 3 if event == "long_threshold" else 2 if event == "short_release" else status
        selected = selected_operand(
            button, wire, argument, Selection(head=head, press_flag="5" + flag)
        )
        assert (control(selected, wire, mode).hex() if isinstance(selected, bytes) else None) == (
            expected.lower() if expected else None
        ), (layout, node, event)
