"""Focused Pairlink controller tests through the registered central callback."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.adjustable_bed.beds.reverie_comfort import ReverieComfortRequest
from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController
from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
    PAIRLINK_WRITE_UUID,
    a7_payload,
    build_user_frame,
    decrypt_user_frame,
    encrypt_login_block,
    encrypt_user_frame,
    state_query_payloads,
    status_sync_payloads,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
    PairlinkCredentials,
    PairlinkHomeIdOrigin,
    PairlinkRole,
    PairlinkRuntime,
    PairlinkRuntimeNotReadyError,
)

_ADDRESS = "AA:BB:CC:DD:EE:FF"
_HOME_ID = 5566
_PASSWORD = b"1122"


class _Characteristic:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class _Service:
    def __init__(self, uuid: str, *characteristic_uuids: str) -> None:
        self.uuid = uuid
        self.characteristics = [_Characteristic(value) for value in characteristic_uuids]


class _GattClient:
    def __init__(self) -> None:
        self.is_connected = True
        self.mtu_size = 27
        self.services = [
            _Service(
                "9e5d1e47-5c13-43a0-8635-82adffc0386f",
                "9e5d1e47-5c13-43a0-8635-82adffc1386f",
                "9e5d1e47-5c13-43a0-8635-82adffc2386f",
            )
        ]
        self.writes: list[tuple[str, bytes, bool]] = []
        self.notify_callback: Callable[[object, bytearray], None] | None = None

    async def write_gatt_char(self, characteristic: str, data: bytes, *, response: bool) -> None:
        self.writes.append((characteristic, data, response))

    async def start_notify(
        self, _characteristic: str, callback: Callable[[object, bytearray], None]
    ) -> None:
        self.notify_callback = callback

    async def stop_notify(self, _characteristic: str) -> None:
        self.notify_callback = None


class _ScheduledCall:
    def __init__(self, delay: float, callback: Callable[..., None], args: tuple[object, ...]) -> None:
        self.delay = delay
        self.callback = callback
        self.args = args
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        if not self.cancelled:
            self.callback(*self.args)


class _FakeLoop:
    def __init__(self) -> None:
        self.calls: list[_ScheduledCall] = []

    def call_later(
        self, delay: float, callback: Callable[..., None], *args: object
    ) -> _ScheduledCall:
        call = _ScheduledCall(delay, callback, args)
        self.calls.append(call)
        return call


def _login_context() -> bytes:
    home = _HOME_ID.to_bytes(4, "little")
    return b"".join(bytes((home_byte, password_byte)) for home_byte, password_byte in zip(home, _PASSWORD, strict=True)) + b"LOGINKEY"


def _login_packet(*, home_id: int = _HOME_ID, session_key: bytes = bytes.fromhex("10203040")) -> bytes:
    plain = home_id.to_bytes(4, "little") + session_key + b"ignored!"
    return b"\x01\x19" + encrypt_login_block(plain, login_key=_login_context())


def _controller(model: str = "R510L") -> tuple[
    ReveriePairlinkController,
    _GattClient,
    PairlinkRuntime,
    list[asyncio.Task[None]],
]:
    credentials = PairlinkCredentials.from_inputs(
        _HOME_ID,
        home_id_origin=PairlinkHomeIdOrigin.DECLARED_HA_POLICY,
    )
    runtime = PairlinkRuntime(
        credentials,
        role=PairlinkRole.CENTRAL,
        target_mac=_ADDRESS,
        local_join_bt_mac=b"\x01" * 6,
    )
    client = _GattClient()
    fake_loop = _FakeLoop()
    tasks: list[asyncio.Task[None]] = []

    def create_task(coroutine: Coroutine[None, None, None], name: str) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine, name=name)
        tasks.append(task)
        return task

    coordinator = SimpleNamespace(
        client=client,
        address=_ADDRESS,
        cancel_command=asyncio.Event(),
        handle_controller_state_update=Mock(),
        handle_controller_state_updates=Mock(),
        clear_position_feedback=Mock(),
        hold_command_connection=nullcontext,
        hass=SimpleNamespace(async_create_task=create_task, loop=fake_loop),
        record_command_trace=Mock(),
    )
    controller = ReveriePairlinkController(coordinator, model=model, runtime=runtime)
    controller._sdk_io._store = Mock(async_load=AsyncMock(return_value=None), async_save=AsyncMock())

    async def execute_controller_command(command, **_kwargs) -> None:
        await command(controller)

    coordinator.async_execute_controller_command = execute_controller_command
    coordinator.async_execute_controller_query = execute_controller_command
    return controller, client, runtime, tasks


async def _notify(
    client: _GattClient,
    tasks: list[asyncio.Task[None]],
    packet: bytes,
) -> None:
    assert client.notify_callback is not None
    client.notify_callback(None, bytearray(packet))
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)


async def _join_central(
    controller: ReveriePairlinkController,
    client: _GattClient,
    runtime: PairlinkRuntime,
    tasks: list[asyncio.Task[None]],
) -> None:
    await controller.start_notify()
    await _notify(client, tasks, _login_packet())
    await _notify(client, tasks, b"\x02\x31\x08")
    assert runtime.joined


async def test_central_login_callback_replies_and_dispatches_with_learned_session() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await controller.start_notify()

    await _notify(client, tasks, _login_packet())

    expected_reply = encrypt_login_block(
        _HOME_ID.to_bytes(4, "little")
        + _PASSWORD
        + bytes.fromhex("10203040")
        + b"\x04" * 4,
        login_key=_login_context(),
    )
    assert client.writes == [(PAIRLINK_WRITE_UUID, b"\x02\x19" + expected_reply, False)]
    assert runtime.admitted_peer_count == 1
    assert runtime.central_add_pending is True
    assert runtime.joined is False

    await _notify(client, tasks, b"\x02\x31\x08")
    assert client.writes[-1] == (PAIRLINK_WRITE_UUID, b"\x01\x20", False)
    assert runtime.joined is True

    # Native BSS zero is a valid own address until a real 010A replaces it.
    await controller.async_send_payload(bytes.fromhex("0101FF00"))
    expected_zero_va = encrypt_user_frame(
        build_user_frame(
            bytes.fromhex("0101FF00"),
            destination=bytes.fromhex("FFFFFFFF"),
            channel=32,
            own_virtual_address=bytes(4),
        ),
        event_key=runtime.current_event_key,
        device_key=bytes.fromhex("10203040"),
    )
    assert client.writes[-1] == (PAIRLINK_WRITE_UUID, expected_zero_va, False)

    await _notify(client, tasks, bytes.fromhex("010A11223344"))
    await controller.async_send_payload(bytes.fromhex("0101FF00"))
    expected_assigned_va = encrypt_user_frame(
        build_user_frame(
            bytes.fromhex("0101FF00"),
            destination=bytes.fromhex("FFFFFFFF"),
            channel=32,
            own_virtual_address=bytes.fromhex("11223344"),
        ),
        event_key=runtime.current_event_key,
        device_key=bytes.fromhex("10203040"),
    )
    assert client.writes[-1] == (PAIRLINK_WRITE_UUID, expected_assigned_va, False)


async def test_central_writes_are_traced_redacted() -> None:
    """The login reply carries the password; no Pairlink frame is traced in clear."""
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    await controller.async_send_payload(bytes.fromhex("0101FF00"))

    traces = [call.kwargs for call in controller._coordinator.record_command_trace.call_args_list]
    assert len(client.writes) >= 3  # login reply, add confirmation, user frame
    assert [(t["characteristic_uuid"], t["payload"]["length"]) for t in traces] == [
        (uuid, len(data)) for uuid, data, _response in client.writes
    ]
    assert {(t["payload"]["hex"], t["payload"]["ascii_preview"]) for t in traces} == {
        ("**REDACTED**", None)
    }


async def test_clock_query_is_one_shot_and_rearmed_only_by_source_response() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    fake_loop = controller._coordinator.hass.loop
    await _join_central(controller, client, runtime, tasks)

    active_call = next(call for call in fake_loop.calls if call.delay == 0)
    clock_call = next(call for call in fake_loop.calls if call.delay == 5)
    assert active_call.delay == 0
    assert clock_call.delay == 5
    active_call.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    status_payloads = tuple(
        decrypt_user_frame(
            value,
            event_key=runtime.current_event_key,
            device_key=bytes.fromhex("10203040"),
        )[10:]
        for _characteristic, value, _response in client.writes[-2:]
    )
    assert status_payloads == status_sync_payloads()
    status_rearm = fake_loop.calls[-1]
    assert status_rearm.delay == 1
    assert not clock_call.cancelled

    status_rearm.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    repeated_status_payloads = tuple(
        decrypt_user_frame(
            value,
            event_key=runtime.current_event_key,
            device_key=bytes.fromhex("10203040"),
        )[10:]
        for _characteristic, value, _response in client.writes[-2:]
    )
    assert repeated_status_payloads == status_sync_payloads()

    clock_call.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert client.writes[-1] == (PAIRLINK_WRITE_UUID, b"\x01\x1a", False)

    await _notify(client, tasks, b"\x02\x1a" + bytes.fromhex("78563412"))
    assert controller._last_pairlink_clock_seconds == 0x12345678
    assert fake_loop.calls[-1].delay == 5
    assert runtime.joined

    current_status_timer = controller._status_sync_timer
    current_clock_timer = controller._clock_sync_timer
    assert current_status_timer is not None
    assert current_clock_timer is not None
    await controller.stop_notify()
    assert current_status_timer.cancelled
    assert current_clock_timer.cancelled
    assert controller._status_sync_timer is None
    assert controller._clock_sync_timer is None


async def test_wrong_home_and_truncated_native_login_do_not_create_a_session() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await controller.start_notify()

    await _notify(client, tasks, b"\x01\x19short")
    await _notify(client, tasks, _login_packet(home_id=5567))

    assert client.writes == []
    assert runtime.admitted_peer_count == 0
    assert runtime.central_add_pending is True
    assert runtime.joined is False


async def test_cmd02_and_encrypted_seed_replace_key_then_zero_seed_only_clears_index() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await controller.start_notify()
    await _notify(client, tasks, _login_packet())
    await _notify(client, tasks, b"\x02\x31\x08")

    first_seed = bytes.fromhex("01020304")
    cmd02 = bytearray(14)
    cmd02[:2] = b"\x01\x02"
    cmd02[10:14] = first_seed
    await _notify(client, tasks, bytes(cmd02))
    first_event_key = runtime.current_event_key
    first_index = runtime.event_key_index
    assert first_event_key != bytes.fromhex("be150000") + b"1122EVENTKEY"
    assert first_index != bytes(4)
    assert len(runtime.event_key_history) == 5

    next_seed = bytes.fromhex("A1A2A3A4")
    source_event = b"\x03\xFF\xFF\xFF\xFF\x11\x32" + next_seed
    encrypted_event = encrypt_user_frame(
        source_event,
        event_key=first_event_key,
        device_key=bytes.fromhex("10203040"),
    )
    await _notify(client, tasks, encrypted_event)
    second_event_key = runtime.current_event_key
    second_index = runtime.event_key_index
    assert second_event_key != first_event_key
    assert second_index != first_index

    zero_seed = bytearray(14)
    zero_seed[:2] = b"\x01\x02"
    await _notify(client, tasks, bytes(zero_seed))
    assert runtime.current_event_key == second_event_key
    assert runtime.event_key_index == bytes(4)
    assert runtime.event_key_history[-1][2] == second_event_key


async def test_registered_channel20_updates_state_without_sdk_fallthrough() -> None:
    controller, client, _runtime, tasks = _controller()
    await controller.start_notify()
    forwarded: list[tuple[int, bytes | None, bool]] = []
    controller.set_mesh_event_callback(
        lambda event_type, data, broadcast: forwarded.append((event_type, data, broadcast))
    )

    # The source envelope carries sender VA4, then 02/A7 and selector/value.
    packet = b"\x03\xFF\xFF\xFF\xFF\x20" + bytes.fromhex("11223344") + bytes.fromhex("02A70137")
    await _notify(client, tasks, packet)

    assert controller._state["back_position"] == 55
    assert forwarded == [(0x20, bytes.fromhex("1122334402A70137"), True)]
    assert controller._coordinator.handle_controller_state_update.call_args_list == [
        (("back_position", 55),)
    ]


async def test_raw_registered_selector_accepts_six_through_nine_bytes_before_sdk() -> None:
    controller, client, _runtime, tasks = _controller()
    await controller.start_notify()
    routed: list[tuple[int, bytes | None, bool]] = []
    sdk_frames: list[bytes] = []
    controller.set_mesh_event_callback(
        lambda event_type, data, broadcast: routed.append(
            (event_type, data, broadcast)
        )
    )
    controller._consume_sdk_frame = lambda effect: sdk_frames.append(effect.frame)

    for size in range(6, 10):
        packet = b"\x03" + b"\xFF" * 4 + b"\x20" + bytes(range(size - 6))
        await _notify(client, tasks, packet)

    assert routed == [
        (0x20, bytes(range(size - 6)), True)
        for size in range(6, 10)
    ]
    assert sdk_frames == []


async def test_channel12_sign_callback_runs_exact_status8_queries_for_current_peer() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await controller.start_notify()
    await _notify(client, tasks, _login_packet())
    await _notify(client, tasks, b"\x02\x31\x08")
    client.writes.clear()

    # MeshCommon uses byte2BtAddr (reverse wire MAC) and requires an actual
    # DeviceBean. Learn it through GetPingResponse before asserting callback8.
    current_peer = bytes.fromhex(_ADDRESS.replace(":", ""))[::-1]
    await _notify(
        client, tasks,
        b"\x03" + b"\xff" * 5 + current_peer
        + bytes.fromhex("1122334406F10102"),
    )
    client.writes.clear()
    sign_response = b"\x03\xFF\xFF\xFF\xFF\x12\x30" + current_peer + b"\x01"
    await _notify(client, tasks, sign_response)

    decoded_payloads = tuple(
        decrypt_user_frame(
            value,
            event_key=runtime.current_event_key,
            device_key=bytes.fromhex("10203040"),
        )[10:]
        for _characteristic, value, _response in client.writes
    )
    assert decoded_payloads == state_query_payloads()

    client.writes.clear()
    other_peer = bytes.fromhex("102030405060")
    unrelated = b"\x03\xFF\xFF\xFF\xFF\x12\x30" + other_peer + b"\x00"
    await _notify(client, tasks, unrelated)
    assert client.writes == []
    assert runtime.sign_gate.sign_all is False

    await _notify(client, tasks, unrelated[:-1])
    assert client.writes == []

    denied_current_peer = b"\x03\xFF\xFF\xFF\xFF\x12\x30" + current_peer + b"\x00"
    await _notify(client, tasks, denied_current_peer)
    assert runtime.sign_gate.device_signs[_ADDRESS] == "0"
    with pytest.raises(PermissionError, match="signing state"):
        await controller.async_send_payload(
            bytes.fromhex("0101FF00"),
            destination=bytes.fromhex("01020304"),
            channel=16,
        )
    assert client.writes == []

    allowed_current_peer = b"\x03\xFF\xFF\xFF\xFF\x12\x30" + current_peer + b"\x01"
    await _notify(client, tasks, allowed_current_peer)
    assert runtime.sign_gate.device_signs[_ADDRESS] == "1"
    assert runtime.sign_gate.sign_all is False
    await controller.async_send_payload(
        bytes.fromhex("0101FF00"),
        destination=bytes.fromhex("01020304"),
        channel=16,
    )
    assert client.writes
    client.writes.clear()
    with pytest.raises(PermissionError, match="signing state"):
        await controller.async_send_payload(bytes.fromhex("0101FF00"))
    assert client.writes == []


async def test_channel12_status8_requires_a_currently_bound_virtual_address() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    client.writes.clear()

    unknown_vaddr_response = (
        b"\x03\xff\xff\xff\xff\x12\x28"
        + bytes.fromhex("11223344")
        + b"\x05"
    )
    await _notify(client, tasks, unknown_vaddr_response)
    assert client.writes == []

    known_vaddr_event = (
        b"\x03\xff\xff\xff\xff\x20"
        + bytes.fromhex("11223344")
        + bytes.fromhex("02A70137")
    )
    await _notify(client, tasks, known_vaddr_event)
    assert controller._state["back_position"] == 55

    # Registered app-channel state does not allocate an SDK DeviceBean.
    await _notify(client, tasks, unknown_vaddr_response)
    assert client.writes == []
    wire_mac = bytes.fromhex(_ADDRESS.replace(":", ""))[::-1]
    await _notify(
        client, tasks,
        b"\x03" + b"\xff" * 5 + wire_mac
        + bytes.fromhex("1122334406F10102"),
    )
    client.writes.clear()
    await _notify(client, tasks, unknown_vaddr_response)
    decoded_payloads = tuple(
        decrypt_user_frame(
            value,
            event_key=runtime.current_event_key,
            device_key=bytes.fromhex("10203040"),
        )[10:]
        for _characteristic, value, _response in client.writes
    )
    assert decoded_payloads == state_query_payloads()

    controller.on_disconnect()
    await _join_central(controller, client, runtime, tasks)
    client.writes.clear()
    await _notify(client, tasks, unknown_vaddr_response)
    assert client.writes == []


async def test_pairlink_timer_number_keeps_the_raw_byte_out_of_minute_api() -> None:
    controller, _client, _runtime, _tasks = _controller()
    controller.async_send_payload = AsyncMock()

    assert controller.supports_massage_timer is False
    spec = controller.controller_number_specs[0]
    await spec.set_fn(controller, 23)

    controller.async_send_payload.assert_awaited_once_with(a7_payload(22, 23))
    with pytest.raises(NotImplementedError):
        await controller.set_massage_timer(23)


async def test_pairlink_action_methods_match_source_command_vectors() -> None:
    controller, _client, _runtime, _tasks = _controller()
    assert controller.has_lumbar_support is True
    assert "lumbar_up" in controller.held_control_options
    assert any(spec.key == "lumbar" for spec in controller.motor_control_specs)
    controller.async_send_payload = AsyncMock()

    actions = (
        controller.move_back_up(),
        controller.move_back_down(),
        controller.move_back_stop(),
        controller.move_legs_up(),
        controller.move_legs_down(),
        controller.move_legs_stop(),
        controller.move_lumbar_up(),
        controller.move_lumbar_down(),
        controller.move_lumbar_stop(),
        controller.set_motor_position("back", 25),
        controller.set_motor_position("legs", 30),
        controller.set_motor_position("lumbar", 40),
        controller.preset_flat(),
        controller.preset_zero_g(),
        controller.preset_anti_snore(),
        controller.preset_memory(1),
        controller.lights_on(),
        controller.lights_off(),
        controller.set_light_level(100),
        controller.set_light_color((10, 20, 30)),
        controller.set_massage_intensity("head", 1),
        controller.set_massage_intensity("foot", 10),
        controller.massage_off(),
        controller.set_massage_timer_byte(23),
        controller.set_massage_mode(3),
        controller.set_massage_rhythm(True),
    )
    for action in actions:
        await action

    assert tuple(call.args[0] for call in controller.async_send_payload.await_args_list) == (
        bytes.fromhex("0101FF00"),
        bytes.fromhex("0102FF00"),
        bytes.fromhex("01030000"),
        bytes.fromhex("0104FF00"),
        bytes.fromhex("0105FF00"),
        bytes.fromhex("01060000"),
        bytes.fromhex("0107FF00"),
        bytes.fromhex("0108FF00"),
        bytes.fromhex("01090000"),
        bytes.fromhex("01011900"),
        bytes.fromhex("01041E00"),
        bytes.fromhex("01073C00"),
        bytes.fromhex("011C0000"),
        bytes.fromhex("01620000"),
        bytes.fromhex("01650000"),
        bytes.fromhex("01290000"),
        bytes.fromhex("015C0000"),
        bytes.fromhex("015D0000"),
        bytes.fromhex("01A71064"),
        bytes.fromhex("01A7110A"),
        bytes.fromhex("01A71214"),
        bytes.fromhex("01A7131E"),
        bytes.fromhex("014D1400"),
        bytes.fromhex("014F4100"),
        bytes.fromhex("01480000"),
        bytes.fromhex("01A71617"),
        bytes.fromhex("01A71503"),
        bytes.fromhex("01A71401"),
    )




async def test_pairlink_raw_integer_setters_clamp_after_type_validation() -> None:
    controller, _client, _runtime, _tasks = _controller()
    controller.async_send_payload = AsyncMock()

    await controller.set_motor_position("back", -9)
    await controller.set_motor_position("legs", 110)
    await controller.set_motor_position("lumbar", -9)
    await controller.set_light_level(-1)
    await controller.set_light_level(110)
    await controller.set_light_color((-1, 300, 42))

    assert tuple(call.args[0] for call in controller.async_send_payload.await_args_list) == (
        bytes.fromhex("01010000"),
        bytes.fromhex("01046400"),
        bytes.fromhex("01076400"),
        bytes.fromhex("01A71000"),
        bytes.fromhex("01A71064"),
        bytes.fromhex("01A71100"),
        bytes.fromhex("01A712FF"),
        bytes.fromhex("01A7132A"),
    )
    with pytest.raises(ValueError, match="between 0 and 100"):
        controller.angle_to_native_position("back", -1)
    with pytest.raises(ValueError, match="between 0 and 100"):
        controller.angle_to_native_position("back", 101)
    assert tuple(spec.native_max_value for spec in controller.position_number_specs) == (100, 100)


@pytest.mark.parametrize("invalid", (True, 1.5, "3"))
async def test_pairlink_raw_integer_setters_reject_non_integer_values(invalid: object) -> None:
    controller, _client, _runtime, _tasks = _controller()
    controller.async_send_payload = AsyncMock()

    with pytest.raises(ValueError):
        await controller.set_motor_position("back", invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await controller.set_light_level(invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await controller.set_light_color((1, invalid, 3))  # type: ignore[arg-type]

    controller.async_send_payload.assert_not_awaited()


async def test_pairlink_harmoniq_comfort_preflight_excludes_unsupported_lumbar() -> None:
    controller, _client, _runtime, _tasks = _controller(model="Harmoniq Upgrade")

    controller.validate_comfort_request(
        ReverieComfortRequest(
            head_position=20,
            foot_position=30,
            head_massage=0,
            foot_massage=0,
            timer_byte=0,
            mode=0,
            force=True,
        )
    )
    with pytest.raises(ValueError, match="does not support lumbar_position"):
        controller.validate_comfort_request(
            ReverieComfortRequest(head_position=20, lumbar_position=40)
        )


async def test_pairlink_harmoniq_hides_lumbar_control_and_held_contract() -> None:
    controller, _client, _runtime, _tasks = _controller(model="Harmoniq Upgrade")
    controller.async_send_payload = AsyncMock()

    assert controller.has_lumbar_support is False
    assert tuple(spec.key for spec in controller.motor_control_specs) == ("back", "legs")
    assert controller.held_control_options == ("back_up", "back_down", "legs_up", "legs_down")
    with pytest.raises(ValueError, match="lumbar"):
        controller.validate_hold_control("lumbar_up", 150)
    with pytest.raises(ValueError, match="lumbar"):
        await controller.move_lumbar_up()
    with pytest.raises(ValueError, match="lumbar"):
        await controller.set_motor_position("lumbar", 40)
    with pytest.raises(ValueError, match="lumbar"):
        controller.angle_to_native_position("lumbar", 40)

    controller.async_send_payload.assert_not_awaited()


async def test_pairlink_held_axis_has_one_press_and_same_axis_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    controller.async_send_payload = AsyncMock()
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.reverie_pairlink.asyncio.sleep",
        AsyncMock(),
    )

    await controller.hold_control("back_up", 150)

    assert tuple(call.args[0] for call in controller.async_send_payload.await_args_list) == (
        bytes.fromhex("0101FF00"),
        bytes.fromhex("01030000"),
    )


async def test_pairlink_diagnostic_uses_fake_two_second_timer_and_exact_stop_pair() -> None:
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    controller.async_send_payload = AsyncMock()

    await controller.async_start_diagnostic()

    assert controller._diagnostic_timer is not None
    timer = controller._diagnostic_timer
    assert timer.delay == 2
    assert tuple(call.args[0] for call in controller.async_send_payload.await_args_list) == (
        bytes.fromhex("014F1400"),
        bytes.fromhex("015C0000"),
    )
    timer.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)

    assert tuple(call.args[0] for call in controller.async_send_payload.await_args_list) == (
        bytes.fromhex("014F1400"),
        bytes.fromhex("015C0000"),
        bytes.fromhex("01480000"),
        bytes.fromhex("015D0000"),
    )


async def test_central_disconnect_invalidates_session_but_retains_event_key_history() -> None:
    pytest.importorskip("cryptography")
    controller, client, runtime, tasks = _controller()
    await controller.start_notify()
    await _notify(client, tasks, _login_packet())
    await _notify(client, tasks, b"\x02\x31\x08")
    await _notify(client, tasks, bytes.fromhex("010A11223344"))
    cmd02 = bytearray(14)
    cmd02[:2] = b"\x01\x02"
    cmd02[10:14] = bytes.fromhex("01020304")
    await _notify(client, tasks, bytes(cmd02))
    retained_key = runtime.current_event_key
    retained_history = runtime.event_key_history

    await controller.stop_notify()

    # Unsubscribing notification delivery does not fabricate a physical drop.
    assert runtime.joined is True
    controller.on_disconnect()

    assert runtime.central_add_pending is False
    assert runtime.joined is False
    assert runtime.admitted_peer_count == 0
    assert runtime.own_virtual_address == bytes(4)
    assert runtime.current_event_key == retained_key
    assert runtime.event_key_history == retained_history
    with pytest.raises(PairlinkRuntimeNotReadyError, match="central session is not joined"):
        await controller.async_send_payload(bytes.fromhex("0101FF00"))
