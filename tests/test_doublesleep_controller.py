"""SleepEase session identity, serialized report flow and release behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import doublesleep_protocol as p
from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.doublesleep import DoubleSleepController, Session
from custom_components.adjustable_bed.const import BED_TYPE_DOUBLESLEEP
from custom_components.adjustable_bed.doublesleep_services import Request
from custom_components.adjustable_bed.doublesleep_state import Report
from tests.test_doublesleep_protocol import NOW, json_notification


class Bed:
    def __init__(self, driver="p2", model=10135, mtu=247):
        self.states = {}
        self.receivers = []
        self.tx = SimpleNamespace(
            uuid=p.TX_UUID,
            handle=1,
            properties=["write", "write-without-response"],
            max_write_without_response_size=mtu - 3,
        )
        self.rx = SimpleNamespace(uuid=p.RX_UUID, handle=2, properties=["notify"])
        self.client = SimpleNamespace(
            is_connected=True,
            mtu_size=mtu,
            services=SimpleNamespace(
                get_service=lambda uuid: SimpleNamespace(characteristics=[self.tx, self.rx]),
                get_characteristic=lambda uuid: None,
            ),
            start_notify=AsyncMock(
                side_effect=lambda char, callback: self.receivers.append(callback)
            ),
            stop_notify=AsyncMock(),
            write_gatt_char=AsyncMock(),
            disconnect=AsyncMock(),
        )
        self.coordinator = SimpleNamespace(
            client=self.client,
            controller_state=self.states,
            address="AA:BB:CC:01:02:03",
            motor_count=2,
            motor_pulse_count=1,
            motor_pulse_delay_ms=100,
            cancel_command=asyncio.Event(),
            hass=SimpleNamespace(data={}, async_create_task=lambda coro: asyncio.create_task(coro)),
            record_command_trace=MagicMock(),
            handle_controller_state_updates=self.states.update,
        )
        self.bed = DoubleSleepController(
            self.coordinator, protocol=driver, model=model, session=Session()
        )
        self.coordinator.capability_controller = self.bed

    async def connect(self):
        with patch(
            "custom_components.adjustable_bed.beds.doublesleep.asyncio.sleep", new=AsyncMock()
        ):
            await self.bed.start_notify()
        self.client.write_gatt_char.reset_mock()

    def packets(self):
        return [call.args[1] for call in self.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("driver", ("p1", "p2", "p3"))
async def test_setup_and_stale_notification_callback(driver):
    bed = Bed(driver=driver, model=11135 if driver == "p3" else 3)
    await bed.connect()
    assert len(bed.receivers) == 1
    assert bed.bed.requires_notification_channel
    assert bed_traits(BED_TYPE_DOUBLESLEEP, driver).persistent_connection
    previous = bed.receivers[0]
    await bed.bed.stop_notify()
    previous(bed.rx, bytearray.fromhex("2a00000881020102"))
    assert "sensor_version" not in bed.bed.parser.state
    assert bed.client.stop_notify.await_count == 1


async def test_cancel_during_motor_write_still_sends_fresh_stop():
    bed = Bed()
    await bed.connect()

    async def write(char, packet, **kwargs):
        if packet == bytes.fromhex("aa000001010401000000"):
            bed.coordinator.cancel_command.set()
            raise asyncio.CancelledError

    bed.client.write_gatt_char.side_effect = write
    with pytest.raises(asyncio.CancelledError):
        await bed.bed.move_head_up()
    assert bed.packets() == [
        bytes.fromhex("aa000001010401000000"),
        bytes.fromhex("aa000001010400000000"),
    ]


async def test_child_gate_prevents_press_but_never_stop():
    bed = Bed()
    await bed.connect()
    bed.bed.session.child_lock = True
    with pytest.raises(ValueError, match="child lock"):
        await bed.bed.move_head_up()
    assert bed.packets() == []
    await bed.bed.stop_all()
    assert bed.packets() == [bytes.fromhex("aa000001010400000000")]


async def test_p3_fail_fast_no_later_fragments_or_false_privacy_success():
    bed = Bed("p3", 11135, 23)
    await bed.connect()
    bed.client.write_gatt_char.side_effect = RuntimeError("native write failed")
    with pytest.raises(RuntimeError):
        await bed.bed.execute(59)
    assert len(bed.packets()) == 1
    assert not bed.bed.session.privacy
    assert bed.client.write_gatt_char.call_args.kwargs["response"] is True
    assert bed.client.disconnect.await_count == 1 and bed.bed._client is None


async def test_native_properties_and_capacity_rejected_before_write():
    bed = Bed()
    bed.tx.properties = ["write"]
    with pytest.raises(ConnectionError, match="properties"):
        await bed.bed.async_discover_capabilities()
    assert not bed.client.write_gatt_char.called
    bed.tx.properties.append("write-without-response")
    await bed.connect()
    bed.tx.max_write_without_response_size = 6
    with pytest.raises(ValueError, match="capacity"):
        await bed.bed.execute(2)
    assert bed.packets() == []


async def test_p3_report_continuation_runs_inside_owned_operation():
    bed = Bed("p3", 11135)
    await bed.connect()
    task = asyncio.create_task(bed.bed.request(Request("report", (1, 0, 2026, 11, 3))))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match="already active"):
        bed.bed.validate_request(Request("report", (0, 0, 2026, 11, 3)))
    bed.bed._receive(json_notification("q_report", {"fsize": 20}))
    for _ in range(5):
        await asyncio.sleep(0)
    assert any(b"q_report" in packet and b"allow" in packet for packet in bed.packets())
    bed.bed._receive(json_notification("q_report", {"fsize": 0}))
    await task
    assert bed.states["doublesleep_right_report_status"] == 1
    assert bed.bed._report_future is None


async def test_report_cancel_ends_session_before_another_request():
    bed = Bed("p3", 11135)
    await bed.connect()
    task = asyncio.create_task(bed.bed.request(Request("report", (0, 0, 2026, 11, 3))))
    await asyncio.sleep(0)
    bed.coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bed.client.disconnect.await_count == 1 and bed.bed._client is None
    assert bed.bed._report_future is None


async def test_parser_error_keeps_p2_timer_until_timeout_then_cleans_up():
    bed = Bed()
    await bed.connect()
    bed.bed._receive(bytes.fromhex("2a00000785070103000000"))
    assert bed.bed._report_timer is not None
    bed.bed._receive(bytes.fromhex("2a00000785000200010203"))
    assert bed.bed.parser.binary.timer_pending
    assert bed.bed._report_timer is not None
    assert "doublesleep_parser_error" in bed.states
    # Exercise actual callback without waiting five seconds.
    bed.bed._report_timer.cancel()
    bed.bed._report_timeout()
    assert bed.states["doublesleep_right_report_status"] == 2
    await bed.bed.stop_notify()
    assert bed.bed._report_timer is None


async def test_caches_retained_for_one_address_and_not_shared_with_another():
    first = Bed()
    first.bed = DoubleSleepController(first.coordinator, protocol="p2", model=10135)
    first.bed.session.cache.regular["head"] = 4
    again = DoubleSleepController(first.coordinator, protocol="p2", model=10135)
    assert again.session.cache.regular["head"] == 4
    first.coordinator.address = "AA:BB:CC:01:02:04"
    other = DoubleSleepController(first.coordinator, protocol="p2", model=10135)
    assert other.session.cache.regular["head"] == 0


@pytest.mark.parametrize("model", p.MODELS)
def test_model_capability_gates_and_all_five_motors(model):
    bed = Bed("p2", model).bed
    assert len(bed.motor_control_specs) == (0 if model in p.P3_MODELS else 5)
    assert not bed.supports_single_address_pairing and bed.position_number_specs == ()
    legacy = next((s for s in bed.controller_button_specs if s.key == "doublesleep_66"), None)
    assert bool(legacy) == (model not in p.P2_MODELS | p.P3_MODELS)


async def test_save_releases_and_massage_queries_follow_source_delay():
    bed = Bed()
    await bed.connect()
    await bed.bed.program_memory(1)
    assert bed.packets() == [bytes.fromhex("aa000001050125"), bytes.fromhex("aa000001010400000000")]
    bed.client.write_gatt_char.reset_mock()
    with patch(
        "custom_components.adjustable_bed.beds.doublesleep.asyncio.sleep", new=AsyncMock()
    ) as delay:
        await bed.bed.press(35)
    delay.assert_awaited_once_with(0.2)
    assert bed.packets() == [bytes.fromhex("aa000002010150"), bytes.fromhex("2a000002810103")]


async def test_cancellation_before_first_fragment_does_not_publish_privacy():
    bed = Bed("p3", 11135)
    await bed.connect()
    bed.coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await bed.bed.execute(59)
    assert not bed.packets() and not bed.bed.session.privacy


async def test_alarm_and_anti_snore_workflows_are_distinct_and_capability_gated():
    bed = Bed()
    await bed.connect()
    with patch("custom_components.adjustable_bed.beds.doublesleep.asyncio.sleep", new=AsyncMock()):
        await bed.bed.request(Request("alarm", (6, 30, 130, 9, 1)))
    assert bed.packets()[0][:6] == bytes.fromhex("aa0000030108")
    assert bed.packets()[1] == bytes.fromhex("aa000003020801820901061e0001")
    assert bed.packets()[2] == bytes.fromhex("2a000003810101")
    bed.client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError, match="capability"):
        bed.bed.validate_request(Request("anti_snore", (1, 2, 30, 10)))
    bed.bed.ui.slow = True
    bed.bed.ui.pwm = 30
    await bed.bed.request(Request("anti_snore", (1, 2, -1, -1)))
    assert bed.packets() == [
        bytes.fromhex("aa0000070108010202011e0a0000"),
        bytes.fromhex("aa00000701080002010100000000"),
    ]
    bed.client.write_gatt_char.reset_mock()
    await bed.bed.request(Request("anti_snore_demo", (2, 3, -1, -1)))
    assert bed.packets()[-1] == bytes.fromhex("aa0000010200")


@pytest.mark.parametrize("driver", ("p1", "p2"))
def test_only_p1_standard_presets_advertise_hold_metadata(driver):
    bed = Bed(driver, 3).bed
    hold = bed.standard_button_hold_spec("preset_flat")
    assert (hold.control if hold else None) == ("doublesleep_26" if driver == "p1" else None)


async def test_legacy_listener_is_ready_before_write_and_quiet_completion_confirms():
    bed = Bed("p1", 3)
    await bed.connect()

    async def write(char, packet, **kwargs):
        if packet == bytes.fromhex("01b102"):
            bed.bed._receive(bytes([166, 48, 0, 75, 14, 6, 1, 80, 15, 3, 2, 126, 10, 3, 6, 30]))

    bed.client.write_gatt_char.side_effect = write
    await bed.bed.execute(66)
    assert len(bed.bed.parser.legacy) == 1
    assert bed.bed._legacy_timer is not None
    bed.bed._legacy_timer.cancel()
    with patch.object(bed.bed, "_followup") as followup:
        bed.bed._finish_legacy()
    followup.assert_called_once_with(64)
    assert bed.states["doublesleep_legacy_report"]["left"][0]["heart"] == 75
    assert not bed.bed._legacy_active and bed.bed._legacy_timer is None
    await bed.bed.stop_notify()


async def test_fragment_writer_does_not_borrow_a_replacement_client():
    bed = Bed("p3", 11135, 23)
    await bed.connect()

    async def replace_client(*args, **kwargs):
        bed.coordinator.client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())

    bed.client.write_gatt_char.side_effect = replace_client
    with pytest.raises(ConnectionError, match="ended session"):
        await bed.bed.execute(59)
    assert len(bed.packets()) == 1
    assert not bed.coordinator.client.write_gatt_char.called
    assert not bed.bed.session.privacy


async def test_numeric_cache_and_view_have_distinct_reload_lifetimes():
    bed = Bed()
    bed.bed = DoubleSleepController(bed.coordinator, protocol="p2", model=10135)
    bed.bed.session.cache.regular["head"] = 4
    bed.bed.ui.sonic_ui = True
    bed.bed._publish()
    reconnect = DoubleSleepController(bed.coordinator, protocol="p2", model=10135)
    assert reconnect.ui.sonic_ui and reconnect.session.cache.regular["head"] == 4
    # A fresh coordinator is a new UI owner, while process numeric statics survive.
    fresh = SimpleNamespace(**vars(bed.coordinator))
    fresh.controller_state = {}
    reloaded = DoubleSleepController(fresh, protocol="p2", model=10135)
    assert not reloaded.ui.sonic_ui and reloaded.session.cache.regular["head"] == 4


def test_child_lock_restore_and_local_change_do_not_republish_stale_sensor_state():
    bed = Bed()
    bed.bed.restore_persisted_app_state({"child_lock": True})
    assert bed.states["doublesleep_child_lock"] == "on"
    bed.states["doublesleep_left_heart_rate"] = 77
    bed.bed.parser.state["left_heart_rate"] = 45
    spec = bed.bed.controller_select_specs[0]
    assert spec.local_select_fn is not None
    spec.local_select_fn("off")
    assert bed.states["doublesleep_child_lock"] == "off"
    assert bed.states["doublesleep_left_heart_rate"] == 77
    assert not bed.client.write_gatt_char.called


async def test_report_busy_is_nonterminal_and_unrelated_samples_are_not_progress():
    bed = Bed("p3", 11135)
    await bed.connect()
    task = asyncio.create_task(bed.bed.request(Request("report", (0, 0, 2026, 11, 3))))
    await asyncio.sleep(0)
    bed.bed._report(Report("history", 0, 2, {}))
    assert bed.bed._report_future is not None and not bed.bed._report_future.done()
    bed.bed.parser.json_reader.buffer.extend(b"retained old report")
    bed.bed._receive(json_notification("q_sens", {"L": [1], "R": [2]}))
    assert not bed.bed._report_wake.is_set()
    bed.bed._report(Report("history", 0, 0, {"date": "2026-11-03"}))
    await task
    assert bed.states["doublesleep_left_report"]["requested_date"] == "2026-11-03"
    assert not bed.client.disconnect.called


async def test_report_silence_closes_session_without_a_real_timeout_wait():
    bed = Bed("p3", 11135)
    await bed.connect()
    with (
        patch(
            "custom_components.adjustable_bed.beds.doublesleep.asyncio.wait",
            new=AsyncMock(return_value=(set(), set())),
        ),
        pytest.raises(TimeoutError, match="no progress"),
    ):
        await bed.bed.request(Request("report", (0, 0, 2026, 11, 3)))
    assert bed.client.disconnect.await_count == 1 and bed.bed._report_future is None


async def test_malformed_month_does_not_publish_success_over_previous_report():
    bed = Bed()
    await bed.connect()
    bed.bed._report(Report("history", 0, 1, {}))
    previous = bed.states["doublesleep_left_report"]
    with pytest.raises(ValueError):
        bed.bed._report(Report("history_month", 0, 0, "[1]"))
    assert bed.states["doublesleep_left_report_status"] == 1
    assert bed.states["doublesleep_left_report"] == previous


@pytest.mark.parametrize("driver,model", [("p2", 10135), ("p3", 11135)])
async def test_sensitivity_change_retains_unselected_reported_values(driver, model):
    bed = Bed(driver, model)
    await bed.connect()
    bed.bed.parser.state.update(use_side=2, left_sensitivity=3, right_sensitivity=9)
    with patch(
        "custom_components.adjustable_bed.beds.doublesleep.asyncio.sleep", new=AsyncMock()
    ) as delay:
        await bed.bed.request(Request("sensitivities", (-1, 1, -1)))
    delay.assert_awaited_once_with(0.2)
    if driver == "p2":
        assert bed.packets()[0] == p.binary_command("p2", 67, (2, 1, 9), p.Cache(), NOW)
    else:
        assert b'"L":[1],"R":[9]' in bed.packets()[0]
        with pytest.raises(ValueError, match="no reachable side-setting"):
            bed.bed.validate_request(Request("sensitivities", (1, 1, 1)))


async def test_rolling_history_survives_connection_recreation_only():
    bed = Bed()
    bed.bed.parser.state["left_history"] = [1, 0, 1, 0, 1, 0, 1, 0]
    bed.bed._publish()
    await bed.bed.stop_notify()
    reconnect = DoubleSleepController(
        bed.coordinator, protocol="p2", model=10135, session=bed.bed.session
    )
    assert reconnect.parser.state["left_history"] == [1, 0, 1, 0, 1, 0, 1, 0]
    fresh = SimpleNamespace(**vars(bed.coordinator))
    fresh.controller_state = {}
    reloaded = DoubleSleepController(fresh, protocol="p2", model=10135, session=bed.bed.session)
    assert reloaded.parser.state["left_history"] == [0] * 8


async def test_unexpected_disconnect_retires_old_timers_tasks_and_report_future():
    bed = Bed("p2", 3)
    await bed.connect()
    old = bed.bed
    old._receive(bytes.fromhex("2a00000785070103000000"))
    await old.execute(66)
    timers = [old._report_timer, old._legacy_timer]
    callbacks = [(timer._callback, timer._args) for timer in timers if timer is not None]
    assert len(callbacks) == 2
    old._report_future = asyncio.get_running_loop().create_future()
    async def queued(*args, **kwargs):
        await asyncio.Event().wait()

    bed.coordinator.async_execute_controller_command = AsyncMock(side_effect=queued)
    old._followup(64)
    pending = tuple(old._followups)
    await asyncio.sleep(0)
    old.on_disconnect()
    assert all(timer.cancelled() for timer in timers if timer is not None)
    assert old._report_future.done()
    assert isinstance(old._report_future.exception(), ConnectionError)
    await asyncio.gather(*pending, return_exceptions=True)
    assert all(task.cancelled() for task in pending)

    replacement = bed.bed = DoubleSleepController(
        bed.coordinator, protocol="p2", model=3, session=old.session
    )
    await bed.connect()
    replacement._receive(bytes.fromhex("2a00000784070103000000"))
    before = dict(bed.states)
    with patch.object(old, "_followup") as followup:
        for callback, args in callbacks:
            callback(*args)
    assert bed.states == before
    followup.assert_not_called()
    await replacement.stop_notify()


async def test_overlapping_legacy_download_waits_for_completion_and_confirmation():
    bed = Bed("p1", 3)
    await bed.connect()
    await bed.bed.execute(66)
    first = bed.bed._legacy_timer
    assert first is not None
    callback, args = first._callback, first._args
    with pytest.raises(ValueError, match="already active"):
        await bed.bed.execute(66)
    assert bed.bed._legacy_timer is first and bed.bed._legacy_active
    assert bed.packets() == [bytes.fromhex("01b102")]

    async def execute(command, **kwargs):
        await command(bed.bed)

    bed.coordinator.async_execute_controller_command = execute
    first.cancel()
    bed.bed._finish_legacy()
    with pytest.raises(ValueError, match="already active"):
        await bed.bed.execute(66)
    await asyncio.gather(*bed.bed._followups)
    assert bed.packets()[-1] == bytes.fromhex("01b301")
    await bed.bed.execute(66)
    callback(*args)  # A queued callback from the first download cannot finish this one.
    assert bed.bed._legacy_active
    assert bed.packets().count(bytes.fromhex("01b102")) == 2
    await bed.bed.stop_notify()


@pytest.mark.parametrize(
    "channel,data",
    [("history", {"sleepQualityScore": True}), ("history_month", '[{"sleepQualityScore": "9"}]')],
)
async def test_invalid_report_scalar_never_publishes_success(channel, data):
    bed = Bed()
    await bed.connect()
    bed.bed._report(Report("history", 0, 1, {}))
    before = dict(bed.states)
    with pytest.raises(ValueError, match="must be an integer"):
        bed.bed._report(Report(channel, 0, 0, data))
    assert bed.states == before
