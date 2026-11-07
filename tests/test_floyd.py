"""Artifact vectors from accepted Floyd 1.0.7 report E3-E17, no hardware claims."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.floyd import FloydController
from custom_components.adjustable_bed.const import (
    BED_TYPE_KAIDI,
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_ROOM_ID,
    KAIDI_NOTIFY_CHAR_UUID,
    KAIDI_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profiles.kaidi import resolve_kaidi_variant


@pytest.fixture
def floyd(mock_bleak_client: MagicMock) -> FloydController:
    coordinator = SimpleNamespace(
        client=mock_bleak_client, cancel_command=asyncio.Event(),
        address="AA:BB:CC:DD:EE:FF", motor_count=4, motor_pulse_count=1,
        motor_pulse_delay_ms=1, has_massage=True,
        entry=SimpleNamespace(data={CONF_KAIDI_ROOM_ID: 0x12345678, CONF_KAIDI_PRODUCT_ID: 139}),
        record_command_trace=MagicMock(), handle_controller_state_update=MagicMock(),
        controller_state={},
    )
    controller = FloydController(coordinator)
    controller._session_ready = True
    controller._own_vaddr = 0x01020304
    controller._target_vaddr = 0x12345678
    # Queue pacing is tested independently, never wait on protocol timers here.
    original_send = controller._send

    async def send(packet: bytes, cancel_event: asyncio.Event | None = None) -> None:
        controller._next_write_at = 0
        await original_send(packet, cancel_event)

    controller._send = send
    return controller


def writes(controller: FloydController) -> list[bytes]:
    return [call.args[1] for call in controller.client.write_gatt_char.call_args_list]


def notify(controller: FloydController, value: str) -> None:
    controller._handle_notification(MagicMock(), bytearray.fromhex(value))


def test_profile_selection_and_capability_boundaries(floyd: FloydController) -> None:
    assert resolve_kaidi_variant("auto", product_id=139).variant == "floyd"
    assert resolve_kaidi_variant("seat_2", product_id=139).variant == "seat_2"
    assert "Floyd Home app (Kaidi product 139)" in [option["label"] for option in get_bed_type_options()]
    assert floyd.supports_lights and floyd.supports_discrete_light_control
    assert floyd.memory_slot_count == 3
    assert not floyd.supports_direct_position_control
    assert not floyd.position_number_specs
    assert not floyd.supports_single_address_pairing
    assert not floyd.supports_massage
    assert not floyd.supports_massage_timer
    assert not floyd.has_lumbar_support
    assert [spec.key for spec in floyd.motor_control_specs] == ["back", "legs"]
    assert floyd.controller_state_binary_sensor_specs[0].state_key == "floyd_battery_mode"


@pytest.mark.parametrize(("method", "args", "opcode"), [
    ("preset_flat", (), 0x1C), ("preset_zero_g", (), 0x62),
    ("preset_anti_snore", (), 0x65),
    ("preset_memory", (1,), 0x29), ("preset_memory", (2,), 0x2A),
    ("preset_memory", (3,), 0x2B),
    ("program_memory", (1,), 0x25), ("program_memory", (2,), 0x26),
    ("program_memory", (3,), 0x27),
    ("lights_on", (), 0x5C), ("lights_off", (), 0x5D),
    ("stop_all", (), 9), ("move_head_stop", (), 3), ("move_legs_stop", (), 6),
])
async def test_normal_command_vectors(floyd: FloydController, method: str, args: tuple, opcode: int) -> None:
    await getattr(floyd, method)(*args)
    assert writes(floyd) == [bytes.fromhex("0378563412200403020101") + bytes((opcode, 0, 0))]
    assert floyd.client.write_gatt_char.call_args.args[0] == KAIDI_WRITE_CHAR_UUID


@pytest.mark.parametrize(("selector", "opcodes"), [
    ("first", (0x62, 0x1C, 0x65, 0x29, 0x2A, 0x2B)),
    ("both", (0x64, 0x1E, 0x67, 0x39, 0x3A, 0x3B)),
    ("second", (0x63, 0x1D, 0x66, 0x31, 0x32, 0x33)),
])
async def test_all_exported_alarm_selectors(floyd: FloydController, selector: str, opcodes: tuple[int, ...]) -> None:
    for action in ("zero_g", "flat", "anti_snore", "memory_1", "memory_2", "memory_3"):
        await floyd.floyd_action(action, selector, False, None)
    assert [p[11] for p in writes(floyd)] == list(opcodes)


@pytest.mark.parametrize(("action", "parameter"), [("save_zero_g", 1), ("save_anti_snore", 4)])
async def test_confirmed_overwrite_retains_parameter(floyd: FloydController, action: str, parameter: int) -> None:
    with pytest.raises(ValueError, match="confirm"):
        await floyd.floyd_action(action, "first", False, None)
    assert not writes(floyd)
    await floyd.floyd_action(action, "first", True, None)
    await floyd.preset_flat()
    assert [(p[11], p[12]) for p in writes(floyd)] == [(0xA7, parameter), (0x1C, parameter)]
    with pytest.raises(ValueError):
        await floyd.program_memory(4)


@pytest.mark.parametrize(("control", "move", "release"), [
    ("head_up", 1, 3), ("head_down", 2, 3),
    ("feet_up", 4, 6), ("feet_down", 5, 6),
    ("head_feet_up", 7, 9), ("head_feet_down", 8, 9),
])
async def test_start_once_then_release(floyd: FloydController, control: str, move: int, release: int) -> None:
    await floyd.hold_control(control, 1)
    assert [p[11] for p in writes(floyd)] == [move, release]


async def test_cancel_and_write_failure_still_release(floyd: FloydController) -> None:
    floyd._coordinator.cancel_command.set()
    await floyd.hold_control("head_up", 30000)
    assert [p[11] for p in writes(floyd)] == [3]
    floyd._coordinator.cancel_command.clear()
    floyd.client.write_gatt_char.reset_mock()
    task = asyncio.create_task(floyd.hold_control("feet_up", 30000))
    while not writes(floyd):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [p[11] for p in writes(floyd)] == [4, 6]
    floyd.client.write_gatt_char.reset_mock()
    floyd._write_gatt_with_retry = AsyncMock(side_effect=[RuntimeError("write failed"), None])
    with pytest.raises(RuntimeError, match="write failed"):
        await floyd.hold_control("head_feet_down", 1)
    assert [call.args[1][11] for call in floyd._write_gatt_with_retry.call_args_list] == [8, 9]


async def test_battery_event_gates_up_but_never_release(floyd: FloydController) -> None:
    notify(floyd, "0300000000200403020101a60100")
    assert floyd._battery_mode is True
    floyd._coordinator.handle_controller_state_update.assert_called_with("floyd_battery_mode", True)
    with pytest.raises(ValueError, match="battery"):
        await floyd.hold_control("head_feet_up", 1)
    await floyd.hold_control("head_down", 1)
    await floyd.stop_all()
    assert [p[11] for p in writes(floyd)] == [2, 3, 9]
    notify(floyd, "0300000000200403020101a60000")
    assert floyd._battery_mode is False


async def test_authentication_ping_identity_and_zero_target(floyd: FloydController) -> None:
    floyd.on_disconnect()
    packets: list[bytes] = []

    async def send(packet: bytes, cancel_event=None) -> None:
        packets.append(packet)
        if packet[:2] == b"\x01\x16":
            notify(floyd, "010a00000000")
            notify(floyd, "021600")
        elif packet[5] == 0xFE:
            notify(floyd, "0300000000ff00112233445501000000")  # other node
            assert floyd._target_vaddr is None
            notify(floyd, "0300000000ffffeeddccbbaa00000000")

    floyd._send = send
    await floyd.preset_flat()
    assert packets == [
        bytes.fromhex("0116017856341231313232"),
        bytes.fromhex("03fffffffffeffffffff"),
        bytes.fromhex("030000000020ffffffff011c0000"),
    ]
    assert floyd._target_vaddr == -2
    notify(floyd, "01020000000000000100")
    assert floyd._target_vaddr is None and not floyd._session_ready


async def test_auth_failure_and_offline_target_never_write_controls(floyd: FloydController) -> None:
    floyd._session_ready = False

    async def reject(packet: bytes, cancel_event=None) -> None:
        notify(floyd, "021601")

    floyd._send = reject
    with pytest.raises(ValueError, match="rejected"):
        await floyd.preset_flat()
    assert not writes(floyd)
    floyd._target_vaddr = 0
    with pytest.raises(RuntimeError, match="live ping"):
        floyd._build_control_packet(1)


async def test_assignment_and_confirmation_vectors(floyd: FloydController) -> None:
    floyd._room_id = 0
    floyd._manufacturer_data = {0xFFFF: bytes.fromhex("c0ff01000000008b010000000000000000")}
    floyd._ensure_notify_started = AsyncMock()

    async def assign(packet: bytes, cancel_event=None) -> None:
        assert packet == bytes.fromhex("0103785634123131323200000000")
        notify(floyd, "020300")

    floyd._send = assign
    await floyd.floyd_action("assign_room", "first", True, 0x12345678)
    assert floyd._room_id == 0x12345678 and not floyd._session_ready
    with pytest.raises(ValueError, match="unassigned"):
        await floyd.floyd_action("assign_room", "first", True, 1)
    floyd._session_ready = True
    floyd._target_vaddr = 1
    floyd._send = AsyncMock()
    await floyd.floyd_action("confirm_add", "first", True, None)
    assert floyd._send.call_args.args[0][11] == 0x45


@pytest.mark.parametrize("packet", ["", "01", "010a", "010a00", "0102", "0216", "0203", "030000000020", "0300000000ff0000", "0300000000200000000001a601"])
def test_malformed_notifications_are_ignored(floyd: FloydController, packet: str) -> None:
    notify(floyd, packet)
    assert floyd._target_vaddr == 0x12345678
    assert floyd._battery_mode is None


async def test_queue_spacing(floyd: FloydController) -> None:
    floyd._next_write_at = 100.04
    with patch("custom_components.adjustable_bed.beds.floyd.time.monotonic", return_value=100), patch(
        "custom_components.adjustable_bed.beds.floyd.asyncio.sleep", new_callable=AsyncMock,
    ) as sleep:
        await FloydController._send(floyd, b"\x00")
    assert sleep.call_args.args[0] == pytest.approx(0.04)


async def test_factory_selects_floyd_from_advertisement(hass, mock_bleak_client) -> None:
    from custom_components.adjustable_bed.controller_factory import create_controller

    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.entry.data = {}
    coordinator.client = mock_bleak_client
    result = await create_controller(
        coordinator, BED_TYPE_KAIDI, protocol_variant="auto", client=mock_bleak_client,
        manufacturer_data={0xFFFF: bytes.fromhex("c0ff01785634128b010000000000000000")},
    )
    assert isinstance(result, FloydController)


async def test_release_uses_started_target_after_topology_change(floyd: FloydController) -> None:
    original_send = floyd._send

    async def send(packet: bytes, cancel_event=None) -> None:
        await original_send(packet, cancel_event)
        if packet[11] == 1:
            notify(floyd, "01020000000000000200")

    floyd._send = send
    await floyd.hold_control("head_up", 1)
    assert [p[11] for p in writes(floyd)] == [1, 3]
    assert all(p[1:5] == bytes.fromhex("78563412") for p in writes(floyd))
    assert not floyd._session_ready


@pytest.mark.parametrize(("payload", "expected"), [
    ("c0ff01785634128b010000000000000000", True),
    ("c0ff01785634128a010000000000000000", False),
    ("c0ff01785634128b061000000000000000", False),
    ("c0ff09000000000000444b00008b0100", True),
    ("c0ff0900000000000000000000008b0100", False),
])
def test_floyd_exact_admission_vectors(payload: str, expected: bool) -> None:
    from custom_components.adjustable_bed.kaidi_protocol import (
        is_floyd_advertisement,
        parse_kaidi_manufacturer_payload,
    )

    assert is_floyd_advertisement(parse_kaidi_manufacturer_payload(bytes.fromhex(payload))) is expected


def test_floyd_discovery_without_shared_name_or_uuid() -> None:
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    info = _make_service_info(
        name="Unlabelled", service_uuids=[],
        manufacturer_data={0xFFFF: bytes.fromhex("c0ff01785634128b010000000000000000")},
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type == BED_TYPE_KAIDI
    assert "product:floyd_139" in result.signals


def service_target(controller: FloydController):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    target = MagicMock(spec=AdjustableBedCoordinator)
    target.name = "Floyd"
    target.bed_type = BED_TYPE_KAIDI
    target.controller_side = None
    target.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    target.async_execute_controller_command = AsyncMock(side_effect=execute)
    return target


async def test_service_validates_all_targets_before_overwrite(hass, floyd: FloydController) -> None:
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    first = service_target(floyd)
    second = service_target(floyd)
    second.controller_side = None
    second.capability_controller = SimpleNamespace(supports_floyd_actions=False, requires_disconnected_transport=False)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
        [(first, "both"), (second, "both")], [],
    )), pytest.raises(ServiceValidationError, match="Floyd Home"):
        await hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": ["one", "two"], "action": "save_zero_g", "confirm": True,
        }, blocking=True)
    assert not writes(floyd)
    first.async_execute_controller_command.assert_not_awaited()


async def test_service_routes_two_address_overwrite_and_conditional_presets(hass, floyd: FloydController) -> None:
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    targets = [service_target(floyd), service_target(floyd)]
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
        [(target, "both") for target in targets], [],
    )):
        await hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": ["one", "two"], "action": "save_anti_snore", "confirm": True,
        }, blocking=True)
        await hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": ["one", "two"], "action": "flat", "internal_side": "second",
        }, blocking=True)
    assert [p[11:13] for p in writes(floyd)] == [b"\xa7\x04", b"\xa7\x04", b"\x1d\x04", b"\x1d\x04"]


async def test_room_service_persists_disconnects_and_confirms(hass, floyd: FloydController) -> None:
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    target = service_target(floyd)
    target.entry = MockConfigEntry(domain=DOMAIN, data={CONF_KAIDI_ROOM_ID: 0})
    target.entry.add_to_hass(hass)
    target.remember_floyd_room.side_effect = lambda room: hass.config_entries.async_update_entry(
        target.entry, data={CONF_KAIDI_ROOM_ID: room},
    )
    floyd._room_id = 0
    floyd._manufacturer_data = {0xFFFF: bytes.fromhex("c0ff01000000008b010000000000000000")}
    events = []

    async def action(name, internal_side, confirm, room_id):
        events.append(name)
        if name == "confirm_add":
            assert target.entry.data[CONF_KAIDI_ROOM_ID] == 0x12345678

    async def disconnect():
        events.append("disconnect")

    floyd.floyd_action = AsyncMock(side_effect=action)
    target.async_disconnect = AsyncMock(side_effect=disconnect)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
        [(target, "both")], [],
    )):
        await hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": "one", "action": "assign_room", "confirm": True, "room_id": 0x12345678,
        }, blocking=True)
    assert events == ["assign_room", "disconnect", "confirm_add"]


async def test_service_hold_uses_bounded_combined_control(hass, floyd: FloydController) -> None:
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    target = service_target(floyd)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
        [(target, "both")], [],
    )):
        await hass.services.async_call(DOMAIN, "hold_control", {
            "device_id": "one", "control": "head_feet_down", "duration": 0.1,
        }, blocking=True)
    assert [p[11] for p in writes(floyd)] == [8, 9]


def test_battery_diagnostic_is_unknown_until_notification(floyd: FloydController) -> None:
    from custom_components.adjustable_bed.binary_sensor import (
        AdjustableBedControllerStateBinarySensor,
    )

    target = MagicMock()
    target.controller_state = {}
    sensor = AdjustableBedControllerStateBinarySensor(target, floyd.controller_state_binary_sensor_specs[0])
    assert sensor.is_on is None
    target.controller_state["floyd_battery_mode"] = True
    assert sensor.is_on is True


@pytest.mark.parametrize(("properties", "response"), [
    (["write"], True), (["write-without-response"], False),
])
async def test_gatt_write_properties_and_subscription(floyd: FloydController, properties: list[str], response: bool) -> None:
    floyd.client.services = [SimpleNamespace(characteristics=[
        SimpleNamespace(uuid=KAIDI_WRITE_CHAR_UUID, properties=properties),
    ])]
    await floyd.start_notify()
    assert floyd._write_with_response is response
    floyd.client.start_notify.assert_awaited_once_with(KAIDI_NOTIFY_CHAR_UUID, floyd._handle_notification)
    await floyd.lights_on()
    assert floyd.client.write_gatt_char.call_args.kwargs["response"] is response


async def test_room_assignment_failure_disconnects_without_persisting(hass, floyd: FloydController) -> None:
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    target = service_target(floyd)
    target.entry = MockConfigEntry(domain=DOMAIN, data={CONF_KAIDI_ROOM_ID: 0})
    target.entry.add_to_hass(hass)
    floyd._room_id = 0
    floyd._manufacturer_data = {0xFFFF: bytes.fromhex("c0ff01000000008b010000000000000000")}
    floyd.floyd_action = AsyncMock(side_effect=ValueError("assignment rejected"))
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
        [(target, "both")], [],
    )), pytest.raises(ServiceValidationError, match="assignment rejected"):
        await hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": "one", "action": "assign_room", "confirm": True, "room_id": 23,
        }, blocking=True)
    assert target.entry.data[CONF_KAIDI_ROOM_ID] == 0
    target.async_disconnect.assert_awaited_once()


def test_retained_parameter_survives_controller_renewal(floyd: FloydController) -> None:
    floyd._coordinator.controller_state = {"floyd_retained_parameter": 4}
    renewed = FloydController(floyd._coordinator)
    assert renewed._parameter == 4


def test_extended_advertisement_and_short_boundary() -> None:
    from custom_components.adjustable_bed.kaidi_protocol import (
        is_floyd_advertisement,
        parse_kaidi_manufacturer_payload,
    )

    full = bytes.fromhex("ffffc0ff02 78563412 ffeeddccbbaa 000000000000 04030201 8b0100")
    parsed = parse_kaidi_manufacturer_payload(full)
    assert parsed.room_id == 0x12345678
    assert parsed.vaddr == 0x01020304
    assert parsed.product_id == 139
    assert parsed.sofa_acu_no == 0x100
    assert is_floyd_advertisement(parsed)
    assert not is_floyd_advertisement(parse_kaidi_manufacturer_payload(full[:-1]))


@pytest.mark.parametrize(("company", "rssi", "expected"), [(0xFFFF, -92, True), (0xFFFF, -93, False), (0x1234, -60, False)])
def test_floyd_discovery_requires_exact_company_and_rssi(company: int, rssi: int, expected: bool) -> None:
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    info = _make_service_info(
        name="Unknown", service_uuids=[],
        manufacturer_data={company: bytes.fromhex("c0ff01785634128b010000000000000000")},
    )
    info.rssi = rssi
    assert (detect_bed_type_detailed(info).bed_type == BED_TYPE_KAIDI) is expected


async def test_acknowledged_room_persistence_suppresses_mid_service_reload(hass) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_KAIDI_TARGET_VADDR,
        DOMAIN,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_KAIDI,
        CONF_KAIDI_ROOM_ID: 0, CONF_KAIDI_TARGET_VADDR: 12,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    coordinator.remember_floyd_room(0x12345678)
    assert entry.data[CONF_KAIDI_ROOM_ID] == 0x12345678
    assert CONF_KAIDI_TARGET_VADDR not in entry.data
    assert coordinator.consume_internal_entry_update(entry)
    assert not coordinator.consume_internal_entry_update(entry)
    # A stale unassigned advertisement cannot undo an acknowledged assignment.
    renewed = FloydController(coordinator, manufacturer_data={
        0xFFFF: bytes.fromhex("c0ff01000000008b010000000000000000"),
    })
    assert renewed._room_id == 0x12345678


async def test_signed_target_domains_differ_for_normal_and_conditional_paths(floyd: FloydController) -> None:
    notify(floyd, "0300000000ffffeeddccbbaafdffffff")
    await floyd.preset_flat()
    assert writes(floyd)[0][1:5] == bytes.fromhex("fdffffff")
    with pytest.raises(ValueError, match="positive target"):
        await floyd.floyd_action("flat", "second", False, None)
    assert len(writes(floyd)) == 1


async def test_preempted_assignment_never_persists_or_confirms(hass, floyd: FloydController) -> None:
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.exceptions import ServiceValidationError
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_KAIDI,
        CONF_KAIDI_ROOM_ID: 0,
    })
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._client = floyd.client
    target._controller = floyd
    floyd._coordinator = target
    floyd._room_id = 0
    floyd._manufacturer_data = {0xFFFF: bytes.fromhex("c0ff01000000008b010000000000000000")}
    sent = asyncio.Event()

    async def write_without_ack(*args, **kwargs):
        sent.set()

    floyd.client.write_gatt_char = AsyncMock(side_effect=write_without_ack)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(target, "both")], [])),
        patch.object(target, "_async_prepare_controller_operation", AsyncMock(return_value=floyd)),
        patch.object(target, "_async_finish_controller_operation", AsyncMock()),
        patch.object(target, "async_disconnect", AsyncMock()) as disconnect,
    ):
        task = asyncio.create_task(hass.services.async_call(DOMAIN, "floyd_action", {
            "device_id": "bed", "action": "assign_room", "confirm": True, "room_id": 123,
        }, blocking=True))
        await asyncio.wait_for(sent.wait(), 1)
        target.request_command_cancel(resource="configuration")
        with pytest.raises(ServiceValidationError, match="cancelled before acknowledgement"):
            await task
        disconnect.assert_awaited_once()
    assert entry.data[CONF_KAIDI_ROOM_ID] == 0
    assert len(writes(floyd)) == 1
    assert writes(floyd)[0][:2] == b"\x01\x03"


async def test_timed_movement_prepares_before_deadline(hass, floyd: FloydController) -> None:
    from custom_components.adjustable_bed.services import _timed_move_plan

    target = service_target(floyd)
    command, *_ = await _timed_move_plan(target, target, [], "back", "up", 100)
    prepared = False
    original_timeout = asyncio.timeout

    async def authenticate():
        nonlocal prepared
        prepared = True

    def movement_deadline(seconds):
        assert prepared, "Session preparation must precede the movement deadline"
        return original_timeout(seconds)

    floyd._ensure_session_ready = AsyncMock(side_effect=authenticate)
    with patch("custom_components.adjustable_bed.services.asyncio.timeout", side_effect=movement_deadline):
        await command(floyd)
    assert writes(floyd)[0][11] == 1
    assert writes(floyd)[-1][11] == 3


async def test_timed_preflight_battery_failure_prevents_every_target(hass, floyd: FloydController) -> None:
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    battery = FloydController(floyd._coordinator)
    battery._battery_mode = True
    first, second = service_target(floyd), service_target(battery)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(
            [(first, "both"), (second, "both")], [],
        )),
        pytest.raises(ServiceValidationError, match="battery"),
    ):
        await hass.services.async_call(DOMAIN, "timed_move", {
            "device_id": ["one", "two"], "motor": "back", "direction": "up", "duration_ms": 100,
        }, blocking=True)
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()
    assert not writes(floyd)
    battery.validate_timed_movement("back", "down", 100)


@pytest.mark.parametrize("payload", [
    "c0ff01000000008b010000000000000000",  # explicit room zero
    "c0ff09000000000000444b00008b0100",  # type09 with exact company/product
])
def test_assignment_requires_positive_unassigned_evidence(floyd: FloydController, payload: str) -> None:
    floyd._room_id = None
    floyd._manufacturer_data = {}
    with pytest.raises(ValueError, match="advertisement proving"):
        floyd.validate_floyd_action("assign_room", "first", True, 123)
    floyd._manufacturer_data = {0xFFFF: bytes.fromhex(payload)}
    floyd.validate_floyd_action("assign_room", "first", True, 123)
