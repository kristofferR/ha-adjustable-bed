"""Immutable artifact byte expectations and exact default/nested membership."""

import json
from pathlib import Path

from custom_components.adjustable_bed.gmmotor_catalog import PROFILES
from custom_components.adjustable_bed.gmmotor_profiles import load_profile
from custom_components.adjustable_bed.gmmotor_protocol import Material

VECTORS = json.loads((Path(__file__).parent / "fixtures/gmmotor_vectors.json").read_text())


def test_all_source_material_wire_forms():
    for material, forms in VECTORS["builder_vectors"]:
        m = Material(*material)
        for side, single, long, expected in forms:
            assert m.packet(side=side, single=single, long=long).hex() == expected, (
                material,
                side,
                single,
                long,
            )


def test_every_default_and_nested_control_has_its_source_state_and_wire_effect():
    assert set(PROFILES) == set(VECTORS["profiles"])
    for code, expected_actions in VECTORS["profiles"].items():
        if code == "QRRM":
            assert not expected_actions  # QR is a selector, not a final controller.
            continue
        actual = load_profile(code).controls
        assert len(actual) == len(expected_actions), code
        for action, index in zip(actual, expected_actions, strict=True):
            material, cases = VECTORS["ui_vectors"][index]
            m = action.material
            assert [
                m.name,
                m.opcode,
                m.long_opcode,
                m.short_override,
                m.long_override,
                m.single_override,
                action.gesture,
            ] == material, code
            for before, phase, after, packet in cases:
                state, wire = action.apply(before, phase, side=0, single=False)
                assert (state, wire.hex()) == (after, packet), (code, material, before, phase)


def test_every_selected_profile_keeps_its_source_gates_and_alarm_overrides():
    for code, expected in VECTORS["profile_metadata"].items():
        if code == "QRRM":
            continue
        p = load_profile(code)
        assert [
            p.has_light,
            p.eight_colors,
            p.repeat_alarm,
            p.sleep_kind,
            list(p.sides),
            [list(choice) for choice in p.alarm_choices],
            p.massage_timer,
        ] == expected, code
