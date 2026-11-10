"""Frozen row135 vectors and the Jalon app's reachable BLE behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.adjustable_bed.beds.jalon_bed.controller import (
    TIMER_BUCKET,
    JalonBedController,
    alarm_frame,
)
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.const import CONF_PRODUCT_TYPE
from custom_components.adjustable_bed.profiles import jalon_bed as app
from custom_components.adjustable_bed.profiles.keeson import encode
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.test_controller_contract import _FactoryCoordinator

ROWS = [
    line.split("\t")
    for line in (Path(__file__).parent / "fixtures/jalon_bed/vectors.tsv").read_text().splitlines()
]


@pytest.mark.parametrize("row", ROWS, ids=lambda row: f"{row[0]}:{row[1]}")
def test_frozen_java_vector(row: list[str]) -> None:
    kind, inputs, expected = row[:3]
    if kind in ("control", "model_test"):
        word, model = map(int, inputs.split(","))
        actual = codec.frame(word & 0xFFFFFFFF, header=0xE6, side=model & 255)
    elif kind == "alarm":
        actual = codec.alarm_table(3, bytes(int(value) & 255 for value in inputs.split(",")))
    elif kind == "unused_rename":
        # Dead helper vectors check only codec compatibility, not feature exposure.
        actual = codec.rename(bytes.fromhex(inputs)[:15])
    elif kind == "current_time":
        fields = bytes.fromhex(expected)[3:9]
        actual = codec.clock(datetime(fields[0] + 1900, fields[1] + 1, *fields[2:]))
    else:
        assert kind == "parser"
        status = codec.parse_jalon_status(bytes.fromhex(expected))
        assert f"{status.timer_minutes},{status.light_value}" == row[3]
        return
    assert actual.hex() == expected


def controller(layout: str = "40") -> JalonBedController:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[CONF_PRODUCT_TYPE] = layout
    coordinator.forward_controller_state_updates = MagicMock()
    return JalonBedController(coordinator)


@pytest.mark.parametrize("layout,axes", [(key, value.axes) for key, value in app.LAYOUTS.items()])
async def test_layout_controls_and_word_model(layout: str, axes: tuple[str, ...]) -> None:
    ctrl = controller(layout)
    assert tuple(spec.key for spec in ctrl.motor_control_specs) == axes
    ctrl.write_command = AsyncMock()
    for axis in axes:
        for up in (True, False):
            await ctrl.move_axis(axis, up)
            calls = ctrl.write_command.call_args_list[-3:]
            assert calls[0].args[0].hex() == "e6fe16000000000005"
            assert calls[0].kwargs["repeat_count"] == calls[2].kwargs["repeat_count"] == 3
            assert calls[1].args[0] == encode(app.PROFILE, app.MOTORS[axis][0 if up else 1])
            assert calls[1].kwargs["repeat_delay_ms"] == 100
            assert calls[1].args[0][7] == 0
    assert ctrl.memory_slot_count == 2 and ctrl.supports_memory_presets
    assert not ctrl.supports_memory_programming
    assert not ctrl.supports_single_address_pairing
    assert not ctrl.execution.concurrent
    assert not ctrl.supports_position_feedback


async def test_movement_cancel_still_releases_with_fresh_event() -> None:
    ctrl = controller()

    async def write(frame, **kwargs):
        if frame == encode(app.PROFILE, 1):
            ctrl._coordinator.cancel_command.set()
            raise asyncio.CancelledError

    ctrl.write_command = AsyncMock(side_effect=write)
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_back_up()
    release = ctrl.write_command.call_args
    assert release.args[0] == encode(app.PROFILE, 0)
    assert release.kwargs["repeat_count"] == 3
    assert not release.kwargs["cancel_event"].is_set()
    ctrl.write_command.reset_mock()
    await ctrl.stop_all()  # STOP never depends on an active timer or cancel gate.
    ctrl.write_command.assert_awaited_once()


@pytest.mark.parametrize("name,word", list(app.PRESETS.items()))
async def test_preset_taps_and_holds(name: str, word: int) -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    await ctrl.preset(name)
    assert ctrl.write_command.call_args_list[0].args[0] == encode(app.PROFILE, word)
    assert ctrl.write_command.call_args_list[0].kwargs["repeat_count"] == 3
    assert ctrl.write_command.call_args.kwargs["repeat_count"] == 1
    ctrl.write_command.reset_mock()
    await ctrl.hold_control(name, 8000)
    ctrl.write_command.assert_awaited_once_with(
        encode(app.PROFILE, word), repeat_count=80, repeat_delay_ms=100
    )
    ctrl.write_command.reset_mock()
    await ctrl.preset_flat()
    assert ctrl.write_command.call_args_list[0].kwargs["repeat_count"] == 2
    with pytest.raises(NotImplementedError):
        await ctrl.program_memory(1)


async def test_combined_gesture_and_cancel_have_no_invented_stop() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await ctrl.hold_control("flat_zero_g", 8000)
    assert ctrl.write_command.await_count == 1
    assert ctrl.write_command.call_args.args[0].hex() == "e6fe160010000800ed"


@pytest.mark.parametrize("word", [*app.MASSAGE.values(), app.LIGHT])
async def test_utility_bursts(word: int) -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    await ctrl._burst(word)
    assert ctrl.write_command.call_args_list[0].args[0] == encode(app.PROFILE, word)
    assert ctrl.write_command.call_args_list[0].kwargs["repeat_count"] == 3
    assert ctrl.write_command.call_args.kwargs["repeat_count"] == 2


@pytest.mark.parametrize(
    "days,hour,minute,expected_mask",
    [
        ([0, 1, 2, 3, 4], 6, 30, 0xBE),
        (list(range(7)), 6, 30, 0xFF),
        ([], 6, 30, 2),
        ([], 6, 29, 4),
        ([], 6, 31, 2),
    ],
)
def test_alarm_selection_and_next_day(days, hour, minute, expected_mask) -> None:
    now = datetime(2026, 11, 9, 6, 29, 55)  # Monday
    frame = alarm_frame(
        enabled=True, weekdays=days, hour=hour, minute=minute, preset="memory_1", now=now
    )
    assert frame[3:7] == bytes((hour, minute, expected_mask, 17))


@pytest.mark.parametrize("mode,value", list(app.WAKE_MODES.items()))
async def test_clock_schedule_and_disable_provenance(mode: str, value: int) -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    now = datetime(2026, 11, 10, 5, 40, 0)
    with (
        patch.object(dt_util, "now", return_value=now),
        patch(
            "custom_components.adjustable_bed.beds.jalon_bed.controller.asyncio.sleep",
            new_callable=AsyncMock,
        ) as sleep,
    ):
        await ctrl.configure_clock_alarm(
            enabled=True, weekdays=[0, 1, 2, 3, 4], hour=7, minute=45, preset=mode
        )
    writes = ctrl.write_command.call_args_list
    assert writes[0].args[0].hex() == "e780017e0a0a052800d8"
    assert writes[1].args[0] == codec.alarm_table(3, bytes((7, 45, 0xBE, value)))
    sleep.assert_awaited_once_with(0.1)
    assert writes[2].args[0] == encode(app.PROFILE, 0)
    ctrl.write_command.reset_mock()
    await ctrl.configure_clock_alarm(enabled=False, weekdays=[], hour=23, minute=59, preset=mode)
    assert ctrl.write_command.call_args_list[0].args[0].hex() == "ed80030000000000000000000000008f"
    assert ctrl.write_command.call_args_list[0].kwargs["repeat_count"] == 2
    assert ctrl.write_command.await_count == 2  # no time sync


def test_notification_session_assembly_and_signed_light() -> None:
    ctrl = controller()
    sender = SimpleNamespace(handle=1)
    ctrl._notify_char = sender
    ctrl.forward_controller_state_updates = MagicMock()
    prefix = bytes.fromhex("f4fe16") + bytes(15) + b"\x40\x03"
    ctrl._notification(sender, bytearray(prefix))
    ctrl._notification(sender, bytearray(3))
    ctrl.forward_controller_state_updates.assert_called_once_with(
        TIMER_BUCKET(30), UNDER_BED_LIGHTS_ON(True)
    )
    ctrl.forward_controller_state_updates.reset_mock()
    ctrl._notification(sender, bytearray(3))  # stale prefix reuse is deliberately refused
    ctrl.forward_controller_state_updates.assert_not_called()
    raw = bytearray(16)
    raw[13] = 0xC0
    raw[14] = 0xF2
    ctrl._notification(sender, raw)
    ctrl.forward_controller_state_updates.assert_called_once_with(
        TIMER_BUCKET(20), UNDER_BED_LIGHTS_ON(False)
    )
    ctrl._notification(sender, bytearray(prefix))
    ctrl.on_disconnect()
    assert ctrl._prefix is None and ctrl._notify_char is None
    ctrl.forward_controller_state_updates.assert_called_with(
        TIMER_BUCKET(None), UNDER_BED_LIGHTS_ON(None)
    )


async def test_gatt_admission_fixed_services_properties_and_no_startup_writes() -> None:
    ctrl = controller()
    write = SimpleNamespace(properties=["write"], uuid=ctrl.control_characteristic_uuid)
    notify = SimpleNamespace(handle=2)
    service = SimpleNamespace(
        uuid="0000ffe5-0000-1000-8000-00805f9b34fb", get_characteristic=lambda uuid: write
    )
    notify_service = SimpleNamespace(
        uuid="0000ffe0-0000-1000-8000-00805f9b34fb", get_characteristic=lambda uuid: notify
    )
    client = SimpleNamespace(
        is_connected=True,
        services=[service, notify_service],
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    ctrl._coordinator.client = client
    ctrl._write_gatt_with_retry = AsyncMock()
    await ctrl.start_notify()
    ctrl._write_gatt_with_retry.assert_not_awaited()
    await ctrl.write_command(encode(app.PROFILE, 1))
    assert ctrl._write_gatt_with_retry.call_args.kwargs["response"] is True
    write.properties = ["write-without-response"]
    await ctrl.write_command(encode(app.PROFILE, 1))
    assert ctrl._write_gatt_with_retry.call_args.kwargs["response"] is False
    service.uuid = "wrong-service"
    with pytest.raises(ConnectionError, match="requires FFE9"):
        await ctrl.write_command(encode(app.PROFILE, 1))
    await ctrl.stop_notify()
    assert ctrl._notify_char is None


async def test_alarm_disconnect_during_delay_cannot_write_into_replacement_session() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()

    async def disconnect(_delay):
        ctrl.on_disconnect()

    with (
        patch(
            "custom_components.adjustable_bed.beds.jalon_bed.controller.asyncio.sleep",
            side_effect=disconnect,
        ),
        pytest.raises(ConnectionError, match="session ended"),
    ):
        await ctrl.configure_clock_alarm(enabled=True, weekdays=[], hour=7, minute=0, preset="none")
    assert ctrl.write_command.await_count == 1  # clock only, no stale alarm or STOP


def test_late_notifications_from_old_session_are_ignored() -> None:
    ctrl = controller()
    sender = SimpleNamespace(handle=1)
    ctrl._notify_char = sender
    ctrl._session = 2
    ctrl.forward_controller_state_updates = MagicMock()
    ctrl._notification(sender, bytearray(10), session=1)
    ctrl.forward_controller_state_updates.assert_not_called()


async def test_light_on_off_requires_feedback_and_never_assumes_state() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    with pytest.raises(ValueError, match="unknown"):
        await ctrl.lights_on()
    ctrl.write_command.assert_not_awaited()
    ctrl._coordinator.controller_state[UNDER_BED_LIGHTS_ON] = True
    await ctrl.lights_on()
    ctrl.write_command.assert_not_awaited()
    await ctrl.lights_off()
    assert ctrl.write_command.call_args_list[0].args[0] == encode(app.PROFILE, app.LIGHT)
    assert ctrl._coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True


def test_setup_owns_layout_capabilities_and_side_fields() -> None:
    from custom_components.adjustable_bed.const import (
        BED_TYPE_JALON_BED,
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
    )
    from custom_components.adjustable_bed.pairing import side_owned_profile_fields
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES

    profile = SETUP_PROFILES[BED_TYPE_JALON_BED]
    for layout, motors in [("20", 2), ("30", 3), ("31", 3), ("40", 4)]:
        data = profile.staged({CONF_BED_TYPE: BED_TYPE_JALON_BED}, {CONF_PRODUCT_TYPE: layout})
        data.update(profile.settled(data))
        assert data[CONF_MOTOR_COUNT] == motors
        assert data[CONF_HAS_MASSAGE] is True
        assert data[CONF_DISABLE_ANGLE_SENSING] is True
        assert data[CONF_MOTOR_PULSE_DELAY_MS] == 100
    assert CONF_PRODUCT_TYPE in side_owned_profile_fields({CONF_BED_TYPE: BED_TYPE_JALON_BED})


async def test_alarm_service_registered_schema_and_sided_dispatch(hass) -> None:
    from custom_components.adjustable_bed.const import BED_TYPE_JALON_BED, DOMAIN, SIDE_RIGHT
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    ctrl = controller()
    ctrl.configure_clock_alarm = AsyncMock()
    target = MagicMock(spec=AdjustableBedCoordinator)
    target.name = "Jalon bed"
    target.bed_type = BED_TYPE_JALON_BED
    target.capability_controller = ctrl
    target.controller_side = None

    async def execute(command, **kwargs):
        await command(ctrl)

    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    pair = MagicMock(spec=PairedBedCoordinator)
    pair.child_for_side.return_value = target
    pair.async_execute_controller_command = AsyncMock(side_effect=execute)
    target.async_execute_controller_command = AsyncMock(side_effect=execute)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, SIDE_RIGHT)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "jalon_set_alarm",
            {
                "device_id": "bed",
                "side": SIDE_RIGHT,
                "enabled": True,
                "time": "07:30:00",
                "weekdays": ["0", "4"],
                "wake_mode": "memory_2",
            },
            blocking=True,
        )
    ctrl.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(0, 4), hour=7, minute=30, preset="memory_2"
    )

    assert pair.async_execute_controller_command.call_args.kwargs["side"] == SIDE_RIGHT


async def test_nonposition_notifications_start_with_angle_sensing_disabled() -> None:
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    ctrl = controller()
    ctrl.start_notify = AsyncMock()
    session = SimpleNamespace(
        _controller=ctrl,
        _disable_angle_sensing=True,
        _address="AA:BB:CC:DD:EE:FF",
        _bed_type="jalon_bed",
    )
    await AdjustableBedCoordinator.async_start_notify(session)
    ctrl.start_notify.assert_awaited_once_with(None)
