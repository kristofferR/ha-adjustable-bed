"""Selected app actions, cancellation ownership and public setup/service paths."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.ronco_motion.controller import RoncoMotionController
from custom_components.adjustable_bed.beds.ronco_motion.protocol import parse_notification
from custom_components.adjustable_bed.beds.ronco_motion.state import ALARM
from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, DOMAIN
from custom_components.adjustable_bed.profiles.ronco_motion import (
    MOTORS,
    PROFILES,
    SHORT,
    STARTUP,
    TRANSPORTS,
    accepts_name,
)
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import setup_profile
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.state_helpers import state_writer


def request(enabled):
    return AlarmRequest(
        enabled=enabled,
        hour=7,
        minute=15,
        wake_action="zero_g",
        reference_time=datetime(2026, 11, 27, 22, 30),
    )


def make_controller(hass, key="premium", transport=0):
    role = TRANSPORTS[transport]
    write = SimpleNamespace(uuid=role.write_uuid, properties=["write"], handle=1)
    notify = SimpleNamespace(uuid=role.notify_uuid, properties=["notify"], handle=2)
    client = MagicMock(is_connected=True)
    client.services = [SimpleNamespace(uuid=role.service_uuid, characteristics=[write, notify])]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    owner = MagicMock(hass=hass, client=client, address="AA:BB:CC:DD:EE:75")
    owner.cancel_command = asyncio.Event()
    owner.motor_pulse_count = 3
    state = {}
    owner.handle_controller_state_updates.side_effect = state_writer(state)
    return RoncoMotionController(owner, PROFILES[key]), owner, client, state


def frames(client):
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("transport", range(5))
async def test_every_transport_uses_full_frames_and_subscribes(hass, transport):
    ctrl, _, client, _ = make_controller(hass, transport=transport)
    await ctrl.start_notify()
    with virtual_time(FakeClock()):
        await ctrl.preset_flat()
    assert frames(client) == ["6e010031a0", "6e01006edd"]
    assert client.write_gatt_char.call_args.args[0].uuid == TRANSPORTS[transport].write_uuid
    client.start_notify.assert_awaited_once()
    await ctrl.stop_notify()
    client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("key", PROFILES)
async def test_layout_entities_and_each_short_action(hass, key):
    ctrl, _, client, _ = make_controller(hass, key)
    assert [spec.key for spec in ctrl.motor_control_specs] == list(PROFILES[key].motors)
    assert ctrl.memory_slot_count == 1 and ctrl.supports_memory_presets
    assert ctrl.supports_single_address_pairing is False
    assert ctrl.execution.hold == "stream" and not ctrl.execution.concurrent
    buttons = {spec.key: spec for spec in ctrl.controller_button_specs}
    assert ("ronco_motion_light" in buttons) == (key == "premium")
    for spec in buttons.values():
        assert spec.card.section in {"presets", "lighting"}
    with virtual_time(FakeClock()):
        for action, code in SHORT.items():
            if action == "light_toggle" and key == "economy":
                with pytest.raises(ServiceValidationError):
                    await ctrl.short(action)
                continue
            await ctrl.short(action)
            assert frames(client)[-2:] == [
                f"6e0100{code:02x}{(0x6F + code) & 255:02x}",
                "6e01006edd",
            ]
    with pytest.raises(ServiceValidationError):
        await ctrl.program_memory(2)


async def test_motors_refresh_then_release_without_end(hass):
    ctrl, _, client, _ = make_controller(hass)
    with virtual_time(FakeClock()):
        for key, codes in MOTORS.items():
            for up in (True, False):
                client.write_gatt_char.reset_mock()
                await ctrl.move(key, up)
                assert len(frames(client)) == 3
                assert all(bytes.fromhex(raw)[3] == codes[0 if up else 1] for raw in frames(client))
                assert "6e01006edd" not in frames(client)
        await ctrl.stop_all()
        assert len(frames(client)) == 3


async def test_startup_and_alarm_timing(hass):
    ctrl, _, client, _ = make_controller(hass)
    clock = FakeClock()
    writes = []

    async def record(_char, data, **_kwargs):
        writes.append((round(clock.now * 1000), data.hex()))

    client.write_gatt_char.side_effect = record
    session = SimpleNamespace(async_start_notify=ctrl.start_notify)
    with (
        virtual_time(clock),
        patch(
            "custom_components.adjustable_bed.beds.ronco_motion.controller.dt_util.now",
            return_value=request(True).reference_time,
        ),
    ):
        await ctrl.async_on_connect(session)
        assert writes == [(0, STARTUP[0].hex()), (300, STARTUP[1].hex()), (600, STARTUP[2].hex())]
        assert round(clock.now * 1000) == 900
        writes.clear()
        await ctrl.configure_alarm(request(True))
        assert writes == [(900, "6e050d0080"), (1020, "6e060245bb")]
        assert round(clock.now * 1000) == 1140
        writes.clear()
        await ctrl.configure_alarm(request(False))
        assert writes == [(1140, "6e05000073"), (1260, "6e06000074")]


async def test_alarm_countdown_accounts_for_admission_delay(hass):
    ctrl, _, client, _ = make_controller(hass)
    alarm = AlarmRequest(
        enabled=True,
        hour=7,
        minute=5,
        wake_action="zero_g",
        reference_time=datetime.fromisoformat("2026-11-27T07:00:30+01:00"),
    )
    with (
        virtual_time(FakeClock()),
        patch(
            "custom_components.adjustable_bed.beds.ronco_motion.controller.dt_util.now",
            return_value=datetime.fromisoformat("2026-11-27T07:01:10+01:00"),
        ),
    ):
        await ctrl.configure_alarm(alarm)
    assert frames(client) == ["6e05040077", "6e060045b9"]


async def test_startup_replies_survive_polling_refresh_until_session_end(hass):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl, owner, client, state = make_controller(hass)
    owner._controller = ctrl
    owner._diagnostic_poll_task = None
    owner._diagnostic_advertisement_task = None
    owner._cancel_diagnostic_polling.side_effect = lambda: (
        AdjustableBedCoordinator._cancel_diagnostic_polling(owner)
    )

    async def reply(_char, _data, **_kwargs):
        callback = client.start_notify.call_args.args[1]
        callback(None, bytearray.fromhex("6e07010177"))
        callback(None, bytearray.fromhex("6e90d18000"))

    client.write_gatt_char.side_effect = reply
    with virtual_time(FakeClock()):
        await ctrl.async_on_connect(SimpleNamespace(async_start_notify=ctrl.start_notify))
    AdjustableBedCoordinator._refresh_diagnostic_polling_schedule(owner)
    assert ctrl.protocol_diagnostics["received"] == {"alarm": "added", "music_volume": -128}
    assert state[ALARM] == "added"
    await ctrl.stop_notify()
    assert ctrl.protocol_diagnostics["received"] == {}
    assert state[ALARM] is None


@pytest.mark.parametrize("operation", ("move", "alarm", "startup", "short"))
@pytest.mark.parametrize("cancel", ("event", "task", "replacement"))
async def test_inflight_write_is_settled_and_remaining_actions_do_not_leak(hass, operation, cancel):
    ctrl, owner, client, _ = make_controller(hass)
    began, finish = asyncio.Event(), asyncio.Event()

    async def blocked(_char, _data, **_kwargs):
        if len(frames(client)) == 1:
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = blocked
    actions = {
        "move": lambda: ctrl.move_head_up(),
        "alarm": lambda: ctrl.configure_alarm(request(False)),
        "startup": lambda: ctrl.async_on_connect(
            SimpleNamespace(async_start_notify=ctrl.start_notify)
        ),
        "short": lambda: ctrl.preset_flat(),
    }
    replacement = None
    task = asyncio.create_task(actions[operation]())
    await began.wait()
    if cancel == "event":
        owner.cancel_command.set()
    elif cancel == "task":
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    else:
        _, _, replacement, _ = make_controller(hass)
        owner.client = replacement
    finish.set()
    if cancel == "task":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    # Only SHORT owns a cleanup frame after an attempted payload.
    expected = 2 if operation == "short" and cancel != "replacement" else 1
    assert len(frames(client)) == expected
    if expected == 2:
        assert frames(client)[-1] == "6e01006edd"
    if cancel == "replacement":
        assert replacement is not None
        replacement.write_gatt_char.assert_not_awaited()


async def test_cancelled_action_waiting_for_ble_lock_writes_nothing(hass):
    ctrl, owner, client, _ = make_controller(hass)
    await ctrl.ble_lock.acquire()
    task = asyncio.create_task(ctrl.preset_flat())
    await asyncio.sleep(0)
    owner.cancel_command.set()
    ctrl.ble_lock.release()
    await task
    assert frames(client) == []


async def test_failures_are_not_retried_and_short_trailer_is_attempted(hass):
    ctrl, _, client, _ = make_controller(hass)
    client.write_gatt_char.side_effect = [ConnectionError("failed"), None]
    with virtual_time(FakeClock()), pytest.raises(ConnectionError, match="failed"):
        await ctrl.preset_flat()
    assert frames(client) == ["6e010031a0", "6e01006edd"]


async def test_received_state_is_typed_and_stale_callbacks_ignored(hass):
    ctrl, owner, client, state = make_controller(hass)
    await ctrl.start_notify()
    callback = client.start_notify.call_args.args[1]
    callback(None, bytearray.fromhex("6e07010177"))
    callback(None, bytearray.fromhex("6e90d18000"))
    received = ctrl.protocol_diagnostics["received"]
    assert isinstance(received, dict)
    assert state[ALARM] == "added" and received["music_volume"] == -128
    owner.client = MagicMock()
    callback(None, bytearray.fromhex("6e07010278"))
    assert state[ALARM] == "added"
    assert parse_notification(bytes.fromhex("6e90d17f006e90d2ff00ff")) == [
        {"music_volume": 127},
        {"music_intensity": -1},
    ]
    assert parse_notification(bytes.fromhex("6e07010177ff")) == []


async def test_fresh_fallback_drops_incomplete_known_roles(hass):
    ctrl, _, client, _ = make_controller(hass, transport=1)
    service = client.services[0]
    service.characteristics[0].properties = ["write", "notify"]
    service.characteristics.pop()
    with pytest.raises(ConnectionError, match="incomplete"):
        await ctrl.start_notify()
    service.characteristics.append(SimpleNamespace(uuid="fallback", properties=["indicate"]))
    await ctrl.start_notify()
    assert ctrl._link.notify.uuid == "fallback"


def test_setup_is_searchable_explicit_and_side_owned():
    assert get_variants_for_bed_type("ronco_motion") == {p.key: p.label for p in PROFILES.values()}
    assert not is_valid_variant_for_bed_type("ronco_motion", "auto")
    profile = setup_profile("ronco_motion")
    assert profile.questions[0].searchable
    assert CONF_MOTOR_COUNT in hidden_generic_fields("ronco_motion", "premium")
    assert per_side_profile("ronco_motion", "premium").variant_owned
    assert accepts_name("qRrM1") and accepts_name("K8RM-bed")
    assert not accepts_name("QRRM") and not accepts_name("RC-bed")


@pytest.mark.parametrize(
    "selected, expected", (("richmat", "bedtech"), ("bedtech", None), ("ronco_motion", None))
)
def test_shared_name_is_an_opt_in_hint_for_setup_and_recommendations(selected, expected):
    from custom_components.adjustable_bed.config_flow import _confident_auto_detect
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_detection import _make_service_info

    info = _make_service_info(
        "QRRM157738",
        service_uuids=["0000fee9-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={19543: bytes.fromhex("54307651")},
    )
    detected = detect_bed_type_detailed(info)
    assert "ronco_motion" in detected.ambiguous_types
    assert _confident_auto_detect(detected) == "bedtech"
    result = recommend_profile(
        {
            "bed_type": selected,
            "protocol_variant": "premium" if selected == "ronco_motion" else "auto",
        },
        info,
        {},
    )
    if expected is None:
        assert result is None
    else:
        assert result is not None and result.suggested == expected


async def test_app_row_leads_to_explicit_searchable_layout(hass, mock_bluetooth_service_info):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _bed_type_selector,
    )
    from tests.form_helpers import start_new_bed

    assert "ronco_motion" in _bed_type_selector(None).rows().values()
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, "picked", "ronco_motion")
    assert result["step_id"] == "profile_questions"
    marker = next(key for key in result["data_schema"].schema if key == "protocol_variant")
    choices = result["data_schema"].schema[marker]
    assert set(choices.rows().values()) == {"economy", "premium"}


@pytest.mark.parametrize("interrupt", ("cancel", "replacement"))
async def test_alarm_first_frame_interruption_reports_partial_delivery(hass, interrupt):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        Delivery,
        delivered,
    )

    ctrl, owner, client, _ = make_controller(hass)
    context = CommandContext(
        object(),
        owner.cancel_command,
        0,
        "alarm",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    observed = []

    async def interrupt_write(*_args, **_kwargs):
        if interrupt == "cancel":
            owner.cancel_command.set()
        else:
            owner.client = MagicMock()

    client.write_gatt_char.side_effect = interrupt_write
    token = _CURRENT_COMMAND_CONTEXT.set(context)
    try:
        with delivered(observed.append):
            await ctrl.configure_alarm(request(False))
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(token)
    assert frames(client) == ["6e05000073"]
    assert observed == [Delivery.PARTIAL]


@pytest.mark.parametrize("interrupt_at", ("first_write", "first_pause", "second_write"))
async def test_alarm_task_cancellation_reports_actual_delivery(hass, interrupt_at, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        Delivery,
        delivered,
    )

    ctrl, owner, client, _ = make_controller(hass)
    context = CommandContext(
        object(),
        owner.cancel_command,
        0,
        "alarm",
        CommandKind.COMMAND,
        None,
        frozenset({"configuration"}),
    )
    entered, finish = asyncio.Event(), asyncio.Event()
    observed = []
    writes = 0
    pauses = 0

    async def write(*_args, **_kwargs):
        nonlocal writes
        writes += 1
        if interrupt_at == ("first_write" if writes == 1 else "second_write"):
            entered.set()
            await finish.wait()

    async def pause(*_args, **_kwargs):
        nonlocal pauses
        pauses += 1
        if interrupt_at == "first_pause" and pauses == 1:
            entered.set()
            await finish.wait()
        return not owner.cancel_command.is_set()

    async def operation():
        token = _CURRENT_COMMAND_CONTEXT.set(context)
        try:
            with delivered(observed.append):
                await ctrl.configure_alarm(request(False))
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)

    client.write_gatt_char.side_effect = write
    monkeypatch.setattr(ctrl, "_pause", pause)
    task = asyncio.create_task(operation())
    await entered.wait()
    owner.cancel_command.set()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    all_frames = ["6e05000073", "6e06000074"]
    assert frames(client) == (all_frames if interrupt_at == "second_write" else all_frames[:1])
    assert observed == [Delivery.SENT if interrupt_at == "second_write" else Delivery.PARTIAL]


@pytest.mark.parametrize("scenario", ("ronco_motion", "ronco_motion:premium:0"))
@pytest.mark.parametrize("end", ("expire", "stop"))
async def test_leased_hold_outlives_finite_pulses_and_ends_without_a_packet(scenario, end):
    from tests.hold_lease_wire import intervals, leased_hold

    async def move(controller):
        await controller.motor_control_specs[0].open_fn(controller)

    wire = await leased_hold(scenario, move, end_after_s=5, end=end)
    assert len(wire.held) > wire.pulse_count
    assert {write.data.hex() for write in wire.held} == {"6e01002493"}
    assert intervals(wire.held) == {107}
    assert wire.after == ()


async def test_alarm_service_uses_selected_side_and_validates_all_targets(hass):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    await async_register_services(hass)
    ctrl, owner, client, _ = make_controller(hass)
    other_ctrl, other, other_client, _ = make_controller(hass)
    for coordinator, controller in ((owner, ctrl), (other, other_ctrl)):
        coordinator.controller = controller
        coordinator.capability_controller = controller
        coordinator.controller_side = None
        coordinator.bed_type = "ronco_motion"
        coordinator.stop_epoch = 0
        coordinator.pairlink_peripheral = False

    async def execute(command, **_kwargs):
        await command(ctrl)

    async def execute_other(command, **_kwargs):
        await command(other_ctrl)

    owner.async_execute_controller_command = AsyncMock(side_effect=execute)
    other.async_execute_controller_command = AsyncMock(side_effect=execute_other)
    parent = MagicMock(spec=PairedBedCoordinator)
    children = {"left": owner, "right": other}
    parent.children = children
    parent.child_for_side.side_effect = children.get
    parent.targets_for.side_effect = lambda side: (
        list(children.items()) if side == "both" else [(side, children[side])]
    )
    parent.pair_cancel_generation.return_value = (0,)

    async def execute_pair(command, *, side, **kwargs):
        for selected in children if side == "both" else [side]:
            await children[selected].async_execute_controller_command(command)

    parent.async_execute_controller_command = AsyncMock(side_effect=execute_pair)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(parent, "left")], []),
    ) as resolve:
        with virtual_time(FakeClock()):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": "bed", "side": "left", "enabled": False},
                blocking=True,
            )
        assert resolve.call_args.args[2] == "left"
        assert frames(client) == ["6e05000073", "6e06000074"]
        other_client.write_gatt_char.assert_not_awaited()
        client.write_gatt_char.reset_mock()
        parent.async_execute_controller_command.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {"device_id": "bed", "enabled": True, "time": "07:15:00", "wake_action": "tv"},
                blocking=True,
            )
        parent.async_execute_controller_command.assert_not_awaited()
        client.write_gatt_char.assert_not_awaited()
    # Both sides are preflighted before either is changed.
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(parent, "both")], []),
        ),
        patch.object(
            other_ctrl, "validate_alarm", side_effect=ServiceValidationError("unavailable")
        ),
    ):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
            )
        client.write_gatt_char.assert_not_awaited()
        other_client.write_gatt_char.assert_not_awaited()
