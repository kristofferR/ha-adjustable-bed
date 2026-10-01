"""Main plus three independent lifts, readiness and delayed-flat cancellation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.starcode_m5x5 import StarcodeM5X5Controller
from custom_components.adjustable_bed.const import (
    BED_TYPE_STARCODE_M5X5,
    CONF_BED_TYPE,
    CONF_STARCODE_DEVICE_NAME,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.starcode_accessory_group import (
    cancel_group_operations,
    interrupt_conflicting_group,
    run_group,
    validate_lift_entries,
)


def target(hass: HomeAssistant, index: int, profile: str) -> AdjustableBedCoordinator:
    name = {
        "cb25": "STAR252201123456",
        "f23": "STAR254205123456",
        "kneading": "STAR255402123456",
        "elevate": "ELEVATE123456",
    }[profile]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=f"AA:00:00:00:00:{index:02X}",
        data={
            CONF_ADDRESS: f"AA:00:00:00:00:{index:02X}",
            CONF_NAME: name,
            CONF_BED_TYPE: BED_TYPE_STARCODE_M5X5,
            CONF_STARCODE_M5X5_PROFILE: profile,
            CONF_STARCODE_DEVICE_NAME: name,
            CONF_STARCODE_LIFT_ENTRIES: [],
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = MagicMock(is_connected=True)
    controller = StarcodeM5X5Controller(coordinator, profile=profile)
    controller._ready = True
    controller.dialect = "star"
    controller.write_command = AsyncMock()
    coordinator._controller = controller
    coordinator.async_ensure_connected = AsyncMock(return_value=True)

    async def execute(fn, **kwargs):
        await fn(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    coordinator.async_stop_command = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return coordinator


def group(
    hass: HomeAssistant, main_profile: str = "cb25", lift_profile: str = "elevate"
) -> tuple[AdjustableBedCoordinator, ...]:
    targets = tuple(
        target(hass, i, profile)
        for i, profile in enumerate((main_profile, lift_profile, "f23", "kneading"), 1)
    )
    main = targets[0]
    hass.config_entries.async_update_entry(
        main.entry,
        data={
            **main.entry.data,
            CONF_STARCODE_LIFT_ENTRIES: [t.entry.entry_id for t in targets[1:]],
        },
    )
    return targets


@pytest.mark.parametrize("profile", ["cb25", "f23", "kneading", "elevate"])
async def test_all_four_bed_classes_in_main_and_lift_slots(
    hass: HomeAssistant, profile: str
) -> None:
    main, *lifts = group(hass, profile, lift_profile=profile)
    assert (
        len(
            validate_lift_entries(
                hass,
                main.entry.data,
                [t.entry.entry_id for t in lifts],
                main_entry_id=main.entry.entry_id,
            )
        )
        == 3
    )
    await run_group(main, "up")
    assert main.controller.write_command.await_args_list[0].args[0] == bytes.fromhex(
        "5a010310304fa5" if profile == "elevate" else "5a010310301fa5"
    )
    for lift in lifts:
        expected = "5a0103103044a5" if lift.controller.profile == "elevate" else "5a010310300ca5"
        assert any(
            call.args[0] == bytes.fromhex(expected)
            for call in lift.controller.write_command.await_args_list
        )
    assert all(t.async_stop_command.await_count == 1 for t in (main, *lifts))


async def test_selection_duplicates_addresses_and_limit(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    ids = [t.entry.entry_id for t in lifts]
    for invalid in (ids + [ids[0]], [ids[0], ids[0]], [main.entry.entry_id], ["missing"]):
        with pytest.raises(ValueError):
            validate_lift_entries(hass, main.entry.data, invalid, main_entry_id=main.entry.entry_id)
    hass.config_entries.async_update_entry(
        lifts[0].entry, data={**lifts[0].entry.data, CONF_ADDRESS: main.address}
    )
    with pytest.raises(ValueError, match="distinct Bluetooth"):
        validate_lift_entries(hass, main.entry.data, ids)


async def test_unrelated_and_unready_rejected_before_movement(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    lifts[1].async_ensure_connected.return_value = False
    with pytest.raises(ConnectionError):
        await run_group(main, "up")
    assert main.async_stop_command.await_count == 1
    assert lifts[0].async_stop_command.await_count == 1
    assert lifts[1].async_stop_command.await_count == 0
    assert all(t.controller.write_command.await_count == 0 for t in (main, *lifts))
    hass.config_entries.async_update_entry(
        lifts[0].entry, data={**lifts[0].entry.data, CONF_BED_TYPE: "desk"}
    )
    with pytest.raises(ValueError, match="bedding profile"):
        validate_lift_entries(hass, main.entry.data, [lifts[0].entry.entry_id])


async def test_ready_identity_does_not_substitute_transport(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    lifts[2].controller._ready = False
    with pytest.raises(ConnectionError, match="not ready"):
        await run_group(main, "up")
    assert all(t.async_stop_command.await_count == 1 for t in (main, *lifts))
    assert all(t.controller.write_command.await_count == 0 for t in (main, *lifts))


async def test_flat_orders_main_then_exact_delay_then_lifts_without_extra_stop(
    hass: HomeAssistant,
) -> None:
    main, *lifts = group(hass)
    events = []
    for member in (main, *lifts):

        async def write(command, *, _member=member, **kwargs):
            events.append((_member.address, command))

        member.controller.write_command.side_effect = write

    async def delay(seconds):
        events.append(("delay", seconds))

    with patch(
        "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", side_effect=delay
    ):
        await run_group(main, "flat")
    delay_index = events.index(("delay", 1.6))
    assert any(
        address == main.address and frame == bytes.fromhex("5a0103103010a5")
        for address, frame in events[:delay_index]
    )
    assert not any(
        address == lifts[0].address and frame == bytes.fromhex("5a0103103046a5")
        for address, frame in events[:delay_index]
    )
    assert (lifts[0].address, bytes.fromhex("5a0103103046a5")) in events[delay_index:]
    assert all(t.async_stop_command.await_count == 0 for t in (main, *lifts))


@pytest.mark.parametrize("reason", ["stop", "selection", "unload"])
async def test_owned_delay_is_cancelled_and_all_admitted_targets_stop(
    hass: HomeAssistant, reason: str
) -> None:
    main, *lifts = group(hass)
    entered = asyncio.Event()
    wait = asyncio.Event()

    async def delay(seconds):
        assert seconds == 1.6
        entered.set()
        await wait.wait()

    with patch(
        "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep", side_effect=delay
    ):
        running = asyncio.create_task(run_group(main, "flat"))
        await entered.wait()
        if reason == "selection":
            hass.config_entries.async_update_entry(
                main.entry, data={**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: []}
            )
            wait.set()
        else:
            cancel_group_operations(
                hass, main.entry.entry_id if reason == "stop" else lifts[0].entry.entry_id
            )
        with pytest.raises(asyncio.CancelledError):
            await running
    assert all(t.async_stop_command.await_count == 1 for t in (main, *lifts))
    assert not any(
        call.args[0] == bytes.fromhex("5a0103103046a5")
        for call in lifts[0].controller.write_command.await_args_list
    )


async def test_member_failure_cancels_sibling_and_cleans_all_targets(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    started = asyncio.Event()
    ended = asyncio.Event()

    async def first(fn, **kwargs):
        if fn.__name__ == "_up":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                ended.set()

    async def second(fn, **kwargs):
        if fn.__name__ == "_up":
            await started.wait()
            raise ConnectionError("second lift failed")

    lifts[0].async_execute_controller_command.side_effect = first
    lifts[1].async_execute_controller_command.side_effect = second
    with pytest.raises(ExceptionGroup):
        await run_group(main, "up")
    assert ended.is_set()
    assert all(t.async_stop_command.await_count == 1 for t in (main, *lifts))


async def test_ordinary_motion_interrupts_conflicting_group_only(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    await interrupt_conflicting_group(main)
    assert main.controller.write_command.await_count == 0
    assert lifts[0].controller.write_command.await_args.args[0] == bytes.fromhex("5a010310304fa5")
    assert lifts[1].controller.write_command.await_args.args[0] == bytes.fromhex("5a010310301fa5")
    for member in (main, *lifts):
        member.controller.write_command.reset_mock()
    await interrupt_conflicting_group(lifts[0])
    assert main.controller.write_command.await_args.args[0] == bytes.fromhex("5a010310301fa5")
    assert all(t.controller.write_command.await_count == 0 for t in lifts)


async def test_concurrent_main_and_lift_commands_settle_through_real_schedulers(
    hass: HomeAssistant,
) -> None:
    main, *lifts = group(hass)
    for member in (main, *lifts):
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._async_finish_controller_operation = AsyncMock()

    async def move(controller):
        await controller.move_head_up()

    async with asyncio.timeout(2):
        results = await asyncio.gather(
            main.async_execute_controller_command(move, read_positions_after_operation=False),
            lifts[0].async_execute_controller_command(move, read_positions_after_operation=False),
            return_exceptions=True,
        )
    assert all(
        result is None or isinstance(result, asyncio.CancelledError) for result in results
    ), results
    assert all(not member._command_scheduler.has_pending for member in (main, *lifts))
    # Both conflicting requests may be replaced before a held write is admitted.
    # The drained queues must still admit and release a subsequent solo movement.
    async with asyncio.timeout(2):
        await main.async_execute_controller_command(move, read_positions_after_operation=False)
    assert main.controller.packet("head_up") in {
        call.args[0] for call in main.controller.write_command.await_args_list
    }
    assert bytes.fromhex("5a010310300fa5") in {
        call.args[0] for call in main.controller.write_command.await_args_list
    }
    for member in (main, *lifts):
        await member._command_scheduler.async_shutdown()


async def test_delayed_flat_holds_quick_handoff_connections(hass: HomeAssistant) -> None:
    main, *lifts = group(hass)
    for member in (main, *lifts):
        member._disconnect_after_command = True
        member.async_execute_controller_command = (
            AdjustableBedCoordinator.async_execute_controller_command.__get__(member)
        )
        member._async_prepare_controller_operation = AsyncMock(return_value=member.controller)
        member._client.stop_notify = AsyncMock()

        async def disconnect(m=member):
            m._client.is_connected = False

        member._client.disconnect = AsyncMock(side_effect=disconnect)
    try:
        await run_group(main, "flat")
        for member in (main, *lifts):
            member._client.disconnect.assert_not_awaited()
            assert member._command_connection_holds == 0
        for lift in lifts:
            assert lift.controller.packet("flat") in {
                call.args[0] for call in lift.controller.write_command.await_args_list
            }
    finally:
        for member in (main, *lifts):
            member._cancel_disconnect_timer()
            await member._command_scheduler.async_shutdown()


@pytest.mark.parametrize("target_index", [0, 1])
@pytest.mark.parametrize("change", ["lost", "client", "controller", "generation"])
async def test_delayed_flat_aborts_after_any_retained_session_changes(
    hass: HomeAssistant,
    target_index: int,
    change: str,
) -> None:
    main, *lifts = group(hass)
    retained_lift_controllers = tuple(lift.controller for lift in lifts)
    changing = (main, *lifts)[target_index]

    async def delay(seconds):
        assert seconds == 1.6
        if change == "lost":
            changing._client.is_connected = False
            changing._controller = None
        elif change == "client":
            changing._client = MagicMock(is_connected=True)
        elif change == "controller":
            changing._controller = StarcodeM5X5Controller(changing, profile="cb25")
            changing._controller._ready = True
        else:
            changing.controller._generation += 1

    with (
        patch(
            "custom_components.adjustable_bed.starcode_accessory_group.asyncio.sleep",
            side_effect=delay,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await run_group(main, "flat")
    for controller in retained_lift_controllers:
        assert controller.packet("flat") not in {
            call.args[0] for call in controller.write_command.await_args_list
        }
    assert all(member._command_connection_holds == 0 for member in (main, *lifts))
    assert all(member.async_stop_command.await_count == 1 for member in (main, *lifts))
