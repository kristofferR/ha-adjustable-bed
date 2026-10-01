"""Cold public commands keep delayed app tasks outside their scheduler ticket."""

import asyncio
from contextvars import ContextVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.command_scheduler import CommandKind, current_command_context
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_abm5_4 import make_controller
from tests.test_starcode_abm5_4_public_presets import literal_frame


def cold_child(hass, address, *, modern=False):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=4,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Cold native bed",
            const.CONF_BLE_DEVICE_NAME: "Original native name",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX25" if modern else "BOX3633",
            const.CONF_STARCODE_UI_SELECTOR: "BOX25" if modern else "BOX3633",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220" if modern else "BOX3633",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


@pytest.mark.parametrize("side", ["standalone", "left", "right", "both"])
async def test_first_cold_registered_timed_move_keeps_query_after_native_STOP(
    hass, mock_coordinator_connected, side
):
    await async_register_services(hass)
    children = {
        key: cold_child(hass, address)
        for key, address in [("left", "AA:BB:CC:DD:EE:01"), ("right", "AA:BB:CC:DD:EE:02")]
    }
    for co in children.values():
        await co.async_prime_offline_controller()
        assert co.capability_controller is not None and co.controller is None
    clients = {co.address: make_controller(device="BOX3633").client for co in children.values()}
    writes = {key: [] for key in children}
    tickets = {key: [] for key in children}
    loop = asyncio.get_running_loop()
    for key, co in children.items():
        client = clients[co.address]

        async def record(_role, packet, *, response, owner=key):
            writes[owner].append((loop.time(), packet.hex()))
            context = current_command_context()
            tickets[owner].append((packet.hex(), context.intent_id if context else None))

        async def disconnect(owner=client):
            owner.is_connected = False

        client.write_gatt_char.side_effect = record
        client.disconnect = AsyncMock(side_effect=disconnect)
    pair_entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "cold-native"})
    pair = PairedBedCoordinator(hass, pair_entry, children)
    parent = children["left"] if side == "standalone" else pair
    selected_side = const.SIDE_BOTH if side == "standalone" else side
    selected = (
        {"left"}
        if side in ("standalone", "left")
        else {"right"}
        if side == "right"
        else set(children)
    )

    def device(_hass, address, *args, **kwargs):
        return MagicMock(address=address, name="Original native name")

    async def connect(_class, ble_device, *args, **kwargs):
        assert current_command_context() is not None
        return clients[ble_device.address]

    try:
        with (
            patch(
                "custom_components.adjustable_bed.coordinator.bluetooth.async_ble_device_from_address",
                device,
            ),
            patch("custom_components.adjustable_bed.coordinator.establish_connection", connect),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(parent, selected_side)], []),
            ),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {"device_id": "cold", "motor": "back", "direction": "up", "duration_ms": 800},
                blocking=True,
            )
            for key, co in children.items():
                if key not in selected:
                    assert writes[key] == [] and co.controller is None
                    continue
                ctrl = co.controller
                assert isinstance(ctrl, StarcodeAbm5_4Controller)
                await asyncio.wait_for(asyncio.gather(*tuple(ctrl._tasks)), 3)
                frames = [packet for _, packet in writes[key]]
                movement = [t for t, p in writes[key] if p == literal_frame("BOX3633", "headUp")]
                assert len(movement) >= 7 and movement[-1] - movement[0] >= 0.58
                assert frames.index(literal_frame("BOX3633", "stop")) < frames.index(
                    literal_frame("BOX3633", "queryMassage")
                )
                movement_ticket = next(
                    ticket
                    for packet, ticket in tickets[key]
                    if packet == literal_frame("BOX3633", "headUp")
                )
                query_tickets = {
                    ticket
                    for packet, ticket in tickets[key]
                    if packet == literal_frame("BOX3633", "queryMassage")
                    and ticket != movement_ticket
                }
                assert None not in query_tickets and query_tickets
                history = {
                    record.intent_id: record for record in co._command_scheduler.recent_records
                }
                assert movement_ticket in history and query_tickets <= history.keys()
                assert all(
                    history[movement_ticket].finished_at <= history[ticket].started_at
                    for ticket in query_tickets
                )
                assert ctrl._active_release is None and not ctrl._tasks
                assert not co._command_lock.locked()
    finally:
        for co in children.values():
            await co.async_shutdown()


async def test_spawn_from_active_command_keeps_other_context_and_genuine_nested_reentry(hass):
    co = cold_child(hass, "AA:BB:CC:DD:EE:03")
    co._client = make_controller(device="BOX3633").client

    async def disconnect():
        co._client.is_connected = False

    co._client.disconnect = AsyncMock(side_effect=disconnect)
    ctrl = StarcodeAbm5_4Controller(
        co, command_selector="BOX3633", ui_selector="BOX3633", transport_selector="BOX3633"
    )
    co._controller = ctrl
    sentinel = ContextVar("test_trace_context", default="missing")
    seen = []
    spawned = asyncio.Event()

    async def delayed():
        seen.append(("background", current_command_context(), sentinel.get()))
        spawned.set()

    async def nested():
        seen.append(("nested", current_command_context(), sentinel.get()))

    async def outer(_ctrl):
        context = current_command_context()
        assert context is not None
        token = sentinel.set("preserved")
        try:
            ctrl._spawn(delayed)
            await asyncio.wait_for(spawned.wait(), 1)
            await co._async_schedule_command_operation(
                nested,
                resource=None,
                resources=None,
                kind=CommandKind.COMMAND,
                cancel_running=False,
            )
            assert seen[-1][1] is context
            assert current_command_context() is context
        finally:
            sentinel.reset(token)

    try:
        await co.async_execute_controller_command(outer)
        assert seen[0] == ("background", None, "preserved")
        assert seen[1][0] == "nested" and seen[1][2] == "preserved"
    finally:
        await co.async_shutdown()


@pytest.mark.parametrize("shutdown_queued", [False, True])
async def test_native_white_callback_inside_movement_queues_own_ticket_and_drains(
    hass, shutdown_queued
):
    co = cold_child(hass, "AA:BB:CC:DD:EE:04", modern=True)
    co._client = make_controller(device="BOX1220").client

    async def disconnect():
        co._client.is_connected = False

    co._client.disconnect = AsyncMock(side_effect=disconnect)
    ctrl = StarcodeAbm5_4Controller(
        co, command_selector="BOX25", ui_selector="BOX25", transport_selector="BOX1220"
    )
    co._controller = ctrl
    ctrl._ready = True
    queued, entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    inherited_context = []
    frames = []
    real_execute = co.async_execute_controller_command

    async def execute(action, **kwargs):
        if kwargs.get("cancel_running") is False:
            inherited_context.append(current_command_context())
            queued.set()
        await real_execute(action, **kwargs)

    async def record(_role, packet, *, response):
        frames.append(packet.hex())
        if packet.hex() == literal_frame("BOX25", "headUp") and not entered.is_set():
            assert current_command_context() is not None
            entered.set()
            ctrl._notification(
                co.client,
                ctrl._session_generation,
                co.client.services[0].characteristics[1],
                bytearray.fromhex("a50b0000006404030300000000002110"),
            )

    async def wait(_seconds, event):
        await release.wait()
        assert not event.is_set()
        return False

    async def movement(controller):
        await controller.hold_control("head_up", 800)

    co.client.write_gatt_char.side_effect = record
    user = None
    try:
        with patch.object(co, "async_execute_controller_command", execute):
            if shutdown_queued:
                with patch.object(ctrl, "_wait", wait):
                    user = asyncio.create_task(execute(movement))
                    await asyncio.wait_for(queued.wait(), 2)
                    assert inherited_context == [None]
                    assert not user.done()
                    assert frames == [literal_frame("BOX25", "headUp")]
                    await ctrl.stop_notify()
                    assert not ctrl._tasks
                    assert not user.done()
                    release.set()
                    await asyncio.wait_for(user, 2)
                assert literal_frame("BOX25", "change2White") not in frames
                # Explicit notification stop invalidates the session; the
                # coordinator owns subsequent disconnect/STOP handling.
            else:
                user = asyncio.create_task(execute(movement))
                await asyncio.wait_for(queued.wait(), 2)
                assert inherited_context == [None]
                await asyncio.wait_for(user, 2)
                await asyncio.wait_for(asyncio.gather(*tuple(ctrl._tasks)), 7)
                stop = frames.index(literal_frame("BOX25", "stop"))
                white = frames.index(literal_frame("BOX25", "change2White"))
                assert stop < white
                assert frames.count(literal_frame("BOX25", "change2White")) >= 45
                assert frames[-1] == literal_frame("BOX25", "change2White")
                assert not ctrl._tasks and ctrl._active_release is None
    finally:
        release.set()
        if user is not None and not user.done():
            user.cancel()
            await asyncio.gather(user, return_exceptions=True)
        await co.async_shutdown()


@pytest.mark.parametrize("terminal", ["stop", "shutdown"])
async def test_cold_command_terminal_invalidates_queued_query_without_leaking_tasks(
    hass, mock_coordinator_connected, terminal
):
    await async_register_services(hass)
    co = cold_child(hass, "AA:BB:CC:DD:EE:05")
    await co.async_prime_offline_controller()
    client = make_controller(device="BOX3633").client
    entered = asyncio.Event()
    frames = []

    async def record(_role, packet, *, response):
        frames.append(packet.hex())
        if packet.hex() == literal_frame("BOX3633", "headUp"):
            entered.set()

    async def disconnect():
        client.is_connected = False

    client.write_gatt_char.side_effect = record
    client.disconnect = AsyncMock(side_effect=disconnect)
    user = None
    try:
        with (
            patch(
                "custom_components.adjustable_bed.coordinator.establish_connection",
                AsyncMock(return_value=client),
            ),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(co, const.SIDE_BOTH)], []),
            ),
        ):
            user = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {"device_id": "cold", "motor": "back", "direction": "up", "duration_ms": 1200},
                    blocking=True,
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.sleep(0.55)
            assert co._command_scheduler.has_pending
            assert literal_frame("BOX3633", "queryMassage") not in frames
            ctrl = co.controller
            assert isinstance(ctrl, StarcodeAbm5_4Controller)
            if terminal == "stop":
                await co.async_stop_command()
                await asyncio.wait_for(user, 2)
                assert literal_frame("BOX3633", "stop") in frames
                await co.async_shutdown()
            else:
                await co.async_shutdown()
                await asyncio.wait_for(asyncio.gather(user, return_exceptions=True), 2)
            assert not ctrl._tasks and ctrl._active_release is None
            assert not co._command_scheduler.has_pending
            assert co._command_scheduler._worker is None
            assert not co._command_lock.locked()
    finally:
        if user is not None and not user.done():
            user.cancel()
            await asyncio.gather(user, return_exceptions=True)
        await co.async_shutdown()
