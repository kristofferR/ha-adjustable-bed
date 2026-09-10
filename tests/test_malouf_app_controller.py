"""Controller lifecycle and capability checks against accepted app vectors."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.malouf_app import MaloufAppController
from custom_components.adjustable_bed.malouf_app_protocol import (
    TRANSPORT_PROFILES,
    encode_alarm,
    encode_command,
    encode_time,
)


def make_controller(transport="command32_new", model="s755", app="malouf"):
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 3
    coordinator.ble_device_name = "Test bed"
    coordinator.client = MagicMock(is_connected=True)
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    role = TRANSPORT_PROFILES[transport]
    services = {}
    for service_uuid, characteristic_uuid, properties in (
        (role.service_uuid, role.write_uuid, ["write-without-response"]),
        (role.notify_service_uuid, role.notify_uuid, ["notify"]),
    ):
        if service_uuid is None:
            continue
        service = services.setdefault(service_uuid, MagicMock(uuid=service_uuid))
        if not isinstance(service.characteristics, list):
            service.characteristics = []
        service.characteristics.append(
            SimpleNamespace(uuid=characteristic_uuid, properties=properties)
        )
        service.get_characteristic.side_effect = lambda key, service=service: next(
            (char for char in service.characteristics if char.uuid == key), None
        )
    collection = MagicMock()
    collection.__iter__.side_effect = lambda: iter(services.values())
    collection.get_service.side_effect = services.get
    coordinator.client.services = collection
    controller = MaloufAppController(coordinator, app_profile=app, model=model, transport=transport)
    controller.write_command = AsyncMock()
    return controller, coordinator


@pytest.mark.parametrize("transport", TRANSPORT_PROFILES)
async def test_manual_release_and_native_cadence(transport):
    controller, coordinator = make_controller(transport)
    controller._wait = AsyncMock(return_value=True)
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ) as sleep:
        await controller.move_back_up()
    assert controller.motor_pulse_settings() == (3, 150)
    assert [call.args[0] for call in controller.write_command.call_args_list] == [
        encode_command("headUp", transport),
    ] * 3 + [encode_command("stopDriver", transport)]
    assert controller._wait.await_count == 2
    sleep.assert_awaited_once_with(0.15)
    release_cancel = controller.write_command.call_args.kwargs["cancel_event"]
    assert release_cancel is not coordinator.cancel_command
    assert not release_cancel.is_set()


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
async def test_manual_failure_still_releases(failure):
    controller, _ = make_controller()
    controller.write_command.side_effect = [failure(), None]
    with (
        patch(
            "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
        ),
        pytest.raises(failure),
    ):
        await controller.move_back_up()
    assert controller.write_command.call_args.args[0] == encode_command(
        "stopDriver", "command32_new"
    )
    assert not controller.write_command.call_args.kwargs["cancel_event"].is_set()


async def test_event_cancel_releases_without_more_movement():
    controller, coordinator = make_controller()

    async def cancel_after_write(*args, **kwargs):
        coordinator.cancel_command.set()

    controller.write_command.side_effect = cancel_after_write
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.sleep", new_callable=AsyncMock
    ):
        await controller.move_back_up()
    assert controller.write_command.await_count == 2
    assert not controller.write_command.call_args.kwargs["cancel_event"].is_set()


@pytest.mark.parametrize(
    "transport,copies,release",
    [
        ("command32_legacy", 3, False),
        ("command32_middle", 3, True),
        ("command32_new", 1, True),
        ("opcode_legacy", 1, True),
        ("opcode_framed", 1, False),
    ],
)
async def test_preset_transport_release_policy(transport, copies, release):
    controller, _ = make_controller(transport)
    await controller.preset_zero_g()
    first = controller.write_command.call_args_list[0]
    assert first.args[0] == encode_command("zeroG", transport)
    assert first.kwargs["repeat_count"] == copies
    assert controller.write_command.await_count == 1 + release


@pytest.mark.parametrize(
    "transport,count",
    [
        ("command32_legacy", 85),
        ("command32_middle", 85),
        ("command32_new", 55),
        ("opcode_framed", 1),
    ],
)
async def test_memory_program_schedule_has_initial_wait_and_no_invented_release(transport, count):
    controller, _ = make_controller(transport)
    controller._wait = AsyncMock(return_value=True)
    await controller.program_memory(2)
    assert controller.write_command.await_count == count
    assert all(
        call.args[0] == encode_command("setMemory2", transport)
        for call in controller.write_command.call_args_list
    )
    assert controller._wait.await_count == (count if transport.startswith("command32") else 0)


async def test_memory_cancel_during_initial_delay_sends_nothing():
    controller, _ = make_controller()
    controller._wait = AsyncMock(return_value=False)
    await controller.program_memory(1)
    controller.write_command.assert_not_awaited()


async def test_model_gates_and_callbacks_use_current_controller():
    old, _ = make_controller("opcode_framed", "altitude")
    current, _ = make_controller("opcode_framed", "altitude")
    current.execute_action = AsyncMock()
    await next(spec for spec in old.motor_control_specs if spec.key == "full_tilt").open_fn(current)
    current.execute_action.assert_awaited_once_with("fullTiltUp")
    simple, coordinator = make_controller("command32_new", "e450")
    coordinator.client = None
    assert {spec.key for spec in simple.motor_control_specs} == {"back", "legs"}
    assert {"head", "lumbar", "dual", "full_tilt"} <= simple.stale_motor_entity_keys
    assert not simple.supports_massage
    assert not simple.supports_position_feedback
    with pytest.raises(ValueError):
        await simple.massage_head_toggle()
    simple.write_command.assert_not_awaited()


async def test_primary_override_is_per_action():
    controller, _ = make_controller("command32_legacy")
    await controller.execute_app_action("zeroG", primary=False)
    assert controller.write_command.call_args.args[0] == encode_command(
        "zeroG", "command32_legacy", primary=False
    )
    await controller.execute_app_action("zeroG")
    assert controller.write_command.call_args.args[0] == encode_command(
        "zeroG", "command32_legacy", primary=True
    )


@pytest.mark.parametrize("transport", ["command32_legacy", "command32_middle", "command32_new"])
async def test_alarm_validates_before_clear_then_clock_and_alarm(transport):
    controller, _ = make_controller(transport, "e450")
    now = datetime(2026, 7, 14, 7, 30, 45)
    with patch("custom_components.adjustable_bed.beds.malouf_app.dt_util.now", return_value=now):
        await controller.configure_clock_alarm(
            enabled=True, weekdays=(0, 6), hour=8, minute=5, preset="memory_2"
        )
    assert controller.clock_alarm_presets == (
        "zero_g",
        "lounge",
        "tv",
        "anti_snore",
        "memory_1",
        "memory_2",
        "massage",
        "flat",
    )
    assert [call.args[0] for call in controller.write_command.call_args_list] == [
        encode_alarm(transport, 0, 0, 0, 0),
        encode_time(transport, now),
        encode_alarm(transport, 8, 5, 18, 131),
    ]
    assert all(
        call.kwargs["repeat_count"] == (1 if transport.endswith("new") else 3)
        for call in controller.write_command.call_args_list
    )


@pytest.mark.parametrize("hour,minute,weekday_bit", [(7, 31, 4), (7, 30, 8), (6, 30, 8)])
async def test_one_shot_alarm_uses_next_occurrence_without_repeat_bit(hour, minute, weekday_bit):
    controller, _ = make_controller("command32_legacy")
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.dt_util.now",
        return_value=datetime(2026, 7, 14, 7, 30),
    ):
        await controller.configure_clock_alarm(
            enabled=True, weekdays=(), hour=hour, minute=minute, preset="flat"
        )
    assert controller.write_command.call_args.args[0] == encode_alarm(
        "command32_legacy", hour, minute, 21, weekday_bit
    )


@pytest.mark.parametrize(
    "invalid",
    [{"weekdays": (True,)}, {"hour": 24}, {"minute": -1}, {"preset": "unknown"}, {"head_level": 1}],
)
async def test_invalid_alarm_never_clears_existing_alarm(invalid):
    controller, _ = make_controller()
    kwargs = {
        "enabled": True,
        "weekdays": (0,),
        "hour": 8,
        "minute": 0,
        "preset": "zero_g",
    } | invalid
    with pytest.raises(ValueError):
        await controller.configure_clock_alarm(**kwargs)
    controller.write_command.assert_not_awaited()


async def test_disabled_alarm_ignores_unused_fields():
    controller, _ = make_controller("command32_middle")
    await controller.configure_clock_alarm(enabled=False, weekdays=(), hour=0, minute=0, preset="")
    controller.write_command.assert_awaited_once_with(
        encode_alarm("command32_middle", 0, 0, 0, 0), repeat_count=3
    )


@pytest.mark.parametrize("transport", TRANSPORT_PROFILES)
async def test_explicit_gatt_profile_validation(transport):
    controller, _ = make_controller(transport)
    await controller.async_discover_capabilities()
    controller.write_command.assert_not_awaited()


async def test_gatt_wrong_properties_rejected_before_bootstrap():
    controller, coordinator = make_controller()
    service = coordinator.client.services.get_service(
        TRANSPORT_PROFILES["command32_new"].service_uuid
    )
    service.characteristics[0].properties = ["write"]
    with pytest.raises(ValueError, match="unacknowledged"):
        await controller.start_notify()
    controller.write_command.assert_not_awaited()
    coordinator.client.start_notify.assert_not_awaited()


async def test_notifications_preserve_raw_signed_light_and_deduplicate():
    controller, coordinator = make_controller("command32_legacy")
    sender = SimpleNamespace(uuid=TRANSPORT_PROFILES["command32_legacy"].notify_uuid)
    data = bytearray.fromhex("00000000000000800300")
    controller._notification_handler(sender, data)
    controller._notification_handler(sender, data)
    coordinator.handle_controller_state_updates.assert_called_once()
    updates = coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["malouf_app_massage_minutes"] == 30
    assert updates["malouf_app_light_raw"] == -2
    assert updates["malouf_app_under_bed_light"] is False
    assert controller.get_light_state() == {"is_on": False}
    middle, _ = make_controller("command32_middle")
    assert not middle.controller_state_binary_sensor_specs


@pytest.mark.parametrize("transport", ["command32_legacy", "opcode_framed"])
async def test_abnormal_preset_completion_sends_defined_stop(transport):
    controller, _ = make_controller(transport)
    controller.write_command.side_effect = [asyncio.CancelledError(), None]
    with pytest.raises(asyncio.CancelledError):
        await controller.preset_zero_g()
    assert controller.write_command.call_args.args[0] == encode_command("stopDriver", transport)
    assert not controller.write_command.call_args.kwargs["cancel_event"].is_set()


async def test_subscription_does_not_send_unsolicited_application_writes():
    controller, coordinator = make_controller()
    await controller.start_notify()
    await controller.start_notify()
    coordinator.client.start_notify.assert_awaited_once()
    controller.write_command.assert_not_awaited()
    await controller.stop_notify()
    await controller.start_notify()
    assert coordinator.client.start_notify.await_count == 2


async def test_subscription_failure_can_retry():
    controller, coordinator = make_controller()
    coordinator.client.start_notify.side_effect = [RuntimeError("subscribe failed"), None]
    with pytest.raises(RuntimeError):
        await controller.start_notify()
    assert not controller._subscribed
    await controller.start_notify()
    assert controller._subscribed


async def test_explicit_transport_ignores_other_complete_profiles():
    controller, coordinator = make_controller()
    original = list(coordinator.client.services)
    extra = MagicMock(uuid=TRANSPORT_PROFILES["opcode_framed"].service_uuid)
    coordinator.client.services.__iter__.side_effect = lambda: iter([*original, extra])
    await controller.async_discover_capabilities()


@pytest.mark.parametrize("transport", TRANSPORT_PROFILES)
async def test_lucid_fallback_save_is_routed_only(transport):
    controller, _ = make_controller(transport, "good_life_base", "lucid")
    controller._wait = AsyncMock(return_value=True)
    assert controller.memory_slot_count == 0
    assert "setMemory2" in controller.app_action_options
    assert "setMemory1" not in controller.app_action_options
    assert "memory2" not in controller.app_action_options
    with pytest.raises(ValueError):
        await controller.program_memory(2)
    await controller.execute_app_action("setMemory2")
    assert controller.write_command.call_args.args[0] == encode_command("setMemory2", transport)


async def test_absolute_program_cadence_absorbs_write_latency():
    controller, _ = make_controller("command32_new")
    tick = 0.0
    waits = []

    async def wait(delay, cancel):
        nonlocal tick
        waits.append(delay)
        tick += delay
        return True

    async def write(*args, **kwargs):
        nonlocal tick
        tick += 0.02

    controller._wait = wait
    controller.write_command.side_effect = write
    clock = SimpleNamespace(time=lambda: tick)
    with patch(
        "custom_components.adjustable_bed.beds.malouf_app.asyncio.get_running_loop",
        return_value=clock,
    ):
        await controller.program_memory(1)
    assert waits[0] == pytest.approx(0.1)
    assert waits[1:] == pytest.approx([0.08] * 54)
    assert tick == pytest.approx(5.52)


@pytest.mark.parametrize("transport", TRANSPORT_PROFILES)
async def test_write_uses_only_selected_characteristic_without_response(transport):
    controller, _ = make_controller(transport)
    controller._write_gatt_with_retry = AsyncMock()
    cancel = asyncio.Event()
    await MaloufAppController.write_command(controller, b"payload", 3, 0, cancel)
    controller._write_gatt_with_retry.assert_awaited_once_with(
        TRANSPORT_PROFILES[transport].write_uuid,
        b"payload",
        repeat_count=3,
        repeat_delay_ms=0,
        cancel_event=cancel,
        response=False,
    )


@pytest.mark.parametrize("transport", TRANSPORT_PROFILES)
async def test_massage_click_mapping_and_followup_query(transport):
    controller, _ = make_controller(transport, "s755")
    if transport.startswith("command32"):
        assert controller.supports_massage_timer_cycle_control
        assert not controller.supports_massage_off_control
        await controller.massage_timer_cycle()
        action = "massageTimer"
    else:
        assert not controller.supports_massage_timer_cycle_control
        assert controller.supports_massage_off_control
        await controller.massage_off()
        action = "massageOff"
    assert controller.write_command.call_args_list[0].args[0] == encode_command(action, transport)
    if transport == "command32_new":
        assert controller.write_command.call_args_list[1].args[0] == bytes.fromhex("00b0")
    else:
        assert controller.write_command.await_count == 1


async def test_explicit_timer_is_separate_from_wave_and_model_gated():
    controller, _ = make_controller("opcode_framed", "s755")
    assert controller.supports_massage_mode_step_control
    assert controller.massage_timer_options == [10, 20, 30]
    await controller.set_massage_timer(20)
    controller.write_command.assert_awaited_once_with(encode_command("massage20", "opcode_framed"))
    limited, _ = make_controller("opcode_framed", "altitude")
    with pytest.raises(ValueError):
        await limited.set_massage_timer(20)
    limited.write_command.assert_not_awaited()
