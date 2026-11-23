"""Stage002 dispatch vectors through registered central and local receive entries."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from tests.test_reverie_pairlink import _notify
from tests.test_reverie_pairlink_sdk_consumers import (
    _ADDRESS,
    _MAC_WIRE,
    _VADDR,
    _ping,
    _ready,
)


def _frame(body: bytes, channel: int = 0x21) -> bytes:
    return bytes.fromhex("03FFFFFFFF") + bytes((channel,)) + body


def _source(address_type: int, *, grouped: bool = False) -> bytes:
    address = _VADDR if address_type in (1, 3) else _MAC_WIRE
    return address + (b"\xa1\xb2" if address_type in (3, 4) else b"")


def _group(mode: int, address_type: int, groups: tuple[int, ...]) -> bytes:
    width = 1 if mode == 1 else 2
    return (
        bytes((mode, len(groups)))
        + b"".join(group.to_bytes(width, "little") for group in groups)
        + bytes((255, address_type))
        + _source(address_type, grouped=True)
        + bytes.fromhex("0080AABB")
    )


@pytest.mark.parametrize("mode,groups", [(1, (0, 255, 255)), (11, (0, 256, 65535))])
@pytest.mark.parametrize("address_type", [1, 2, 3, 4])
async def test_group_modes_reach_private_vendor_callback_with_exact_source_and_groups(
    mode, groups, address_type
) -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    await _notify(client, tasks, _frame(_group(mode, address_type, groups)))
    observed.assert_called_once()
    message = observed.call_args.args[0]
    assert message.groups == groups
    assert message.address_type == address_type
    assert message.address == (_VADDR if address_type in (1, 3) else _MAC_WIRE).ljust(6, b"\x00")
    assert message.unit_index == -1
    assert message.opcode == -32768
    assert message.data == bytes.fromhex("AABB")
    assert client.writes == []


async def test_group_vendor_callback_null_and_registered20_preemption() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    packet = _frame(_group(11, 3, (256,)), channel=0x20)
    await _notify(client, tasks, packet)
    observed.assert_not_called()
    runtime._mesh_callback_present = False
    await _notify(client, tasks, packet)
    observed.assert_not_called()
    assert client.writes == []


@pytest.mark.parametrize(
    "body",
    [
        bytes.fromhex("0102FF"),  # incomplete count/list
        bytes.fromhex("0B0100"),  # incomplete uint16 group
        _group(1, 1, (1,))[:-3],  # short opcode
        _group(11, 4, (2,))[:-4],  # missing UID/opcode bytes
    ],
)
async def test_group_failed_read_never_reaches_callback_or_send(body) -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    await _notify(client, tasks, _frame(body))
    observed.assert_not_called()
    assert client.writes == []


@pytest.mark.parametrize("channels,last", [(b"", 0), (b"\x01\xff", -1)])
async def test_mode2_preserves_last_signed_channel_and_remainder(channels, last) -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_aux_callback = observed
    packet = _frame(bytes((2, len(channels))) + channels + b"\xfe\x02" + _MAC_WIRE + b"payload")
    await _notify(client, tasks, packet)
    observed.assert_called_once()
    event = observed.call_args.args[0]
    assert event.kind == "channel"
    assert event.mac == _ADDRESS
    assert event.address == _MAC_WIRE
    assert event.values == (last,)
    assert event.data == b"payload"
    assert client.writes == []


async def test_mode2_negative_count_and_no_callback_or_wrong_address_type() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_aux_callback = observed
    packet = _frame(b"\x02\xff\x00\x02" + _MAC_WIRE)
    await _notify(client, tasks, packet)
    assert observed.call_args.args[0].values == (0,)
    observed.reset_mock()
    runtime._mesh_callback_present = False
    await _notify(client, tasks, packet)
    observed.assert_not_called()
    runtime._mesh_callback_present = True
    await _notify(client, tasks, _frame(b"\x02\x00\x00\x01" + _VADDR))
    await _notify(client, tasks, packet[:-1])
    observed.assert_not_called()
    assert client.writes == []


def _nested_source() -> bytes:
    return b"\x07\x00\xfd\x01" + _VADDR


async def test_one_command_dispatches_each_actual_target_and_group_record() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    cmd = b"\x03\x01\x00\x80"
    targets = b"\x11\x02" + _MAC_WIRE + b"\x01\x00" + b"\xff" * 6 + b"\x00\x80"
    groups8 = b"\x03\x03\x01\xff"
    groups16 = b"\x06\x0d\x00\x01\xff\xff\xcc"  # odd tail is ignored
    await _notify(
        client, tasks, _frame(b"\x03" + _nested_source() + cmd + targets + groups8 + groups16)
    )
    messages = [call.args[0] for call in observed.call_args_list]
    assert len(messages) == 4
    assert [message.opcode for message in messages] == [-32768] * 4
    assert messages[0].target_mac == _ADDRESS
    assert messages[0].unit_mask == 1
    assert messages[1].broadcast is True
    assert messages[1].unit_mask == -32768
    assert messages[2].groups == (1, 255)
    assert messages[3].groups == (256, 65535)
    assert client.writes == []


async def test_multi_command_targets_and_distinct_group16_range() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    target = b"\x0b\x04" + _MAC_WIRE + b"\x00\x00\x00\x80"
    group8 = b"\x04\x05\xfe\x00\x80"
    group16 = b"\x06\x0e\x00\x01\x00\x80\xcc"
    await _notify(client, tasks, _frame(b"\x04" + _nested_source() + target + group8 + group16))
    messages = [call.args[0] for call in observed.call_args_list]
    assert len(messages) == 3
    assert messages[0].target_mac == _ADDRESS
    assert messages[0].unit_mask == 0
    assert messages[0].unit_index == -3
    assert messages[1].groups == (254,)
    assert messages[2].groups == (256,)
    assert all(message.opcode == -32768 for message in messages)


async def test_multi_sensor_interception_preempts_following_vendor_only_with_callback() -> None:
    controller, client, runtime, tasks = await _ready()
    vendor, aux = Mock(), Mock()
    controller._sdk_vendor_callback = vendor
    controller._sdk_aux_callback = aux
    sensor = b"\x0b\x04" + _MAC_WIRE + b"\x01\x00\x6c\x04"
    vendor_target = b"\x0b\x04" + _MAC_WIRE + b"\x01\x00\x00\x80"
    await _notify(client, tasks, _frame(b"\x04" + _nested_source() + sensor + vendor_target))
    aux.assert_called_once()
    assert aux.call_args.args[0].data == b"\x01"
    vendor.assert_not_called()
    assert client.writes == []


@pytest.mark.parametrize("kind", [3, 4])
async def test_nested_malformed_header_has_no_effect(kind) -> None:
    controller, client, runtime, tasks = await _ready()
    vendor, aux = Mock(), Mock()
    controller._sdk_vendor_callback = vendor
    controller._sdk_aux_callback = aux
    for data in (b"", b"\x07", b"\x07\x00\x00\x01\x11", b"\x02\x00\x00"):
        await _notify(client, tasks, _frame(bytes((kind,)) + data))
    vendor.assert_not_called()
    aux.assert_not_called()
    assert client.writes == []


async def test_public_mac_sensor_route_has_exact_unknown_device_guard() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_aux_callback = observed
    target_wire = bytes.fromhex("665544332211")
    inner = b"\x00\x01\x00\x00\x02" + _MAC_WIRE + bytes.fromhex("5C040302AABB")
    public = bytes.fromhex("03FFFFFFFF14") + target_wire + b"\x20" + inner
    await _notify(client, tasks, public)
    observed.assert_called_once()
    event = observed.call_args.args[0]
    assert event.kind == "sensor"
    assert event.values == (2,)
    assert event.data == bytes.fromhex("AABB")
    observed.reset_mock()
    await _notify(client, tasks, _ping(mac=target_wire))
    client.writes.clear()
    await _notify(client, tasks, public)
    observed.assert_not_called()
    assert client.writes == []


async def test_private_callback_generation_change_stops_later_nested_targets() -> None:
    controller, client, runtime, tasks = await _ready()
    seen = []

    def callback(message):
        seen.append(message)
        controller.on_disconnect()

    controller._sdk_vendor_callback = callback
    target = b"\x09\x02" + _MAC_WIRE + b"\x01\x00"
    await _notify(
        client, tasks, _frame(b"\x03" + _nested_source() + b"\x03\x01\x00\x80" + target + target)
    )
    assert len(seen) == 1
    assert client.writes == []


async def test_real_profile_discovery_failure_projects_library3_status8() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock(wraps=controller._sdk_status_callback)
    controller._sdk_status_callback = observed
    client.services = []
    with pytest.raises(ConnectionError, match="complete Pairlink GATT profile"):
        await controller.async_discover_capabilities()
    observed.assert_called_once()
    assert observed.call_args.args[0].status == 8
    assert runtime.joined is False
    assert controller._sdk_devices == []
    assert client.writes == []


async def test_real_notification_enable_failure_projects_library4_before_mesh_exit() -> None:
    from bleak.exc import BleakError

    from tests.test_reverie_pairlink import _controller

    controller, client, runtime, tasks = _controller()
    observed = Mock(wraps=controller._sdk_status_callback)
    controller._sdk_status_callback = observed

    async def fail(*args, **kwargs):
        raise BleakError("fake descriptor write failure")

    client.start_notify = fail
    with pytest.raises(BleakError, match="descriptor"):
        await controller.start_notify()
    observed.assert_called_once()
    event = observed.call_args.args[0]
    assert event.status == 8
    assert event.epoch < runtime.epoch
    assert client.writes == []
    assert runtime.joined is False


async def test_library_status_callback_null_still_ends_transport_generation() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_status_callback = observed
    runtime._mesh_callback_present = False
    epoch = runtime.epoch
    runtime._on_central_library_status(4, source_mac=_ADDRESS)
    observed.assert_not_called()
    assert runtime.epoch > epoch
    await controller.start_notify()
    assert controller._sdk_devices == []
    assert client.writes == []


@pytest.mark.parametrize("status", [0, 1, 2, 5, 7, 8])
async def test_other_library_status_does_not_fabricate_status8(status) -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_status_callback = observed
    epoch = runtime.epoch
    runtime._on_central_library_status(status, source_mac=_ADDRESS)
    observed.assert_not_called()
    assert runtime.epoch == epoch
    assert runtime.joined is True
    assert client.writes == []


async def test_real_coordinator_exhausted_connect_failure_projects_library6(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_establish_connection,
) -> None:
    from bleak.exc import BleakError
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.reverie.pairlink import ReveriePairlinkController
    from custom_components.adjustable_bed.beds.reverie.pairlink_protocol import (
        PAIRLINK_NOTIFY_UUID,
        PAIRLINK_SERVICE_UUID,
        PAIRLINK_WRITE_UUID,
    )
    from custom_components.adjustable_bed.const import (
        BED_TYPE_REVERIE_PAIRLINK,
        CONF_PAIRLINK_ROLE,
        DOMAIN,
        PAIRLINK_ROLE_CENTRAL,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_reverie_pairlink_production import _GattService

    del mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SDK central status",
        unique_id=_ADDRESS,
        data={
            "address": _ADDRESS,
            "name": "R510L",
            "bed_type": BED_TYPE_REVERIE_PAIRLINK,
            "protocol_variant": "R510L",
            "motor_count": 2,
            "disable_angle_sensing": True,
        },
        options={CONF_PAIRLINK_ROLE: PAIRLINK_ROLE_CENTRAL},
    )
    entry.add_to_hass(hass)
    mock_bleak_client.services = [
        _GattService(PAIRLINK_SERVICE_UUID, PAIRLINK_WRITE_UUID, PAIRLINK_NOTIFY_UUID)
    ]
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    assert await coordinator.async_connect() is True
    controller = coordinator.controller
    assert isinstance(controller, ReveriePairlinkController)
    runtime = controller._runtime
    observed = Mock(wraps=controller._sdk_status_callback)
    controller._sdk_status_callback = observed
    await coordinator.async_disconnect()
    mock_bleak_client.write_gatt_char.reset_mock()
    mock_establish_connection.side_effect = BleakError("fake exhausted central connection")
    assert await coordinator.async_connect() is False
    observed.assert_called_once()
    assert observed.call_args.args[0].status == 8
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    await runtime.async_shutdown()


async def test_verified_local_writevalue_dispatches_group_and_channel_with_current_identity(
    hass,
    monkeypatch,
    enable_custom_integrations,
) -> None:
    from dbus_fast import DBusError

    from custom_components.adjustable_bed import async_unload_entry
    from tests.test_reverie_pairlink_production import (
        _PEER_PATH,
        _drain_socket,
        _entry,
        _local_setup,
        _login_packet,
        _recv,
        _send_peer_write,
        _subscribe_peer,
    )
    from tests.test_reverie_pairlink_transport import FakeBlueZBus, _device

    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    monkeypatch.setattr(controller, "_schedule_status_sync", lambda *args, **kwargs: None)
    socket = await _subscribe_peer(bus, _PEER_PATH)
    try:
        await _send_peer_write(bus, _PEER_PATH, _login_packet())
        _recv(socket)
        await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
        _recv(socket)
        await hass.async_block_till_done()
        _drain_socket(socket)
        vendor, aux = Mock(), Mock()
        controller._sdk_vendor_callback = vendor
        controller._sdk_aux_callback = aux
        await _send_peer_write(bus, _PEER_PATH, _frame(_group(11, 4, (256,))))
        vendor.assert_called_once()
        assert vendor.call_args.args[0].groups == (256,)
        await _send_peer_write(bus, _PEER_PATH, _frame(b"\x02\x01\xff\x00\x02" + _MAC_WIRE + b"x"))
        aux.assert_called_once()
        assert aux.call_args.args[0].values == (-1,)
        with pytest.raises(BlockingIOError):
            _recv(socket)
        bus.managed_objects[_PEER_PATH] = _device(connected=False)
        assert bus.peer_disconnect_callback is not None
        bus.peer_disconnect_callback(_PEER_PATH, False)
        with pytest.raises(DBusError):
            await _send_peer_write(bus, _PEER_PATH, _frame(_group(11, 4, (256,))))
        assert vendor.call_count == 1
    finally:
        await async_unload_entry(hass, entry)
        socket.close()


async def test_group_unknown_address_type_keeps_constructor_address_without_transport_borrow() -> (
    None
):
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    await _notify(client, tasks, _frame(bytes.fromhex("010000050080")))
    observed.assert_called_once()
    event = observed.call_args.args[0]
    assert event.groups == ()
    assert event.address_type == 5
    assert event.address == bytes(6)
    assert client.writes == []


@pytest.mark.parametrize("mode", [3, 4])
async def test_nested_calendar_calls_actual_private_send_from_learned_device(
    monkeypatch, mode
) -> None:
    from custom_components.adjustable_bed.beds.reverie import pairlink
    from tests.test_reverie_pairlink_sdk_consumers import _CalendarClock, _decoded

    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    if mode == 3:
        target = b"\x09\x02" + _MAC_WIRE + b"\x01\x00"
        body = _nested_source() + b"\x03\x01\x9b\x04" + target + target
    else:
        target = b"\x0b\x04" + _MAC_WIRE + b"\x01\x00\x9b\x04"
        body = _nested_source() + target + target
    await _notify(client, tasks, _frame(bytes((mode,)) + body))
    assert (
        _decoded(client, runtime)
        == [bytes.fromhex("0311223344200001000001000000009204EA07091C081E0003FD00000000")] * 2
    )


async def test_nested_valid_prefix_effect_survives_later_failed_read(monkeypatch) -> None:
    from custom_components.adjustable_bed.beds.reverie import pairlink
    from tests.test_reverie_pairlink_sdk_consumers import _CalendarClock, _decoded

    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    good = b"\x0b\x04" + _MAC_WIRE + b"\x01\x00\x9b\x04"
    bad = b"\x20\x04\xaa"
    await _notify(client, tasks, _frame(b"\x04" + _nested_source() + good + bad))
    assert len(_decoded(client, runtime)) == 1


async def test_multi_unit_empty_mask_returns_before_following_vendor() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    empty = b"\x0b\x04" + _MAC_WIRE + b"\x00\x00\x44\x03"
    vendor = b"\x0b\x04" + _MAC_WIRE + b"\x01\x00\x00\x80"
    await _notify(client, tasks, _frame(b"\x04" + _nested_source() + empty + vendor))
    observed.assert_not_called()
    assert client.writes == []


async def test_nested_overlong_source_caps_address_copy_and_stalls_cursor_exactly() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    # Source count=8 copies only six bytes; cursor remains10. Thus these two
    # nominal UID bytes become the command length/type, rather than a UID skip.
    source_and_command = b"\x0b\x00\x00\x04" + _MAC_WIRE + b"\x03\x01\x00\x80"
    target = b"\x09\x02" + _MAC_WIRE + b"\x01\x00"
    await _notify(client, tasks, _frame(b"\x03" + source_and_command + target))
    observed.assert_called_once()
    message = observed.call_args.args[0]
    assert message.address == _MAC_WIRE
    assert message.address_type == 4
    assert message.opcode == -32768
    assert client.writes == []


async def test_nested_zero_length_record_progress_and_unknown_mode_are_noops() -> None:
    controller, client, runtime, tasks = await _ready()
    vendor, aux = Mock(), Mock()
    controller._sdk_vendor_callback = vendor
    controller._sdk_aux_callback = aux
    await _notify(client, tasks, _frame(b"\x04" + _nested_source() + bytes(6)))
    await _notify(client, tasks, _frame(b"\x7f" + bytes(8)))
    vendor.assert_not_called()
    aux.assert_not_called()
    assert client.writes == []


async def test_library_failure_always_invalidates_session_if_callback_raises() -> None:
    controller, client, runtime, tasks = await _ready()
    epoch = runtime.epoch
    controller._sdk_status_callback = Mock(side_effect=ValueError("callback failure"))
    with pytest.raises(ValueError, match="callback failure"):
        runtime._on_central_library_status(4, source_mac=_ADDRESS)
    assert runtime.epoch > epoch
    assert runtime.joined is False
    assert client.writes == []


async def test_nonvendor_group_reaches_actual_callback_after_excluded_control_gate() -> None:
    controller, client, runtime, tasks = await _ready()
    aux = Mock()
    controller._sdk_aux_callback = aux
    body = b"\x01\x01\x01\x00\x01" + _VADDR + bytes.fromhex("5C040302AABB")
    await _notify(client, tasks, _frame(body))
    assert aux.call_count == 1
    assert aux.call_args.args[0].kind == "sensor"
    assert client.writes == []


@pytest.mark.parametrize(
    "opcode,data,kind",
    [
        (0x45C, bytes.fromhex("0302AABB"), "sensor"),
        (0x45C, b"x", "sensor_raw"),
        (0x503, b"\xff", "dynamic_group"),
    ],
)
def test_group_callback_record_follows_model_record_with_source_payload(opcode, data, kind) -> None:
    from custom_components.adjustable_bed.beds.reverie.pairlink_sdk import PairlinkSdkMessage
    from custom_components.adjustable_bed.beds.reverie.pairlink_sdk_dispatch import (
        PairlinkSdkCallbackEvent,
        decode_sdk_dispatch,
    )

    body = b"\x01\x01\x01\x00\x01" + _VADDR + opcode.to_bytes(2, "little") + data
    events = list(
        decode_sdk_dispatch(
            _frame(body),
            local_mac="00:00:00:00:00:00",
            known_macs=set(),
            callback_present=True,
        )
    )
    assert isinstance(events[0], PairlinkSdkMessage)
    assert events[0].groups == (1,)
    assert isinstance(events[1], PairlinkSdkCallbackEvent)
    assert events[1].kind == kind
    if kind == "sensor":
        assert events[1].data == bytes.fromhex("AABB")
        assert events[1].values == (2,)
    elif kind == "dynamic_group":
        assert events[1].groups == (1,)
        assert events[1].values == (-1,)
