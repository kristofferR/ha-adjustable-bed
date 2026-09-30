"""Profile reloads reconcile app entities and preserve native unknown-state toggles."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_MALOUF_APP,
    CONF_BED_TYPE,
    DOMAIN,
)
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for

from .conftest import make_controller_mock
from .test_malouf_app import make_controller, written


def configure_entity_runtime(
    hass: HomeAssistant, controller: BedController, bed_type: str = BED_TYPE_MALOUF_APP
) -> MagicMock:
    controller._coordinator.motor_count = 2
    controller._coordinator.get_max_angle.return_value = 68.0
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BED_TYPE: bed_type})
    entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.capability_controller = controller
    coordinator.controller = controller
    coordinator.has_massage = True
    coordinator.disable_angle_sensing = True
    coordinator.device_info = {}
    coordinator.entity_side = "left"
    coordinator.entity_unique_id.side_effect = lambda key: f"bed_{key}_left"
    coordinator.entity_translation_key.side_effect = lambda key: key
    return coordinator


@pytest.mark.parametrize(
    ("transport", "model", "app", "active_key"),
    [
        ("okin_new", "Premium", "lucid", "malouf_read"),
        ("richmat_framed", "GoodLifeBase", "lucid", "malouf_oz_save_memory_2"),
        ("richmat_framed", "Premium", "lucid", None),
        ("okin_new", "Premium", "malouf", None),
    ],
)
async def test_profile_reload_reconciles_only_current_side_app_buttons(
    hass: HomeAssistant, transport: str, model: str, app: str, active_key: str | None
) -> None:
    controller = make_controller(transport, model, app)
    coordinator = configure_entity_runtime(hass, controller)
    registry = er.async_get(hass)
    previous = {
        key: registry.async_get_or_create(
            "button", DOMAIN, f"bed_{key}_left", config_entry=coordinator.entry
        )
        for key in ("malouf_read", "malouf_oz_save_memory_2")
    }
    other_side = registry.async_get_or_create(
        "button", DOMAIN, "bed_malouf_read_right", config_entry=coordinator.entry
    )
    unrelated = registry.async_get_or_create(
        "button", DOMAIN, "bed_other_action_left", config_entry=coordinator.entry
    )

    entities = _button_entities_for(hass, coordinator)

    for key, old in previous.items():
        assert (registry.async_get(old.entity_id) is not None) is (key == active_key)
    assert registry.async_get(other_side.entity_id) is not None
    assert registry.async_get(unrelated.entity_id) is not None
    assert {
        entity.unique_id for entity in entities if "malouf_" in entity.unique_id
    } == ({f"bed_{active_key}_left"} if active_key else set())


@pytest.mark.parametrize("destination", ["richmat", "no_massage", "different_bed_type", "retain"])
async def test_profile_reload_reconciles_massage_sensor(
    hass: HomeAssistant, destination: str
) -> None:
    controller = (
        make_controller_mock(
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            position_number_specs=(),
        )
        if destination == "different_bed_type"
        else make_controller(
            "richmat_framed" if destination == "richmat" else "okin_new",
            "E450" if destination == "no_massage" else "S755",
        )
    )
    coordinator = configure_entity_runtime(
        hass, controller,
        BED_TYPE_DIAGNOSTIC if destination == "different_bed_type" else BED_TYPE_MALOUF_APP,
    )
    registry = er.async_get(hass)
    previous = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_malouf_massage_remaining_left", config_entry=coordinator.entry
    )
    other_side = registry.async_get_or_create(
        "sensor", DOMAIN, "bed_malouf_massage_remaining_right", config_entry=coordinator.entry
    )

    entities = _sensor_entities_for(hass, coordinator)

    assert (registry.async_get(previous.entity_id) is not None) is (destination == "retain")
    assert registry.async_get(other_side.entity_id) is not None
    assert any(
        entity.unique_id == "bed_malouf_massage_remaining_left" for entity in entities
    ) is (destination == "retain")


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        ("okin_legacy", ["e6fe16000002000003"]),
        ("okin_new", ["0502000200000000", "00b0"]),
    ],
)
async def test_feedback_light_entity_toggles_without_initial_state(
    hass: HomeAssistant, transport: str, expected: list[str]
) -> None:
    controller = make_controller(transport, "S750")
    coordinator = configure_entity_runtime(hass, controller)

    async def dispatch(command, *, cancel_running):
        assert cancel_running is False
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    light = _light_entities_for(hass, coordinator)[0]
    assert light.is_on is None
    assert controller.get_light_state() == {}

    await light.async_toggle()

    assert [frame.hex() for frame in written(controller)] == expected
    assert light.is_on is None
    assert controller.get_light_state() == {}
