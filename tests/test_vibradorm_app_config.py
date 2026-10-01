"""Explicit app selection, per-side settings and pre-bond onboarding order."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.vibradorm_app import (
    VibradormAppController,
    VibradormAppMetadata,
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
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    supports_single_address_pairing,
)
from custom_components.adjustable_bed.setup_operation import OperationOutcome, OperationResult
from custom_components.adjustable_bed.vibradorm_app_state import clear_vibradorm_app_session_intent

PREFIX = "custom_components.adjustable_bed.config_flow."
ADDRESS = "11:22:33:44:55:66"
SOURCE = "AA:BB:CC:DD:EE:FF"


def app_data(app="caresse", control="2", **extra):
    return {
        CONF_ADDRESS: ADDRESS,
        const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_VIBRADORM_APP_PROFILE: app,
        const.CONF_VIBRADORM_CONTROL_TYPE: control,
        const.CONF_VIBRADORM_RESTORED: False,
        const.CONF_VIBRADORM_FLOOR_LIGHT: app == "werkmeister",
        const.CONF_VIBRADORM_RGB: False,
        const.CONF_VIBRADORM_MASSAGE: False,
        const.CONF_VIBRADORM_LIGHT_EXTENSION: False,
        **extra,
    }


@pytest.mark.parametrize("step,pairing", [
    ("manual_entry", "manual_pairing"),
    ("manual_config", "manual_pairing"),
    ("bluetooth_confirm", "bluetooth_pairing"),
])
async def test_every_setup_route_collects_app_then_pairs(hass, mock_bluetooth_service_info, step, pairing):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")({
        CONF_ADDRESS: ADDRESS, CONF_NAME: "App bed",
        const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_PREFERRED_ADAPTER: "auto",
    })
    assert result["step_id"] == "vibradorm_app"
    result = await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_APP_PROFILE: "caresse"})
    assert result["type"] == FlowResultType.FORM
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert const.CONF_VIBRADORM_RESTORED in fields
    assert const.CONF_VIBRADORM_RGB not in fields
    with patch.object(flow, f"async_step_{pairing}", new=AsyncMock()) as resume:
        await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_RESTORED: False})
    resume.assert_awaited_once_with()
    assert flow._manual_data[const.CONF_VIBRADORM_CONTROL_TYPE] == "2"
    assert flow._manual_data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert flow._manual_data[const.CONF_HAS_MASSAGE] is False


async def test_restored_basic_features_and_no_motor_branch_are_explicit(hass):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data()
    result = await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_RESTORED: True})
    assert const.CONF_VIBRADORM_RGB in {key.schema for key in result["data_schema"].schema}
    for control, expected_groups in (("2", 2), ("other", 0)):
        with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as resume:
            await flow.async_step_vibradorm_app({
                const.CONF_VIBRADORM_CONTROL_TYPE: control,
                const.CONF_VIBRADORM_RGB: True,
                const.CONF_VIBRADORM_MASSAGE: True,
            })
        resume.assert_awaited_once()
        coordinator = MagicMock()
        coordinator.hass = hass
        coordinator.address = ADDRESS
        coordinator.entry = SimpleNamespace(data=flow._manual_data)
        controller = await create_controller(coordinator, const.BED_TYPE_VIBRADORM_APP, None, None)
        assert len(controller.motor_control_specs) == expected_groups
        assert controller.supports_massage
        assert controller.supports_position_feedback is False
        assert controller.memory_slot_count == (0 if control == "2" else 6)


async def test_app_change_rebuilds_options_and_clears_retained_features(hass):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(**{
        const.CONF_VIBRADORM_RESTORED: True,
        const.CONF_VIBRADORM_RGB: True,
        const.CONF_VIBRADORM_MASSAGE: True,
        const.CONF_VIBRADORM_APP_METADATA: {"model": "old metadata"},
    }))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({const.CONF_VIBRADORM_APP_PROFILE: "werkmeister"})
    assert result["type"] == FlowResultType.FORM
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert const.CONF_VIBRADORM_CONTROL_TYPE in fields
    assert const.CONF_VIBRADORM_RGB not in fields
    assert const.CONF_MOTOR_COUNT not in fields
    assert const.CONF_MOTOR_PULSE_DELAY_MS not in fields
    result = await flow.async_step_settings({const.CONF_VIBRADORM_CONTROL_TYPE: "7"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_VIBRADORM_MASSAGE] is False
    assert entry.data[const.CONF_MOTOR_COUNT] == 4
    assert const.CONF_VIBRADORM_APP_METADATA not in entry.data


@pytest.mark.parametrize("options", [False, True])
@pytest.mark.parametrize("old_app", ["caresse", "werkmeister"])
async def test_full_rendered_form_profile_switch_discards_old_app_fields(hass, options, old_app):
    old = app_data(old_app, "2" if old_app == "caresse" else "7", **{
        const.CONF_VIBRADORM_RESTORED: old_app == "caresse",
        const.CONF_VIBRADORM_RGB: old_app == "caresse",
        const.CONF_VIBRADORM_MASSAGE: old_app == "caresse",
        const.CONF_VIBRADORM_LIGHT_EXTENSION: old_app == "caresse",
        const.CONF_VIBRADORM_FLOOR_DEFAULT: 8,
        const.CONF_VIBRADORM_APP_METADATA: {"model": "old metadata"},
    })
    entry = MockConfigEntry(domain=const.DOMAIN, data=old)
    if options:
        entry.add_to_hass(hass)
        flow = AdjustableBedOptionsFlow(entry)
        flow.handler = entry.entry_id
        step = flow.async_step_settings
    else:
        flow = AdjustableBedConfigFlow()
        flow.context = {}
        flow._manual_data = old
        step = flow.async_step_vibradorm_app
    flow.hass = hass
    rendered = await step()
    assert rendered["type"] == FlowResultType.FORM
    assert rendered["data_schema"] is not None
    submitted = rendered["data_schema"]({})
    assert isinstance(submitted, dict)
    new_app = "werkmeister" if old_app == "caresse" else "caresse"
    submitted[const.CONF_VIBRADORM_APP_PROFILE] = new_app
    rebuilt = await step(submitted)
    assert rebuilt["type"] == FlowResultType.FORM
    assert not rebuilt["errors"]
    assert rebuilt["data_schema"] is not None
    defaults = rebuilt["data_schema"]({})
    assert isinstance(defaults, dict)
    assert defaults[const.CONF_VIBRADORM_APP_PROFILE] == new_app
    if new_app == "werkmeister":
        assert defaults[const.CONF_VIBRADORM_CONTROL_TYPE] == "5"
    else:
        assert defaults[const.CONF_VIBRADORM_RESTORED] is False
    for key in (const.CONF_VIBRADORM_RGB, const.CONF_VIBRADORM_MASSAGE,
                const.CONF_VIBRADORM_LIGHT_EXTENSION, const.CONF_VIBRADORM_FLOOR_DEFAULT):
        assert key not in defaults
    if options:
        finished = await step(defaults)
        assert finished["type"] == FlowResultType.CREATE_ENTRY
        updated = entry.data
    else:
        with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pairing:
            await step(defaults)
        pairing.assert_awaited_once()
        updated = flow._manual_data
    assert updated[const.CONF_VIBRADORM_CONTROL_TYPE] == ("5" if new_app == "werkmeister" else "2")
    assert updated[const.CONF_VIBRADORM_FLOOR_DEFAULT] == 6
    assert updated[const.CONF_VIBRADORM_MASSAGE] is False
    assert updated[const.CONF_VIBRADORM_RGB] is False
    assert const.CONF_VIBRADORM_APP_METADATA not in updated


async def test_two_address_pair_keeps_different_side_profiles(hass):
    left = app_data()
    right = app_data("werkmeister", "7")
    right[CONF_ADDRESS] = "11:22:33:44:55:77"
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    assert not const.VIBRADORM_APP_CONFIG_KEYS.intersection(
        key.schema for key in result["data_schema"].schema
    )
    result = await flow.async_step_settings({const.CONF_VIBRADORM_CONTROL_TYPE: "5"})
    assert result["errors"] == {"base": "vibradorm_app_unpair_first"}
    assert [child[const.CONF_VIBRADORM_CONTROL_TYPE] for child in entry.data[const.CONF_PAIR_CHILDREN]] == ["2", "7"]
    assert not supports_single_address_pairing(const.BED_TYPE_VIBRADORM_APP)


@pytest.mark.parametrize("failure", [None, "information", "pair", "deadline", "cancel"])
async def test_information_precedes_native_pair_and_shares_connection_deadline(hass, failure):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data("werkmeister", "7")
    client = MagicMock()
    events = []
    path = ConnectionPath(SOURCE, transport=TransportClass.LOCAL, adapter="hci0")
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)

    async def connect(*args, **kwargs):
        events.append("connect")
        if failure == "deadline":
            await asyncio.sleep(0.015)
        return client

    async def info(*args, deadline, **kwargs):
        events.append("information")
        assert 0 < deadline - asyncio.get_running_loop().time() <= 10
        if failure == "information":
            raise ValueError("missing required information")
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "deadline":
            await asyncio.sleep(0.015)
        return VibradormAppMetadata("model", "firmware", "software", "article")

    async def pair():
        events.append("pair")
        if failure == "pair":
            raise ValueError("pair failed")
        if failure == "deadline":
            await asyncio.sleep(0.025)

    client.pair = AsyncMock(side_effect=pair)
    client.disconnect = AsyncMock()
    results = [unknown, unknown if failure == "pair" else native]
    with (
        patch("bleak_retry_connector.establish_connection", side_effect=connect) as establish,
        patch(PREFIX + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(PREFIX + "client_source", return_value=SOURCE),
        patch(PREFIX + "async_path_for_source", return_value=path),
        patch(PREFIX + "async_verify_native_bond", new=AsyncMock(side_effect=results)),
        patch(PREFIX + "async_verify_authenticated_access", new=AsyncMock()) as auth,
        patch("custom_components.adjustable_bed.beds.vibradorm_app.async_prepare_vibradorm_app_pairing", side_effect=info),
        patch(PREFIX + "VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS", 0.04 if failure == "deadline" else 10.0),
    ):
        kwargs = {"request_bond": True, "track_for_flow_cleanup": False, "device": BLEDevice(ADDRESS, "Bed", {}), "preferred_adapter": "auto"}
        if failure is None:
            evidence = await flow._attempt_pairing_with_capture(ADDRESS, **kwargs)
            assert evidence.status is BondVerificationStatus.NATIVE_OS_STATE
            assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["model"] == "model"
        else:
            expected = asyncio.CancelledError if failure == "cancel" else TimeoutError if failure == "deadline" else ValueError
            with pytest.raises(expected):
                await flow._attempt_pairing_with_capture(ADDRESS, **kwargs)
        assert "pair" not in establish.call_args.kwargs
        auth.assert_not_awaited()
    assert events[:2] == ["connect", "information"]
    assert ("pair" in events) == (failure not in {"information", "cancel"})
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("succeeded", [False, True])
@pytest.mark.parametrize("app,control,restored", [("werkmeister", "5", False), ("werkmeister", "7", False), ("caresse", "4", True)])
async def test_pairing_result_finish_records_fresh_selection_without_changing_retained_intent(hass, app, control, restored, succeeded):
    from tests.test_vibradorm_app import make_controller

    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data(app, control, **{const.CONF_VIBRADORM_RESTORED: restored})
    flow._pairing_result_shown = True
    path = ConnectionPath(SOURCE, transport=TransportClass.LOCAL, adapter="hci0")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    flow.operation.result = OperationResult(
        outcome=OperationOutcome.SUCCESS if succeeded else OperationOutcome.BOND_VERIFICATION_INCONCLUSIVE,
        payload=native if succeeded else None,
    )
    result = await flow.async_step_pairing_result({"action": "finish"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert bool(result["data"].get(const.CONF_BLE_BOND_ESTABLISHED)) is succeeded
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator, const.BED_TYPE_VIBRADORM_APP, "auto", make_controller(int(control), app=app).client,
    )
    assert isinstance(controller, VibradormAppController)
    assert controller._floor_level == (0 if restored else 6)
    assert coordinator.vibradorm_app_session_intent.floor is controller._floor_intent


@pytest.mark.parametrize("failure", ["software", "article", "cancel", "timeout"])
async def test_setup_retains_completed_metadata_before_later_information_failure(hass, failure):
    from tests.test_vibradorm_app import make_controller

    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data("werkmeister", "7", **{
        const.CONF_VIBRADORM_APP_METADATA: {
            "model": "old model", "firmware": "old firmware", "software": "old software",
            "main_firmware_article": "old article",
        },
    })
    client = make_controller(7, app="werkmeister").client
    client.pair = AsyncMock()
    client.disconnect = AsyncMock()
    reads = 0

    async def read(char):
        nonlocal reads
        reads += 1
        if reads == 5 and failure != "article":
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "timeout":
                await asyncio.Event().wait()
            raise ValueError("software read failed")
        return [b"gap", b"manufacturer", b" new model ", b" new firmware ", b" new software "][reads - 1]

    client.read_gatt_char = AsyncMock(side_effect=read)
    client.write_gatt_char = AsyncMock(side_effect=ValueError("article request failed"))
    path = ConnectionPath(SOURCE, transport=TransportClass.LOCAL, adapter="hci0")
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    with (
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)),
        patch(PREFIX + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(PREFIX + "client_source", return_value=SOURCE),
        patch(PREFIX + "async_path_for_source", return_value=path),
        patch(PREFIX + "async_verify_native_bond", new=AsyncMock(return_value=unknown)),
        patch(PREFIX + "async_verify_authenticated_access", new=AsyncMock()) as authenticated,
        patch(PREFIX + "VIBRADORM_APP_ONBOARDING_TIMEOUT_SECONDS", 0.04 if failure == "timeout" else 10.0),
    ):
        expected = asyncio.CancelledError if failure == "cancel" else TimeoutError if failure == "timeout" else ValueError
        with pytest.raises(expected):
            await flow._attempt_pairing_with_capture(
                ADDRESS, request_bond=True, track_for_flow_cleanup=False,
                device=BLEDevice(ADDRESS, "Bed", {}), preferred_adapter="auto",
            )
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA] == {
        "model": "new model", "firmware": "new firmware",
        "software": "new software" if failure == "article" else "old software",
        "main_firmware_article": "old article",
    }
    assert reads == 5
    client.pair.assert_not_awaited()
    authenticated.assert_not_awaited()
    client.stop_notify.assert_awaited_once()
    client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("control", ["2", "4"])
async def test_setup_preserves_remembered_article_when_profile_does_not_read_it(hass, control):
    from tests.test_vibradorm_app import make_controller

    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data("caresse", control, **{
        const.CONF_VIBRADORM_RESTORED: control != "2",
        const.CONF_VIBRADORM_APP_METADATA: {"main_firmware_article": "retained article"},
    })
    client = make_controller(int(control)).client
    client.read_gatt_char.side_effect = [b"gap", b"manufacturer", b"model", b"firmware", b"software"]
    client.pair = AsyncMock()
    client.disconnect = AsyncMock()
    path = ConnectionPath(SOURCE, transport=TransportClass.LOCAL, adapter="hci0")
    unknown = BondEvidence(BondVerificationStatus.INCONCLUSIVE, BondOwner.from_path(path), "native", "now")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    with (
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)),
        patch(PREFIX + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(PREFIX + "client_source", return_value=SOURCE),
        patch(PREFIX + "async_path_for_source", return_value=path),
        patch(PREFIX + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native])),
    ):
        result = await flow._attempt_pairing_with_capture(
            ADDRESS, request_bond=True, track_for_flow_cleanup=False,
            device=BLEDevice(ADDRESS, "Bed", {}), preferred_adapter="auto",
        )
    assert result is native
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA] == {
        "model": "model", "firmware": "firmware", "software": "software",
        "main_firmware_article": "retained article",
    }
    client.write_gatt_char.assert_not_awaited()
    client.pair.assert_awaited_once()


@pytest.mark.parametrize("control", ["5", "7"])
async def test_successful_first_selection_and_later_cold_start_use_distinct_intent(hass, control):
    from tests.test_vibradorm_app import make_controller, written

    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    selected = app_data("werkmeister", control, **{const.CONF_VIBRADORM_FLOOR_DEFAULT: 6})
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow._finish_with_verify(selected, "App bed")
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert not any("first_selection" in key for key in result["data"])
    entry = MockConfigEntry(domain=const.DOMAIN, data=result["data"])
    entry.add_to_hass(hass)

    async def construct():
        coordinator = AdjustableBedCoordinator(hass, entry)
        coordinator._client = make_controller(int(control), app="werkmeister").client
        controller = await create_controller(coordinator, const.BED_TYPE_VIBRADORM_APP, None, coordinator.client)
        return coordinator, controller

    first, controller = await construct()
    assert controller._floor_level == 6
    assert controller._floor_default == 6
    assert first.controller_state == {}
    await controller.lights_toggle()
    assert written(controller) == ["80110000"]
    await controller.set_pending_floor_timer(12)
    await controller.execute_app_action("floor_timer_toggle")
    second, reconnected = await construct()
    assert second.vibradorm_app_session_intent is first.vibradorm_app_session_intent
    assert reconnected._floor_level == 0 and reconnected._timer_minutes == 12
    assert reconnected._timer_enabled is True
    previous_session = first.vibradorm_app_session_intent
    clear_vibradorm_app_session_intent(hass, ADDRESS)
    cold, restarted = await construct()
    assert cold.vibradorm_app_session_intent is not previous_session
    assert restarted._floor_level == 0 and restarted._floor_default == 6
    assert restarted._timer_minutes == 0 and restarted._timer_enabled is False
    await restarted.lights_toggle()
    assert written(restarted) == ["8011c000"]


@pytest.mark.parametrize("level", [True, False, 0, 9, 1.5, float("nan"), float("inf"), "6"])
async def test_retained_remembered_level_rejects_invalid_raw_inputs(hass, level):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data(**{const.CONF_VIBRADORM_RESTORED: True})
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pair:
        result = await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_FLOOR_DEFAULT: level})
    assert result["errors"] == {const.CONF_VIBRADORM_FLOOR_DEFAULT: "vibradorm_app_invalid"}
    pair.assert_not_awaited()


async def test_retained_extension_preserves_remembered_eight_above_slider_limit(hass):
    from tests.test_vibradorm_app import make_controller, written

    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(**{
        const.CONF_VIBRADORM_RESTORED: True,
        const.CONF_VIBRADORM_FLOOR_LIGHT: True,
        const.CONF_VIBRADORM_FLOOR_DEFAULT: 8,
    }))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({const.CONF_VIBRADORM_LIGHT_EXTENSION: True})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_VIBRADORM_FLOOR_DEFAULT] == 8
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = make_controller().client
    controller = await create_controller(coordinator, const.BED_TYPE_VIBRADORM_APP, None, coordinator.client)
    assert controller.light_level_max == 6
    await controller.lights_toggle()
    assert written(controller) == ["80110800"]
    with pytest.raises(ValueError):
        await controller.set_light_level(8)
    assert written(controller) == ["80110800"]


@pytest.mark.parametrize("control", [True, False, None, 2.5])
async def test_factory_rejects_invalid_retained_types_before_any_write(hass, control):
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.address = ADDRESS
    coordinator.entry = SimpleNamespace(data=app_data(control=control))
    with pytest.raises(ValueError, match="Invalid retained"):
        await create_controller(coordinator, const.BED_TYPE_VIBRADORM_APP, None, None)
    coordinator.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("control", ["-1", "0", "1", "2", "3", "4", "5", "6", "7", "other"])
async def test_retained_options_persist_literal_remote_and_independent_features(hass, control):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(**{
        const.CONF_VIBRADORM_RESTORED: True,
        const.CONF_VIBRADORM_APP_METADATA: {"model": "old profile"},
    }))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({
        const.CONF_VIBRADORM_CONTROL_TYPE: control,
        const.CONF_VIBRADORM_RGB: True,
        const.CONF_VIBRADORM_MASSAGE: True,
        const.CONF_VIBRADORM_FLOOR_LIGHT: False,
        const.CONF_VIBRADORM_LIGHT_EXTENSION: True,
    })
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_VIBRADORM_CONTROL_TYPE] == control
    assert entry.data[const.CONF_VIBRADORM_RGB] is True
    assert entry.data[const.CONF_VIBRADORM_MASSAGE] is True
    assert entry.data[const.CONF_VIBRADORM_FLOOR_LIGHT] is False
    assert entry.data[const.CONF_VIBRADORM_LIGHT_EXTENSION] is True
    assert entry.data[const.CONF_MOTOR_PULSE_USER_SET] is False
    assert (const.CONF_VIBRADORM_APP_METADATA in entry.data) == (control == "2")


async def test_switching_away_from_app_removes_its_configuration(hass):
    entry = MockConfigEntry(domain=const.DOMAIN, data=app_data(**{
        const.CONF_VIBRADORM_APP_METADATA: {"model": "old profile"},
    }))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM})
    assert result["type"] == FlowResultType.FORM
    result = await flow.async_step_settings({})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert not const.VIBRADORM_APP_CONFIG_KEYS.intersection(entry.data)
    assert const.CONF_VIBRADORM_APP_METADATA not in entry.data


@pytest.mark.parametrize("app,control,field", [
    ("caresse", "99", const.CONF_VIBRADORM_CONTROL_TYPE),
    ("werkmeister", "2", const.CONF_VIBRADORM_CONTROL_TYPE),
])
async def test_invalid_profile_remote_cannot_reach_pairing(hass, app, control, field):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data(app, control, **{const.CONF_VIBRADORM_RESTORED: app == "caresse"})
    with patch.object(flow, "async_step_manual_pairing", new=AsyncMock()) as pair:
        result = await flow.async_step_vibradorm_app({const.CONF_VIBRADORM_CONTROL_TYPE: control})
    assert result["errors"] == {field: "vibradorm_app_invalid"}
    pair.assert_not_awaited()


async def test_exact_native_bond_skips_first_information_and_pair_rpc(hass):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._manual_data = app_data("werkmeister", "7")
    client = MagicMock(pair=AsyncMock(), disconnect=AsyncMock())
    path = ConnectionPath(SOURCE, transport=TransportClass.LOCAL, adapter="hci0")
    native = BondEvidence(BondVerificationStatus.NATIVE_OS_STATE, BondOwner.from_path(path), "native", "now", kind=BondEvidenceKind.NATIVE_OS_STATE)
    with (
        patch("bleak_retry_connector.establish_connection", new=AsyncMock(return_value=client)),
        patch(PREFIX + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(PREFIX + "client_source", return_value=SOURCE),
        patch(PREFIX + "async_path_for_source", return_value=path),
        patch(PREFIX + "async_verify_native_bond", new=AsyncMock(return_value=native)),
        patch("custom_components.adjustable_bed.beds.vibradorm_app.async_prepare_vibradorm_app_pairing", new=AsyncMock()) as info,
        patch(PREFIX + "async_verify_authenticated_access", new=AsyncMock()) as authenticated,
    ):
        result = await flow._attempt_pairing_with_capture(ADDRESS, request_bond=True, track_for_flow_cleanup=False, device=BLEDevice(ADDRESS, "Bed", {}), preferred_adapter="auto")
    assert result is native
    info.assert_not_awaited()
    authenticated.assert_not_awaited()
    client.pair.assert_not_awaited()
    client.disconnect.assert_awaited_once()
