"""GM Control sleep transport and finite HA session ownership."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.gmmotor_sleep import GmmotorSleepController
from custom_components.adjustable_bed.gmmotor_requests import Request
from custom_components.adjustable_bed.gmmotor_sleep_protocol import frame
from custom_components.adjustable_bed.gmmotor_sleep_state import (
    ClockUpdate,
    Followup,
    ReportSize,
    Stream,
    dispatch,
)
from custom_components.adjustable_bed.gmmotor_transport import SLEEP_NOTIFY, SLEEP_WRITE, Transport


def controller(hass: HomeAssistant, *, sxb: bool = True) -> GmmotorSleepController:
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.cancel_command = asyncio.Event()
    coordinator.client.is_connected = True
    coordinator.client.mtu_size = 23
    coordinator.client.write_gatt_char = AsyncMock()
    ctrl = GmmotorSleepController(coordinator, sxb=sxb)
    coordinator.controller = ctrl
    write = MagicMock(uuid=SLEEP_WRITE, handle=7)
    notify = MagicMock(uuid=SLEEP_NOTIFY, handle=8)
    ctrl._transport = Transport(write, (notify,), response=sxb)
    return ctrl


async def test_frame_is_chunked_at_mtu_without_per_chunk_delay(hass: HomeAssistant) -> None:
    ctrl = controller(hass, sxb=False)
    with patch("custom_components.adjustable_bed.beds.gmmotor_sleep._QUEUE_TICK", 0):
        await ctrl._send("q_part")
    calls = ctrl.client.write_gatt_char.call_args_list
    chunks = [call.args[1] for call in calls]
    assert len(chunks[0]) == 20 and all(len(c) <= 20 for c in chunks)
    assert json.loads(b"".join(chunks)[14:]) == {"id": 1, "cmd": "s_part", "val": None}
    assert all(call.kwargs["response"] is False for call in calls)
    assert ctrl._receive_buffer.command == "q_part"


async def test_native_error_drops_remaining_chunks_without_retry(hass: HomeAssistant) -> None:
    ctrl = controller(hass)
    ctrl.client.write_gatt_char.side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        await ctrl.write_command(b"x" * 60)
    assert ctrl.client.write_gatt_char.call_count == 1


async def test_global_native_mutex_serializes_independent_sessions(hass: HomeAssistant) -> None:
    first, second = controller(hass), controller(hass, sxb=False)
    active = maximum = 0

    async def write(*args, **kwargs):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0)
        active -= 1

    first.client.write_gatt_char.side_effect = second.client.write_gatt_char.side_effect = write
    await asyncio.gather(first.write_command(b"a" * 40), second.write_command(b"b" * 40))
    assert maximum == 1
    assert first.client.write_gatt_char.call_count == second.client.write_gatt_char.call_count == 2


async def test_local_stop_invalidates_delayed_followup_without_wire_stop(
    hass: HomeAssistant,
) -> None:
    ctrl = controller(hass)
    ctrl._queue("q_time", delayed=True)
    await ctrl.async_execute_gmmotor_request(Request("sensor_stop"))
    await hass.async_block_till_done()
    ctrl.client.write_gatt_char.assert_not_awaited()
    ctrl._coordinator.async_execute_controller_command.assert_not_called()
    assert ctrl._receive_buffer.command is None and not ctrl._tasks


def test_report_size_and_future_order_match_source() -> None:
    clock = dict.fromkeys(("0x7", "0xb", "0xf", "0x13", "0x17", "0x1b"))
    effects = dispatch(
        b'{"id":7,"cmd":"q_report","val":{"fsize":16}}',
        sxb=True,
        active="q_report",
        clock=clock,
        session_side=1,
        report_type=1,
    )
    assert effects == (ReportSize(16), Followup("q_report_allow", delayed=True))
    effects = dispatch(
        b'{"id":7,"cmd":"q_report","val":{"fsize":0}}',
        sxb=False,
        active="q_report",
        clock=clock,
        session_side=2,
        report_type=1,
    )
    assert effects[0] == ReportSize(0)
    assert effects[1] == Stream(
        "0x13",
        {"class": "RMSleepReportSizeRespWrapBean", "fields": {"0x7": 2, "0xf": 1, "0x17": 0}},
    )


def test_time_publication_precedes_clock_update_and_followup() -> None:
    clock = dict.fromkeys(("0x7", "0xb", "0xf", "0x13", "0x17", "0x1b"))
    effects = dispatch(
        b'{"id":7,"cmd":"s_time","val":{"error":0,"ver":"0.0.3.0","type":"test"}}',
        sxb=True,
        active="s_time",
        clock=clock,
        session_side=1,
        report_type=1,
    )
    assert isinstance(effects[0], Stream)
    assert effects[1:] == (ClockUpdate({"0x7": "test", "0xb": "0.0.3.0"}), Followup("q_time"))
    # A null optional value still emits then queries device time.
    null = dispatch(
        b'{"id":7,"cmd":"s_time","val":null}',
        sxb=True,
        active="s_time",
        clock=clock,
        session_side=1,
        report_type=1,
    )
    assert len(null) == 2 and isinstance(null[0], Stream) and null[1] == Followup("q_time")


def test_sxb_part_setter_marks_its_response(hass: HomeAssistant) -> None:
    ctrl = controller(hass)
    effects = dispatch(
        b'{"id":7,"cmd":"s_part","val":12}',
        sxb=True,
        active="s_part",
        clock=ctrl._clock,
        session_side=1,
        report_type=1,
    )
    assert isinstance(effects[0], Stream)
    assert isinstance(effects[0].value, dict)
    fields = effects[0].value["fields"]
    assert isinstance(fields, dict)
    assert fields["0x17"] is True
    ctrl._publish(effects[0])
    assert ctrl._reported_part == 12


async def test_setting_pages_admit_distinct_part_values(hass: HomeAssistant) -> None:
    sxb, normal = controller(hass), controller(hass, sxb=False)
    sxb._send = normal._send = AsyncMock()
    await normal.async_execute_gmmotor_request(Request("sensor_part", value=2))
    await sxb.async_execute_gmmotor_request(Request("sensor_part", value=13))
    assert normal._device_part == 2 and sxb._device_part == 13
    with pytest.raises(ValueError):
        sxb.validate_gmmotor_request(Request("sensor_part", value=2))
    with pytest.raises(ValueError):
        normal.validate_gmmotor_request(Request("sensor_part", value=13))
    with pytest.raises(ValueError):
        normal.validate_gmmotor_request(Request("sensor_sensitivity"))
    sxb._reported_part = 12
    sxb._send.reset_mock()
    await sxb.async_execute_gmmotor_request(Request("sensor_part", value=12))
    sxb._send.assert_not_awaited()


def test_live_receive_uses_actual_consumer_gates(hass: HomeAssistant) -> None:
    ctrl = controller(hass)
    ctrl._receive_buffer.start("q_realtime")
    payload = json.dumps(
        {"id": 7, "cmd": "q_realtime", "val": {"L": [0, -2, 65, 17, 1], "R": [1]}}
    ).encode()
    ctrl._receive(MagicMock(uuid="notify"), bytearray(frame(payload, 7)))
    update = ctrl._coordinator.handle_controller_state_updates.call_args.args[0]
    assert update["gmmotor_sleep_left"] == {
        "first_value": "65",
        "second_value": "17",
        "on_bed": True,
        "moving": True,
        "snoring": True,
        "online": True,
    }
    assert "gmmotor_sleep_right" not in update
    assert ctrl._invalid == 0


@pytest.mark.parametrize("sxb", [False, True])
@pytest.mark.parametrize("size", [0, -1])
async def test_terminal_report_size_preserves_publication_and_resumes_live_polling(
    hass: HomeAssistant,
    sxb: bool,
    size: int,
) -> None:
    ctrl = controller(hass, sxb=sxb)
    ctrl._live_enabled = True
    ctrl._receive_buffer.start("q_report")
    ctrl._queue = MagicMock()
    payload = json.dumps({"id": 7, "cmd": "q_report", "val": {"fsize": size}}).encode()
    ctrl._receive(MagicMock(uuid="notify"), bytearray(frame(payload, 7)))
    assert ctrl._streams["report_size"] == {
        "class": "SxbSleepReportSizeRespWrapBean" if sxb else "RMSleepReportSizeRespWrapBean",
        "fields": {"0x7": 1, "0xf": 1, "0x17": size},
    }
    ctrl._queue.assert_not_called()
    ctrl._poll()
    ctrl._queue.assert_called_once_with("q_realtime")
    assert ctrl._live_enabled and ctrl._receive_buffer.command is None
    ctrl.on_disconnect()


async def test_sxb_stale_window_keeps_a_seen_side_then_clears_each_empty_window(
    hass: HomeAssistant,
) -> None:
    ctrl = controller(hass)
    ctrl._live_enabled = True
    ctrl._receive_buffer.start("q_realtime")
    ctrl._receive(
        MagicMock(uuid="notify"),
        bytearray(frame(b'{"id":7,"cmd":"q_realtime","val":{"L":[0,1,65,17,0],"R":[1]}}', 7)),
    )
    ctrl._stale_tick()
    updates = ctrl._coordinator.handle_controller_state_updates.call_args.args[0]
    assert "gmmotor_sleep_left" not in updates
    assert updates["gmmotor_sleep_right"]["online"] is False
    ctrl._stale_timer.cancel()
    ctrl._stale_tick()
    updates = ctrl._coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["gmmotor_sleep_left"]["online"] is False
    assert updates["gmmotor_sleep_left"]["first_value"] is None
    ctrl.on_disconnect()
    assert ctrl._stale_timer is None


async def test_notification_cleanup_clears_resources_without_ending_live_intent(
    hass: HomeAssistant,
) -> None:
    ctrl = controller(hass)
    ctrl._live_enabled = True
    timer = asyncio.get_running_loop().call_later(3600, lambda: None)
    ctrl._poll_timer = timer
    ctrl._subscriptions = list(ctrl._transport.notifications)
    ctrl.client.stop_notify = AsyncMock()
    await ctrl.stop_notify()
    assert ctrl._live_enabled and ctrl._poll_timer is None and timer.cancelled()
    assert ctrl._transport is None and not ctrl._subscriptions
    ctrl.client.stop_notify.assert_awaited_once()
