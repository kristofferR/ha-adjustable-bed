"""Native pairing provenance and first-bond ordering for the explicit app profile."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children
from custom_components.adjustable_bed.beds.vibradorm_app import (
    CBI,
    COMMAND,
    INFO_FIELDS,
    RESPONSE,
    VibradormAppController,
    VibradormAppMetadata,
    async_prepare_vibradorm_app_pairing,
)
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.bond_verification import (
    BondEvidence,
    BondEvidenceKind,
    BondOwner,
    BondVerificationStatus,
    build_bond_context,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_VIBRADORM_APP,
    CONF_BED_TYPE,
    CONF_BLE_BOND_ATTEMPTED_SOURCE,
    CONF_BLE_BOND_CONTEXT,
    CONF_BLE_BOND_ESTABLISHED,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_SIDE,
    CONF_VIBRADORM_APP_METADATA,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_DEFAULT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.vibradorm_app_state import (
    clear_vibradorm_app_session_intent,
    get_vibradorm_app_session_intent,
    mark_vibradorm_app_selection,
)

from .conftest import TEST_ADDRESS, TEST_NAME, make_controller_mock

_LOCAL = ConnectionPath(source="11:22:33:44:55:66", transport=TransportClass.LOCAL, adapter="hci0")
_PROXY = ConnectionPath(source="proxy-source", transport=TransportClass.PROXY)
_METADATA = VibradormAppMetadata("model", "firmware", "software", "article")
_MODULE = "custom_components.adjustable_bed.coordinator"
_HELPER = "custom_components.adjustable_bed.beds.vibradorm_app.async_prepare_vibradorm_app_pairing"


def _evidence(path: ConnectionPath, positive: bool = False) -> BondEvidence:
    return BondEvidence(
        BondVerificationStatus.NATIVE_OS_STATE if positive else BondVerificationStatus.INCONCLUSIVE,
        BondOwner.from_path(path), "native_probe", "now", kind=BondEvidenceKind.NATIVE_OS_STATE,
    )


@pytest.fixture
def coordinator(hass: HomeAssistant) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, title=TEST_NAME, data={
        CONF_ADDRESS: TEST_ADDRESS, CONF_NAME: TEST_NAME, CONF_BED_TYPE: BED_TYPE_VIBRADORM_APP,
        CONF_VIBRADORM_APP_PROFILE: "caresse", CONF_VIBRADORM_CONTROL_TYPE: 2,
    })
    entry.add_to_hass(hass)
    result = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = result
    result._connection_path = _LOCAL
    client = MagicMock(spec=BleakClient)
    client.is_connected = True
    client.pair = AsyncMock()
    client.disconnect = AsyncMock()
    client.read_gatt_char = AsyncMock()
    result._client = client
    return result


@pytest.mark.parametrize("source", [None, "unknown", "other-source", _LOCAL.source])
def test_legacy_marker_is_not_native_proof(
    coordinator: AdjustableBedCoordinator, source: str | None
) -> None:
    coordinator._persist_bond_flags(established=True)
    device = MagicMock(details={"props": {"Bonded": True, "Paired": True}})
    assert not coordinator._device_reports_existing_bond(device)
    assert not coordinator._unverified_marker_applies(source)
    details: dict = {}
    _, requested, after_discovery = coordinator._prepare_pairing_attempt(device, details, source)
    assert requested and after_discovery
    assert details["os_bond_reported"] is False


def test_marker_scope_requires_exact_context_or_attempt_source(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    context = build_bond_context(_evidence(_LOCAL, True))
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_BLE_BOND_CONTEXT: context,
        CONF_BLE_BOND_ATTEMPTED_SOURCE: _PROXY.source,
    })
    assert coordinator._unverified_marker_applies(_LOCAL.source)
    assert coordinator._unverified_marker_applies(_PROXY.source)
    assert not coordinator._unverified_marker_applies(None)
    assert not coordinator._unverified_marker_applies("other-source")


async def test_existing_exact_native_proof_skips_first_information_and_pair(
    coordinator: AdjustableBedCoordinator
) -> None:
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL, True)), patch(
        _HELPER, new_callable=AsyncMock
    ) as info:
        assert await coordinator._async_pair_on_live_link({})
    info.assert_not_called()
    coordinator.client.pair.assert_not_called()
    context = coordinator.entry.data[CONF_BLE_BOND_CONTEXT]
    assert context["evidence_kind"] == "native_os_state"
    assert context["source"] == _LOCAL.source
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert not coordinator.last_bond_evidence.proves_stale_host_bond


async def test_live_native_repair_does_not_write_an_intermediate_false_marker(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_BLE_BOND_ESTABLISHED: True,
        CONF_BLE_BOND_CONTEXT: {**build_bond_context(_evidence(_LOCAL, True)), "verified_at": "before"},
    })
    coordinator._ble_bond_established = True
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL, True)), patch.object(
        coordinator, "_async_persist_config", wraps=coordinator._async_persist_config
    ) as persist:
        assert await coordinator.async_pair_now()
    persist.assert_called_once()
    assert persist.call_args.args[0][CONF_BLE_BOND_ESTABLISHED] is True
    assert coordinator.consume_internal_entry_update(coordinator.entry)


async def test_first_bond_information_precedes_rpc_and_native_proof(
    coordinator: AdjustableBedCoordinator
) -> None:
    trace: list[str] = []

    async def info(*args, **kwargs):
        trace.append("information")
        assert args == (coordinator.client, "caresse", 2)
        assert kwargs["cancel_event"] is None
        return _METADATA

    async def pair():
        trace.append("pair")

    coordinator.client.pair.side_effect = pair
    with patch(f"{_MODULE}.async_verify_native_bond", side_effect=[
        _evidence(_LOCAL), _evidence(_LOCAL, True)
    ]) as native, patch(_HELPER, side_effect=info):
        assert await coordinator._async_pair_on_live_link({})
    assert trace == ["information", "pair"]
    assert native.await_count == 2
    assert coordinator.controller_state == {
        "vibradorm_app_model": "model", "vibradorm_app_firmware": "firmware",
        "vibradorm_app_software": "software", "vibradorm_app_main_firmware_article": "article",
    }
    assert coordinator.entry.data[CONF_VIBRADORM_APP_METADATA] == {
        "model": "model", "firmware": "firmware", "software": "software",
        "main_firmware_article": "article",
    }
    coordinator.client.read_gatt_char.assert_not_called()


async def test_fresh_metadata_and_replacement_native_marker_use_one_guarded_write(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_BLE_BOND_ESTABLISHED: True,
        CONF_VIBRADORM_APP_METADATA: {"model": "old"},
    })
    coordinator._ble_bond_established = True
    with patch(f"{_MODULE}.async_verify_native_bond", side_effect=[
        _evidence(_LOCAL), _evidence(_LOCAL, True)
    ]), patch(_HELPER, return_value=_METADATA), patch.object(
        coordinator, "_async_persist_config", wraps=coordinator._async_persist_config
    ) as persist:
        assert await coordinator._async_pair_on_live_link({})
    persist.assert_called_once()
    assert coordinator.entry.data[CONF_VIBRADORM_APP_METADATA]["model"] == "model"
    assert coordinator.entry.data[CONF_BLE_BOND_CONTEXT]["evidence_kind"] == "native_os_state"
    assert coordinator.consume_internal_entry_update(coordinator.entry)


async def test_proxy_rpc_success_is_only_source_scoped_unverified_attempt(
    coordinator: AdjustableBedCoordinator
) -> None:
    coordinator._connection_path = _PROXY
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_PROXY)), patch(
        _HELPER, return_value=_METADATA
    ) as info, patch.object(coordinator, "_async_raise_pairing_issue", new_callable=AsyncMock) as issue:
        assert not await coordinator._async_pair_on_live_link({})
        assert not await coordinator._async_pair_on_live_link({})
    assert coordinator.entry.data[CONF_BLE_BOND_ATTEMPTED_SOURCE] == _PROXY.source
    assert CONF_BLE_BOND_CONTEXT not in coordinator.entry.data
    assert coordinator.last_bond_evidence.kind is BondEvidenceKind.NATIVE_OS_STATE
    assert not coordinator.last_bond_evidence.proves_bond
    assert coordinator._last_bond_verification["status"] in ("unverified", "inconclusive")
    assert info.await_count == 1
    assert coordinator.client.pair.await_count == 1
    issue.assert_awaited_once()
    assert not coordinator._unverified_marker_applies(_LOCAL.source)


@pytest.mark.parametrize("error", [NotImplementedError(), BleakError("pairing rejected")])
async def test_failed_native_pair_keeps_live_link_without_proof(
    coordinator: AdjustableBedCoordinator, error: Exception
) -> None:
    coordinator.client.pair.side_effect = error
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, return_value=_METADATA
    ), patch.object(coordinator, "_async_raise_pairing_issue", new_callable=AsyncMock) as issue:
        assert not await coordinator._async_pair_on_live_link({})
    coordinator.client.disconnect.assert_not_called()
    assert not coordinator.last_bond_evidence.proves_bond
    assert CONF_BLE_BOND_ATTEMPTED_SOURCE not in coordinator.entry.data
    issue.assert_awaited_once()


async def test_runtime_native_probe_keeps_unverified_link_but_repair_cannot_succeed(
    coordinator: AdjustableBedCoordinator
) -> None:
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, return_value=_METADATA
    ), patch.object(coordinator, "_async_raise_pairing_issue", new_callable=AsyncMock):
        assert await coordinator._async_verify_bonded()
        assert not await coordinator._async_pair_live_and_verify()
    coordinator.client.read_gatt_char.assert_not_called()
    coordinator.client.disconnect.assert_not_called()


async def test_one_deadline_bounds_information_and_pair_without_reset(
    coordinator: AdjustableBedCoordinator
) -> None:
    deadline = asyncio.get_running_loop().time() + 0.04
    reached_pair = asyncio.Event()

    async def info(*args, **kwargs):
        assert kwargs["deadline"] == deadline
        await asyncio.sleep(0.02)
        return _METADATA

    async def pair():
        reached_pair.set()
        await asyncio.Event().wait()

    coordinator.client.pair.side_effect = pair
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, side_effect=info
    ), pytest.raises(TimeoutError):
        await coordinator._async_pair_on_live_link({}, onboarding_deadline=deadline)
    assert reached_pair.is_set()
    assert not coordinator._ble_bond_established


async def test_actual_rerouted_source_is_used_before_first_bond_and_dis_is_skipped(
    coordinator: AdjustableBedCoordinator, mock_coordinator_connected, mock_bleak_client
) -> None:
    coordinator._client = None
    coordinator._retry_base_delay = 0
    controller = make_controller_mock()
    controller.supports_position_feedback = False
    seen_paths: list[ConnectionPath | None] = []

    async def native(address, *, path, operation):
        seen_paths.append(path)
        return _evidence(_PROXY)

    with patch(f"{_MODULE}.client_source", return_value=_PROXY.source), patch(
        f"{_MODULE}.async_path_for_source", return_value=_PROXY
    ), patch(f"{_MODULE}.async_verify_native_bond", side_effect=native), patch(
        _HELPER, return_value=_METADATA
    ), patch(f"{_MODULE}.create_controller", return_value=controller), patch(
        f"{_MODULE}.read_ble_device_info", new_callable=AsyncMock
    ) as dis, patch.object(coordinator, "_async_raise_pairing_issue", new_callable=AsyncMock), patch(
        f"{_MODULE}.close_stale_connections_by_address", new_callable=AsyncMock
    ):
        assert await coordinator.async_connect()
    assert seen_paths and all(path == _PROXY for path in seen_paths)
    assert coordinator.entry.data[CONF_BLE_BOND_ATTEMPTED_SOURCE] == _PROXY.source
    dis.assert_not_called()
    assert mock_bleak_client.pair.await_count == 1
    await coordinator.async_shutdown()


async def test_connect_and_information_share_deadline_and_expiry_cleans_link(
    coordinator: AdjustableBedCoordinator, mock_coordinator_connected, mock_bleak_client
) -> None:
    coordinator._client = None
    coordinator._max_retries = 1
    coordinator._retry_base_delay = 0
    connection_started = 0.0

    async def connect(*args, **kwargs):
        nonlocal connection_started
        connection_started = asyncio.get_running_loop().time()
        assert kwargs["pair"] is False
        await asyncio.sleep(0.02)
        return mock_bleak_client

    async def info(*args, **kwargs):
        assert 0.035 < kwargs["deadline"] - connection_started < 0.045
        await asyncio.Event().wait()

    with patch(f"{_MODULE}.VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS", 0.04), patch(
        f"{_MODULE}.establish_connection", side_effect=connect
    ), patch(f"{_MODULE}.client_source", return_value=_LOCAL.source), patch(
        f"{_MODULE}.async_path_for_source", return_value=_LOCAL
    ), patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, side_effect=info
    ), patch(
        f"{_MODULE}.close_stale_connections_by_address", new_callable=AsyncMock
    ):
        assert not await coordinator.async_connect()
    assert mock_bleak_client.disconnect.await_count >= 1
    mock_bleak_client.pair.assert_not_called()
    assert coordinator.client is None


async def test_historical_command_stop_does_not_cancel_explicit_pairing(
    coordinator: AdjustableBedCoordinator
) -> None:
    coordinator._cancel_command.set()

    async def info(*args, **kwargs):
        assert kwargs["cancel_event"] is None
        return _METADATA

    with patch(f"{_MODULE}.async_verify_native_bond", side_effect=[
        _evidence(_LOCAL), _evidence(_LOCAL, True)
    ]), patch(_HELPER, side_effect=info):
        assert await coordinator._async_pair_live_and_verify()


async def test_existing_werkmeister_bond_starts_real_notifications_without_information(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant,
    mock_coordinator_connected, mock_bleak_client,
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: "werkmeister",
        CONF_VIBRADORM_CONTROL_TYPE: 7,
    })
    coordinator._client = None
    coordinator._disable_angle_sensing = True
    command = MagicMock(uuid=COMMAND, properties=["write"])
    control = MagicMock(uuid=CBI, properties=["write"])
    response = MagicMock(uuid=RESPONSE, properties=["notify"])
    mock_bleak_client.services = [MagicMock(
        uuid="service-membership-does-not-select-the-app", characteristics=[command, control, response]
    )]
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    with patch(f"{_MODULE}.client_source", return_value=_LOCAL.source), patch(
        f"{_MODULE}.async_path_for_source", return_value=_LOCAL
    ), patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL, True)), patch(
        _HELPER, new_callable=AsyncMock
    ) as info, patch(f"{_MODULE}.read_ble_device_info", new_callable=AsyncMock) as dis, patch(
        f"{_MODULE}.close_stale_connections_by_address", new_callable=AsyncMock
    ):
        assert await coordinator.async_connect()
    assert isinstance(coordinator.controller, VibradormAppController)
    info.assert_not_called()
    dis.assert_not_called()
    mock_bleak_client.pair.assert_not_called()
    mock_bleak_client.start_notify.assert_awaited_once()
    callback = mock_bleak_client.start_notify.await_args.args[1]
    callback(response, bytearray.fromhex("203f40"))
    assert coordinator.controller_state["vibradorm_app_sync_observed"] is True
    assert coordinator._position_hydration_task is None
    await coordinator.async_shutdown()


@pytest.mark.parametrize(("app", "stored_control"), [
    ("werkmeister", "5"), ("werkmeister", "7"), ("caresse", "5"),
    ("caresse", "2"), ("caresse", "3"), ("caresse", "other"),
])
@pytest.mark.parametrize("cached_article", [False, True])
async def test_first_native_onboarding_with_stored_strings_runs_real_information_helper(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant,
    mock_coordinator_connected, mock_bleak_client, app: str, stored_control: str,
    cached_article: bool,
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: app,
        CONF_VIBRADORM_CONTROL_TYPE: stored_control,
        CONF_VIBRADORM_RESTORED: app == "caresse" and stored_control != "2",
        **({CONF_VIBRADORM_APP_METADATA: {"main_firmware_article": "old article"}}
           if cached_article else {}),
    })
    coordinator._client = None
    coordinator._disable_angle_sensing = True
    trace: list[str] = []
    replies: dict[str, Callable] = {}
    characters = {
        uuid: MagicMock(uuid=uuid, handle=index + 1, properties=properties)
        for index, (uuid, properties) in enumerate([
            (COMMAND, ["write"]), (CBI, ["write"]), (RESPONSE, ["notify"]),
            *((uuid, ["read"]) for _, uuid in INFO_FIELDS),
        ])
    }
    mock_bleak_client.services = [MagicMock(
        uuid="service-membership-is-not-an-app-selector", characteristics=list(characters.values())
    )]
    article_requests = stored_control in ("5", "7")
    basic = stored_control in ("2", "3")
    values = {uuid: field.encode() for field, uuid in INFO_FIELDS}
    article_count = 0
    connection_issued = 0.0

    async def establish(*args, **kwargs):
        nonlocal connection_issued
        connection_issued = asyncio.get_running_loop().time()
        assert kwargs["pair"] is False
        assert kwargs["use_services_cache"] is False
        trace.append("connect")
        return mock_bleak_client

    async def subscribe(char, callback):
        replies[char.uuid] = callback
        trace.append("subscribe")

    async def unsubscribe(char):
        replies.pop(char.uuid)
        trace.append("unsubscribe")

    async def read(char):
        assert mock_bleak_client.pair.await_count == 0
        trace.append(f"read:{char.uuid}")
        return values[char.uuid]

    async def write(char, packet, *, response):
        nonlocal article_count
        assert mock_bleak_client.pair.await_count == 0
        assert char.uuid == CBI and packet == bytes.fromhex("01a0c8") and response is True
        article_count += 1
        trace.append("article")
        replies[RESPONSE](characters[RESPONSE], bytearray.fromhex("21a0c8") + b"article")

    async def pair():
        assert article_count == (3 if article_requests else 0)
        assert mock_bleak_client.read_gatt_char.await_count == 5
        assert not replies  # Temporary info notification subscription has been cleaned up.
        trace.append("pair")

    async def native(address, *, path, operation):
        assert path == _LOCAL
        trace.append("native")
        return _evidence(_LOCAL, positive=mock_bleak_client.pair.await_count == 1)

    mock_bleak_client.start_notify = AsyncMock(side_effect=subscribe)
    mock_bleak_client.stop_notify = AsyncMock(side_effect=unsubscribe)
    mock_bleak_client.read_gatt_char = AsyncMock(side_effect=read)
    mock_bleak_client.write_gatt_char = AsyncMock(side_effect=write)
    mock_bleak_client.pair = AsyncMock(side_effect=pair)
    with patch(f"{_MODULE}.establish_connection", side_effect=establish), patch(
        f"{_MODULE}.client_source", return_value=_LOCAL.source
    ), patch(f"{_MODULE}.async_path_for_source", return_value=_LOCAL), patch(
        f"{_MODULE}.async_verify_native_bond", side_effect=native
    ), patch(_HELPER, wraps=async_prepare_vibradorm_app_pairing) as helper, patch.object(
        coordinator, "_async_pair_on_live_link", wraps=coordinator._async_pair_on_live_link
    ) as onboarding, patch(f"{_MODULE}.read_ble_device_info", new_callable=AsyncMock) as generic, patch(
        f"{_MODULE}.close_stale_connections_by_address", new_callable=AsyncMock
    ):
        assert await coordinator.async_connect()
    expected = ["connect", "native", *([] if basic else ["subscribe"]),
                *(f"read:{uuid}" for _, uuid in INFO_FIELDS),
                *(["article"] * 3 if article_requests else []),
                *([] if basic else ["unsubscribe"]), "pair", "native",
                *([] if basic else ["subscribe"])]
    assert trace == expected
    deadline = helper.await_args.kwargs["deadline"]
    assert deadline == onboarding.await_args.kwargs["onboarding_deadline"]
    assert 9.9 < deadline - connection_issued <= 10.0
    assert helper.await_args.args[2] == ("other" if stored_control == "other" else int(stored_control))
    assert isinstance(coordinator.controller, VibradormAppController)
    assert coordinator.entry.data[CONF_BLE_BOND_CONTEXT]["evidence_kind"] == "native_os_state"
    assert coordinator.controller_state["vibradorm_app_model"] == "model"
    expected_article = "article" if article_requests else "old article" if cached_article else None
    assert coordinator.controller_state.get("vibradorm_app_main_firmware_article") == expected_article
    assert coordinator.entry.data[CONF_VIBRADORM_APP_METADATA].get("main_firmware_article") == expected_article
    generic.assert_not_called()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("stored_control", ["invalid", "99", True, None, 5.5])
async def test_invalid_retained_control_is_rejected_before_information_or_pair(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, stored_control
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_CONTROL_TYPE: stored_control,
    })
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), pytest.raises(ValueError):
        await coordinator._async_pair_on_live_link({})
    coordinator.client.read_gatt_char.assert_not_called()
    coordinator.client.pair.assert_not_called()


@pytest.mark.parametrize("error", [TimeoutError(), asyncio.CancelledError(), ValueError("invalid role")])
async def test_failed_information_clears_cached_marker_with_one_write_and_reload_retries(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, error: BaseException
) -> None:
    historical_context = build_bond_context(_evidence(_LOCAL, True))
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_BLE_BOND_ESTABLISHED: True,
        CONF_BLE_BOND_CONTEXT: historical_context,
    })
    coordinator._ble_bond_established = True
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, side_effect=error
    ), patch.object(coordinator, "_async_persist_config", wraps=coordinator._async_persist_config) as persist, pytest.raises(type(error)):
        await coordinator._async_pair_on_live_link({})
    persist.assert_called_once()
    assert coordinator.entry.data[CONF_BLE_BOND_ESTABLISHED] is False
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert not coordinator.last_bond_evidence.proves_bond
    assert not coordinator.last_bond_evidence.proves_stale_host_bond
    # Historical owner identity cannot suppress first-bond work after a reload.
    reloaded = AdjustableBedCoordinator(hass, coordinator.entry)
    _, requested, after_discovery = reloaded._prepare_pairing_attempt(MagicMock(), {}, _LOCAL.source)
    assert requested and after_discovery
    coordinator.client.pair.assert_not_called()


async def test_cancelled_first_information_cleans_actual_connection_and_propagates(
    coordinator: AdjustableBedCoordinator, mock_coordinator_connected, mock_bleak_client
) -> None:
    coordinator._client = None
    reading = asyncio.Event()

    async def info(*args, **kwargs):
        reading.set()
        await asyncio.Event().wait()

    with patch(f"{_MODULE}.client_source", return_value=_LOCAL.source), patch(
        f"{_MODULE}.async_path_for_source", return_value=_LOCAL
    ), patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch(
        _HELPER, side_effect=info
    ), patch(f"{_MODULE}.close_stale_connections_by_address", new_callable=AsyncMock):
        task = asyncio.create_task(coordinator.async_connect())
        await asyncio.wait_for(reading.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert mock_bleak_client.disconnect.await_count >= 1
    mock_bleak_client.pair.assert_not_called()
    assert coordinator.client is None


def test_new_selection_intent_is_process_local_and_isolated_by_physical_target(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    selected = mark_vibradorm_app_selection(
        hass, coordinator.address.lower(), app_profile="caresse", control_type=2
    )
    assert coordinator.vibradorm_app_session_intent is selected
    assert (selected.floor.level, selected.floor.default_level) == (6, 6)
    assert (selected.timer.enabled, selected.timer.minutes) == (False, 0)
    other = get_vibradorm_app_session_intent(
        hass, "AA:BB:CC:DD:EE:00", app_profile="caresse", control_type=2,
        remembered_floor_default=6,
    )
    assert other is not selected
    assert other.floor.level == 0
    cold_hass = MagicMock(spec=HomeAssistant, data={})
    cold = get_vibradorm_app_session_intent(
        cold_hass, coordinator.address, app_profile="caresse", control_type=2,
        remembered_floor_default=6,
    )
    assert cold is not selected
    assert (cold.floor.level, cold.floor.default_level) == (0, 6)
    assert DOMAIN not in cold_hass.data  # Cache cannot look like a loaded integration entry.
    assert CONF_BLE_BOND_ESTABLISHED not in coordinator.entry.data


async def test_floor_and_pending_timer_survive_teardown_reload_and_unpair(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    state = coordinator.vibradorm_app_session_intent
    state.floor.level = 4
    state.timer.enabled, state.timer.minutes = True, 23
    coordinator.apply_confirmed_bond_removal()
    assert coordinator.vibradorm_app_session_intent is state
    await coordinator.async_shutdown()
    hass.data.pop(DOMAIN)
    reloaded = AdjustableBedCoordinator(hass, coordinator.entry)
    assert reloaded.vibradorm_app_session_intent is state
    assert state.floor.level == 4
    assert (state.timer.enabled, state.timer.minutes) == (True, 23)


def test_profile_change_and_explicit_clear_never_resurrect_previous_session(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    old = coordinator.vibradorm_app_session_intent
    old.floor.level = 5
    old.timer.enabled, old.timer.minutes = True, 15
    changed = get_vibradorm_app_session_intent(
        hass, coordinator.address, app_profile="werkmeister", control_type=7,
        remembered_floor_default=6,
    )
    assert changed is not old and changed.floor.level == 0
    returned = coordinator.vibradorm_app_session_intent
    assert returned is not old and returned.floor.level == 0
    assert (returned.timer.enabled, returned.timer.minutes) == (False, 0)
    clear_vibradorm_app_session_intent(hass, coordinator.address)
    assert coordinator.vibradorm_app_session_intent is not returned


@pytest.mark.parametrize(("app", "restored", "extension", "stored_default", "expected"), [
    ("werkmeister", False, False, None, 6),
    ("caresse", False, False, None, 6),
    ("caresse", True, False, None, 8),
    ("caresse", True, True, None, 6),
    ("caresse", True, True, 8, 8),
    ("caresse", True, False, 4, 4),
])
def test_cold_remembered_default_fallback_and_extension_retained_eight(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, app: str, restored: bool,
    extension: bool, stored_default: int | None, expected: int,
) -> None:
    data = {
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: app,
        CONF_VIBRADORM_CONTROL_TYPE: "7" if app == "werkmeister" else "2",
        CONF_VIBRADORM_RESTORED: restored, CONF_VIBRADORM_LIGHT_EXTENSION: extension,
    }
    if stored_default is not None:
        data[CONF_VIBRADORM_FLOOR_DEFAULT] = stored_default
    hass.config_entries.async_update_entry(coordinator.entry, data=data)
    state = coordinator.vibradorm_app_session_intent
    assert (state.floor.level, state.floor.default_level) == (0, expected)


def test_remembered_preference_updates_once_without_resetting_live_intent(
    coordinator: AdjustableBedCoordinator
) -> None:
    state = coordinator.vibradorm_app_session_intent
    state.floor.level = 6
    state.timer.enabled, state.timer.minutes = True, 30
    with patch.object(coordinator, "_async_persist_config", wraps=coordinator._async_persist_config) as persist:
        coordinator.remember_vibradorm_app_floor_default(8)
        coordinator.remember_vibradorm_app_floor_default(8)
    persist.assert_called_once()
    assert coordinator.entry.data[CONF_VIBRADORM_FLOOR_DEFAULT] == 8
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert coordinator.vibradorm_app_session_intent is state
    assert (state.floor.level, state.floor.default_level) == (6, 8)
    assert (state.timer.enabled, state.timer.minutes) == (True, 30)


@pytest.mark.parametrize("value", [True, 0, 9, None, 2.5])
def test_invalid_remembered_preference_is_rejected_before_storage_or_ble(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, value
) -> None:
    with patch.object(coordinator, "_async_persist_config") as persist, pytest.raises(ValueError):
        coordinator.remember_vibradorm_app_floor_default(value)
    persist.assert_not_called()
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_FLOOR_DEFAULT: value,
    })
    with pytest.raises(ValueError):
        _ = coordinator.vibradorm_app_session_intent
    coordinator.client.write_gatt_char.assert_not_called()


async def test_actual_factory_first_selection_and_reconstruction_use_shared_floor_timer_intent(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: "werkmeister",
        CONF_VIBRADORM_CONTROL_TYPE: "7", CONF_VIBRADORM_FLOOR_DEFAULT: 6,
    })
    state = mark_vibradorm_app_selection(
        hass, coordinator.address, app_profile="werkmeister", control_type=7
    )
    coordinator.client.services = [MagicMock(characteristics=[
        MagicMock(uuid=CBI, handle=1, properties=["write"]),
        MagicMock(uuid=RESPONSE, handle=2, properties=["notify"]),
    ])]
    coordinator.client.write_gatt_char = AsyncMock()
    first = await create_controller(coordinator, BED_TYPE_VIBRADORM_APP, None, coordinator.client)
    assert isinstance(first, VibradormAppController)
    assert first.get_light_state()["state_source"] == "local_intent"
    await first.lights_toggle()
    assert coordinator.client.write_gatt_char.await_args.args[1].hex() == "80110000"
    assert state.floor.level == 0 and state.floor.default_level == 6
    await first.set_pending_floor_timer(23)
    await first.execute_app_action("floor_timer_toggle")
    recreated = await create_controller(coordinator, BED_TYPE_VIBRADORM_APP, None, coordinator.client)
    assert isinstance(recreated, VibradormAppController)
    await recreated.lights_toggle()
    assert coordinator.client.write_gatt_char.await_args.args[1].hex() == "8011c017"
    assert (state.floor.level, state.timer.enabled, state.timer.minutes) == (6, True, 23)


async def test_failed_ble_toggle_keeps_remembered_intent_through_guarded_preference_write(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: "werkmeister",
        CONF_VIBRADORM_CONTROL_TYPE: "7", CONF_VIBRADORM_FLOOR_DEFAULT: 6,
    })
    state = coordinator.vibradorm_app_session_intent
    state.floor.level = 4
    coordinator.client.services = [MagicMock(characteristics=[
        MagicMock(uuid=CBI, handle=1, properties=["write"]),
        MagicMock(uuid=RESPONSE, handle=2, properties=["notify"]),
    ])]
    coordinator.client.write_gatt_char = AsyncMock(side_effect=BleakError("write failed"))
    controller = await create_controller(coordinator, BED_TYPE_VIBRADORM_APP, None, coordinator.client)
    assert isinstance(controller, VibradormAppController)
    with patch.object(coordinator, "_async_persist_config", wraps=coordinator._async_persist_config) as persist, pytest.raises(BleakError):
        await controller.lights_toggle()
    persist.assert_called_once()
    assert coordinator.entry.data[CONF_VIBRADORM_FLOOR_DEFAULT] == 4
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert (state.floor.level, state.floor.default_level) == (0, 4)
    assert controller.get_light_state()["state_source"] == "local_intent"


async def test_paired_preference_write_and_ownership_migration_preserve_only_target_intent(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant
) -> None:
    state = coordinator.vibradorm_app_session_intent
    state.floor.level = 4
    state.timer.enabled, state.timer.minutes = True, 23
    left_descriptor = {
        **coordinator.entry.data, CONF_SIDE: SIDE_LEFT, CONF_BLE_BOND_ESTABLISHED: True,
        CONF_VIBRADORM_APP_METADATA: {"software": "old software", "main_firmware_article": "old article"},
    }
    right_descriptor = {
        **left_descriptor, CONF_SIDE: SIDE_RIGHT, CONF_ADDRESS: "AA:BB:CC:DD:EE:00",
        CONF_VIBRADORM_FLOOR_DEFAULT: 6, CONF_BLE_BOND_ESTABLISHED: False,
    }
    parent_entry = MockConfigEntry(domain=DOMAIN, title="Paired bed", data={
        CONF_PAIR_ID: "native-intent-pair", CONF_NAME: "Paired bed",
        CONF_PAIR_CHILDREN: [left_descriptor, right_descriptor],
    })
    parent_entry.add_to_hass(hass)
    children = _build_paired_children(hass, parent_entry)
    parent = PairedBedCoordinator(hass, parent_entry, children)
    hass.data[DOMAIN][parent_entry.entry_id] = parent
    left, right = children[SIDE_LEFT], children[SIDE_RIGHT]
    assert left.vibradorm_app_session_intent is state
    other_state = right.vibradorm_app_session_intent
    assert other_state is not state
    with patch.object(hass.config_entries, "async_update_entry", wraps=hass.config_entries.async_update_entry) as update:
        left.remember_vibradorm_app_floor_default(4)
        left.remember_vibradorm_app_floor_default(4)
    update.assert_called_once()
    left_saved = get_child(parent_entry.data, SIDE_LEFT)
    assert left_saved is not None and dict(left_saved)[CONF_VIBRADORM_FLOOR_DEFAULT] == 4
    assert get_child(parent_entry.data, SIDE_RIGHT) == right_descriptor
    assert not right.consume_internal_entry_update(parent_entry)
    assert parent.consume_internal_entry_update(parent_entry)
    assert not parent.consume_internal_entry_update(parent_entry)
    assert (state.floor.level, state.floor.default_level) == (4, 4)
    assert (state.timer.enabled, state.timer.minutes) == (True, 23)
    assert (other_state.floor.level, other_state.timer.minutes) == (0, 0)
    with patch.object(hass.config_entries, "async_update_entry", wraps=hass.config_entries.async_update_entry) as update:
        left.remember_vibradorm_app_metadata({"model": "new model", "firmware": ""})
        left.remember_vibradorm_app_metadata({"model": "new model", "firmware": ""})
    update.assert_called_once()
    assert left.entry.data[CONF_VIBRADORM_APP_METADATA] == {
        "model": "new model", "firmware": "", "software": "old software",
        "main_firmware_article": "old article",
    }
    assert get_child(parent_entry.data, SIDE_RIGHT) == right_descriptor
    assert parent.consume_internal_entry_update(parent_entry)
    assert not parent.consume_internal_entry_update(parent_entry)
    left.apply_confirmed_bond_removal()
    assert parent.consume_internal_entry_update(parent_entry)
    await parent.async_shutdown()
    # A new standalone owner after separation reuses the physical target's session.
    separated_entry = MockConfigEntry(domain=DOMAIN, title="Left bed", data=dict(left.entry.data))
    separated_entry.add_to_hass(hass)
    separated = AdjustableBedCoordinator(hass, separated_entry)
    assert separated.vibradorm_app_session_intent is state
    assert (state.floor.level, state.floor.default_level) == (4, 4)
    assert (state.timer.enabled, state.timer.minutes) == (True, 23)
    assert right.vibradorm_app_session_intent is other_state
    assert separated.entry.data[CONF_VIBRADORM_APP_METADATA] == left.entry.data[CONF_VIBRADORM_APP_METADATA]


@pytest.mark.parametrize("failure", [
    "software_error", "software_timeout", "software_cancel",
    "article_error", "article_timeout", "article_cancel", "pair_timeout",
])
async def test_real_information_partial_progress_survives_terminal_failure_in_one_write(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, failure: str,
) -> None:
    old_metadata = {
        "model": "old model", "firmware": "old firmware", "software": "old software",
        "main_firmware_article": "old article",
    }
    historical_context = build_bond_context(_evidence(_LOCAL, True))
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_PROFILE: "werkmeister",
        CONF_VIBRADORM_CONTROL_TYPE: "7", CONF_BLE_BOND_ESTABLISHED: True,
        CONF_BLE_BOND_CONTEXT: historical_context, CONF_VIBRADORM_APP_METADATA: old_metadata,
    })
    coordinator._ble_bond_established = True
    coordinator.handle_controller_state_updates({
        f"vibradorm_app_{field}": value for field, value in old_metadata.items()
    })
    client = coordinator.client
    characters = {
        uuid: MagicMock(uuid=uuid, handle=index + 1, properties=properties)
        for index, (uuid, properties) in enumerate([
            (CBI, ["write"]), (RESPONSE, ["notify"]),
            *((uuid, ["read"]) for _, uuid in INFO_FIELDS),
        ])
    }
    client.services = [MagicMock(characteristics=list(characters.values()))]
    notify: Callable | None = None
    article_count = 0

    async def fail(stage: str) -> None:
        if failure == f"{stage}_error":
            raise BleakError("later information failed")
        if failure == f"{stage}_cancel":
            raise asyncio.CancelledError
        await asyncio.Event().wait()

    async def subscribe(char, callback):
        nonlocal notify
        notify = callback

    async def read(char):
        persist.assert_not_called()  # No entry update/reload for each read.
        field = next(field for field, uuid in INFO_FIELDS if uuid == char.uuid)
        if field == "firmware":
            assert coordinator.controller_state["vibradorm_app_model"] == "new model"
        if field == "software":
            assert coordinator.controller_state["vibradorm_app_firmware"] == ""
            if failure.startswith("software_"):
                await fail("software")
        return {"model": b" new model\t", "firmware": b"\x00 \t", "software": b"new software"}.get(field, b"unused")

    async def write(char, packet, *, response):
        nonlocal article_count
        persist.assert_not_called()
        assert char.uuid == CBI and packet == bytes.fromhex("01a0c8") and response is True
        article_count += 1
        if article_count == 2 and failure.startswith("article_"):
            assert coordinator.controller_state["vibradorm_app_main_firmware_article"] == "article1"
            await fail("article")
        assert notify is not None
        notify(characters[RESPONSE], bytearray.fromhex("21a0c8") + f"article{article_count}".encode())

    client.start_notify = AsyncMock(side_effect=subscribe)
    client.stop_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(side_effect=read)
    client.write_gatt_char = AsyncMock(side_effect=write)
    async def pair():
        await fail("pair")

    client.pair = AsyncMock(side_effect=pair)
    expected_exception = (
        asyncio.CancelledError if failure.endswith("cancel")
        else BleakError if failure.endswith("error") else TimeoutError
    )
    deadline = asyncio.get_running_loop().time() + 0.04
    with patch(f"{_MODULE}.async_verify_native_bond", return_value=_evidence(_LOCAL)), patch.object(
        coordinator, "_async_persist_config", wraps=coordinator._async_persist_config
    ) as persist, pytest.raises(expected_exception):
        await coordinator._async_pair_on_live_link({}, onboarding_deadline=deadline)
    persist.assert_called_once()
    expected = {**old_metadata, "model": "new model", "firmware": ""}
    if not failure.startswith("software_"):
        expected["software"] = "new software"
        expected["main_firmware_article"] = "article3" if failure == "pair_timeout" else "article1"
    assert coordinator.entry.data[CONF_VIBRADORM_APP_METADATA] == expected
    assert coordinator.entry.data[CONF_BLE_BOND_ESTABLISHED] is False
    assert coordinator.entry.data[CONF_BLE_BOND_CONTEXT] == historical_context
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert not coordinator.consume_internal_entry_update(coordinator.entry)
    for field, value in expected.items():
        assert coordinator.controller_state[f"vibradorm_app_{field}"] == value
    client.stop_notify.assert_awaited_once()
    assert client.pair.await_count == (1 if failure == "pair_timeout" else 0)
    assert not coordinator.last_bond_evidence.proves_bond
    reloaded = AdjustableBedCoordinator(hass, coordinator.entry)
    _, requested, after_discovery = reloaded._prepare_pairing_attempt(MagicMock(), {}, _LOCAL.source)
    assert requested and after_discovery


@pytest.mark.parametrize("result", ["software_error", "software_timeout", "software_cancel", "success"])
async def test_real_refresh_batch_persists_partial_or_full_metadata_for_reconstruction(
    coordinator: AdjustableBedCoordinator, hass: HomeAssistant, result: str,
) -> None:
    old = {"model": "old model", "firmware": "old firmware", "software": "old software", "main_firmware_article": "old article"}
    context = build_bond_context(_evidence(_LOCAL, True))
    hass.config_entries.async_update_entry(coordinator.entry, data={
        **coordinator.entry.data, CONF_VIBRADORM_APP_METADATA: old,
        CONF_BLE_BOND_ESTABLISHED: True, CONF_BLE_BOND_CONTEXT: context,
    })
    coordinator._ble_bond_established = True
    client = coordinator.client
    client.services = [MagicMock(characteristics=[
        MagicMock(uuid=COMMAND, handle=1, properties=["write"]),
        *(MagicMock(uuid=uuid, handle=index + 2, properties=["read"]) for index, (_, uuid) in enumerate(INFO_FIELDS)),
    ])]
    controller = await create_controller(coordinator, BED_TYPE_VIBRADORM_APP, None, client)
    assert isinstance(controller, VibradormAppController)
    error = {"software_error": BleakError("software failed"), "software_timeout": TimeoutError(), "software_cancel": asyncio.CancelledError()}.get(result)

    async def read(char):
        persist.assert_not_called()
        field = next(field for field, uuid in INFO_FIELDS if uuid == char.uuid)
        if field == "software" and error is not None:
            raise error
        return {"model": b" new model\t", "firmware": b"\x00 \t", "software": b"new software"}.get(field, b"unused")

    client.read_gatt_char = AsyncMock(side_effect=read)
    with patch.object(coordinator, "_async_persist_config", wraps=coordinator._async_persist_config) as persist, patch(
        f"{_MODULE}.async_verify_native_bond"
    ) as native:
        if error is None:
            await controller.refresh_device_info()
        else:
            with pytest.raises(type(error)):
                await controller.refresh_device_info()
    persist.assert_called_once()
    expected = {**old, "model": "new model", "firmware": ""}
    if result == "success":
        expected["software"] = "new software"
    assert coordinator.entry.data[CONF_VIBRADORM_APP_METADATA] == expected
    assert coordinator.entry.data[CONF_BLE_BOND_ESTABLISHED] is True
    assert coordinator.entry.data[CONF_BLE_BOND_CONTEXT] == context
    assert coordinator.consume_internal_entry_update(coordinator.entry)
    assert not coordinator.consume_internal_entry_update(coordinator.entry)
    native.assert_not_called()
    client.pair.assert_not_called()
    assert coordinator.last_bond_evidence is None
    reloaded = AdjustableBedCoordinator(hass, coordinator.entry)
    reloaded._client = client
    recreated = await create_controller(reloaded, BED_TYPE_VIBRADORM_APP, None, client)
    assert isinstance(recreated, VibradormAppController)
    assert recreated.protocol_diagnostics["metadata"] == expected
    for field, value in expected.items():
        assert reloaded.controller_state[f"vibradorm_app_{field}"] == value
