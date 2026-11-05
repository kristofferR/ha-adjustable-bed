"""SDK consumers exercised through the real registered notification path."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from custom_components.adjustable_bed.beds import reverie_pairlink as pairlink
from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
    decrypt_user_frame,
    fragment_central_frame,
    state_query_payloads,
)
from tests.test_reverie_pairlink import (
    _ADDRESS,
    _controller,
    _join_central,
    _notify,
)

_MAC_WIRE = bytes.fromhex("FFEEDDCCBBAA")
_VADDR = bytes.fromhex("11223344")


def _ping(vaddr: bytes = _VADDR, mac: bytes = _MAC_WIRE) -> bytes:
    return bytes.fromhex("03FFFFFFFFFF") + mac + vaddr + bytes.fromhex("06F10102")


def _message(
    opcode: int,
    *,
    address_type: int = 1,
    address: bytes = _VADDR,
    data: bytes = b"",
    channel: int = 0x21,
    unit: int = 0,
) -> bytes:
    uid = bytes.fromhex("FACA") if address_type in (3, 4) else b""
    return (
        bytes.fromhex("03FFFFFFFF")
        + bytes((channel,))
        + bytes.fromhex("000100")
        + bytes((unit, address_type))
        + address
        + uid
        + opcode.to_bytes(2, "little")
        + data
    )


def _decoded(client, runtime) -> list[bytes]:
    # MTU247 in tests below keeps these responses in one GATT write.
    return [
        decrypt_user_frame(
            value, event_key=runtime.current_event_key, device_key=bytes.fromhex("10203040")
        )
        for _characteristic, value, _response in client.writes
    ]


def _bean(controller):
    return next(bean for bean in controller._sdk_devices if bean is not None and bean.bt_addr == _ADDRESS)


async def _ready():
    controller, client, runtime, tasks = _controller()
    client.mtu_size = 247
    await _join_central(controller, client, runtime, tasks)
    client.writes.clear()
    return controller, client, runtime, tasks


async def test_channel_ff_getter0_creates_updates_and_rekeys_device_table() -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    devices = controller._sdk_devices
    bean = _bean(controller)
    assert bean.vaddr == _VADDR
    assert bean.app_id == -3834
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())

    client.writes.clear()
    replacement = bytes.fromhex("55667788")
    await _notify(client, tasks, _ping(replacement))
    assert devices[0] is bean
    assert bean.vaddr == replacement
    assert controller._sdk_virtual_address_is_current(_ADDRESS, None, replacement)
    assert not controller._sdk_virtual_address_is_current(_ADDRESS, None, _VADDR)
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())

    controller.on_disconnect()
    assert controller._sdk_devices == []


@pytest.mark.parametrize("size", [6, 7, 16, 19])
async def test_channel_ff_status8_does_not_depend_on_ping_helper_result(size: int) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping()[:size])
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    assert controller._sdk_devices == []


async def test_channel_ff_null_callback_still_updates_table_without_queries() -> None:
    controller, client, runtime, tasks = await _ready()
    runtime._mesh_callback_present = False
    await _notify(client, tasks, _ping())
    assert _bean(controller).vaddr == _VADDR
    assert client.writes == []


async def test_channel_ff_detector_branch_skips_response_and_status8() -> None:
    controller, client, runtime, tasks = await _ready()
    runtime._join_check_type = 1
    await _notify(client, tasks, _ping())
    assert controller._sdk_devices == []
    assert client.writes == []


@pytest.mark.parametrize(
    ("address_type", "address"),
    [(1, _VADDR), (2, _MAC_WIRE), (3, _VADDR), (4, _MAC_WIRE)],
)
async def test_vendor_dispatch_preserves_packet_source_and_early_return(
    address_type: int, address: bytes
) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    packet = _message(
        0x8000, address_type=address_type, address=address, data=b"\x9b\x04", unit=255
    )
    await _notify(client, tasks, packet)
    observed.assert_called_once()
    message = observed.call_args.args[0]
    assert message.address_type == address_type
    assert message.address == address.ljust(6, b"\x00")
    assert message.unit_index == -1
    assert message.opcode == -32768
    assert message.data == b"\x9b\x04"
    assert client.writes == []


async def test_vendor_unknown_device_is_callback_input_and_null_callback_is_noop() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    packet = _message(0xFFFF, address=bytes.fromhex("88776655"))
    await _notify(client, tasks, packet)
    assert observed.call_args.args[0].opcode == -1
    assert observed.call_args.args[0].data == b""
    runtime._mesh_callback_present = False
    observed.reset_mock()
    await _notify(client, tasks, packet)
    observed.assert_not_called()
    assert client.writes == []


async def test_registered_callback_preempts_sdk_even_when_ignored_or_throwing() -> None:
    controller, client, runtime, tasks = await _ready()
    vendor = Mock()
    controller._sdk_vendor_callback = vendor
    await _notify(client, tasks, _message(0x8000, channel=0x20))
    vendor.assert_not_called()
    controller.set_mesh_event_callback(Mock(side_effect=ValueError("registered callback")))
    with pytest.raises(ValueError, match="registered callback"):
        await _notify(client, tasks, _message(0x8000, channel=0x20))
    vendor.assert_not_called()
    # Null MeshCallback alone stops preempting, despite registered channel20.
    runtime._mesh_callback_present = False
    controller.set_mesh_event_callback(None)
    await _notify(client, tasks, _message(0x049B, channel=0x20))
    vendor.assert_not_called()
    assert client.writes == []


class _LocalDateTime(datetime):
    def astimezone(self, tz=None):
        return self


class _CalendarClock:
    calls = 0

    @classmethod
    def now(cls):
        cls.calls += 1
        # Distinct calendar and zone samples, including negative half-hour.
        return _LocalDateTime(
            2026, 10, 28, 8, 30, 0, tzinfo=timezone(timedelta(hours=-3, minutes=-30))
        )


@pytest.mark.parametrize(
    ("address_type", "address"),
    [(1, _VADDR), (2, _MAC_WIRE), (3, _VADDR), (4, _MAC_WIRE)],
)
async def test_known_049b_sends_exact_0492_calendar_via_actual_transport(
    monkeypatch, address_type: int, address: bytes
) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    _CalendarClock.calls = 0
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)
    await _notify(client, tasks, _message(0x049B, address_type=address_type, address=address))
    assert _decoded(client, runtime) == [
        bytes.fromhex("0311223344200001000001000000009204EA07091C081E0003FD00000000")
    ]
    assert _CalendarClock.calls == 2


@pytest.mark.parametrize("zone_minutes,zone_byte", [(-30, 0), (345, 5), (-210, 253)])
async def test_calendar_timezone_mapping_and_month_weekday(
    monkeypatch, zone_minutes, zone_byte
) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()

    class Clock:
        @staticmethod
        def now():
            return _LocalDateTime(
                2026, 11, 1, 23, 59, 58, tzinfo=timezone(timedelta(minutes=zone_minutes))
            )

    monkeypatch.setattr(pairlink, "datetime", Clock)
    await _notify(client, tasks, _message(0x049B))
    payload = _decoded(client, runtime)[0][17:]
    assert payload == bytes.fromhex("EA070A01173B3A00") + bytes((zone_byte,)) + bytes(4)


@pytest.mark.parametrize(
    "packet",
    [
        _message(0x049B),
        _message(0x049B, address_type=2, address=_MAC_WIRE),
        _message(0x049B, address_type=3),
        _message(0x049B, address_type=4, address=_MAC_WIRE),
        _message(0x049B, address_type=5),
        _message(0x049B)[:-1],
        _message(0x8000)[:-1],
    ],
)
async def test_unknown_device_or_short_opcode_never_borrows_transport_ownership(packet) -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock()
    controller._sdk_vendor_callback = observed
    await _notify(client, tasks, packet)
    assert client.writes == []
    observed.assert_not_called()


async def test_public_profile_checks_embedded_channel_and_destination(monkeypatch) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)
    inner = _message(0x049B)[6:]
    public = bytes.fromhex("03FFFFFFFF14FFFFFFFFFFFF20") + inner
    await _notify(client, tasks, public)
    assert len(_decoded(client, runtime)) == 1
    client.writes.clear()
    await _notify(client, tasks, public[:12] + b"\x21" + inner)
    await _notify(client, tasks, public[:6] + bytes.fromhex("605040302010") + public[12:])
    assert client.writes == []


async def test_calendar_stale_at_scheduler_admission_does_not_send(monkeypatch) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)

    async def execute(command, **kwargs):
        controller.on_disconnect()
        await command(controller)

    controller._coordinator.async_execute_controller_command = execute
    await _notify(client, tasks, _message(0x049B))
    assert client.writes == []


async def test_calendar_uses_existing_central_fragment_sender(monkeypatch) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)
    client.mtu_size = 23
    await _notify(client, tasks, _message(0x049B))
    plain = bytes.fromhex("0311223344200001000001000000009204EA07091C081E0003FD00000000")
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import encrypt_user_frame

    wire = encrypt_user_frame(
        plain, event_key=runtime.current_event_key, device_key=bytes.fromhex("10203040")
    )
    assert tuple(value for _, value, _ in client.writes) == fragment_central_frame(wire, att_mtu=23)


async def test_local_writevalue_ping_and_calendar_use_verified_peer_socket(
    hass, monkeypatch, enable_custom_integrations
) -> None:
    from custom_components.adjustable_bed import async_unload_entry
    from tests.test_reverie_pairlink_production import (
        _PEER_ADDRESS,
        _PEER_PATH,
        _drain_socket,
        _entry,
        _local_setup,
        _login_packet,
        _recv,
        _send_peer_write,
        _subscribe_peer,
    )
    from tests.test_reverie_pairlink_transport import FakeBlueZBus

    del enable_custom_integrations
    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    runtime = controller._runtime
    monkeypatch.setattr(controller, "_schedule_status_sync", lambda *a, **kw: None)
    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    try:
        await _send_peer_write(bus, _PEER_PATH, _login_packet())
        _recv(peer_socket)
        await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
        _recv(peer_socket)
        await hass.async_block_till_done()
        _drain_socket(peer_socket)
        await _send_peer_write(bus, _PEER_PATH, _ping())
        await hass.async_block_till_done()
        assert (
            tuple(
                decrypt_user_frame(
                    _recv(peer_socket),
                    event_key=runtime.current_event_key,
                    device_key=bytes.fromhex("10203040"),
                )[10:]
                for _ in state_query_payloads()
            )
            == state_query_payloads()
        )
        peer = runtime.peer_sessions[_PEER_ADDRESS].identity
        assert _bean(controller).vaddr == _VADDR
        assert controller._sdk_owners[id(_bean(controller))] == (runtime.epoch, _PEER_ADDRESS, peer)

        monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)
        await _send_peer_write(bus, _PEER_PATH, _message(0x049B))
        await hass.async_block_till_done()
        assert decrypt_user_frame(
            _recv(peer_socket),
            event_key=runtime.current_event_key,
            device_key=bytes.fromhex("10203040"),
        ) == bytes.fromhex("0311223344200001000001000000009204EA07091C081E0003FD00000000")
        with pytest.raises(BlockingIOError):
            _recv(peer_socket)
        # Old BlueZ identity cannot repopulate or use the ended peer's table.
        bus.managed_objects[_PEER_PATH] = {
            "org.bluez.Device1": {
                **bus.managed_objects[_PEER_PATH]["org.bluez.Device1"],
                "Connected": False,
            }
        }
        assert bus.peer_disconnect_callback is not None
        bus.peer_disconnect_callback(_PEER_PATH, False)
        assert controller._sdk_devices == []
    finally:
        await async_unload_entry(hass, entry)
        peer_socket.close()


async def test_calendar_refuses_transport_failure_without_another_peer_fallback(
    monkeypatch,
) -> None:
    from bleak.exc import BleakError

    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock, raising=False)

    async def fail(*args, **kwargs):
        raise BleakError("fake GATT failure")

    monkeypatch.setattr(client, "write_gatt_char", fail)
    await _notify(client, tasks, _message(0x049B))
    assert client.writes == []


async def test_status8_queued_before_disconnect_does_not_query_new_generation() -> None:
    controller, client, runtime, tasks = await _ready()

    async def execute(command, **kwargs):
        controller.on_disconnect()
        await command(controller)

    controller._coordinator.async_execute_controller_command = execute
    await _notify(client, tasks, _ping())
    assert client.writes == []


async def test_calendar_requires_known_device_but_not_a_mesh_callback(monkeypatch) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    runtime._mesh_callback_present = False
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    # With callback null, registered20 reaches built-in mode0 instead.
    await _notify(client, tasks, _message(0x049B, channel=0x20))
    assert len(_decoded(client, runtime)) == 1


async def test_calendar_pending_target_address_update_is_not_sent(monkeypatch) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)

    async def execute(command, **kwargs):
        bean = _bean(controller)
        bean.vaddr = bytes.fromhex("55667788")
        await command(controller)

    controller._coordinator.async_execute_controller_command = execute
    await _notify(client, tasks, _message(0x049B))
    assert client.writes == []


async def test_calendar_uses_runtime_learned_source_and_current_key(monkeypatch) -> None:
    from tests.test_reverie_pairlink import _login_packet

    controller, client, runtime, tasks = _controller()
    client.mtu_size = 247
    await controller.start_notify()
    # This first login produces the current key; duplicate logins after join
    # are correctly ignored by the source runtime.
    key = bytes.fromhex("FECDAB89")
    await _notify(client, tasks, _login_packet(session_key=key))
    await _notify(client, tasks, b"\x02\x31\x08")
    await _notify(client, tasks, bytes.fromhex("010A44332211"))
    await _notify(client, tasks, _ping())
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    await _notify(client, tasks, _message(0x049B))
    assert [
        decrypt_user_frame(value, event_key=runtime.current_event_key, device_key=key)
        for _, value, _ in client.writes
    ] == [bytes.fromhex("0311223344200001000001443322119204EA07091C081E0003FD00000000")]


def _basic_ping(app_id: int = 0x1234, unit_count: int = 0) -> bytes:
    return (
        app_id.to_bytes(2, "little")
        + bytes.fromhex("010200000000")
        + _MAC_WIRE
        + bytes((unit_count,))
    )


@pytest.mark.parametrize("opcode", [3, 4])
async def test_sdk_ping_produces_device_identity_then_queries(opcode) -> None:
    controller, client, runtime, tasks = await _ready()
    basic = _basic_ping()
    body = basic + b"\x00" if opcode == 3 else b"\x10\x00" + basic
    await _notify(client, tasks, _message(opcode, data=body))
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    bean = _bean(controller)
    assert bean.vaddr == _VADDR
    assert bean.app_id == 0x1234


@pytest.mark.parametrize("body", [b"", b"\x00\x00", b"\x02\x00\x34"])
async def test_tlv_ping_helper_return_still_emits_status8(body) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _message(4, data=body))
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    assert controller._sdk_devices == []


@pytest.mark.parametrize(
    ("opcode", "body"),
    [
        (3, b""),
        (3, _basic_ping()),
        (3, _basic_ping(app_id=0xF106, unit_count=0) + bytes(3)),
        (3, _basic_ping(unit_count=1) + b"\xff"),
        (4, b"\x10\x00"),
        (4, b"\x01\x00"),
    ],
)
async def test_failed_ping_reads_never_emit_queries(opcode, body) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _message(opcode, data=body))
    assert client.writes == []
    assert controller._sdk_devices == []


async def test_j2_ping_uses_signed_appid_and_real_prefix_before_callback() -> None:
    controller, client, runtime, tasks = await _ready()
    body = _basic_ping(app_id=0xF106, unit_count=1) + bytes.fromhex("000000030001000000")
    await _notify(client, tasks, _message(3, data=body))
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    assert _bean(controller).app_id == -3834


async def test_sdk_mac_source_uses_devicebean_constructor_vaddr_then_ping_update() -> None:
    controller, client, runtime, tasks = await _ready()
    body = b"\x10\x00" + _basic_ping()
    await _notify(client, tasks, _message(4, address_type=2, address=_MAC_WIRE, data=body))
    assert _bean(controller).vaddr == bytes(4)
    await _notify(client, tasks, _ping())
    assert _bean(controller).vaddr == _VADDR


async def test_sdk_tlv_ping_keeps_registered20_preemption_and_null_callback_guard() -> None:
    controller, client, runtime, tasks = await _ready()
    body = b"\x10\x00" + _basic_ping()
    await _notify(client, tasks, _message(4, channel=0x20, data=body))
    assert client.writes == []
    assert controller._sdk_devices == []
    runtime._mesh_callback_present = False
    await _notify(client, tasks, _message(4, channel=0x20, data=body))
    assert _bean(controller).vaddr == _VADDR
    assert client.writes == []


@pytest.mark.parametrize("known", [False, True])
async def test_short_mode8_opcode7_status8_keeps_existing_address(known) -> None:
    controller, client, runtime, tasks = await _ready()
    if known:
        await _notify(client, tasks, _ping())
        client.writes.clear()
    short = bytes.fromhex("03FFFFFFFF2108") + _MAC_WIRE + bytes.fromhex("88776655FF0700")
    await _notify(client, tasks, short)
    assert [frame[10:] for frame in _decoded(client, runtime)] == list(state_query_payloads())
    if known:
        bean = _bean(controller)
        assert bean.online is True
        assert bean.vaddr == _VADDR
    else:
        assert controller._sdk_devices == []


@pytest.mark.parametrize("suffix", [b"", b"\x07", b"\x08\x00"])
async def test_short_mode8_incomplete_or_other_opcode_does_not_query(suffix) -> None:
    controller, client, runtime, tasks = await _ready()
    short = bytes.fromhex("03FFFFFFFF2108") + _MAC_WIRE + _VADDR + b"\x00" + suffix
    await _notify(client, tasks, short)
    assert client.writes == []


async def test_short_mode8_registered_callback_and_null_callback_gates() -> None:
    controller, client, runtime, tasks = await _ready()
    runtime.registered_channels.add(0x21)
    short = bytes.fromhex("03FFFFFFFF2108") + _MAC_WIRE + _VADDR + b"\x00\x07\x00"
    await _notify(client, tasks, short)
    assert client.writes == []
    runtime._mesh_callback_present = False
    await _notify(client, tasks, short)
    assert client.writes == []


@pytest.mark.parametrize("opcode", [3, 4])
async def test_calendar_consumes_real_sdk_ping_producer_without_ff_or_injected_state(
    monkeypatch, opcode
) -> None:
    controller, client, runtime, tasks = await _ready()
    basic = _basic_ping()
    body = basic + b"\x00" if opcode == 3 else b"\x10\x00" + basic
    await _notify(client, tasks, _message(opcode, data=body))
    client.writes.clear()
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    await _notify(client, tasks, _message(0x049B))
    assert _decoded(client, runtime) == [
        bytes.fromhex("0311223344200001000001000000009204EA07091C081E0003FD00000000")
    ]
