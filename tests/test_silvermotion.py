"""SILVERmotion setup, shared control shapes and physical-session transactions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_families import LOGICDATA_FAMILY
from custom_components.adjustable_bed.beds.silvermotion.controller import SilvermotionController
from custom_components.adjustable_bed.beds.silvermotion.discovery import scan_matches
from custom_components.adjustable_bed.codec import silvermotion as codec
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
    Delivery,
    delivered,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import _check_manufacturer_data
from custom_components.adjustable_bed.profiles import silvermotion as app
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.form_helpers import form_fields, start_new_bed
from tests.hold_lease_wire import virtual_clock


def bed(hass, *, size="queen", massage=True):
    char = MagicMock(
        uuid=codec.CHARACTERISTIC,
        handle=10,
        properties=["write-without-response", "notify"],
        descriptors=[],
    )
    client = MagicMock(
        is_connected=True, services=[SimpleNamespace(uuid=codec.SERVICE, characteristics=[char])]
    )
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    co = MagicMock(
        hass=hass,
        client=client,
        address="AA:BB:CC:DD:EE:FF",
        cancel_command=asyncio.Event(),
        motor_pulse_count=1,
    )
    co.entry.data = {
        const.CONF_BED_TYPE: "silvermotion",
        const.CONF_PRODUCT_TYPE: size,
        const.CONF_HAS_MASSAGE: massage,
    }
    co.controller_state = ControllerState()
    co.is_shutting_down = False
    co.command_scheduler.has_pending_stop = False
    co.async_note_control_access_succeeded = AsyncMock()
    co.handle_controller_state_updates.side_effect = lambda *updates: co.controller_state.update(
        (u.key, u.value) for u in updates
    )
    controller = SilvermotionController(co)
    co.controller = controller
    return controller, co, client, char


def writes(client):
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


def frame(action):
    return list(codec.chunks(codec.encode(app.COMMANDS[action], app.repeat_count(action))))


@pytest.mark.parametrize("size", app.SIZES)
@pytest.mark.parametrize("massage", (True, False))
async def test_layout_gates_and_shared_shapes(hass, size, massage):
    ctrl, co, client, char = bed(hass, size=size, massage=massage)
    await ctrl.async_discover_capabilities()
    assert [s.key for s in ctrl.motor_control_specs] == ["back", "legs"]
    assert ctrl.memory_slot_count == 2
    assert ctrl.supports_massage is massage
    assert ctrl.supports_massage_timer is massage
    assert ctrl.supports_lights and ctrl.supports_light_toggle_control
    assert not ctrl.supports_discrete_light_control
    assert not ctrl.supports_position_feedback and not ctrl.supports_clock_alarm
    assert not ctrl.supports_single_address_pairing
    specs = {s.key: s for s in ctrl.controller_button_specs}
    assert ("massage_form_two" in specs) is massage
    for name in ("flat_reset", "factory_reset"):
        assert specs[name].requires_confirmation and specs[name].hold is None
        assert not specs[name].entity_registry_enabled_default
        assert specs[name].diagnostic
    if not massage:
        with pytest.raises(ValueError):
            await ctrl.massage_intensity_up()
        assert writes(client) == []
    ctrl.on_disconnect()


@pytest.mark.parametrize("marker", (b"LL", b"NS", b"FS"))
def test_manufacturer_gate_without_name_guessing(marker):
    data = bytes(7) + marker + bytes((0, 99))
    assert scan_matches({1351: data})
    assert _check_manufacturer_data({1351: data})[0] == "silvermotion"
    assert not scan_matches({1351: data[:9] + bytes((1, 99))})
    assert scan_matches({1351: data[:9] + bytes((1, 99))}, bonded=True)
    assert not scan_matches({1351: data[:9] + bytes((2, 99))}, bonded=True)
    assert not scan_matches({100: b"", 1351: data})
    assert scan_matches({1351: bytes(7)})
    assert not scan_matches({1351: bytes(11)})
    assert not scan_matches({1351: bytes(8)})
    assert not scan_matches({})


async def test_public_family_setup_reaches_size_and_massage(hass):
    assert LOGICDATA_FAMILY.answers["silvermotion_android"].bed_type == "silvermotion"
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    result = await start_new_bed(flow, "typed", "silvermotion", "AA:BB:CC:DD:EE:FF")
    assert result["step_id"] == "logicdata_family"
    result = await flow.async_step_logicdata_family({"choice": "silvermotion_android"})
    assert result["step_id"] == "profile_questions"
    assert {m.schema for m in form_fields(result["data_schema"])} == {
        const.CONF_PRODUCT_TYPE,
        const.CONF_HAS_MASSAGE,
    }
    result = await flow.async_step_profile_questions(
        {const.CONF_PRODUCT_TYPE: "twin_xl", const.CONF_HAS_MASSAGE: False}
    )
    assert result["step_id"] == "finish_settings"


async def test_startup_subscribes_without_pair_or_control_writes(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    client.start_notify.assert_awaited_once()
    client.pair.assert_not_called()
    assert writes(client) == []
    assert co.controller_state[MASSAGE_TIMER_MINUTES] == 10
    await ctrl.stop_notify()
    client.stop_notify.assert_awaited_once_with(char)


async def test_movement_and_cancel_finish_frame_before_release(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    count = 0

    async def cancel_after_first(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            co.cancel_command.set()

    client.write_gatt_char.side_effect = cancel_after_first
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await ctrl.move_back_up()
    assert writes(client) == frame("back_up") + frame("release")
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.call_args_list)
    ctrl.on_disconnect()


async def test_task_cancellation_during_fragment_settles_before_cleanup(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    entered, resume = asyncio.Event(), asyncio.Event()

    async def block(*args, **kwargs):
        if len(writes(client)) == 1:
            entered.set()
            await resume.wait()

    client.write_gatt_char.side_effect = block
    with virtual_clock():
        task = asyncio.create_task(ctrl.move_legs_up())
        await entered.wait()
        task.cancel()
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert writes(client) == frame("legs_up") + frame("release")
    ctrl.on_disconnect()


@pytest.mark.parametrize("change", ("client", "config", "gatt", "owner", "disconnect"))
async def test_stale_session_never_gets_tail_or_release(hass, change):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    replacement = MagicMock(write_gatt_char=AsyncMock(), is_connected=True)

    async def invalidate(*args, **kwargs):
        if change == "client":
            co.client = replacement
        elif change == "config":
            co.entry.data = {**co.entry.data, const.CONF_PRODUCT_TYPE: "king"}
        elif change == "gatt":
            client.services[0].characteristics = [
                SimpleNamespace(uuid=char.uuid, properties=char.properties)
            ]
        elif change == "owner":
            ctrl._owner.publisher = object()
        else:
            client.is_connected = False

    client.write_gatt_char.side_effect = invalidate
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.move_back_up()
    assert writes(client) == frame("back_up")[:1]
    replacement.write_gatt_char.assert_not_called()
    ctrl.on_disconnect()


async def test_recall_stop_fence_blocks_recall_after_preamble(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()

    async def stop_after_preamble(*args, **kwargs):
        if len(writes(client)) == len(frame("any_key")):
            co.cancel_command.set()

    client.write_gatt_char.side_effect = stop_after_preamble
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await ctrl.preset_memory(1)
    assert writes(client) == frame("any_key")
    ctrl.on_disconnect()


async def test_split_notification_is_ack_only_and_old_callbacks_are_ignored(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    callback = client.start_notify.call_args.args[1]
    ack = codec.encode_plain(bytes.fromhex("0300000000000000"))
    callback(char, bytearray(ack[:8]))
    assert not ctrl._ack.is_set()
    callback(char, bytearray(ack[8:]))
    assert ctrl._ack.is_set()
    assert list(co.controller_state) == [MASSAGE_TIMER_MINUTES]
    ctrl.on_disconnect()
    ctrl._ack.clear()
    callback(char, bytearray(ack))
    assert not ctrl._ack.is_set()


async def test_timer_and_reset_native_actions(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    with virtual_clock():
        await ctrl.set_massage_timer(1)
        assert writes(client) == []
        await ctrl.press("massage_form_two")
        assert writes(client) == frame("massage_form_two")
        assert ctrl._owner.deadline is not None
        await ctrl.massage_off()
        assert writes(client) == frame("massage_form_two") + frame("massage_off")
        assert ctrl._owner.deadline is None
        client.write_gatt_char.reset_mock()
        await ctrl.press("flat_reset")
        assert writes(client) == frame("flat_reset")
        client.write_gatt_char.reset_mock()
        await ctrl.press("factory_reset")
        assert writes(client) == frame("factory_reset")
    ctrl.on_disconnect()


async def test_partial_and_cancelled_delivery(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=co.cancel_command,
        admitted_stop_epoch=0,
        intent_id="test",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    observed = []
    try:
        co.cancel_command.set()
        with virtual_clock(), delivered(observed.append):
            await ctrl.lights_toggle()
        assert observed == [Delivery.NONE]
        assert writes(client) == []
        co.cancel_command.clear()
        observed.clear()

        async def fail_tail(*args, **kwargs):
            if len(writes(client)) == 2:
                raise ConnectionError("Radio lost")

        client.write_gatt_char.side_effect = fail_tail
        with virtual_clock(), pytest.raises(ConnectionError), delivered(observed.append):
            await ctrl.lights_toggle()
        assert observed == [Delivery.PARTIAL]
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
        ctrl.on_disconnect()


@pytest.fixture
async def connected_silvermotion(hass, mock_coordinator_connected, mock_bleak_client):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "Bed",
            "bed_type": "silvermotion",
            "product_type": "queen",
            "has_massage": True,
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
        },
    )
    entry.add_to_hass(hass)
    char = MagicMock(
        uuid=codec.CHARACTERISTIC,
        handle=10,
        properties=["write-without-response", "notify"],
        descriptors=[],
    )
    mock_bleak_client.services = [SimpleNamespace(uuid=codec.SERVICE, characteristics=[char])]
    co = AdjustableBedCoordinator(hass, entry)
    assert await co.async_connect()
    try:
        yield co, mock_bleak_client
    finally:
        await co.async_shutdown()


async def test_real_coordinator_and_native_entity_actions(hass, connected_silvermotion):
    from custom_components.adjustable_bed.button import ControllerActionButton

    co, client = connected_silvermotion
    ctrl = co.controller
    assert isinstance(ctrl, SilvermotionController)
    assert writes(client) == []
    client.pair.assert_not_called()
    specs = {s.key: s for s in ctrl.controller_button_specs}
    button = ControllerActionButton(co, specs["breakfast"])
    button.hass = hass
    with virtual_clock():
        await button.async_press()
        await co.async_execute_controller_command(lambda c: c.program_memory(2))
        await co.async_execute_controller_command(lambda c: c.lights_toggle())
    assert writes(client) == frame("breakfast") + frame("save_memory_2") + frame("light_toggle")


@pytest.mark.parametrize("quick_handoff", [False, True])
async def test_countdown_retains_default_idle_link_then_restores_handoff(
    connected_silvermotion, quick_handoff
):
    co, client = connected_silvermotion
    co._disconnect_after_command = quick_handoff
    with virtual_clock(), patch.object(co.hass, "loop", asyncio.get_running_loop()):
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        assert co._command_connection_holds == 1
        assert co._disconnect_timer is None
        timer = co.controller._timer
        assert timer is not None
        await timer
        await asyncio.sleep(0)
        assert co.is_connected
        client.disconnect.assert_not_called()
        assert co._command_connection_holds == 0
        assert co._disconnect_timer.when() - asyncio.get_running_loop().time() == pytest.approx(
            1 if quick_handoff else 40
        )
    assert writes(client) == frame("massage_form_one") + frame("massage_off")


async def test_failed_disconnect_retains_command_and_stop_path(connected_silvermotion):
    co, client = connected_silvermotion
    ctrl = co.controller
    link = ctrl._link
    # The backend returns without releasing its connected flag.
    client.disconnect.side_effect = None
    assert not await co.async_disconnect()
    assert co.controller is ctrl and ctrl._link is link
    assert ctrl._notifying
    with virtual_clock():
        await co.async_execute_controller_command(lambda c: c.lights_toggle())
        await co.async_stop_command()
    assert client.start_notify.await_count == 2
    assert writes(client) == frame("light_toggle") + frame("release")


async def test_expiry_queues_behind_active_user_action(connected_silvermotion):
    co, client = connected_silvermotion
    entered, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_three"))
        timer = co.controller._timer
        assert timer is not None

        async def wait_for_user(char, chunk, **kwargs):
            if chunk == frame("light_toggle")[0]:
                entered.set()
                await resume.wait()

        client.write_gatt_char.side_effect = wait_for_user
        user = asyncio.create_task(co.async_execute_controller_command(lambda c: c.lights_toggle()))
        await entered.wait()
        await asyncio.sleep(60)
        assert not user.done() and not timer.done()
        assert writes(client) == frame("massage_form_three") + frame("light_toggle")[:1]
        resume.set()
        await user
        await timer
    assert writes(client) == frame("massage_form_three") + frame("light_toggle") + frame(
        "massage_off"
    )


async def test_timer_expiry_and_expired_off_before_motion(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()

    async def execute(fn, **kwargs):
        if kwargs["run_if"]():
            await fn(ctrl)

    co.async_execute_controller_query = execute
    with virtual_clock():
        await ctrl.set_massage_timer(1)
        await ctrl.press("massage_form_three")
        timer = ctrl._timer
        assert timer is not None
        await timer
        assert writes(client) == frame("massage_form_three") + frame("massage_off")
        ctrl._owner.deadline = asyncio.get_running_loop().time() - 1
        client.write_gatt_char.reset_mock()
        await ctrl.move_legs_down()
        assert writes(client) == frame("massage_off") + frame("legs_down") + frame("release")
    ctrl.on_disconnect()


async def test_ended_generation_cannot_send_old_cleanup(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    old_link, old_generation = ctrl._link, ctrl._generation
    assert old_link is not None
    with virtual_clock():
        await ctrl.stop_all()
        client.write_gatt_char.reset_mock()
        await ctrl._release(old_link, old_generation)
    assert writes(client) == []
    ctrl.on_disconnect()


async def test_stale_teardown_cannot_unsubscribe_new_owner(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    ctrl._owner.publisher = object()
    await ctrl.stop_notify()
    client.stop_notify.assert_not_called()


async def test_sent_massage_intent_survives_cancellation_after_complete_frame(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=co.cancel_command,
        admitted_stop_epoch=0,
        intent_id="test",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    token = _CURRENT_COMMAND_CONTEXT.set(context)

    async def cancel_last(*args, **kwargs):
        if len(writes(client)) == len(frame("massage_form_one")):
            co.cancel_command.set()

    client.write_gatt_char.side_effect = cancel_last
    try:
        with virtual_clock(), pytest.raises(asyncio.CancelledError):
            await ctrl.press("massage_form_one")
        assert writes(client) == frame("massage_form_one")
        assert ctrl._owner.deadline is not None
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
        ctrl._clear_timer()
        ctrl.on_disconnect()


def test_android_bonding_is_observed_error_recovery_not_forced_pairing():
    assert not const.requires_pairing("silvermotion")
    assert const.supports_runtime_authentication_recovery("silvermotion")
    # An explicit repair follows the app's discover-before-bond ordering.
    assert const.requires_pairing_after_service_discovery("silvermotion")


async def test_notification_teardown_retains_physical_session_and_restores_on_stop(hass):
    ctrl, co, client, char = bed(hass)
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    link = ctrl._link
    await ctrl.stop_notify()
    assert ctrl._link is link and not ctrl._notifying
    with virtual_clock():
        await ctrl.stop_all()
    assert client.start_notify.await_count == 2
    assert ctrl._notifying
    assert writes(client) == frame("release")
    ctrl.on_disconnect()


@pytest.mark.parametrize(
    "error,repair", [("Insufficient authentication", True), ("Device went away", False)]
)
async def test_only_observed_authentication_failure_offers_bond_repair(
    connected_silvermotion, error, repair
):
    from bleak.exc import BleakError

    co, client = connected_silvermotion
    client.write_gatt_char.side_effect = BleakError(error)
    with (
        virtual_clock(),
        patch(
            "custom_components.adjustable_bed.coordinator_bonds.create_pairing_required_issue",
            new_callable=AsyncMock,
        ) as issue,
    ):
        with pytest.raises(BleakError):
            await co.async_execute_controller_command(lambda c: c.lights_toggle())
        assert issue.await_count == int(repair)
    client.pair.assert_not_called()


@pytest.mark.parametrize("elapsed_during_teardown", [0, 65])
async def test_failed_disconnect_restores_countdown_without_user_command(
    connected_silvermotion, elapsed_during_teardown
):
    co, client = connected_silvermotion
    with virtual_clock(), patch.object(co.hass, "loop", asyncio.get_running_loop()):
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))

        async def retained():
            await asyncio.sleep(elapsed_during_teardown)

        client.disconnect.side_effect = retained
        assert not await co.async_disconnect()
        timer = co.controller._timer
        assert timer is not None
        await timer
        await asyncio.sleep(0)
        assert writes(client) == frame("massage_form_one") + frame("massage_off")
        assert co._command_connection_holds == 0
        assert co._disconnect_timer.when() - asyncio.get_running_loop().time() == pytest.approx(40)
    client.disconnect.side_effect = None


@pytest.mark.parametrize("replacement", ["light", "stop"])
async def test_waiting_expiry_survives_user_replacement_but_respects_stop(
    connected_silvermotion, replacement
):
    co, client = connected_silvermotion
    entered, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_three"))
        timer = co.controller._timer
        assert timer is not None
        blocked = False

        async def first_light(char, chunk, **kwargs):
            nonlocal blocked
            if chunk == frame("light_toggle")[0] and not blocked:
                blocked = True
                entered.set()
                await resume.wait()

        client.write_gatt_char.side_effect = first_light
        first = asyncio.create_task(
            co.async_execute_controller_command(lambda c: c.lights_toggle())
        )
        await entered.wait()
        await asyncio.sleep(60)
        if replacement == "light":
            second = asyncio.create_task(
                co.async_execute_controller_command(lambda c: c.lights_toggle())
            )
        else:
            second = asyncio.create_task(co.async_stop_command())
        await asyncio.sleep(0)
        resume.set()
        await asyncio.gather(first, second)
        await timer
    actual = writes(client)
    if replacement == "light":
        assert actual == frame("massage_form_three") + frame("light_toggle") + frame(
            "massage_off"
        ) + frame("light_toggle")
    else:
        assert actual == frame("massage_form_three") + frame("light_toggle") + frame("release")


@pytest.mark.parametrize("stop_pending", [True, False])
async def test_expiry_rejects_pending_stop_but_allows_a_completed_stop(
    connected_silvermotion, stop_pending
):
    co, client = connected_silvermotion
    ctrl = co.controller
    assert isinstance(ctrl, SilvermotionController)
    link = ctrl._link
    assert link is not None
    entered, resume = asyncio.Event(), asyncio.Event()
    send_stop = co._async_send_stop_command

    async def delayed_stop():
        entered.set()
        await resume.wait()
        await send_stop()

    with virtual_clock():
        with patch.object(ctrl, "_arm_timer"):
            await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        with patch.object(co, "_async_send_stop_command", side_effect=delayed_stop):
            stop = asyncio.create_task(co.async_stop_command())
            await entered.wait()
            if not stop_pending:
                resume.set()
                await stop
            ctrl._owner.deadline = asyncio.get_running_loop().time()
            ctrl._arm_timer(link)
            timer = ctrl._timer
            assert timer is not None
            try:
                await timer
                expected = frame("massage_form_one")
                if not stop_pending:
                    expected += frame("release") + frame("massage_off")
                assert writes(client) == expected
            finally:
                resume.set()
                await stop


async def test_bond_bookkeeping_does_not_invalidate_current_control_session(hass):
    ctrl, co, client, char = bed(hass)
    co.entry.data = {
        **co.entry.data,
        const.CONF_BLE_BOND_ESTABLISHED: True,
        const.CONF_BLE_BOND_ATTEMPTED_SOURCE: "host",
    }
    await ctrl.async_discover_capabilities()
    co.entry.data = {k: v for k, v in co.entry.data.items() if k not in const.RUNTIME_BOND_KEYS}
    with virtual_clock():
        await ctrl.lights_toggle()
    assert writes(client) == frame("light_toggle")
    ctrl.on_disconnect()


async def test_host_repair_discovers_then_pairs_and_reloaded_controller_accepts_commands(
    connected_silvermotion,
):
    from custom_components.adjustable_bed.repairs import PairingRequiredRepairFlow

    co, client = connected_silvermotion
    assert await co.async_disconnect()
    flow = PairingRequiredRepairFlow(co.address, "Bed", co.entry.entry_id)
    flow.hass = co.hass
    order = []
    repair_client = MagicMock()
    repair_client.disconnect = AsyncMock()
    repair_client.read_gatt_char = AsyncMock(return_value=b"Model")

    async def pair():
        order.append("pair")
        return True

    repair_client.pair = AsyncMock(side_effect=pair)

    async def discovered(*args, **kwargs):
        assert not kwargs.get("pair", False)
        order.append("services_discovered")
        return repair_client

    async def reload(entry_id):
        assert entry_id == co.entry.entry_id
        assert co.entry.data[const.CONF_BLE_BOND_ESTABLISHED]
        assert await co.async_connect()
        await co.async_execute_controller_command(lambda c: c.lights_toggle())
        order.append("command_after_reload")
        return True

    with (
        virtual_clock(),
        patch.object(flow, "_find_device", return_value=MagicMock()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(side_effect=discovered)),
        patch.object(co.hass.config_entries, "async_reload", new=AsyncMock(side_effect=reload)),
    ):
        assert await flow._async_try_pair()
    assert order == ["services_discovered", "pair", "command_after_reload"]
    repair_client.pair.assert_awaited_once()
    client.pair.assert_not_called()
    assert writes(client) == frame("light_toggle")


async def test_notification_only_reconnect_preserves_write_auth_repair_until_actual_write(
    connected_silvermotion,
):
    from bleak.exc import BleakError

    co, client = connected_silvermotion
    with (
        virtual_clock(),
        patch(
            "custom_components.adjustable_bed.coordinator_bonds.delete_pairing_required_issue",
            new_callable=AsyncMock,
        ) as delete,
    ):
        client.write_gatt_char.side_effect = BleakError("Insufficient authentication")
        with pytest.raises(BleakError):
            await co.async_execute_controller_command(lambda c: c.lights_toggle())
        evidence = co.last_bond_evidence
        assert evidence is not None
        assert await co.async_connect()
        assert co.last_bond_evidence is evidence
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        assert co.last_bond_evidence is evidence
        delete.assert_not_awaited()
        client.write_gatt_char.side_effect = None
        await co.async_execute_controller_command(lambda c: c.lights_toggle())
        assert co.last_bond_evidence is None
        delete.assert_awaited_once()


async def test_failed_disconnect_during_shutdown_does_not_restore_countdown(connected_silvermotion):
    co, client = connected_silvermotion
    with virtual_clock(), patch.object(co.hass, "loop", asyncio.get_running_loop()):
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        client.disconnect.side_effect = None
        await co.async_shutdown()
        await asyncio.sleep(65)
        assert co.controller._timer is None
        assert not co.controller._notifying
        assert co._command_connection_holds == 0
        assert co._disconnect_timer is None
        assert client.start_notify.await_count == 1
        assert writes(client) == frame("massage_form_one")


@pytest.mark.parametrize(
    "intervention", ["light_before_frame", "light_during_frame", "stop_before_frame"]
)
async def test_expiry_owns_its_event_and_clears_only_after_full_off(
    connected_silvermotion, intervention
):
    co, client = connected_silvermotion
    later = []
    original = co.async_execute_controller_query

    async def new_intent():
        if intervention == "stop_before_frame":
            later.append(asyncio.create_task(co.async_stop_command()))
        else:
            later.append(
                asyncio.create_task(
                    co.async_execute_controller_command(lambda c: c.lights_toggle())
                )
            )
        await asyncio.sleep(0)

    async def query(fn, **kwargs):
        async def admitted(controller):
            if intervention != "light_during_frame":
                await new_intent()
            await fn(controller)

        return await original(admitted, **kwargs)

    async def mid_frame(char, chunk, **kwargs):
        if intervention == "light_during_frame" and chunk == frame("massage_off")[0]:
            await new_intent()

    with virtual_clock(), patch.object(co, "async_execute_controller_query", side_effect=query):
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        timer = co.controller._timer
        assert timer is not None
        client.write_gatt_char.side_effect = mid_frame
        await timer
        await asyncio.gather(*later)
        if intervention == "stop_before_frame":
            assert co.controller._owner.deadline is not None
            assert writes(client) == frame("massage_form_one") + frame("release")
        else:
            assert co.controller._owner.deadline is None
            assert writes(client) == frame("massage_form_one") + frame("massage_off") + frame(
                "light_toggle"
            )


async def test_persisted_auth_repair_survives_fresh_runtime_notification_startup(
    connected_silvermotion,
):
    from bleak.exc import BleakError
    from homeassistant.helpers import issue_registry as ir

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    old, client = connected_silvermotion
    registry = ir.async_get(old.hass)
    issue_id = "pairing_required_aa_bb_cc_dd_ee_ff"
    with virtual_clock():
        client.write_gatt_char.side_effect = BleakError("Insufficient authentication")
        with pytest.raises(BleakError):
            await old.async_execute_controller_command(lambda c: c.lights_toggle())
        assert registry.async_get_issue(const.DOMAIN, issue_id) is not None
        await old.async_shutdown()
        fresh = AdjustableBedCoordinator(old.hass, old.entry)
        try:
            assert await fresh.async_connect()
            assert registry.async_get_issue(const.DOMAIN, issue_id) is not None
            client.write_gatt_char.side_effect = None
            await fresh.async_execute_controller_command(lambda c: c.lights_toggle())
            assert registry.async_get_issue(const.DOMAIN, issue_id) is None
        finally:
            await fresh.async_shutdown()


async def test_cancelled_complete_control_frame_resolves_prior_auth_issue(connected_silvermotion):
    from bleak.exc import BleakError

    co, client = connected_silvermotion
    entered, resume = asyncio.Event(), asyncio.Event()
    with virtual_clock():
        client.write_gatt_char.side_effect = BleakError("Insufficient authentication")
        with pytest.raises(BleakError):
            await co.async_execute_controller_command(lambda c: c.lights_toggle())
        assert await co.async_connect()
        assert co.last_bond_evidence is not None
        client.write_gatt_char.reset_mock()

        async def last_fragment(char, chunk, **kwargs):
            if chunk == frame("light_toggle")[-1]:
                entered.set()
                await resume.wait()

        client.write_gatt_char.side_effect = last_fragment
        task = asyncio.create_task(co.async_execute_controller_command(lambda c: c.lights_toggle()))
        await entered.wait()
        task.cancel()
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with co.async_command_operation_guard():
            pass
        assert writes(client) == frame("light_toggle")
        assert co.last_bond_evidence is None


@pytest.mark.parametrize("retained", [True, False])
async def test_cancelled_disconnect_settles_retained_or_released_session(
    connected_silvermotion, retained
):
    co, client = connected_silvermotion
    entered = asyncio.Event()
    with virtual_clock(), patch.object(co.hass, "loop", asyncio.get_running_loop()):
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        ctrl = co.controller

        async def disconnect():
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                client.is_connected = retained

        client.disconnect.side_effect = disconnect
        task = asyncio.create_task(co.async_disconnect())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        client.disconnect.side_effect = None
        if retained:
            assert co.controller is ctrl and ctrl._notifying and not ctrl._releasing
            await co.async_stop_command()
            timer = ctrl._timer
            assert timer is not None
            await timer
            assert writes(client) == frame("massage_form_one") + frame("release") + frame(
                "massage_off"
            )
        else:
            assert co.controller is None and not co.is_connected
            assert ctrl._link is None and ctrl._timer is None


@pytest.mark.parametrize("intervention", ["stop", "shutdown"])
async def test_expiry_rechecks_admission_inside_scheduled_transaction(
    connected_silvermotion, intervention
):
    from custom_components.adjustable_bed.beds.silvermotion import controller as runtime

    co, client = connected_silvermotion
    original = runtime.settled
    injected = False
    pending = []

    async def schedule_gap(operation):
        nonlocal injected
        if not injected and operation.cr_code.co_name == "transaction":
            injected = True
            if intervention == "stop":
                pending.append(asyncio.create_task(co.async_stop_command()))
            else:
                client.disconnect.side_effect = None
                pending.append(asyncio.create_task(co.async_shutdown()))
            await asyncio.sleep(0)
        return await original(operation)

    with virtual_clock():
        await co.async_execute_controller_command(lambda c: c.set_massage_timer(1))
        await co.async_execute_controller_command(lambda c: c.press("massage_form_one"))
        ctrl = co.controller
        timer = ctrl._timer
        assert timer is not None
        with patch.object(runtime, "settled", side_effect=schedule_gap):
            await timer
            await asyncio.gather(*pending)
        assert injected
        assert ctrl._owner.deadline is not None
        assert writes(client) == frame("massage_form_one") + (
            frame("release") if intervention == "stop" else []
        )
