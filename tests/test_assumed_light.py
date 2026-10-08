"""Opt-in state estimates for existing toggle-only lighting controls."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.light.const import ColorMode
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.const import BED_TYPE_KEESON, CONF_BED_TYPE, DOMAIN
from custom_components.adjustable_bed.light import (
    ASSUMED_LIGHT_DESCRIPTION,
    AdjustableBedAssumedLight,
    _light_entities_for,
)

from .conftest import make_controller_mock


@pytest.fixture
def toggle_runtime():
    controller = make_controller_mock(supports_light_toggle_control=True)
    controller.lights_toggle = AsyncMock()
    runtime = MagicMock()
    runtime.capability_controller = controller
    runtime.controller = controller
    runtime.device_info = {}
    runtime.entity_side = None
    runtime.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    runtime.entity_translation_key.side_effect = lambda key: key
    command_lock = asyncio.Lock()

    async def dispatch(command, *, cancel_running):
        assert cancel_running is False
        async with command_lock:
            await command(runtime.controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    return runtime


async def test_toggle_light_is_opt_in_and_preserves_button(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator_connected,
    enable_custom_integrations,
) -> None:
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BED_TYPE: BED_TYPE_KEESON},
    )
    with patch(
        "custom_components.adjustable_bed.beds.keeson.KeesonController.lights_toggle",
        new=AsyncMock(),
    ) as toggle:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        toggle.assert_not_awaited()

    runtime = hass.data[DOMAIN][mock_config_entry.entry_id]
    registry = er.async_get(hass)
    light_id = registry.async_get_entity_id(
        "light", DOMAIN, runtime.entity_unique_id(ASSUMED_LIGHT_DESCRIPTION.key)
    )
    assert light_id is not None
    assert registry.async_get(light_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(light_id) is None
    button_id = registry.async_get_entity_id(
        "button", DOMAIN, runtime.entity_unique_id("toggle_light")
    )
    assert button_id is not None
    assert hass.states.get(button_id) is not None


@pytest.mark.parametrize("restored", [None, STATE_ON, STATE_OFF, "unknown", "unavailable"])
async def test_enabled_light_restores_estimate_without_toggling(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator_connected,
    enable_custom_integrations,
    restored: str | None,
) -> None:
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, CONF_BED_TYPE: BED_TYPE_KEESON},
    )
    registry = er.async_get(hass)
    light = registry.async_get_or_create(
        "light",
        DOMAIN,
        f"{mock_config_entry.data['address']}_{ASSUMED_LIGHT_DESCRIPTION.key}",
        config_entry=mock_config_entry,
    )
    with (
        patch.object(
            AdjustableBedAssumedLight,
            "async_get_last_state",
            new=AsyncMock(return_value=MagicMock(state=restored) if restored else None),
        ),
        patch(
            "custom_components.adjustable_bed.beds.keeson.KeesonController.lights_toggle",
            new=AsyncMock(),
        ) as toggle,
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        toggle.assert_not_awaited()
        state = hass.states.get(light.entity_id)
        assert state is not None
        assert state.state == (STATE_ON if restored == STATE_ON else STATE_OFF)
        assert state.attributes["assumed_state"] is True
        assert state.attributes["supported_color_modes"] == [ColorMode.ONOFF]

        await hass.services.async_call(
            "light", "toggle", {"entity_id": light.entity_id}, blocking=True
        )
        toggle.assert_awaited_once()
        assert hass.states.get(light.entity_id).state != state.state


async def test_repeated_and_concurrent_directional_calls_toggle_once(toggle_runtime) -> None:
    light = AdjustableBedAssumedLight(toggle_runtime)
    light.async_write_ha_state = MagicMock()

    await asyncio.gather(light.async_turn_on(), light.async_turn_on())
    await light.async_turn_on()
    assert light.is_on is True
    toggle_runtime.controller.lights_toggle.assert_awaited_once()

    await asyncio.gather(light.async_turn_off(), light.async_turn_off())
    await light.async_turn_off()
    assert light.is_on is False
    assert toggle_runtime.controller.lights_toggle.await_count == 2
    assert light.async_write_ha_state.call_count == 2


async def test_concurrent_toggles_both_run_and_use_live_controller(toggle_runtime) -> None:
    light = AdjustableBedAssumedLight(toggle_runtime)
    light.async_write_ha_state = MagicMock()
    previous = toggle_runtime.controller
    current = make_controller_mock(supports_light_toggle_control=True)
    current.lights_toggle = AsyncMock()
    toggle_runtime.controller = current

    await asyncio.gather(light.async_toggle(), light.async_toggle())

    assert light.is_on is False
    assert current.lights_toggle.await_count == 2
    previous.lights_toggle.assert_not_awaited()


@pytest.mark.parametrize("action", ["async_turn_on", "async_turn_off", "async_toggle"])
async def test_failed_command_keeps_estimate(toggle_runtime, action: str) -> None:
    light = AdjustableBedAssumedLight(toggle_runtime)
    light.async_write_ha_state = MagicMock()
    if action == "async_turn_off":
        await light.async_turn_on()
        light.async_write_ha_state.reset_mock()
    before = light.is_on
    toggle_runtime.controller.lights_toggle.side_effect = ConnectionError("write failed")

    with pytest.raises(ConnectionError, match="write failed"):
        await getattr(light, action)()

    assert light.is_on is before
    light.async_write_ha_state.assert_not_called()


async def test_side_lights_keep_independent_estimates_and_command_routes(
    hass: HomeAssistant, toggle_runtime
) -> None:
    left = toggle_runtime
    right = MagicMock()
    right.capability_controller = make_controller_mock(supports_light_toggle_control=True)
    right.device_info = {}
    lights = []
    for side, runtime in (("left", left), ("right", right)):
        runtime.entity_side = side
        runtime.entity_unique_id.side_effect = lambda key, side=side: f"bed_{key}_{side}"
        runtime.entity_translation_key.side_effect = lambda key, side=side: f"{key}_{side}"
        light, = _light_entities_for(hass, runtime)
        light.async_write_ha_state = MagicMock()
        lights.append(light)

    await lights[0].async_turn_on()

    assert lights[0].unique_id == "bed_under_bed_lights_assumed_left"
    assert lights[1].unique_id == "bed_under_bed_lights_assumed_right"
    assert lights[0].translation_key == "under_bed_lights_left"
    assert lights[0].is_on is True
    assert lights[1].is_on is False
    right.async_execute_controller_command.assert_not_called()


@pytest.mark.parametrize(
    "capabilities",
    [
        {"supports_light_toggle_control": False},
        {"supports_discrete_light_control": True},
        {"supports_light_color_control": True},
        {"supports_light_state_feedback": True},
        {"light_color_control_pending": True},
    ],
)
async def test_assumed_light_does_not_replace_other_light_modes(
    hass: HomeAssistant, toggle_runtime, capabilities: dict[str, bool]
) -> None:
    for key, value in capabilities.items():
        setattr(toggle_runtime.capability_controller, key, value)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "light", DOMAIN, "bed_under_bed_lights_assumed", config_entry=entry
    )

    lights = _light_entities_for(hass, toggle_runtime)

    assert not any(isinstance(light, AdjustableBedAssumedLight) for light in lights)
    assert registry.async_get(stale.entity_id) is None


async def test_unknown_capabilities_preserve_existing_assumed_light(
    hass: HomeAssistant, toggle_runtime
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "light", DOMAIN, "bed_under_bed_lights_assumed", config_entry=entry
    )
    toggle_runtime.capability_controller = None

    assert _light_entities_for(hass, toggle_runtime) == []
    assert registry.async_get(existing.entity_id) is not None
