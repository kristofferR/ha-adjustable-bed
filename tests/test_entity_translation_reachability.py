"""Entity translations hold no paired-side variant that no entity can be given."""

from __future__ import annotations

import json

from tests.entity_translation_reachability import (
    TRANSLATION_FILES,
    entity_strings,
    factory_controllers,
    unreachable_side_variants,
)


async def test_every_side_variant_is_reachable() -> None:
    controllers = await factory_controllers()
    assert unreachable_side_variants(entity_strings(), controllers) == {}


async def test_controller_state_sensors_and_unpaired_platforms_carry_no_side_variant() -> None:
    """The removed classes: sided controller-state sensors and non-combined ``_both``."""
    strings = {
        "sensor": {"motion_bed_brightness": {}, "motion_bed_brightness_left": {}, "back_angle_left": {}},
        "binary_sensor": {"motion_bed_fault_right": {}, "ble_connection_left": {}},
        "cover": {"back_both": {}, "back_left": {}},
        "button": {"preset_flat_both": {}, "connect_both": {}},
        "number": {"back_position_both": {}, "massage_head_intensity_both": {}},
    }
    assert unreachable_side_variants(strings, await factory_controllers()) == {
        "sensor": {"motion_bed_brightness_left"},
        "binary_sensor": {"motion_bed_fault_right"},
        "cover": {"back_both"},
        "button": {"connect_both"},
        "number": {"massage_head_intensity_both"},
    }


def test_translation_files_share_entity_strings() -> None:
    first, *rest = (json.loads(path.read_text())["entity"] for path in TRANSLATION_FILES)
    assert all(entity == first for entity in rest)
