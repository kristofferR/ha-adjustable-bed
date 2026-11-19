"""Real coordinators, scheduler, HA device/child registry and app production paths."""

from __future__ import annotations

import asyncio
import json
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
)
from custom_components.adjustable_bed.beds.keeson import betterliving2 as runtime
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    entity_runtimes,
)
from custom_components.adjustable_bed.paired_devices import async_register_children, side_identifier
from custom_components.adjustable_bed.profiles import betterliving2 as app
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock

FIXTURES = Path(__file__).parent / "fixtures/betterliving2"
TIMERS = json.loads((FIXTURES / "state_cases.json").read_text())["timer_counterexamples"]
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())
NOW = datetime(2026, 7, 14, 12, 30, 45)


@pytest.mark.parametrize("stopped", (False, True))
async def test_pause_preserves_task_cancellation_when_stop_arrives(stopped):
    event = asyncio.Event()
    waiting = asyncio.create_task(runtime.pause(60, event))
    await asyncio.sleep(0)
    if stopped:
        event.set()
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting


def data(wire="p1", layout="2", address="AA:BB:CC:DD:08:21"):
    return {
        "address": address,
        "name": "BetterLiving2",
        "bed_type": "betterliving2",
        "protocol_variant": wire,
        "product_type": layout,
        "motor_count": int(layout),
        "has_massage": True,
        "disable_angle_sensing": True,
        "motor_pulse_count": 3,
        "motor_pulse_delay_ms": app.LAYOUTS[layout].refresh_ms,
        "disconnect_after_command": False,
    }


def client_for(wire="P1", properties=("write",)):
    service, write, notify_service, notify = app.GATT[wire]
    write_char = SimpleNamespace(uuid=write, handle=1, properties=properties)
    notify_char = SimpleNamespace(uuid=notify, handle=2, properties=("notify",))
    services = []
    for uuid in dict.fromkeys((service, notify_service)):
        chars = [
            char
            for owner, char in ((service, write_char), (notify_service, notify_char))
            if owner == uuid
        ]
        services.append(
            SimpleNamespace(
                uuid=uuid,
                characteristics=chars,
                get_characteristic=lambda key, chars=chars: next(
                    (ch for ch in chars if ch.uuid == key), None
                ),
            )
        )
    client = MagicMock()
    client.is_connected = True
    client.services = services
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()

    async def disconnect():
        client.is_connected = False
        return True

    client.disconnect = AsyncMock(side_effect=disconnect)
    return client


async def attach(coordinator, wire):
    client = client_for(wire.upper())
    coordinator._client = client
    controller = await create_controller(coordinator, "betterliving2", wire, client)
    coordinator._controller = controller
    assert isinstance(controller, runtime.BetterLiving2Controller)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return controller, client


async def bed(hass, wire="p1", layout="2", address="AA:BB:CC:DD:08:21"):
    hass.config.components.add(DOMAIN)
    entry = MockConfigEntry(
        domain=DOMAIN, title="BetterLiving2", data=data(wire, layout, address), version=5
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller, client = await attach(coordinator, wire)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=coordinator.device_info
    )
    return coordinator, controller, client, device


def writes(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("wire", ("p1", "p2", "p3"))
@pytest.mark.parametrize("layout", ("2", "3"))
async def test_all_six_live_routes_startup_and_stale_notify_fence(hass, wire, layout):
    coordinator, controller, client, _ = await bed(hass, wire, layout)
    try:
        with virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            await controller.async_on_connect(
                SimpleNamespace(
                    async_start_notify=controller.start_notify, store_device_info=lambda *_: None
                )
            )
        assert writes(client) == [
            app.current_time(wire.upper(), app.Calendar.from_datetime(NOW)),
            app.alarm_query(wire.upper(), app.Calendar.from_datetime(NOW)),
        ]
        sender, callback = client.start_notify.call_args.args
        controller.on_disconnect()
        await controller.async_discover_capabilities()
        callback(sender, bytearray.fromhex("0000001e0700be1111f8"))
        assert coordinator.controller_state.get(runtime.ALARM) is None
        assert {spec.key for spec in controller.motor_control_specs} == {"head", "feet", "both"}
        assert controller.execution.hold_for(None) is None
        assert not controller.supports_single_address_pairing
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("ack", (0, 0.04, 0.4))
async def test_strict_elapsed_hold_and_drained_release(hass, ack):
    coordinator, controller, client, _ = await bed(hass)
    events = []
    try:
        with virtual_clock() as clock:

            async def write(_char, frame, **_kwargs):
                events.append((clock.now, bytes(frame)))
                await asyncio.sleep(ack)

            client.write_gatt_char.side_effect = write
            await controller.hold_control("back_up", 450)
        stop = app.command("P1", 0)
        assert all(at < 0.45 for at, frame in events if frame != stop)
        assert [frame for _, frame in events][-2:] == [stop, stop]
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("row", TIMERS, ids=lambda row: row["id"])
async def test_eight_unsafe_android_sequences_use_safe_ha_ownership(hass, row):
    coordinator, controller, client, _ = await bed(hass, layout=str(row["layout"]))
    try:
        with virtual_clock():
            if "unowned-recall" in row["id"]:
                await asyncio.gather(controller.preset_memory(1), controller.move_head_up())
                frames = writes(client)
                first_move = frames.index(app.command("P1", 1))
                assert frames[first_move - 1] == app.command("P1", 0)
                assert all(frame == app.command("P1", 1) for frame in frames[first_move:-2])
            else:
                entered = asyncio.Event()

                async def write(_char, frame, **_kwargs):
                    if frame == app.command("P1", 1):
                        entered.set()

                client.write_gatt_char.side_effect = write
                running = asyncio.create_task(controller.move_head_up())
                await entered.wait()
                program = asyncio.create_task(controller.program_memory(1))
                await asyncio.sleep(0)
                if "memory-release-clears" in row["id"]:
                    program.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await program
                    assert all(frame == app.command("P1", 1) for frame in writes(client))
                    running.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await running
                    assert writes(client)[-2:] == [app.command("P1", 0)] * 2
                else:
                    running.cancel()
                    if "movement-release-stops-program" in row["id"]:
                        running.cancel()  # A repeated stale release cannot transfer ownership.
                    with pytest.raises(asyncio.CancelledError):
                        await running
                    await program
                    frames = writes(client)
                    first_program = frames.index(app.command("P1", app.PROGRAM["P1"]["memory_1"]))
                    assert frames[first_program - 2 : first_program] == [app.command("P1", 0)] * 2
                    assert all(frame != app.command("P1", 0) for frame in frames[first_program:])
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("row", COMMANDS, ids=lambda row: row["protocol"] + ":" + row["action"])
async def test_all_83_callers_reach_actual_production_actions(hass, row):
    action = row["action"]
    layout = "3" if action.startswith("all ") else "2"
    coordinator, controller, client, _ = await bed(hass, row["protocol"].lower(), layout)
    try:
        with virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
            if action in ("head up", "head down", "foot up", "foot down"):
                fn = {
                    "head up": controller.move_head_up,
                    "head down": controller.move_head_down,
                    "foot up": controller.move_feet_up,
                    "foot down": controller.move_feet_down,
                }[action]
                await fn()
            elif action.startswith(("head+foot ", "all ")):
                await controller.combined(action.endswith("up"))
            elif action == "movement STOP/release":
                await controller.stop_all()
            elif action.endswith("recall"):
                await controller.recall(
                    {
                        "zero gravity recall": "zero_g",
                        "flat recall": "flat",
                        "memory A recall": "memory_1",
                        "memory B recall": "memory_2",
                    }[action]
                )
            elif action.startswith("program "):
                await controller.program(
                    {
                        "program zero gravity": "zero_g",
                        "program memory A": "memory_1",
                        "program memory B": "memory_2",
                    }[action]
                )
            elif action.startswith("stop active preset"):
                button = next(
                    spec
                    for spec in controller.controller_button_specs
                    if spec.key == "betterliving2_stop_preset"
                )
                await button.press_fn(controller)
            elif (
                action
                in (
                    "head massage absolute level",
                    "foot massage absolute level",
                    "massage wave absolute level",
                    "massage timer cycle",
                )
                and row["protocol"] == "P1"
            ):
                zone = {
                    "head massage absolute level": "head",
                    "foot massage absolute level": "feet",
                    "massage wave absolute level": "wave",
                    "massage timer cycle": "timer",
                }[action]
                await controller.set_level(zone, -1 if zone == "timer" else 0)
            elif action == "light off/on":
                await controller.lights_off()
                await controller.lights_on()
            elif action == "light toggle":
                await controller.lights_toggle()
            elif action == "synchronize bed current time":
                await controller.sync_clock()
            elif action in ("enable bed alarm", "disable bed alarm"):
                plan = controller.prepare_alarm(
                    enabled=action.startswith("enable"),
                    hour=7,
                    minute=30,
                    weekdays=frozenset({1, 2, 3, 4, 5}),
                    action="memory_1",
                )
                await controller.set_alarm(plan)
            elif action == "query bed alarm":
                await controller.query_alarm()
            elif action == "query massage":
                await controller.query_massage()
            else:
                word = row["opcode"]
                button = next(
                    spec
                    for spec in controller.controller_button_specs
                    if spec.key
                    == "betterliving2_massage_"
                    + next(name for name, value in app.STEP_MASSAGE.items() if value == word)
                )
                await button.press_fn(controller)
        assert writes(client), action
        if all(char in "0123456789abcdef" for char in row["bytes"]):
            assert writes(client)[0] == bytes.fromhex(row["bytes"])
    finally:
        await coordinator.async_shutdown()


async def test_gatt_dispatch_rechecks_queued_route_and_old_client(hass):
    coordinator, controller, client, _ = await bed(hass)
    await controller._wire_lock.acquire()
    task = asyncio.create_task(controller.tap(1))
    await asyncio.sleep(0)
    hass.config_entries.async_update_entry(
        coordinator.entry, data={**coordinator.entry.data, "protocol_variant": "p3"}
    )
    controller._wire_lock.release()
    try:
        with pytest.raises(ConnectionError):
            await task
        assert not writes(client)
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("wire,packet", (("p2", "ed8003071ebe11"), ("p3", "a50c0000be05071e0001")))
async def test_alarm_notify_stop_precedes_state_and_short_record_still_stops(hass, wire, packet):
    coordinator, controller, client, _ = await bed(hass, wire)
    sender, callback = client.start_notify.call_args.args
    try:
        with virtual_clock():
            callback(sender, bytearray.fromhex(packet))
            assert coordinator.controller_state.get(runtime.ALARM) is None
            await runtime.drain(controller._notify_stop)
            assert writes(client) == [app.command(wire.upper(), 0)]
            assert coordinator.controller_state[runtime.ALARM] == "selected"
            before = coordinator.controller_state.copy()
            callback(sender, bytearray.fromhex(packet[:6] if wire == "p2" else packet[:4]))
            await runtime.drain(controller._notify_stop)
            assert writes(client) == [app.command(wire.upper(), 0)] * 2
            assert coordinator.controller_state == before
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "properties,response",
    (
        (["write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], True),
    ),
)
async def test_live_property_selection_is_not_claimed_android_mode(hass, properties, response):
    coordinator, controller, client, _ = await bed(hass)
    try:
        client.services[0].characteristics[0].properties = properties
        await controller.async_discover_capabilities()
        await controller.lights_on()
        assert client.write_gatt_char.call_args.kwargs["response"] is response
        client.services[0].characteristics[0].properties = ["read"]
        with pytest.raises(ValueError):
            await controller.async_discover_capabilities()
    finally:
        await coordinator.async_shutdown()


async def test_stalled_gatt_has_finite_deadlines_and_drained_cleanup(hass):
    coordinator, controller, client, _ = await bed(hass)

    async def stalled(*_args, **_kwargs):
        await asyncio.Event().wait()

    client.write_gatt_char.side_effect = stalled
    try:
        with virtual_clock() as clock, pytest.raises(TimeoutError):
            await controller.hold_control("back_up", 200)
        assert clock.now <= 10
        assert not controller._wire_lock.locked() and not controller._operation_lock.locked()
    finally:
        await coordinator.async_shutdown()


async def test_explicit_stop_uses_fresh_event_even_without_active_motion(hass):
    coordinator, controller, client, _ = await bed(hass)
    coordinator.cancel_command.set()
    try:
        with virtual_clock():
            await controller.stop_all()
        assert writes(client) == [app.command("P1", 0)] * 2
    finally:
        await coordinator.async_shutdown()


async def pair(hass, mode="concurrent"):
    hass.config.components.add(DOMAIN)
    descriptors = [
        {"side": side, **data(wire, layout, address)}
        for side, wire, layout, address in (
            ("left", "p1", "2", "AA:BB:CC:DD:08:21"),
            ("right", "p3", "3", "AA:BB:CC:DD:08:22"),
        )
    ]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="BetterLiving2 pair",
        version=5,
        data={
            "pair_id": "betterliving2-test",
            "pair_mode": "separate_address",
            "name": "Pair",
            "bed_type": "betterliving2",
            "pair_children": descriptors,
            "pair_member_addresses": [child["address"] for child in descriptors],
        },
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    attached = {
        side: await attach(child, child.entry.data["protocol_variant"])
        for side, child in children.items()
    }
    parent = PairedBedCoordinator(hass, entry, children, connection_mode=mode)
    _async_ensure_paired_device_registry(hass, entry, parent)
    async_register_children(hass, parent)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = parent
    rows = dr.async_child_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    ids = {
        side: next(row.id for row in rows if side_identifier(parent, side) in row.identifiers)
        for side in children
    }
    return parent, attached, ids


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
async def test_native_child_target_and_conflicting_side(hass, mode):
    parent, attached, ids = await pair(hass, mode)
    await async_register_services(hass)
    try:
        with ExitStack() as stack:
            for child in parent.children.values():
                stack.enter_context(
                    patch.object(child, "async_ensure_connected", AsyncMock(return_value=True))
                )
                stack.enter_context(
                    patch.object(child, "_async_refresh_controller_auth", AsyncMock())
                )
            with virtual_clock(), patch.object(runtime.dt_util, "now", return_value=NOW):
                await hass.services.async_call(
                    DOMAIN,
                    "set_alarm",
                    {
                        "device_id": [ids["right"]],
                        "enabled": True,
                        "time": "07:30",
                        "weekdays": ["monday"],
                        "wake_action": "memory_1",
                    },
                    blocking=True,
                )
                assert not writes(attached["left"][1])
                assert writes(attached["right"][1])[0][:2] == b"\x07\x05"
                before = len(writes(attached["right"][1]))
                with pytest.raises(ServiceValidationError):
                    await hass.services.async_call(
                        DOMAIN,
                        "set_alarm",
                        {
                            "device_id": [ids["right"]],
                            "side": "left",
                            "enabled": False,
                            "time": "07:30",
                        },
                        blocking=True,
                    )
                assert len(writes(attached["right"][1])) == before
    finally:
        await parent.async_shutdown()


async def test_all_target_validation_barrier_uses_real_registry(hass):
    parent, attached, ids = await pair(hass)
    await async_register_services(hass)
    try:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "betterliving2_massage",
                {
                    "device_id": [ids["left"], ids["right"]],
                    "head": 1,
                    "feet": 2,
                },
                blocking=True,
            )
        assert not writes(attached["left"][1]) and not writes(attached["right"][1])
    finally:
        await parent.async_shutdown()


async def test_stop_during_lazy_import_cancels_original_admission(hass):
    coordinator, _, client, device = await bed(hass)
    await async_register_services(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_import(*_args):
        entered.set()
        await release.wait()

    try:
        with (
            patch(
                "custom_components.adjustable_bed.beds.keeson.betterliving2_services.async_import_modules",
                delayed_import,
            ),
            virtual_clock(),
        ):
            call = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "set_alarm",
                    {
                        "device_id": [device.id],
                        "enabled": True,
                        "time": "07:30",
                    },
                    blocking=True,
                )
            )
            await entered.wait()
            await coordinator.async_stop_command()
            boundary = len(writes(client))
            release.set()
            await call
        assert len(writes(client)) == boundary
    finally:
        await coordinator.async_shutdown()


async def test_ordinary_disconnect_keeps_entity_identity_but_revokes_session(hass):
    coordinator, controller, _, device = await bed(hass)
    registry = er.async_get(hass)
    view = next(iter(entity_runtimes(coordinator)))
    spec = next(
        spec
        for spec in controller.controller_number_specs
        if spec.key == "betterliving2_massage_head"
    )
    entity = AdjustableBedControllerNumber(view, spec)
    assert entity.unique_id is not None
    row = registry.async_get_or_create(
        "number",
        DOMAIN,
        entity.unique_id,
        config_entry=coordinator.entry,
        device_id=device.id,
        suggested_object_id="head_massage_intensity",
    )
    old_link = controller._live()
    controller.on_disconnect()
    try:
        with pytest.raises(ConnectionError):
            await controller._send(old_link, app.command("P1", 1), asyncio.Event())
        assert registry.async_get(row.entity_id).id == row.id
        assert controller.controller_number_specs
    finally:
        await coordinator.async_shutdown()
