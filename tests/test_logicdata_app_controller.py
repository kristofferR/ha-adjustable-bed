"""Lifecycle, gesture cleanup, and state routing for both MOTIONrelax apps."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import logicdata_app_protocol as protocol
from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController


@pytest.fixture
def coordinator():
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    coordinator.async_execute_controller_command = AsyncMock()
    services = {}
    characteristics = {}
    for transport in protocol.TRANSPORTS.values():
        uuids = {transport.write_uuid, transport.notify_uuid, transport.rename_uuid} - {None}
        chars = [MagicMock(uuid=uuid, properties=["write", "notify"]) for uuid in uuids]
        service = MagicMock(uuid=transport.service_uuid, characteristics=chars)
        services[transport.service_uuid] = service
        characteristics.update({char.uuid: char for char in chars})
    coordinator.client.services.get_service.side_effect = services.get
    coordinator.client.services.get_characteristic.side_effect = characteristics.get
    coordinator.client.services.__iter__.side_effect = lambda: iter(services.values())
    return coordinator


def controller(coordinator, **overrides):
    options = {
        "profile": "phone",
        "command_family": "p1",
        "layout": "standard_2",
        "transport": "t1",
        "has_light": True,
        "has_massage": True,
    }
    options.update(overrides)
    return LogicdataAppController(coordinator, **options)


def packets(coordinator):
    return [call.args[1] for call in coordinator.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("profile", ["phone", "tablet"])
@pytest.mark.parametrize(("family", "layout"), [("p1", "standard_2"), ("p2", "middle")])
async def test_motion_has_terminal_touch_repeat_and_fresh_p1_release(
    coordinator, profile, family, layout
):
    bed = controller(coordinator, profile=profile, command_family=family, layout=layout)
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.move_back_up()
    expected = protocol.motion_command(family, layout, "back", True)
    assert packets(coordinator) == [expected] * 3 + [protocol.P1_RELEASE]


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_motion_cancel_stops_refresh_and_releases(coordinator, task_cancel):
    bed = controller(coordinator)
    entered = asyncio.Event()

    async def hold(seconds, cancel_event=None):
        if cancel_event is not None:
            assert not cancel_event.is_set()
            return True
        entered.set()
        if task_cancel:
            await asyncio.Event().wait()
        coordinator.cancel_command.set()
        return False

    with patch.object(bed, "_pause", side_effect=hold):
        task = asyncio.create_task(bed.move_back_up())
        await entered.wait()
        if task_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    assert packets(coordinator) == [bytes.fromhex("f1f1010101037e"), protocol.P1_RELEASE]


@pytest.mark.parametrize("action", ["movement", "hold", "repeat"])
async def test_slow_write_cancellation_stops_overdue_repeats(coordinator, action):
    bed = controller(coordinator, command_family="p2", layout="middle")

    async def slow_write(*args, **kwargs):
        await asyncio.sleep(0.12)
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = slow_write
    if action == "movement":
        await bed.move_back_up()
        assert packets(coordinator)[1:] == [protocol.P1_RELEASE]
    elif action == "hold":
        await bed.hold_preset("flat", 1000)
        assert packets(coordinator)[1:] == [protocol.P1_RELEASE]
    else:
        await bed.write_command(b"test", repeat_count=5)
        assert packets(coordinator) == [b"test"]


@pytest.mark.parametrize("seconds", [0, -0.1])
async def test_overdue_pause_honors_explicit_cleanup_event(coordinator, seconds):
    bed = controller(coordinator)
    coordinator.cancel_command.set()
    assert not await bed._pause(seconds)
    cleanup = asyncio.Event()
    assert await bed._pause(seconds, cleanup)
    cleanup.set()
    assert not await bed._pause(seconds, cleanup)


async def test_p2_flat_failure_still_releases(coordinator):
    bed = controller(coordinator, command_family="p2", layout="middle")
    coordinator.client.write_gatt_char.side_effect = [ConnectionError("failed motion"), None]
    with (
        patch.object(bed, "_pause", new=AsyncMock(return_value=True)),
        pytest.raises(ConnectionError, match="failed motion"),
    ):
        await bed.preset_flat()
    assert packets(coordinator)[-1] == protocol.P1_RELEASE


@pytest.mark.parametrize("profile", ["phone", "tablet"])
async def test_light_preserves_both_release_families(coordinator, profile):
    bed = controller(coordinator, profile=profile)
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.lights_toggle()
    assert packets(coordinator) == [
        bytes.fromhex("f1f10f000f7e"),
        protocol.P1_RELEASE,
        protocol.P2_RELEASE,
        protocol.P1_RELEASE,
    ]


@pytest.mark.parametrize("profile", ["phone", "tablet"])
async def test_massage_mode_cleanup_is_app_specific(coordinator, profile):
    bed = controller(coordinator, profile=profile)
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.massage_mode_step()
    assert packets(coordinator) == [protocol.MASSAGE_MODE] + (
        [protocol.P2_RELEASE, protocol.P1_RELEASE] if profile == "phone" else []
    )


async def test_memory_saves_three_copies_without_release(coordinator):
    bed = controller(coordinator, command_family="p2", layout="middle")
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.program_memory(2)
    assert packets(coordinator) == [bytes.fromhex("f1f10c0200000e7e")] * 3
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await bed.program_memory(3)
    assert packets(coordinator) == []


@pytest.mark.parametrize("profile", ["phone", "tablet"])
async def test_startup_awaits_exact_app_query_and_clock_burst(coordinator, profile):
    bed = controller(coordinator, profile=profile)
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.start_notify()
    assert packets(coordinator)[:6] == [
        packet for _, packet in protocol.startup_schedule(profile, "p1")
    ]
    assert len(packets(coordinator)) == (8 if profile == "phone" else 6)
    assert bed._initialized
    await bed.start_notify()
    assert coordinator.client.start_notify.await_count == 1
    await bed.stop_notify()
    assert not bed._initialized


async def test_t2_only_skips_burst_but_copresent_ready_profile_bootstraps(coordinator):
    for ready in (False, True):
        coordinator.client.write_gatt_char.reset_mock()
        original_lookup = coordinator.client.services.get_service.side_effect
        if not ready:
            coordinator.client.services.get_service.side_effect = (
                lambda uuid, lookup=original_lookup: (
                    lookup(uuid) if uuid == protocol.TRANSPORTS["t2"].service_uuid else None
                )
            )
        bed = controller(coordinator, profile="tablet", transport="t2")
        with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
            await bed.start_notify()
        assert len(packets(coordinator)) == (6 if ready else 0)
        assert all(
            call.args[0] == protocol.TRANSPORTS["t2"].write_uuid
            for call in coordinator.client.write_gatt_char.call_args_list
        )
        coordinator.client.services.get_service.side_effect = original_lookup


async def test_failed_startup_unsubscribes_and_retry_runs_full_burst(coordinator):
    bed = controller(coordinator, profile="tablet")
    coordinator.client.write_gatt_char.side_effect = ConnectionError("query failed")
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        with pytest.raises(ConnectionError):
            await bed.start_notify()
        assert not bed._initialized
        assert bed._subscribed == []
        coordinator.client.stop_notify.assert_awaited_once()
        coordinator.client.write_gatt_char.reset_mock(side_effect=True)
        await bed.start_notify()
    assert len(packets(coordinator)) == 6
    assert bed._initialized


async def test_auto_rejects_ambiguous_transport_before_writes(coordinator):
    bed = controller(coordinator, transport="auto")
    with pytest.raises(ValueError, match="ambiguous"):
        await bed.async_discover_capabilities()
    assert packets(coordinator) == []


async def test_runtime_characteristic_write_mode(coordinator):
    bed = controller(coordinator)
    char = coordinator.client.services.get_characteristic(bed.control_characteristic_uuid)
    char.properties = ["write-without-response"]
    await bed.write_command(protocol.P1_RELEASE)
    coordinator.client.write_gatt_char.assert_awaited_once_with(
        bed.control_characteristic_uuid, protocol.P1_RELEASE, response=False
    )


async def test_known_family_mismatch_rejects_motion_but_allows_cleanup(coordinator):
    bed = controller(coordinator)
    sender = MagicMock(uuid=protocol.TRANSPORTS["t1"].notify_uuid)
    bed._notification_handler(sender, bytearray.fromhex("f2f2110001"))
    with (
        patch.object(bed, "_pause", new=AsyncMock(return_value=True)),
        pytest.raises(ValueError, match="different packet family"),
    ):
        await bed.move_back_up()
    assert packets(coordinator) == [protocol.P1_RELEASE]


async def test_layout_axes_and_massage_are_not_inferred_from_motor_count(coordinator):
    bed = controller(coordinator, layout="standard_3_hi_low")
    coordinator.motor_count = 4
    assert [spec.key for spec in bed.motor_control_specs] == ["back", "legs", "bed_height"]
    current = controller(coordinator, layout="standard_3_hi_low")
    with patch.object(current, "move_axis", new=AsyncMock()) as move:
        await bed.motor_control_specs[-1].open_fn(current)
    move.assert_awaited_once_with("bed_height", True)
    with pytest.raises(ValueError):
        await bed.move_head_up()
    assert packets(coordinator) == []
    p2 = controller(coordinator, command_family="p2", layout="middle")
    assert not p2.supports_massage
    assert not p2.supports_clock_alarm
    assert p2.massage_intensity_zones == []


def test_split_state_maps_raw_levels_and_keeps_light_contract(coordinator):
    bed = controller(coordinator, layout="split_series")
    sender = MagicMock(uuid=protocol.TRANSPORTS["t1"].notify_uuid)
    for unknown in (b"", b"\xf2\xf2\x06", b"\x01\x02\x03"):
        bed._notification_handler(sender, bytearray(unknown))
    coordinator.handle_controller_state_updates.assert_not_called()
    bed._notification_handler(sender, bytearray.fromhex("aaaa06000400030040"))
    assert bed.get_massage_state() == {"head_intensity": 3, "right_intensity": 2}
    assert bed.get_light_state() == {"is_on": True}
    coordinator.handle_controller_state_updates.assert_called_with(
        {"head_intensity": 3, "right_intensity": 2, "under_bed_lights_on": True}
    )


async def test_clock_response_uses_coordinator_and_tablet_has_no_writer(coordinator):
    bed = controller(coordinator)
    sender = MagicMock(uuid=protocol.TRANSPORTS["t1"].notify_uuid)
    bed._notification_handler(sender, bytearray.fromhex("f2f250000000"))
    task = bed._clock_task
    assert task is not None
    await task
    coordinator.async_execute_controller_command.assert_awaited_once()
    callback = coordinator.async_execute_controller_command.call_args.args[0]
    assert coordinator.async_execute_controller_command.call_args.kwargs == {
        "cancel_running": False,
        "skip_disconnect": True,
    }
    await callback(bed)
    assert packets(coordinator)[0][:4] == bytes.fromhex("f1f15007")
    tablet = controller(coordinator, profile="tablet")
    tablet._notification_handler(sender, bytearray.fromhex("f2f250000000"))
    assert tablet._clock_task is None
    with pytest.raises(NotImplementedError):
        await tablet._sync_clock()


@pytest.mark.parametrize("profile", ["phone", "tablet"])
async def test_rename_targets_name_characteristic_with_app_repeats(coordinator, profile):
    bed = controller(coordinator, profile=profile, transport="t3")
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.rename_device("BED")
    assert packets(coordinator) == [bytes.fromhex("01fc0703424544")] * (
        1 if profile == "phone" else 2
    )
    assert all(
        call.args[0] == protocol.TRANSPORTS["t3"].rename_uuid
        for call in coordinator.client.write_gatt_char.call_args_list
    )


async def test_alarm_phone_only_and_invalids_do_not_write(coordinator):
    bed = controller(coordinator)
    await bed.configure_clock_alarm(
        enabled=True,
        weekdays=(0, 2, 4),
        hour=6,
        minute=30,
        preset="memory_1",
        head_level=2,
        foot_level=3,
    )
    assert packets(coordinator) == [bytes.fromhex("f1f1510801012a061e030203b17e")]
    coordinator.client.write_gatt_char.reset_mock()
    for options in ({"preset": "yoga"}, {"weekdays": (7,)}, {"hour": 24}):
        kwargs = {"enabled": True, "weekdays": (), "hour": 6, "minute": 0, "preset": "flat"}
        kwargs.update(options)
        with pytest.raises(ValueError):
            await bed.configure_clock_alarm(**kwargs)
    tablet = controller(coordinator, profile="tablet")
    with pytest.raises(NotImplementedError):
        await tablet.configure_clock_alarm(
            enabled=False, weekdays=(), hour=0, minute=0, preset="flat"
        )
    assert packets(coordinator) == []


@pytest.mark.parametrize("operation", ["preset", "repeat"])
async def test_scheduled_writes_absorb_ble_latency(coordinator, operation):
    bed = controller(coordinator)
    now = 0.0
    clock = MagicMock()
    clock.time.side_effect = lambda: now
    waits = []

    async def slow_write(*args, **kwargs):
        nonlocal now
        now += 0.04

    async def pause(seconds, cancel_event=None):
        nonlocal now
        waits.append(seconds)
        now += seconds
        return True

    coordinator.client.write_gatt_char.side_effect = slow_write
    with (
        patch(
            "custom_components.adjustable_bed.beds.logicdata_app.asyncio.get_running_loop",
            return_value=clock,
        ),
        patch.object(bed, "_pause", side_effect=pause),
    ):
        if operation == "preset":
            await bed.preset_flat()
        else:
            await bed.write_command(protocol.P1_RELEASE, repeat_count=2, repeat_delay_ms=100)
    assert waits == pytest.approx([0.06])


async def test_tablet_t3_subscribes_name_after_queries_without_clock(coordinator):
    bed = controller(coordinator, profile="tablet", transport="t3")
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.start_notify()
    assert [call.args[0] for call in coordinator.client.start_notify.call_args_list] == [
        protocol.TRANSPORTS["t3"].notify_uuid,
        protocol.TRANSPORTS["t3"].rename_uuid,
    ]
    assert len(packets(coordinator)) == 6


@pytest.mark.parametrize(("preset", "writes"), [("flat", 6), ("memory_1", 3), ("memory_2", 3)])
async def test_p2_held_presets_use_own_repeat_cadence(coordinator, preset, writes):
    bed = controller(coordinator, command_family="p2", layout="middle")
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.hold_preset(preset, 500)
    assert len(packets(coordinator)) == writes + 1
    assert packets(coordinator)[-1] == protocol.P1_RELEASE
    assert len(set(packets(coordinator)[:-1])) == 1


async def test_cancel_p2_memory_hold_prevents_refresh_and_releases(coordinator):
    bed = controller(coordinator, command_family="p2", layout="middle")

    async def pause(seconds, cancel_event=None):
        if cancel_event is None:
            coordinator.cancel_command.set()
            return False
        assert not cancel_event.is_set()
        return True

    with patch.object(bed, "_pause", side_effect=pause):
        await bed.hold_preset("memory_1", 1000)
    assert packets(coordinator) == [bytes.fromhex("f1f10b0200000d7e"), protocol.P1_RELEASE]


@pytest.mark.parametrize(
    ("preset", "duration"), [("yoga", 1000), ("flat", 0), ("memory_1", 100), ("flat", 60001)]
)
async def test_invalid_held_preset_never_writes(coordinator, preset, duration):
    bed = controller(coordinator, command_family="p2", layout="middle")
    with pytest.raises(ValueError):
        await bed.hold_preset(preset, duration)
    assert packets(coordinator) == []


@pytest.mark.parametrize("profile", ["phone", "tablet"])
async def test_early_family_mismatch_keeps_startup_and_sensor_available(coordinator, profile):
    bed = controller(coordinator, profile=profile)
    sender = MagicMock(uuid=protocol.TRANSPORTS["t1"].notify_uuid)

    async def mismatch_on_write(*args, **kwargs):
        bed._notification_handler(sender, bytearray.fromhex("f2f2110001"))

    coordinator.client.write_gatt_char.side_effect = mismatch_on_write
    with patch.object(bed, "_pause", new=AsyncMock(return_value=True)):
        await bed.start_notify()
        assert bed._initialized
        assert bed._family_matches is False
        assert packets(coordinator)[:6] == [
            packet for _, packet in protocol.startup_schedule(profile, "p1")
        ]
        assert len(packets(coordinator)) == (8 if profile == "phone" else 6)
        coordinator.client.stop_notify.assert_not_awaited()
        coordinator.client.write_gatt_char.reset_mock()
        with pytest.raises(ValueError, match="different packet family"):
            await bed.move_back_up()
        assert packets(coordinator) == [protocol.P1_RELEASE]


@pytest.mark.parametrize("profile", ["phone", "tablet"])
@pytest.mark.parametrize(("family", "layout"), [("p1", "standard_2"), ("p2", "middle")])
@pytest.mark.parametrize(("duration_ms", "release_ms"), [(100, 100), (1000, 1000), (1050, 1100)])
async def test_timed_motion_releases_at_planned_endpoint(
    coordinator, profile, family, layout, duration_ms, release_ms
):
    bed = controller(coordinator, profile=profile, command_family=family, layout=layout)
    coordinator.motor_pulse_count = bed.timed_move_repeat_count(duration_ms, 100)
    now = 0.0
    clock = MagicMock()
    clock.time.side_effect = lambda: now
    writes = []

    async def write(uuid, packet, **kwargs):
        writes.append((now, packet))

    async def pause(seconds, cancel_event=None):
        nonlocal now
        now += seconds
        return True

    coordinator.client.write_gatt_char.side_effect = write
    with (
        patch(
            "custom_components.adjustable_bed.beds.logicdata_app.asyncio.get_running_loop",
            return_value=clock,
        ),
        patch.object(bed, "_pause", side_effect=pause),
    ):
        await bed.move_back_up()
    movement = protocol.motion_command(family, layout, "back", True)
    assert [packet for _, packet in writes] == (
        [movement] * (release_ms // 100) + [protocol.P1_RELEASE]
    )
    assert [when for when, _ in writes] == pytest.approx(
        [tick / 10 for tick in range(release_ms // 100 + 1)]
    )
