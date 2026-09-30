"""Frozen artifact vectors and real command lifecycle for Malouf/Lucid profiles."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.malouf_app import MaloufAppController
from custom_components.adjustable_bed.malouf_app_protocol import (
    APP_MODEL_OPTIONS,
    MALOUF_APP_MODELS,
    TRANSPORTS,
    alarm_frame,
    clock_frame,
    command_frame,
    parse_notification,
)


def gatt_services(*transports: str) -> list[MagicMock]:
    """Construct coherent service roles while retaining duplicate-service testing."""
    services: dict[str, MagicMock] = {}
    for transport in transports:
        spec = TRANSPORTS[transport]
        service = services.setdefault(
            spec.command_service, MagicMock(uuid=spec.command_service, characteristics=[])
        )
        if not any(char.uuid == spec.command_characteristic for char in service.characteristics):
            service.characteristics.append(
                MagicMock(uuid=spec.command_characteristic, properties=["write"], handle=1)
            )
        if spec.notify_service is not None and spec.notify_characteristic is not None:
            notify_service = services.setdefault(
                spec.notify_service, MagicMock(uuid=spec.notify_service, characteristics=[])
            )
            if not any(
                char.uuid == spec.notify_characteristic for char in notify_service.characteristics
            ):
                notify_service.characteristics.append(
                    MagicMock(uuid=spec.notify_characteristic, properties=["notify"], handle=2)
                )
    return list(services.values())


def make_controller(
    transport: str, model: str = "S755", app_profile: str = "malouf", primary: bool = True
) -> MaloufAppController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.observed_ble_device_name = (
        "X1RM" if transport.startswith("richmat") else "Smartbed238"
    )
    coordinator.ble_device_name = coordinator.observed_ble_device_name
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.client = MagicMock(is_connected=True, services=gatt_services(transport))
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return MaloufAppController(
        coordinator, app_profile=app_profile, model=model, transport=transport, primary=primary
    )


def written(controller: MaloufAppController) -> list[bytes]:
    return [call.args[1] for call in controller.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    ("transport", "command", "selector", "expected"),
    [
        ("richmat_single", 0x24, 0, "24"),
        ("richmat_single", 0x6E, 0, "6e"),
        ("richmat_framed", 0x24, 0, "6e01002493"),
        ("richmat_framed", 0x24, 1, "6e01012494"),
        ("richmat_framed", 0x6E, 0, "6e01006edd"),
        ("okin_legacy", 1, 0, "e6fe16010000000004"),
        ("okin_legacy", 0x08000000, 0, "e6fe160000000800fd"),
        ("okin_custom", 1, 0, "04020000000100000000"),
        ("okin_custom", 0x08000000, 0, "04020800000000000000"),
        ("okin_new", 1, 0, "0502000000010000"),
        ("okin_new", 0x08000000, 0, "0502080000000000"),
    ],
)
def test_artifact_command_vectors(
    transport: str, command: int, selector: int, expected: str
) -> None:
    assert command_frame(transport, command, selector=selector).hex() == expected


@pytest.mark.parametrize(
    ("transport", "expected_clock", "expected_alarm", "expected_clear"),
    [
        (
            "okin_legacy",
            "e780017e060e071e2db3",
            "ed8003071e800d0000000000000000dd",
            "ed80030000000000000000000000008f",
        ),
        (
            "okin_custom",
            "e780017e060e071e2db3",
            "ed8003071e800d0000000000000000dd",
            "ed80030000000000000000000000008f",
        ),
        ("okin_new", "0704ea070e02071e2d", "07050101071e000100", "070500f40000000000"),
    ],
)
def test_artifact_clock_alarm_vectors(
    transport: str, expected_clock: str, expected_alarm: str, expected_clear: str
) -> None:
    assert clock_frame(transport, datetime(2026, 7, 14, 7, 30, 45)).hex() == expected_clock
    assert alarm_frame(transport, 7, 30, 13, 0x80).hex() == expected_alarm
    assert alarm_frame(transport, 0, 0, 0, 0).hex() == expected_clear


@pytest.mark.parametrize(
    ("transport", "payload", "minutes", "light"),
    [
        ("okin_legacy", "00000000000000400200", 20, 1),
        ("okin_legacy", "00000000000000800300", 30, -2),
        ("okin_legacy", "00000000000000ff1100", 10, -1),
        ("okin_custom", "0000000000000000000002", 20, 0),
        ("okin_custom", "00000000000000000000ff", -10, 0),
        ("okin_custom", "", 0, 0),
        ("okin_new", "000b0000030000000001", 20, 1),
        ("okin_new", "000b000005000000000000000001", 30, 1),
        ("okin_new", "000b0000", 0, 0),
        ("okin_new", "000b0000ff0000000002", 0, 0),
    ],
)
def test_artifact_parser_vectors(transport: str, payload: str, minutes: int, light: int) -> None:
    state = parse_notification(transport, bytes.fromhex(payload))
    assert state is not None
    assert (state.massage_remaining_minutes, state.light_status) == (minutes, light)


@pytest.mark.parametrize(
    ("transport", "payload"),
    [
        ("okin_legacy", ""),
        ("okin_legacy", "000000000000004002"),
        ("okin_new", "00"),
        ("okin_new", "000a0000030000000001"),
        ("richmat_single", "000b0000030000000001"),
    ],
)
def test_parser_guard_mutations(transport: str, payload: str) -> None:
    assert parse_notification(transport, bytes.fromhex(payload)) is None


@pytest.mark.parametrize(
    ("length", "light_offset", "timer_offset"), [(10, 7, 8), (16, 13, 14), (20, 18, 19)]
)
def test_legacy_notification_offsets_and_timer_nibble(
    length: int, light_offset: int, timer_offset: int
) -> None:
    payload = bytearray(length)
    payload[light_offset], payload[timer_offset] = 0x40, 0xF2
    state = parse_notification("okin_legacy", payload)
    assert state is not None and state.massage_remaining_minutes == 20 and state.light_status == 1
    payload[timer_offset] = 0xF4
    state = parse_notification("okin_legacy", payload)
    assert state is not None and state.massage_remaining_minutes == 0


@pytest.mark.parametrize(
    ("transport", "motion", "stop"),
    [
        ("richmat_single", "24", "6e"),
        ("richmat_framed", "6e01002493", "6e01006edd"),
        ("okin_legacy", "e6fe16010000000004", "e6fe16000000000005"),
        ("okin_custom", "04020000000100000000", "04020000000000000000"),
        ("okin_new", "0502000000010000", "0502000000000000"),
    ],
)
async def test_real_motion_lifecycle_acknowledged_hold_and_release(
    transport: str, motion: str, stop: str
) -> None:
    ctrl = make_controller(transport)
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await ctrl.move_back_up()
    assert written(ctrl) == [bytes.fromhex(motion), bytes.fromhex(motion), bytes.fromhex(stop)]
    assert sleep.call_args_list[-1].args == (0.15,)
    assert all(
        call.kwargs["response"] is True for call in ctrl.client.write_gatt_char.call_args_list
    )
    assert ctrl._coordinator.record_command_trace.call_args_list[0].kwargs["repeat_delay_ms"] == 150


@pytest.mark.parametrize("cancel_task", [False, True])
async def test_motion_cancellation_still_sends_uncancelled_stop(cancel_task: bool) -> None:
    ctrl = make_controller("richmat_framed")

    async def cancel_on_motion(uuid: str, payload: bytes, *, response: bool) -> None:
        if payload[3] != 0x6E:
            ctrl._coordinator.cancel_command.set()
            if cancel_task:
                raise asyncio.CancelledError

    ctrl.client.write_gatt_char.side_effect = cancel_on_motion
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        if cancel_task:
            with pytest.raises(asyncio.CancelledError):
                await ctrl.move_back_up()
        else:
            await ctrl.move_back_up()
    assert written(ctrl) == [bytes.fromhex("6e01002493"), bytes.fromhex("6e01006edd")]


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        ("richmat_single", ["31", "6e"]),
        ("richmat_framed", ["6e010031a0"]),
        ("okin_legacy", ["e6fe160000000800fd"] * 3),
        ("okin_custom", ["04020800000000000000"] * 3 + ["04020000000000000000"]),
        ("okin_new", ["0502080000000000", "0502000000000000"]),
    ],
)
async def test_variant_specific_preset_repeats_and_stop(
    transport: str, expected: list[str]
) -> None:
    ctrl = make_controller(transport)
    await ctrl.preset_flat()
    assert [data.hex() for data in written(ctrl)] == expected


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("head_up", "6e01012494"),
        ("head_down", "6e01012595"),
        ("massage_head", "6e01014cbc"),
        ("flat", "6e010131a1"),
        ("zero_g", "6e010145b5"),
        ("anti_snore", "6e010146b6"),
        ("stop", "6e01006edd"),
        ("foot_up", "6e01002695"),
        ("dual_up", "6e01002998"),
        ("memory_1", "6e01002e9d"),
        ("light", "6e01003cab"),
    ],
)
def test_only_six_secondary_actions_embed_physical_role(action: str, expected: str) -> None:
    ctrl = make_controller("richmat_framed", primary=False)
    assert ctrl._frames(action) == (bytes.fromhex(expected),)


async def test_paired_logical_side_does_not_change_configured_role() -> None:
    ctrl = make_controller("richmat_framed", primary=False)
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await ctrl.bind_side("left").move_back_up()
    assert written(ctrl)[0].hex() == "6e01012494"
    assert written(ctrl)[-1].hex() == "6e01006edd"


@pytest.mark.parametrize(
    ("transport", "slot", "count", "delay", "frame"),
    [
        ("richmat_single", 1, 1, None, "2b"),
        ("richmat_framed", 2, 1, None, "6e01002c9b"),
        ("okin_legacy", 1, 85, 0.15, "e6fe16000001800084"),
        ("okin_custom", 2, 85, 0.15, "04028004000000000000"),
        ("okin_new", 1, 55, 0.1, "0502800100000000"),
    ],
)
async def test_memory_save_exact_hold_count_initial_delay_and_no_stop(
    transport: str, slot: int, count: int, delay: float | None, frame: str
) -> None:
    ctrl = make_controller(transport)
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await ctrl.program_memory(slot)
    assert written(ctrl) == [bytes.fromhex(frame)] * count
    if delay is not None:
        assert sleep.call_args_list[0].args == (delay,)
    assert all(call.kwargs["response"] for call in ctrl.client.write_gatt_char.call_args_list)


async def test_memory1_normal_name_has_no_save_bit_and_cancellation_has_no_invented_stop() -> None:
    ctrl = make_controller("okin_new")
    ctrl._coordinator.observed_ble_device_name = "OKIN"

    async def cancel_after_one(*args: object, **kwargs: object) -> None:
        ctrl._coordinator.cancel_command.set()

    ctrl.client.write_gatt_char.side_effect = cancel_after_one
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await ctrl.program_memory(1)
    assert written(ctrl) == [bytes.fromhex("0502000100000000")]


@pytest.mark.parametrize(
    ("method", "opcode"),
    [
        ("massage_off", 0x47),
        ("massage_mode_step", 0x48),
        ("massage_head_toggle", 0x4C),
        ("massage_foot_toggle", 0x4E),
    ],
)
async def test_richmat_reachable_massage_commands(method: str, opcode: int) -> None:
    ctrl = make_controller("richmat_single")
    await getattr(ctrl, method)()
    assert written(ctrl) == [bytes((opcode,))]


@pytest.mark.parametrize(("minutes", "opcode"), [(10, 0x5F), (20, 0x63), (30, 0x61)])
async def test_richmat_direct_timer_opcode_order(minutes: int, opcode: int) -> None:
    ctrl = make_controller("richmat_single")
    await ctrl.set_massage_timer(minutes)
    assert written(ctrl) == [bytes((opcode,))]


@pytest.mark.parametrize(
    ("method", "frame"),
    [
        ("massage_toggle", "0502000002000000"),
        ("massage_head_toggle", "0502000008000000"),
        ("massage_foot_toggle", "0502000004000000"),
        ("massage_mode_step", "0502100000000000"),
        ("lights_toggle", "0502000200000000"),
    ],
)
async def test_new_telemetry_query_only_after_reachable_state_actions(
    method: str, frame: str
) -> None:
    ctrl = make_controller("okin_new", model="S750")
    await getattr(ctrl, method)()
    assert written(ctrl) == [bytes.fromhex(frame), b"\x00\xb0"]
    assert ctrl.supports_massage_off_control is False
    with pytest.raises(ValueError):
        await ctrl.massage_off()


@pytest.mark.parametrize(
    ("transport", "model", "keys", "slots"),
    [
        ("richmat_framed", "Altitude", {"back", "legs", "malouf_tilt_head", "malouf_full_tilt"}, 0),
        ("richmat_framed", "Forte", {"back", "legs"}, 0),
        ("richmat_framed", "M555", {"back", "legs"}, 1),
        ("richmat_framed", "S655", {"back", "legs", "tilt"}, 2),
        ("okin_custom", "S750", {"back", "legs", "tilt", "lumbar"}, 2),
        ("richmat_framed", "GoodLifePremierBase", {"back", "legs", "tilt", "lumbar"}, 0),
    ],
)
def test_model_axes_memory_and_legacy_entity_retirement(
    transport: str, model: str, keys: set[str], slots: int
) -> None:
    ctrl = make_controller(transport, model)
    assert {spec.key for spec in ctrl.motor_control_specs} == keys
    assert ctrl.memory_slot_count == slots
    assert ctrl.supports_memory_presets == (slots > 0)
    assert ctrl.supports_memory_programming == (slots > 0)
    assert "bed_height" in ctrl.stale_motor_entity_keys
    assert ctrl.has_bed_height_support is False


async def test_altitude_distinct_literal_actions_and_no_invented_height() -> None:
    ctrl = make_controller("richmat_single", "Altitude")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await ctrl.move_tilt_head_up()
        await ctrl.move_full_tilt_up()
    assert written(ctrl) == [b"\x41", b"\x41", b"\x6e", b"\x3f", b"\x3f", b"\x6e"]


async def test_dual_moves_only_proven_same_direction_axes() -> None:
    ctrl = make_controller("richmat_single")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await ctrl.move_simultaneously("back", True, "legs", True)
    assert written(ctrl) == [b"\x29", b"\x29", b"\x6e"]
    ctrl.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await ctrl.move_simultaneously("back", True, "legs", False)
    assert written(ctrl) == []


async def test_profile_specific_preset_terminal_dispositions() -> None:
    lucid = make_controller("okin_new", "Premium", "lucid")
    await lucid.preset_read()
    assert written(lucid) == [bytes.fromhex("0502000020000000"), bytes.fromhex("0502000000000000")]
    assert lucid.controller_button_specs[0].key == "malouf_read"
    malouf = make_controller("okin_new", "Premium", "malouf")
    with pytest.raises(ValueError):
        await malouf.preset_read()
    assert written(malouf) == []
    oz = make_controller("okin_new", "GoodLifeBase", "lucid")
    assert not oz.supports_preset_zero_g and not oz.supports_preset_anti_snore
    with pytest.raises(ValueError):
        await oz.preset_zero_g()
    assert written(oz) == []


def test_all_persisted_models_available_but_fresh_lists_are_app_specific() -> None:
    assert len(MALOUF_APP_MODELS) == 16
    assert len(APP_MODEL_OPTIONS["malouf"]) == 14
    assert APP_MODEL_OPTIONS["lucid"] == ("L300", "L600", "Premium")
    assert make_controller("okin_custom", "M550", "lucid").memory_slot_count == 1


@pytest.mark.parametrize(
    ("name", "transports"),
    [
        ("X1RM", ("richmat_single", "richmat_framed")),
        ("OKIN", ("okin_legacy", "okin_custom")),
        ("x1rm", ("richmat_framed",)),
    ],
)
async def test_auto_rejects_order_dependent_or_unmatched_transport(
    name: str, transports: tuple[str, ...]
) -> None:
    ctrl = make_controller(transports[0])
    ctrl._configured_transport, ctrl._transport = "auto", None
    ctrl._coordinator.observed_ble_device_name = name
    ctrl.client.services = gatt_services(*transports)
    with pytest.raises(ValueError):
        await ctrl.async_discover_capabilities()
    assert written(ctrl) == []
    assert ctrl.transport is None


async def test_auto_null_name_uses_legacy_derived_family_not_user_title() -> None:
    ctrl = make_controller("okin_new")
    ctrl._configured_transport, ctrl._transport = "auto", None
    ctrl._coordinator.observed_ble_device_name = None
    ctrl._coordinator.ble_device_name = "My Bed"
    await ctrl.async_discover_capabilities()
    assert ctrl.transport == "okin_new"


@pytest.mark.parametrize("bad_role", ["write_without_response", "missing_notify", "wrong_service"])
async def test_configured_transport_validates_actual_service_roles(bad_role: str) -> None:
    ctrl = make_controller("okin_new")
    service = ctrl.client.services[0]
    if bad_role == "write_without_response":
        service.characteristics[0].properties = ["write-without-response"]
    elif bad_role == "missing_notify":
        service.characteristics = service.characteristics[:1]
    else:
        service.uuid = "0000180a-0000-1000-8000-00805f9b34fb"
    with pytest.raises(ValueError):
        await ctrl.move_back_up()
    assert written(ctrl) == []


async def test_explicit_transport_breaks_service_order_tie_without_hybrid() -> None:
    ctrl = make_controller("richmat_framed")
    ctrl.client.services = gatt_services("richmat_single", "richmat_framed")
    await ctrl.preset_flat()
    assert written(ctrl) == [bytes.fromhex("6e010031a0")]


async def test_alarm_sync_then_weekly_program_and_exact_clear() -> None:
    ctrl = make_controller("okin_new", "Premium", "lucid")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.dt_util.now",
        return_value=datetime(2026, 7, 14, 7, 30, 45),
    ):
        await ctrl.configure_clock_alarm(
            enabled=True, weekdays=[0, 6, 0], hour=8, minute=15, preset="lounge"
        )
        await ctrl.configure_clock_alarm(
            enabled=False, weekdays=[], hour=0, minute=0, preset="zero_g"
        )
    assert [data.hex() for data in written(ctrl)] == [
        "0704ea070e02071e2d",
        "07050302080f000100",
        "070500f40000000000",
    ]
    # Lounge is a valid alarm even though Premium's manual preset array has READ.
    assert "lounge" in ctrl.clock_alarm_preset_options
    assert not ctrl.supports_preset_lounge


@pytest.mark.parametrize(("hour", "minute", "day_bits"), [(7, 31, 4), (7, 30, 8), (6, 30, 8)])
async def test_alarm_one_shot_today_or_tomorrow_without_repeat_bit(
    hour: int, minute: int, day_bits: int
) -> None:
    ctrl = make_controller("okin_legacy", "L600")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.dt_util.now",
        return_value=datetime(2026, 7, 14, 7, 30, 45),
    ):
        await ctrl.configure_clock_alarm(
            enabled=True, weekdays=[], hour=hour, minute=minute, preset="zero_g"
        )
    data = written(ctrl)
    assert len(data) == 6 and data[3] == data[4] == data[5]
    assert data[3][5] == day_bits


async def test_invalid_alarm_has_no_clock_or_alarm_side_effect() -> None:
    ctrl = make_controller("okin_new", "L600")
    for args in [
        {"preset": "memory_2"},
        {"head_level": 1},
        {"weekdays": [7]},
        {"preset": "massage"},
    ]:
        options = {
            "enabled": True,
            "weekdays": [0],
            "hour": 7,
            "minute": 30,
            "preset": "zero_g",
        } | args
        with pytest.raises(ValueError):
            await ctrl.configure_clock_alarm(**options)
    assert written(ctrl) == []


async def test_notification_subscription_raw_forward_state_dedup_and_no_clock_on_connect() -> None:
    ctrl = make_controller("okin_new", "S750")
    await ctrl.start_notify()
    assert written(ctrl) == []
    sender = MagicMock(uuid=TRANSPORTS["okin_new"].notify_characteristic)
    payload = bytearray.fromhex("000b0000030000000001")
    raw = MagicMock()
    ctrl.set_raw_notify_callback(raw)
    ctrl._notification_handler(sender, payload)
    ctrl._notification_handler(sender, payload)
    assert raw.call_count == 2
    ctrl._coordinator.handle_controller_state_updates.assert_called_once_with(
        {"massage_remaining_minutes": 20, "underbed_light_on": True}
    )
    assert ctrl.get_light_state() == {"is_on": True}
    assert ctrl.get_massage_state() == {"remaining_minutes": 20}
    assert ctrl.controller_state_sensor_specs[0].state_key == "massage_remaining_minutes"
    await ctrl.stop_notify()
    ctrl.client.stop_notify.assert_awaited_once_with(sender.uuid)


async def test_custom_notifications_do_not_claim_light_feedback() -> None:
    ctrl = make_controller("okin_custom", "S750")
    await ctrl.start_notify()
    sender = MagicMock(uuid=TRANSPORTS["okin_custom"].notify_characteristic)
    ctrl._notification_handler(sender, bytearray.fromhex("0000000000000000000002"))
    ctrl._coordinator.handle_controller_state_updates.assert_called_once_with(
        {"massage_remaining_minutes": 20}
    )
    assert not ctrl.supports_light_state_feedback
    assert ctrl.get_light_state() == {}


@pytest.mark.parametrize(
    ("app", "transport", "model", "direct_timer", "off", "timer_step"),
    [
        ("malouf", "richmat_single", "Forte", True, True, False),
        ("lucid", "richmat_single", "Forte", False, True, False),
        ("malouf", "richmat_single", "L600", True, True, False),
        ("lucid", "richmat_single", "L600", False, True, False),
        ("malouf", "okin_new", "S755", False, False, True),
        ("lucid", "okin_new", "S755", False, False, True),
        ("malouf", "richmat_single", "E450", False, False, False),
    ],
)
def test_massage_timer_visibility_and_shared_listener_gate(
    app: str, transport: str, model: str, direct_timer: bool, off: bool, timer_step: bool
) -> None:
    ctrl = make_controller(transport, model, app)
    assert ctrl.supports_massage_timer is direct_timer
    assert ctrl.supports_massage_off_control is off
    assert ctrl.supports_massage_toggle_control is timer_step


@pytest.mark.parametrize("app", ["malouf", "lucid"])
async def test_goodlife_all_label_does_not_invent_okin_dual_alias(app: str) -> None:
    ctrl = make_controller("okin_new", "GoodLifeBase", app)
    assert not ctrl.supports_simultaneous_movement
    with pytest.raises(ValueError):
        await ctrl.move_simultaneously("back", True, "legs", True)
    assert written(ctrl) == []


async def test_callback_specs_invoke_current_controller_after_reconnect() -> None:
    old = make_controller("richmat_single", "Altitude")
    current = make_controller("richmat_single", "Altitude")
    spec = next(spec for spec in old.motor_control_specs if spec.key == "malouf_tilt_head")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await spec.open_fn(current.bind_side("right"))
    assert written(old) == []
    assert written(current) == [b"\x41", b"\x41", b"\x6e"]
    old_read = make_controller("okin_new", "Premium", "lucid")
    current_read = make_controller("okin_new", "Premium", "lucid")
    await old_read.controller_button_specs[0].press_fn(current_read.bind_side("left"))
    assert written(old_read) == []
    assert written(current_read)[0].hex() == "0502000020000000"


async def test_feedback_light_power_uses_known_state_and_native_toggle() -> None:
    ctrl = make_controller("okin_new", "S750")
    assert ctrl.requires_notification_channel
    with pytest.raises(ValueError):
        await ctrl.lights_on()
    assert written(ctrl) == []
    sender = MagicMock(uuid=TRANSPORTS["okin_new"].notify_characteristic)
    ctrl._notification_handler(sender, bytearray.fromhex("000b0000030000000001"))
    await ctrl.lights_on()
    assert written(ctrl) == []
    await ctrl.lights_off()
    assert written(ctrl) == [bytes.fromhex("0502000200000000"), b"\x00\xb0"]


async def test_name_factory_precedence_and_duplicate_role_rejection() -> None:
    ctrl = make_controller("richmat_framed")
    ctrl._configured_transport, ctrl._transport = "auto", None
    ctrl._coordinator.observed_ble_device_name = "SmartbedX1RM"
    await ctrl.async_discover_capabilities()
    assert ctrl.transport == "richmat_framed"
    ctrl.client.services += gatt_services("richmat_framed")
    with pytest.raises(ValueError):
        await ctrl.preset_flat()
    assert written(ctrl) == []


# Independent vectors transcribed from the frozen constructor inventory. Empty
# READ is intentional for the shared preset table; its app-specific terminal is
# exercised separately above, not aliased to lounge on every transport.
@pytest.mark.parametrize(
    ("key", "name", "slots", "manual", "presets", "functions"),
    [
        (
            "Altitude",
            "Altitude",
            0,
            "back legs dual tilt_head full_tilt",
            "zero_g anti_snore",
            "massage massage_head massage_foot massage_wave massage_off light",
        ),
        ("E450", "E450", 0, "back legs", "zero_g anti_snore", ""),
        ("E455", "E455", 0, "back legs", "zero_g anti_snore", ""),
        (
            "Forte",
            "Forte",
            0,
            "back legs",
            "zero_g",
            "massage massage_head massage_wave massage_off",
        ),
        ("GoodLifeBase", "Good Life Base", 0, "back legs dual", "zero_g tv anti_snore lounge", ""),
        (
            "GoodLifePremierBase",
            "Good Life Premier Base",
            0,
            "back legs dual tilt lumbar",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_off massage_timer_set light",
        ),
        (
            "GoodLifeProBase",
            "Good Life Pro Base",
            0,
            "back legs dual",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_off massage_timer_set light",
        ),
        ("L300", "L300", 0, "back legs", "zero_g anti_snore", ""),
        (
            "L600",
            "L600",
            1,
            "back legs",
            "zero_g anti_snore lounge tv",
            "massage massage_head massage_foot massage_wave massage_timer_step alarm light",
        ),
        (
            "M455",
            "M455",
            0,
            "back legs",
            "zero_g anti_snore",
            "massage massage_head massage_wave massage_off massage_timer_set",
        ),
        (
            "M550",
            "M550",
            1,
            "back legs",
            "zero_g anti_snore lounge tv",
            "massage massage_head massage_foot massage_wave massage_timer_step alarm light",
        ),
        (
            "M555",
            "M555",
            1,
            "back legs dual",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_off massage_timer_set light",
        ),
        (
            "Premium",
            "Premium",
            2,
            "back legs dual",
            "zero_g anti_snore tv",
            "massage massage_head massage_foot massage_wave massage_timer_step alarm light",
        ),
        (
            "S655",
            "S655",
            2,
            "back legs dual tilt",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_off massage_timer_set light",
        ),
        (
            "S750",
            "S750",
            2,
            "back legs tilt lumbar",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_timer_step alarm light",
        ),
        (
            "S755",
            "S755",
            2,
            "back legs dual tilt lumbar",
            "zero_g tv anti_snore lounge",
            "massage massage_head massage_foot massage_wave massage_off massage_timer_set light",
        ),
    ],
)
def test_all_model_constructor_contracts(
    key: str, name: str, slots: int, manual: str, presets: str, functions: str
) -> None:
    profile = MALOUF_APP_MODELS[key]
    assert (
        profile.name,
        profile.memory_slots,
        profile.manual,
        profile.presets,
        profile.functions,
    ) == (name, slots, tuple(manual.split()), tuple(presets.split()), tuple(functions.split()))


@pytest.mark.parametrize(
    ("method", "args", "model", "expected"),
    [
        ("move_back_up", (), "S755", "24"),
        ("move_back_down", (), "S755", "25"),
        ("move_legs_up", (), "S755", "26"),
        ("move_legs_down", (), "S755", "27"),
        ("move_simultaneously", ("back", True, "legs", True), "S755", "29"),
        ("move_simultaneously", ("back", False, "legs", False), "S755", "2a"),
        ("program_memory", (1,), "S755", "2b"),
        ("program_memory", (2,), "S755", "2c"),
        ("preset_memory", (1,), "S755", "2e"),
        ("preset_memory", (2,), "S755", "2f"),
        ("preset_flat", (), "S755", "31"),
        ("lights_toggle", (), "S755", "3c"),
        ("move_tilt_up", (), "S755", "3f"),
        ("move_tilt_down", (), "S755", "40"),
        ("move_full_tilt_up", (), "Altitude", "3f"),
        ("move_full_tilt_down", (), "Altitude", "40"),
        ("move_lumbar_up", (), "S755", "41"),
        ("move_lumbar_down", (), "S755", "42"),
        ("move_tilt_head_up", (), "Altitude", "41"),
        ("move_tilt_head_down", (), "Altitude", "42"),
        ("preset_zero_g", (), "S755", "45"),
        ("preset_anti_snore", (), "S755", "46"),
        ("massage_off", (), "S755", "47"),
        ("massage_mode_step", (), "S755", "48"),
        ("massage_head_toggle", (), "S755", "4c"),
        ("massage_foot_toggle", (), "S755", "4e"),
        ("preset_tv", (), "S755", "58"),
        ("preset_lounge", (), "S755", "59"),
        ("set_massage_timer", (10,), "S755", "5f"),
        ("set_massage_timer", (20,), "S755", "63"),
        ("set_massage_timer", (30,), "S755", "61"),
        ("stop_all", (), "S755", "6e"),
    ],
)
async def test_all_reachable_richmat_action_vectors(
    method: str, args: tuple[object, ...], model: str, expected: str
) -> None:
    ctrl = make_controller("richmat_single", model)
    ctrl._coordinator.motor_pulse_count = 1
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await getattr(ctrl, method)(*args)
    assert written(ctrl)[0].hex() == expected


@pytest.mark.parametrize(
    ("method", "args", "model", "expected"),
    [
        ("stop_all", (), "S750", "00000000"),
        ("move_back_up", (), "S750", "00000001"),
        ("move_back_down", (), "S750", "00000002"),
        ("move_legs_up", (), "S750", "00000004"),
        ("move_legs_down", (), "S750", "00000008"),
        ("move_simultaneously", ("back", True, "legs", True), "Premium", "00000005"),
        ("move_simultaneously", ("back", False, "legs", False), "Premium", "0000000a"),
        ("move_tilt_up", (), "S750", "00000010"),
        ("move_tilt_down", (), "S750", "00000020"),
        ("move_lumbar_up", (), "S750", "00000040"),
        ("move_lumbar_down", (), "S750", "00000080"),
        ("massage_toggle", (), "S750", "00000200"),
        ("massage_foot_toggle", (), "S750", "00000400"),
        ("massage_head_toggle", (), "S750", "00000800"),
        ("preset_zero_g", (), "S750", "00001000"),
        ("preset_lounge", (), "S750", "00002000"),
        ("preset_read", (), "Premium", "00002000"),
        ("preset_tv", (), "S750", "00004000"),
        ("preset_anti_snore", (), "S750", "00008000"),
        ("preset_memory", (1,), "S750", "00010000"),
        ("lights_toggle", (), "S750", "00020000"),
        ("preset_memory", (2,), "S750", "00040000"),
        ("preset_flat", (), "S750", "08000000"),
        ("massage_mode_step", (), "S750", "10000000"),
    ],
)
async def test_all_reachable_okin_action_vectors(
    method: str, args: tuple[object, ...], model: str, expected: str
) -> None:
    ctrl = make_controller("okin_custom", model, "lucid")
    ctrl._coordinator.motor_pulse_count = 1
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await getattr(ctrl, method)(*args)
    assert written(ctrl)[0][2:6].hex() == expected


@pytest.mark.parametrize(
    ("transport", "slot", "name", "value"),
    [
        (transport, slot, name, value)
        for transport in ("okin_legacy", "okin_custom", "okin_new")
        for slot, name, value in (
            (1, "OKIN", "00010000"),
            (1, "Smartbed238", "80010000"),
            (2, "OKIN", "80040000"),
        )
    ],
)
async def test_okin_memory_save_values_on_every_variant(
    transport: str, slot: int, name: str, value: str
) -> None:
    ctrl = make_controller(transport, "S750")
    ctrl._coordinator.observed_ble_device_name = name
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await ctrl.program_memory(slot)
    data = written(ctrl)
    actual = data[0][3:7][::-1] if transport == "okin_legacy" else data[0][2:6]
    assert actual.hex() == value
    assert len(data) == (55 if transport == "okin_new" else 85)
    assert len(set(data)) == 1


@pytest.mark.parametrize(
    ("preset", "type_value"),
    [
        ("zero_g", 13),
        ("lounge", 14),
        ("tv", 15),
        ("anti_snore", 16),
        ("memory_1", 17),
        ("memory_2", 18),
    ],
)
async def test_six_reachable_alarm_types(preset: str, type_value: int) -> None:
    ctrl = make_controller("okin_new", "S750")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.dt_util.now",
        return_value=datetime(2026, 7, 14, 7, 30, 45),
    ):
        await ctrl.configure_clock_alarm(
            enabled=True, weekdays=[0], hour=8, minute=0, preset=preset
        )
    assert written(ctrl)[-1][3] == type_value - 12


@pytest.mark.parametrize(
    ("light_byte", "raw", "is_on"),
    [(0, 0, False), (0x40, 1, True), (0x80, -2, True), (0xFF, -1, True)],
)
def test_legacy_light_boolean_matches_artifact_ui_nonzero_selection(
    light_byte: int, raw: int, is_on: bool
) -> None:
    ctrl = make_controller("okin_legacy", "S750")
    sender = MagicMock(uuid=TRANSPORTS["okin_legacy"].notify_characteristic)
    data = bytearray(10)
    data[7] = light_byte
    ctrl._notification_handler(sender, data)
    assert ctrl.get_light_state() == {"is_on": is_on}
    assert ctrl.protocol_diagnostics["underbed_light_status"] == raw
    assert (
        ctrl._coordinator.handle_controller_state_updates.call_args.args[0]["underbed_light_on"]
        is is_on
    )


async def test_timed_combined_motion_ceiling_stops_refresh_before_release() -> None:
    ctrl = make_controller("richmat_framed")
    loop = asyncio.get_running_loop()
    writes: list[tuple[float, bytes]] = []

    async def record(uuid: str, payload: bytes, *, response: bool) -> None:
        writes.append((loop.time(), payload))

    ctrl.client.write_gatt_char.side_effect = record
    started = loop.time()
    await ctrl.move_simultaneously("back", True, "legs", True, duration_ms=1000)
    refreshes = [timestamp - started for timestamp, payload in writes if payload[3] == 0x29]
    assert len(refreshes) == 7
    assert all(timestamp < 1 for timestamp in refreshes)
    assert writes[-1][1].hex() == "6e01006edd"
    assert writes[-1][0] - started >= 1.15


async def test_timed_combined_motion_preserves_controller_timeout_and_still_releases() -> None:
    ctrl = make_controller("richmat_framed")

    async def timeout_on_motion(uuid: str, payload: bytes, *, response: bool) -> None:
        if payload[3] == 0x29:
            raise TimeoutError("Peripheral write timed out")

    ctrl.client.write_gatt_char.side_effect = timeout_on_motion
    with (
        patch(
            "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
        ),
        pytest.raises(TimeoutError, match="Peripheral write timed out"),
    ):
        await ctrl.move_simultaneously("back", True, "legs", True, duration_ms=1000)
    assert [frame.hex() for frame in written(ctrl)] == ["6e01002998", "6e01006edd"]


async def test_timed_motion_preserves_controller_timeout_during_deadline_cancellation() -> None:
    ctrl = make_controller("richmat_framed")

    async def timeout_during_cancellation(uuid: str, payload: bytes, *, response: bool) -> None:
        if payload[3] == 0x29:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError as err:
                raise TimeoutError("Controller timed out during cancellation") from err

    ctrl.client.write_gatt_char.side_effect = timeout_during_cancellation
    with pytest.raises(TimeoutError, match="Controller timed out during cancellation"):
        await ctrl.move_simultaneously("back", True, "legs", True, duration_ms=20)
    assert [frame.hex() for frame in written(ctrl)] == ["6e01002998", "6e01006edd"]


@pytest.mark.parametrize("duration_ms", [0, -1])
async def test_timed_combined_motion_rejects_nonpositive_duration_before_write(
    duration_ms: int,
) -> None:
    ctrl = make_controller("richmat_framed")
    with pytest.raises(ValueError, match="duration must be positive"):
        await ctrl.move_simultaneously("back", True, "legs", True, duration_ms=duration_ms)
    assert written(ctrl) == []


async def test_alarm_clear_ignores_unused_memory_preset_capacity() -> None:
    ctrl = make_controller("okin_new", "L600")
    await ctrl.configure_clock_alarm(
        enabled=False, weekdays=[], hour=0, minute=0, preset="memory_2"
    )
    assert [frame.hex() for frame in written(ctrl)] == ["070500f40000000000"]


@pytest.mark.parametrize("model", ["GoodLifeBase", "GoodLifePremierBase", "GoodLifeProBase"])
@pytest.mark.parametrize(
    ("transport", "expected", "count", "initial_delay"),
    [
        ("richmat_single", "2c", 1, None),
        ("richmat_framed", "6e01002c9b", 1, None),
        ("okin_legacy", "e6fe16000004800081", 85, 0.15),
        ("okin_custom", "04028004000000000000", 85, 0.15),
        ("okin_new", "0502800400000000", 55, 0.1),
    ],
)
async def test_lucid_oz_long_hold_editor_slot2_save_vectors(
    model: str,
    transport: str,
    expected: str,
    count: int,
    initial_delay: float | None,
) -> None:
    ctrl = make_controller(transport, model, "lucid", primary=False)
    assert ctrl.memory_slot_count == 0
    assert not ctrl.supports_memory_presets and not ctrl.supports_memory_programming
    spec = ctrl.controller_button_specs[0]
    assert (spec.key, spec.name) == ("malouf_oz_save_memory_2", "Save Memory 2")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await spec.press_fn(ctrl.bind_side("left"))
    assert written(ctrl) == [bytes.fromhex(expected)] * count
    if initial_delay is not None:
        assert sleep.call_args_list[0].args == (initial_delay,)
        assert (
            ctrl._coordinator.record_command_trace.call_args.kwargs["repeat_delay_ms"]
            == initial_delay * 1000
        )
    for standard_action in (ctrl.program_memory, ctrl.preset_memory):
        with pytest.raises(ValueError, match="no memory slot"):
            await standard_action(2)
    assert len(written(ctrl)) == count
    with pytest.raises(ValueError, match="Read has no writable endpoint"):
        await ctrl.preset_read()


@pytest.mark.parametrize(
    ("app", "model"),
    [
        ("malouf", "GoodLifeBase"),
        ("malouf", "GoodLifePremierBase"),
        ("malouf", "GoodLifeProBase"),
        ("lucid", "L300"),
        ("lucid", "Premium"),
    ],
)
async def test_oz_memory_editor_is_restricted_to_exact_lucid_models(app: str, model: str) -> None:
    ctrl = make_controller("richmat_framed", model, app)
    assert all(spec.key != "malouf_oz_save_memory_2" for spec in ctrl.controller_button_specs)
    with pytest.raises(ValueError, match="no Oz preset memory editor"):
        await ctrl.save_oz_memory_position()
    assert written(ctrl) == []


async def test_oz_memory_editor_callback_uses_current_controller() -> None:
    old = make_controller("richmat_framed", "GoodLifeBase", "lucid", primary=False)
    current = make_controller("richmat_framed", "GoodLifeBase", "lucid", primary=False)
    await old.controller_button_specs[0].press_fn(current.bind_side("right"))
    assert written(old) == []
    assert written(current) == [bytes.fromhex("6e01002c9b")]
