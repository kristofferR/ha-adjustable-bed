"""Explicit app selection, offline snapshot and local options persistence."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.fsm_relax import FsmRelaxController
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _add_fsm_relax_schema_fields,
    _fsm_relax_errors,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.fsm_relax_state import FsmRelaxState


def data():
    return {
        const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
        const.CONF_FSM_RELAX_LAYOUT: "bed",
        const.CONF_FSM_RELAX_LIGHT: True,
        const.CONF_FSM_RELAX_MASSAGE: True,
        **dict(zip(const.CONF_FSM_RELAX_REVERSALS, (True, False, True, False), strict=True)),
        const.CONF_FSM_RELAX_MEMORY_NAMES: ["Sleep"] + [""] * 7,
    }


async def test_factory_retains_exact_profile_store_and_legacy_limoss(hass):
    entry = MockConfigEntry(domain=const.DOMAIN, data=data())
    c = MagicMock(hass=hass, entry=entry, address="AA:BB:CC:DD:EE:FF", client=None)
    c._cancel_command = asyncio.Event()
    stored = FsmRelaxState(hass, entry.entry_id, c.address)
    await stored.async_save_capabilities(bytes.fromhex("0206000008"))
    await stored.async_save_slot(8, {0: -1})
    ctrl = await create_controller(c, const.BED_TYPE_FSM_RELAX, None, None)
    assert isinstance(ctrl, FsmRelaxController)
    assert ctrl.profile.layout == "bed"
    assert ctrl.profile.reversals == (True, False, True, False)
    assert ctrl.profile.light_enabled and ctrl.profile.massage_enabled
    assert ctrl.key_count == 6 and ctrl.memory_slot_count == 8
    assert ctrl.local.slots[8] == {0: -1} and ctrl.memory_slot_names[0] == "Sleep"
    assert ctrl.motor_control_specs == () and not ctrl.supports_position_feedback
    ctrl._counter = 255
    rebuilt = await create_controller(c, const.BED_TYPE_FSM_RELAX, None, None)
    assert rebuilt._counter == 255
    rebuilt._counter = 0
    assert ctrl._counter == 0
    assert rebuilt._memory_lock is ctrl._memory_lock
    c.client = MagicMock(is_connected=True)
    legacy = await create_controller(c, const.BED_TYPE_LIMOSS, None, c.client)
    assert type(legacy) is LimossController
    assert legacy.supports_preset_flat


async def test_explicit_profile_step_validates_and_persists_all_values(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX}
    flow._finish_with_verify = AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY})
    form = await flow.async_step_fsm_relax()
    assert form["step_id"] == "fsm_relax"
    await flow.async_step_fsm_relax(data())
    assert flow._manual_data[const.CONF_FSM_RELAX_LAYOUT] == "bed"
    assert flow._manual_data[const.CONF_FSM_RELAX_MEMORY_NAMES][0] == "Sleep"
    assert flow._manual_data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert flow._manual_data[const.CONF_HAS_MASSAGE] is False
    flow._finish_with_verify.assert_awaited_once_with(flow._manual_data, "Adjustable Bed")
    flow._finish_with_verify.reset_mock()
    form = await flow.async_step_fsm_relax({const.CONF_FSM_RELAX_MEMORY_NAMES: [""] * 7})
    assert form["errors"] == {"base": "fsm_relax_invalid"}
    flow._finish_with_verify.assert_not_called()


def test_profile_fields_schema_and_exact_options_validation():
    schema = {}
    _add_fsm_relax_schema_fields(schema, data())
    result = vol.Schema(schema)({})
    assert isinstance(result, dict)
    assert result[const.CONF_FSM_RELAX_LAYOUT] == "bed"
    assert result[const.CONF_FSM_RELAX_MEMORY_NAMES][0] == "Sleep"
    assert _fsm_relax_errors(data()) == {}
    assert _fsm_relax_errors({**data(), const.CONF_FSM_RELAX_REVERSALS[0]: "yes"})
    assert const.BED_TYPE_FSM_RELAX not in const.BEDS_WITH_POSITION_FEEDBACK
    assert const.BED_TYPE_FSM_RELAX in const.BEDS_WITHOUT_ANGLE_FEEDBACK
    assert const.BED_TYPE_FSM_RELAX in {option["value"] for option in get_bed_type_options()}


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        (None, b"xlimoss", False),
        ("Limoss", None, False),
        ("limoss", None, True),
        ("xlimoss ", None, True),
        ("other", b"limoss", False),
        ("other", b"xlimoss", True),
        ("other", b"xLIMOSS", False),
        ("other", b"\xfflimoss", True),
    ],
)
def test_exact_source_candidate_predicate_and_raw_record_limit(name, raw, expected):
    from custom_components.adjustable_bed.fsm_relax_discovery import matches_fsm_relax_candidate

    assert matches_fsm_relax_candidate(name, raw) is expected


def test_candidate_is_ambiguous_never_selects_app_from_shared_transport():
    from types import SimpleNamespace

    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = SimpleNamespace(
        name="limossBed",
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=["0000ffe0-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={},
        service_data={},
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type == const.BED_TYPE_LIMOSS
    assert const.BED_TYPE_FSM_RELAX in result.ambiguous_types


def test_physical_profile_fields_never_inherit_from_paired_parent():
    from custom_components.adjustable_bed.pairing import inheritable_child_fields
    parent = {**data(), const.CONF_MOTOR_PULSE_COUNT: 4}
    inherited = inheritable_child_fields(parent)
    for key in (const.CONF_FSM_RELAX_LAYOUT, const.CONF_FSM_RELAX_LIGHT, const.CONF_FSM_RELAX_MASSAGE, const.CONF_FSM_RELAX_MEMORY_NAMES, *const.CONF_FSM_RELAX_REVERSALS):
        assert key not in inherited
    assert inherited[const.CONF_MOTOR_PULSE_COUNT] == 4


@pytest.mark.parametrize("existing_fsm", (False, True))
async def test_pair_options_requires_unpair_for_new_route_or_physical_profile_edit(hass, existing_fsm):
    from homeassistant.const import CONF_ADDRESS

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    left = {**data(), CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}
    right = {**data(), CONF_ADDRESS: "11:22:33:44:55:66", const.CONF_FSM_RELAX_LAYOUT: "chair"}
    if not existing_fsm:
        left[const.CONF_BED_TYPE] = right[const.CONF_BED_TYPE] = const.BED_TYPE_LIMOSS
    entry = MockConfigEntry(domain=const.DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    shown = await flow.async_step_settings()
    fields = {marker.schema for marker in shown["data_schema"].schema}
    assert const.CONF_FSM_RELAX_LAYOUT not in fields
    submitted = {const.CONF_FSM_RELAX_LAYOUT: "bed"} if existing_fsm else {const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX}
    result = await flow.async_step_settings(submitted)
    assert result["errors"] == {"base": "fsm_relax_unpair_first"}
    assert [child[const.CONF_FSM_RELAX_LAYOUT] for child in entry.data[const.CONF_PAIR_CHILDREN]] == ["bed", "chair"]
    assert [child[const.CONF_BED_TYPE] for child in entry.data[const.CONF_PAIR_CHILDREN]] == [left[const.CONF_BED_TYPE], right[const.CONF_BED_TYPE]]


@pytest.mark.parametrize("name,chooser", [("limossBed", True), ("LimossBed", False)])
async def test_public_ffe0_discovery_requires_choice_only_for_exact_app_candidate(
    hass, enable_custom_integrations, mock_bluetooth_service_info, name, chooser,
):
    from homeassistant.config_entries import SOURCE_BLUETOOTH

    info = mock_bluetooth_service_info
    info.name = name
    info.service_uuids = ["0000ffe0-0000-1000-8000-00805f9b34fb"]
    info.manufacturer_data = {}
    info.service_data = {}
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info,
    )
    assert result["step_id"] == ("bluetooth_disambiguate" if chooser else "bluetooth_confirm")
    if chooser:
        schema = result["data_schema"]
        for candidate in (const.BED_TYPE_LIMOSS, const.BED_TYPE_FSM_RELAX):
            assert schema({"bed_type_choice": candidate})["bed_type_choice"] == candidate
        selected = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"bed_type_choice": const.BED_TYPE_FSM_RELAX},
        )
        assert selected["step_id"] == "bluetooth_confirm"
        assert "Selected: FSM Relax" in selected["description_placeholders"]["detection_note"]
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize("route", ("manual", "bluetooth"))
async def test_public_explicit_profile_finishes_without_pairing_backend(
    hass, enable_custom_integrations, mock_bluetooth_service_info, route,
):
    from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
    from homeassistant.const import CONF_ADDRESS

    with (
        patch("custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]),
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch("bleak_retry_connector.establish_connection", AsyncMock(side_effect=NotImplementedError("pairing unsupported"))) as connect,
        patch("custom_components.adjustable_bed.async_setup_entry", AsyncMock(return_value=True)),
    ):
        if route == "manual":
            result = await hass.config_entries.flow.async_init(const.DOMAIN, context={"source": SOURCE_USER})
            result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_ADDRESS: "manual"})
            assert result["step_id"] == "manual_entry"
        else:
            info = mock_bluetooth_service_info
            info.name = "limossBed"
            info.service_uuids = ["0000ffe0-0000-1000-8000-00805f9b34fb"]
            info.manufacturer_data = {}
            info.service_data = {}
            result = await hass.config_entries.flow.async_init(
                const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info,
            )
            if result["step_id"] == "bluetooth_disambiguate":
                result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={"bed_type_choice": const.BED_TYPE_FSM_RELAX})
            assert result["step_id"] == "bluetooth_confirm"
        submitted = {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "App profile",
            const.CONF_BED_TYPE: const.BED_TYPE_FSM_RELAX,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_PREFERRED_ADAPTER: const.ADAPTER_AUTO,
            const.CONF_DISCONNECT_AFTER_COMMAND: True,
        }
        if route == "bluetooth":
            submitted.pop(CONF_ADDRESS)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=submitted)
        assert result["step_id"] == "fsm_relax"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={
            key: value for key, value in data().items() if key != const.CONF_BED_TYPE
        })
        assert result["type"] == FlowResultType.CREATE_ENTRY
        saved = result["data"]
        assert saved[const.CONF_BED_TYPE] == const.BED_TYPE_FSM_RELAX
        assert saved[const.CONF_FSM_RELAX_LAYOUT] == "bed"
        assert saved[const.CONF_FSM_RELAX_REVERSALS[0]] is True
        assert saved[const.CONF_FSM_RELAX_MEMORY_NAMES][0] == "Sleep"
        assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True
        assert const.BED_TYPE_FSM_RELAX not in const.BEDS_REQUIRING_PAIRING
        connect.assert_not_called()
        await hass.async_block_till_done()


async def test_profile_keeps_normal_verification_when_transport_available(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {**data(), CONF_NAME: "App profile", "address": "AA:BB:CC:DD:EE:FF"}
    with (
        patch.object(flow, "_verification_possible", return_value=True),
        patch.object(flow, "async_step_setup_progress", AsyncMock(return_value={"type": FlowResultType.FORM, "step_id": "setup_progress"})) as progress,
        patch.object(flow, "async_step_manual_pairing", AsyncMock(side_effect=AssertionError("unexpected pairing"))) as pairing,
    ):
        result = await flow.async_step_fsm_relax({})
    assert result["step_id"] == "setup_progress"
    assert flow._pending_entry is not None
    assert flow._pending_entry[const.CONF_BED_TYPE] == const.BED_TYPE_FSM_RELAX
    progress.assert_awaited_once()
    pairing.assert_not_called()
