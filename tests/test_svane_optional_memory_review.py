"""Optional query priority, opaque memory persistence and ordinary pulse overrides."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import POSITION, SvaneController, uuid
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_BOTH,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.svane_state import get_svane_session, svane_multi_slots
from tests.app_state_helpers import restart_app_state, stored_app_state
from tests.test_svane import make_controller, written


@pytest.fixture
async def current(hass, request):
    profile = request.param
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC if profile == "jmc" else SVANE_VARIANT_MULTI,
        CONF_DISCONNECT_AFTER_COMMAND: False,
        CONF_MOTOR_PULSE_COUNT: 1, CONF_MOTOR_PULSE_DELAY_MS: 1,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(profile)
    coordinator._client = controller.client
    coordinator._controller = controller
    controller._coordinator = coordinator
    await async_register_services(hass)
    try:
        yield coordinator, controller
    finally:
        await controller.stop_notify()
        coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("current", ["multi", "jmc"], indirect=True)
async def test_optional_reads_cannot_take_wire_before_first_command(current):
    coordinator, controller = current
    events = []
    release_read = asyncio.Event()
    original_read = controller.client.read_gatt_char.side_effect

    async def read(role):
        if role.uuid == uuid("2a26"):
            events.append("diagnostic")
            await release_read.wait()
        return await original_read(role)

    async def write(role, payload, **kwargs):
        if bytes(payload).startswith(b"\x13\x02"):
            events.append("control")

    async def wait(seconds):
        return True

    async def prepare(_name):
        await controller.start_notify()
        # Yield as real connection setup does after notifications.
        for _ in range(3):
            await asyncio.sleep(0)
        return controller

    controller.client.read_gatt_char.side_effect = read
    controller.client.write_gatt_char.side_effect = write
    controller._wait = wait
    coordinator._async_prepare_controller_operation = AsyncMock(side_effect=prepare)
    command = asyncio.create_task(coordinator.async_execute_controller_command(lambda c: c.lights_on()))
    try:
        for _ in range(24):
            await asyncio.sleep(0)
        assert events and events[0] == "control"
    finally:
        release_read.set()
        await command
        assert controller._device_info_task is not None
        await controller._device_info_task
    assert events == ["control", "diagnostic"]
    assert controller.session.observations["svane_firmware"] == "firmware"
    assert not coordinator._command_lock.locked() and not controller.ble_lock.locked()


@pytest.mark.parametrize("length", [21, 64])
async def test_long_opaque_memory_save_survives_cold_restore_and_exact_recall(hass, length):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_MULTI,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller("multi")
    native = controller.client
    controller._coordinator = coordinator
    coordinator._client = native
    coordinator._controller = controller
    await coordinator._async_restore_app_state(controller)
    assert native is not None
    raw = bytes(range(length))

    async def read(role):
        return raw if role.uuid == POSITION else b""

    async def wait(seconds):
        return True

    native.read_gatt_char.side_effect = read
    controller._wait = wait
    await coordinator.async_execute_controller_command(lambda c: c.program_memory(1))
    saved = await stored_app_state(coordinator)
    assert svane_multi_slots(saved)[1] == (raw, raw)
    await restart_app_state(hass, coordinator.address)
    restored = get_svane_session(hass, coordinator.address, "multi")
    restored.restore(await stored_app_state(AdjustableBedCoordinator(hass, entry), "multi"))
    assert restored.multi_slots[1] == (raw, raw)
    rebuilt = SvaneController(coordinator, profile="multi", session=restored)
    coordinator._controller = rebuilt
    rebuilt._wait = wait
    await coordinator.async_execute_controller_command(lambda c: c.preset_memory(1))
    assert [call.args[1] for call in native.write_gatt_char.call_args_list] == [raw, raw]
    coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("raw", ["", "abc", "xx", 123])
def test_opaque_memory_still_rejects_invalid_hex(raw):
    with pytest.raises(ValueError, match="nonempty opaque"):
        svane_multi_slots({"multi_slots": {"1": [raw, "00"]}})


@pytest.mark.parametrize("current", ["multi", "jmc"], indirect=True)
async def test_public_cover_low_stored_pulses_retains_ordinary_duration(current, hass, monkeypatch):
    coordinator, controller = current
    clock = [0.0]
    local = SimpleNamespace(**vars(asyncio))
    local.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local)

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)

    controller._motor_wait = advance
    legs = next(c for c in _cover_entities_for(hass, coordinator) if c.entity_description.key == "legs")
    legs.async_write_ha_state = MagicMock()
    await legs.async_open_cover()
    assert clock[0] == pytest.approx(1.0)
    assert len(written(controller)) > 1
    assert written(controller)[-1][2] in ("0000", "100000000000")
    controller.client.write_gatt_char.reset_mock()
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        pytest.raises(ServiceValidationError, match="longer than 100"),
    ):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": "bed", "motor": "legs", "direction": "up", "duration_ms": 100,
        }, blocking=True)
    assert not written(controller)
