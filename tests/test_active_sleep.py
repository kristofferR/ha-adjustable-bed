"""Frozen Active Sleep frames, live admission and release on the real GATT writer."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from functools import reduce
from operator import xor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.active_sleep.controller import (
    HEART,
    RESPIRATION,
    WARNING,
    ActiveSleepController,
)
from custom_components.adjustable_bed.codec import active_sleep as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed
from tests.active_sleep_vectors import VECTORS
from tests.error_helpers import raises_key


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_all_32_accepted_literals(row):
    assert getattr(codec, row["builder"])(**row["inputs"]).hex() == row["expected_bytes"]


def test_existing_paramount_codec_does_not_reproduce_active_sleep():
    from custom_components.adjustable_bed.codec import paramount

    assert paramount.control(2).hex() != "b405027f7f7f7fb3"
    assert paramount.frame(0x81).hex() != "810081"


def test_frozen_signed_positions_and_mattress_fields():
    position = codec.Position.parse(bytes.fromhex("0a141efd15000100"))
    assert position.posture == (10, 20, 30, -3)
    assert position.locks == 21 and position.fast and position.fail == 0
    spec = codec.Spec.parse(bytes.fromhex("31214315670829ab0c"))
    assert spec == codec.Spec(True, True, True, 5, 4)
    mattress = codec.Mattress.parse(bytes.fromhex("214365d3780055000000000000000002"))
    assert mattress.zones == (1, 2, 3, 4, 5, 6)
    assert mattress.sound == mattress.ventilation == 1 and mattress.fukatto
    assert mattress.remaining == 120 and mattress.busy == 85 and mattress.fail == 2


def test_split_boundaries_and_rolling_xor_assembly():
    assert codec.fragments(bytes(range(45)), True) == (
        bytes(range(20)),
        b"\x8f" + bytes(range(20, 39)),
        b"\x8f" + bytes(range(39, 45)),
    )
    raw = bytes((0x41, 24)) + bytes(range(24))
    receiver = codec.Receiver()
    assert receiver.feed(raw[:20]) is None
    reply = receiver.feed(b"\x8f" + raw[20:] + bytes((reduce(xor, raw, 0),)))
    assert reply and reply.opcode == 0x41 and reply.payload == raw[2:18]
    assert receiver.feed(b"\x8f\x00") is None
    assert receiver.feed(b"\x32\x00" + bytes(10)) is None
    assert receiver.feed(b"\x34\x06\x02") is None


@pytest.mark.parametrize(
    ("raw", "resp", "heart"),
    [
        (0, None, None),
        (1, 0, 1),
        (75, 15, 75),
        (251, 50, 251),
        (252, None, None),
        (255, None, None),
    ],
)
def test_corrected_realtime_conversion(raw, resp, heart):
    assert codec.sensor_value(raw, respiration=True) == resp
    assert codec.sensor_value(raw) == heart


class Bed:
    def __init__(self):
        self.coordinator = MagicMock()
        self.coordinator.entry = SimpleNamespace(
            data={"active_sleep_auth_id": "0123456789ABCDEF"}, options={}
        )
        self.coordinator.cancel_command = asyncio.Event()
        self.coordinator.controller_state = ControllerState()
        self.coordinator.handle_controller_state_updates.side_effect = lambda *u: (
            self.coordinator.controller_state.update((x.key, x.value) for x in u)
        )
        self.char = SimpleNamespace(uuid=codec.CHAR_UUID, handle=17, properties=["write", "notify"])
        self.client = self.coordinator.client
        self.client.is_connected = True
        self.client.services.get_service.return_value.get_characteristic.return_value = self.char
        self.client.services.get_characteristic.return_value = self.char
        self.controller = ActiveSleepController(self.coordinator, "0123456789ABCDEF")
        self.coordinator.controller = self.controller
        self.controller.profile = replace(
            self.controller.profile,
            interval_ms=0,
            manual_delay_ms=0,
            preset_delay_ms=0,
            response_timeout_ms=15,
            query_timeout_s=0.02,
        )
        self.writes = []
        self.drop = None
        self.position = codec.Position((10, 5, 40, 0), 0, False, 0)
        self.mattress = codec.Mattress((1, 2, 3, 4, 5, 6), 1, 0, False, 3, 0, 0, 0)
        self.model = 3
        self.auth = 0
        self.callback = None
        self.swap = False
        self.client.write_gatt_char = AsyncMock(side_effect=self.write)
        self.client.start_notify = AsyncMock(side_effect=self.subscribe)
        self.client.stop_notify = AsyncMock()
        self.session = SimpleNamespace(
            async_start_notify=self.controller.start_notify, persist_capability_snapshot=MagicMock()
        )

    async def subscribe(self, _char, callback):
        self.callback = callback

    def emit(self, raw):
        assert self.callback is not None
        self.callback(self.char, bytearray(raw))

    async def write(self, _char, raw, **kwargs):
        self.writes.append(raw)
        if self.swap:
            self.controller.on_disconnect()
            return
        if raw[0] == self.drop:
            return
        reply = raw[0] & 127
        payload = b""
        if raw[0] == 0x81:
            payload = b"12345678"
        elif raw[0] == 0x82:
            payload = bytes((0x31, 0, 0, 0x10 | self.model, 0, 0, 0x21, 0, 0))
        elif raw[0] == 0x84:
            payload = bytes((self.auth,))
        elif raw[0] == 0xB1:
            payload = bytes((0, 70, 0, 30, 20, 50, 0, 10, 31))
        elif raw[0] == 0xB3:
            self.position = replace(self.position, locks=raw[2], fast=raw[4] == 1)
        elif raw[0] == 0xB2:
            payload = bytes(
                (
                    *(v & 255 for v in self.position.posture),
                    self.position.locks,
                    0,
                    int(self.position.fast),
                    self.position.fail,
                )
            )
        elif raw[0] == 0xB4:
            payload = bytes((raw[2], *(v & 255 for v in self.position.posture), 0))
        elif raw[0] == 0xC1:
            payload = self.mattress.encode()[2:6] + bytes(12)
        elif raw[0] == 0xC2:
            self.mattress = codec.Mattress.parse(raw[2:6] + bytes(12))
        elif raw[0] == 0xA2:
            payload = bytes((1, *range(8), 0, 75, 75))
        self.emit(bytes((reply, len(payload))) + payload)

    async def connect(self):
        await self.controller.async_on_connect(self.session)
        self.writes.clear()
        return self.controller


@pytest.fixture
def bed():
    return Bed()


async def test_startup_requires_existing_id_then_subscribes_and_authenticates(bed):
    bed.controller._token = ""
    with raises_key("active_sleep_auth_id_required", ServiceValidationError):
        await bed.connect()
    assert not bed.writes
    bed.controller._token = "0123456789ABCDEF"
    await bed.controller.async_on_connect(bed.session)
    assert [raw[0] for raw in bed.writes] == [0x81, 0x82, 0x84, 0xB1, 0xB2, 0xC1]
    assert bed.controller._authenticated
    assert bed.controller._format_command_trace_payload(bed.writes[2]) == {
        "redacted": True,
        "length": 19,
    }
    bed.session.persist_capability_snapshot.assert_called_once()


async def test_rejected_auth_never_queries_controls(bed):
    bed.auth = 1
    with raises_key("active_sleep_auth_rejected", ServiceValidationError):
        await bed.connect()
    assert not bed.controller._authenticated
    assert [raw[0] for raw in bed.writes] == [0x81, 0x82, 0x84]


async def test_movement_uses_real_writer_and_same_link_stop(bed):
    ctrl = await bed.connect()
    await ctrl.hold_control("head_up", 2)
    assert bed.writes[0] == codec.arrow(2) and bed.writes[-1] == codec.arrow(0)
    assert not ctrl._poisoned
    await ctrl.hold_control("legs_up", 2)
    assert bed.writes[-1] == codec.arrow(0)
    assert all(
        call.args[0] is bed.char and call.kwargs["response"]
        for call in bed.client.write_gatt_char.await_args_list
    )


async def test_no_reply_never_replays_and_cancel_cannot_suppress_release(bed):
    ctrl = await bed.connect()
    bed.drop = 0xB4
    with pytest.raises(TimeoutError):
        await ctrl.hold_control("head_up", 100)
    assert bed.writes == [codec.arrow(2), codec.arrow(0)]
    with raises_key("active_sleep_reconnect_required", ServiceValidationError):
        await ctrl.hold_control("legs_up", 100)


async def test_stop_during_pending_reply_releases_and_poisons_ambiguous_session(bed):
    ctrl = await bed.connect()
    bed.drop = 0xB4
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    while not bed.writes:
        await asyncio.sleep(0)
    bed.coordinator.cancel_command.set()
    await task
    assert bed.writes == [codec.arrow(2), codec.arrow(0)]


async def test_replacement_link_never_receives_old_cleanup(bed):
    ctrl = await bed.connect()
    bed.swap = True
    with pytest.raises(ConnectionError):
        await ctrl.hold_control("head_up", 100)
    assert bed.writes == [codec.arrow(2)]


async def test_gatt_replacement_or_changed_token_rejected_before_write(bed):
    ctrl = await bed.connect()
    bed.client.services.get_characteristic.return_value = object()
    with pytest.raises(ConnectionError):
        await ctrl.hold_control("head_up", 1)
    assert not bed.writes
    bed.client.services.get_characteristic.return_value = bed.char
    ctrl._token = "FEDCBA9876543210"
    with pytest.raises(ConnectionError):
        await ctrl.hold_control("head_up", 1)
    assert not bed.writes


async def test_height_threshold_counterexample_and_explicit_ack(bed):
    bed.position = replace(bed.position, posture=(10, 5, 28, 0))
    ctrl = await bed.connect()
    with raises_key("active_sleep_height_clearance", ServiceValidationError):
        await ctrl.hold_control("height_down", 1)
    assert not bed.writes and bed.coordinator.controller_state[WARNING] is True
    await ctrl.press("acknowledge")
    await ctrl.hold_control("height_down", 1)
    assert bed.writes[0] == codec.arrow(7)
    ctrl.on_disconnect()
    assert not ctrl._acknowledged


async def test_later_warning_requires_two_seconds_without_position_change(bed):
    ctrl = await bed.connect()
    ctrl._position = replace(bed.position, posture=(10, 5, 28, 0))
    ctrl._last_change = 0
    with raises_key("active_sleep_height_clearance", ServiceValidationError):
        ctrl._height_gate("height_down", first=False, start_high=True)
    assert not bed.writes


async def test_settings_and_mattress_read_modify_readback_preserve_other_fields(bed):
    ctrl = await bed.connect()
    await ctrl.change_setting(axis="head", enabled=True)
    assert bed.writes == [codec.frame(0xB2), codec.settings(head=True), codec.frame(0xB2)]
    bed.writes.clear()
    await ctrl.change_mattress(ventilation=True)
    assert [b[0] for b in bed.writes] == [0xC1, 0xC2, 0xC1]
    assert bed.mattress.zones == (1, 2, 3, 4, 5, 6) and bed.mattress.sound == 1
    assert bed.mattress.ventilation and not bed.mattress.fukatto
    bed.writes.clear()
    await ctrl.press("mattress_template_1")
    assert bed.mattress.zones == (5, 5, 5, 1, 1, 1) and not bed.mattress.ventilation
    assert codec.arrow(0) not in bed.writes


async def test_realtime_sequence_suppression_and_invalid_clear(bed):
    ctrl = await bed.connect()
    await ctrl.read_positions()
    assert bed.coordinator.controller_state[HEART] == 75
    assert bed.coordinator.controller_state[RESPIRATION] == 15
    future = asyncio.get_running_loop().create_future()
    ctrl._pending = (0x22, future)
    bed.emit(bytes((0x22, 12, 2, *range(8), 0, 252, 255)))
    assert bed.coordinator.controller_state[HEART] is None
    assert bed.coordinator.controller_state[RESPIRATION] is None
    ctrl._pending = None
    future.result()
    old_callback = bed.callback
    ctrl.on_disconnect()
    old_callback(bed.char, bytearray((0x22, 12, 3, *range(8), 0, 75, 75)))
    assert bed.coordinator.controller_state[HEART] is None


async def test_live_model_presence_locks_and_ranges_gate_native_entities(bed):
    ctrl = await bed.connect()
    assert {s.key for s in ctrl.motor_control_specs} == {"head", "legs", "height", "tilt"}
    assert {s.position_key for s in ctrl.position_number_specs} == {"head", "legs"}
    assert not ctrl.supports_memory_programming and ctrl.memory_slot_count == 0
    assert not ctrl.controller_number_specs  # No guessed user pressure range.
    bed.position = replace(bed.position, locks=1)
    await ctrl.read_positions()
    with raises_key("active_sleep_motor_locked", ServiceValidationError):
        ctrl.validate_hold_control("head_up", 1)
    ctrl._spec = replace(ctrl._spec, model=0)
    assert not ctrl.motor_control_specs


@pytest.mark.parametrize(
    ("name", "hint"), [("Active123", True), ("active123", False), ("XActive", False)]
)
def test_exact_prefix_is_an_app_hint_not_a_product(name, hint):
    info = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF",
        name=name,
        service_uuids=[],
        manufacturer_data={},
        service_data={},
        advertisement=SimpleNamespace(local_name=name),
    )
    result = detect_bed_type_detailed(info)
    assert ("app_hint:active_sleep" in result.signals) is hint
    assert detect_bed_type(info) is None


async def test_local_template_save_and_reset_never_program_bed_memory(bed):
    ctrl = await bed.connect()
    await ctrl.press("save_bed_1")
    assert bed.writes == [codec.frame(0xB2)]
    assert ctrl._bed_templates[0] == bed.position.posture
    bed.writes.clear()
    await ctrl.press("reset_bed_1")
    assert not bed.writes
    assert ctrl._bed_templates[0] == (70, 5, 30, 255)
    restored = ActiveSleepController(bed.coordinator)
    restored.restore_persisted_app_state(ctrl.persisted_app_state)
    assert restored.persisted_app_state == ctrl.persisted_app_state


async def test_setup_side_ownership_secret_redaction_and_real_factory():
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.const import CONF_DISABLE_ANGLE_SENSING
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.redaction import redact_data
    from custom_components.adjustable_bed.setup_questions import GENERIC_FIELDS, setup_profile
    from tests.test_controller_contract import _FactoryCoordinator

    profile = setup_profile("active_sleep", None)
    assert profile.hidden() == GENERIC_FIELDS - {CONF_DISABLE_ANGLE_SENSING}
    assert "active_sleep_auth_id" in per_side_profile("active_sleep", None).keys
    assert redact_data({"active_sleep_auth_id": "secret"})["active_sleep_auth_id"] != "secret"
    coordinator = _FactoryCoordinator()
    coordinator.entry.data["active_sleep_auth_id"] = "0123456789ABCDEF"
    controller = await create_controller(coordinator, "active_sleep", "auto", None)
    assert isinstance(controller, ActiveSleepController) and controller._token == "0123456789ABCDEF"


async def test_native_setup_entities_and_services(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.runtime_data import entry_runtime
    from scripts.wire_snapshot import FakeServices

    simulator = Bed()
    mock_bleak_client.services = FakeServices(
        {
            "services": {codec.SERVICE_UUID: [codec.CHAR_UUID]},
            "properties": {codec.CHAR_UUID: ["write", "notify"]},
        }
    )
    simulator.char = mock_bleak_client.services.get_characteristic(codec.CHAR_UUID)
    mock_bleak_client.start_notify.side_effect = simulator.subscribe
    mock_bleak_client.write_gatt_char.side_effect = simulator.write
    address = "AA:BB:CC:DD:15:96"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Active Sleep",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Active Sleep",
            const.CONF_BED_TYPE: "active_sleep",
            const.CONF_DISABLE_ANGLE_SENSING: False,
            "active_sleep_auth_id": "0123456789ABCDEF",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        coordinator = entry_runtime(hass, entry.entry_id)
        controller = coordinator.controller
        assert isinstance(controller, ActiveSleepController)
        assert controller._authenticated
        assert entry.data["capabilities"]["active_sleep"]["spec"]
        registry = er.async_get(hass)
        speed = registry.async_get_entity_id(
            "select", const.DOMAIN, f"{address}_controller_select_active_sleep_speed"
        )
        assert speed
        await hass.services.async_call(
            "select", "select_option", {"entity_id": speed, "option": "fast"}, blocking=True
        )
        assert simulator.position.fast
        assert hass.states.get(speed).state == "fast"
        assert not any(x[0] in (0x91, 0x92, 0x93, 0x94, 0xF1, 0xF2, 0xF3) for x in simulator.writes)
    finally:
        mock_bleak_client.start_notify.side_effect = None
        mock_bleak_client.write_gatt_char.side_effect = None
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("control", "locks"), (("head_up", 1), ("combination_up", 8)))
async def test_generic_hold_preflights_every_target_before_any_movement(hass, bed, control, locks):
    from unittest.mock import patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import target

    ctrl = await bed.connect()
    bed.position = replace(bed.position, locks=locks)
    await ctrl.read_positions()
    first, first_controller = target(held_control_options=(control,))
    second, second_controller = target(
        "active_sleep",
        held_control_options=ctrl.held_control_options,
        validate_hold_control=ctrl.validate_hold_control,
    )
    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="locked"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": ["a", "b"], "control": control, "duration": 1},
            blocking=True,
        )
    first_controller.hold_control.assert_not_awaited()
    second_controller.hold_control.assert_not_awaited()


async def test_direct_target_reuses_stream_and_validates_live_range(bed):
    ctrl = await bed.connect()
    ctrl._hold_movement = AsyncMock()
    await ctrl.set_motor_position("head", 25)
    ctrl._hold_movement.assert_awaited_once_with("target", 30000, (25, 255, 255, 255))
    for value, key in ((71, "active_sleep_target_unavailable"), (-1, "active_sleep_target_unavailable"), (2.5, "whole_number_required")):
        with raises_key(key, ServiceValidationError):
            ctrl.validate_position_request("head", value)
    assert not bed.writes


@pytest.mark.parametrize(("motor", "lock"), [("head", 4), ("legs", 1)])
async def test_single_axis_target_ignores_other_motor_locks(bed, motor, lock):
    ctrl = await bed.connect()
    ctrl._position = replace(ctrl._position, locks=lock)
    ctrl._hold_movement = AsyncMock()
    await ctrl.set_motor_position(motor, 25)
    target = (25, 255, 255, 255) if motor == "head" else (255, 25, 255, 255)
    ctrl._hold_movement.assert_awaited_once_with("target", 30000, target)
    ctrl._position = replace(ctrl._position, locks=codec.LOCKS[motor])
    with raises_key("active_sleep_target_unavailable", ServiceValidationError):
        ctrl.validate_position_request(motor, 25)


async def test_position_service_plan_rejects_live_lock_before_any_dispatch(bed):
    from custom_components.adjustable_bed import services

    ctrl = await bed.connect()
    bed.position = replace(bed.position, locks=1)
    await ctrl.read_positions()
    bed.coordinator.entry.data["bed_type"] = "active_sleep"
    bed.coordinator.disable_angle_sensing = False
    with raises_key("active_sleep_target_unavailable", ServiceValidationError):
        services._position_config(bed.coordinator, ctrl, "head", 20)
    assert bed.writes == [codec.frame(0xB2), codec.frame(0xC1), codec.frame(0xA2)]


async def test_later_height_gate_waits_for_no_change_window_then_sends_stop(bed):
    from unittest.mock import patch

    from scripts.wire_snapshot import FakeClock, virtual_time

    ctrl = await bed.connect()
    ctrl.profile = replace(ctrl.profile, interval_ms=200, manual_delay_ms=50)
    bed.position = replace(bed.position, posture=(10, 5, 28, 0))
    clock = FakeClock()
    times = []
    original = bed.write

    async def write(char, raw, **kwargs):
        times.append((clock.now, raw))
        await original(char, raw, **kwargs)

    bed.client.write_gatt_char.side_effect = write
    with (
        virtual_time(clock),
        patch(
            "custom_components.adjustable_bed.beds.active_sleep.controller.monotonic",
            lambda: clock.now,
        ),
        raises_key("active_sleep_height_clearance", ServiceValidationError),
    ):
        await ctrl.hold_control("height_down", 4000)
    assert len([raw for _, raw in times if raw == codec.arrow(7)]) >= 10
    assert times[-1][1] == codec.arrow(0) and times[-1][0] >= 2.2


async def test_explicit_task_cancel_keeps_same_link_cleanup(bed):
    ctrl = await bed.connect()
    bed.drop = 0xB4
    task = asyncio.create_task(ctrl.hold_control("head_up", 1000))
    while not bed.writes:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert bed.writes == [codec.arrow(2), codec.arrow(0)]


async def test_opt_in_monitor_uses_the_audited_100ms_query_lane(bed):
    from time import monotonic

    ctrl = await bed.connect()
    ctrl.set_monitor(True)
    ctrl._last_poll = monotonic()
    await ctrl.async_refresh_diagnostics()
    assert ctrl.diagnostic_poll_interval == 0.1
    assert bed.writes == [codec.frame(0xA2)]


async def test_combination_lock_changed_at_final_dispatch_sends_no_motion(bed):
    ctrl = await bed.connect()
    await ctrl.ble_lock.acquire()
    moving = asyncio.create_task(ctrl.hold_control("combination_up", 100))
    try:
        for _ in range(20):
            if ctrl._pending is not None:
                break
            await asyncio.sleep(0)
        assert ctrl._pending is not None
        ctrl._position = replace(bed.position, locks=8)
    finally:
        ctrl.ble_lock.release()
    with raises_key("active_sleep_motor_locked", ServiceValidationError):
        await moving
    assert not bed.writes
