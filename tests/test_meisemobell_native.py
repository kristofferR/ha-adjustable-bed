"""Native HA setup, entities/card placement and shared action admission."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.meisemobell.controller import MeisemobellController
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import meisemobell as p
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.setup_questions import setup_profile
from tests.hold_lease_wire import virtual_clock
from tests.test_meisemobell import frames, gatt

ADDRESS = "AA:BB:CC:DD:AA:40"


@pytest.mark.parametrize("route", p.PROFILES)
async def test_native_setup_entities_card_and_services(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, route
):
    mock_bleak_client.services = gatt(route)
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Meisemobell",
        const.CONF_BED_TYPE: "meisemobell",
        const.CONF_PROTOCOL_VARIANT: route,
        const.CONF_HAS_MASSAGE: False,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_MOTOR_COUNT: 2,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }
    entry = MockConfigEntry(domain=const.DOMAIN, title="Meisemobell", unique_id=ADDRESS, data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    c = runtime.controller
    assert isinstance(c, MeisemobellController)
    assert c.profile is p.PROFILES[route]
    registry = er.async_get(hass)
    entities = [
        item for item in registry.entities.values() if item.config_entry_id == entry.entry_id
    ]
    device = next(item.device_id for item in entities if item.device_id)
    for axis in ("back", "legs"):
        assert registry.async_get_entity_id("cover", const.DOMAIN, f"{ADDRESS}_{axis}")
    for slot in (1, 2):
        entity = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_preset_memory_{slot}"
        )
        assert entity
        attrs = hass.states.get(entity).attributes
        assert attrs["card_section"] == "memory"
        save = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_program_memory_{slot}"
        )
        assert save
        assert hass.states.get(save).attributes["card_role"] == "save"
    assert not any(
        item.domain == "number" or "massage_toggle" in item.unique_id for item in entities
    )
    for action in ("reset_memories", "reset_settings"):
        entity = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_meisemobell_{action}"
        )
        assert entity and registry.async_get(entity).disabled_by is not None
    with virtual_clock():
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device, "control": "head_up", "duration": 0.4},
            blocking=True,
        )
        assert frames(mock_bleak_client)[:2] == [p.control(route, "head_up")] * 2
        assert frames(mock_bleak_client)[-2:] == [p.control(route, "stop")] * 2
        mock_bleak_client.write_gatt_char.reset_mock()
        if route == "15_22_15a":
            # Native shared service preflight needs a real complete peer readback.
            if c._link is None:
                await runtime.async_ensure_connected()
            c._receive(c._current(), bytes.fromhex("ed800300000000072d841300"))
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device,
                "enabled": True,
                "time": "06:30:00",
                "weekdays": ["monday"],
                "slot": 1,
                "wake_action": "memory_1",
            },
            blocking=True,
        )
        assert frames(mock_bleak_client)[0][:2] == (
            b"\xed\x80" if route == "15_22_15a" else b"\x07\x05"
        )
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN, "sync_clock", {"device_id": device}, blocking=True
        )
        assert frames(mock_bleak_client)[0] == p.clock(route, dt_util.now())
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("route", p.PROFILES)
async def test_explicit_setup_profile_and_side_ownership(hass, route):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    step = await start_new_bed(flow, "typed", "meisemobell")
    assert step["step_id"] == "profile_questions"
    step = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: route})
    assert step["step_id"] == "finish_settings"
    result = await flow.async_step_finish_settings({})
    assert result["type"] == "create_entry"
    data = flow._finish_with_verify.await_args.args[0]
    assert data[const.CONF_PROTOCOL_VARIANT] == route
    profile = setup_profile("meisemobell", route)
    assert profile is not None
    assert profile.owns[const.CONF_MOTOR_COUNT] == 2
    assert profile.owns[const.CONF_HAS_MASSAGE] is False
    assert per_side_profile("meisemobell", route).variant_owned
    assert (
        resolve_profile_id({const.CONF_BED_TYPE: "meisemobell", const.CONF_PROTOCOL_VARIANT: route})
        == "meisemobell:" + route
    )


async def test_native_pair_keeps_routes_and_checks_both_sides_before_alarm_writes(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    from tests.pair_mode import CONF_PAIR_CONNECTION_MODE
    from tests.test_paired_setup import _paired_entry_data

    mock_bleak_client.services = gatt("15_22_15a") + gatt("24_xx_xx")
    data = _paired_entry_data()
    data[const.CONF_BED_TYPE] = "meisemobell"
    data[CONF_PAIR_CONNECTION_MODE] = const.PAIR_CONNECTION_MODE_CONCURRENT
    data[const.CONF_CONNECTION_MODE] = const.CONNECTION_MODE_IDLE
    for child, route in zip(data[const.CONF_PAIR_CHILDREN], p.PROFILES, strict=True):
        child.update(
            {
                const.CONF_BED_TYPE: "meisemobell",
                const.CONF_PROTOCOL_VARIANT: route,
                const.CONF_MOTOR_COUNT: 2,
                const.CONF_HAS_MASSAGE: False,
                const.CONF_DISABLE_ANGLE_SENSING: True,
            }
        )
        child.pop("capabilities", None)
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="Meisemobell pair", data=data, unique_id=data[const.CONF_PAIR_ID]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert runtime.children["left"].controller.route == "15_22_15a"
    assert runtime.children["right"].controller.route == "24_xx_xx"
    device = next(
        item
        for item in dr.async_get(hass).devices
        if (const.DOMAIN, data[const.CONF_PAIR_ID]) in item.identifiers
    )
    assert device is not None
    with virtual_clock():
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device.id, "side": "right", "control": "foot_up", "duration": 0.1},
            blocking=True,
        )
        assert (
            frames(mock_bleak_client)
            == [p.control("24_xx_xx", "foot_up")] + [p.control("24_xx_xx", "stop")] * 2
        )
        mock_bleak_client.write_gatt_char.reset_mock()
        request = {
            "device_id": device.id,
            "side": "both",
            "enabled": True,
            "time": "06:30:00",
            "weekdays": ["monday"],
            "slot": 1,
            "wake_action": "memory_1",
        }
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(const.DOMAIN, "set_alarm", request, blocking=True)
        assert not any(
            frame[:2] in (b"\xed\x80", b"\x07\x05") for frame in frames(mock_bleak_client)
        )
        left = runtime.children["left"].controller
        left._receive(left._current(), bytes.fromhex("ed800300000000072d841300"))
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(const.DOMAIN, "set_alarm", request, blocking=True)
        assert any(frame[:2] == b"\xed\x80" for frame in frames(mock_bleak_client))
        assert bytes.fromhex("07058205061e000100") in frames(mock_bleak_client)
    assert await hass.config_entries.async_unload(entry.entry_id)
