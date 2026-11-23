"""Catalog buttons take the shared shape of what they are."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.beds.catalog_buttons import (
    Kind,
    catalog_button,
    classify,
    unique_buttons,
)
from custom_components.adjustable_bed.card import (
    CARD_LIGHTING,
    CARD_MASSAGE,
    CARD_PRESET_SAVE,
    CARD_PRESETS,
    CARD_UTILITY,
    CardRole,
    memory_card,
    motor_card,
)


async def _press(_controller: object) -> None:
    return None


@pytest.mark.parametrize(
    ("label", "translation_key", "card", "enabled"),
    [
        ("Zero gravity", "preset_zero_g", CARD_PRESETS, True),
        ("TV position", "preset_tv", CARD_PRESETS, True),
        ("Sleep aid", "catalog_preset", CARD_PRESETS, True),
        ("Head up and foot down", "catalog_preset", CARD_PRESETS, True),
        ("Memory position 2", "preset_memory_2", memory_card(2), True),
        ("M1", "preset_memory_1", memory_card(1), True),
        ("Save Memory position 1", "program_memory_1", memory_card(1, save=True), True),
        ("Save TV position", "catalog_save", CARD_PRESET_SAVE, True),
        ("Head up", "head_up", motor_card("head", CardRole.UP), True),
        ("Foot Down", "feet_down", motor_card("feet", CardRole.DOWN), True),
        ("Head and foot up", "head_feet_up", motor_card("head_feet", CardRole.UP), True),
        ("Increase head massage", "massage_head_up", CARD_MASSAGE, True),
        ("Massage foot intensity up", "massage_foot_up", CARD_MASSAGE, True),
        ("Massage: Head Up", "massage_head_up", CARD_MASSAGE, True),
        ("Massage mode all off", "massage_all_off", CARD_MASSAGE, True),
        ("Massage 10 minute timer", "catalog_massage", CARD_MASSAGE, True),
        ("Light board", "catalog_light", CARD_LIGHTING, True),
        ("Music next song", "catalog_action", CARD_UTILITY, False),
        ("Fan pulse mode", "catalog_action", CARD_UTILITY, False),
        ("Motor reset", "catalog_action", CARD_UTILITY, False),
    ],
)
def test_a_label_maps_onto_the_shape_of_what_it_is(
    label: str, translation_key: str, card: object, enabled: bool
) -> None:
    control = classify(label)
    assert control is not None
    assert (control.translation_key, control.card, control.enabled) == (
        translation_key,
        card,
        enabled,
    )


@pytest.mark.parametrize("label", ["No action", "Massage menu", "Logo"])
def test_an_empty_slot_or_menu_heading_is_not_a_control(label: str) -> None:
    assert classify(label) is None
    assert catalog_button("key", label, _press) is None


def test_a_catalog_group_does_not_turn_music_into_massage() -> None:
    control = classify("Music next", kind=Kind.MASSAGE)
    assert control is not None and control.kind is Kind.EXTRA


def test_a_preset_save_asks_first_and_a_memory_save_uses_set_mode() -> None:
    preset = catalog_button("save_tv", "Save TV", _press, kind=Kind.SAVE)
    memory = catalog_button("save_m1", "Save Memory 1", _press, kind=Kind.SAVE)
    assert preset is not None and memory is not None
    assert (preset.card, preset.requires_confirmation) == (CARD_PRESET_SAVE, True)
    assert preset.translation_placeholders == {"preset": "TV"}
    assert (memory.card, memory.requires_confirmation) == (memory_card(1, save=True), False)


def test_a_terse_screen_label_keeps_its_name_but_takes_the_enum_shape() -> None:
    spec = catalog_button("p", "Gravedad Cero", _press, meaning="Zero gravity 2")
    assert spec is not None
    assert (spec.translation_key, spec.card) == ("catalog_preset", CARD_PRESETS)
    assert spec.translation_placeholders == {"action": "Gravedad cero"}


def test_unique_buttons_drops_repeats_and_tells_same_names_apart() -> None:
    specs = unique_buttons(
        [
            catalog_button("a", "Zero gravity", _press),
            catalog_button("a", "Zero gravity", _press),
            catalog_button("b", "Zero gravity", _press),
            catalog_button("c", "Wave", _press),
            catalog_button("d", "Wave", _press),
            catalog_button("e", "No action", _press),
        ]
    )
    assert [(s.key, s.translation_key, s.translation_placeholders) for s in specs] == [
        ("a", "preset_zero_g", None),
        ("b", "catalog_preset", {"action": "Zero gravity 2"}),
        ("c", "catalog_massage", {"action": "Wave"}),
        ("d", "catalog_massage", {"action": "Wave 2"}),
    ]


@pytest.mark.parametrize("remote", ["harm", "hbrm", "jmrm", "o6rm"])
async def test_mlily_remotes_list_each_control_once(remote: str) -> None:
    """These remotes repeat catalog descriptors; one entity per control, one unique ID each."""
    from custom_components.adjustable_bed.const import CONF_PROTOCOL_VARIANT
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    coordinator = _FactoryCoordinator()
    coordinator.entry.data = {**coordinator.entry.data, CONF_PROTOCOL_VARIANT: remote}
    controller = await create_controller(coordinator, "mlily", remote, _make_connected_client())
    keys = [spec.key for spec in controller.controller_button_specs]
    names = [spec.translation_placeholders for spec in controller.controller_button_specs]
    assert len(keys) == len(set(keys))
    assert not any(name and "No action" in name.values() for name in names)


def test_an_explicit_save_reads_its_memory_slot() -> None:
    """Richmat legacy names a memory save "Save to Memory 1"."""
    spec = catalog_button("save", "Save to Memory 1", _press, kind=Kind.SAVE)
    assert spec is not None
    assert (spec.translation_key, spec.card) == ("program_memory_1", memory_card(1, save=True))
    assert not spec.requires_confirmation


def test_a_confirmed_save_never_publishes_a_held_gesture() -> None:
    """The card holds a held button without asking; a save must ask first."""
    from custom_components.adjustable_bed.beds.entity_specs import ControllerHoldSpec

    spec = catalog_button("save_zg", "Save Zero gravity", _press, kind=Kind.SAVE,
                          hold=ControllerHoldSpec("save_zg"))
    assert spec is not None and spec.hold is None and spec.requires_confirmation


def test_a_catalog_clock_setter_is_a_disabled_diagnostic() -> None:
    """SUTA's "Sync clock" until the shared sync_clock action covers the bed."""
    spec = catalog_button("suta_set_date", "Sync clock", _press)
    assert spec is not None and spec.diagnostic and not spec.entity_registry_enabled_default


def test_an_app_motor_button_tells_the_card_not_to_time_it() -> None:
    """The card would otherwise send timed_move for a motor the bed's covers do not have."""
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.button import ControllerActionButton

    runtime = MagicMock()
    runtime.entity_side = None
    runtime.capability_controller = None
    spec = catalog_button("lumbarup", "Lumbar up", _press)
    assert spec is not None
    assert ControllerActionButton(runtime, spec).extra_state_attributes["timed_move"] is False
    preset = catalog_button("zg", "Zero G", _press)
    assert preset is not None
    assert "timed_move" not in ControllerActionButton(runtime, preset).extra_state_attributes
