"""Explicit VMAT configuration, process state and public entity capabilities."""

from unittest.mock import AsyncMock, patch

import pytest
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


@pytest.mark.parametrize("remote", VMAT_REMOTES)
def test_normalization_uses_remote_not_submitted_capability_flags(remote):
    profile = VMAT_REMOTES[remote]
    data = _vibradorm_app_data({const.CONF_VIBRADORM_APP_PROFILE: "vmat"}, {
        const.CONF_VIBRADORM_VMAT_REMOTE: remote,
        const.CONF_VIBRADORM_CONTROL_TYPE: "99",
        const.CONF_VIBRADORM_MASSAGE: not profile.massage,
        const.CONF_VIBRADORM_FLOOR_LIGHT: not profile.floor_light,
    })
    assert _vibradorm_app_errors(data) == {}
    assert data[const.CONF_VIBRADORM_CONTROL_TYPE] == str(profile.control_type)
    assert data[const.CONF_VIBRADORM_MASSAGE] is profile.massage
    assert data[const.CONF_VIBRADORM_FLOOR_LIGHT] is profile.floor_light
    assert data[const.CONF_VIBRADORM_FLOOR_DEFAULT] == (6 if profile.light_extension else 8)


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
async def test_real_setup_stages_then_pair_proof_close_disconnect_and_metadata_retention(hass, absent):
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

    c.client.write_gatt_char.side_effect = write
    c.client.pair = AsyncMock(side_effect=pair)
    c.client.disconnect = AsyncMock(side_effect=disconnect)
    prefix = "custom_components.adjustable_bed.config_flow."
    with (
        patch("bleak_retry_connector.establish_connection", side_effect=connect),
        patch(prefix + "async_predict_path", return_value=PathPrediction(path, (path,))),
        patch(prefix + "client_source", return_value=source),
        patch(prefix + "async_path_for_source", return_value=path),
        patch(prefix + "async_verify_native_bond", new=AsyncMock(side_effect=[unknown, native_absent if absent else native])),
    ):
        result = await flow._attempt_pairing_with_capture(
            address, request_bond=True, track_for_flow_cleanup=False,
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
    assert events == ["connect", "pair", "close", "disconnect"]
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["opmode"] == "-127"
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["xmc_status"] == "129"
    assert flow._manual_data[const.CONF_VIBRADORM_APP_METADATA]["revision_id"] == "revision_id"
