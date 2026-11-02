"""Stage003 actual SDK ingress, canonical persistence and lifecycle proofs."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from unittest.mock import Mock

import pytest
from homeassistant.helpers.storage import Store

from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_metadata import (
    SdkFingerprintRecord,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_models import (
    PairlinkSdkDevice,
    PairlinkSdkSensorCadence,
)
from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_storage import (
    decode_fingerprint,
)
from tests.test_reverie_pairlink import _controller, _notify
from tests.test_reverie_pairlink_sdk_consumers import (
    _ADDRESS,
    _MAC_WIRE,
    _VADDR,
    _bean,
    _decoded,
    _message,
    _ping,
    _ready,
)

_BASIC = bytes.fromhex("3412010234127856") + _MAC_WIRE + b"\x01"
_FP = bytes.fromhex("1122334455667788")


def _tlv(kind: int, data: bytes) -> bytes:
    return bytes((len(data) + 1, kind & 255)) + data


def _full_tlv() -> bytes:
    return (
        _tlv(0, _BASIC)
        + _tlv(2, b"Runtime name")
        + _tlv(7, bytes.fromhex("03010707"))
        + _tlv(1, bytes.fromhex("03003412"))
        + _tlv(5, bytes.fromhex("01015634"))
        + _tlv(13, bytes.fromhex("CDAB"))
        + _tlv(18, bytes.fromhex("ABCD"))
    )


def _composition() -> bytes:
    # appearance + signed unit count + signed function count + LE16 functions.
    return bytes.fromhex("C0070103040004000500")


def _network(count: int = 1) -> bytes:
    return b"\x01\x02" + bytes(6) + count.to_bytes(2, "little") + bytes.fromhex("01020304")


async def _canonical_ready():
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _message(4, data=_full_tlv()))
    client.writes.clear()
    return controller, client, runtime, tasks


async def test_central_tlv_wires_all_canonical_fields_from_actual_notify() -> None:
    controller, client, _runtime, tasks = await _ready()
    await _notify(client, tasks, _message(4, data=_full_tlv()))
    bean = _bean(controller)
    assert isinstance(bean, PairlinkSdkDevice)
    assert (bean.app_id, bean.company_id, bean.product_id) == (0x1234, 0x1234, 0x5678)
    assert (bean.version, bean.unit_num, bean.device_name) == ("4660 1.2", 1, "Runtime name")
    assert bean.units[0].groups == [1, 7, 7]
    assert bean.units[0].function_id == 3 and bean.units[0].level == 0x1234
    assert bean.units[0].sensors[0].sensitivity == 0x3456
    assert bean.profile_ver == 0xABCD and bean.vendor_business == bytes.fromhex("ABCD")
    assert controller._sdk_metadata.devices[0].canonical is bean
    assert controller._sdk_metadata.devices[0].units[0].functions is bean.units[0].function_list


async def test_central_composition_persists_then_emits_exact_initial_queries() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    await _notify(client, tasks, _message(1, data=_composition()))
    assert len(_decoded(client, runtime)) == 14
    bean = _bean(controller)
    assert bean.appearance == 0x07C0
    assert bean.units[0].function_list == [4, 4, 5]
    record = controller._sdk_metadata.attributes[-1]
    assert record.units[0].functions == [4, 3, 4, 5]
    payload = controller._sdk_io._store.async_save.call_args.args[0]
    saved = json.loads(payload["attributesManagement"]["list"])
    assert saved[-1] == {
        "appId": 0x1234,
        "companyId": 0x1234,
        "pidList": [0x5678],
        "appearance": 0x07C0,
        "unitList": [{"attributesList": [4, 3, 4, 5]}],
    }
    client.writes.clear()
    await _notify(client, tasks, _message(1, data=_composition()))
    assert client.writes == []  # known identity returns before status/finish/write
    assert controller._sdk_io._store.async_save.call_count == 1


async def test_null_tlv_sensor_abandons_receive_without_status8() -> None:
    controller, client, _runtime, tasks = await _ready()
    # Count1 means None payload, distinct from a byte array. TLV5 reads length.
    await _notify(client, tasks, _message(4, data=_tlv(0, _BASIC) + b"\x01\x05"))
    assert client.writes == []
    assert not controller._sdk_devices


async def test_composition_partial_writes_survive_later_malformed_read() -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    bean = _bean(controller)
    bean.units[0].function_list[:] = [99]
    await _notify(client, tasks, _message(1, data=bytes.fromhex("341201020400")))
    assert bean.appearance == 0x1234
    assert bean.units[0].function_list == [4]
    assert client.writes == []
    controller._sdk_io._store.async_save.assert_not_called()


async def test_composition_unknown_device_does_not_borrow_transport_identity() -> None:
    controller, client, _runtime, tasks = await _ready()
    await _notify(client, tasks, _message(1, data=_composition()))
    assert client.writes == []
    controller._sdk_io._store.async_save.assert_not_called()


async def test_registered20_preemption_and_null_callback_keep_composition_gates() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    await _notify(client, tasks, _message(1, channel=0x20, data=_composition()))
    controller._sdk_io._store.async_save.assert_not_called()
    runtime._mesh_callback_present = False
    await _notify(client, tasks, _message(1, channel=0x20, data=_composition()))
    controller._sdk_io._store.async_save.assert_called_once()
    assert client.writes == []


async def test_attribute_io_failure_keeps_model_and_catalog_but_omits_completion() -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    controller._sdk_io._store.async_save.side_effect = OSError("test storage failure")
    with pytest.raises(OSError, match="test storage"):
        await _notify(client, tasks, _message(1, data=_composition()))
    assert _bean(controller).units[0].function_list == [4, 4, 5]
    assert controller._sdk_metadata.attributes[-1].units[0].functions == [4, 3, 4, 5]
    assert client.writes == []
    assert controller._sdk_io._data == {}


async def test_full_ping_replacement_retains_forward_removal_adjacent_duplicate() -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    original = _bean(controller)
    # Populate a second position with the SAME actual bean. This is list state,
    # not an independent logical device/provider.
    controller._sdk_devices.append(original)
    incoming = _message(4, address=bytes.fromhex("55667788"), data=_full_tlv())
    await _notify(client, tasks, incoming)
    assert len(controller._sdk_devices) == 2
    assert controller._sdk_devices[0] is original
    fresh = controller._sdk_devices[1]
    assert isinstance(fresh, PairlinkSdkDevice) and fresh is not original
    assert fresh.vaddr == bytes.fromhex("55667788")
    assert list(controller._sdk_metadata.devices)[0].canonical is original
    assert list(controller._sdk_metadata.devices)[1].canonical is fresh


async def test_ff_first_duplicate_update_does_not_replace_other_model_fields() -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    first = _bean(controller)
    second = PairlinkSdkDevice(bt_addr=_ADDRESS, vaddr=bytes.fromhex("AABBCCDD"))
    controller._sdk_devices.append(second)
    await _notify(client, tasks, _ping(bytes.fromhex("55667788")))
    assert controller._sdk_devices[0] is first
    assert first.vaddr == bytes.fromhex("55667788") and first.app_id == 0x1234
    assert first.units[0].level == 0x1234 and first.device_name == "Runtime name"
    assert second.vaddr == bytes.fromhex("AABBCCDD")


async def test_low_power_parser_reaches_only_its_actual_callback() -> None:
    controller, client, _runtime, tasks = await _ready()
    received = Mock()
    controller._sdk_low_power_callback = received
    await _notify(
        client,
        tasks,
        _message(
            6,
            address_type=2,
            address=_MAC_WIRE,
            data=_tlv(0, bytes.fromhex("341281FF34127856C007")) + _tlv(13, b"\x34\x12"),
        ),
    )
    assert received.call_count == 1
    bean = received.call_args.args[0]
    assert isinstance(bean, PairlinkSdkDevice)
    assert (bean.bt_addr, bean.version_major, bean.version_minor, bean.appearance) == (
        _ADDRESS,
        -127,
        -1,
        1984,
    )
    assert bean.profile_ver == 0x1234
    assert not controller._sdk_devices and client.writes == []


async def test_default_network_info_projects_status7_without_fingerprint_query() -> None:
    controller, client, runtime, tasks = await _ready()
    statuses = Mock()
    controller._sdk_status_delegate = statuses
    await _notify(client, tasks, _network(2))
    assert statuses.call_args_list == [((7,),)]
    assert client.writes.pop(0)[1] == b"\x01\x1a"
    assert _decoded(client, runtime) == [
        b"\x03" + bytes.fromhex("FFFFFFFF") + b"\xfe" + runtime.own_virtual_address,
    ]
    assert controller._sdk_expected_devices == 2
    assert not controller._sdk_metadata.fingerprint_enabled
    assert runtime.sign_gate.sign_all
    assert runtime.current_event_key != bytes(16)


async def test_fingerprint_match_loads_same_canonical_refs_and_exact_effect_order() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    bean = _bean(controller)
    metadata = controller._sdk_metadata
    view = controller._sdk_views.view(bean)
    metadata.fingerprint = SdkFingerprintRecord(
        runtime.credentials.home_id_le.hex(), _FP.hex(), [view, view], True
    )
    metadata.fingerprint_enabled = True  # exact SDK setting, source default is false
    statuses: list[int] = []
    controller._sdk_status_delegate = statuses.append
    await _notify(client, tasks, _network(2))
    assert [wire for _, wire, _ in client.writes] == [b"\x01\x1a", b"\x01\x42"]
    timer = controller._sdk_timers["fingerprint"]
    assert timer.delay == 0.5
    client.writes.clear()
    await _notify(client, tasks, b"\x02\x42" + _FP)
    assert timer.cancelled
    assert metadata.fingerprint_state == 3 and metadata.fingerprint.valid is False
    assert controller._sdk_devices == [bean, bean]
    assert metadata.fingerprint.devices[0] is metadata.fingerprint.devices[1] is view
    assert statuses == [8]
    assert len(_decoded(client, runtime)) == 14


async def test_fingerprint_miss_ping_tail_saves_after_status_and_before_exit_teardown() -> None:
    controller, client, runtime, tasks = await _ready()
    metadata = controller._sdk_metadata
    metadata.fingerprint_enabled = True
    order: list[object] = []
    controller._sdk_status_delegate = lambda status: order.append(status)
    store = controller._sdk_io._store

    async def save(snapshot):
        # Serialized JSON strings cannot change when later models change.
        order.append(
            json.loads(
                snapshot.get("pl_finger_print", {}).get(
                    runtime.credentials.home_id_le.hex(), "null"
                )
            )
        )

    store.async_save.side_effect = save
    await _notify(client, tasks, _network())
    await _notify(client, tasks, b"\x02\x42" + _FP)
    assert metadata.fingerprint_state == 2 and order == [7]
    client.writes.clear()
    await _notify(client, tasks, _ping())
    assert order[1] == 8
    assert isinstance(order[2], dict) and order[2]["isFingerPrintValid"] is False
    assert metadata.fingerprint_state == 3
    bean = _bean(controller)
    before = store.async_save.call_args.args[0]
    old_snapshot = before["pl_finger_print"][runtime.credentials.home_id_le.hex()]
    bean.device_name = "modified after snapshot"
    assert "modified after snapshot" not in old_snapshot
    assert metadata.fingerprint.devices[0].canonical is bean

    async def save_exit(snapshot):
        assert not runtime.is_closed and runtime.joined
        assert controller._sdk_devices[0] is bean
        order.append("exit")
        assert json.loads(snapshot["pl_finger_print"][runtime.credentials.home_id_le.hex()])[
            "isFingerPrintValid"
        ]

    store.async_save.side_effect = save_exit
    await runtime.async_shutdown()
    assert order[-1] == "exit" and runtime.is_closed
    assert not controller._sdk_timers


async def test_fingerprint_write_failure_keeps_pending_state_and_omits_later_state3() -> None:
    controller, client, _runtime, tasks = await _ready()
    metadata = controller._sdk_metadata
    metadata.fingerprint_enabled = True
    await _notify(client, tasks, _network())
    await _notify(client, tasks, b"\x02\x42" + _FP)
    controller._sdk_io._store.async_save.side_effect = OSError("fingerprint write")
    with pytest.raises(OSError, match="fingerprint write"):
        await _notify(client, tasks, _ping())
    assert metadata.fingerprint_state == 2
    assert metadata.fingerprint.fingerprint == _FP.hex().upper()
    assert len(metadata.fingerprint.devices) == 1


async def test_fingerprint_native_short_stale_and_callback_only_guards() -> None:
    controller, client, runtime, tasks = await _ready()
    metadata = controller._sdk_metadata
    metadata.fingerprint_state = 1
    await _notify(client, tasks, b"\x02\x42" + _FP[:-1])
    assert metadata.fingerprint_state == 1 and metadata.pending_fingerprint == ""
    old_callback = client.notify_callback
    controller.on_disconnect()
    assert old_callback is not None
    old_callback(None, bytearray(b"\x02\x42" + _FP))
    assert tasks == []
    await controller.start_notify()
    assert metadata.fingerprint_state == 0
    metadata.fingerprint_state = 3
    client.writes.clear()
    await _notify(client, tasks, b"\x02\x42" + _FP)
    assert metadata.pending_fingerprint == "" and client.writes == []
    assert runtime.joined is False


async def test_fingerprint_timer_fires_exact_callback_and_rejects_ended_generation() -> None:
    controller, client, _runtime, tasks = await _ready()
    metadata = controller._sdk_metadata
    metadata.fingerprint_enabled = True
    statuses = Mock()
    controller._sdk_status_delegate = statuses
    await _notify(client, tasks, _network())
    timer = controller._sdk_timers["fingerprint"]
    timer.fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert metadata.fingerprint_state == 3
    statuses.assert_called_once_with(7)
    metadata.fingerprint_state = 0
    await _notify(client, tasks, _network())
    stale_timer = controller._sdk_timers["fingerprint"]
    controller.on_disconnect()
    statuses.reset_mock()
    # Even forced invocation after cancellation cannot own the new generation.
    stale_timer.callback(*stale_timer.args)
    assert not tasks
    statuses.assert_not_called()
    assert metadata.fingerprint_state == 1  # disconnect is NOT source join reset


async def test_storage_codec_snapshots_complete_models_and_preserves_source_namespaces() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    bean = _bean(controller)
    bean.units[0].sensors[0].cadence = PairlinkSdkSensorCadence(
        delta_down=1,
        delta_up=2,
        fast_high=3,
        fast_low=4,
        min_interval=5,
        period_divisor=6,
        publish_period=1 << 40,
    )
    metadata = controller._sdk_metadata
    metadata.fingerprint_enabled = True
    metadata.fingerprint = SdkFingerprintRecord(
        runtime.credentials.home_id_le.hex(), "aabb", [controller._sdk_views.view(bean)], False
    )
    await controller.stop_notify()
    stored = controller._sdk_io._store.async_save.call_args.args[0]
    encoded = stored["pl_finger_print"][runtime.credentials.home_id_le.hex()]
    decoded = decode_fingerprint(encoded, controller._sdk_views)
    assert decoded is not None
    assert asdict(decoded.devices[0].canonical) == asdict(bean)
    assert decoded.devices[0].canonical is not bean
    model_json = json.loads(encoded)["deviceList"][0]
    assert model_json["btAddrStr"] == _ADDRESS
    assert model_json["vAddr"] == [17, 34, 51, 68]
    assert model_json["unitInfoList"][0]["sensorList"][0]["candence"]["publishPeriod"] == 1 << 40
    assert model_json["vendorBusiness"] == [-85, -51]
    assert not any(
        word in encoded
        for word in (
            "password",
            "credentials",
            "session_key",
            "event_key",
            "peer_sessions",
            "host_adapter",
        )
    )
    assert stored.keys() == {"pl_finger_print"}
    client.writes.clear()
    await runtime.async_shutdown()
    assert controller._sdk_io._store.async_save.call_count == 1


async def test_actual_ha_store_is_entry_scoped_and_recovers_source_json_null(hass) -> None:
    controller, _client, runtime, _tasks = _controller()
    controller._sdk_io._store = None
    controller._sdk_io._factory = lambda: Store(
        hass, 1, "adjustable_bed.pairlink_sdk.wiring-test-entry"
    )
    await controller.start_notify()
    assert len(controller._sdk_metadata.attributes) == 15
    # Persist the source JSON-null catalog, not an absent preference.
    await controller._sdk_io._write("attributesManagement", "list", "null")
    other, _client2, _runtime2, _tasks2 = _controller()
    other._sdk_io._store = None
    other._sdk_io._factory = lambda: Store(hass, 1, "adjustable_bed.pairlink_sdk.wiring-test-entry")
    await other.start_notify()
    assert other._sdk_metadata.attributes == []
    separate, _client3, _runtime3, _tasks3 = _controller()
    separate._sdk_io._store = None
    separate._sdk_io._factory = lambda: Store(hass, 1, "adjustable_bed.pairlink_sdk.other-entry")
    await separate.start_notify()
    assert len(separate._sdk_metadata.attributes) == 15
    assert controller._sdk_metadata.fingerprint.home_id == runtime.credentials.home_id_le.hex()
    await controller.stop_notify()
    await other.stop_notify()
    await separate.stop_notify()


async def test_metadata_queue_continuation_uses_actual_composition_send_and_timer() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    bean = _bean(controller)
    key = controller._sdk_metadata.identity_key(controller._sdk_views.view(bean))
    controller._sdk_metadata.unknown_identities[:] = ["first-queue-row", key]
    await _notify(client, tasks, _message(1, data=_composition()))
    assert controller._sdk_metadata.unknown_identities == [key]
    assert controller._sdk_timers["attributes"].delay == 3
    frames = _decoded(client, runtime)
    assert frames == [
        bytes.fromhex("03FFFFFFFF14")
        + _MAC_WIRE
        + b"\x20\x00\x00\x00\x00\x02"
        + runtime.local_join_bt_mac
        + b"\x00\x00"
    ]
    client.writes.clear()
    controller._sdk_timers["attributes"].fire()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert controller._sdk_metadata.unknown_identities == []
    assert "attributes" not in controller._sdk_timers
    assert client.writes == []


def _read_available(peer_socket):
    from tests.test_reverie_pairlink_production import _recv

    values = []
    while True:
        try:
            values.append(_recv(peer_socket))
        except BlockingIOError:
            return values


@asynccontextmanager
async def _local_canonical(hass, monkeypatch):
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
    from tests.test_reverie_pairlink_transport import FakeBlueZBus

    bus = FakeBlueZBus()
    entry = _entry()
    coordinator = await _local_setup(hass, monkeypatch, entry, bus)
    controller = coordinator.controller
    monkeypatch.setattr(controller, "_schedule_status_sync", lambda *a, **kw: None)
    peer_socket = await _subscribe_peer(bus, _PEER_PATH)
    try:
        await _send_peer_write(bus, _PEER_PATH, _login_packet())
        _recv(peer_socket)
        await _send_peer_write(bus, _PEER_PATH, b"\x02\x31\x08")
        _recv(peer_socket)
        await hass.async_block_till_done()
        _drain_socket(peer_socket)
        await _send_peer_write(bus, _PEER_PATH, _message(4, data=_full_tlv()))
        await hass.async_block_till_done()
        _drain_socket(peer_socket)
        yield controller, bus, peer_socket, entry
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
        peer_socket.close()


async def test_local_writevalue_composition_reaches_real_ha_store_and_peer_queries(
    hass, monkeypatch, enable_custom_integrations
) -> None:
    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        decrypt_user_frame,
        state_query_payloads,
    )
    from tests.test_reverie_pairlink_production import _PEER_PATH, _send_peer_write

    del enable_custom_integrations
    async with _local_canonical(hass, monkeypatch) as (controller, bus, peer_socket, entry):
        await _send_peer_write(bus, _PEER_PATH, _message(1, data=_composition()))
        await hass.async_block_till_done()
        wires = _read_available(peer_socket)
        assert len(wires) == 14
        runtime = controller._runtime
        assert [
            decrypt_user_frame(
                value, event_key=runtime.current_event_key, device_key=bytes.fromhex("10203040")
            )[10:]
            for value in wires
        ] == list(state_query_payloads())
        bean = _bean(controller)
        assert isinstance(bean, PairlinkSdkDevice)
        assert bean.units[0].function_list == [4, 4, 5]
        stored = await Store(hass, 1, f"adjustable_bed.pairlink_sdk.{entry.entry_id}").async_load()
        row = json.loads(stored["attributesManagement"]["list"])[-1]
        assert row["unitList"] == [{"attributesList": [4, 3, 4, 5]}]
        assert not controller._sdk_metadata.unknown_identities
        assert not controller._sdk_timers


async def test_local_native_fingerprint_load_binds_current_peer_and_exit_saves_before_backend_stop(
    hass, monkeypatch, enable_custom_integrations
) -> None:
    from tests.test_reverie_pairlink_production import (
        _PEER_ADDRESS,
        _PEER_PATH,
        _send_peer_write,
    )

    del enable_custom_integrations
    async with _local_canonical(hass, monkeypatch) as (controller, bus, peer_socket, entry):
        runtime = controller._runtime
        metadata = controller._sdk_metadata
        bean = _bean(controller)
        metadata.fingerprint_enabled = True
        metadata.fingerprint_state = 1
        metadata.fingerprint = SdkFingerprintRecord(
            runtime.credentials.home_id_le.hex(),
            _FP.hex(),
            [controller._sdk_views.view(bean)],
            True,
        )
        await _send_peer_write(bus, _PEER_PATH, _network(4))
        assert metadata.fingerprint_state == 1
        assert not controller._sdk_timers and _read_available(peer_socket) == []
        await _send_peer_write(bus, _PEER_PATH, b"\x02\x42" + _FP)
        await hass.async_block_till_done()
        assert len(_read_available(peer_socket)) == 14
        assert metadata.fingerprint_state == 3 and not metadata.fingerprint.valid
        assert metadata.devices[0].canonical is bean
        assert controller._sdk_owners[id(bean)] == (
            runtime.epoch,
            _PEER_ADDRESS,
            runtime.peer_sessions[_PEER_ADDRESS].identity,
        )
        store = controller._sdk_io._store
        actual_save = store.async_save
        saved: list[bool] = []

        async def saving(snapshot):
            saved.append(runtime.peripheral_backend.is_ready and not runtime.is_closed)
            await actual_save(snapshot)

        monkeypatch.setattr(store, "async_save", saving)
        await runtime.async_shutdown()
        assert saved == [True]
        stored = await Store(hass, 1, f"adjustable_bed.pairlink_sdk.{entry.entry_id}").async_load()
        value = json.loads(stored["pl_finger_print"][metadata.fingerprint.home_id])
        assert (
            value["isFingerPrintValid"] and value["deviceList"][0]["deviceName"] == "Runtime name"
        )


@pytest.mark.parametrize("mode", [1, 11])
async def test_group_modes_use_canonical_catalog_gate_with_duplicate_group_order(mode) -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    unit = _bean(controller).units[0]
    unit.onoff = True
    supports = Mock(wraps=controller._sdk_metadata.supports)
    controller._sdk_metadata.supports = supports
    width = 1 if mode == 1 else 2
    groups = (7).to_bytes(width, "little") * 2
    body = bytes((mode, 2)) + groups + b"\x00\x01" + _VADDR + bytes.fromhex("BA030100")
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF21") + body)
    assert supports.call_args_list == [((0x1234, 0x1234, 0x5678, 0, 5),)] * 2
    assert client.writes == []
    controller._sdk_lib_calc_status = False
    supports.reset_mock()
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF21") + body)
    supports.assert_not_called()


async def test_callback_null_group_sensor_stops_nested_receive_before_later_ping() -> None:
    controller, client, runtime, tasks = await _ready()
    runtime._mesh_callback_present = False
    from tests.test_reverie_pairlink_sdk_dispatch import _frame

    body = b"\x01\x01\x01\x00\x01" + _VADDR + bytes.fromhex("5C040302AABB")
    await _notify(client, tasks, _frame(body))
    assert client.writes == [] and not controller._sdk_devices


async def test_source_join_entry_reset_does_not_repeat_on_ack_or_notify() -> None:
    controller, client, runtime, tasks = _controller()
    controller._sdk_metadata.fingerprint_state = 2
    await controller.start_notify()
    assert controller._sdk_metadata.fingerprint_state == 0
    controller._sdk_metadata.fingerprint_state = 2
    await controller.start_notify()
    assert controller._sdk_metadata.fingerprint_state == 2
    from tests.test_reverie_pairlink import _login_packet

    await _notify(client, tasks, _login_packet())
    await _notify(client, tasks, b"\x02\x31\x08")
    assert runtime.joined and controller._sdk_metadata.fingerprint_state == 2


async def test_mesh_info_reinitialization_keeps_loaded_record_home_and_source_hex() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    metadata = controller._sdk_metadata
    bean = _bean(controller)
    from custom_components.adjustable_bed.beds.reverie_pairlink_runtime import (
        PairlinkCredentials,
        PairlinkHomeIdOrigin,
    )
    from custom_components.adjustable_bed.beds.reverie_pairlink_sdk_storage import (
        encode_fingerprint,
    )

    metadata.fingerprint_state = 2
    old_attributes = metadata.attributes
    encoded = encode_fingerprint(
        SdkFingerprintRecord(
            "stored-own-home-id",
            "aabb",
            [controller._sdk_views.view(bean)],
            True,
        )
    )
    controller._sdk_io._data = {"pl_finger_print": {"78563412": encoded}}
    runtime.credentials = PairlinkCredentials.from_inputs(
        0x12345678, home_id_origin=PairlinkHomeIdOrigin.DECLARED_HA_POLICY
    )
    await _notify(client, tasks, b"\x02\x42" + _FP)
    assert controller._sdk_home_id == "78563412"
    assert metadata.fingerprint.home_id == "stored-own-home-id"
    assert metadata.attributes is old_attributes and metadata.fingerprint_state == 2


async def test_actual_controller_exit_storage_failure_still_closes_native_material() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    metadata = controller._sdk_metadata
    metadata.fingerprint_enabled = True
    metadata.fingerprint.fingerprint = "aabb"
    controller._sdk_io._store.async_save.side_effect = OSError("exit failure")
    with pytest.raises(OSError, match="exit failure"):
        await runtime.async_shutdown()
    assert metadata.fingerprint.valid
    assert runtime.is_closed and runtime.admitted_peer_count == 0
    assert not runtime.joined and not controller._sdk_timers


async def test_receive_lane_serializes_native_seed_changes_across_persistence_await() -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    entered, release = asyncio.Event(), asyncio.Event()
    initial_key = runtime.current_event_key

    async def saving(_snapshot):
        entered.set()
        await release.wait()

    controller._sdk_io._store.async_save.side_effect = saving
    assert client.notify_callback is not None
    client.notify_callback(None, bytearray(_message(1, data=_composition())))
    await entered.wait()
    assert client.notify_callback is not None
    client.notify_callback(None, bytearray(_network(7)))
    # Yield deterministically to the queued receive task; no wall-clock delay.
    queued = asyncio.Event()
    asyncio.get_running_loop().call_soon(queued.set)
    await queued.wait()
    assert runtime.current_event_key == initial_key
    assert controller._sdk_expected_devices == 0
    release.set()
    while tasks:
        pending, tasks[:] = tasks[:], []
        await asyncio.gather(*pending)
    assert runtime.current_event_key != initial_key
    assert controller._sdk_expected_devices == 7


async def test_coordinator_shutdown_disconnects_central_even_when_exit_persistence_fails(
    hass, monkeypatch, mock_coordinator_connected, mock_bleak_client
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.beds.reverie_pairlink_protocol import (
        PAIRLINK_NOTIFY_UUID,
        PAIRLINK_SERVICE_UUID,
        PAIRLINK_WRITE_UUID,
    )
    from custom_components.adjustable_bed.const import BED_TYPE_REVERIE_PAIRLINK, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_reverie_pairlink import _login_packet
    from tests.test_reverie_pairlink_production import _GattService

    del mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="SDK exit ordering",
        unique_id=_ADDRESS,
        data={
            "address": _ADDRESS,
            "name": "R510L",
            "bed_type": BED_TYPE_REVERIE_PAIRLINK,
            "protocol_variant": "R510L",
            "motor_count": 2,
            "disable_angle_sensing": True,
        },
    )
    entry.add_to_hass(hass)
    mock_bleak_client.services = [
        _GattService(PAIRLINK_SERVICE_UUID, PAIRLINK_WRITE_UUID, PAIRLINK_NOTIFY_UUID)
    ]
    coordinator = AdjustableBedCoordinator(hass, entry)
    assert await coordinator.async_connect()
    controller = coordinator.controller
    runtime = controller._runtime
    monkeypatch.setattr(controller, "_schedule_status_sync", lambda *a, **kw: None)
    notify = mock_bleak_client.start_notify.await_args.args[1]
    notify(None, bytearray(_login_packet()))
    await hass.async_block_till_done()
    notify(None, bytearray(b"\x02\x31\x08"))
    await hass.async_block_till_done()
    notify(None, bytearray(_message(4, data=_full_tlv())))
    await hass.async_block_till_done()
    assert runtime.joined and controller._sdk_devices
    controller._sdk_metadata.fingerprint_enabled = True
    controller._sdk_metadata.fingerprint.fingerprint = "aabb"

    async def fail(_snapshot):
        assert runtime.joined and not runtime.is_closed
        raise OSError("coordinator exit storage")

    monkeypatch.setattr(controller._sdk_io._store, "async_save", fail)
    with pytest.raises(OSError, match="coordinator exit storage"):
        await coordinator.async_shutdown()
    mock_bleak_client.disconnect.assert_awaited()
    assert runtime.is_closed and not runtime.joined
    assert runtime.admitted_peer_count == 0


async def test_controller_replacement_reuses_the_entry_metadata_lane_without_catalog_reset() -> (
    None
):
    from custom_components.adjustable_bed.beds.reverie_pairlink import ReveriePairlinkController

    first, client, runtime, tasks = await _canonical_ready()
    await _notify(client, tasks, _message(1, data=_composition()))
    metadata = first._sdk_metadata
    metadata.fingerprint_enabled = True
    metadata.fingerprint_state = 2
    catalog = metadata.attributes
    first.on_disconnect()
    second = ReveriePairlinkController(first._coordinator, model="R510L", runtime=runtime)
    assert second._sdk_metadata is metadata
    assert second._sdk_receive_lock is first._sdk_receive_lock
    assert second._sdk_devices is first._sdk_devices
    assert metadata.fingerprint_state == 2 and metadata.fingerprint_enabled
    assert metadata.attributes is catalog and len(catalog) == 16
    assert not second._sdk_devices
    await second.start_notify()
    assert metadata.fingerprint_state == 0  # successful new central join entry
    assert metadata.attributes is catalog


async def test_actual_tlv_stream_calls_every_supplied_model_branch_without_enabling_excluded_workers(
    monkeypatch,
) -> None:
    from custom_components.adjustable_bed.beds import reverie_pairlink_sdk as sdk

    controller, client, runtime, tasks = await _ready()
    vectors = [
        (1, bytes.fromhex("03003412")),
        (2, b"name"),
        (3, b"\x01\x81"),
        (4, bytes.fromhex("01073412")),
        (5, bytes.fromhex("01015634")),
        (6, b"\x01x"),
        (7, b"\x02\x07\x07"),
        (8, bytes.fromhex("03002143")),
        (9, b"\x00\x01"),
        (10, b"\xff\xff"),
        (12, b""),
        (13, b"\xcd\xab"),
        (16, b""),
        (17, bytes.fromhex("0207010701")),
        (18, b"\xab\xcd"),
        (19, bytes.fromhex("0300214301")),
        (20, b"\x00"),
        (22, bytes.fromhex("020000")),
        (23, bytes.fromhex("0100FEFF")),
        (24, b"\xff"),
        (-3, bytes.fromhex("02000300")),
    ]
    called = Mock(wraps=sdk.apply_nonbasic_tlv)
    monkeypatch.setattr(sdk, "apply_nonbasic_tlv", called)
    await _notify(
        client,
        tasks,
        _message(4, data=_tlv(0, _BASIC) + b"".join(_tlv(kind, body) for kind, body in vectors)),
    )
    bean = _bean(controller)
    assert called.call_count == len(vectors)
    assert [call.args[1] for call in called.call_args_list] == [kind for kind, _ in vectors]
    assert all(call.args[0] is bean for call in called.call_args_list)
    assert called.call_args_list[10].args[2] is None
    assert called.call_args_list[12].args[2] is None
    unit = bean.units[0]
    assert (bean.reboot_times, bean.mesh_changed_times, bean.deleted, bean.dynamic_running) == (
        2,
        3,
        True,
        True,
    )
    assert bean.support_storage and bean.profile_ver == 0xABCD
    assert unit.groups == [263, 263] and unit.name == "x"
    assert (unit.function_id, unit.level, unit.restore_level, unit.onoff) == (
        2,
        0x4321,
        0x4321,
        False,
    )
    assert (
        unit.level_toggle_up,
        unit.temperature_toggle_up,
        unit.hue_toggle_up,
        unit.scene_toggle,
    ) == (False, True, False, -1)
    assert (unit.ctl.minimum, unit.ctl.maximum) == (1, 65534)
    assert len(_decoded(client, runtime)) == 14
    assert not controller._sdk_timers and not controller._sdk_metadata.unknown_identities
    controller._sdk_io._store.async_save.assert_not_called()


async def test_fingerprint_list_restore_binds_models_even_with_null_callback(monkeypatch) -> None:
    from custom_components.adjustable_bed.beds import reverie_pairlink as pairlink
    from tests.test_reverie_pairlink_sdk_consumers import _CalendarClock

    controller, client, runtime, tasks = await _canonical_ready()
    bean = _bean(controller)
    metadata = controller._sdk_metadata
    metadata.fingerprint = SdkFingerprintRecord(
        runtime.credentials.home_id_le.hex(), _FP.hex(), [controller._sdk_views.view(bean)], True
    )
    metadata.fingerprint_state = 1
    runtime._mesh_callback_present = False
    controller._sdk_owners.clear()
    await _notify(client, tasks, b"\x02\x42" + _FP)
    assert metadata.fingerprint_state == 3 and client.writes == []
    assert controller._sdk_owners[id(bean)] == (runtime.epoch, _ADDRESS, None)
    monkeypatch.setattr(pairlink, "datetime", _CalendarClock)
    await _notify(client, tasks, _message(0x049B))
    assert len(_decoded(client, runtime)) == 1
    assert _decoded(client, runtime)[0][1:5] == _VADDR


@pytest.mark.parametrize(
    "app,units,tail,online",
    [
        (0xF106, 1, bytes.fromhex("000000030034120100"), False),
        (0xF105, 0, bytes.fromhex("000000"), False),
        (0xF10D, 0, bytes.fromhex("00000002"), False),
        (0x1234, 1, bytes.fromhex("01010400010002000300017800"), True),
    ],
)
async def test_legacy_ping_preparser_and_special_app_chains_reach_actual_canonical_list(
    app, units, tail, online
) -> None:
    controller, client, runtime, tasks = await _ready()
    basic = app.to_bytes(2, "little") + _BASIC[2:14] + bytes((units,))
    await _notify(client, tasks, _message(3, data=basic + tail))
    bean = _bean(controller)
    assert isinstance(bean, PairlinkSdkDevice) and bean.online is online
    assert bean.unit_num == units and len(bean.units) == units
    assert len(_decoded(client, runtime)) == 14
    if app == 0xF106:
        assert (
            bean.units[0].level,
            bean.units[0].sensors[0].onoff,
            bean.units[0].sensors[1].onoff,
        ) == (0x1234, True, False)
    elif app == 0x1234:
        assert (
            bean.units[0].ctl.lightness,
            bean.units[0].ctl.temperature,
            bean.units[0].ctl.delta_uv,
        ) == (1, 2, 3)
        assert bean.device_name == "x" and bean.units[0].groups == [0]


async def test_sign_response_unknown_bean_updates_gate_without_borrowing_physical_peer() -> None:
    controller, client, runtime, tasks = await _ready()
    observed = Mock(wraps=controller._sdk_status_callback)
    controller._sdk_status_callback = observed
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF1230") + _MAC_WIRE + b"\xff")
    assert runtime.sign_gate.device_signs[_ADDRESS] == "-1"
    assert not runtime.sign_gate.sign_all and client.writes == []
    observed.assert_not_called()


async def test_sign_response_known_logical_mac_uses_canonical_lookup_before_status8() -> None:
    controller, client, runtime, tasks = await _ready()
    logical_wire = bytes.fromhex("605040302010")
    await _notify(client, tasks, _ping(mac=logical_wire))
    client.writes.clear()
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF1230") + logical_wire + b"\x01")
    assert runtime.sign_gate.device_signs["10:20:30:40:50:60"] == "1"
    assert len(_decoded(client, runtime)) == 14


@pytest.mark.parametrize("subtype", [8, 11])
async def test_channel16_uses_exact_reported_vaddr_instead_of_any_known_bean(subtype) -> None:
    controller, client, runtime, tasks = await _canonical_ready()
    head = bytes.fromhex("03FFFFFFFF16") + bytes((subtype,))
    await _notify(client, tasks, head + bytes.fromhex("55667788") + bytes(3))
    assert client.writes == []
    await _notify(client, tasks, head + _VADDR + bytes(3))
    assert len(_decoded(client, runtime)) == 14


async def test_channel12_first_null_row_suppresses_link_callback() -> None:
    controller, client, _runtime, tasks = await _canonical_ready()
    controller._sdk_devices.insert(0, None)
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF124000"))
    assert client.writes == []


async def test_sign_callback_known_bean_is_not_gated_on_joined_send_readiness() -> None:
    controller, client, runtime, tasks = _controller()
    client.mtu_size = 247
    await controller.start_notify()
    await _notify(client, tasks, _ping())
    assert not runtime.joined and client.writes == []
    observed = Mock(wraps=controller._sdk_status_callback)
    controller._sdk_status_callback = observed
    await _notify(client, tasks, bytes.fromhex("03FFFFFFFF1230") + _MAC_WIRE + b"\x01")
    observed.assert_called_once()
    assert client.writes == []


@pytest.mark.parametrize("mode8", [False, True])
async def test_ping_after_uses_online_count_and_saves_before_func_callback(mode8) -> None:
    controller, client, runtime, tasks = await _ready()
    await _notify(client, tasks, _ping())
    bean = _bean(controller)
    # A second offline canonical row makes list length differ from online count.
    controller._sdk_devices.append(PairlinkSdkDevice(bt_addr="FF:FF:FF:FF:FF:FF"))
    controller._sdk_expected_devices = 1
    controller._sdk_metadata.fingerprint_state = 2
    controller._sdk_metadata.pending_fingerprint = _FP.hex()
    order = []
    controller._sdk_status_delegate = lambda status: order.append(status)
    controller._sdk_io._store.async_save.side_effect = lambda _snapshot: order.append("save")
    client.writes.clear()
    packet = (
        bytes.fromhex("03FFFFFFFF2108") + _MAC_WIRE + bytes.fromhex("88776655FF0700")
        if mode8
        else _message(4, data=_full_tlv())
    )
    await _notify(client, tasks, packet)
    assert order == ["save", 8]
    assert controller._sdk_metadata.fingerprint_state == 3
    assert len(controller._sdk_metadata.fingerprint.devices) == 2
    assert len(_decoded(client, runtime)) == 14
    if mode8:
        assert _bean(controller) is bean and bean.vaddr == _VADDR
