"""Customatic app entities follow the selected profile across reloads."""

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_DIAGNOSTIC,
    DOMAIN,
)
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from tests.conftest import make_controller_mock
from tests.test_customatic import make_controller, written
from tests.test_malouf_app_entities import configure_entity_runtime


@pytest.mark.parametrize(("profile", "bed_type", "expected"), [
    ("clarity", BED_TYPE_CUSTOMATIC_CLARITY, {"back", "legs"}),
    ("jeromes", BED_TYPE_CUSTOMATIC_JEROMES, {"back", "legs"}),
    ("remedy", BED_TYPE_CUSTOMATIC_REMEDY, {"back", "legs", "lumbar"}),
])
async def test_only_selected_profile_axes_and_light_button_exist(hass, profile, bed_type, expected):
    controller = make_controller(profile)
    runtime = configure_entity_runtime(hass, controller, bed_type)
    covers = _cover_entities_for(hass, runtime)
    assert {cover.entity_description.key for cover in covers} == expected
    buttons = _button_entities_for(hass, runtime)
    assert any(button.unique_id == "bed_toggle_light_left" for button in buttons) is (profile != "jeromes")
    assert _light_entities_for(hass, runtime) == []
    assert not any("memory_" in button.unique_id for button in buttons)


@pytest.mark.parametrize("destination", ["clarity", "jeromes", "other"])
async def test_app_button_reload_preserves_only_current_side_actions(hass, destination):
    controller = (make_controller_mock(controller_button_specs=()) if destination == "other"
                  else make_controller(destination))
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_DIAGNOSTIC if destination == "other"
                                       else BED_TYPE_CUSTOMATIC_CLARITY)
    registry = er.async_get(hass)
    old = {key: registry.async_get_or_create("button", DOMAIN, f"bed_{key}_left",
                                             config_entry=runtime.entry)
           for key in ["customatic_zg", "customatic_restored_flat", "customatic_refresh_device_info"]}
    other = registry.async_get_or_create("button", DOMAIN, "bed_customatic_zg_right",
                                         config_entry=runtime.entry)
    unrelated = registry.async_get_or_create("button", DOMAIN, "bed_unrelated_left",
                                             config_entry=runtime.entry)
    entities = _button_entities_for(hass, runtime)
    desired = {spec.key for spec in controller.controller_button_specs}
    for key, row in old.items():
        assert (registry.async_get(row.entity_id) is not None) is (key in desired)
    assert registry.async_get(other.entity_id) is not None
    assert registry.async_get(unrelated.entity_id) is not None
    assert {entity.unique_id for entity in entities if "customatic_" in entity.unique_id} == {
        f"bed_{key}_left" for key in desired
    }


async def test_switching_from_remedy_retires_lumbar_cover(hass):
    controller = make_controller("clarity")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_CUSTOMATIC_CLARITY)
    registry = er.async_get(hass)
    old = registry.async_get_or_create("cover", DOMAIN, "bed_lumbar_left", config_entry=runtime.entry)
    other = registry.async_get_or_create("cover", DOMAIN, "bed_lumbar_right", config_entry=runtime.entry)
    _cover_entities_for(hass, runtime)
    assert registry.async_get(old.entity_id) is None
    assert registry.async_get(other.entity_id) is not None


@pytest.mark.parametrize("retain", [True, False])
async def test_device_info_sensor_lifecycle_preserves_other_side(hass, retain):
    controller = (make_controller("clarity") if retain else make_controller_mock(
        controller_state_sensor_specs=(), stale_controller_state_sensor_entity_keys=frozenset(),
        position_number_specs=(),
    ))
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_CUSTOMATIC_CLARITY if retain
                                       else BED_TYPE_DIAGNOSTIC)
    registry = er.async_get(hass)
    keys = ["customatic_manufacturer", "customatic_hardware_revision", "customatic_software_revision",
            "customatic_firmware_revision", "customatic_model"]
    old = [registry.async_get_or_create("sensor", DOMAIN, f"bed_{key}_left", config_entry=runtime.entry)
           for key in keys]
    other = registry.async_get_or_create("sensor", DOMAIN, "bed_customatic_model_right",
                                         config_entry=runtime.entry)
    entities = _sensor_entities_for(hass, runtime)
    assert all((registry.async_get(row.entity_id) is not None) is retain for row in old)
    assert registry.async_get(other.entity_id) is not None
    assert {entity.unique_id for entity in entities if "customatic_" in entity.unique_id} == (
        {f"bed_{key}_left" for key in keys} if retain else set()
    )


async def test_native_toggle_button_sends_one_frame_without_inventing_light_state(hass):
    from unittest.mock import AsyncMock

    controller = make_controller("clarity")
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_CUSTOMATIC_CLARITY)

    async def dispatch(command, **kwargs):
        await command(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    button = next(button for button in _button_entities_for(hass, runtime)
                  if button.unique_id == "bed_toggle_light_left")
    await button.async_press()
    assert written(controller) == ["040200020000"]
    assert controller.get_light_state() == {}


async def test_cross_axis_cover_stop_preempts_shared_mask_with_production_scheduler(hass):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_DISABLE_ANGLE_SENSING
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    source = make_controller("clarity")
    client = source.client
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_CUSTOMATIC_CLARITY,
        CONF_DISABLE_ANGLE_SENSING: True,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client
    coordinator._controller = source
    coordinator._motor_pulse_count = 100
    source._coordinator = coordinator
    started = asyncio.Event()
    frames = []

    async def write(_characteristic, payload, **kwargs):
        frames.append(payload.hex())
        if payload.hex() == "040200000001":
            started.set()

    client.write_gatt_char.side_effect = write
    covers = {cover.entity_description.key: cover for cover in _cover_entities_for(hass, coordinator)}
    assert all(cover._motor_resource == "*" for cover in covers.values())
    with (
        patch.object(coordinator, "_async_prepare_controller_operation", AsyncMock(return_value=source)),
        patch.object(coordinator, "_async_finish_controller_operation", AsyncMock()),
        patch.object(covers["back"], "async_write_ha_state", MagicMock()),
        patch.object(covers["legs"], "async_write_ha_state", MagicMock()),
    ):
        movement = asyncio.create_task(covers["back"].async_open_cover())
        await started.wait()
        async with asyncio.timeout(1):
            await covers["legs"].async_stop_cover()
            await movement
    assert frames == ["040200000001", "040200000000", "040200000000"]
