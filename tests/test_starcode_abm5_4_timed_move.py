"""Public timed movement planning follows native held duration, not stored delay."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import _timed_move_plan, async_register_services
from tests.test_starcode_abm5_4 import make_controller
from tests.test_starcode_abm5_4_public_presets import literal_frame


async def connected_child(hass, address, delay):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=4,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Native timed movement",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX3633",
            const.CONF_STARCODE_UI_SELECTOR: "BOX3633",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
            const.CONF_MOTOR_PULSE_COUNT: 9,
            const.CONF_MOTOR_PULSE_DELAY_MS: delay,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    co = AdjustableBedCoordinator(hass, entry)
    co._client = make_controller(device="BOX3633").client

    async def disconnect():
        co._client.is_connected = False

    co._client.disconnect = AsyncMock(side_effect=disconnect)
    co._controller = StarcodeAbm5_4Controller(
        co, command_selector="BOX3633", ui_selector="BOX3633", transport_selector="BOX3633"
    )
    await co._controller.start_notify()
    await asyncio.gather(*tuple(co._controller._tasks))
    return co


@pytest.mark.parametrize("delay", [50, 100, 200])
@pytest.mark.parametrize("duration", [100, 101, 60000])
async def test_actual_public_plan_and_scheduler_override_keep_native_duration_bounds(
    hass, delay, duration
):
    co = await connected_child(hass, "AA:BB:CC:DD:EE:01", delay)
    ctrl = co.controller
    assert isinstance(ctrl, StarcodeAbm5_4Controller)
    try:
        action, count, cadence, resource = await _timed_move_plan(
            co, co, [], "back", "up", duration
        )
        assert (count, cadence) == ((duration + 99) // 100, 100)
        # Execute the real registered motor handler under the real scheduler's
        # override. The 60-second boundary validates without waiting a minute.
        with patch.object(ctrl, "_stream", new=AsyncMock()) as stream:
            await co.async_execute_controller_command(
                action, resource=resource, pulse_count=count, pulse_delay_ms=cadence
            )
        stream.assert_awaited_once_with("headUp", count * 100)
        assert (co.motor_pulse_count, co.motor_pulse_delay_ms) == (9, delay)
        assert co.entry.data[const.CONF_MOTOR_PULSE_DELAY_MS] == delay
        assert not co._command_lock.locked()
    finally:
        await co.async_shutdown()


@pytest.mark.parametrize("delay", [50, 200])
@pytest.mark.parametrize("side", ["standalone", "left", "right", "both"])
async def test_registered_timed_move_600ms_uses_actual_native_stream_and_fresh_STOP(
    hass, delay, side
):
    await async_register_services(hass)
    left = await connected_child(hass, "AA:BB:CC:DD:EE:01", delay)
    right = await connected_child(hass, "AA:BB:CC:DD:EE:02", delay)
    children = {"left": left, "right": right}
    entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "timed-native"})
    pair = PairedBedCoordinator(hass, entry, children)
    parent = left if side == "standalone" else pair
    routed = const.SIDE_BOTH if side == "standalone" else side
    loop = asyncio.get_running_loop()
    observed = {key: [] for key in children}
    for key, co in children.items():

        async def record(_role, packet, *, response, owner=key):
            observed[owner].append((loop.time(), packet.hex()))

        co.client.write_gatt_char.side_effect = record
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, routed)], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {"device_id": "native", "motor": "back", "direction": "up", "duration_ms": 600},
                blocking=True,
            )
        selected = (
            {"left"}
            if side in ("standalone", "left")
            else {"right"}
            if side == "right"
            else set(children)
        )
        for key, co in children.items():
            assert all(
                packet
                in {
                    literal_frame("BOX3633", action)
                    for action in ("headUp", "stop", "queryMassage")
                }
                for _, packet in observed[key]
            )
            # read_positions performs its source query after the command.
            writes = [
                (t, p) for t, p in observed[key] if p != literal_frame("BOX3633", "queryMassage")
            ]
            if key not in selected:
                assert writes == []
                continue
            movement = [t for t, packet in writes if packet == literal_frame("BOX3633", "headUp")]
            assert len(movement) >= 5
            assert movement[-1] - movement[0] >= 0.38
            assert writes[-1][1] == literal_frame("BOX3633", "stop")
            assert writes[-1][0] - movement[0] >= 0.55
            assert (co.motor_pulse_count, co.motor_pulse_delay_ms) == (9, delay)
            assert co.entry.data[const.CONF_MOTOR_PULSE_DELAY_MS] == delay
            assert not co._command_lock.locked()
            assert co.controller._active_release is None
    finally:
        await left.async_shutdown()
        await right.async_shutdown()
