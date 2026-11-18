"""Focused public-route checks for the five accepted implementation findings."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.ultramatic import controller as module
from custom_components.adjustable_bed.beds.ultramatic import services as alarm_services
from custom_components.adjustable_bed.beds.ultramatic.controller import UltramaticController
from custom_components.adjustable_bed.beds.ultramatic.state import SIDES
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
)
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data
from custom_components.adjustable_bed.profiles import ultramatic as app
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_ultramatic_runtime import (
    ALARM_REPORT,
    BED,
    connected,
    entry,
    make_client,
    runtime,  # noqa: F401 - imported pytest fixture
    writes,
)

MATCHING = bytes.fromhex("ed8003017f0106300001027f0106300001")
SET = {"operation": "set", "time": "21:09:00", "days": 2, "wake": "zero_g", "enabled": False}


def native_pair(hass, inner):
    data = build_single_address_pair_entry_data(dict(inner.entry.data), name="Ultramatic sides")
    pair_entry = MockConfigEntry(domain=DOMAIN, data=data)
    pair_entry.add_to_hass(hass)
    return SingleAddressPairedCoordinator(hass, pair_entry, inner)


async def alarm(hass, operation, **fields):
    await hass.services.async_call(
        DOMAIN,
        "ultramatic_alarm",
        {"device_id": ["bed"], "operation": operation, **fields},
        blocking=True,
    )


@pytest.mark.parametrize(
    ("report", "side", "display"),
    [
        (ALARM_REPORT, "both", "06:05"),  # Existing unequal A/B fixture: display fallback only.
        (bytes.fromhex("ed8003027f0106300001027f0106300001"), "left", "06:05"),
        (bytes.fromhex("ed8003017f011a2f0001027f011a2f0001"), "both", "20:35"),
        (bytes.fromhex("ed80030100010630000102000106300001"), "both", "06:05"),
        (bytes.fromhex("ed8003017f0406300001027f0406300001"), "both", "06:30"),
        (bytes.fromhex("ed8003017f0106300002027f0106300002"), "both", "06:30"),
        (bytes.fromhex("ed8003007f0106300001007f0106300001"), "both", "06:30"),
    ],
    ids=[
        "different",
        "missing-A",
        "invalid-BCD",
        "zero-days",
        "unsupported-type",
        "invalid-enabled",
        "standalone-display",
    ],
)
async def test_toggle_never_turns_display_fallback_or_invalid_records_into_writes(
    runtime,  # noqa: F811 - pytest fixture
    report,
    side,
    display,
):
    hass, coord, client = runtime
    parent = native_pair(hass, coord) if side == "left" else coord
    key = SIDES["A" if side == "left" else "AB"].alarm
    spec = next(s for s in coord.controller.controller_state_sensor_specs if s.state_key == key)
    sensor = AdjustableBedControllerStateSensor(coord, spec)
    callback = client.start_notify.await_args.args[1]
    with (
        patch.object(module.dt_util, "now", return_value=datetime(2026, 11, 18, 6, 5)),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, side)], []),
        ),
    ):
        callback(None, bytearray(MATCHING))  # A later invalid report must remove old permission.
        callback(None, bytearray(report))
        assert sensor.native_value == display
        with pytest.raises((ServiceValidationError, ValueError)):
            await alarm(hass, "toggle")
    assert writes(client) == []
    assert sensor.native_value == display


@pytest.mark.parametrize("side,selector", [("both", 0), ("left", 1), ("right", 2)])
async def test_valid_matching_report_toggle_uses_exact_current_physical_side(
    runtime,  # noqa: F811 - pytest fixture
    side,
    selector,
):
    hass, coord, client = runtime
    parent = coord if side == "both" else native_pair(hass, coord)
    client.start_notify.await_args.args[1](None, bytearray(MATCHING))
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, side)], []),
        ),
        virtual_clock(),
    ):
        await alarm(hass, "toggle")
    frame = bytes.fromhex("07057f0106300000") + bytes([selector])
    assert writes(client) == [frame] * 2 + [app.QUERY_ALARM] * 3


@pytest.mark.parametrize("operation", ["set", "toggle", "query"])
async def test_native_parent_both_alarm_dispatches_one_combined_plan(
    runtime,  # noqa: F811 - pytest fixture
    operation,
):
    hass, coord, client = runtime
    parent = native_pair(hass, coord)
    if operation == "toggle":
        client.start_notify.await_args.args[1](None, bytearray(MATCHING))
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, "both")], []),
        ),
        virtual_clock(),
    ):
        await alarm(
            hass,
            operation,
            **(
                {key: value for key, value in SET.items() if key != "operation"}
                if operation == "set"
                else {}
            ),
        )
    frame = bytes.fromhex("070502022109000000" if operation == "set" else "07057f010630000000")
    assert writes(client) == (
        [app.QUERY_ALARM] * 2 if operation == "query" else [frame] * 2 + [app.QUERY_ALARM] * 3
    )


async def test_native_parent_both_toggle_rejects_unequal_reports_before_preflight(runtime):  # noqa: F811 - pytest fixture
    hass, coord, client = runtime
    parent = native_pair(hass, coord)
    client.start_notify.await_args.args[1](None, bytearray(ALARM_REPORT))
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, "both")], []),
        ),
        pytest.raises((ServiceValidationError, ValueError), match="Refresh alarms"),
    ):
        await alarm(hass, "toggle")
    assert writes(client) == []
    coord.async_ensure_connected.assert_not_awaited()


async def test_disconnect_and_stale_report_cannot_authorize_registered_toggle(runtime):  # noqa: F811 - pytest fixture
    hass, coord, client = runtime
    callback = client.start_notify.await_args.args[1]
    callback(None, bytearray(MATCHING))
    coord.controller.on_disconnect()
    callback(None, bytearray(MATCHING))
    with pytest.raises((ConnectionError, ServiceValidationError, ValueError)):
        await alarm(hass, "toggle")
    assert writes(client) == []


@pytest.mark.usefixtures("mock_coordinator_connected")
@pytest.mark.parametrize("native", [False, True], ids=["standalone", "native-right"])
@pytest.mark.parametrize("operation", ["set", "query"])
async def test_idle_registered_set_and_query_connect_actual_owner(
    hass, mock_bleak_client, native, operation
):
    roles = make_client().services
    mock_bleak_client.services.__iter__ = lambda _self: iter(roles)
    mock_bleak_client.services.__len__ = lambda _self: len(roles)
    coord = AdjustableBedCoordinator(hass, entry(hass))
    await coord.async_prime_offline_controller()
    assert coord.controller is None
    assert isinstance(coord.capability_controller, UltramaticController)
    parent, side = (native_pair(hass, coord), "right") if native else (coord, "both")
    hass.data.setdefault(DOMAIN, {})[coord.entry.entry_id] = parent
    await async_register_services(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(parent, side)], []),
            ),
            patch.object(module.dt_util, "now", return_value=datetime(2026, 11, 18, 6, 5)),
            virtual_clock(),
        ):
            fields = (
                {key: value for key, value in SET.items() if key != "operation"}
                if operation == "set"
                else {}
            )
            await alarm(hass, operation, **fields)
        assert coord.is_connected and isinstance(coord.controller, UltramaticController)
        tail = (
            [bytes.fromhex("0705020221090000") + bytes([2 if native else 0])] * 2
            + [app.QUERY_ALARM] * 3
            if operation == "set"
            else [app.QUERY_ALARM] * 2
        )
        assert writes(mock_bleak_client) == [
            bytes.fromhex("070426111803060500"),
            app.QUERY_MASSAGE,
            app.QUERY_MASSAGE,
            *tail,
        ]
    finally:
        await coord.async_shutdown()


@pytest.mark.parametrize("reason", ["unknown", "offline-toggle", "stop", "replacement", "route"])
async def test_registered_alarm_rejects_unknown_offline_and_changed_owner_before_command_writes(
    runtime,  # noqa: F811 - pytest fixture
    reason,
):
    hass, coord, client = runtime
    original = alarm_services._preflight_capability

    async def changed(*args, **kwargs):
        result = await original(*args, **kwargs)
        if reason == "stop":
            coord._command_scheduler.finish_stop(coord._command_scheduler.request_stop())
        elif reason == "replacement":
            coord._controller = UltramaticController(coord)
        elif reason == "route":
            coord.controller._default_side = "B"
        return result

    with ExitStack() as stack:
        if reason == "unknown":
            stack.enter_context(
                patch(
                    "custom_components.adjustable_bed.services._resolve_sided_targets",
                    return_value=([(coord, "both")], ["unknown"]),
                )
            )
        if reason == "offline-toggle":
            coord.controller.on_disconnect()
            coord._offline_controller, coord._controller = coord.controller, None
        stack.enter_context(
            patch.object(alarm_services, "_preflight_capability", side_effect=changed)
        )
        with pytest.raises((ServiceValidationError, ConnectionError, ValueError)):
            await alarm(
                hass,
                "toggle" if reason == "offline-toggle" else "set",
                **(
                    {key: value for key, value in SET.items() if key != "operation"}
                    if reason != "offline-toggle"
                    else {}
                ),
            )
    assert writes(client) == []
    coord.async_ensure_connected.assert_not_awaited()


@pytest.fixture
async def paired_runtime(runtime):  # noqa: F811 - pytest fixture
    hass, left, left_client = runtime
    right, right_client = await connected(hass, address="AA:BB:CC:DD:EE:77", selector=2)
    pair_entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "ultramatic-review"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, pair_entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    try:
        with (
            patch.object(right, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(right, "_async_refresh_controller_auth", AsyncMock()),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(pair, "both")], []),
            ),
        ):
            yield hass, pair, left, right, left_client, right_client
    finally:
        await right.async_shutdown()


@pytest.mark.parametrize("operation", ["set", "toggle", "query"])
async def test_concurrent_parent_both_alarm_owns_only_its_sibling_generation_advances(
    paired_runtime, operation
):
    hass, _, left, right, left_client, right_client = paired_runtime
    for client in (left_client, right_client):
        client.start_notify.await_args.args[1](None, bytearray(MATCHING))
    with virtual_clock():
        await alarm(
            hass,
            operation,
            **(
                {key: value for key, value in SET.items() if key != "operation"}
                if operation == "set"
                else {}
            ),
        )
    for client, selector in ((left_client, 0), (right_client, 2)):
        frame = (
            bytes.fromhex("0705020221090000")
            if operation == "set"
            else bytes.fromhex("07057f0106300000")
        ) + bytes([selector])
        assert writes(client) == (
            [app.QUERY_ALARM] * 2 if operation == "query" else [frame] * 2 + [app.QUERY_ALARM] * 3
        )


@pytest.mark.parametrize(
    "race", ["stop", "command", "replacement", "roster", "route", "pair-generation"]
)
async def test_concurrent_alarm_barrier_rechecks_every_owner_after_first_sequence_await(
    paired_runtime, race
):
    hass, pair, left, right, left_client, right_client = paired_runtime
    original = module._pause
    injected = False

    async def interleave(cancel, seconds):
        nonlocal injected
        if not injected:
            injected = True
            if race == "stop":
                right._command_scheduler.finish_stop(right._command_scheduler.request_stop())
            elif race == "command":
                right.controller._operation_generation += 1
            elif race == "replacement":
                right._controller = UltramaticController(right, 2)
            elif race == "roster":
                pair._children["right"] = left
            elif race == "route":
                right.controller._default_side = "A"
            else:
                pair._admission.bump("right", {"*"})
        return await original(cancel, seconds)

    with (
        patch.object(module, "_pause", side_effect=interleave),
        virtual_clock(),
        pytest.raises((HomeAssistantError, ConnectionError, ValueError)),
    ):
        await alarm(hass, "set", **{key: value for key, value in SET.items() if key != "operation"})
    assert injected
    assert all(
        frame == app.control("STOP")
        for client in (left_client, right_client)
        for frame in writes(client)
    )


async def test_alarm_queued_at_gatt_lock_rechecks_all_targets_before_delivery(paired_runtime):
    hass, _, left, right, left_client, right_client = paired_runtime
    original = UltramaticController._write
    queued = {left.controller: asyncio.Event(), right.controller: asyncio.Event()}
    enter_gatt = asyncio.Event()

    async def observe(controller, link, frame, cancel, **kwargs):
        if frame != app.control("STOP"):
            queued[controller].set()
            await enter_gatt.wait()
        await original(controller, link, frame, cancel, **kwargs)

    with patch.object(UltramaticController, "_write", new=observe), virtual_clock():
        task = asyncio.create_task(
            alarm(hass, "set", **{key: value for key, value in SET.items() if key != "operation"})
        )
        ready = asyncio.gather(*(event.wait() for event in queued.values()))
        try:
            done, _pending = await asyncio.wait({task, ready}, return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                await task  # Surface admission failures before taking locks needed by cleanup.
                pytest.fail("Alarm service finished before reaching the queued-write barrier")
            await ready
            async with left.controller.ble_lock, right.controller.ble_lock:
                enter_gatt.set()
                await asyncio.sleep(0)
                right.controller._operation_generation += 1
            with pytest.raises((HomeAssistantError, ConnectionError, ValueError)):
                await task
        finally:
            enter_gatt.set()
            if not ready.done():
                ready.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, ready, return_exceptions=True)
    assert all(
        frame == app.control("STOP")
        for client in (left_client, right_client)
        for frame in writes(client)
    )


@pytest.mark.parametrize("action", ["memory", "light", "set", "query"])
async def test_sequential_finite_both_connects_operates_and_releases_one_receiver_at_a_time(
    paired_runtime, action
):
    hass, pair, left, right, left_client, right_client = paired_runtime
    pair._adopt_connection_mode("sequential")
    order = []

    async def connect(coordinator, client, other, label):
        assert not other.is_connected
        client.is_connected = True
        coordinator._client = client
        coordinator._controller = await create_controller(coordinator, BED, "auto", client)
        await coordinator.controller.async_discover_capabilities()
        await coordinator.controller.start_notify()
        order.append(label)
        return True

    async def connect_left():
        return await connect(left, left_client, right_client, "left")

    async def connect_right():
        return await connect(right, right_client, left_client, "right")

    with (
        patch.object(left, "async_connect", AsyncMock(side_effect=connect_left)),
        patch.object(right, "async_connect", AsyncMock(side_effect=connect_right)),
        virtual_clock(),
    ):
        if action == "memory":
            await hass.services.async_call(
                DOMAIN, "goto_preset", {"device_id": ["pair"], "preset": 1}, blocking=True
            )
        elif action == "light":
            await pair.async_execute_controller_command(
                lambda c: c.action("LIGHT"), side="both", resource="*"
            )
        else:
            try:
                await alarm(
                    hass,
                    action,
                    **(
                        {key: value for key, value in SET.items() if key != "operation"}
                        if action == "set"
                        else {}
                    ),
                )
            except PairedSideError as error:
                if len(error.side_errors) == 1:
                    side, inner = next(iter(error.side_errors.items()))
                    inner.add_note(f"Ultramatic sequential {action}, physical side {side}")
                    raise inner from error
                raise
    assert order == ["left", "right"]
    assert not left_client.is_connected and not right_client.is_connected
    for client, selector in ((left_client, 0), (right_client, 2)):
        if action in ("memory", "light"):
            control = app.control(
                "M1" if action == "memory" else "LIGHT", "B" if selector else "AB"
            )
            assert writes(client) == [control] * (3 if action == "memory" else 1) + [
                app.control("STOP")
            ]
        else:
            frame = bytes.fromhex("0705020221090000") + bytes([selector])
            assert writes(client) == (
                [app.QUERY_ALARM] * 2 if action == "query" else [frame] * 2 + [app.QUERY_ALARM] * 3
            )


async def test_sequential_both_renewable_hold_is_rejected_before_connection_or_motion(
    paired_runtime,
):
    hass, pair, left, right, left_client, right_client = paired_runtime
    pair._adopt_connection_mode("sequential")
    with (
        patch.object(left, "async_connect", AsyncMock()) as connect_left,
        patch.object(right, "async_connect", AsyncMock()) as connect_right,
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": ["pair"],
                "control": "HEADUP",
                "duration": 0.5,
                "hold_owner": "review-card",
                "hold_generation": 1,
            },
            blocking=True,
        )
    connect_left.assert_not_awaited()
    connect_right.assert_not_awaited()
    assert writes(left_client) == writes(right_client) == []


async def test_sequential_failed_release_never_connects_or_mutates_the_next_receiver(
    paired_runtime,
):
    hass, pair, left, right, left_client, right_client = paired_runtime
    pair._adopt_connection_mode("sequential")
    with (
        patch.object(right, "async_disconnect", AsyncMock(return_value=False)),
        patch.object(left, "async_connect", AsyncMock()) as connect_left,
        virtual_clock(),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["pair"], "preset": 1}, blocking=True
        )
    connect_left.assert_not_awaited()
    assert writes(left_client) == writes(right_client) == []


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_stop_while_idle_alarm_connects_blocks_the_alarm_after_owned_startup(
    hass, mock_bleak_client
):
    roles = make_client().services
    mock_bleak_client.services.__iter__ = lambda _self: iter(roles)
    mock_bleak_client.services.__len__ = lambda _self: len(roles)
    coord = AdjustableBedCoordinator(hass, entry(hass))
    await coord.async_prime_offline_controller()
    await async_register_services(hass)
    original = coord.async_ensure_connected

    async def stopped(reset_timer=True):
        result = await original(reset_timer=reset_timer)
        coord._command_scheduler.finish_stop(coord._command_scheduler.request_stop())
        return result

    try:
        with (
            patch.object(coord, "async_ensure_connected", side_effect=stopped),
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coord, "both")], []),
            ),
            virtual_clock(),
            pytest.raises(ServiceValidationError),
        ):
            await alarm(
                hass, "set", **{key: value for key, value in SET.items() if key != "operation"}
            )
        assert len(writes(mock_bleak_client)) == 3
        assert writes(mock_bleak_client)[1:] == [app.QUERY_MASSAGE] * 2
        assert not any(
            frame.startswith(bytes.fromhex("0705")) or frame == app.QUERY_ALARM
            for frame in writes(mock_bleak_client)
        )
    finally:
        await coord.async_shutdown()
