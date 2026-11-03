"""GM Control controller lifecycle, cancellation and source event consumption."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.gmmotor import GmmotorController
from custom_components.adjustable_bed.gmmotor_notifications import Event
from custom_components.adjustable_bed.gmmotor_requests import Request
from custom_components.adjustable_bed.gmmotor_transport import E0FF, P1_SERVICES


def controller(profile: str = "6BRM", side: str = "left") -> GmmotorController:
    coordinator = MagicMock()
    coordinator.hass.data = {}
    coordinator.cancel_command = asyncio.Event()
    coordinator.client.is_connected = True
    coordinator.client.mtu_size = 23
    coordinator.client.write_gatt_char = AsyncMock()
    return GmmotorController(coordinator, profile=profile, side=side)


def named(ctrl: GmmotorController, name: str) -> str:
    return next(f"gm_{i}" for i, a in enumerate(ctrl.profile.controls) if a.material.name == name)


async def test_sustain_tick_and_failure_cleanup_use_fresh_side_release() -> None:
    ctrl = controller(side="right")
    ctrl._pause = AsyncMock(return_value=True)
    ctrl.write_command = AsyncMock(side_effect=[RuntimeError("failed"), None])
    with pytest.raises(RuntimeError, match="failed"):
        await ctrl.hold_control(named(ctrl, "deviceFunctionItemHeadUp"), 100)
    assert [c.args[0] for c in ctrl.write_command.call_args_list] == [
        bytes.fromhex("6e01012494"),
        bytes.fromhex("6e01016ede"),
    ]
    assert not ctrl.write_command.call_args_list[-1].kwargs["cancel_event"].is_set()
    assert (
        ctrl.write_command.call_args_list[-1].kwargs["cancel_event"]
        is not ctrl._coordinator.cancel_command
    )


async def test_sub_tick_and_cancelled_before_first_tick_do_not_release() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    await ctrl.hold_control(named(ctrl, "deviceFunctionItemHeadUp"), 99)
    ctrl.write_command.assert_not_awaited()
    ctrl._pause = AsyncMock(return_value=False)
    await ctrl.hold_control(named(ctrl, "deviceFunctionItemHeadUp"), 100)
    ctrl.write_command.assert_not_awaited()


async def test_cancelled_running_hold_still_releases_bound_child() -> None:
    ctrl = controller("V9RM:1")
    ctrl._pause = AsyncMock(return_value=True)
    ctrl.write_command = AsyncMock(side_effect=[asyncio.CancelledError(), None])
    with pytest.raises(asyncio.CancelledError):
        await ctrl.bind_side("right").hold_control(named(ctrl, "deviceFunctionItemHeadUp"), 100)
    assert ctrl.write_command.call_args_list[-1].args[0] == bytes.fromhex("6e01016ede")


async def test_long_phase_waits_source_threshold_without_release() -> None:
    ctrl = controller("6DRM")
    ctrl._pause = AsyncMock(return_value=True)
    ctrl.write_command = AsyncMock()
    await ctrl.hold_control(named(ctrl, "deviceFunctionItemZeroGravity"), 3000)
    ctrl._pause.assert_awaited_once_with(3, ctrl._coordinator.cancel_command)
    assert [c.args[0] for c in ctrl.write_command.call_args_list] == [bytes.fromhex("6e010066d5")]


def test_outer_zero_length_does_not_promote_unreachable_ack() -> None:
    ctrl = controller()
    sender = MagicMock(uuid="notify")
    ctrl._receive(sender, bytearray.fromhex("6e090100786e2100008f"))
    assert ctrl._invalid_notifications == 1
    assert not ctrl._events
    ctrl._receive(sender, bytearray.fromhex("6e09010078"))
    assert ctrl._events == {"clock_capability": None}


def test_ha_raw_capture_fault_is_isolated_before_semantic_dispatch() -> None:
    ctrl = controller()

    def observer(_uuid, payload):
        assert payload == bytes.fromhex("6e09010078")
        assert not ctrl._events
        raise RuntimeError("capture failed")

    ctrl.set_raw_notify_callback(observer)
    ctrl._receive(MagicMock(uuid="notify"), bytearray.fromhex("6e09010078"))
    assert ctrl._events == {"clock_capability": None}


def test_required_field_failure_retains_prior_effect_and_drops_later_frames() -> None:
    ctrl = controller()
    sender = MagicMock(uuid="notify")
    ctrl._receive(sender, bytearray.fromhex("6e090100786e2004926e0e00037f"))
    assert ctrl._events == {"clock_capability": None}
    assert ctrl._invalid_notifications == 1
    assert ctrl._remainder_timer is None


def test_alarm_list_dedup_and_escalation_replace_existing_id_only() -> None:
    ctrl = controller()
    record = {"id": 1, "repeat": 0, "hour": 6, "minute": 30, "mode": 88, "status": 1}
    ctrl._accept(Event("alarm_list", record))
    ctrl._accept(Event("alarm_list", dict(record)))
    ctrl._accept(Event("alarm_escalation", {**record, "id": 2}))
    assert ctrl._alarms == [record]
    replacement = {**record, "hour": 7}
    ctrl._accept(Event("alarm_escalation", replacement))
    assert ctrl._alarms == [replacement]


async def test_write_uses_selected_role_no_retry_and_att_limit() -> None:
    ctrl = controller()
    write = MagicMock(uuid=P1_SERVICES[E0FF], properties=["write"], handle=7)
    notify = MagicMock(uuid="any-notify", properties=["notify"])
    ctrl.client.services = [MagicMock(uuid=E0FF, characteristics=[write, notify])]
    ctrl.client.start_notify = AsyncMock()
    ctrl.client.stop_notify = AsyncMock()
    with patch.object(ctrl, "write_command", new_callable=AsyncMock):
        ctrl._pause = AsyncMock(return_value=True)
        await ctrl.start_notify()
    assert ctrl._transport is not None and ctrl._subscribed
    ctrl.client.write_gatt_char.side_effect = RuntimeError("ATT failure")
    with pytest.raises(RuntimeError, match="ATT failure"):
        await ctrl.write_command(b"test")
    ctrl.client.write_gatt_char.assert_awaited_once_with(write, b"test", response=True)
    with pytest.raises(ValueError, match="ATT payload"):
        await ctrl.write_command(b"x" * 21)
    await ctrl.stop_notify()
    assert ctrl._transport is None and not ctrl._subscribed
    ctrl.client.stop_notify.assert_awaited_once_with(notify)


async def test_secondary_gates_are_exact_not_legacy_capabilities() -> None:
    ctrl = controller("FTRN")
    assert ctrl.profile.repeat_alarm and ctrl.profile.sleep_kind == "none"
    with pytest.raises(ValueError, match="BLE sleep"):
        ctrl.validate_gmmotor_request(Request("sleep_name"))
    ctrl.write_command = AsyncMock()
    ctrl.validate_gmmotor_request(Request("light_color"))
    with pytest.raises(ValueError, match="live light_capability"):
        await ctrl.async_execute_gmmotor_request(Request("light_color"))
    ctrl.write_command.assert_not_awaited()
    ctrl._accept(Event("light_capability"))
    await ctrl.async_execute_gmmotor_request(Request("light_color"))
    ctrl.write_command.assert_awaited_once()


async def test_alarm_and_snore_pages_require_their_actual_admission_paths() -> None:
    countdown = controller("A0RN")
    mode = countdown.profile.alarm_choices[0][0]
    countdown.write_command = AsyncMock()
    with pytest.raises(ValueError, match="live clock_capability"):
        await countdown.async_execute_gmmotor_request(Request("alarm_at", mode=mode, hour=7))
    countdown.write_command.assert_not_awaited()
    countdown._accept(Event("clock_capability"))
    countdown.validate_gmmotor_request(Request("alarm_at", mode=mode, hour=7))
    repeat = controller("FTRN")
    repeat._accept(Event("clock_capability"))
    with pytest.raises(ValueError, match="repeat-alarm page"):
        repeat.validate_gmmotor_request(
            Request("alarm_at", mode=repeat.profile.alarm_choices[0][0])
        )
    snore = controller("HNRN")
    snore.validate_gmmotor_request(Request("snore_query"))
    snore.validate_gmmotor_request(Request("snore_time", value=5))
    with pytest.raises(ValueError, match="slider range"):
        snore.validate_gmmotor_request(Request("snore_count", value=0))


@pytest.mark.parametrize("end", ["timeout", "disconnect", "stop", "cancel"])
async def test_missing_capability_never_writes_and_wait_ends(monkeypatch, end) -> None:
    ctrl = controller("FTRN")
    ctrl._subscribed = True
    ctrl.write_command = AsyncMock()
    waiting = asyncio.Event()
    wait = ctrl._capability_changed.wait

    async def observed_wait():
        waiting.set()
        await wait()

    monkeypatch.setattr(ctrl._capability_changed, "wait", observed_wait)
    if end == "timeout":
        monkeypatch.setattr("custom_components.adjustable_bed.beds.gmmotor._CAPABILITY_TIMEOUT", 0)
        with pytest.raises(ValueError, match="live light_capability"):
            await ctrl.async_execute_gmmotor_request(Request("light_off"))
    else:
        task = asyncio.create_task(ctrl.async_execute_gmmotor_request(Request("light_off")))
        await asyncio.wait_for(waiting.wait(), 1)
        if end == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            if end == "disconnect":
                ctrl.on_disconnect()
            else:
                await ctrl.stop_notify()
            with pytest.raises(ValueError, match="live light_capability"):
                await task
    ctrl.write_command.assert_not_awaited()
