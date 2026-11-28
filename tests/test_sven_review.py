"""Public-flow regressions from the first A70 implementation review."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import SOURCE_BLUETOOTH
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import device_registry as dr
from probatio import Invalid
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat.sven import SvenController
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.select import _select_entities_for
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_atlas_lift import client_on, frames, packet_info, session_for
from tests.test_config_flow import _advance_only_progress, _patch_gate
from tests.test_richmat_family_flow import setup_flow
from tests.test_sven import make_controller, service
from tests.test_sven import runtime as runtime


async def test_paired_both_queue_then_side_cover_cannot_replace_due_shutoff(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    c.confirm_massage_off(True)
    c._levels = [1, 1]
    right_entry = MockConfigEntry(
        domain=const.DOMAIN, data={**coordinator.entry.data, CONF_ADDRESS: "AA:BB:CC:DD:EE:16"}
    )
    right_entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, right_entry)
    right._client = client_on(service())
    right._client.disconnect = AsyncMock()
    right._controller = SvenController(right)
    await right.controller.async_on_connect(session_for(right.controller, right.client))
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={"pair_id": "sven-safety"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": coordinator, "right": right}, connection_mode="concurrent"
    )
    dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    hass.data[const.DOMAIN][coordinator.entry.entry_id] = pair
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == bytes.fromhex("6e01004cbb") and not entered.is_set():
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    side = PairedSideProxy(pair, coordinator, "left")
    cover = AdjustableBedCover(side, _build_cover_description(c.motor_control_specs[0]))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        due = asyncio.create_task(c._timer_off(c._link, c._timer_epoch))
        await entered.wait()
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ):
            both = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {"device_id": ["bed"], "motor": "back", "direction": "up", "duration_ms": 100},
                    blocking=True,
                )
            )
            for _ in range(30):
                await asyncio.sleep(0)
                if pair.is_admitted_child(coordinator):
                    break
            if not pair.is_admitted_child(coordinator):
                finish.set()
                await asyncio.gather(due, both)
                pytest.fail("Both movement did not reach paired admission")
            replacement = asyncio.create_task(cover.async_close_cover())
            for _ in range(8):
                await asyncio.sleep(0)
            finish.set()
            await asyncio.gather(due, both, replacement)
    assert frames(client) == [
        bytes.fromhex(v)
        for v in ("6e01004cbb", "6e01006edd") * 3
        + ("6e01004ebd", "6e01006edd") * 3
        + ("6e01002594", "6e01006edd")
    ]
    assert c._levels == [0, 0]
    hass.data[const.DOMAIN][coordinator.entry.entry_id] = coordinator
    await right.async_shutdown()


async def test_explicit_stop_cancels_safety_waiting_for_coordinator_lock(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    c.confirm_massage_off(True)
    c._levels = [1, 1]
    with virtual_clock():
        async with coordinator._command_lock:
            due = asyncio.create_task(c._timer_off(c._link, c._timer_epoch))
            for _ in range(8):
                await asyncio.sleep(0)
            stop = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "stop_all",
                    {"device_id": ["bed"]},
                    blocking=True,
                )
            )
            for _ in range(8):
                await asyncio.sleep(0)
        await asyncio.gather(due, stop)
    assert frames(client) == [bytes.fromhex("6e01006edd")]


async def test_nonzero_level_change_through_zero_preserves_selected_absolute_deadline(
    hass, runtime
):
    coordinator, _client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    head = next(
        n
        for n in _number_entities_for(hass, coordinator)
        if n.entity_description.key == "massage_head_intensity"
    )
    timer = next(
        s
        for s in _select_entities_for(hass, coordinator)
        if s.entity_description.key == "massage_timer"
    )
    for entity in (head, timer):
        entity.hass = hass
        entity.async_write_ha_state = MagicMock()
    with virtual_clock():
        c.confirm_massage_off(True)
        await head.async_set_native_value(3)
        await timer.async_select_option("10 min")
        deadline = c._duration_deadline
        await asyncio.sleep(540)
        before = c._usage()
        await head.async_set_native_value(2)
        assert c._levels == [2, 0]
        assert c._duration_deadline == deadline
        assert c._timer.when() == pytest.approx(deadline)
        assert head.native_value == 2
        assert timer.current_option == "10 min"
        # The zero interval pauses use accounting, but never resets prior use.
        assert before < c._usage() < before + 0.6
        await asyncio.sleep(deadline - asyncio.get_running_loop().time() + 2)
        assert c._levels == [0, 0]
        assert timer.current_option == "Off"


@pytest.mark.parametrize("interruption", ("movement", "stop"))
async def test_due_shutoff_survives_movement_but_explicit_stop_still_cancels(
    hass, runtime, interruption
):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    c.confirm_massage_off(True)
    c._levels = [1, 1]
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == bytes.fromhex("6e01004cbb") and not entered.is_set():
            entered.set()
            await release.wait()

    client.write_gatt_char.side_effect = write
    cover = AdjustableBedCover(coordinator, _build_cover_description(c.motor_control_specs[0]))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        due_done = asyncio.Event()
        original_off = c._timer_off

        async def off(link, epoch):
            try:
                await original_off(link, epoch)
            finally:
                due_done.set()

        c._timer_off = off

        async def arm(ctrl):
            ctrl._duration_deadline = asyncio.get_running_loop().time() + 0.05
            ctrl._account()

        # Schedule under a real command context, then exercise the actual timer callback.
        await coordinator.async_execute_controller_command(arm)
        await entered.wait()
        interrupt = asyncio.create_task(
            cover.async_open_cover()
            if interruption == "movement"
            else coordinator.async_stop_command()
        )
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(due_done.wait(), interrupt)
    data = frames(client)
    if interruption == "movement":
        assert data == [
            bytes.fromhex(v)
            for v in ("6e01004cbb", "6e01006edd") * 3
            + ("6e01004ebd", "6e01006edd") * 3
            + ("6e01002493", "6e01006edd")
        ]
        assert c._levels == [0, 0]
    else:
        assert bytes.fromhex("6e01004ebd") not in data
        assert c._levels == [None, None]


async def test_duration_deadline_is_absolute_and_only_active_massage_can_select_it():
    c, client = make_controller()
    await c.async_on_connect(session_for(c, client))
    with virtual_clock():
        c.confirm_massage_off(True)
        with raises_key("sven_massage_inactive"):
            await c.set_massage_timer(10)
        await c.massage_head_toggle()
        await c.set_massage_timer(10)
        deadline = c._duration_deadline
        await asyncio.sleep(540)
        await c.massage_head_toggle()
        await c.massage_mode_step()
        assert c._duration_deadline == deadline
        assert c._timer.when() == pytest.approx(deadline)
        c.on_disconnect()


async def test_timer_revision_is_rechecked_under_scheduler_admission(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    c.confirm_massage_off(True)
    c._levels = [1, 1]
    entered, finish = asyncio.Event(), asyncio.Event()
    cancel = None

    async def write(_char, data, **kwargs):
        nonlocal cancel
        if data == bytes.fromhex("6e01002493"):
            cancel = coordinator.cancel_command
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        movement = asyncio.create_task(
            coordinator.async_execute_controller_command(
                lambda ctrl: ctrl.move_head_up(), resource="motor:back"
            )
        )
        await entered.wait()
        counter = coordinator.cancel_counter
        async with coordinator.command_scheduler._lock:
            due = asyncio.create_task(c._timer_off(c._link, c._timer_epoch))
            for _ in range(8):
                await asyncio.sleep(0)
            c._timer_epoch += 1
        await due
        assert coordinator.cancel_counter == counter
        assert cancel is not None and not cancel.is_set()
        finish.set()
        await movement
    assert frames(client) == [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")]


@pytest.mark.parametrize("error", (BleakError("CCCD refused"), TimeoutError("CCCD timeout")))
async def test_optional_notification_failure_retains_current_writer(error):
    c, client = make_controller()
    client.start_notify.side_effect = error
    await c.async_on_connect(session_for(c, client))
    with virtual_clock():
        await c.preset_flat()
    assert frames(client) == [bytes.fromhex("6e010031a0"), bytes.fromhex("6e01006edd")]
    c.on_disconnect()


@pytest.mark.parametrize("failure", ("cancel", "disconnected", "stale"))
async def test_optional_notify_does_not_hide_cancel_or_a_lost_session(failure):
    c, client = make_controller()
    current = True

    async def subscribe(*_args):
        nonlocal current
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "stale":
            current = False
        else:
            client.is_connected = False
        raise BleakError("failed subscription")

    client.start_notify.side_effect = subscribe
    session = session_for(c, client)
    session.is_current = lambda: current
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else ConnectionError):
        await c.async_on_connect(session)
    assert c._link is None


async def test_expired_card_lease_release_never_stops_a_replacement_link(hass, runtime):
    coordinator, old = runtime
    assert await coordinator.async_connect()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": ["bed"],
                "motor": "pillow",
                "direction": "up",
                "duration_ms": 100,
                "hold_owner": "card-review",
                "hold_generation": 1,
            },
            blocking=True,
        )
        c = coordinator.controller
        c.on_disconnect()
        new = client_on(service())
        new.disconnect = AsyncMock()
        coordinator._client = new
        await c.async_on_connect(session_for(c, new))
        # This is the card's automatic pointer release; it carries the admitted lease.
        await hass.services.async_call(
            const.DOMAIN,
            "stop_all",
            {
                "device_id": ["bed"],
                "hold_owner": "card-review",
                "hold_generation": 1,
            },
            blocking=True,
        )
        new.write_gatt_char.assert_not_awaited()
        # An explicit user Stop remains an ordinary physical safety action.
        await hass.services.async_call(
            const.DOMAIN, "stop_all", {"device_id": ["bed"]}, blocking=True
        )
        assert frames(new) == [bytes.fromhex("6e01006edd")]


async def test_live_card_release_ends_only_its_admitted_hold(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    entered = asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == bytes.fromhex("6e010041b0"):
            entered.set()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        held = asyncio.create_task(
            hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {
                    "device_id": ["bed"],
                    "motor": "pillow",
                    "direction": "up",
                    "duration_ms": 1000,
                    "hold_owner": "card-review",
                    "hold_generation": 2,
                },
                blocking=True,
            )
        )
        await entered.wait()
        # A delayed release for the previous generation cannot touch this hold.
        await hass.services.async_call(
            const.DOMAIN,
            "stop_all",
            {
                "device_id": ["bed"],
                "hold_owner": "card-review",
                "hold_generation": 1,
            },
            blocking=True,
        )
        assert frames(client)[-1] == bytes.fromhex("6e010041b0")
        await hass.services.async_call(
            const.DOMAIN,
            "stop_all",
            {
                "device_id": ["bed"],
                "hold_owner": "card-review",
                "hold_generation": 2,
            },
            blocking=True,
        )
        await held
    assert frames(client)[-1] == bytes.fromhex("6e01006edd")
    assert frames(client).count(bytes.fromhex("6e01006edd")) == 1


async def test_device_first_not_sure_keeps_the_confident_bedtech_route(hass):
    info = packet_info(
        "QRRMABCD",
        "QRRMABCD",
        (const.BEDTECH_SERVICE_UUID,),
        {const.BEDTECH_MANUFACTURER_ID: bytes.fromhex("54307651")},
    )
    flow = setup_flow(hass)
    flow._all_ble_devices = {info.address: info}
    await flow.async_step_manual({CONF_ADDRESS: info.address})
    await flow.async_step_select_app({const.CONF_BED_TYPE: "not_listed"})
    result = await flow.async_step_select_family({const.CONF_BED_TYPE: "not_sure"})
    assert "not_sure_detected" in result["menu_options"]


@pytest.mark.parametrize("accepted", (False, True))
async def test_setup_uses_the_runtime_selector_before_allowing_finish(
    hass, enable_custom_integrations, accepted
):
    manager = hass.config_entries.flow
    info = packet_info("QJ-ABCD", "QJ-ABCD")
    chooser = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    confirm = await manager.async_configure(chooser["flow_id"], {"bed_type_choice": "sven"})
    questions = await manager.async_configure(confirm["flow_id"], {const.CONF_BED_TYPE: "sven"})
    settings = await manager.async_configure(
        questions["flow_id"], {const.CONF_PROTOCOL_VARIANT: "classic"}
    )
    assert settings["step_id"] == "finish_settings"
    roles = service()
    if not accepted:
        roles = SimpleNamespace(
            uuid="0000180a-0000-1000-8000-00805f9b34fb", characteristics=roles.characteristics
        )
    client = client_on(roles)
    client.disconnect = AsyncMock()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -53),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
    ):
        result = await _advance_only_progress(
            hass, await manager.async_configure(settings["flow_id"], {})
        )
    assert result["step_id"] == "verify_connection"
    if not accepted:
        schema = result["data_schema"]
        assert schema({"action": "retry"}) == {"action": "retry"}
        with pytest.raises(Invalid):
            schema({"action": "finish"})
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()


@pytest.mark.parametrize("mode", ("sequential", "auto"))
async def test_massage_requires_persistent_topology_including_automatic_fallback(
    hass, runtime, mode
):
    from custom_components.adjustable_bed import paired_topology

    coordinator, client = runtime
    assert await coordinator.async_connect()
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data={"pair_id": "sven-review"})
    pair = PairedBedCoordinator(hass, entry, {"left": coordinator}, connection_mode=mode)
    hass.data[const.DOMAIN][coordinator.entry.entry_id] = pair
    if mode == "auto":
        coordinator.controller.confirm_massage_off(True)
        with (
            patch.object(paired_topology, "connection_slot_exhausted", return_value=True),
            patch.object(paired_topology, "shared_connection_slot_pressure", return_value=True),
        ):
            await pair._lanes.fallback_after_connection_slot_exhaustion(
                ConnectionError("slots"), {}
            )
        assert pair.connection_mode == "sequential"
        client.is_connected = True
        coordinator._client = client
        from custom_components.adjustable_bed.beds.richmat.sven import SvenController

        coordinator._controller = SvenController(coordinator)
        await coordinator.controller.async_on_connect(session_for(coordinator.controller, client))
    c = coordinator.controller
    with raises_key("sven_massage_concurrent"):
        c.confirm_massage_off(True)
    with raises_key("sven_massage_concurrent"):
        await c.massage_head_toggle()
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            lambda ctrl: ctrl.move_head_up(), resource="motor:back"
        )
    assert bytes.fromhex("6e01002493") in frames(client)
    hass.data[const.DOMAIN][coordinator.entry.entry_id] = coordinator
