"""Row 052 vectors: Jordan's Tranquil 1.0.2 and Customatic Z-Series 1.0.4 (Z-230/Z-280)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.serenity import (
    TranquilController,
    ZSeriesController,
    alarm_frame,
    alarm_repeat_bit,
    clock_frame,
)

STOP = "0c02000000000000000000000000"


def _coordinator(manufacturer: bytes = b"CST13", pulse_count: int = 2) -> MagicMock:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = pulse_count
    coordinator.motor_count = 4
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(
                uuid="62741523-52f9-8864-b1ab-3b3a8d65950b",
                characteristics=[
                    MagicMock(
                        uuid="62741525-52f9-8864-b1ab-3b3a8d65950b", properties=["write"], handle=1
                    ),
                    MagicMock(
                        uuid="62741625-52f9-8864-b1ab-3b3a8d65950b", properties=["notify"], handle=2
                    ),
                ],
            ),
            MagicMock(
                uuid="0000180a-0000-1000-8000-00805f9b34fb",
                characteristics=[
                    MagicMock(
                        uuid="00002a29-0000-1000-8000-00805f9b34fb", properties=["read"], handle=3
                    )
                ],
            ),
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=manufacturer)
    return coordinator


def tranquil(**kwargs) -> TranquilController:
    return TranquilController(_coordinator(**kwargs))


def zseries(model: str, **kwargs) -> ZSeriesController:
    return ZSeriesController(_coordinator(**kwargs), model=model)  # type: ignore[arg-type]


def written(controller) -> list[str]:
    return [call.args[1].hex() for call in controller.client.write_gatt_char.call_args_list]


def status(code: int, *, alarm: bool = False) -> bytearray:
    payload = bytearray(11)
    payload[1] = 12 if alarm else 99
    payload[10] = code
    return payload


# Tranquil C01..C44. C43 (voice "stop") streams Head Up before STOP; HA sends STOP only.
TRANQUIL_ROWS = (
    ("C01", "head_up", "0c02000000010000000000000000"),
    ("C02", "head_down", "0c02000000020000000000000000"),
    ("C03", "foot_up", "0c02000000040000000000000000"),
    ("C04", "foot_down", "0c02000000080000000000000000"),
    ("C05", "selector_4_up", "0c02000000100000000000000000"),
    ("C06", "selector_4_down", "0c02000000200000000000000000"),
    ("C07", "selector_5_up", "0c02000000400000000000000000"),
    ("C08", "selector_5_down", "0c02000000800000000000000000"),
    ("C09", "flat", "0c02080000000000000000000000"),
    ("C10", "zero_g", "0c02000010000000000000000000"),
    ("C11", "lounge", "0c02000020000000000000000000"),
    ("C12", "memory_1", "0c02000100000000000000000000"),
    ("C13", "memory_2", "0c02000400000000000000000000"),
    ("C14", "save_zero_g", "0c02080010000000000000000000"),
    ("C15", "save_lounge", "0c02080020000000000000000000"),
    ("C16", "save_memory_1", "0c02080100000000000000000000"),
    ("C17", "save_memory_2", "0c02080400000000000000000000"),
    ("C18", "massage_head_cycle", "0c02000008000000000000000000"),
    ("C19", "massage_foot_cycle", "0c02000004000000000000000000"),
    ("C20", "massage_mode_cycle", "0c02100000000000000000000000"),
    ("C21", "massage_timer_cycle", "0c02000002000000000000000000"),
    ("C22", "massage_toggle", "0c02000001000000000000000000"),
    ("C23", "light_toggle", "0c02000200000000000000000000"),
    ("C24", "anti_snore", "0c02000080000000000000000000"),
    ("C25", "wave_1", "0c02000000000008000000000000"),
    ("C26", "wave_2", "0c02000000000010000000000000"),
    ("C27", "wave_3", "0c02000000000020000000000000"),
    ("C28", "massage_off", "0c02020000000000000000000000"),
    ("C29", "light_on", "0c02000000000000004000000000"),
    ("C30", "light_off", "0c02000000000000008000000000"),
    ("C31", "light_toggle", "0c02000200000000000000000000"),
    ("C32", "head_up", "0c02000000010000000000000000"),
    ("C33", "head_down", "0c02000000020000000000000000"),
    ("C34", "foot_up", "0c02000000040000000000000000"),
    ("C35", "foot_down", "0c02000000080000000000000000"),
    ("C36", "selector_4_up", "0c02000000100000000000000000"),
    ("C37", "selector_4_down", "0c02000000200000000000000000"),
    ("C38", "selector_5_up", "0c02000000400000000000000000"),
    ("C39", "selector_5_down", "0c02000000800000000000000000"),
    ("C40", "lounge", "0c02000020000000000000000000"),
    ("C41", "zero_g", "0c02000010000000000000000000"),
    ("C42", "flat", "0c02080000000000000000000000"),
    ("C43", None, STOP),
    ("C44", None, STOP),
)

# Z-Series C01..C26 with the profile pages that reach each row.
ZSERIES_ROWS = (
    ("C01", ("z230", "z280"), "head_up", "0c02000000010000000000000000"),
    ("C02", ("z230", "z280"), "head_down", "0c02000000020000000000000000"),
    ("C03", ("z230", "z280"), "foot_up", "0c02000000040000000000000000"),
    ("C04", ("z230", "z280"), "foot_down", "0c02000000080000000000000000"),
    ("C05", ("z230",), "head_foot_up", "0c02000000050000000000000000"),
    ("C06", ("z230",), "head_foot_down", "0c020000000a0000000000000000"),
    ("C07", ("z280",), "selector_5_up", "0c02000000100000000000000000"),
    ("C08", ("z280",), "selector_5_down", "0c02000000200000000000000000"),
    ("C09", ("z230", "z280"), None, STOP),
    ("C10", ("z230", "z280"), "flat", "0c02080000000000000000000000"),
    ("C11", ("z230", "z280"), "anti_snore", "0c02000080000000000000000000"),
    ("C12", ("z230", "z280"), "memory_1", "0c02000100000000000000000000"),
    ("C13", ("z230", "z280"), "zero_g", "0c02000010000000000000000000"),
    ("C14", ("z230", "z280"), "tv", "0c02000040000000000000000000"),
    ("C15", ("z280",), "memory_2", "0c02000400000000000000000000"),
    ("C16", ("z230", "z280"), "save_zero_g", "0c02080010000000000000000000"),
    ("C17", ("z230", "z280"), "save_memory_1", "0c02080100000000000000000000"),
    ("C18", ("z230", "z280"), "save_tv", "0c02080040000000000000000000"),
    ("C19", ("z280",), "save_memory_2", "0c02080400000000000000000000"),
    ("C20", ("z230", "z280"), "light_toggle", "0c02000200000000000000000000"),
    ("C21", ("z230", "z280"), "massage_toggle", "0c02000001000000000000000000"),
    ("C22", ("z230", "z280"), "massage_mode_cycle", "0c02100000000000000000000000"),
    ("C23", ("z230", "z280"), "massage_timer_cycle", "0c02000002000000000000000000"),
    ("C24", ("z230",), "massage_intensity_cycle", "0c0200000c000000000000000000"),
    ("C25", ("z280",), "massage_head_cycle", "0c02000008000000000000000000"),
    ("C26", ("z280",), "massage_foot_cycle", "0c02000004000000000000000000"),
)


@pytest.mark.parametrize(("row", "action", "expected"), TRANQUIL_ROWS)
async def test_tranquil_every_artifact_row_with_safe_voice_stop(row, action, expected) -> None:
    controller = tranquil()
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        if action is None:
            await controller.stop_all()
        else:
            await controller.hold_control(action, 250)
    frames = written(controller)
    assert frames[-2:] == [STOP, STOP]
    assert [call.args[0] for call in sleep.call_args_list[-2:]] == pytest.approx([0.1, 0.2], abs=0.01)
    if action is None:
        assert frames == [STOP, STOP]
    else:
        assert set(frames[:-2]) == {expected}


@pytest.mark.parametrize(("row", "models", "action", "expected"), ZSERIES_ROWS)
@pytest.mark.parametrize("model", ["z230", "z280"])
async def test_zseries_every_artifact_row_on_its_own_page(row, models, action, expected, model):
    controller = zseries(model)
    if model not in models:
        assert action not in controller.held_control_options
        with pytest.raises(ValueError, match="Unknown"):
            await controller.hold_control(action, 250)
        assert written(controller) == []
        return
    with patch("asyncio.sleep", new=AsyncMock()):
        if action is None:
            await controller.stop_all()
        else:
            await controller.hold_control(action, 250)
    frames = written(controller)
    assert frames[-2:] == [STOP, STOP]
    assert action is None or set(frames[:-2]) == {expected}


def test_profiles_expose_only_their_own_app_surface() -> None:
    t, z230, z280 = tranquil(), zseries("z230"), zseries("z280")
    for controller in (t, z230, z280):
        assert tuple(spec.key for spec in controller.motor_control_specs) == ("head", "feet")
        assert all(spec.scheduler_resource == "*" for spec in controller.motor_control_specs)
        assert controller.requires_notification_channel
        assert controller.supports_massage and controller.supports_massage_toggle_control
        assert not controller.supports_massage_intensity_step_control
        assert not controller.has_lumbar_support and not controller.has_tilt_support
        assert not controller.supports_preset_incline
        assert controller.supports_light_toggle_control
    assert t.supports_preset_lounge and not t.supports_preset_tv
    assert t.supports_discrete_light_control and t.supports_massage_off_control
    assert t.supports_massage_wave_direction_control
    assert t.memory_slot_names == ("M1", "M2")
    assert len(t.held_control_options) == 30
    for z in (z230, z280):
        assert z.supports_preset_tv and not z.supports_preset_lounge
        assert not z.supports_discrete_light_control
        assert not z.supports_massage_off_control
        assert not z.supports_massage_wave_direction_control
        assert not z.supports_clock_alarm and not z.supports_clock_sync
    assert z230.memory_slot_names == ("M1",)
    assert z280.memory_slot_names == ("M1", "M2")
    assert {spec.key for spec in t.controller_button_specs} == {
        f"tranquil_{key}"
        for key in (
            "refresh_manufacturer",
            "selector_4_up",
            "selector_4_down",
            "selector_5_up",
            "selector_5_down",
            "save_zero_g",
            "save_lounge",
            "light_toggle",
            "massage_head_cycle",
            "massage_foot_cycle",
            "massage_timer_cycle",
            "wave_1",
            "wave_2",
            "wave_3",
        )
    }
    assert {spec.key for spec in z230.controller_button_specs} == {
        f"zseries_{key}"
        for key in (
            "refresh_manufacturer",
            "head_foot_up",
            "head_foot_down",
            "save_zero_g",
            "save_tv",
            "light_toggle",
            "massage_timer_cycle",
            "massage_intensity_cycle",
        )
    }
    assert {spec.key for spec in z280.controller_button_specs} == {
        f"zseries_{key}"
        for key in (
            "refresh_manufacturer",
            "selector_5_up",
            "selector_5_down",
            "save_zero_g",
            "save_tv",
            "light_toggle",
            "massage_timer_cycle",
            "massage_head_cycle",
            "massage_foot_cycle",
        )
    }


@pytest.mark.parametrize(
    ("factory", "action", "code"),
    [
        (tranquil, "save_zero_g", 5),
        (tranquil, "save_lounge", 3),
        (tranquil, "save_memory_1", 4),
        (tranquil, "save_memory_2", 8),
        (lambda: zseries("z230"), "save_tv", 6),
        (lambda: zseries("z280"), "save_memory_2", 8),
    ],
)
async def test_save_records_app_local_code_and_status_change_reports_it(factory, action, code):
    controller = factory()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control(action, 100)
    prefix = controller._app.prefix
    controller._handle_notification(None, status(2))
    assert controller.protocol_diagnostics[f"{prefix}_save_event_code"] == code
    assert f"{prefix}_massage_timer_code" not in controller.protocol_diagnostics
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.hold_control(action, 100)
        await controller.hold_control("flat", 100)  # Any recall clears pending intent.
    controller._handle_notification(None, status(1))
    assert controller.protocol_diagnostics[f"{prefix}_massage_timer_minutes"] == 10


async def test_tranquil_defaults_follow_its_voice_and_save_help_deadlines() -> None:
    controller = tranquil()
    controller.hold_control = AsyncMock()
    await controller.preset_flat()
    await controller.preset_lounge()
    await controller.preset_memory(2)
    await controller.program_memory(1)
    await controller.massage_off()
    assert [call.args for call in controller.hold_control.await_args_list] == [
        ("flat", 1500),
        ("lounge", 500),
        ("memory_2", 500),
        ("save_memory_1", 5000),
        ("massage_off", 500),
    ]


@pytest.mark.parametrize("pulse_count", [3, 25])
async def test_zseries_press_is_bounded_by_configured_pulses_and_save_help(pulse_count) -> None:
    controller = zseries("z280", pulse_count=pulse_count)
    controller.hold_control = AsyncMock()
    await controller.preset_flat()
    await controller.preset_tv()
    await controller.preset_memory(2)
    await controller.program_memory(2)
    spec = next(s for s in controller.controller_button_specs if s.key == "zseries_save_tv")
    await spec.press_fn(controller)
    assert [call.args for call in controller.hold_control.await_args_list] == [
        ("flat", pulse_count * 100),
        ("tv", pulse_count * 100),
        ("memory_2", pulse_count * 100),
        ("save_memory_2", 5000),
        ("save_tv", 5000),
    ]


async def test_zseries_z230_has_only_m1() -> None:
    controller = zseries("z230")
    with pytest.raises(ValueError, match="only M1"):
        await controller.preset_memory(2)
    with pytest.raises(ValueError, match="only M1"):
        await controller.program_memory(2)
    with pytest.raises(ValueError, match="not reachable"):
        await controller.massage_off()
    assert written(controller) == []


@pytest.mark.parametrize(
    ("manufacturer", "available"),
    [(b"CST13", True), (b"CST14", True), (b"cst13", False), (b"CST13 ", False), (b"CST15", False)],
)
async def test_exact_manufacturer_string_gates_zseries_alarm_page(manufacturer, available):
    controller = zseries("z230", manufacturer=manufacturer)
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify()
    assert controller.supports_clock_alarm is available
    assert controller.supports_clock_sync is available
    assert controller.clock_alarm_preset_options == (("massage", "memory_1") if available else ())
    assert controller.protocol_diagnostics["zseries_manufacturer"] == manufacturer.decode()
    if not available:
        with pytest.raises(ValueError, match="manufacturer"):
            await controller.configure_clock_alarm(enabled=True, hour=7, minute=45, preset="massage")
        assert written(controller) == []


async def test_tranquil_manufacturer_never_enables_alarm() -> None:
    controller = tranquil(manufacturer=b"CST13")
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify()
    assert controller.protocol_diagnostics["tranquil_manufacturer"] == "CST13"
    assert not controller.supports_clock_alarm and not controller.supports_clock_sync


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # T-C27 / T-C28 / T-C29 from the frozen Z-Series vectors.
        ({"enabled": True, "hour": 7, "minute": 45, "repeat": 1, "wake": "massage"}, "07050101072d000101"),
        ({"enabled": True, "hour": 23, "minute": 59, "repeat": 64, "wake": "memory_1"}, "07054002173b000101"),
        ({"enabled": False, "hour": 0, "minute": 0, "repeat": 0, "wake": "massage"}, "070500000000000001"),
    ],
)
def test_alarm_frame_vectors(kwargs, expected) -> None:
    assert alarm_frame(**kwargs).hex() == expected


def test_clock_frame_vector_and_repeat_bit_rules() -> None:
    now = datetime(2026, 10, 1, 13, 47, 59)  # Thursday
    assert clock_frame(now).hex() == "07061a0a01040d2f3b"  # T-C31
    assert alarm_repeat_bit(now, 13, 47) == 1 << 4  # Equal time stays today.
    assert alarm_repeat_bit(now, 13, 48) == 1 << 4
    assert alarm_repeat_bit(now, 13, 46) == 1 << 5  # Earlier moves to tomorrow.
    saturday = datetime(2026, 10, 3, 23, 0)
    assert alarm_repeat_bit(saturday, 22, 59) == 1  # 128 wraps to Sunday.
    assert alarm_repeat_bit(datetime(2026, 10, 4, 6, 0), 7, 0) == 1  # Sunday is bit 0.


async def test_set_alarm_writes_clock_alarm_then_two_app_queries() -> None:
    controller = zseries("z280")
    controller._alarm_available = True
    now = datetime(2026, 10, 1, 13, 47, 59)
    with (
        patch("custom_components.adjustable_bed.beds.serenity.dt_util.now", return_value=now),
        patch("asyncio.sleep", new=AsyncMock()) as sleep,
    ):
        await controller.configure_clock_alarm(enabled=True, hour=7, minute=45, preset="memory_1")
        await controller.configure_clock_alarm(enabled=False, hour=0, minute=0, preset="massage")
        await controller.sync_clock()
    assert written(controller) == [
        "07061a0a01040d2f3b",
        "07052002072d000101",  # 07:45 has passed today: Friday bit, M1 wake.
        "00c0",
        "00c0",
        "07061a0a01040d2f3b",
        "070500000000000001",
        "00c0",
        "00c0",
        "07061a0a01040d2f3b",
        "00c0",
        "00c0",
    ]
    assert [call.args[0] for call in sleep.call_args_list] == [0.5, 0.3] * 3


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        # T-P01, T-P02 (Z-Series) and NP1 (Tranquil): signed fields, unmapped type kept.
        ("000c00004002173b0001ff", {"alarm_repeat": 64, "alarm_type": 17, "alarm_hour": 23, "alarm_minute": 59, "alarm_on": True}),
        ("ff0cffff8000ff80ff00ff", {"alarm_repeat": -128, "alarm_type": 17, "alarm_hour": -1, "alarm_minute": -128, "alarm_on": False}),
        ("000c00008006173b000100", {"alarm_repeat": -128, "alarm_type": 19, "alarm_hour": 23, "alarm_minute": 59, "alarm_on": True}),
    ],
)
def test_alarm_reply_parser_vectors(payload, expected) -> None:
    controller = zseries("z280")
    controller._alarm_type = 17
    controller._handle_notification(None, bytearray.fromhex(payload))
    assert {
        key: controller.protocol_diagnostics[f"zseries_{key}"] for key in expected
    } == expected
    assert "zseries_status_code" not in controller.protocol_diagnostics


def test_status_parser_vectors_and_short_input() -> None:
    controller = tranquil()
    controller._handle_notification(None, bytearray.fromhex("000c00000101072d0001"))  # T-P06
    assert controller.protocol_diagnostics.get("tranquil_alarm_type") is None
    controller._handle_notification(None, bytearray.fromhex("00010000000000000000ff"))
    assert controller.protocol_diagnostics["tranquil_status_code"] == -1  # NP2
    assert controller.protocol_diagnostics["tranquil_massage_timer_code"] == -1
    controller._handle_notification(None, status(1))  # T-P03
    assert controller.protocol_diagnostics["tranquil_massage_timer_minutes"] == 10


async def test_inherited_routes_use_only_reachable_frames() -> None:
    controller = tranquil()
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.preset_lounge()
        await controller.massage_wave_next()
        await controller.lights_on()
        await controller.preset_anti_snore()
    frames = [frame for frame in written(controller) if frame != STOP]
    assert set(frames) == {
        "0c02000020000000000000000000",
        "0c02000000000008000000000000",
        "0c02000000000000004000000000",
        "0c02000080000000000000000000",
    }
    z230 = zseries("z230")
    with patch("asyncio.sleep", new=AsyncMock()):
        await z230.preset_zero_g()
        await z230.massage_toggle()
        await z230.lights_toggle()
    assert list(dict.fromkeys(frame for frame in written(z230) if frame != STOP)) == [
        "0c02000010000000000000000000",
        "0c02000001000000000000000000",
        "0c02000200000000000000000000",
    ]
