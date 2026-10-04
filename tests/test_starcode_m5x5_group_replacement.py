"""Registered replacement actions settle the former group's native cleanup."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.adjustable_bed.const import CONF_STARCODE_LIFT_ENTRIES, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_accessory_group import action_frame, group, target


@pytest.mark.parametrize("replacement", ["up", "down", "flat"])
async def test_registered_replacement_waits_for_prior_cleanup(
    hass: HomeAssistant, replacement: str
) -> None:
    members = group(hass)
    main = members[0]
    for member in members:
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member.async_stop_command = AdjustableBedCoordinator.async_stop_command.__get__(member)
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
    main.entry.mock_state(hass, ConfigEntryState.LOADED)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=main.entry.entry_id, identifiers={(DOMAIN, main.address)}
    )
    await async_register_services(hass)
    entered = asyncio.Event()
    delays = 0
    writes: list[tuple[str, bytes]] = []
    for member in members:

        async def write(command: bytes, *, owner=member, **kwargs: object) -> None:
            writes.append((owner.address, command))

        member.controller.write_command.side_effect = write

    async def delay(seconds: float) -> None:
        nonlocal delays
        assert seconds == 1.6
        delays += 1
        if delays == 1:
            entered.set()
            await asyncio.Event().wait()

    async def invoke(action: str) -> None:
        await hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: device.id, "action": action},
            blocking=True,
        )

    old = None
    try:
        with patch(
            "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", delay
        ):
            old = asyncio.create_task(invoke("flat"))
            async with asyncio.timeout(3):
                await entered.wait()
                start = len(writes)
                await invoke(replacement)
                with pytest.raises(asyncio.CancelledError):
                    await old
        after = writes[start:]
        # All four old-session releases precede any replacement interrupt/admission.
        assert {
            address for address, frame in after[:4] if frame == bytes.fromhex("5a010310300fa5")
        } == {member.address for member in members}
        action = {"up": "union_up", "down": "union_down", "flat": "flat"}[replacement]
        for lift in members[1:]:
            assert (lift.address, action_frame(lift.controller, action)) in after[4:]
            if replacement != "flat":
                assert after[-4:].count((lift.address, bytes.fromhex("5a010310300fa5"))) == 1
        assert delays == (2 if replacement == "flat" else 1)
        assert all(not member._command_scheduler.has_pending for member in members)
    finally:
        if old is not None:
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
        for member in members:
            await member._command_scheduler.async_shutdown()


@pytest.mark.parametrize("cancel_waiter", [False, True, "stop", "ordinary_stop"])
@pytest.mark.parametrize("shared_group", [False, True])
async def test_waiting_replacements_preserve_cleanup_and_shared_member_ownership(
    hass: HomeAssistant, cancel_waiter: bool | str, shared_group: bool
) -> None:
    members = group(hass)
    main = members[0]
    successor = target(hass, 10, "cb25") if shared_group else main
    if shared_group:
        hass.config_entries.async_update_entry(
            successor.entry,
            data={**successor.entry.data, CONF_STARCODE_LIFT_ENTRIES: [members[1].entry.entry_id]},
        )
    runtimes = tuple(dict.fromkeys((*members, successor)))
    for member in runtimes:
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member.async_stop_command = AdjustableBedCoordinator.async_stop_command.__get__(member)
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
        member.entry.mock_state(hass, ConfigEntryState.LOADED)
    devices = {
        member.entry.entry_id: dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=member.entry.entry_id, identifiers={(DOMAIN, member.address)}
        )
        .id
        for member in (main, successor)
    }
    await async_register_services(hass)
    delayed = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    writes: list[tuple[str, bytes]] = []
    for member in runtimes:

        async def write(command: bytes, *, owner=member, **kwargs: object) -> None:
            if delayed.is_set() and owner is main and command == bytes.fromhex("5a010310300fa5"):
                cleanup_started.set()
                await release_cleanup.wait()
            writes.append((owner.address, command))

        member.controller.write_command.side_effect = write

    async def delay(seconds: float) -> None:
        assert seconds == 1.6
        delayed.set()
        await asyncio.Event().wait()

    async def invoke(runtime: AdjustableBedCoordinator, action: str) -> None:
        await hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: devices[runtime.entry.entry_id], "action": action},
            blocking=True,
        )

    tasks: list[asyncio.Task[None]] = []
    yield_to_loop = asyncio.sleep
    try:
        with patch(
            "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", delay
        ):
            async with asyncio.timeout(3):
                old = asyncio.create_task(invoke(main, "flat"))
                tasks.append(old)
                await delayed.wait()
                start = len(writes)
                waiting = asyncio.create_task(invoke(successor, "up"))
                tasks.append(waiting)
                await cleanup_started.wait()
                if cancel_waiter is True:
                    waiting.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await waiting
                    release_cleanup.set()
                elif cancel_waiter == "stop":
                    counter = main._cancel_counter
                    stopping = asyncio.create_task(invoke(main, "stop"))
                    tasks.append(stopping)
                    while main._cancel_counter == counter:
                        await yield_to_loop(0)
                    release_cleanup.set()
                    await stopping
                    with pytest.raises(asyncio.CancelledError):
                        await waiting
                elif cancel_waiter == "ordinary_stop":
                    await members[1].async_stop_command()
                    release_cleanup.set()
                    with pytest.raises(asyncio.CancelledError):
                        await waiting
                else:
                    latest = asyncio.create_task(invoke(successor, "down"))
                    tasks.append(latest)
                    release_cleanup.set()
                    results = await asyncio.gather(waiting, latest, return_exceptions=True)
                    assert results[1] is None
                    assert results[0] is None or isinstance(results[0], asyncio.CancelledError)
                with pytest.raises(asyncio.CancelledError):
                    await old
        after = writes[start:]
        stops = set(after if cancel_waiter in ("stop", "ordinary_stop") else after[:4])
        assert stops == {(member.address, bytes.fromhex("5a010310300fa5")) for member in members}
        if cancel_waiter:
            assert all(frame == bytes.fromhex("5a010310300fa5") for _, frame in after)
            assert len(after) == (
                8 if cancel_waiter == "stop" else 5 if cancel_waiter == "ordinary_stop" else 4
            )
        else:
            assert (members[1].address, bytes.fromhex("5a0103103045a5")) in after[4:]
        assert not any(frame == bytes.fromhex("5a0103103046a5") for _, frame in after)
        assert all(not member._command_scheduler.has_pending for member in runtimes)
    finally:
        release_cleanup.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for member in runtimes:
            await member._command_scheduler.async_shutdown()


@pytest.mark.parametrize("stop_target", ["group", "main", "lift"])
async def test_stop_during_connection_preflight_admits_no_movement(
    hass: HomeAssistant, stop_target: str
) -> None:
    members = group(hass)
    main = members[0]
    for member in members:
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member.async_stop_command = AdjustableBedCoordinator.async_stop_command.__get__(member)
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()
    main.entry.mock_state(hass, ConfigEntryState.LOADED)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=main.entry.entry_id, identifiers={(DOMAIN, main.address)}
    )
    await async_register_services(hass)
    connecting = asyncio.Event()
    attempts = 0

    async def connect(**kwargs: object) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            connecting.set()
            await asyncio.Event().wait()
        return True

    main.async_ensure_connected.side_effect = connect
    running = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: device.id, "action": "up"},
            blocking=True,
        )
    )
    try:
        async with asyncio.timeout(3):
            await connecting.wait()
            if stop_target == "group":
                await hass.services.async_call(
                    DOMAIN,
                    "starcode_move_lifts",
                    {CONF_DEVICE_ID: device.id, "action": "stop"},
                    blocking=True,
                )
            else:
                await members[0 if stop_target == "main" else 1].async_stop_command()
            with pytest.raises(asyncio.CancelledError):
                await running
        assert all(
            call.args[0] == bytes.fromhex("5a010310300fa5")
            for member in members
            for call in member.controller.write_command.await_args_list
        )
        assert any(member.controller.write_command.await_count for member in members)
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        for member in members:
            await member._command_scheduler.async_shutdown()
