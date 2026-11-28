"""Actual connector, refresh ordering and dashboard lease cases for S1/S3/S6."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ar_connect.headboard import ROUTINE_COUNT, ROUTINE_LIST
from custom_components.adjustable_bed.bluetooth_bond import (
    BluezReadStatus,
    LocalBondInventory,
    LocalBondRecord,
)
from custom_components.adjustable_bed.bluetooth_freshness import (
    AdvertisementEvidence,
    FreshnessStatus,
)
from custom_components.adjustable_bed.bluetooth_transport import (
    ConnectionPath,
    PathPrediction,
    TransportClass,
)
from custom_components.adjustable_bed.codec import ar_connect as codec
from custom_components.adjustable_bed.repairs import PairingRequiredRepairFlow
from custom_components.adjustable_bed.setup_operation import OperationOutcome
from custom_components.adjustable_bed.unsupported import create_pairing_required_issue
from tests.hold_lease_wire import virtual_clock
from tests.test_ar_connect_review_fixes import call, paired  # noqa: F401
from tests.test_ar_connect_runtime import app, hb, native_gatt, publish_runtime, runtime, writes
from tests.test_config_flow import _pairing_flow, _run_pairing


@pytest.mark.parametrize("paired_ok", [True, False])
async def test_s1_public_pair_now_pairs_once_on_actual_proxy_without_auth_proof(hass, paired_ok):
    flow = _pairing_flow(hass)
    flow._manual_data.update(
        bed_type="ar_connect", protocol_variant="native", product_type="back_legs"
    )
    forecast = ConnectionPath("forecast-proxy", TransportClass.PROXY)
    actual = ConnectionPath("actual-proxy", TransportClass.PROXY)
    client = MagicMock()
    client.pair = AsyncMock(return_value=paired_ok)
    client.disconnect = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"model")
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=0, source="forecast-proxy"
    )
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.async_predict_path",
            return_value=PathPrediction(forecast, (forecast, actual)),
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            new=AsyncMock(return_value=(fresh, MagicMock())),
        ),
        patch(
            "bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)
        ) as connector,
        patch(
            "custom_components.adjustable_bed.config_flow.client_source",
            return_value="actual-proxy",
        ),
        patch(
            "custom_components.adjustable_bed.config_flow.async_path_for_source",
            return_value=actual,
        ),
    ):
        result = await _run_pairing(hass, flow)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert connector.await_args.kwargs.get("pair", False) is False
    client.pair.assert_awaited_once()
    client.read_gatt_char.assert_not_awaited()
    assert "ble_bond_context" not in result["data"]
    assert result["data"].get("ble_bond_established", False) is paired_ok
    assert result["data"].get("ble_bond_attempted_source") == (
        "actual-proxy" if paired_ok else None
    )


@pytest.mark.parametrize("route", ["missing", "unknown", "host_unreadable", "host_exact"])
async def test_s1_pair_now_requires_classified_route_and_exact_host_proof(hass, route):
    flow = _pairing_flow(hass)
    flow._manual_data.update(
        bed_type="ar_connect", protocol_variant="native", product_type="back_legs"
    )
    host = route.startswith("host_")
    source = "11:22:33:44:55:66" if host else "unclassified"
    actual = (
        ConnectionPath(source, TransportClass.LOCAL, adapter="hci0")
        if host
        else None if route == "missing" else ConnectionPath(source, TransportClass.UNKNOWN)
    )
    forecast = ConnectionPath("forecast-proxy", TransportClass.PROXY)
    client = MagicMock()
    client.pair = AsyncMock(return_value=True)
    client.disconnect = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"model")
    inventory = LocalBondInventory(status=BluezReadStatus.UNAVAILABLE)
    if route == "host_exact":
        inventory = LocalBondInventory(
            status=BluezReadStatus.OK,
            records=(LocalBondRecord(
                address=flow._manual_data["address"],
                device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_01",
                adapter_path="/org/bluez/hci0",
                adapter_address=source,
                paired=True,
                bonded=True,
            ),),
        )
    fresh = AdvertisementEvidence(
        status=FreshnessStatus.FRESH, age_seconds=0, source=forecast.source
    )
    with (
        patch("custom_components.adjustable_bed.config_flow.async_predict_path",
              return_value=PathPrediction(forecast, (forecast,))),
        patch("custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
              new=AsyncMock(return_value=(fresh, MagicMock()))),
        patch("bleak_retry_connector.establish_connection",
              new=AsyncMock(return_value=client)) as connector,
        patch("custom_components.adjustable_bed.config_flow.client_source", return_value=source),
        patch("custom_components.adjustable_bed.config_flow.async_path_for_source",
              return_value=actual),
        patch("custom_components.adjustable_bed.bond_verification.async_read_local_bonds",
              new=AsyncMock(return_value=inventory)),
    ):
        result = await _run_pairing(hass, flow)
    assert connector.await_args.kwargs.get("pair", False) is False
    assert client.pair.await_count == int(host)
    client.read_gatt_char.assert_not_awaited()
    assert flow.operation.result is not None
    assert flow.operation.result.outcome is (
        OperationOutcome.SUCCESS if route == "host_exact"
        else OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE if host
        else OperationOutcome.ROUTE_MISMATCH
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"].get("ble_bond_established", False) is (route == "host_exact")
    assert "ble_bond_attempted_source" not in result["data"]
    assert ("ble_bond_context" in result["data"]) is (route == "host_exact")


@pytest.mark.parametrize("step", ["confirm", "proxy_pairing"])
@pytest.mark.parametrize("paired_ok", [True, False])
async def test_s1_public_guided_proxy_repair_records_attempt_and_reconnect_reuses_it(
    hass, actual_connection, step, paired_ok
):
    c, client, connector, _ = actual_connection
    flow = PairingRequiredRepairFlow(
        c.address,
        c.name,
        c.entry.entry_id,
        issue_data={
            "evidence_status": "auth_failed",
            "evidence_transport": "proxy",
            "evidence_source": "actual-proxy",
        },
    )
    flow.hass = hass
    await create_pairing_required_issue(
        hass,
        c.address,
        c.name,
        c.entry.entry_id,
        evidence={
            "status": "auth_failed",
            "owner": {"transport": "proxy", "source": "actual-proxy"},
        },
    )
    client.pair.reset_mock(return_value=True)
    client.pair.return_value = paired_ok
    read = client.read_gatt_char.side_effect
    client.read_gatt_char.side_effect = None
    client.read_gatt_char.return_value = b"model"
    client.read_gatt_char.reset_mock()
    with (
        patch.object(flow, "_find_device", return_value=MagicMock()),
        patch(
            "bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)
        ) as repair_connector,
        patch(
            "custom_components.adjustable_bed.repairs.client_source", return_value="actual-proxy"
        ),
        patch(
            "custom_components.adjustable_bed.repairs.async_path_for_source",
            return_value=ConnectionPath("actual-proxy", TransportClass.PROXY),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload,
    ):
        result = await getattr(flow, "async_step_" + step)({})
    assert result["type"] is (
        FlowResultType.CREATE_ENTRY
        if paired_ok
        else FlowResultType.ABORT
        if step == "confirm"
        else FlowResultType.FORM
    )
    client.pair.assert_awaited_once()
    client.read_gatt_char.assert_not_awaited()
    assert repair_connector.await_args.kwargs.get("pair", False) is False
    assert "ble_bond_context" not in c.entry.data
    assert c.entry.data.get("ble_bond_established") is paired_ok
    assert c.entry.data.get("ble_bond_attempted_source") == ("actual-proxy" if paired_ok else None)
    assert reload.await_count == int(paired_ok)
    client.read_gatt_char.side_effect = read
    client.pair.return_value = True
    await c.async_disconnect(reason="intentional")
    assert await c.async_ensure_connected()
    assert client.pair.await_count == (1 if paired_ok else 2)
    assert all(
        row.kwargs["pair"] is False for row in connector.await_args_list if "pair" in row.kwargs
    )


@pytest.mark.parametrize("proof", ["exact", "absent", "other_adapter", "paired_only"])
async def test_s1_public_host_repair_requires_exact_native_stored_bond(hass, proof):
    address, source = "AA:BB:CC:DD:EE:95", "11:22:33:44:55:66"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Native repair",
        data={
            "address": address,
            "name": "Native repair",
            "bed_type": "ar_connect",
            "protocol_variant": "native",
            "ble_bond_established": True,
            "ble_bond_attempted_source": "old-proxy",
            "ble_bond_context": {"old": True},
        },
    )
    entry.add_to_hass(hass)
    flow = PairingRequiredRepairFlow(address, "Native repair", entry.entry_id)
    flow.hass = hass
    client = MagicMock(
        pair=AsyncMock(return_value=True),
        disconnect=AsyncMock(),
        read_gatt_char=AsyncMock(return_value=b"model"),
    )
    record = LocalBondRecord(
        address=address,
        device_path="/org/bluez/hci0/dev_AA_BB_CC_DD_EE_95",
        adapter_path="/org/bluez/hci0",
        adapter_address="22:33:44:55:66:77" if proof == "other_adapter" else source,
        paired=True,
        bonded=proof != "paired_only",
    )
    inventory = LocalBondInventory(
        status=BluezReadStatus.OK, records=() if proof == "absent" else (record,)
    )
    with (
        patch.object(flow, "_find_device", return_value=MagicMock()),
        patch(
            "bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)
        ) as connector,
        patch("custom_components.adjustable_bed.repairs.client_source", return_value=source),
        patch(
            "custom_components.adjustable_bed.repairs.async_path_for_source",
            return_value=ConnectionPath(source, TransportClass.LOCAL, adapter="hci0"),
        ),
        patch(
            "custom_components.adjustable_bed.bond_verification.async_read_local_bonds",
            new=AsyncMock(return_value=inventory),
        ),
        patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload,
    ):
        result = await flow.async_step_confirm({})
    accepted = proof == "exact"
    assert result["type"] is (FlowResultType.CREATE_ENTRY if accepted else FlowResultType.ABORT)
    assert connector.await_args.kwargs.get("pair", False) is False
    client.pair.assert_awaited_once()
    client.read_gatt_char.assert_not_awaited()
    assert reload.await_count == int(accepted)
    assert entry.data.get("ble_bond_established") is accepted
    assert "ble_bond_attempted_source" not in entry.data
    if accepted:
        assert entry.data["ble_bond_context"]["evidence_kind"] == "native_os_state"
        assert entry.data["ble_bond_context"]["source"] == source
        assert entry.data["ble_bond_context"]["verification"] == "repair_native_pairing"
    else:
        assert "ble_bond_context" not in entry.data


@pytest.fixture
async def actual_connection(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_establish_connection,
    enable_custom_integrations,
    request,
):
    stored = getattr(request, "param", "same")
    actual = {"source": "actual-proxy", "initial_stored": stored}
    g = native_gatt(mask=None, config=False)
    client = mock_bleak_client
    client.services = g
    client.read_gatt_char = AsyncMock(side_effect=lambda char: bytearray(g.reads[char.uuid]))
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.pair = AsyncMock(return_value=True)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        unique_id="AA:BB:CC:DD:EE:93",
        title="AR actual route",
        version=5,
        data={
            "address": "AA:BB:CC:DD:EE:93",
            "name": "AR actual route",
            "bed_type": "ar_connect",
            "protocol_variant": "native",
            "product_type": "back_legs",
            "motor_count": 2,
            "disable_angle_sensing": True,
            "has_massage": False,
            "connection_mode": "always",
            **(
                {
                    "ble_bond_established": True,
                    "ble_bond_attempted_source": "actual-proxy"
                    if stored == "same"
                    else "old-proxy",
                }
                if stored != "none"
                else {}
            ),
        },
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_connection.client_source",
            side_effect=lambda _: actual["source"],
        ),
        patch(
            "custom_components.adjustable_bed.coordinator_connection.async_path_for_source",
            side_effect=lambda _hass, source, **_kwargs: ConnectionPath(
                source, TransportClass.PROXY, source_domain="esphome"
            ),
        ),
        patch.object(app, "STARTUP_DELAY_S", 0),
        patch.object(app, "AR_CONNECT", replace(app.AR_CONNECT, custom_speed_post_write_ms=0)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = hass.data[const.DOMAIN][entry.entry_id]
        assert c.controller is not None and c.controller.link.ready
        yield c, client, mock_establish_connection, actual
        await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("actual_connection", ["same", "other", "none"], indirect=True)
async def test_s1_actual_ha_connector_never_pairs_before_route_and_reuses_reconnect(
    actual_connection,
):
    c, client, connector, actual = actual_connection
    assert all(call.kwargs["pair"] is False for call in connector.await_args_list)
    # The marker now always belongs to the actual selected proxy, not a forecast.
    assert c.entry.data["ble_bond_attempted_source"] == "actual-proxy"
    assert "ble_bond_context" not in c.entry.data
    first_count = client.pair.await_count
    assert first_count == (0 if actual["initial_stored"] == "same" else 1)
    await c.async_disconnect(reason="intentional")
    assert await c.async_ensure_connected()
    assert client.pair.await_count == first_count
    actual["source"] = "replacement-proxy"
    await c.async_disconnect(reason="intentional")
    assert await c.async_ensure_connected()
    assert client.pair.await_count == first_count + 1
    assert c.entry.data["ble_bond_attempted_source"] == "replacement-proxy"
    assert all(call.kwargs["pair"] is False for call in connector.await_args_list)
    assert "ble_bond_context" not in c.entry.data


@pytest.mark.parametrize("paired_ok", [True, False])
async def test_s1_actual_public_motion_auth_recovery_records_attempt_only(
    hass, actual_connection, paired_ok
):
    c, client, connector, _ = actual_connection
    assert client.pair.await_count == 0
    client.pair.return_value = paired_ok
    failed = False

    async def write(char, data, **kwargs):
        nonlocal failed
        if bytes(data) == b"\x0b\0" and not failed:
            failed = True
            raise BleakError("Insufficient authentication")

    client.write_gatt_char.side_effect = write
    entities = er.async_get(hass)
    entity = next(
        row
        for row in er.async_entries_for_config_entry(entities, c.entry.entry_id)
        if row.unique_id.endswith("_back") and row.domain == "cover"
    )
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "cover", "open_cover", {"entity_id": entity.entity_id}, blocking=True
        )
    assert client.pair.await_count == 1
    assert "ble_bond_context" not in c.entry.data
    assert c.entry.data.get("ble_bond_established") is paired_ok
    assert c._last_bond_evidence is None or not c._last_bond_evidence.proves_bond
    if paired_ok:
        assert c.entry.data["ble_bond_attempted_source"] == "actual-proxy"
        await c.async_disconnect(reason="intentional")
        assert await c.async_ensure_connected()
        assert client.pair.await_count == 1
    else:
        client.pair.return_value = True
        client.write_gatt_char.side_effect = None
        assert await c.async_ensure_connected()
        assert client.pair.await_count == 2
    assert all(row.kwargs["pair"] is False for row in connector.await_args_list)
    assert "ble_bond_context" not in c.entry.data


@pytest.mark.parametrize("chunks", [False, True])
async def test_s3_public_refresh_completes_when_notifications_beat_read_header(hass, chunks):
    ctrl, c, client, callbacks, _ = await runtime(hass, "headboard")
    device = await publish_runtime(hass, c)
    value = codec.compact_json({"13": codec.Routine(True, "wake", 7, 30, 10).payload()})
    previous = client.read_gatt_char.side_effect

    async def read(char):
        if char.uuid == hb.TRANSPORTS["routine"][1]:
            parts = [value[: len(value) // 2], value[len(value) // 2 :]] if chunks else [value]
            for part in parts:
                callbacks[char.uuid](char, bytearray(part))
            await asyncio.sleep(0)
            assert c.controller_state.get(ROUTINE_COUNT) is None
            return codec.compact_json({"length": len(value)})
        return await previous(char)

    client.read_gatt_char.side_effect = read
    with virtual_clock():
        await call(hass, "ar_connect_routine", device, action="refresh")
    assert c.controller_state.get(ROUTINE_COUNT) == 1 and "13" in c.controller_state.get(
        ROUTINE_LIST
    )
    assert ctrl.framer.length is None and not ctrl.framer.buffer
    client.is_connected = False
    await c.async_shutdown()


def test_s3_early_buffer_keeps_byte_length_boundary_and_recovers_after_bad_header():
    value = b'{"12":{"enabled":true,"mode":"wake","hour":7,"minute":30,"duration":10,"track":null,"volume":0,"recurrence":{}}}'
    framer = codec.RoutineFramer()
    assert framer.feed(value[:-1]) is None
    assert framer.feed(codec.compact_json({"length": len(value)})) is None
    event = framer.feed(value[-1:])
    assert event[0] == "list" and "12" in event[1]
    assert framer.feed(value) is None
    with pytest.raises(ValueError):
        framer.feed(b'{"length":65537}')
    assert not framer.buffer and framer.length is None
    assert framer.feed(value) is None
    assert framer.feed(codec.compact_json({"length": len(value)}))[0] == "list"


@pytest.mark.parametrize("service", ["hold_control", "timed_move"])
@pytest.mark.parametrize("paired_side", [False, True])
async def test_s6_ignored_lease_reverse_preserves_old_generation_renewal_and_stop(
    hass,
    paired,  # noqa: F811
    service,
    paired_side,
):
    pair, parent, children, left, right = paired
    if paired_side:
        c = left[1]
        client = left[2]
        device = children["left"]
    else:
        _, c, client, _, _ = await runtime(hass, mask=None, address="AA:BB:CC:DD:EE:94")
        device = await publish_runtime(hass, c)
        client.write_gatt_char.reset_mock()

    def fields(direction, generation):
        values = (
            {"control": "back_" + direction, "duration": 0.7}
            if service == "hold_control"
            else {"motor": "back", "direction": direction, "duration_ms": 700}
        )
        return {**values, "hold_owner": "dashboard", "hold_generation": generation}

    with virtual_clock():
        first = asyncio.create_task(call(hass, service, device, **fields("up", 1)))
        await asyncio.sleep(0.1)
        cancel_count = c.cancel_counter
        await call(hass, service, device, **fields("down", 2))
        assert c.cancel_counter == cancel_count and not writes(client) and not first.done()
        await asyncio.sleep(0.05)
        await call(hass, service, device, **fields("up", 1))
        await asyncio.sleep(0.3)
        assert [row[1] for row in writes(client)] == [b"\x0b\0"]
        await call(hass, service, device, **fields("up", 1))
        await call(hass, "stop_all", device)
        await first
        with pytest.raises(ServiceValidationError):
            await call(hass, service, device, **fields("up", 1))
    assert [row[1] for row in writes(client)] == [b"\x0b\0", b"\xfe\0"]
    assert not writes(right[2])
    if not paired_side:
        client.is_connected = False
        await c.async_shutdown()
