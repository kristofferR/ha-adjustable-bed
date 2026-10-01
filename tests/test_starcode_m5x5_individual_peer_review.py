"""Healthy standalone controls do not depend on grouped peers being online."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.starcode_m5x5 import StarcodeM5X5Controller
from custom_components.adjustable_bed.const import CONF_STARCODE_M5X5_PROFILE, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.starcode_accessory_group import _tasks
from tests.test_starcode_accessory_group import group
from tests.test_starcode_m5x5 import make_controller


@pytest.mark.parametrize("role", ["main", "lift"])
@pytest.mark.parametrize("failure", ["unloaded", "reconnect", "unready", "write"])
@pytest.mark.parametrize("action", ["back", "legs", "flat", "memory"])
async def test_public_individual_control_ignores_unavailable_grouped_peer(
    hass: HomeAssistant, enable_custom_integrations: None, role: str, failure: str, action: str
) -> None:
    members = group(hass)
    selected = members[0 if role == "main" else 2]
    peer = members[1 if role == "main" else 0]
    entry = selected.entry
    hass.config_entries.async_update_entry(entry, version=4)

    async def connect(runtime: AdjustableBedCoordinator) -> bool:
        profile = str(runtime.entry.data[CONF_STARCODE_M5X5_PROFILE])
        runtime._client = make_controller(hass, profile, "star").client
        runtime._client.disconnect = AsyncMock()
        runtime._controller = StarcodeM5X5Controller(runtime, profile=profile)
        runtime._controller.write_command = AsyncMock()
        await runtime._controller.start_notify()
        return True

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
        patch.object(AdjustableBedCoordinator, "_schedule_controller_state_refresh"),
        patch("custom_components.adjustable_bed.PLATFORMS", [Platform.BUTTON]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    members = [hass.data[DOMAIN][member.entry.entry_id] for member in members]
    source = members[0 if role == "main" else 2]
    peer = members[1 if role == "main" else 0]
    for member in members:
        member._async_finish_controller_operation = AsyncMock()
    writes = source.controller.write_command
    writes.reset_mock()
    if failure == "unloaded":
        hass.data[DOMAIN].pop(peer.entry.entry_id)
    elif failure == "reconnect":
        peer._client.is_connected = False
        peer.async_ensure_connected = AsyncMock(return_value=False)
    elif failure == "unready":
        peer.controller._ready = False
    else:
        peer.async_execute_controller_command = AsyncMock(
            side_effect=ConnectionError("peer write unavailable")
        )
    device_id = (
        dr.async_get(hass)
        .async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, source.address)})
        .id
    )
    started = asyncio.Event()

    async def retained() -> None:
        started.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(retained())
    await started.wait()
    for member in members:
        _tasks(hass).setdefault(member.entry.entry_id, set()).add(pending)
    try:
        if action in ("back", "legs"):
            await hass.services.async_call(
                DOMAIN,
                "timed_move",
                {CONF_DEVICE_ID: device_id, "motor": action, "direction": "up", "duration_ms": 100},
                blocking=True,
            )
        elif action == "memory":
            await hass.services.async_call(
                DOMAIN, "goto_preset", {CONF_DEVICE_ID: device_id, "preset": 1}, blocking=True
            )
        else:
            flat = next(
                row
                for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
                if row.translation_key == "preset_flat"
            )
            await hass.services.async_call(
                "button", "press", {"entity_id": flat.entity_id}, blocking=True
            )
        with pytest.raises(asyncio.CancelledError):
            await pending
        expected = {"back": "00", "legs": "02", "flat": "10", "memory": "1a"}[action]
        assert bytes.fromhex(f"5a01031030{expected}a5") in {
            call.args[0] for call in writes.await_args_list
        }
        stop = next(
            call
            for call in writes.await_args_list
            if call.args[0] == bytes.fromhex("5a010310300fa5")
        )
        assert not stop.kwargs["cancel_event"].is_set()
        if role == "main":
            for healthy_peer in members[2:]:
                assert any(
                    call.args[0] == bytes.fromhex("5a010310301fa5")
                    for call in healthy_peer.controller.write_command.await_args_list
                )
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("role", ["main", "lift"])
async def test_public_individual_motion_cancels_actual_retained_group(
    hass: HomeAssistant, role: str
) -> None:
    members = group(hass)
    main = members[0]
    source = members[0 if role == "main" else 2]
    for member in members:
        member.entry.mock_state(hass, ConfigEntryState.LOADED)
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member.async_stop_command = AdjustableBedCoordinator.async_stop_command.__get__(member)
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
    devices = {
        member.entry.entry_id: dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=member.entry.entry_id, identifiers={(DOMAIN, member.address)}
        )
        .id
        for member in (main, source)
    }
    await async_register_services(hass)
    delayed = asyncio.Event()

    async def delay(seconds: float) -> None:
        assert seconds == 1.6
        delayed.set()
        await asyncio.Event().wait()

    old = None
    try:
        with patch(
            "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", delay
        ):
            old = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "starcode_move_lifts",
                    {CONF_DEVICE_ID: devices[main.entry.entry_id], "action": "flat"},
                    blocking=True,
                )
            )
            async with asyncio.timeout(3):
                await delayed.wait()
                for member in members:
                    member.controller.write_command.reset_mock()
                await hass.services.async_call(
                    DOMAIN,
                    "timed_move",
                    {
                        CONF_DEVICE_ID: devices[source.entry.entry_id],
                        "motor": "back",
                        "direction": "up",
                        "duration_ms": 100,
                    },
                    blocking=True,
                )
                with pytest.raises(asyncio.CancelledError):
                    await old
        assert bytes.fromhex("5a0103103000a5") in {
            call.args[0] for call in source.controller.write_command.await_args_list
        }
        for lift in members[1:]:
            assert lift.controller.packet("flat") not in {
                call.args[0] for call in lift.controller.write_command.await_args_list
            }
    finally:
        if old is not None:
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
        for member in members:
            await member._command_scheduler.async_shutdown()


@pytest.mark.parametrize(
    "boundary", ["caller", "stop", "group_stop", "unload", "selection", "replace"]
)
@pytest.mark.parametrize("role", ["main", "lift"])
async def test_pending_individual_admission_preserves_cleanup_and_stop(
    hass: HomeAssistant, boundary: str, role: str
) -> None:
    members = group(hass)
    main = members[0]
    source = members[0 if role == "main" else 2]
    for member in members:
        member.entry.mock_state(hass, ConfigEntryState.LOADED)
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member.async_stop_command = AdjustableBedCoordinator.async_stop_command.__get__(member)
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
    devices = {
        member.entry.entry_id: dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=member.entry.entry_id, identifiers={(DOMAIN, member.address)}
        )
        .id
        for member in (main, source)
    }
    await async_register_services(hass)
    delayed = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    frames: list[tuple[str, bytes]] = []
    for member in members:

        async def write(command: bytes, *, owner=member, **kwargs: object) -> None:
            if delayed.is_set() and owner is source and command == bytes.fromhex("5a010310300fa5"):
                cleanup_started.set()
                await release_cleanup.wait()
            frames.append((owner.address, command))

        member.controller.write_command.side_effect = write

    async def delay(seconds: float) -> None:
        assert seconds == 1.6
        delayed.set()
        await asyncio.Event().wait()

    async def move(direction: str) -> None:
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                CONF_DEVICE_ID: devices[source.entry.entry_id],
                "motor": "back",
                "direction": direction,
                "duration_ms": 100,
            },
            blocking=True,
        )

    tasks: list[asyncio.Task[object]] = []
    stopping: asyncio.Task[object] | None = None
    latest: asyncio.Task[None] | None = None
    yield_to_loop = asyncio.sleep
    try:
        with patch(
            "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", delay
        ):
            async with asyncio.timeout(3):
                old = asyncio.create_task(
                    hass.services.async_call(
                        DOMAIN,
                        "starcode_move_lifts",
                        {CONF_DEVICE_ID: devices[main.entry.entry_id], "action": "flat"},
                        blocking=True,
                    )
                )
                tasks.append(old)
                await delayed.wait()
                start = len(frames)
                waiting = asyncio.create_task(move("up"))
                tasks.append(waiting)
                await cleanup_started.wait()
                if boundary == "caller":
                    waiting.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await waiting
                elif boundary in ("stop", "group_stop"):
                    counter = source._cancel_counter
                    stopping = asyncio.create_task(
                        source.async_stop_command()
                        if boundary == "stop"
                        else hass.services.async_call(
                            DOMAIN,
                            "starcode_move_lifts",
                            {CONF_DEVICE_ID: devices[main.entry.entry_id], "action": "stop"},
                            blocking=True,
                        )
                    )
                    tasks.append(stopping)
                    while source._cancel_counter == counter:
                        await yield_to_loop(0)
                elif boundary == "unload":
                    from custom_components.adjustable_bed.starcode_accessory_group import (
                        cancel_group_operations,
                    )

                    cancel_group_operations(hass, source.entry.entry_id)
                    hass.data[DOMAIN].pop(source.entry.entry_id)
                elif boundary == "selection":
                    from custom_components.adjustable_bed.const import CONF_STARCODE_LIFT_ENTRIES

                    hass.config_entries.async_update_entry(
                        main.entry, data={**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: []}
                    )
                else:
                    latest = asyncio.create_task(move("down"))
                    tasks.append(latest)
                    await yield_to_loop(0)
                release_cleanup.set()
                if boundary in ("stop", "group_stop"):
                    assert stopping is not None
                    await stopping
                if boundary == "replace":
                    assert latest is not None
                    await latest
                if boundary != "caller":
                    with pytest.raises(asyncio.CancelledError):
                        await waiting
                with pytest.raises(asyncio.CancelledError):
                    await old
        after = frames[start:]
        assert (source.address, bytes.fromhex("5a0103103000a5")) not in after
        if boundary == "replace":
            assert (source.address, bytes.fromhex("5a0103103001a5")) in after
        else:
            assert all(frame == bytes.fromhex("5a010310300fa5") for _, frame in after)
        assert {
            address for address, frame in after if frame == bytes.fromhex("5a010310300fa5")
        } == {member.address for member in members}
    finally:
        release_cleanup.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for member in members:
            await member._command_scheduler.async_shutdown()


@pytest.mark.parametrize("role", ["main", "lift"])
async def test_individual_caller_cancellation_is_not_a_peer_failure(
    hass: HomeAssistant, role: str
) -> None:
    members = group(hass)
    source = members[0 if role == "main" else 2]
    peer = members[1 if role == "main" else 0]
    source.entry.mock_state(hass, ConfigEntryState.LOADED)
    source.async_execute_controller_command = (
        AdjustableBedCoordinator.async_execute_controller_command.__get__(source)
    )
    source._async_prepare_controller_operation = AsyncMock(return_value=source.controller)
    source._async_finish_controller_operation = AsyncMock()
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry.entry_id, identifiers={(DOMAIN, source.address)}
    )
    await async_register_services(hass)
    entered = asyncio.Event()

    async def blocked(*args: object, **kwargs: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    peer.async_execute_controller_command.side_effect = blocked
    running = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "timed_move",
            {CONF_DEVICE_ID: device.id, "motor": "back", "direction": "up", "duration_ms": 100},
            blocking=True,
        )
    )
    try:
        async with asyncio.timeout(3):
            await entered.wait()
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
        assert bytes.fromhex("5a0103103000a5") not in {
            call.args[0] for call in source.controller.write_command.await_args_list
        }
        stops = [
            call
            for call in source.controller.write_command.await_args_list
            if call.args[0] == bytes.fromhex("5a010310300fa5")
        ]
        assert stops and all(not call.kwargs["cancel_event"].is_set() for call in stops)
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await source._command_scheduler.async_shutdown()
