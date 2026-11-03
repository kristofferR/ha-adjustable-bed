"""Accepted row063 byte vectors and direct-BLE state/lifecycle consequences.

BF revision01 dff12e6a…, Cherish report 17910423…, cluster db1b2bc5….
Expected bytes below are artifact values, not calls to the production builders.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.bf_cherish import (
    NOTIFY_UUID,
    WRITE_UUID,
    BfCherishController,
    alarm_frame,
    control_frame,
    finish,
    query_frame,
)
from custom_components.adjustable_bed.bf_cherish_services import register_services
from custom_components.adjustable_bed.const import (
    BED_TYPE_BF,
    BED_TYPE_CHERISH,
    CONF_MOTOR_COUNT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import _create_from_registry
from custom_components.adjustable_bed.detection import get_bed_type_options

NOW = datetime(2026, 11, 1, 7, 5, 9, tzinfo=UTC)  # Sunday


def characteristic(uuid=WRITE_UUID, handle=1, properties=None):
    return SimpleNamespace(
        uuid=uuid,
        service_uuid="0000ffe0-0000-1000-8000-00805f9b34fb",
        handle=handle,
        properties=properties if properties is not None else ["write"],
    )


def make_controller(hass, cherish=False):
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.services = [
        SimpleNamespace(
            characteristics=[characteristic(), characteristic(NOTIFY_UUID, 2, ["notify"])]
        )
    ]
    owner = MagicMock(hass=hass, address="AA:BB:CC:DD:EE:63", client=client)
    owner.cancel_command = asyncio.Event()
    owner.motor_pulse_count = 2
    owner.motor_pulse_delay_ms = 0
    return BfCherishController(owner, cherish=cherish), owner, client


def frames(client):
    return [args.args[1].hex().upper() for args in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    ("cherish", "name", "expected"),
    [
        (False, "zero_g", "E5FE160100000104"),
        (False, "flat", "E5FE160100000203"),
        (False, "anti_snore", "E5FE160100000401"),
        (False, "memory_1", "E5FE1601000008FD"),
        (False, "memory_2", "E5FE1601000009FC"),
        (True, "zero_g", "E5FE1621000001E4"),
        (True, "flat", "E5FE1621000002E3"),
        (True, "anti_snore", "E5FE1621000003E2"),
        (True, "memory_1", "E5FE1621000004E1"),
        (True, "memory_2", "E5FE1621000006DF"),
    ],
)
async def test_preset_vectors_and_second_tap_stop(hass, cherish, name, expected):
    ctrl, _, client = make_controller(hass, cherish)
    await ctrl.tap_preset(name)
    assert frames(client) == [expected]
    await ctrl.tap_preset(name)
    assert frames(client)[-1] == ("E5FE1621000000E5" if cherish else "E5FE160100000005")
    await ctrl.tap_preset(name)
    assert frames(client)[-1] == expected


@pytest.mark.parametrize(
    ("cherish", "slot", "expected"),
    [
        (False, 1, "E5FE1620000008DE"),
        (False, 2, "E5FE1620000009DD"),
        (True, 1, "E5FE1621000014D1"),
        (True, 2, "E5FE1621000016CF"),
    ],
)
async def test_long_save_preserves_shared_count_and_suppresses_initial_same_slot(
    hass, cherish, slot, expected
):
    ctrl, _, client = make_controller(hass, cherish)
    await ctrl.program_memory(slot)
    await ctrl.preset_memory(slot)
    assert frames(client) == [expected]
    assert ctrl.state.count == -1
    await ctrl.preset_flat()
    await ctrl.program_memory(slot)
    await ctrl.preset_memory(slot)
    assert frames(client)[-1] == ("E5FE1621000000E5" if cherish else "E5FE160100000005")
    with pytest.raises(ValueError):
        await ctrl.program_memory(3)


@pytest.mark.parametrize(
    ("control", "expected"),
    [
        ("back_up", "E5FE160000000105"),
        ("back_down", "E5FE160000000204"),
        ("legs_up", "E5FE160000000402"),
        ("legs_down", "E5FE1600000008FE"),
        ("head_up", "E5FE1600000010F6"),
        ("head_down", "E5FE1600000020E6"),
        ("both_up", "E5FE160000000501"),
        ("both_down", "E5FE160000000AFC"),
    ],
)
async def test_movement_artifact_vectors_and_fixed_hold_interval(hass, control, expected):
    ctrl, _, client = make_controller(hass, control.startswith("both"))
    with patch(
        "custom_components.adjustable_bed.beds.base.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        await ctrl.move(control)
    assert frames(client) == [expected, expected, "E5FE160000000006"]
    assert 0 < sleep.call_args.args[0] <= 0.2
    assert all(call.kwargs == {"response": True} for call in client.write_gatt_char.call_args_list)


@pytest.mark.parametrize("failure", ["cancel_event", "task_cancel", "write_error"])
async def test_move_cleanup_uses_fresh_event_even_when_first_write_fails(hass, failure):
    ctrl, owner, client = make_controller(hass)

    async def write(target, data, **kwargs):
        if data.hex().upper() != "E5FE160000000006":
            if failure == "cancel_event":
                owner.cancel_command.set()
            elif failure == "task_cancel":
                raise asyncio.CancelledError
            else:
                raise BleakError("transport failure")

    client.write_gatt_char.side_effect = write
    if failure == "cancel_event":
        await ctrl.move_back_up()
    else:
        with pytest.raises(asyncio.CancelledError if failure == "task_cancel" else BleakError):
            await ctrl.move_back_up()
    assert frames(client)[-1] == "E5FE160000000006"


async def test_stop_attempts_both_artifact_release_frames(hass):
    ctrl, owner, client = make_controller(hass)
    owner.cancel_command.set()
    client.write_gatt_char.side_effect = [BleakError("movement release failed"), None]
    with pytest.raises(BleakError):
        await ctrl.stop_all()
    assert frames(client) == ["E5FE160000000006", "E5FE160100000005"]


async def test_gatt_duplicate_roles_properties_and_recovery(hass):
    ctrl, _, client = make_controller(hass)
    first, last = characteristic(handle=11), characteristic(handle=31)
    client.services = [
        SimpleNamespace(characteristics=[first]),
        SimpleNamespace(characteristics=[last]),
    ]
    await ctrl.preset_flat()
    assert client.write_gatt_char.call_args.args[0] is last
    client.write_gatt_char.reset_mock()
    last.properties = ["write-without-response"]
    with pytest.raises(ConnectionError):
        await ctrl.preset_zero_g()
    assert not client.write_gatt_char.called
    last.properties = ["write"]
    client.is_connected = False
    with pytest.raises(ConnectionError):
        await ctrl.preset_zero_g()
    client.is_connected = True
    await ctrl.preset_zero_g()
    assert frames(client) == ["E5FE160100000104"]


async def test_cancelled_and_failed_presets_do_not_advance_count(hass):
    ctrl, owner, client = make_controller(hass)
    owner.cancel_command.set()
    await ctrl.preset_flat()
    assert not client.write_gatt_char.called
    assert ctrl.state.count == -1
    owner.cancel_command.clear()
    client.write_gatt_char.side_effect = BleakError("write rejected")
    with pytest.raises(BleakError):
        await ctrl.preset_flat()
    assert ctrl.state.count == -1


async def test_notification_length_prefix_selector_and_member_gates(hass):
    ctrl, _, client = make_controller(hass)
    sender = characteristic(NOTIFY_UUID, 2, ["notify"])
    for data in (b"", b"\xe2", b"\xe2\xfe\x16", bytes.fromhex("E2FE16010500000000"), bytes(12)):
        ctrl._notification(sender, bytearray(data))
    assert ctrl.state.alarm_enabled is None
    ctrl._notification(sender, bytearray.fromhex("E2FE161E0800000000F8"))
    assert (ctrl.state.alarm_hour, ctrl.state.alarm_minute, ctrl.state.alarm_memory) == (
        8,
        30,
        "memory_1",
    )
    ctrl._notification(sender, bytearray.fromhex("E2FE163C180000000088"))
    assert ctrl.state.alarm_enabled is True  # Preserve the artifact's AND and hour>24 boundary.
    assert ctrl.state.alarm_memory == "memory_1"  # unknown selector retains previous choice
    with patch("custom_components.adjustable_bed.beds.bf_cherish.dt_util.now", return_value=NOW):
        ctrl._notification(sender, bytearray.fromhex("E2FE16FFFF00000000FF"))
    assert (ctrl.state.alarm_enabled, ctrl.state.alarm_hour, ctrl.state.alarm_minute) == (
        False,
        7,
        5,
    )
    ctrl, _, _ = make_controller(hass, True)
    ctrl._notification(sender, bytearray.fromhex("E2FE161E0800000000F8"))
    assert ctrl.state.alarm_enabled is None
    await ctrl.start_notify()
    await ctrl.stop_notify()


@pytest.mark.parametrize(
    ("cherish", "enabled", "memory", "hour", "minute", "expected"),
    [
        (True, True, "memory_1", 8, 30, "EAFE160905071E08FFFFFF04C5"),
        (True, False, "none", 0, 0, "EAFE16090507FFFFFFFFFFFFF2"),
        (False, True, "memory_1", 8, 30, "EBFE160905071E0800010000F8CC"),
    ],
)
def test_alarm_artifact_vectors(cherish, enabled, memory, hour, minute, expected):
    assert (
        alarm_frame(cherish, NOW, enabled=enabled, hour=hour, minute=minute, memory=memory)
        .hex()
        .upper()
        == expected
    )


@pytest.mark.parametrize("cherish", [False, True])
async def test_disable_sequence_retains_schedule_and_resamples_clock(hass, cherish):
    ctrl, _, client = make_controller(hass, cherish)
    with patch("custom_components.adjustable_bed.beds.bf_cherish.dt_util.now", return_value=NOW):
        await ctrl.configure_clock_alarm(enabled=True, hour=8, minute=30, preset="memory_2")
        first = frames(client)[0]
        await ctrl.configure_clock_alarm(enabled=False, hour=0, minute=0, preset="none")
    assert frames(client)[-1] == "EAFE16090507FFFFFFFFFFFFF2"
    assert len(frames(client)) == 3
    assert frames(client)[1].startswith("EAFE16" if cherish else "EBFE16")
    assert (ctrl.state.alarm_hour, ctrl.state.alarm_minute, ctrl.state.alarm_memory) == (
        8,
        30,
        "memory_2",
    )
    if cherish:
        restored = ctrl.persisted_app_state
        ctrl.restore_persisted_app_state(restored)
        assert ctrl.state.alarm_enabled is False
    else:
        await ctrl.query_alarm()
        assert frames(client)[-1].startswith("E2FE16")
    assert first != frames(client)[-1]


def test_alarm_weekday_rollover_and_equal_minute():
    saturday = datetime(2026, 10, 31, 23, 59, 59)
    # BF uses today's weekday at8 and next-day mask at9. Equal minute stays today.
    assert alarm_frame(False, saturday, enabled=True, hour=23, minute=59, memory="none")[
        8:10
    ] == bytes((6, 64))
    assert alarm_frame(False, saturday, enabled=True, hour=0, minute=0, memory="none")[
        8:10
    ] == bytes((6, 1))
    assert query_frame(NOW)[3:7] == bytes((9, 5, 7, 0))


async def test_cherish_massage_sequences_bounds_and_timer_only_behavior(hass):
    ctrl, _, client = make_controller(hass, True)
    with patch(
        "custom_components.adjustable_bed.beds.bf_cherish.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        await ctrl.massage_on()
        assert frames(client) == ["E5FE1610000030C6", "E5FE1610000021D5", "E5FE1610000011E5"]
        assert [c.args[0] for c in sleep.call_args_list] == [0.1, 0.2]
        await ctrl.massage_on()
        assert len(frames(client)) == 3
        await ctrl.massage_intensity_down()  # clamped at1, no write
        assert len(frames(client)) == 3
        await ctrl.massage_intensity_up()
        await ctrl.massage_wave_next()
        assert frames(client)[-2:] == ["E5FE1610000012E4", "E5FE1610000022D4"]
        await ctrl.set_massage_timer(30)
        assert frames(client)[-1] == "E5FE1610000032C4"
        assert ctrl.state.massage_on is False
        with pytest.raises(ValueError):
            await ctrl.set_level("intensity", 3)
        await ctrl.massage_off()
        assert frames(client)[-2:] == ["E5FE1610000010E6", "E5FE1610000020D6"]
        assert (ctrl.state.wave, ctrl.state.intensity, ctrl.state.timer) == (2, 2, 30)


async def test_massage_cancellation_does_not_leave_delayed_start(hass):
    ctrl, owner, client = make_controller(hass, True)

    async def sleep(seconds):
        owner.cancel_command.set()

    with patch("custom_components.adjustable_bed.beds.bf_cherish.asyncio.sleep", side_effect=sleep):
        await ctrl.massage_on()
    assert frames(client) == ["E5FE1610000030C6", "E5FE1610000010E6", "E5FE1610000020D6"]
    assert not ctrl.state.massage_on


async def test_profile_entities_findability_and_light_collision(hass):
    options = get_bed_type_options()
    assert any(x["value"] == BED_TYPE_BF and "BF" in x["label"] for x in options)
    assert any(x["value"] == BED_TYPE_CHERISH and "Cherish" in x["label"] for x in options)
    for cherish, bed_type in ((False, BED_TYPE_BF), (True, BED_TYPE_CHERISH)):
        ctrl, owner, client = make_controller(hass, cherish)
        assert {x.key for x in ctrl.motor_control_specs} == (
            {"back", "legs"} if cherish else {"back", "legs", "head"}
        )
        assert ctrl.supports_memory_presets and ctrl.memory_slot_count == 2
        assert ctrl.auto_enable_massage is cherish and ctrl.supports_lights is cherish
        assert not ctrl.supports_single_address_pairing and not ctrl.supports_position_feedback
        assert CONF_MOTOR_COUNT in hidden_generic_fields(bed_type, "auto")
        assert per_side_profile(bed_type, None) is not None
        created = await _create_from_registry(owner, bed_type)
        assert isinstance(created, BfCherishController) and created.cherish is cherish
        if cherish:
            await ctrl.lights_on()
            await ctrl.lights_off()
            assert frames(client) == ["E5FE1631000001D4", "E5FE1631000000D5"]
        else:
            with pytest.raises(NotImplementedError):
                await ctrl.lights_on()
            assert not client.write_gatt_char.called


async def test_alarm_service_preflight_and_invalid_target_no_write(hass):
    register_services(hass)
    with pytest.raises(ServiceValidationError, match="Choose an alarm time"):
        await hass.services.async_call(
            DOMAIN, "bf_cherish_set_alarm", {"device_id": "missing", "enabled": True}, blocking=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "bf_cherish_set_alarm",
            {"device_id": "missing", "enabled": False},
            blocking=True,
        )


@pytest.mark.parametrize("key", [0, 1, 0x21000016, 0x10000032, -1, 0x100000001])
def test_builder_wrap_checksum_idempotence(key):
    packet = control_frame(key)
    assert sum(packet) & 255 == 255
    assert finish(packet) == packet
    assert int.from_bytes(packet[3:7], "big") == key & 0xFFFFFFFF


@pytest.mark.parametrize(
    ("now", "hour", "minute", "memory", "expected"),
    [
        (datetime(2026, 11, 3, 12, 34, 56), 13, 5, "memory_1", "EBFE1638220C050D02040000F88A"),
        (datetime(2026, 10, 31, 23, 59, 58), 0, 1, "memory_2", "EBFE163A3B17010006010000F973"),
        (datetime(2026, 11, 1, 6, 9, 20), 6, 9, "none", "EBFE16140906090600010000FFCE"),
    ],
)
def test_bf_accepted_alarm_vectors(now, hour, minute, memory, expected):
    assert (
        alarm_frame(False, now, enabled=True, hour=hour, minute=minute, memory=memory).hex().upper()
        == expected
    )


async def test_notify_failure_does_not_gate_commands_and_partial_setup_is_cleaned(hass):
    ctrl, _, client = make_controller(hass)
    client.start_notify.side_effect = BleakError("CCCD write rejected")
    await ctrl.start_notify()
    await ctrl.preset_flat()
    assert frames(client) == ["E5FE160100000203"]
    assert not ctrl._subscriptions
    client.start_notify.side_effect = None
    await ctrl.start_notify()
    await ctrl.stop_notify()
    assert client.stop_notify.call_count == 1


async def test_repeated_cancellation_waits_for_release_before_return(hass):
    ctrl, _, client = make_controller(hass)
    release_started, finish_release = asyncio.Event(), asyncio.Event()

    async def write(target, data, **kwargs):
        if data.hex().upper() == "E5FE160000000006":
            release_started.set()
            await finish_release.wait()
        else:
            raise asyncio.CancelledError

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(ctrl.move_back_up())
    await release_started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client)[-1] == "E5FE160000000006"


async def test_alarm_service_validates_all_profiles_before_serialized_write(hass):
    from custom_components.adjustable_bed.beds.base import SideBoundController

    ctrl, owner, client = make_controller(hass, True)
    target = MagicMock(bed_type=BED_TYPE_CHERISH)
    register_services(hass)

    async def execute(coordinator, side, command, **kwargs):
        assert kwargs == {"cancel_running": False, "resource": "configuration"}
        await command(SideBoundController(ctrl, side))

    async def preflight(targets, capability, label, validate):
        assert capability == "supports_clock_alarm"
        validate(ctrl)
        return []

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(owner, "right")], []),
        ),
        patch("custom_components.adjustable_bed.services._command_targets", return_value=[target]),
        patch(
            "custom_components.adjustable_bed.services._preflight_capability", side_effect=preflight
        ),
        patch("custom_components.adjustable_bed.services._execute_sided", side_effect=execute),
        patch("custom_components.adjustable_bed.beds.bf_cherish.dt_util.now", return_value=NOW),
    ):
        register_services(hass)
        await hass.services.async_call(
            DOMAIN,
            "bf_cherish_set_alarm",
            {
                "device_id": "bed",
                "side": "right",
                "enabled": True,
                "time": "08:30:00",
                "memory": "memory_1",
            },
            blocking=True,
        )
    assert frames(client) == ["EAFE160905071E08FFFFFF04C5"]


@pytest.mark.parametrize(
    ("field", "level", "expected"),
    [
        ("intensity", 1, "E5FE1610000011E5"),
        ("intensity", 2, "E5FE1610000012E4"),
        ("intensity", 3, "E5FE1610000013E3"),
        ("wave", 1, "E5FE1610000021D5"),
        ("wave", 2, "E5FE1610000022D4"),
        ("wave", 3, "E5FE1610000023D3"),
    ],
)
async def test_all_cherish_level_vectors(hass, field, level, expected):
    ctrl, _, client = make_controller(hass, True)
    ctrl.state.massage_on = True
    await ctrl.set_level(field, level)
    assert frames(client) == [expected]


async def test_cherish_twenty_minute_timer_vector(hass):
    ctrl, _, client = make_controller(hass, True)
    await ctrl.set_massage_timer(20)
    assert frames(client) == ["E5FE1610000031C5"]


async def test_last_notify_uuid_pair_controls_consumption_even_if_subscription_failed(hass):
    ctrl, _, client = make_controller(hass)
    early = characteristic(NOTIFY_UUID, 2, ["notify"])
    late = characteristic(NOTIFY_UUID, 9, ["notify"])
    late.service_uuid = "0000ffff-0000-1000-8000-00805f9b34fb"
    client.services += [SimpleNamespace(characteristics=[late])]
    client.start_notify.side_effect = [None, BleakError("last subscription failed")]
    await ctrl.start_notify()
    ctrl._notification(early, bytearray.fromhex("E2FE161E0800000000F8"))
    assert ctrl.state.alarm_enabled is None
    ctrl._notification(late, bytearray.fromhex("E2FE161E0800000000F8"))
    assert ctrl.state.alarm_memory == "memory_1"
    await ctrl.stop_notify()
    assert client.stop_notify.call_count == 1


@pytest.mark.parametrize("cherish", [False, True])
async def test_normal_coordinator_startup_subscribes_with_angle_sensing_disabled(hass, cherish):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl, owner, client = make_controller(hass, cherish)
    startup = SimpleNamespace(
        _controller=ctrl,
        _disable_angle_sensing=True,
        _address=owner.address,
        _bed_type=BED_TYPE_CHERISH if cherish else BED_TYPE_BF,
    )
    await AdjustableBedCoordinator.async_start_notify(startup)
    assert client.start_notify.call_count == 1
    sender, callback = client.start_notify.call_args.args
    callback(sender, bytearray.fromhex("E2FE161E0800000000F8"))
    assert ctrl.state.alarm_enabled is (None if cherish else True)
    await ctrl.stop_notify()


async def test_notify_timeout_keeps_writable_profile_usable(hass):
    ctrl, _, client = make_controller(hass)
    client.start_notify.side_effect = TimeoutError("ESPHome descriptor timeout")
    await ctrl.start_notify()
    assert not ctrl._subscriptions
    await ctrl.preset_flat()
    assert frames(client) == ["E5FE160100000203"]


async def test_actual_cherish_timer_select_retains_commanded_selection_when_disconnected(hass):
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )
    from tests.test_malouf_app_entities import configure_entity_runtime

    ctrl, owner, _ = make_controller(hass, True)
    runtime = configure_entity_runtime(hass, ctrl, BED_TYPE_CHERISH)
    select = AdjustableBedMassageTimerSelect(runtime, MASSAGE_TIMER_DESCRIPTION, [10, 20, 30])
    assert select.current_option == "Off"
    await ctrl.set_massage_timer(20)
    assert select.current_option == "20 min"
    runtime.controller_state = owner.handle_controller_state_updates.call_args.args[0]
    runtime.controller = None
    assert select.current_option == "20 min"
    runtime.controller = ctrl
    with patch("custom_components.adjustable_bed.beds.bf_cherish.asyncio.sleep", new=AsyncMock()):
        await ctrl.massage_on()
        assert select.current_option == "20 min"
        await ctrl.massage_off()
    assert select.current_option == "Off"
    assert ctrl.state.timer == 20  # Off retains the next start's selection.
    runtime.controller_state = owner.handle_controller_state_updates.call_args.args[0]
    runtime.controller = None
    assert select.current_option == "Off"
