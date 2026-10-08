"""Session sequencing, transport identity, state and cancellation on mocked BLE."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed import sleeptracker_protocol as p
from custom_components.adjustable_bed.beds.sleeptracker import SleeptrackerController


class Processor:
    def __init__(self, *, model="ergo_prosmart", restricted=False, mtu=23):
        self.receivers = {}
        self.outgoing = {uuid: p.Reassembler() for uuid in (p.AUTH_UUID, p.CONTROL_UUID)}
        self.requests = []
        self.frames = []
        self.hold = asyncio.Event()
        self.block_movement = False
        self.char = {
            uuid: SimpleNamespace(
                uuid=uuid,
                handle=index,
                properties=["read", "write", "notify", "write-without-response"],
                max_write_without_response_size=mtu - 3,
            )
            for index, uuid in enumerate(
                (p.HELLO_UUID, p.AUTH_UUID, p.CONTROL_UUID, p.FIRMWARE_UUID)
            )
        }
        self.client = SimpleNamespace(
            is_connected=True,
            mtu_size=mtu,
            services=SimpleNamespace(
                get_service=lambda uuid: (
                    SimpleNamespace(characteristics=list(self.char.values()))
                    if uuid == p.SERVICE_UUID
                    else None
                )
            ),
            read_gatt_char=AsyncMock(side_effect=self.read),
            write_gatt_char=AsyncMock(side_effect=self.write),
            start_notify=AsyncMock(side_effect=self.subscribe),
            stop_notify=AsyncMock(),
            disconnect=AsyncMock(side_effect=self.disconnect),
        )
        self.states = {}

        async def executor(fn, *args):
            return fn(*args)

        def create_task(coro, *, eager_start=True):
            return asyncio.Task(coro, eager_start=eager_start)

        self.coordinator = SimpleNamespace(
            client=self.client,
            address="AA:BB:CC:01:02:03",
            motor_count=3,
            motor_pulse_count=1,
            motor_pulse_delay_ms=10,
            cancel_command=asyncio.Event(),
            hass=SimpleNamespace(async_create_task=create_task, async_add_executor_job=executor),
            record_command_trace=MagicMock(),
            handle_controller_state_updates=lambda updates: self.states.update(updates),
        )
        self.bed = SleeptrackerController(
            self.coordinator,
            model=model,
            unit_number=0 if restricted else 2,
            snapshot_side=1,
            restricted=restricted,
        )

    def subscribe(self, char, callback):
        self.receivers[char.uuid] = callback

    async def read(self, char):
        if char.uuid == p.FIRMWARE_UUID:
            return b"1.5.4"
        if char.uuid == p.HELLO_UUID:
            value = {
                "authCode": "synthetic-secret",
                "macAddress": "AA:BB:CC:01:02:03",
                "Serial": "private",
                "FSPVersion": "6.1.56",
                "motorMeta": {"capabilities": [{"controllerModel": "BEST"}]},
                "leftSensor": {
                    "motors_bitfield": 7,
                    "massagers_bitfield": 3,
                    "sample_range": 42,
                    "status": "Connected",
                },
            }
            return p.frames(json.dumps(value).encode(), 500)[0]
        raise AssertionError("Unexpected continuation read")

    async def write(self, char, data, response):
        self.frames.append((char.uuid, bytes(data), response))
        if (payload := self.outgoing[char.uuid].feed(bytes(data))) is None:
            return
        value = json.loads(payload)
        self.requests.append((char.uuid, value))
        if self.block_movement and value.get("request", {}).get("movement", {}).get("action") in (
            "up",
            "down",
        ):
            self.hold.set()
            return
        reply = (
            {"details": {"token": "session-secret", "validUntil": 123}}
            if char.uuid == p.AUTH_UUID
            else {
                "details": {
                    "body": {
                        "snapshots": [
                            {
                                "massagePattern": 1,
                                "head": {"massage": {"strength": 4}},
                                "safetyLightOn": True,
                                "fan": {"leftLevel": 2, "leftIsHeating": True},
                            }
                        ],
                        "invariants": [{"type": "controller", "model": "BEST", "version": 80}],
                    }
                }
            }
        )
        for frame in p.frames(json.dumps(reply).encode(), 500):
            self.receivers[char.uuid](char, bytearray(frame))

    def disconnect(self):
        self.client.is_connected = False
        self.bed.on_disconnect()


def reply_with(target: Processor, value, channel=p.CONTROL_UUID) -> None:
    encoded = value if isinstance(value, bytes) else json.dumps(value).encode()

    async def write(char, data, response):
        if char.uuid != channel:
            return await target.write(char, data, response)
        target.frames.append((char.uuid, bytes(data), response))
        if (payload := target.outgoing[char.uuid].feed(bytes(data))) is not None:
            target.requests.append((char.uuid, json.loads(payload)))
            for frame in p.frames(encoded, 500):
                target.receivers[char.uuid](char, bytearray(frame))

    target.client.write_gatt_char.side_effect = write


@pytest.mark.parametrize("phase", ["hello", "auth", "status"])
async def test_empty_startup_reply_closes_session(phase) -> None:
    target = Processor()
    if phase == "hello":
        target.client.read_gatt_char.return_value = p.frames(b"{}", 500)[0]
        target.client.read_gatt_char.side_effect = None
    else:
        reply_with(target, {}, p.AUTH_UUID if phase == "auth" else p.CONTROL_UUID)
    with pytest.raises(ValueError, match="nonempty"):
        await target.bed.start_notify()
    assert not target.client.is_connected
    assert not target.bed.protocol_diagnostics["session_ready"]
    assert not target.bed.protocol_diagnostics["authenticated"]


@pytest.mark.parametrize("action", ["climate", "movement", "release"])
async def test_empty_control_reply_releases_without_acknowledged_state(action) -> None:
    target = Processor(model="activebreeze_large")
    await target.bed.start_notify()
    reply_with(target, {})
    with pytest.raises(ValueError, match="nonempty"):
        if action == "climate":
            await target.bed.async_execute_sleeptracker_request(
                p.Request("climate", fan_side="left", heating=True, level=3, constant=False)
            )
        elif action == "movement":
            await target.bed.move_back_up()
        else:
            await target.bed._release()
    assert not target.client.is_connected
    assert not target.bed.protocol_diagnostics["session_ready"]
    assert target.states.get("sleeptracker_left_commanded_timer_seconds") is None
    assert target.states.get("sleeptracker_left_curve") is None
    final = target.requests[-1][1]["request"]
    assert "stop" in final or final.get("movement", {}).get("action") == "stop"


@pytest.mark.parametrize("reply", [{"details": {}}, {"body": {"snapshots": []}}])
async def test_nonempty_partial_reply_remains_valid(reply) -> None:
    target = Processor(model="activebreeze_large")
    await target.bed.start_notify()
    reply_with(target, reply)
    await target.bed.async_execute_sleeptracker_request(
        p.Request("climate", fan_side="left", heating=True, level=3)
    )
    assert target.states["sleeptracker_left_commanded_timer_seconds"] == 3600
    assert target.states["sleeptracker_left_level"] == 2
    assert target.bed.protocol_diagnostics["session_ready"]
    await target.bed.stop_notify()


async def test_consecutive_fragmented_replies_with_eager_ha_task_creation() -> None:
    target = Processor()
    await target.bed.start_notify()
    remaining = []

    async def read(char):
        assert char.uuid == p.CONTROL_UUID
        return remaining.pop(0)

    async def write(char, data, response):
        if target.outgoing[char.uuid].feed(bytes(data)) is not None:
            parts = p.frames(b'{"details":{"body":{"snapshots":[]}}}', 15)
            remaining.extend(parts[1:])
            target.receivers[char.uuid](char, bytearray(parts[0]))

    target.client.read_gatt_char.side_effect = read
    target.client.write_gatt_char.side_effect = write
    for _ in range(2):
        await target.bed.read_positions()
        assert not remaining
        assert not target.bed._reads
    await target.bed.stop_notify()


async def test_cancelled_old_continuation_cannot_remove_new_generation_task() -> None:
    target = Processor()
    await target.bed.start_notify()
    entered = asyncio.Event()

    async def read(char):
        entered.set()
        await asyncio.Event().wait()

    target.client.read_gatt_char.side_effect = read
    future = asyncio.get_running_loop().create_future()
    target.bed._pending[p.CONTROL_UUID] = future
    target.bed._accept(p.CONTROL_UUID, p.frames(b'{"details":{}}', 5)[0])
    await entered.wait()
    old = target.bed._reads[p.CONTROL_UUID]
    target.bed.on_disconnect()
    replacement = asyncio.create_task(asyncio.Event().wait())
    target.bed._reads[p.CONTROL_UUID] = replacement
    await old
    assert target.bed._reads[p.CONTROL_UUID] is replacement
    assert isinstance(future.exception(), ConnectionError)
    target.bed._pending.clear()
    target.bed.on_disconnect()
    with pytest.raises(asyncio.CancelledError):
        await replacement
    assert not target.bed._reads and not target.bed._buffers


@pytest.mark.parametrize("axis", ["head", "foot", "lumbar"])
@pytest.mark.parametrize("source", ["write", "reply"])
async def test_early_transport_timeout_reaches_caller_after_axis_release(axis, source) -> None:
    target = Processor()
    await target.bed.start_notify()
    target.coordinator.motor_pulse_delay_ms = 1000
    if source == "write":
        original = target.client.write_gatt_char.side_effect

        async def fail_once(char, data, response):
            target.client.write_gatt_char.side_effect = original
            raise TimeoutError("ATT failed")

        target.client.write_gatt_char.side_effect = fail_once
    else:
        target.block_movement = True
    with (
        patch("custom_components.adjustable_bed.beds.sleeptracker.REPLY_TIMEOUT", 0.001),
        pytest.raises(TimeoutError),
    ):
        await target.bed._move(axis, "up")
    assert target.requests[-1][1]["request"]["movement"] == {
        "position": {"side": 2, "location": axis},
        "action": "stop",
    }
    assert not target.client.is_connected


async def test_local_hold_expiry_is_successful_and_releases() -> None:
    target = Processor()
    await target.bed.start_notify()
    target.block_movement = True
    target.coordinator.motor_pulse_delay_ms = 1
    await target.bed.move_back_up()
    assert target.requests[-1][1]["request"]["movement"]["action"] == "stop"
    assert not target.client.is_connected


@pytest.mark.parametrize("ordinal", range(4))
@pytest.mark.parametrize("mode", [0, 2])
@pytest.mark.parametrize("count", [2, 3])
@pytest.mark.parametrize("scalar", [7, "not-a-remote-snapshot", True])
async def test_wind_down_transaction_ignores_unconsumed_later_scalar(
    ordinal, mode, count, scalar
) -> None:
    target = Processor()
    await target.bed.start_notify()
    target.bed._snapshot_side = ordinal
    target.bed._state["wind_down_running"] = mode == 0
    snapshots = [{"side": (ordinal + 1) % 4, "windDownMode": mode}, scalar]
    if count == 3:
        snapshots.append({"windDownMode": 0 if mode else 2})
    reply_with(target, {"details": {"body": {"snapshots": snapshots}}})
    prior_remote = {
        key: target.states[key]
        for key in (
            "sleeptracker_massage_pattern",
            "sleeptracker_light_on",
            "sleeptracker_massage_head_strength",
            "sleeptracker_left_level",
        )
    }
    await target.bed.read_positions()
    assert target.states["sleeptracker_wind_down_running"] is (mode != 0)
    assert all(target.states[key] == value for key, value in prior_remote.items())
    assert target.client.is_connected and target.bed.protocol_diagnostics["session_ready"]
    target.client.write_gatt_char.side_effect = target.write
    await target.bed.read_positions()
    assert target.bed.protocol_diagnostics["session_ready"]
    await target.bed.stop_notify()


@pytest.mark.parametrize(
    "snapshots",
    [
        [7, {"windDownMode": 2}],
        [{"windDownMode": 2}, []],
        [{"windDownMode": 2, "head": 7}],
        [{"windDownMode": 2, "fan": 7}],
    ],
)
async def test_wind_down_transaction_rejects_malformed_consumed_shapes(snapshots) -> None:
    target = Processor()
    await target.bed.start_notify()
    reply_with(target, {"details": {"body": {"snapshots": snapshots}}})
    with pytest.raises(ValueError):
        await target.bed.read_positions()
    assert not target.client.is_connected
    assert target.states["sleeptracker_wind_down_running"] is None


@pytest.mark.parametrize(
    "model,operation",
    [
        (model, operation)
        for model in ("ergo_prosmart", "activebreeze_large", "activebreeze_small", "slim_prosmart")
        for operation in ("read", "wind_down", "climate")
        if operation != "climate" or p.MODELS[model].breeze
    ],
)
@pytest.mark.parametrize(
    "snapshots",
    [
        [{"windDownMode": 2, "unused": [[]]}, 7],
        [{"windDownMode": 2}, 7, {"unused": [[]]}],
    ],
)
async def test_nested_array_reply_cannot_publish_acknowledged_state(model, operation, snapshots) -> None:
    target = Processor(model=model)
    await target.bed.start_notify()
    reply_with(target, {"details": {"body": {"snapshots": snapshots}}})
    with pytest.raises(ValueError, match="nested array"):
        if operation == "read":
            await target.bed.read_positions()
        elif operation == "wind_down":
            await target.bed.async_execute_sleeptracker_request(p.Request("wind_down", mode=1))
        else:
            await target.bed.async_execute_sleeptracker_request(
                p.Request("climate", fan_side="left", heating=True, level=3)
            )
    assert not target.client.is_connected
    assert not target.bed.protocol_diagnostics["session_ready"]
    assert target.states["sleeptracker_wind_down_running"] is None
    assert target.states.get("sleeptracker_left_commanded_timer_seconds") is None


@pytest.mark.parametrize(
    "model,operation",
    [
        (model, operation)
        for model in ("ergo_prosmart", "activebreeze_large", "activebreeze_small", "slim_prosmart")
        for operation in ("read", "wind_down", "climate")
        if operation != "climate" or p.MODELS[model].breeze
    ],
)
@pytest.mark.parametrize(
    "raw",
    [
        b'{"details":{"body":{"snapshots":[{"windDownMode":2,"unused":[[]],"unused":0},7]}}}',
        b'{"details":{"body":{"snapshots":[{"windDownMode":2,"unused":[[]],"unused":{}},7]}}}',
        b'{"details":{"body":{"unused":[[]]},"body":{"snapshots":[{"windDownMode":2},7]}}}',
        b'{"details":{"unused":[[]]},"details":{"body":{"snapshots":[{"windDownMode":2},7]}}}',
        b'{"details":{"body":{"snapshots":[{"windDownMode":2,"unused":{"deep":[[]]},"unused":0},7]}}}',
    ],
)
async def test_duplicate_key_reply_cannot_publish_acknowledged_state(model, operation, raw) -> None:
    target = Processor(model=model)
    await target.bed.start_notify()
    reply_with(target, raw)
    with pytest.raises(ValueError, match="nested array"):
        if operation == "read":
            await target.bed.read_positions()
        elif operation == "wind_down":
            await target.bed.async_execute_sleeptracker_request(p.Request("wind_down", mode=1))
        else:
            await target.bed.async_execute_sleeptracker_request(
                p.Request("climate", fan_side="left", heating=True, level=3)
            )
    assert not target.client.is_connected
    assert target.states["sleeptracker_wind_down_running"] is None
    assert target.states.get("sleeptracker_left_commanded_timer_seconds") is None


async def test_nonpremium_remote_rejects_scalar_snapshots() -> None:
    target = Processor(model="ergo")
    await target.bed.start_notify()
    reply_with(target, {"details": {"body": {"snapshots": [{"windDownMode": 2}, 7]}}})
    with pytest.raises(ValueError):
        await target.bed.read_positions()
    assert not target.client.is_connected


async def test_authenticated_handshake_and_transport_bounded_frames() -> None:
    target = Processor(mtu=23)
    await target.bed.start_notify()
    assert [uuid for uuid, _ in target.requests] == [p.AUTH_UUID, p.CONTROL_UUID]
    assert target.requests[0][1]["type"] == "authenticate"
    assert target.requests[1][1] == {"wsCommand": "motor-status", "authToken": "session-secret"}
    assert all(len(frame) <= 20 for _, frame, _ in target.frames)
    assert [call.args[0].uuid for call in target.client.start_notify.await_args_list] == [
        p.HELLO_UUID,
        p.AUTH_UUID,
        p.CONTROL_UUID,
    ]
    diagnostics = json.dumps(target.bed.protocol_diagnostics)
    assert (
        "synthetic-secret" not in diagnostics
        and "session-secret" not in diagnostics
        and "private" not in diagnostics
    )
    assert target.states["sleeptracker_massage_head_strength"] == 4
    assert target.states["sleeptracker_left_mode"] == "heat"
    assert target.bed.protocol_diagnostics["layout_matches_report"] is True
    assert target.bed.protocol_diagnostics["reported_controller_version"] == 80
    assert not target.bed.supports_position_feedback
    assert target.bed.position_number_specs == ()
    assert not target.bed.supports_single_address_pairing
    for call in target.coordinator.record_command_trace.call_args_list:
        assert call.kwargs["payload"]["hex"] == "**REDACTED**"
    await target.bed.stop_notify()


async def test_restricted_session_and_explicit_light_route() -> None:
    target = Processor(restricted=True)
    await target.bed.start_notify()
    assert [uuid for uuid, _ in target.requests] == [p.CONTROL_UUID]
    await target.bed.lights_toggle()
    assert target.requests[-1][1] == {"command": "light", "params": {"operation": "toggle"}}
    await target.bed.stop_notify()


async def test_restricted_route_does_not_require_unused_auth_or_firmware_read() -> None:
    target = Processor(restricted=True)
    del target.char[p.AUTH_UUID]

    async def read(char):
        if char.uuid == p.FIRMWARE_UUID:
            raise OSError("Optional revision read unavailable")
        return await target.read(char)

    target.client.read_gatt_char.side_effect = read
    await target.bed.start_notify()
    assert [call.args[0].uuid for call in target.client.start_notify.await_args_list] == [
        p.HELLO_UUID,
        p.CONTROL_UUID,
    ]
    assert target.bed.protocol_diagnostics["session_ready"] is True
    await target.bed.stop_notify()


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_movement_release_ignores_cancel_and_discards_late_session(task_cancel) -> None:
    target = Processor()
    await target.bed.start_notify()
    target.block_movement = True
    task = asyncio.create_task(target.bed.move_back_up())
    await target.hold.wait()
    if task_cancel:
        task.cancel()
    else:
        target.coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert target.requests[-1][1]["request"]["movement"] == {
        "position": {"side": 2, "location": "head"},
        "action": "stop",
    }
    assert target.client.disconnect.await_count == 1
    assert target.bed.protocol_diagnostics["authenticated"] is False
    assert target.bed.protocol_diagnostics["session_ready"] is False


async def test_completed_movement_has_axis_release_and_no_fixed_refresh_delay() -> None:
    target = Processor()
    await target.bed.start_notify()
    await target.bed.move_lumbar_up()
    movements = [
        value["request"]["movement"]
        for _, value in target.requests
        if "movement" in value.get("request", {})
    ]
    assert movements[0] == {
        "position": {"side": 2, "location": "lumbar"},
        "action": "up",
        "ticks": 4,
        "waitForResponse": False,
    }
    assert movements[-1]["action"] == "stop"
    await target.bed.stop_notify()


async def test_service_and_entity_climate_model_gates() -> None:
    target = Processor(model="activebreeze_small")
    await target.bed.start_notify()
    await target.bed.async_execute_sleeptracker_request(
        p.Request("climate", fan_side="left", level=3, heating=False, constant=False)
    )
    fan = target.requests[-1][1]["request"]["fanControl"]
    assert fan == {
        "position": {"side": 0},
        "leftIsConstant": False,
        "leftIsHeating": False,
        "leftLevel": 3,
        "leftTimer": 36000,
    }
    assert target.states["sleeptracker_left_curve"] == "curve"
    assert target.states["sleeptracker_left_commanded_timer_seconds"] == 36000
    spec = next(
        s for s in target.bed.controller_number_specs if s.key == "sleeptracker_right_level"
    )
    await spec.set_fn(target.bed, 1)
    assert "rightLevel" in target.requests[-1][1]["request"]["fanControl"]
    await target.bed.stop_notify()
    generic = Processor(model="ergo")
    with pytest.raises(ValueError):
        generic.bed.validate_sleeptracker_request(p.Request("climate"))
    assert not any("level" in s.key for s in generic.bed.controller_number_specs)
    assert generic.bed.memory_slot_count == 1
    assert not generic.bed.supports_preset_tv


async def test_wrong_service_cannot_send_json_to_uart() -> None:
    target = Processor()
    target.client.services.get_service = lambda uuid: None
    with pytest.raises(ConnectionError, match="processor service"):
        await target.bed.start_notify()
    assert not target.client.write_gatt_char.called


async def test_first_service_precedence_is_not_fallback_after_missing_channels() -> None:
    target = Processor()
    target.client.services.get_service = lambda uuid: SimpleNamespace(
        characteristics=[] if uuid == p.SERVICE_UUID else list(target.char.values())
    )
    with pytest.raises(ConnectionError, match="lacks"):
        await target.bed.start_notify()
    assert not target.client.write_gatt_char.called


async def test_read_continuation_uses_same_channel() -> None:
    target = Processor(restricted=True)
    parts = list(p.frames(b'{"FSPVersion":"6.1.56"}', 10))

    async def read(char):
        if char.uuid == p.HELLO_UUID:
            return parts.pop(0)
        return b"1.0"

    target.client.read_gatt_char.side_effect = read
    await target.bed.start_notify()
    assert not parts
    assert [call.args[0].uuid for call in target.client.read_gatt_char.await_args_list].count(
        p.HELLO_UUID
    ) == 3
    await target.bed.stop_notify()


async def test_old_callbacks_are_ignored_after_disconnect() -> None:
    target = Processor()
    await target.bed.start_notify()
    old = target.receivers[p.CONTROL_UUID]
    target.bed.on_disconnect()
    before = dict(target.states)
    old(
        target.char[p.CONTROL_UUID],
        bytearray(p.frames(b'{"body":{"snapshots":[{"massagePattern":3}]}}', 500)[0]),
    )
    assert target.states == before


def test_saving_disabled_only_for_exact_processor_type() -> None:
    target = Processor()
    for processor_type in (5, 6, 7):
        target.bed._processor_type = processor_type
        with pytest.raises(ValueError):
            target.bed.validate_sleeptracker_request(
                p.Request("preset", preset="zero_g", save=True)
            )
    for processor_type in (0, 4, 8, -1):
        target.bed._processor_type = processor_type
        target.bed.validate_sleeptracker_request(p.Request("preset", preset="zero_g", save=True))


@pytest.mark.parametrize("mode", [1, 2])
async def test_wind_down_mode_does_not_invent_a_countdown_parameter(mode) -> None:
    target = Processor()
    await target.bed.start_notify()
    await target.bed.async_execute_sleeptracker_request(p.Request("wind_down", mode=mode))
    assert target.requests[-1][1] == {
        "wsCommand": "motor-command",
        "authToken": "session-secret",
        "request": {"windDown": {"position": {"side": 2}, "mode": mode}},
    }
    await target.bed.massage_off()
    assert target.requests[-1][1]["request"]["stop"] == {
        "action": "massage",
        "position": {"side": 2},
    }
    await target.bed.stop_notify()


async def test_missing_movement_reply_still_releases_within_hold_budget() -> None:
    target = Processor()
    await target.bed.start_notify()
    target.block_movement = True
    await asyncio.wait_for(target.bed.move_back_down(), timeout=0.5)
    assert target.requests[-1][1]["request"]["movement"]["action"] == "stop"
    assert not target.client.is_connected


async def test_explicit_write_cancel_releases_all_and_reauthenticates() -> None:
    target = Processor()
    await target.bed.start_notify()
    target.block_movement = True
    cancel = asyncio.Event()
    task = asyncio.create_task(
        target.bed.write_command(p.movement("head", "up", 2, "session-secret"), cancel_event=cancel)
    )
    await target.hold.wait()
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert target.requests[-1][1]["request"]["stop"]["action"] == "all"
    assert target.states["sleeptracker_massage_head_strength"] is None
    assert target.states["sleeptracker_left_mode"] is None
    target.client.is_connected = True
    await target.bed.start_notify()
    assert sum(uuid == p.AUTH_UUID for uuid, _ in target.requests) == 2
    assert target.bed.protocol_diagnostics["session_ready"] is True
    await target.bed.stop_notify()


async def test_identify_cancellation_sends_literal_light_off() -> None:
    target = Processor()
    await target.bed.start_notify()
    task = asyncio.create_task(target.bed.async_execute_sleeptracker_request(p.Request("identify")))
    while not any(value.get("command") == "light" for _, value in target.requests):
        await asyncio.sleep(0)
    target.coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert target.requests[-1][1] == {"side": 1, "command": "light", "params": {"operation": "off"}}
    await target.bed.stop_notify()


async def test_local_identification_uses_four_response_driven_bare_lights_and_cleanup() -> None:
    target = Processor(restricted=True)
    await target.bed.start_notify()
    await target.bed.async_execute_sleeptracker_request(p.Request("identify", mode=2))
    lights = [value for _, value in target.requests if value.get("command") == "light"]
    assert [value["params"]["operation"] for value in lights] == [
        "toggle",
        "off",
        "toggle",
        "off",
        "off",
    ]
    assert all(set(value) == {"command", "params"} for value in lights)
    await target.bed.stop_notify()


@pytest.mark.parametrize("mode,restricted", [(1, False), (2, True)])
@pytest.mark.parametrize(
    "raw,invalid",
    [
        (b'{}', True),
        (b'{"unused":[[]]}', True),
        (b'{"unused":[[]],"unused":0}', True),
        (b'{"details":{"body":{}}}', False),
        (b'{"unused":[{"children":[true,null,7]}]}', False),
    ],
)
async def test_identification_final_off_validates_reply_before_session_reuse(mode, restricted, raw, invalid) -> None:
    target = Processor(restricted=restricted)
    await target.bed.start_notify()
    count = 0

    async def write(char, data, response):
        nonlocal count
        target.frames.append((char.uuid, bytes(data), response))
        if (payload := target.outgoing[char.uuid].feed(bytes(data))) is None:
            return
        target.requests.append((char.uuid, json.loads(payload)))
        count += 1
        reply = raw if count == 5 else b'{"details":{"body":{"snapshots":[{"windDownMode":0}]}}}'
        for frame in p.frames(reply, 500):
            target.receivers[char.uuid](char, bytearray(frame))

    async def immediate(coro, *, timeout):
        coro.close()
        raise TimeoutError

    target.client.write_gatt_char.side_effect = write
    with patch("custom_components.adjustable_bed.beds.sleeptracker.asyncio.wait_for", immediate):
        if invalid:
            with pytest.raises(ValueError):
                await target.bed.async_execute_sleeptracker_request(p.Request("identify", mode=mode))
        else:
            await target.bed.async_execute_sleeptracker_request(p.Request("identify", mode=mode))
    assert count == 5
    assert target.requests[-1][1]["params"]["operation"] == "off"
    assert target.client.is_connected is (not invalid)
    assert target.bed.protocol_diagnostics["session_ready"] is (not invalid)
    if invalid:
        assert target.bed._token is None
        assert target.states["sleeptracker_wind_down_running"] is None
        with pytest.raises(ConnectionError):
            await target.bed.lights_toggle()
    else:
        target.client.write_gatt_char.side_effect = target.write
        await target.bed.read_positions()
        assert target.bed.protocol_diagnostics["session_ready"]
        await target.bed.stop_notify()


def test_metadata_preserves_optional_sensor_count_rule_and_firmware_ui_gates() -> None:
    target = Processor(model="activebreeze_small")
    target.bed._parse_hello(
        {
            "product": "sleeptracker",
            "FSPVersion": "6.1.55",
            "leftSensor": {"status": "Disconnected", "motors_bitfield": 128},
            "rightSensor": {"status": "Connected", "massagers_bitfield": 255},
            "motorMeta": {"capabilities": [{"controllerModel": "SLIM_BEST"}]},
        }
    )
    target.bed._update_status(
        {
            "body": {
                "invariants": [
                    {"type": "controller", "model": "ACTIVE_BREEZE_SMALL", "version": 112}
                ]
            }
        }
    )
    metadata = target.bed.protocol_diagnostics
    assert metadata["connected_sensor_count"] == 1
    assert metadata["setup_connected_sensor_count"] == 0
    assert metadata["left_sensor_motors_bitfield"] == 128
    assert metadata["hello_layout_alias"] == 19
    assert metadata["layout_id"] == 21
    assert metadata["app_firmware_threshold"] == 113
    assert metadata["app_firmware_below_threshold"] is True
    assert target.bed.supports_sleeptracker_controls


async def test_late_read_cannot_restore_disconnected_state() -> None:
    target = Processor()
    await target.bed.start_notify()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def read(char):
        entered.set()
        await finish.wait()
        return p.frames(b'{"body":{"snapshots":[{"massagePattern":3}]}}', 500)[0]

    target.client.read_gatt_char.side_effect = read
    task = asyncio.create_task(target.bed._read(p.CONTROL_UUID))
    await entered.wait()
    target.bed.on_disconnect()
    before = dict(target.states)
    finish.set()
    await task
    assert target.states == before


async def test_reply_timeout_releases_and_closes_ambiguous_session() -> None:
    target = Processor()
    await target.bed.start_notify()
    target.block_movement = True
    with (
        patch("custom_components.adjustable_bed.beds.sleeptracker.REPLY_TIMEOUT", 0.005),
        pytest.raises(TimeoutError),
    ):
        await target.bed.write_command(p.movement("head", "up", 2, "session-secret"))
    assert target.requests[-1][1]["request"]["stop"]["action"] == "all"
    assert not target.client.is_connected


@pytest.mark.parametrize(
    "key,value", [("sleeptracker_wave_minutes", 6), ("sleeptracker_left_level", 1.5)]
)
async def test_number_callbacks_reject_fractional_or_unsupported_values(key, value) -> None:
    target = Processor(model="activebreeze_large")
    spec = next(s for s in target.bed.controller_number_specs if s.key == key)
    with pytest.raises(ValueError):
        await spec.set_fn(target.bed, value)
    assert not target.client.write_gatt_char.called
