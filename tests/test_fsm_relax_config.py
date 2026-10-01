"""Explicit app selection, offline snapshot and local options persistence."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
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
    flow.async_step_manual_pairing = AsyncMock(return_value={"type": FlowResultType.CREATE_ENTRY})
    form = await flow.async_step_fsm_relax()
    assert form["step_id"] == "fsm_relax"
    await flow.async_step_fsm_relax(data())
    assert flow._manual_data[const.CONF_FSM_RELAX_LAYOUT] == "bed"
    assert flow._manual_data[const.CONF_FSM_RELAX_MEMORY_NAMES][0] == "Sleep"
    assert flow._manual_data[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert flow._manual_data[const.CONF_HAS_MASSAGE] is False
    flow.async_step_manual_pairing.assert_awaited_once()
    flow.async_step_manual_pairing.reset_mock()
    form = await flow.async_step_fsm_relax({const.CONF_FSM_RELAX_MEMORY_NAMES: [""] * 7})
    assert form["errors"] == {"base": "fsm_relax_invalid"}
    flow.async_step_manual_pairing.assert_not_called()


def test_profile_fields_schema_and_exact_options_validation():
    schema = {}
    _add_fsm_relax_schema_fields(schema, data())
    result = vol.Schema(schema)({})
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
