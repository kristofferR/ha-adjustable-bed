"""Focused protocol and entity tests for the TiMOTION AHF app profile."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.timotion_ahf import (
    STATUS_READINESS_TIMEOUT_SECONDS,
    TiMOTIONAhfCommands,
    TiMOTIONAhfController,
    build_timotion_ahf_command,
)
from custom_components.adjustable_bed.button import (
    ControllerActionButton,
    _button_entities_for,
    _massage_entities_enabled,
)
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.config_flow import _show_profile_fields
from custom_components.adjustable_bed.const import (
    BED_TYPE_TIMOTION_AHF,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SIDE_BOTH,
    TIMOTION_AHF_NOTIFY_CHAR_UUID,
    TIMOTION_AHF_SERVICE_UUID,
    TIMOTION_AHF_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.services import async_register_services


def status_frame(
    *,
    lock_mask: int = 0,
    lamp_code: int = 1,
    unchecked: int = 0xA5,
    opaque: bytes = bytes(range(10)),
    marker: int = 0x9D,
) -> bytes:
    """Build an RX test frame with its app-defined checksum."""
    assert len(opaque) == 10
    frame = bytearray((marker, unchecked, lock_mask, lamp_code, *opaque, 0))
    frame[14] = sum(frame[2:14]) & 0x7F
    return bytes(frame)


class _Coordinator:
    """Small controller runtime with observable state and STOP scheduling."""

    def __init__(self, client: object | None = None) -> None:
        self.client = client
        self.address = "AA:BB:CC:DD:EE:39"
        self.motor_count = 2
        self.motor_pulse_count = 10
        self.motor_pulse_delay_ms = 100
        self._cancel_command = asyncio.Event()
        self.cancel_command = self._cancel_command
        self.state: dict[str, object] = {}
        self.state_callbacks: list[Callable[[dict[str, object]], None]] = []
        self.stop_calls = 0
        self.cancel_requests = 0
        self.tasks: list[asyncio.Task[object]] = []
        self.hass = SimpleNamespace(async_create_task=self._create_task)

    def _create_task(self, coro, *, name: str | None = None):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task

    def handle_controller_state_updates(self, updates: dict[str, object]) -> None:
        self.state.update(updates)
        for callback_fn in tuple(self.state_callbacks):
            callback_fn(self.state)

    def register_controller_state_callback(self, callback_fn):
        self.state_callbacks.append(callback_fn)

        def unregister() -> None:
            self.state_callbacks.remove(callback_fn)

        return unregister

    def request_command_cancel(self) -> None:
        self.cancel_requests += 1
        self._cancel_command.set()

    async def async_stop_command(self) -> None:
        self.stop_calls += 1


class _GattClient:
    """Client stub for status lifecycle and discovered write-property tests."""

    def __init__(self, status: bytes | Exception | None = None) -> None:
        self.is_connected = True
        self.notify_callbacks: dict[str, Callable[..., None]] = {}
        self.start_notify = AsyncMock(side_effect=self._start_notify)
        self.stop_notify = AsyncMock()
        self.read_gatt_char = AsyncMock(side_effect=self._read_status(status))
        self.services = MagicMock()
        self.service = SimpleNamespace(characteristics=[])
        self.services.get_service.return_value = self.service
        self.services.__iter__ = lambda _self: iter([])

    def _start_notify(self, char_uuid: str, callback) -> None:
        self.notify_callbacks[char_uuid] = callback

    @staticmethod
    def _read_status(status: bytes | Exception | None):
        async def read(_char_uuid: str) -> bytes:
            if isinstance(status, Exception):
                raise status
            if status is None:
                raise BleakError("status read unavailable")
            return status

        return read


def controller_for(
    *,
    client: _GattClient | None = None,
    runtime: _Coordinator | None = None,
) -> tuple[TiMOTIONAhfController, _Coordinator]:
    """Build a controller on a minimal runtime without opening a BLE connection."""
    coordinator = runtime or _Coordinator(client)
    if client is not None:
        coordinator.client = client
    return TiMOTIONAhfController(coordinator), coordinator


@pytest.fixture
def ahf_coordinator(
    hass: HomeAssistant,
    mock_coordinator_connected,
    mock_bleak_client: MagicMock,
):
    """Connect with angle sensing disabled and a valid app status read."""
    mock_bleak_client.read_gatt_char.side_effect = None
    mock_bleak_client.read_gatt_char.return_value = status_frame()
    mock_bleak_client.services.get_service.return_value = SimpleNamespace(
        characteristics=[
            SimpleNamespace(
                uuid=TIMOTION_AHF_WRITE_CHAR_UUID,
                properties=["write", "write-without-response"],
            )
        ]
    )

    async def create(address: str, entry_id: str):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="AHF Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: "AHF Test Bed",
                CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    return create


def test_controller_declares_app_labels_without_physical_axes() -> None:
    controller, _ = controller_for()

    assert controller.control_characteristic_uuid == TIMOTION_AHF_WRITE_CHAR_UUID
    assert controller.requires_notification_channel
    assert controller.held_control_options == (
        "control_1_up",
        "control_1_down",
        "control_2_up",
        "control_2_down",
        "control_3_up",
        "control_3_down",
        "control_4_up",
        "control_4_down",
        "control_5_up",
        "control_5_down",
        "night",
        "light",
        "chair",
    )
    assert [spec.name for spec in controller.controller_button_specs] == [
        "Control 1 Up",
        "Control 1 Down",
        "Control 2 Up",
        "Control 2 Down",
        "Control 3 Up",
        "Control 3 Down",
        "Control 4 Up",
        "Control 4 Down",
        "Control 5 Up",
        "Control 5 Down",
        "Night",
        "Light",
        "Chair",
    ]
    assert all(spec.key.startswith("timotion_ahf_") for spec in controller.controller_button_specs)
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert controller.position_number_specs == ()
    assert controller.supports_motor_control
    assert not controller.has_pillow_support
    assert not controller.supports_memory_presets
    assert not controller.supports_memory_programming
    assert not controller.supports_massage
    assert controller.supports_light_toggle_control
    assert controller.supports_stop_all
    assert not supports_single_address_pairing(BED_TYPE_TIMOTION_AHF)


async def test_status_channel_stays_required_when_angle_sensing_is_disabled(
    ahf_coordinator,
    mock_bleak_client: MagicMock,
) -> None:
    coordinator = await ahf_coordinator("AA:BB:CC:DD:EE:39", "ahf_status_angle_disabled")

    assert coordinator.disable_angle_sensing
    assert coordinator.controller.status_ready
    mock_bleak_client.start_notify.assert_awaited_once()
    assert mock_bleak_client.start_notify.await_args.args[0] == TIMOTION_AHF_NOTIFY_CHAR_UUID
    mock_bleak_client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("lock_mask", [0, 0x01])
async def test_idle_disconnected_hold_reconnects_then_checks_current_status(
    hass: HomeAssistant,
    ahf_coordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    lock_mask: int,
) -> None:
    coordinator = await ahf_coordinator("AA:BB:CC:DD:EE:3B", f"ahf_idle_reconnect_{lock_mask}")
    original_controller = coordinator.controller
    assert original_controller is not None
    coordinator.cache_capability_controller()
    action_spec = next(
        spec
        for spec in original_controller.controller_button_specs
        if spec.key == "timotion_ahf_control_1_up"
    )
    action_button = ControllerActionButton(coordinator, action_spec)

    await coordinator.async_disconnect("idle_timeout", serialize_with_commands=True)

    assert not coordinator.is_connected
    assert action_button.available
    coordinator.capability_controller.validate_hold_control("control_1_up", 450)

    clock = {"now": 0.0}
    monkeypatch.setattr(
        TiMOTIONAhfController,
        "_monotonic",
        lambda _controller: clock["now"],
    )

    async def controlled_sleep(_controller, seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(TiMOTIONAhfController, "_sleep", controlled_sleep)
    neutral = build_timotion_ahf_command()
    action = build_timotion_ahf_command(0x01, 0)
    action_cancel_events: list[asyncio.Event] = []
    stop_cancel_events: list[asyncio.Event] = []
    written: list[bytes] = []

    async def write_gatt(
        controller: TiMOTIONAhfController,
        _char_uuid: str,
        command: bytes,
        **kwargs: object,
    ) -> None:
        event = kwargs["cancel_event"]
        assert isinstance(event, asyncio.Event)
        written.append(command)
        if command == neutral:
            stop_cancel_events.append(event)
            return

        context = current_command_context()
        assert context is not None
        assert event is context.cancel_event
        assert event is coordinator.cancel_command
        assert event is not coordinator._cancel_command
        assert not event.is_set()
        action_cancel_events.append(event)

    monkeypatch.setattr(TiMOTIONAhfController, "_write_gatt_with_retry", write_gatt)
    mock_bleak_client.read_gatt_char.return_value = status_frame(lock_mask=lock_mask)
    await async_register_services(hass)

    call_data = {
        "device_id": "ahf",
        "control": "control_1_up",
        "duration": 0.45,
    }
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        if lock_mask:
            with pytest.raises(ValueError, match="disabled by status lock bit 0"):
                await hass.services.async_call(DOMAIN, "hold_control", call_data, blocking=True)
        else:
            await hass.services.async_call(DOMAIN, "hold_control", call_data, blocking=True)

    assert coordinator.is_connected
    assert coordinator.controller is not original_controller
    assert coordinator.controller.status_ready
    assert coordinator.controller._feature_mask == lock_mask
    assert action_button.available is (lock_mask == 0)
    if lock_mask:
        assert action_cancel_events == []
        assert written == []
        assert stop_cancel_events == []
    else:
        assert action_cancel_events
        assert len(set(map(id, action_cancel_events))) == 1
        assert len(stop_cancel_events) == 3
        assert all(event is not action_cancel_events[0] for event in stop_cancel_events)
        assert written.count(action) >= 1
        assert written[-3:] == [neutral, neutral, neutral]


@pytest.mark.parametrize(
    ("key", "packet", "lock_bit"),
    [
        ("control_1_up", "ddddff0101000000000000", 0),
        ("control_1_down", "ddddff0202000000000000", 0),
        ("control_2_up", "ddddff0404000000000000", 1),
        ("control_2_down", "ddddff0808000000000000", 1),
        ("control_3_up", "ddddff1010000000000000", 2),
        ("control_3_down", "ddddff2020000000000000", 2),
        ("control_4_up", "ddddff0000010100000000", 3),
        ("control_4_down", "ddddff0000020200000000", 3),
        ("control_5_up", "ddddff0000040400000000", 4),
        ("control_5_down", "ddddff0000080800000000", 4),
        ("night", "ddddff0000101000000000", 5),
        ("light", "ddddff0000202000000000", None),
        ("chair", "ddddff0000404000000000", 6),
    ],
)
async def test_app_action_vectors_and_finite_button_pulse(
    key: str,
    packet: str,
    lock_bit: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every app label dispatches its exact vector through a finite pulse."""
    controller, _ = controller_for()
    controller._status_ready = True
    controller._feature_mask = 0
    writes: list[tuple[bytes, dict[str, object]]] = []

    async def write(command: bytes, **kwargs: object) -> None:
        writes.append((command, kwargs))

    monkeypatch.setattr(controller, "write_command", write)
    stop = AsyncMock()
    monkeypatch.setattr(controller, "_send_stop", stop)

    spec = next(
        spec for spec in controller.controller_button_specs if spec.key == f"timotion_ahf_{key}"
    )
    action = next(action for action in controller.held_control_options if action == key)
    assert action == key
    await spec.press_fn(controller)

    assert writes == [
        (
            bytes.fromhex(packet),
            {"repeat_count": 10, "repeat_delay_ms": 100},
        )
    ]
    stop.assert_awaited_once()
    assert lock_bit is None or key in controller.held_control_options


def test_command_builder_is_immutable_neutral_based_and_eleven_bytes() -> None:
    packet = build_timotion_ahf_command(group1=TiMOTIONAhfCommands.CONTROL_2_UP)

    assert packet == bytes.fromhex("ddddff0404000000000000")
    assert len(packet) == 11


@pytest.mark.parametrize(
    ("properties", "expected_response"),
    [
        (["write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], True),
    ],
)
async def test_write_mode_uses_only_supported_gatt_properties(
    properties: list[str], expected_response: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _GattClient(status_frame())
    characteristic = SimpleNamespace(uuid=TIMOTION_AHF_WRITE_CHAR_UUID, properties=properties)
    client.service.characteristics = [characteristic]
    controller, _ = controller_for(client=client)
    write = AsyncMock()
    monkeypatch.setattr(controller, "_write_gatt_with_retry", write)

    await controller.write_command(b"action")

    client.services.get_service.assert_called_once_with(TIMOTION_AHF_SERVICE_UUID)
    assert write.await_args.kwargs["response"] is expected_response


async def test_write_mode_rejects_a_characteristic_without_write_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _GattClient(status_frame())
    client.service.characteristics = [
        SimpleNamespace(uuid=TIMOTION_AHF_WRITE_CHAR_UUID, properties=["read", "notify"])
    ]
    controller, _ = controller_for(client=client)
    write = AsyncMock()
    monkeypatch.setattr(controller, "_write_gatt_with_retry", write)

    with pytest.raises(BleakError, match="supports neither"):
        await controller.write_command(b"action")
    write.assert_not_awaited()


@pytest.mark.parametrize("missing", ["service", "characteristic"])
async def test_write_mode_rejects_missing_discovered_service_or_characteristic(
    missing: str,
) -> None:
    client = _GattClient(status_frame())
    if missing == "service":
        client.services.get_service.return_value = None
    else:
        client.service.characteristics = []
    controller, _ = controller_for(client=client)

    with pytest.raises(BleakError, match="was not discovered"):
        controller._refresh_write_mode()


@pytest.mark.parametrize(
    "frame",
    [
        status_frame()[:-1],
        status_frame(marker=0x00),
        status_frame()[:-1] + bytes([status_frame()[-1] ^ 1]),
    ],
)
def test_status_parser_rejects_wrong_size_marker_or_checksum(frame: bytes) -> None:
    controller, _ = controller_for()

    assert not controller._is_valid_notification(frame)
    controller._process_status_frame(frame)
    assert not controller.status_ready


def test_status_parser_accepts_unchecked_and_uninterpreted_fields() -> None:
    controller, runtime = controller_for()
    frame = status_frame(
        lock_mask=0xA5,
        lamp_code=0xE7,
        unchecked=0x00,
        opaque=bytes(range(10, 20)),
    )

    assert controller._is_valid_notification(frame)
    controller._process_status_frame(frame)

    assert controller.status_ready
    assert runtime.state["timotion_ahf_lock_mask"] == 0xA5
    assert runtime.state["timotion_ahf_lamp_display_code"] == 0xE7
    assert runtime.state["timotion_ahf_status"] == "ready"
    assert {spec.key for spec in controller.controller_state_sensor_specs} == {
        "timotion_ahf_status",
        "timotion_ahf_lock_mask",
        "timotion_ahf_lamp_display_code",
    }


async def test_status_notify_and_initial_read_establish_session_readiness() -> None:
    client = _GattClient(status_frame(lock_mask=0x40, lamp_code=0x91))
    controller, _ = controller_for(client=client)

    await controller.start_notify()

    assert client.start_notify.await_count == 1
    assert client.start_notify.await_args.args[0] == TIMOTION_AHF_NOTIFY_CHAR_UUID
    assert client.read_gatt_char.await_count == 1
    assert controller.status_ready
    assert controller.controller_button_available("timotion_ahf_chair") is False
    assert controller.controller_button_available("timotion_ahf_light") is True


async def test_duplicate_notification_frame_establishes_readiness() -> None:
    client = _GattClient(BleakError("initial read failed"))
    controller, _ = controller_for(client=client)

    async def read_and_notify(_char_uuid: str) -> bytes:
        callback = client.notify_callbacks[TIMOTION_AHF_NOTIFY_CHAR_UUID]
        callback(MagicMock(), bytearray(status_frame()))
        raise BleakError("initial read failed")

    client.read_gatt_char.side_effect = read_and_notify
    await controller.start_notify()

    assert client.start_notify.await_count == 1
    assert controller.status_ready
    callback = client.notify_callbacks[TIMOTION_AHF_NOTIFY_CHAR_UUID]
    callback(MagicMock(), bytearray(status_frame()))
    assert controller.status_ready


async def test_valid_initial_read_establishes_readiness_after_notify_failure() -> None:
    client = _GattClient(status_frame(lock_mask=2))
    client.start_notify.side_effect = BleakError("subscribe failed")
    controller, _ = controller_for(client=client)

    await controller.start_notify()

    assert controller.status_ready
    assert controller._notify_error is None


async def test_read_and_notify_failure_stay_unready_until_eight_second_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _GattClient(BleakError("read failed"))
    client.start_notify.side_effect = BleakError("notify failed")
    controller, _ = controller_for(client=client)
    requested_timeouts: list[float] = []
    now = 0.0
    monkeypatch.setattr(controller, "_monotonic", lambda: now)
    original_wait_for = asyncio.wait_for

    async def expire(awaitable, *, timeout: float):
        nonlocal now
        requested_timeouts.append(timeout)
        if len(requested_timeouts) == 1:
            try:
                return await original_wait_for(awaitable, timeout=timeout)
            finally:
                now = 3.0
        assert isinstance(awaitable, asyncio.Task)
        now += timeout
        raise TimeoutError

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.timotion_ahf.asyncio.wait_for", expire
    )

    await controller.start_notify()

    assert requested_timeouts == [8.0, 5.0]
    assert now == 8.0
    assert not controller.status_ready
    assert controller._status_state == "timed_out"
    assert "within 8 seconds" in (controller._status_error or "")
    assert "read failed" in (controller._status_error or "")
    assert controller.controller_button_available("timotion_ahf_control_1_up") is False


async def test_status_deadline_includes_a_stalled_notification_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _GattClient()
    controller, _ = controller_for(client=client)
    start_entered = asyncio.Event()
    now = 0.0

    async def stalled_subscribe(_char_uuid: str, _callback) -> None:
        start_entered.set()
        await asyncio.Future()

    client.start_notify.side_effect = stalled_subscribe
    monkeypatch.setattr(controller, "_monotonic", lambda: now)

    async def expire_subscription(awaitable, *, timeout: float):
        nonlocal now
        assert timeout == STATUS_READINESS_TIMEOUT_SECONDS
        task = asyncio.create_task(awaitable)
        await asyncio.sleep(0)
        assert start_entered.is_set()
        now += timeout
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise TimeoutError

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.timotion_ahf.asyncio.wait_for",
        expire_subscription,
    )

    await controller.start_notify()

    assert now == STATUS_READINESS_TIMEOUT_SECONDS
    assert client.read_gatt_char.await_count == 0
    assert controller._status_state == "timed_out"
    assert "subscription timed out" in (controller._status_error or "")


@pytest.mark.parametrize("notify_before_deadline", [False, True])
async def test_status_deadline_covers_pending_read_and_notification_can_win(
    monkeypatch: pytest.MonkeyPatch,
    notify_before_deadline: bool,
) -> None:
    client = _GattClient()
    controller, _ = controller_for(client=client)
    read_entered = asyncio.Event()
    now = 0.0
    wait_timeouts: list[float] = []

    async def subscribe(char_uuid: str, notify_callback) -> None:
        client.notify_callbacks[char_uuid] = notify_callback
        nonlocal now
        now += 3.0

    async def stalled_read(_char_uuid: str) -> bytes:
        read_entered.set()
        await asyncio.Future()
        raise AssertionError("unreachable")

    client.start_notify.side_effect = subscribe
    client.read_gatt_char.side_effect = stalled_read
    monkeypatch.setattr(controller, "_monotonic", lambda: now)

    async def controlled_wait(awaitables, *, timeout: float, return_when: int):
        nonlocal now
        wait_timeouts.append(timeout)
        assert timeout == pytest.approx(5.0)
        assert return_when == asyncio.FIRST_COMPLETED
        read_task, status_task = awaitables
        await asyncio.sleep(0)
        assert read_entered.is_set()
        if notify_before_deadline:
            client.notify_callbacks[TIMOTION_AHF_NOTIFY_CHAR_UUID](
                MagicMock(), bytearray(status_frame(lock_mask=0x12, lamp_code=0xE7))
            )
            await asyncio.sleep(0)
            return {status_task}, {read_task}
        now += timeout
        return set(), set(awaitables)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.timotion_ahf.asyncio.wait",
        controlled_wait,
    )

    await controller.start_notify()

    assert wait_timeouts == [5.0]
    if notify_before_deadline:
        assert controller.status_ready
        assert controller._feature_mask == 0x12
        assert controller._lamp_display_code == 0xE7
    else:
        assert now == STATUS_READINESS_TIMEOUT_SECONDS
        assert not controller.status_ready
        assert controller._status_state == "timed_out"


async def test_failed_status_can_become_ready_from_a_later_valid_notification() -> None:
    client = _GattClient(BleakError("read failed"))
    controller, _ = controller_for(client=client)

    async def read_and_notify(_char_uuid: str) -> bytes:
        callback = client.notify_callbacks[TIMOTION_AHF_NOTIFY_CHAR_UUID]
        callback(MagicMock(), bytearray(status_frame(lock_mask=3)))
        raise BleakError("read failed")

    client.read_gatt_char.side_effect = read_and_notify

    await controller.start_notify()

    assert controller.status_ready
    assert controller._feature_mask == 3


async def test_disconnect_resets_readiness_and_rejects_stale_notification() -> None:
    client = _GattClient(status_frame())
    controller, _ = controller_for(client=client)
    await controller.start_notify()
    old_callback = client.notify_callbacks[TIMOTION_AHF_NOTIFY_CHAR_UUID]

    controller.on_disconnect()
    old_callback(MagicMock(), bytearray(status_frame(lock_mask=1)))

    assert not controller.status_ready
    assert controller._feature_mask is None
    assert controller._lamp_display_code is None


async def test_same_valid_status_frame_establishes_readiness_in_reconnected_session() -> None:
    repeated_frame = status_frame(lock_mask=0x12, lamp_code=0xE7)
    client = _GattClient(repeated_frame)
    controller, _ = controller_for(client=client)
    await controller.start_notify()
    assert controller.status_ready

    controller.on_disconnect()
    assert not controller.status_ready
    await controller.start_notify()

    assert controller.status_ready
    assert controller._feature_mask == 0x12
    assert controller._lamp_display_code == 0xE7


@pytest.mark.parametrize(
    ("mask", "disabled"),
    [
        (0x01, {"control_1_up", "control_1_down"}),
        (0x02, {"control_2_up", "control_2_down"}),
        (0x04, {"control_3_up", "control_3_down"}),
        (0x08, {"control_4_up", "control_4_down"}),
        (0x10, {"control_5_up", "control_5_down"}),
        (0x20, {"night"}),
        (0x40, {"chair"}),
        (0x80, set()),
    ],
)
def test_lock_mask_gates_only_app_actions(mask: int, disabled: set[str]) -> None:
    controller, _ = controller_for(client=_GattClient(status_frame()))
    controller._status_ready = True
    controller._lamp_display_code = 1
    controller._process_status_frame(status_frame(lock_mask=mask, lamp_code=1))

    for key in controller.held_control_options:
        assert controller.controller_button_available(f"timotion_ahf_{key}") is (
            key not in disabled
        )
        if key in disabled:
            with pytest.raises(ValueError, match="disabled by status lock bit"):
                controller.validate_hold_control(key, 100)
        else:
            controller.validate_hold_control(key, 100)


def test_hold_control_requires_status_but_stop_never_checks_readiness() -> None:
    controller, _ = controller_for()

    # Service preflight must allow the coordinator to reconnect first.
    controller.validate_hold_control("control_1_up", 100)
    assert controller.controller_button_available("timotion_ahf_control_1_up")

    controller._coordinator.client = SimpleNamespace(is_connected=True)
    with pytest.raises(ValueError, match="valid status frame"):
        controller.validate_hold_control("control_1_up", 100)
    assert not controller.controller_button_available("timotion_ahf_light")
    assert controller.controller_button_available("unknown") is True


async def test_lamp_display_changes_preempt_serialized_stop_but_duplicates_do_not() -> None:
    controller, runtime = controller_for()
    runtime.async_stop_command = AsyncMock()
    other_controller, other_runtime = controller_for()
    other_controller._process_status_frame(status_frame(lamp_code=0))

    controller._process_status_frame(status_frame(lamp_code=0))
    controller._process_status_frame(status_frame(lock_mask=0x80, lamp_code=0))
    assert not runtime.tasks

    controller._process_status_frame(status_frame(lamp_code=0xE2))
    controller._process_status_frame(status_frame(lamp_code=0xE2))
    controller._process_status_frame(status_frame(lamp_code=0xFF))
    await asyncio.gather(*runtime.tasks)

    assert runtime.cancel_requests == 2
    assert runtime.async_stop_command.await_count == 2
    assert runtime.state["timotion_ahf_lamp_display_code"] == 0xFF
    assert other_runtime.cancel_requests == 0


async def test_lamp_change_preempts_active_command_through_its_serialized_lane(
    hass: HomeAssistant,
    ahf_coordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lamp-state STOP cancels and queues on this device without deadlocking."""
    coordinator = await ahf_coordinator("AA:BB:CC:DD:EE:3A", "ahf_lamp_lock_order")
    controller = coordinator.controller
    monkeypatch.setattr(controller, "_sleep", AsyncMock())
    mock_bleak_client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def active_command(_controller: BedController) -> None:
        entered.set()
        await release.wait()

    command_task = hass.async_create_task(
        coordinator.async_execute_controller_command(
            active_command,
            read_positions_after_operation=False,
        )
    )
    await entered.wait()
    controller._process_status_frame(status_frame(lamp_code=2))
    assert coordinator.cancel_command.is_set()
    release.set()
    await command_task
    await hass.async_block_till_done()

    writes = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert writes == [build_timotion_ahf_command()] * 3


async def test_hold_duration_includes_initial_wait_cadence_and_three_stop_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, runtime = controller_for()
    controller._status_ready = True
    controller._feature_mask = 0
    now = 0.0
    timeline: list[tuple[float, bytes, asyncio.Event | None]] = []
    sleeps: list[float] = []
    neutral = build_timotion_ahf_command()

    def monotonic() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    async def write(command: bytes, **kwargs: object) -> None:
        cancel = kwargs.get("cancel_event")
        timeline.append((now, command, cancel if isinstance(cancel, asyncio.Event) else None))

    monkeypatch.setattr(controller, "_monotonic", monotonic)
    monkeypatch.setattr(controller, "_sleep", sleep)
    monkeypatch.setattr(controller, "write_command", write)

    await controller.hold_control("control_1_up", 450)

    action_writes = [(at, cancel) for at, command, cancel in timeline if command != neutral]
    stop_writes = [(at, cancel) for at, command, cancel in timeline if command == neutral]
    assert [at for at, _ in action_writes] == pytest.approx([0.1, 0.2, 0.3, 0.4])
    assert [at for at, _ in stop_writes] == pytest.approx([0.45, 0.55, 0.65])
    assert list(sleeps[:5]) == pytest.approx([0.1, 0.1, 0.1, 0.1, 0.05])
    assert len({id(cancel) for _, cancel in stop_writes}) == 1
    assert stop_writes[0][1] is not runtime._cancel_command
    assert all(at <= 0.45 for at, _ in action_writes)
    assert timeline[-1][1] == neutral


async def test_stalled_hold_write_is_cancelled_at_deadline_before_stop_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _ = controller_for()
    controller._status_ready = True
    controller._feature_mask = 0
    now = 0.0
    deadline = 0.25
    action = build_timotion_ahf_command(0x01, 0)
    neutral = build_timotion_ahf_command()
    writes: list[bytes] = []
    action_cancelled = asyncio.Event()
    write_entered = asyncio.Event()
    parent_task: asyncio.Task[object] | None = None

    def monotonic() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    async def write(command: bytes, **_kwargs: object) -> None:
        writes.append(command)
        if command == action:
            write_entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                action_cancelled.set()
                raise

    class ControlledTimeout:
        def __init__(self, duration: float) -> None:
            assert duration == pytest.approx(0.25)
            self._expired = False
            self._timer_task: asyncio.Task[None] | None = None

        async def __aenter__(self):
            nonlocal parent_task
            parent_task = asyncio.current_task()
            self._timer_task = asyncio.create_task(expire_at_write())
            return self

        async def __aexit__(self, exc_type, _exc, _traceback):
            if self._timer_task is not None and not self._timer_task.done():
                self._timer_task.cancel()
                await asyncio.gather(self._timer_task, return_exceptions=True)
            if exc_type is asyncio.CancelledError and self._expired:
                assert parent_task is not None
                parent_task.uncancel()
                raise TimeoutError
            return False

        def expired(self) -> bool:
            return self._expired

    timeout_context: ControlledTimeout | None = None

    async def expire_at_write() -> None:
        nonlocal now
        await write_entered.wait()
        now = deadline
        assert parent_task is not None
        assert timeout_context is not None
        timeout_context._expired = True
        parent_task.cancel()

    monkeypatch.setattr(controller, "_monotonic", monotonic)
    monkeypatch.setattr(controller, "_sleep", sleep)
    monkeypatch.setattr(controller, "write_command", write)
    timeout_context = ControlledTimeout(0.25)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.timotion_ahf.asyncio.timeout",
        lambda _duration: timeout_context,
    )

    await controller.hold_control("control_1_up", 250)

    assert action_cancelled.is_set()
    assert writes == [action, neutral, neutral, neutral]
    assert now > deadline  # The three safety STOP writes remain outside the hold bound.


async def test_hold_cancel_and_action_write_error_both_attempt_neutral_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, runtime = controller_for()
    controller._status_ready = True
    controller._feature_mask = 0
    now = 0.0
    writes: list[bytes] = []
    neutral = build_timotion_ahf_command()
    cancel_during_first_call = True

    def monotonic() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now, cancel_during_first_call
        now += seconds
        if cancel_during_first_call and seconds == 0.1 and now == pytest.approx(0.1):
            runtime._cancel_command.set()
            cancel_during_first_call = False

    async def write(command: bytes, **kwargs: object) -> None:
        del kwargs
        writes.append(command)

    monkeypatch.setattr(controller, "_monotonic", monotonic)
    monkeypatch.setattr(controller, "_sleep", sleep)
    monkeypatch.setattr(controller, "write_command", write)

    await controller.hold_control("light", 500)
    assert writes == [neutral, neutral, neutral]
    assert runtime._cancel_command.is_set()

    runtime._cancel_command.clear()
    writes.clear()
    now = 0.0
    cancel_during_first_call = False

    async def fail_action(command: bytes, **kwargs: object) -> None:
        if command != neutral:
            raise OSError("action write failed")
        writes.append(command)

    monkeypatch.setattr(controller, "write_command", fail_action)
    with pytest.raises(OSError, match="action write failed"):
        await controller.hold_control("light", 500)
    assert writes == [neutral, neutral, neutral]


async def test_stop_uses_three_neutral_writes_and_a_fresh_cancel_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, runtime = controller_for()
    now = 0.0
    writes: list[tuple[float, bytes, asyncio.Event | None]] = []

    def monotonic() -> float:
        return now

    async def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    async def write(command: bytes, **kwargs: object) -> None:
        cancel = kwargs.get("cancel_event")
        writes.append((now, command, cancel if isinstance(cancel, asyncio.Event) else None))

    monkeypatch.setattr(controller, "_monotonic", monotonic)
    monkeypatch.setattr(controller, "_sleep", sleep)
    monkeypatch.setattr(controller, "write_command", write)

    await controller._send_stop()

    assert [at for at, _, _ in writes] == pytest.approx([0.0, 0.1, 0.2])
    assert [command for _, command, _ in writes] == [build_timotion_ahf_command()] * 3
    assert len({id(cancel) for _, _, cancel in writes}) == 1
    assert writes[0][2] is not runtime._cancel_command


def test_ahf_setup_hides_massage_and_motor_count_only_sizes_legacy_covers() -> None:
    assert hidden_generic_fields(BED_TYPE_TIMOTION_AHF, None) == frozenset({CONF_HAS_MASSAGE})
    schema = {vol_marker(CONF_MOTOR_COUNT): object(), vol_marker(CONF_HAS_MASSAGE): object()}
    _show_profile_fields(schema, BED_TYPE_TIMOTION_AHF, None)
    assert [str(key) for key in schema] == [CONF_MOTOR_COUNT]

    low_runtime = _Coordinator()
    high_runtime = _Coordinator()
    high_runtime.motor_count = 5
    low, _ = controller_for(runtime=low_runtime)
    high, _ = controller_for(runtime=high_runtime)
    assert [(spec.key, spec.name) for spec in low.controller_button_specs] == [
        (spec.key, spec.name) for spec in high.controller_button_specs
    ]
    assert [spec.key for spec in low.motor_control_specs] == ["back", "legs"]
    assert [spec.key for spec in high.motor_control_specs] == [
        "back",
        "legs",
        "head",
        "feet",
        "pillow",
    ]


def vol_marker(key: str):
    """Make the same required marker shape used by config-flow schema helpers."""
    import voluptuous as vol

    return vol.Optional(key)


async def test_legacy_ahf_entities_keep_their_ids_and_send_app_actions(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="AHF migration test",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:39",
            CONF_NAME: "AHF",
            CONF_BED_TYPE: BED_TYPE_TIMOTION_AHF,
            CONF_MOTOR_COUNT: 5,
            CONF_HAS_MASSAGE: True,
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    legacy_covers = [
        registry.async_get_or_create("cover", DOMAIN, f"bed_{key}", config_entry=entry)
        for key in ("back", "legs", "head", "feet", "pillow")
    ]
    legacy_light = registry.async_get_or_create(
        "light", DOMAIN, "bed_under_bed_lights_assumed", config_entry=entry
    )
    legacy_toggle = registry.async_get_or_create(
        "button", DOMAIN, "bed_toggle_light", config_entry=entry
    )
    stale_named_action = registry.async_get_or_create(
        "button", DOMAIN, "bed_timotion_ahf_old_axis", config_entry=entry
    )
    unrelated_action = registry.async_get_or_create(
        "button", DOMAIN, "bed_other_app_action", config_entry=entry
    )
    controller_runtime = _Coordinator()
    controller_runtime.motor_count = 5
    controller, _ = controller_for(runtime=controller_runtime)
    runtime = SimpleNamespace(
        controller=None,
        capability_controller=controller,
        entry=entry,
        bed_type=BED_TYPE_TIMOTION_AHF,
        has_massage=True,
        name="AHF",
        device_info={},
        entity_side=None,
        entity_unique_id=lambda key: f"bed_{key}",
        entity_translation_key=lambda key: key,
    )

    covers = _cover_entities_for(hass, runtime)
    assert not _massage_entities_enabled(runtime, controller)
    buttons = _button_entities_for(hass, runtime)
    lights = _light_entities_for(hass, runtime)
    actions = [button for button in buttons if button.unique_id.startswith("bed_timotion_ahf_")]
    stop_button = next(button for button in buttons if button.unique_id == "bed_stop")
    toggle_button = next(button for button in buttons if button.unique_id == "bed_toggle_light")

    assert [cover.unique_id for cover in covers] == [row.unique_id for row in legacy_covers]
    assert len(actions) == 13
    assert stop_button.available
    assert [light.unique_id for light in lights] == [legacy_light.unique_id]
    assert all(registry.async_get(row.entity_id) is not None for row in legacy_covers)
    assert registry.async_get(legacy_light.entity_id) is not None
    assert registry.async_get(legacy_toggle.entity_id) is not None
    assert registry.async_get(stale_named_action.entity_id) is None
    assert registry.async_get(unrelated_action.entity_id) is not None

    writes: list[bytes] = []

    async def write(command: bytes, **_kwargs: object) -> None:
        writes.append(command)

    stop = AsyncMock()
    monkeypatch.setattr(controller, "write_command", write)
    monkeypatch.setattr(controller, "_send_stop", stop)

    # Legacy entities pass the same status gate as the app buttons.
    with pytest.raises(HomeAssistantError):
        await toggle_button.entity_description.press_fn(controller)
    assert writes == []

    controller._status_ready = True
    controller._feature_mask = 0
    for cover in covers:
        await cover.entity_description.open_fn(controller)
    await toggle_button.entity_description.press_fn(controller)
    assert writes == [
        build_timotion_ahf_command(group1=0x01),
        build_timotion_ahf_command(group1=0x04),
        build_timotion_ahf_command(group1=0x10),
        build_timotion_ahf_command(group2=0x01),
        build_timotion_ahf_command(group2=0x04),
        build_timotion_ahf_command(group2=0x20),
    ]
    assert stop.await_count == 6
