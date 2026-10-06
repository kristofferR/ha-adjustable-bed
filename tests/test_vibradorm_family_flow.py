"""One family picker and verified, transactional migration of existing receivers."""

import asyncio
from contextlib import AsyncExitStack, ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.address_lock import async_get_connect_lock
from custom_components.adjustable_bed.bluetooth_bond import BluezReadStatus, LocalBondInventory
from custom_components.adjustable_bed.bluetooth_freshness import (
    AdvertisementEvidence,
    FreshnessStatus,
)
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
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    CapabilityReport,
    _vibradorm_app_data,
    _vmatbasic_data,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import DetectionResult, get_bed_type_options
from custom_components.adjustable_bed.profile_review import (
    ProfileReviewRepairFlow,
    async_refresh_profile_review_issue,
    profile_review_mark,
)
from tests.test_vibradorm_app import make_controller as make_app
from tests.test_vibradorm_app_config import app_data
from tests.test_vibradorm_vmat import make_vmat
from tests.test_vmatbasic import make_controller as make_basic

ADDRESS = "11:22:33:44:55:66"
PREFIX = "custom_components.adjustable_bed.config_flow."


def entry_for(hass, data=None, options=None):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=4,
        minor_version=3,
        data=data
        or {
            CONF_ADDRESS: ADDRESS,
            const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_PREFERRED_ADAPTER: "auto",
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def client_for(app):
    client = (
        make_vmat("07")
        if app == "vmat"
        else make_basic("cbi")
        if app == "vmatbasic"
        else make_app(7 if app == "werkmeister" else 2, app=app)
    ).client
    assert client is not None

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    client.pair = AsyncMock()
    return client


def bluetooth_patches(stack, client):
    path = ConnectionPath("AA:BB:CC:DD:EE:FF", transport=TransportClass.LOCAL, adapter="hci0")
    native = BondEvidence(
        BondVerificationStatus.NATIVE_OS_STATE,
        BondOwner.from_path(path),
        "native",
        "now",
        kind=BondEvidenceKind.NATIVE_OS_STATE,
    )
    evidence = AdvertisementEvidence(FreshnessStatus.FRESH, source=path.source, path=path)
    stack.enter_context(
        patch(
            PREFIX + "async_wait_for_advertisement",
            new=AsyncMock(return_value=(evidence, BLEDevice(ADDRESS, "Bed", {}))),
        )
    )
    stack.enter_context(
        patch(
            PREFIX + "async_read_local_bonds",
            new=AsyncMock(return_value=LocalBondInventory(BluezReadStatus.OK)),
        )
    )
    stack.enter_context(
        patch(PREFIX + "async_predict_path", return_value=PathPrediction(path, (path,)))
    )
    stack.enter_context(patch(PREFIX + "client_source", return_value=path.source))
    stack.enter_context(patch(PREFIX + "async_path_for_source", return_value=path))
    stack.enter_context(
        patch(PREFIX + "async_verify_native_bond", new=AsyncMock(return_value=native))
    )
    stack.enter_context(patch(PREFIX + "discover_services", new=AsyncMock()))
    stack.enter_context(
        patch(
            PREFIX + "read_ble_device_info", new=AsyncMock(return_value=("Vibradorm", "receiver"))
        )
    )
    stack.enter_context(
        patch(
            "custom_components.adjustable_bed.support_proxy_logs.capture_proxy_logs",
            return_value=AsyncExitStack(),
        )
    )
    return stack.enter_context(
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client))
    )


async def select_app(hass, entry, app):
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "vibradorm"
    result = await manager.async_configure(result["flow_id"], {"app": app})
    seed = (
        {const.CONF_VIBRADORM_VMAT_REMOTE: "07"}
        if app == "vmat"
        else {const.CONF_VMATBASIC_PROFILE: "cbi"}
        if app == "vmatbasic"
        else {}
    )
    values = result["data_schema"](seed)
    result = await manager.async_configure(result["flow_id"], values)
    if result["type"] == FlowResultType.FORM and result["step_id"] in (
        "vmatbasic",
        "vibradorm_app",
    ):
        result = await manager.async_configure(result["flow_id"], result["data_schema"]({}))
    if result["type"] == FlowResultType.FORM and result["step_id"] == "manual_pairing":
        result = await manager.async_configure(result["flow_id"], {"action": "pair_now"})
    assert result["type"] == FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    return await manager.async_configure(result["flow_id"])


@pytest.mark.parametrize("app", ["caresse", "werkmeister", "vmat", "vmatbasic"])
async def test_managed_reconfigure_verifies_then_updates_same_entry_and_ids(
    hass, enable_custom_integrations, app
):
    entry = entry_for(
        hass,
        options={
            const.CONF_CONNECTION_PROFILE: "responsive",
            const.CONF_IDLE_DISCONNECT_SECONDS: 77,
        },
    )
    before, options = dict(entry.data), dict(entry.options)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(const.DOMAIN, ADDRESS)}
    )
    entity = er.async_get(hass).async_get_or_create(
        "cover", const.DOMAIN, ADDRESS + "_back", config_entry=entry, device_id=device.id
    )
    runtime = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = runtime
    old_client = client_for("caresse")
    runtime._client = old_client
    client = client_for(app)
    with (
        patch.object(
            runtime, "async_transport_operation", wraps=runtime.async_transport_operation
        ) as reservation,
        ExitStack() as stack,
    ):
        bluetooth_patches(stack, client)
        result = await select_app(hass, entry, app)
        assert not result.get("errors")
        assert result["step_id"] in ("pairing_result", "verify_connection")
        assert entry.data == before and entry.options == options
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "vibradorm_confirm"
        assert entry.data == before and entry.options == options
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"confirm": True}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert len(hass.config_entries.async_entries(const.DOMAIN)) == 1
    assert entry.unique_id == ADDRESS and entry.data[CONF_ADDRESS] == ADDRESS
    assert entry.data[const.CONF_BED_TYPE] == (
        const.BED_TYPE_VMATBASIC if app == "vmatbasic" else const.BED_TYPE_VIBRADORM_APP
    )
    assert entry.options == options
    assert dr.async_get(hass).async_get(device.id).identifiers == {(const.DOMAIN, ADDRESS)}
    assert er.async_get(hass).async_get(entity.entity_id).unique_id == entity.unique_id
    reservation.assert_called_once_with("vibradorm_setup")
    old_client.disconnect.assert_awaited_once()
    assert not client.is_connected


@pytest.mark.parametrize("app", ["caresse", "werkmeister", "vmat", "vmatbasic"])
async def test_missing_selected_roles_cannot_finish_even_with_native_bond(
    hass, enable_custom_integrations, app
):
    entry = entry_for(hass)
    before = dict(entry.data)
    client = client_for(app)
    client.services = []
    with ExitStack() as stack:
        bluetooth_patches(stack, client)
        result = await select_app(hass, entry, app)
        choices = result["data_schema"].schema["action"].config["options"]
        assert choices == ["retry", "keep"]
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(result["flow_id"], {"action": "finish"})
        assert entry.data == before
        hass.config_entries.flow.async_abort(result["flow_id"])
    assert entry.data == before
    assert not client.is_connected


@pytest.mark.parametrize("app", ["caresse", "vmatbasic"])
@pytest.mark.parametrize("disconnect_raises", [False, True])
async def test_migration_retains_unclosed_link_and_refuses_second_connect(
    hass, enable_custom_integrations, app, disconnect_raises: bool
):
    entry = entry_for(hass)
    before = dict(entry.data)
    client = client_for(app)
    client.disconnect = AsyncMock(
        side_effect=RuntimeError("Disconnect failed") if disconnect_raises else None
    )
    manager = hass.config_entries.flow
    lock = async_get_connect_lock(hass, ADDRESS)
    with ExitStack() as stack:
        connect = bluetooth_patches(stack, client)
        result = await select_app(hass, entry, app)
        assert lock.retained_setup_client is client
        assert result["data_schema"].schema["action"].config["options"] == ["retry", "keep"]
        result = await manager.async_configure(result["flow_id"], {"action": "retry"})
        if result["type"] == FlowResultType.FORM:
            assert result["step_id"] == "manual_pairing"
            result = await manager.async_configure(result["flow_id"], {"action": "pair_now"})
        await hass.async_block_till_done()
        result = await manager.async_configure(result["flow_id"])
        assert result["type"] == FlowResultType.FORM
        assert entry.data == before
        connect.assert_awaited_once()
        assert lock.retained_setup_client is client
        client.is_connected = False
        assert lock.retained_setup_client is None
        manager.async_abort(result["flow_id"])
        await hass.async_block_till_done()


async def test_vmat_migration_requires_native_proof_after_successful_role_check(
    hass, enable_custom_integrations
):
    entry = entry_for(hass)
    before = dict(entry.data)
    client = client_for("vmat")
    with ExitStack() as stack:
        bluetooth_patches(stack, client)
        path = ConnectionPath("AA:BB:CC:DD:EE:FF", transport=TransportClass.LOCAL, adapter="hci0")
        proof = BondEvidence(
            BondVerificationStatus.NATIVE_OS_STATE,
            BondOwner.from_path(path),
            "native",
            "now",
            kind=BondEvidenceKind.NATIVE_OS_STATE,
        )
        inconclusive = BondEvidence(
            BondVerificationStatus.INCONCLUSIVE, proof.owner, "native", "now"
        )
        stack.enter_context(
            patch(
                PREFIX + "async_verify_native_bond",
                new=AsyncMock(side_effect=[proof, inconclusive]),
            )
        )
        result = await select_app(hass, entry, "vmat")
        assert result["errors"] == {"base": "vmat_bond_required"}
        assert result["data_schema"].schema["action"].config["options"] == ["retry", "keep"]
        hass.config_entries.flow.async_abort(result["flow_id"])
    assert entry.data == before
    assert not client.is_connected


@pytest.mark.parametrize("change", ["data", "options"])
async def test_confirmation_rejects_concurrent_changes(hass, enable_custom_integrations, change):
    entry = entry_for(hass)
    with ExitStack() as stack:
        bluetooth_patches(stack, client_for("caresse"))
        result = await select_app(hass, entry, "caresse")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        changed = {**getattr(entry, change), const.CONF_IDLE_DISCONNECT_SECONDS: 99}
        hass.config_entries.async_update_entry(entry, **{change: changed})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"confirm": True}
        )
    assert result["reason"] == "vibradorm_configuration_changed"
    assert getattr(entry, change) == changed
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_VIBRADORM


async def test_cancelling_final_confirmation_keeps_entry_and_review_pending(
    hass, enable_custom_integrations
):
    entry = entry_for(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, const.CONF_PROFILE_REVIEW_PENDING: profile_review_mark(entry.data)},
    )
    async_refresh_profile_review_issue(hass, entry)
    before = dict(entry.data)
    with ExitStack() as stack:
        bluetooth_patches(stack, client_for("caresse"))
        result = await select_app(hass, entry, "caresse")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        hass.config_entries.flow.async_abort(result["flow_id"])
    assert entry.data == before


async def test_no_scanner_cannot_skip_migration_verification(hass, enable_custom_integrations):
    entry = entry_for(hass)
    before = dict(entry.data)
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch.object(
            AdjustableBedConfigFlow,
            "_probe_capabilities",
            new=AsyncMock(return_value=CapabilityReport(freshness=FreshnessStatus.MISSING)),
        ) as probe,
    ):
        result = await select_app(hass, entry, "vmatbasic")
        assert result["errors"] == {"base": "vibradorm_verification_required"}
        assert result["data_schema"].schema["action"].config["options"] == ["retry", "keep"]
        hass.config_entries.flow.async_abort(result["flow_id"])
    probe.assert_awaited_once()
    assert entry.data == before


async def test_cancelling_progress_closes_candidate_and_keeps_working_configuration(
    hass, enable_custom_integrations
):
    entry = entry_for(hass)
    before = dict(entry.data)
    client = client_for("caresse")
    started = asyncio.Event()

    async def verify(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    manager = hass.config_entries.flow
    with ExitStack() as stack:
        bluetooth_patches(stack, client)
        stack.enter_context(patch(PREFIX + "async_verify_native_bond", new=verify))
        result = await manager.async_init(
            const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await manager.async_configure(result["flow_id"], {"app": "caresse"})
        result = await manager.async_configure(result["flow_id"], result["data_schema"]({}))
        result = await manager.async_configure(result["flow_id"], {"action": "pair_now"})
        await started.wait()
        manager.async_abort(result["flow_id"])
        await hass.async_block_till_done()
    assert entry.data == before
    assert not client.is_connected
    client.disconnect.assert_awaited()


@pytest.mark.parametrize("app", ["caresse", "vmat", "vmatbasic"])
async def test_same_app_seeds_retained_remote_and_settings(hass, enable_custom_integrations, app):
    if app == "caresse":
        data = app_data(
            control="-1",
            **{
                const.CONF_VIBRADORM_RESTORED: True,
                const.CONF_VIBRADORM_RGB: True,
                const.CONF_VIBRADORM_FLOOR_DEFAULT: 8,
            },
        )
        expected = {
            const.CONF_VIBRADORM_CONTROL_TYPE: "-1",
            const.CONF_VIBRADORM_RGB: True,
            const.CONF_VIBRADORM_FLOOR_DEFAULT: 8,
        }
    elif app == "vmat":
        data = _vibradorm_app_data(
            {
                CONF_ADDRESS: ADDRESS,
                const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
                const.CONF_VIBRADORM_APP_PROFILE: app,
            },
            {const.CONF_VIBRADORM_VMAT_REMOTE: "12"},
        )
        expected = {const.CONF_VIBRADORM_VMAT_REMOTE: "12"}
    else:
        data = _vmatbasic_data(
            {
                CONF_ADDRESS: ADDRESS,
                const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
                const.CONF_VMATBASIC_PROFILE: "cbi",
            },
            {
                const.CONF_VMATBASIC_PROFILE: "cbi",
                const.CONF_VMATBASIC_FLOOR_LEVEL: 123,
                const.CONF_VMATBASIC_FLOOR_MINUTES: 45,
            },
        )
        expected = {const.CONF_VMATBASIC_FLOOR_LEVEL: 123, const.CONF_VMATBASIC_FLOOR_MINUTES: 45}
    entry = entry_for(hass, data)
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await manager.async_configure(result["flow_id"], {"app": app})
    values = result["data_schema"]({})
    assert all(values[key] == value for key, value in expected.items())
    assert entry.data == data
    manager.async_abort(result["flow_id"])


async def test_repairs_handoff_leaves_review_pending_until_explicit_keep(
    hass, enable_custom_integrations
):
    from homeassistant.helpers import issue_registry as ir

    entry = entry_for(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, const.CONF_PROFILE_REVIEW_PENDING: profile_review_mark(entry.data)},
    )
    async_refresh_profile_review_issue(hass, entry)
    flow = ProfileReviewRepairFlow(entry.entry_id)
    flow.hass = hass
    result = await flow.async_step_init({"issue_id": "ignored"})
    assert result["step_id"] == "vibradorm"
    result = await flow.async_step_init({"choice": "configure"})
    assert result["type"] == FlowResultType.ABORT
    assert const.CONF_PROFILE_REVIEW_PENDING in entry.data
    flow_id = result["next_flow"][1]
    hass.config_entries.flow.async_abort(flow_id)
    assert (
        ir.async_get(hass).async_get_issue(const.DOMAIN, "app_profile_review_" + entry.entry_id)
        is not None
    )
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"app": "legacy"})
    assert result["reason"] == "vibradorm_legacy_kept"
    assert const.CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert (
        ir.async_get(hass).async_get_issue(const.DOMAIN, "app_profile_review_" + entry.entry_id)
        is None
    )


@pytest.mark.parametrize("mode", [const.PAIR_MODE_SINGLE_ADDRESS, const.PAIR_MODE_SEPARATE_ADDRESS])
async def test_paired_setup_is_unchanged_until_explicit_split(
    hass, enable_custom_integrations, mode
):
    # A Vibradorm receiver on the nonrepresentative side still needs the guard.
    data = {
        const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
        const.CONF_PAIR_ID: "pair",
        const.CONF_PAIR_MODE: mode,
        const.CONF_PAIR_CHILDREN: [
            {
                const.CONF_SIDE: const.SIDE_LEFT,
                CONF_ADDRESS: ADDRESS,
                const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
            },
            {
                const.CONF_SIDE: const.SIDE_RIGHT,
                CONF_ADDRESS: ADDRESS
                if mode == const.PAIR_MODE_SINGLE_ADDRESS
                else "11:22:33:44:55:77",
                const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM,
            },
        ],
    }
    entry = entry_for(hass, data)
    manager = hass.config_entries.flow
    result = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )
    assert result["step_id"] == "vibradorm_unpair"
    assert entry.data == data
    manager.async_abort(result["flow_id"])
    assert entry.data == data
    with patch("custom_components.adjustable_bed.async_unpair_entry", new=AsyncMock()) as unpair:
        result = await manager.async_init(
            const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await manager.async_configure(result["flow_id"], {"confirm": True})
        await hass.async_block_till_done()
    assert result["reason"] == "vibradorm_pair_split_started"
    unpair.assert_awaited_once_with(hass, entry)


@pytest.mark.parametrize(
    "bed_type", [const.BED_TYPE_VIBRADORM, const.BED_TYPE_VIBRADORM_APP, const.BED_TYPE_VMATBASIC]
)
async def test_unchanged_rendered_options_keep_internal_family_route(hass, bed_type):
    data = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: bed_type}
    if bed_type == const.BED_TYPE_VIBRADORM_APP:
        data = _vibradorm_app_data(
            {**data, const.CONF_VIBRADORM_APP_PROFILE: "vmat"},
            {const.CONF_VIBRADORM_VMAT_REMOTE: "07"},
        )
    elif bed_type == const.BED_TYPE_VMATBASIC:
        data = _vmatbasic_data(data, {const.CONF_VMATBASIC_PROFILE: "cbi"})
    entry = entry_for(hass, data)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass
    result = await flow.async_step_settings()
    schema = result["data_schema"]
    assert schema is not None
    values = schema({})
    assert isinstance(values, dict)
    rows = schema.schema[const.CONF_BED_TYPE].config["options"]
    assert sum("Vibradorm:" in row["label"] for row in rows) == 1
    assert values[const.CONF_BED_TYPE] == bed_type
    result = await flow.async_step_settings(values)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == bed_type
    if bed_type == const.BED_TYPE_VIBRADORM_APP:
        assert entry.data[const.CONF_VIBRADORM_VMAT_REMOTE] == "07"
    elif bed_type == const.BED_TYPE_VMATBASIC:
        assert entry.data[const.CONF_VMATBASIC_PROFILE] == "cbi"


@pytest.mark.parametrize(
    "step,pairing",
    [
        ("manual_entry", "manual_pairing"),
        ("manual_config", "manual_pairing"),
        ("bluetooth_confirm", "bluetooth_pairing"),
    ],
)
async def test_fresh_legacy_choice_keeps_existing_pairing_route(
    hass, mock_bluetooth_service_info, step, pairing
):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, "async_step_" + step)(
        {
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Bed",
            const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM,
            const.CONF_PREFERRED_ADAPTER: "auto",
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        }
    )
    assert result["step_id"] == "vibradorm"
    with patch.object(flow, "async_step_" + pairing, new=AsyncMock()) as pair:
        await flow.async_step_vibradorm({"app": "legacy"})
    pair.assert_awaited_once_with()
    assert flow._manual_data[const.CONF_BED_TYPE] == const.BED_TYPE_VIBRADORM


async def test_repairs_does_not_link_to_a_terminated_reconfigure_flow(hass):
    entry = entry_for(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, const.CONF_PROFILE_REVIEW_PENDING: profile_review_mark(entry.data)},
    )
    flow = ProfileReviewRepairFlow(entry.entry_id)
    flow.hass = hass
    with patch.object(
        hass.config_entries.flow,
        "async_init",
        new=AsyncMock(
            return_value={"type": FlowResultType.ABORT, "reason": "reconfigure_not_supported"}
        ),
    ):
        result = await flow.async_step_init({"choice": "configure"})
    assert result["type"] == FlowResultType.ABORT
    assert "next_flow" not in result
    assert const.CONF_PROFILE_REVIEW_PENDING in entry.data


@pytest.mark.parametrize(
    "source,target",
    [
        (const.BED_TYPE_VIBRADORM_APP, const.BED_TYPE_LINAK),
        (const.BED_TYPE_LINAK, const.BED_TYPE_VIBRADORM),
    ],
)
async def test_options_can_correct_a_mistaken_bed_family(hass, source, target):
    data = (
        app_data()
        if source == const.BED_TYPE_VIBRADORM_APP
        else {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: source}
    )
    entry = entry_for(hass, data)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass
    result = await flow.async_step_settings({const.CONF_BED_TYPE: target})
    for _ in range(3):
        if result["type"] == FlowResultType.CREATE_ENTRY:
            break
        assert not result.get("errors")
        schema = result["data_schema"]
        assert schema is not None
        result = await flow.async_step_settings(schema({}))
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == target


async def test_focused_discovery_offers_one_family_with_other_candidates(
    hass, mock_bluetooth_service_info
):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    assert flow._prepare_disambiguation(
        DetectionResult(
            bed_type=const.BED_TYPE_VIBRADORM_APP,
            confidence=0.5,
            ambiguous_types=[
                const.BED_TYPE_VIBRADORM,
                const.BED_TYPE_VMATBASIC,
                const.BED_TYPE_LINAK,
            ],
        )
    )
    form = await flow.async_step_bluetooth_disambiguate()
    values = [
        option["value"]
        for option in form["data_schema"].schema["bed_type_choice"].config["options"]
    ]
    assert values == [const.BED_TYPE_VIBRADORM, const.BED_TYPE_LINAK, "show_all"]


def test_top_level_family_choice_is_single_and_searchable():
    rows = [
        row
        for row in get_bed_type_options()
        if row["value"]
        in (const.BED_TYPE_VIBRADORM, const.BED_TYPE_VIBRADORM_APP, const.BED_TYPE_VMATBASIC)
    ]
    assert len(rows) == 1
    assert all(
        app in rows[0]["label"] for app in ("VMAT", "Caresse Diamant", "Werkmeister", "V-MAT Basic")
    )
