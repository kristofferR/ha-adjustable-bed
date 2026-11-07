"""Entity translations hold exactly the keys entities can be given."""

from __future__ import annotations

import json

from tests.entity_translation_reachability import (
    TRANSLATION_FILES,
    entity_strings,
    factory_controllers,
    missing_translations,
    unreachable_side_keys,
)


async def test_no_side_suffixed_copy_is_left() -> None:
    controllers = await factory_controllers()
    assert unreachable_side_keys(entity_strings(), controllers) == {}


async def test_every_key_an_entity_can_be_given_is_translated() -> None:
    """A missing key names the entity after its device alone, such as "Bed Left" (#711)."""
    assert missing_translations(entity_strings(), await factory_controllers()) == {}


async def test_only_natively_sided_keys_keep_a_side_suffix() -> None:
    """Paired sides name their device, so side and combined copies are dead."""
    strings: dict[str, dict[str, object]] = {
        "cover": {"back": {}, "back_left": {}, "head": {}, "head_left": {}, "legs": {}, "legs_both": {}},
        "button": {"stop": {}, "stop_both": {}, "preset_flat": {}, "preset_flat_right": {}},
        "climate": {"sleep_number_thermal_climate": {}, "sleep_number_thermal_climate_left": {}},
        "sensor": {"motomotion_heat_left": {}},
    }
    # back_left is a Sleep Number MCR motor, head_left and stop_both are code
    # literals, the side climate is built per side and motomotion_heat_left has
    # no base to copy.
    assert unreachable_side_keys(strings, await factory_controllers()) == {
        "cover": {"legs_both"},
        "button": {"preset_flat_right"},
    }


def test_translation_files_share_entity_strings() -> None:
    first, *rest = (json.loads(path.read_text())["entity"] for path in TRANSLATION_FILES)
    assert all(entity == first for entity in rest)


def test_translation_files_name_single_address_side_devices() -> None:
    for path in TRANSLATION_FILES:
        devices = json.loads(path.read_text())["device"]
        assert devices == {
            "left_side": {"name": "{name} Left"},
            "right_side": {"name": "{name} Right"},
        }
