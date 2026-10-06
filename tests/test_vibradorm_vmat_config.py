"""Explicit VMAT configuration, process state and public entity capabilities."""

import asyncio
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _vibradorm_app_data,
    _vibradorm_app_errors,
)
from custom_components.adjustable_bed.vibradorm_app_state import get_vibradorm_app_session_intent
from custom_components.adjustable_bed.vibradorm_vmat_profiles import VMAT_REMOTES
from tests.test_vibradorm_vmat import make_vmat


@pytest.mark.parametrize("disconnect_kind", ["noop", "error", "cancel", "task_cancel"])
@pytest.mark.parametrize("mode", ["pair", "replace_local"])
@pytest.mark.parametrize("native_proved", [False, True])
async def test_public_progress_worker_retains_failed_setup_across_retry_removal_and_replacement(
    hass, disconnect_kind, mode, native_proved,
):
    from contextlib import AsyncExitStack

    from bleak.backends.device import BLEDevice
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.adapter import AdapterSelectionResult
    from custom_components.adjustable_bed.address_lock import async_get_connect_lock
    from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner
    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondEvidenceKind,
        BondOwner,
        BondVerificationStatus,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.vibradorm_vmat_setup import QUERY_STAGES

    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})

    def new_flow():
        flow = AdjustableBedConfigFlow()
        flow.context = {}
        flow.hass = hass
        flow._manual_data = dict(data)
        return flow

    flow = new_flow()
    c = make_vmat("07")
    c.client.pair = AsyncMock()
    queried = 0

    async def write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            return
        _, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        c.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    async def disconnect():
        if disconnect_kind == "error":
            raise BleakError("disconnect failed")
        if disconnect_kind == "cancel":
            raise asyncio.CancelledError
        if disconnect_kind == "task_cancel":
            task = asyncio.current_task()
            assert task is not None
            task.cancel()
            await asyncio.sleep(0)

    c.client.write_gatt_char.side_effect = write
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    device = BLEDevice(address, "Bed", {"source": source})
    module = "custom_components.adjustable_bed.config_flow."
    lock = async_get_connect_lock(hass, address)
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=c.client)) as establish,
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native if native_proved else unknown])),
    ):
        async def worker():
            return await flow._async_pair_and_classify(address, mode, device)

        if disconnect_kind in ("cancel", "task_cancel"):
            with pytest.raises(asyncio.CancelledError):
                await flow._async_guarded_worker(worker)
        else:
            assert not (await flow._async_guarded_worker(worker)).succeeded
        assert queried == 7
        establish.assert_awaited_once()
        assert flow._operation_client is c.client
        assert lock.retained_setup_client is c.client
        # Stabilize cancellation variants for subsequent real retry/teardown calls.
        c.client.disconnect.side_effect = None
        with pytest.raises(ConnectionError):
            flow.async_track_client(None)
        with pytest.raises(ConnectionError):
            flow.async_track_client(make_vmat("07").client)
        flow.async_begin_operation(address=address)
        await hass.async_block_till_done()
        assert not (await flow._async_guarded_worker(worker)).succeeded
        establish.assert_awaited_once()
        flow.async_remove()
        await hass.async_block_till_done()
        assert flow._operation_client is c.client
        # HA-owned address state survives the removed flow's terminal task.
        replacement = new_flow()

        async def replacement_worker():
            return await replacement._async_pair_and_classify(address, mode, device)

        assert not (await replacement._async_guarded_worker(replacement_worker)).succeeded
        establish.assert_awaited_once()
    assert lock.retained_setup_client is c.client
    async with async_get_connect_lock(hass, "22:33:44:55:66:77"):
        pass
    # Configured runtime and standalone capture share this exact guarded lock.
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    runtime_module = "custom_components.adjustable_bed.coordinator."
    with (
        patch(runtime_module + "select_adapter", return_value=AdapterSelectionResult(device, source, -50, True, [source])),
        patch(runtime_module + "async_connection_paths", return_value=()),
        patch(runtime_module + "establish_connection", new=AsyncMock()) as runtime_connect,
    ):
        assert not await coordinator.async_connect()
        runtime_connect.assert_not_awaited()
    with pytest.raises(ConnectionError):
        async with async_get_connect_lock(hass, address.lower()):
            pytest.fail("capture/connection admission cannot bypass the retained link")
    diagnostic_module = "custom_components.adjustable_bed.ble_diagnostics."
    with (
        patch(diagnostic_module + "select_adapter", new=AsyncMock(return_value=AdapterSelectionResult(device, source, -50, True, [source]))),
        patch(diagnostic_module + "establish_connection", new=AsyncMock()) as diagnostic_connect,
    ):
        with pytest.raises(ConnectionError):
            await BLEDiagnosticRunner(hass, address)._connect()
        diagnostic_connect.assert_not_awaited()
    # Observed closure, rather than an RPC return, permits the next real setup.
    c.client.is_connected = False
    assert lock.retained_setup_client is None
    recovered = make_vmat("07")
    recovered.client.pair = AsyncMock()
    queried = 0

    async def recovered_write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            return
        _, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        recovered.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    async def close_recovered():
        recovered.client.is_connected = False

    recovered.client.write_gatt_char.side_effect = recovered_write
    recovered.client.disconnect.side_effect = close_recovered
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=recovered.client)) as establish,
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native])),
    ):
        assert (await replacement._async_guarded_worker(replacement_worker)).succeeded
        assert queried == 7
        establish.assert_awaited_once()
        assert replacement._operation_client is None
        assert lock.retained_setup_client is None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("mode", ["pair", "replace_local"])
@pytest.mark.parametrize("disconnect_kind", ["noop", "error"])
@pytest.mark.parametrize("pre_stage", ["native_present", "route_mismatch"])
async def test_vmat_pre_stage_failure_retains_native_owner(hass, mode, disconnect_kind, pre_stage):
    from contextlib import AsyncExitStack

    from bleak.backends.device import BLEDevice

    from custom_components.adjustable_bed.address_lock import async_get_connect_lock
    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondEvidenceKind,
        BondOwner,
        BondVerificationStatus,
    )

    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    if pre_stage == "route_mismatch":
        flow._pairing_retry_source = "22:33:44:55:66:77"
    c = make_vmat("07")
    c.client.pair = AsyncMock()

    async def disconnect():
        if disconnect_kind == "error":
            raise BleakError("disconnect failed")

    c.client.disconnect = AsyncMock(side_effect=disconnect)
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    module = "custom_components.adjustable_bed.config_flow."
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=c.client)),
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(return_value=native)),
    ):
        async def worker():
            return await flow._async_pair_and_classify(address, mode, BLEDevice(address, "Bed", {}))

        assert not (await flow._async_guarded_worker(worker)).succeeded
        assert c.client.is_connected
        assert flow._operation_client is c.client
        assert async_get_connect_lock(hass, address).retained_setup_client is c.client
        c.client.write_gatt_char.assert_not_awaited()
        c.client.pair.assert_not_awaited()
    c.client.is_connected = False
    await flow._async_release_client()
    assert flow._operation_client is None


@pytest.mark.parametrize("remote", VMAT_REMOTES)
def test_normalization_uses_remote_not_submitted_capability_flags(remote):
    profile = VMAT_REMOTES[remote]
    data = _vibradorm_app_data({const.CONF_VIBRADORM_APP_PROFILE: "vmat"}, {
        const.CONF_VIBRADORM_VMAT_REMOTE: remote,
        const.CONF_VIBRADORM_CONTROL_TYPE: "99",
        const.CONF_HAS_MASSAGE: not profile.massage,
        const.CONF_VIBRADORM_FLOOR_LIGHT: not profile.floor_light,
    })
    assert _vibradorm_app_errors(data) == {}
    assert data[const.CONF_VIBRADORM_CONTROL_TYPE] == str(profile.control_type)
    assert data[const.CONF_HAS_MASSAGE] is profile.massage
    assert data[const.CONF_VIBRADORM_FLOOR_LIGHT] is profile.floor_light
    assert data[const.CONF_VIBRADORM_FLOOR_DEFAULT] == (6 if profile.light_extension else 8)


@pytest.mark.parametrize("app", ["caresse", "werkmeister"])
async def test_public_options_switch_from_vmat_removes_remote_before_factory(hass, app):
    """The profile switch now uses guided setup, retaining this ledger binding."""
    from homeassistant.config_entries import SOURCE_RECONFIGURE
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    data = _vibradorm_app_data({
        CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    data[const.CONF_VIBRADORM_APP_METADATA] = {"device_name": "old VMAT"}
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedConfigFlow()
    flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    flow.hass = hass
    await flow.async_step_reconfigure()
    initial = await flow.async_step_vibradorm({"app": "vmat"})
    schema = initial["data_schema"]
    assert callable(schema)
    submission = schema({})
    assert isinstance(submission, dict)
    submission[const.CONF_VIBRADORM_APP_PROFILE] = app
    rebuilt = await flow.async_step_vibradorm_app(submission)
    assert rebuilt["type"] == FlowResultType.FORM
    assert not rebuilt["errors"]
    schema = rebuilt["data_schema"]
    assert callable(schema)
    defaults = schema({})
    assert isinstance(defaults, dict)
    assert const.CONF_VIBRADORM_VMAT_REMOTE not in defaults
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()):
        await flow.async_step_vibradorm_app(defaults)
    flow._vibradorm_verified = True
    flow._create_selected_app_entry(title="Bed", data=flow._manual_data)
    finished = await flow.async_step_vibradorm_confirm({"confirm": True})
    assert finished["type"] == FlowResultType.ABORT
    assert entry.data[const.CONF_VIBRADORM_APP_PROFILE] == app
    assert const.CONF_VIBRADORM_VMAT_REMOTE not in entry.data
    assert const.CONF_VIBRADORM_APP_METADATA not in entry.data
    assert const.CONF_VIBRADORM_VMAT_REMOTE not in _vibradorm_app_data(entry.data, {})
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, const.BED_TYPE_VIBRADORM_APP, None, None)
    assert controller.profile.app_profile == app
    assert coordinator.vibradorm_app_session_intent is not None
    await coordinator.async_shutdown()


@pytest.mark.parametrize("mode", ["pair", "replace_local"])
async def test_public_setup_accepts_native_closure_after_disconnect_rpc_error(hass, mode):
    from contextlib import AsyncExitStack

    from bleak.backends.device import BLEDevice

    from custom_components.adjustable_bed.address_lock import async_get_connect_lock
    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondEvidenceKind,
        BondOwner,
        BondVerificationStatus,
    )

    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    c = make_vmat("07")
    c.client.pair = AsyncMock()
    queried = 0
    from custom_components.adjustable_bed.vibradorm_vmat_setup import QUERY_STAGES

    async def write(char, packet, **kwargs):
        nonlocal queried
        if packet == bytes.fromhex("01a7"):
            return
        _, expected, prefix, _ = QUERY_STAGES[queried]
        assert packet == expected
        c.client.start_notify.call_args.args[1](char, bytearray(prefix + b"A"))
        queried += 1

    async def disconnect():
        c.client.is_connected = False
        raise BleakError("disconnect RPC failed after observed closure")

    c.client.write_gatt_char.side_effect = write
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    module = "custom_components.adjustable_bed.config_flow."
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=c.client)),
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native])),
    ):
        async def worker():
            return await flow._async_pair_and_classify(address, mode, BLEDevice(address, "Bed", {}))

        result = await flow._async_guarded_worker(worker)
        assert result.succeeded and result.payload.proves_bond
        assert queried == 7
        c.client.pair.assert_awaited_once()
        c.client.disconnect.assert_awaited_once()
        assert flow._operation_client is None
        assert async_get_connect_lock(hass, address).retained_setup_client is None
        assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["variant"] == "A"


async def test_separate_address_options_preserve_each_vmat_remote(hass):
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left = _vibradorm_app_data({
        CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    right = _vibradorm_app_data({**left, CONF_ADDRESS: "22:33:44:55:66:77"}, {const.CONF_VIBRADORM_VMAT_REMOTE: "13"})
    data = build_pair_entry_data(left, right, name="Two beds")
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    rendered = await flow.async_step_settings()
    schema = rendered["data_schema"]
    assert callable(schema)
    submission = schema({})
    assert isinstance(submission, dict)
    submission[const.CONF_IDLE_DISCONNECT_SECONDS] = 55
    assert (await flow.async_step_settings(submission))["type"] == FlowResultType.CREATE_ENTRY
    assert [child[const.CONF_VIBRADORM_VMAT_REMOTE] for child in entry.data[const.CONF_PAIR_CHILDREN]] == ["07", "13"]
    assert all(child[const.CONF_VIBRADORM_APP_PROFILE] == "vmat" for child in entry.data[const.CONF_PAIR_CHILDREN])


@pytest.mark.parametrize(("remote", "missing"), [("00", None), ("00", "command"), ("00", "light"), ("07", None), ("07", "cbi")])
async def test_public_prebonded_setup_validates_ordinary_profile_roles(hass, remote, missing):
    from contextlib import AsyncExitStack

    from bleak.backends.device import BLEDevice

    from custom_components.adjustable_bed.beds.vibradorm_app import CBI, COMMAND, LIGHT
    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondEvidenceKind,
        BondOwner,
        BondVerificationStatus,
    )

    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    flow = AdjustableBedConfigFlow()
    flow.context, flow.hass = {}, hass
    flow._manual_data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: remote})
    c = make_vmat(remote)
    if missing is not None:
        uuid = {"command": COMMAND, "light": LIGHT, "cbi": CBI}[missing]
        for service in c.client.services:
            service.characteristics = [char for char in service.characteristics if char.uuid != uuid]
    c.client.pair = AsyncMock()

    async def disconnect():
        c.client.is_connected = False

    c.client.disconnect = AsyncMock(side_effect=disconnect)
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    module = "custom_components.adjustable_bed.config_flow."
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=c.client)),
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(return_value=native)),
    ):
        async def worker():
            return await flow._async_pair_and_classify(address, "pair", BLEDevice(address, "Bed", {}))

        assert (await flow._async_guarded_worker(worker)).succeeded is (missing is None)
    c.client.write_gatt_char.assert_not_awaited()
    c.client.start_notify.assert_not_awaited()
    c.client.pair.assert_not_awaited()
    assert not c.client.is_connected


@pytest.mark.parametrize("mode", ["pair", "replace_local"])
async def test_public_setup_transport_write_timeout_never_pairs(hass, mode):
    from contextlib import AsyncExitStack

    from bleak.backends.device import BLEDevice

    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondOwner,
        BondVerificationStatus,
    )
    from custom_components.adjustable_bed.setup_operation import OperationOutcome
    from custom_components.adjustable_bed.vibradorm_vmat_setup import QUERY_STAGES

    address, source = "11:22:33:44:55:66", "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    flow = AdjustableBedConfigFlow()
    flow.context, flow.hass = {}, hass
    flow._manual_data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    c = make_vmat("07")
    c.client.pair = AsyncMock()

    async def write(_char, packet, **kwargs):
        if packet != bytes.fromhex("01a7"):
            assert packet == QUERY_STAGES[0][1]
            raise TimeoutError("query transport delivery timed out")

    async def disconnect():
        c.client.is_connected = False

    c.client.write_gatt_char.side_effect = write
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    module = "custom_components.adjustable_bed.config_flow."
    with (
        patch("custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs", return_value=AsyncExitStack()),
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=c.client)),
        patch(module + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(module + "client_source", return_value=source),
        patch(module + "async_path_for_source", return_value=path),
        patch(module + "async_verify_native_bond", new=AsyncMock(return_value=unknown)),
    ):
        async def worker():
            return await flow._async_pair_and_classify(address, mode, BLEDevice(address, "Bed", {}))

        assert (await flow._async_guarded_worker(worker)).outcome is OperationOutcome.TIMEOUT
    assert [call.args[1] for call in c.client.write_gatt_char.call_args_list] == [QUERY_STAGES[0][1], bytes.fromhex("01a7")]
    c.client.pair.assert_not_awaited()
    c.client.stop_notify.assert_awaited_once()
    assert not c.client.is_connected


@pytest.mark.asyncio
async def test_two_step_app_form_requires_remote_then_enters_existing_bond_flow(hass):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = {CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP}
    result = await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_APP_PROFILE: "vmat"})
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert fields == {const.CONF_VIBRADORM_APP_PROFILE, const.CONF_VIBRADORM_VMAT_REMOTE}
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pairing:
        await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_VMAT_REMOTE: "11"})
    pairing.assert_awaited_once()
    assert flow._manual_data[const.CONF_MOTOR_COUNT] == 3
    assert flow._manual_data[const.CONF_DISABLE_ANGLE_SENSING] is True


def test_remote_change_clears_metadata_even_when_control_type_is_unchanged():
    before = _vibradorm_app_data({const.CONF_VIBRADORM_APP_PROFILE: "vmat"}, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    before[const.CONF_VIBRADORM_APP_METADATA] = {"model": "old", "xmc_status": "1"}
    after = _vibradorm_app_data(before, {const.CONF_VIBRADORM_VMAT_REMOTE: "08"})
    assert after[const.CONF_VIBRADORM_CONTROL_TYPE] == before[const.CONF_VIBRADORM_CONTROL_TYPE]
    assert const.CONF_VIBRADORM_APP_METADATA not in after


def test_reconnect_retains_all_accessory_intent_but_another_remote_does_not(hass):
    kwargs = {"app_profile": "vmat", "control_type": 8, "remembered_floor_default": 8}
    a = get_vibradorm_app_session_intent(hass, "11:22:33:44:55:66", remote="07", **kwargs)
    a.floor.level = 3
    a.timer.enabled, a.timer.minutes = True, 30
    a.mood["effect"] = "disco"
    a.massage.zones = (2, 4)
    assert get_vibradorm_app_session_intent(hass, "11:22:33:44:55:66", remote="07", **kwargs) is a
    b = get_vibradorm_app_session_intent(hass, "11:22:33:44:55:66", remote="08", **kwargs)
    assert b.floor.level == 0 and b.timer.minutes == 0 and b.massage.zones == (0, 0)
    assert b.mood == {}


@pytest.mark.parametrize("remote", VMAT_REMOTES)
def test_profile_exposes_only_bounded_public_controls(remote):
    c = make_vmat(remote)
    numbers = {spec.key: (spec.native_min_value, spec.native_max_value) for spec in c.controller_number_specs}
    assert ("vibradorm_app_floor_timer_minutes" in numbers) is c.profile.floor_light
    assert ("vibradorm_app_mood_speed" in numbers) is c.profile.rgb
    assert ("vibradorm_app_massage_speed" in numbers) is c.profile.massage
    selects = {spec.key: spec.options for spec in c.controller_select_specs}
    if c.profile.rgb:
        assert len(selects["vibradorm_app_mood_palette"]) == 18
        assert selects["vibradorm_app_mood_effect"] == ("sunrise", "rainbow", "disco")
        assert numbers["vibradorm_app_mood_speed"] == (0, 8)
    if c.profile.massage:
        assert selects["vibradorm_app_massage_wave"] == ("1", "2", "3", "4")
        assert numbers["vibradorm_app_massage_speed"] == (1, 5)
    assert not c.position_number_specs


@pytest.mark.asyncio
@pytest.mark.parametrize("remote", ["00", "07", "11", "12", "13"])
async def test_actual_entity_factories_follow_remote_gates(hass, remote):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.number import _number_entities_for
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from custom_components.adjustable_bed.switch import _switch_entities_for
    from tests.test_malouf_app_entities import configure_entity_runtime

    c = make_vmat(remote)
    runtime = configure_entity_runtime(hass, c, const.BED_TYPE_VIBRADORM_APP)
    light_keys = {entity.translation_key for entity in _light_entities_for(hass, runtime)}
    number_keys = {entity.translation_key for entity in _number_entities_for(hass, runtime)}
    switch_keys = {entity.translation_key for entity in _switch_entities_for(hass, runtime)}
    button_keys = {entity.translation_key for entity in _button_entities_for(hass, runtime)}
    sensor_keys = {entity.translation_key for entity in _sensor_entities_for(hass, runtime)}
    assert ("vibradorm_app_mood_speed" in number_keys) is c.profile.rgb
    assert ("vibradorm_app_massage_speed" in number_keys) is c.profile.massage
    assert ("vibradorm_app_floor_timer_minutes" in number_keys) is c.profile.floor_light
    assert "vibradorm_app_opmode" in sensor_keys
    assert "vibradorm_app_main_firmware_article" in sensor_keys
    assert ("vibradorm_app_sync_observed" in sensor_keys) is c.profile.sync
    assert ("massage_head_toggle" in button_keys) is c.profile.massage
    assert ("massage_foot_toggle" in button_keys) is c.profile.massage
    assert ("under_bed_lights" in switch_keys) is c.profile.floor_light
    assert light_keys == set()  # No arbitrary RGB light or measured on/off feedback.


@pytest.mark.asyncio
@pytest.mark.parametrize("restored", [False, True])
async def test_selected_vmat_entry_discards_previous_app_selection_intent(hass, restored):
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.vibradorm_app_state import mark_vibradorm_app_selection

    address = "11:22:33:44:55:66"
    old = mark_vibradorm_app_selection(
        hass, address, app_profile="caresse", control_type=5,
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    data = _vibradorm_app_data({
        CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: "vmat",
        const.CONF_VIBRADORM_RESTORED: restored,
    }, {const.CONF_VIBRADORM_VMAT_REMOTE: "07"})
    result = flow._create_selected_app_entry(title="VMAT", data=data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    restored_old = get_vibradorm_app_session_intent(
        hass, address, app_profile="caresse", control_type=5,
        remembered_floor_default=6,
    )
    assert restored_old is not old
    assert restored_old.floor.level == 0
    vmat = get_vibradorm_app_session_intent(
        hass, address, app_profile="vmat", control_type=8,
        remembered_floor_default=8, remote="07",
    )
    assert vmat.floor.level == 0


@pytest.mark.asyncio
async def test_unverified_native_bond_cannot_save_a_configured_vmat_address(hass):
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.setup_operation import OperationOutcome, OperationResult

    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = _vibradorm_app_data(
        {CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_VIBRADORM_APP_PROFILE: "vmat"},
        {const.CONF_VIBRADORM_VMAT_REMOTE: "07"},
    )
    flow._pairing_result_shown = True
    flow.operation.result = OperationResult(outcome=OperationOutcome.SUCCESS, payload=None)
    result = await flow.async_step_pairing_result({"action": "finish"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "vmat_bond_required"}
    assert not flow._manual_data.get(const.CONF_BLE_BOND_ESTABLISHED)


@pytest.mark.asyncio
@pytest.mark.parametrize("absent", [False, True])
@pytest.mark.parametrize("cleanup", ["normal", "close_error", "close_cancel", "task_cancel", "disconnect_error", "disconnect_cancel", "disconnect_noop", "disconnect_error_without_close_cancel", "disconnect_cancel_without_close_cancel", "disconnect_noop_after_close_cancel"])
async def test_real_setup_stages_then_pair_proof_close_disconnect_and_metadata_retention(hass, absent, cleanup):
    from bleak.backends.device import BLEDevice

    from custom_components.adjustable_bed.bluetooth_transport import (
        ConnectionPath,
        PathPrediction,
        TransportClass,
    )
    from custom_components.adjustable_bed.bond_verification import (
        BondEvidence,
        BondEvidenceKind,
        BondOwner,
        BondVerificationStatus,
    )
    from custom_components.adjustable_bed.vibradorm_vmat_setup import QUERY_STAGES

    address = "11:22:33:44:55:66"
    source = "AA:BB:CC:DD:EE:FF"
    path = ConnectionPath(source, transport=TransportClass.LOCAL, adapter="hci0")
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    native_absent = BondEvidence(
        BondVerificationStatus.NATIVE_ABSENT, BondOwner.from_path(path), "native", "now",
        kind=BondEvidenceKind.NATIVE_OS_STATE, error="native_bond_not_stored",
    )
    flow = AdjustableBedConfigFlow()
    flow.context, flow.hass = {}, hass
    flow._manual_data = _vibradorm_app_data(
        {CONF_ADDRESS: address, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP, const.CONF_VIBRADORM_APP_PROFILE: "vmat"},
        {const.CONF_VIBRADORM_VMAT_REMOTE: "07"},
    )
    c = make_vmat("07")
    events = []
    queries = 0

    async def write(char, packet, **kwargs):
        nonlocal queries
        if packet == bytes.fromhex("01a7"):
            events.append("close")
            if cleanup == "close_error":
                raise BleakError("close failed")
            if cleanup == "task_cancel":
                task = asyncio.current_task()
                assert task is not None
                task.cancel()
                await asyncio.sleep(0)
            if cleanup in ("close_cancel", "disconnect_error", "disconnect_cancel", "disconnect_noop_after_close_cancel"):
                raise asyncio.CancelledError
            return
        field, expected, prefix, _ = QUERY_STAGES[queries]
        assert packet == expected
        raw = prefix + (b"\x81" if field in ("xmc_status", "opmode") else field.encode())
        c.client.start_notify.call_args.args[1](char, bytearray(raw))
        queries += 1

    async def connect(*args, **kwargs):
        assert kwargs["timeout"] == 5
        assert "pair" not in kwargs
        events.append("connect")
        return c.client

    async def pair():
        assert queries == 7
        events.append("pair")

    async def disconnect():
        events.append("disconnect")
        if cleanup.startswith("disconnect_error"):
            raise BleakError("disconnect failed")
        if cleanup.startswith("disconnect_cancel"):
            raise asyncio.CancelledError
        if not cleanup.startswith("disconnect_noop"):
            c.client.is_connected = False

    c.client.write_gatt_char.side_effect = write
    c.client.pair = AsyncMock(side_effect=pair)
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    prefix = "custom_components.adjustable_bed.config_flow."
    expected_error = (
        ConnectionError if cleanup == "disconnect_noop"
        else BleakError if cleanup == "disconnect_error_without_close_cancel"
        else asyncio.CancelledError if cleanup not in ("normal", "close_error")
        else None
    )
    with (
        patch("bleak_retry_connector.establish_connection", side_effect=connect),
        patch(prefix + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(prefix + "client_source", return_value=source),
        patch(prefix + "async_path_for_source", return_value=path),
        patch(prefix + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native_absent if absent else native])),
        patch.object(flow, "async_track_client", new=MagicMock()) as track,
        (pytest.raises(expected_error) if expected_error is not None else nullcontext()),
    ):
        result = await flow._attempt_pairing_with_capture(
            address, request_bond=True, track_for_flow_cleanup=True,
            device=BLEDevice(address, "Bed", {}), preferred_adapter="auto",
        )
        assert result.proves_bond is not absent
        if absent:
            from custom_components.adjustable_bed.setup_operation import OperationOutcome

            assert result.proves_native_bond_absent
            with patch.object(flow, "_attempt_pairing", new=AsyncMock(return_value=result)):
                classified = await flow._async_pair_and_classify(address, "pair")
            assert classified.outcome is OperationOutcome.BOND_VERIFICATION_FAILED
            assert classified.payload is result
    assert track.call_args_list[0].args == (c.client,)
    assert track.call_args_list[-1].args == (
        c.client if cleanup.startswith("disconnect_") else None,
    )
    assert events == ["connect", "pair", "close", "disconnect"]
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["opmode"] == "-127"
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["xmc_status"] == "129"
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["revision_id"] == "revision_id"
