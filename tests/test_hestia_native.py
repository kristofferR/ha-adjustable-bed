"""Hestia's actual HA native entities, shared alarm action and setup route."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.hestia.controller import HestiaController
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.runtime_data import entry_runtime
from tests.form_helpers import finish_new_bed
from tests.hold_lease_wire import virtual_clock
from tests.test_somos import gatt

ADDRESS = "AA:BB:CC:DD:01:64"


async def test_explicit_manual_ingress_owns_its_fixed_layout(hass):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["hestia_motion"]})
    step = await flow.async_step_manual_entry({"address": ADDRESS})
    await finish_new_bed(flow, step)
    data = flow._finish_with_verify.await_args.args[0]
    assert resolve_profile_id(data) == "hestia_motion"
    assert data[const.CONF_MOTOR_COUNT] == 2
    assert data[const.CONF_HAS_MASSAGE] is True
    assert data.get(const.CONF_DISABLE_ANGLE_SENSING, True) is True
    assert per_side_profile("hestia_motion", None) is not None


async def test_real_native_controls_alarm_and_admission(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    # Arbitrary services are legal. Reuse only the test GATT object's shape.
    mock_bleak_client.services = gatt("a")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Hestia Motion",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Hestia Motion",
            const.CONF_BED_TYPE: "hestia_motion",
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime.controller, HestiaController)
    registry = er.async_get(hass)
    entries = [
        item for item in registry.entities.values() if item.config_entry_id == entry.entry_id
    ]
    device = next(item.device_id for item in entries if item.device_id)

    def entity(domain, suffix):
        entity_id = registry.async_get_entity_id(domain, const.DOMAIN, f"{ADDRESS}_{suffix}")
        assert entity_id and hass.states.get(entity_id) is not None, suffix
        return entity_id

    async def call(domain, service, suffix, **fields):
        await hass.services.async_call(
            domain, service, {"entity_id": entity(domain, suffix), **fields}, blocking=True
        )

    def words():
        return [bytes(c.args[1]).hex() for c in mock_bleak_client.write_gatt_char.await_args_list]

    with virtual_clock():
        mock_bleak_client.write_gatt_char.reset_mock()
        await call("select", "select_option", "controller_select_hestia_wave", option="2")
        await call("select", "select_option", "controller_select_hestia_intensity", option="3")
        assert not words()
        await call("switch", "turn_on", "controller_switch_hestia_massage")
        assert words() == ["e5fe1610000022d4", "e5fe1610000013e3"]
        await call("switch", "turn_off", "controller_switch_hestia_massage")
        assert words()[-1] == "e5fe1610000010e6"
        await call("select", "select_option", "massage_timer", option="20 min")
        assert words()[-1] == "e5fe1610000031c5"
        for on in ("turn_on", "turn_off"):
            await call("light", on, "under_bed_lights")
            light_state = hass.states.get(entity("light", "under_bed_lights"))
            assert light_state is not None
            assert light_state.attributes.get("assumed_state") is True
        assert words()[-2:] == ["e5fe1631000001d4", "e5fe1631000000d5"]
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device, "control": "both_up", "duration": 0.2},
            blocking=True,
        )
        assert words() == ["e5fe160000000501"] * 2 + ["e5fe160000000006"]
        await call("button", "press", "preset_memory_1")
        await call("button", "press", "preset_memory_1")
        await call("button", "press", "program_memory_2")
        assert words()[-3:] == ["e5fe1621000004e1", "e5fe1621000000e5", "e5fe1621000016cf"]
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device,
                "enabled": True,
                "time": "07:45:00",
                "wake_action": "memory_2",
                "massage": True,
                "massage_intensity": 3,
                "massage_duration": 20,
            },
            blocking=True,
        )
        frame = bytes(mock_bleak_client.write_gatt_char.await_args_list[-1].args[1])
        assert frame[:3] == bytes.fromhex("eafe16")
        assert frame[6:12] == bytes((45, 7, 19, 34, 49, 6))
        mock_bleak_client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {"device_id": device, "enabled": True, "time": "07:45:00", "weekdays": ["monday"]},
                blocking=True,
            )
        assert not words()
        await call("select", "select_option", "controller_select_hestia_hour", option="8")
        await call("select", "select_option", "controller_select_hestia_minute", option="12")
        await call("select", "select_option", "controller_select_hestia_memory", option="memory_1")
        await call("switch", "turn_on", "controller_switch_hestia_enhancement")
        assert not words()
        await call("switch", "turn_on", "controller_switch_hestia_alarm")
        frame = bytes(mock_bleak_client.write_gatt_char.await_args_list[-1].args[1])
        assert frame[6:12] == bytes((12, 8, 19, 34, 49, 4))
        await call("switch", "turn_off", "controller_switch_hestia_alarm")
        frame = bytes(mock_bleak_client.write_gatt_char.await_args_list[-1].args[1])
        assert frame[6:12] == b"\xff" * 6
    assert await runtime.async_disconnect(serialize_with_commands=True)
    assert runtime.capability_controller.persisted_app_state["timer"] == "20"
    mock_bleak_client.write_gatt_char.reset_mock()
    await call("select", "select_option", "controller_select_hestia_wave", option="1")
    assert not words()
    with virtual_clock():
        await call("switch", "turn_on", "controller_switch_hestia_massage")
    assert words() == ["e5fe1610000021d5", "e5fe1610000013e3"]
    for suffix in ("back", "legs", "both"):
        assert hass.states.get(entity("cover", suffix)).attributes["hold_lease_mode"] == "stream"
    assert not any("angle" in item.unique_id for item in entries)
    assert await hass.config_entries.async_unload(entry.entry_id)
