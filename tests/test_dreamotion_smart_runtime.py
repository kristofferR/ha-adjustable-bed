"""Exercise the native HA scheduler, entity and service routes on concrete GATT."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.jiecang.dreamotion_smart import DreamotionSmartController
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from scripts.wire_snapshot import FakeClock, FakeServices, virtual_time
from tests.test_dreamotion_smart import LAYOUT


async def receiver(hass, index):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Dreamotion Smart",
        data={
            "address": f"AA:BB:CC:DD:EE:{index:02X}",
            "name": "Dreamotion Smart",
            const.CONF_BED_TYPE: const.BED_TYPE_DREAMOTION_SMART,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: "idle",
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._client = SimpleNamespace(
        is_connected=True,
        services=FakeServices(LAYOUT),
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )

    async def disconnected():
        target.client.is_connected = False

    target.client.disconnect.side_effect = disconnected
    target._controller = await create_controller(
        target, const.BED_TYPE_DREAMOTION_SMART, "auto", target.client
    )
    target.async_ensure_connected = AsyncMock(return_value=True)
    target._async_refresh_controller_auth = AsyncMock()
    await target.controller.start_notify()
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    return target


@pytest.fixture
async def runtime(hass):
    target = await receiver(hass, 1)
    await services.async_register_services(hass)
    yield target
    await target.async_shutdown()


async def test_rgb_entity_and_controller_select_use_current_runtime(hass, runtime):
    target = runtime
    c = target.controller
    c._receive(bytes.fromhex("f2f24507a164ff0080012c"))
    lights = _light_entities_for(hass, target)
    assert len(lights) == 1
    light = lights[0]
    light.async_write_ha_state = MagicMock()
    with virtual_time(FakeClock()):
        await light.async_turn_on(rgb_color=(18, 52, 171), brightness=128)
    frames = [a.args[1] for a in target.client.write_gatt_char.await_args_list]
    assert frames == [
        app.setting(0x43, 1),
        app.timed(app.Color(51, 18, 52, 171), 300),
        app.setting(0x43, 1),
    ]
    spec = next(s for s in c.controller_select_specs if s.key == "dreamotion_smart_duration")
    select = AdjustableBedControllerSelect(target, spec)
    select.async_write_ha_state = MagicMock()
    await select.async_select_option("60")
    assert c._timed[1] == 60
    assert target.client.write_gatt_char.await_count == len(frames)


async def test_memory_service_and_two_address_mirror_admission(hass, runtime):
    left = runtime
    right = await receiver(hass, 2)
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "dreamotion-pair"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    try:
        with (
            patch.object(services, "_resolve_sided_targets", return_value=([(pair, "both")], [])),
            virtual_time(FakeClock()),
        ):
            await hass.services.async_call(
                const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1}, blocking=True
            )
        for child in (left, right):
            assert [a.args[1] for a in child.client.write_gatt_char.await_args_list] == [
                bytes.fromhex("f1f10b0200000d7e")
            ]
        right.async_ensure_connected = AsyncMock(return_value=False)
        for child in (left, right):
            child.client.write_gatt_char.reset_mock()
        with (
            patch.object(services, "_resolve_sided_targets", return_value=([(pair, "both")], [])),
            virtual_time(FakeClock()),
            pytest.raises(HomeAssistantError),
        ):
            await hass.services.async_call(
                const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1}, blocking=True
            )
        assert left.client.write_gatt_char.await_count == 0
    finally:
        await pair.async_shutdown()


async def test_setup_owns_fixed_layout_and_offline_factory(hass):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES

    setup = SETUP_PROFILES[const.BED_TYPE_DREAMOTION_SMART]
    assert setup.owns[const.CONF_MOTOR_COUNT] == 4
    assert not setup.questions
    assert const.CONF_PROTOCOL_VARIANT in hidden_generic_fields(
        const.BED_TYPE_DREAMOTION_SMART, "auto"
    )
    assert per_side_profile(const.BED_TYPE_DREAMOTION_SMART, "auto") is not None
    target = await receiver(hass, 3)
    try:
        target._client = None
        offline = await create_controller(
            target, const.BED_TYPE_DREAMOTION_SMART, "auto", target.client
        )
        assert isinstance(offline, DreamotionSmartController)
        offline.set_page("presets")
        replacement = await create_controller(target, const.BED_TYPE_DREAMOTION_SMART, "auto", None)
        assert replacement._page == "presets"  # Local choice survives the first live controller.
        assert len(offline.motor_control_specs) == 4
        assert offline.execution.declared == {"hold"}
        assert const.BED_TYPE_DREAMOTION_SMART in const.OFFLINE_CAPABILITY_SAFE_BED_TYPES
    finally:
        await target.async_shutdown()
