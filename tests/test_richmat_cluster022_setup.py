"""Explicit app selection survives setup, Configure, restore and native pairing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _async_sync_profile_ids,
    _build_paired_children,
    const,
)
from custom_components.adjustable_bed.beds.richmat_mh.app_controller import RichmatMHAppController
from custom_components.adjustable_bed.beds.richmat_mh.app_sleep import (
    RichmatMHAppSleepController,
)
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import async_register_children, side_identifier
from custom_components.adjustable_bed.profile_id import profile_route, resolve_profile_id
from custom_components.adjustable_bed.services import (
    _get_support_bundle_target_from_device,
    _resolve_sided_targets,
)
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_paired_receiver_questions import child, pair_entry, receiver_form
from tests.test_paired_receiver_questions import fields as receiver_fields
from tests.test_richmat_family_flow import answer, entry_for, fields, setup_flow

APPS = (("nisco", "Nisco"), ("mlily_supreme", "MLILY Supreme"))


@pytest.mark.parametrize(("app", "label"), APPS)
async def test_new_install_and_configure_keep_explicit_app(hass, app, label) -> None:
    bed_type = f"richmat_{app}"
    # A common Bluetooth model name cannot choose a sibling app over this answer.
    flow = setup_flow(hass, name="CFRM0001")
    form, finish = await answer(flow, app)
    assert form["step_id"] == "profile_questions"
    assert const.CONF_PROTOCOL_VARIANT in fields(form)
    finish.assert_not_awaited()
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: "model_cfrm"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_BED_TYPE] == bed_type
    assert profile_route(resolve_profile_id(saved)).bed_type == bed_type

    entry = entry_for(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.hass, options.handler = hass, entry.entry_id
    form = await options.async_step_settings()
    selector = form["data_schema"].schema[fields(form)[const.CONF_BED_TYPE]]
    choice = selector(f"{label} app · Richmat")
    form = await options.async_step_settings({const.CONF_BED_TYPE: choice})
    assert const.CONF_PROTOCOL_VARIANT in fields(form)
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_RICHMAT
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await options.async_step_settings({const.CONF_PROTOCOL_VARIANT: "model_cfrm"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BED_TYPE] == bed_type
    # The mocked reload above omits setup, which normally synchronizes ids.
    _async_sync_profile_ids(hass, entry)
    assert profile_route(entry.data[const.CONF_PROFILE_ID]).variant == "model_cfrm"


@pytest.mark.parametrize(("app", "_label"), APPS)
@pytest.mark.parametrize("variant", ["model_cfrm", "sleep"])
async def test_imported_serialized_profile_uses_actual_factory(hass, app, _label, variant) -> None:
    data = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        const.CONF_BED_TYPE: f"richmat_{app}",
        const.CONF_PROTOCOL_VARIANT: variant,
        # Deliberately looks like a different member of the old Richmat family.
        const.CONF_BLE_DEVICE_NAME: "VORM1234",
        "capabilities": {"richmat_mh": {
            "app": app, "model": "cfrm", "version": "0001", "call_page": True,
            "dev": {"led": True}, "transmit_mode": 2,
        }},
    }
    data[const.CONF_PROFILE_ID] = resolve_profile_id(data)
    # The integration has no import wizard: imported/restored entries use the
    # same serialized schema and profile resolver as ordinary entries.
    entry = MockConfigEntry(domain=const.DOMAIN, source="import", version=5, data=json.loads(json.dumps(data)))
    entry.add_to_hass(hass)
    route = profile_route(entry.data[const.CONF_PROFILE_ID])
    coordinator = _FactoryCoordinator()
    coordinator.hass, coordinator.entry = hass, entry
    restored = await create_controller(coordinator, route.bed_type, route.variant, None)
    assert restored.app == app
    assert restored.supports_single_address_pairing is False
    if variant == "sleep":
        assert isinstance(restored, RichmatMHAppSleepController)
        assert restored.motor_control_specs == ()
    else:
        assert isinstance(restored, RichmatMHAppController)
        assert restored.model.model_id == "cfrm"
        assert restored.route == "C"
        assert restored._transmit_mode == 2
        assert restored.profile.key == f"richmat_mh_{app}"


async def test_pair_configure_preserves_other_physical_profile(hass, enable_custom_integrations) -> None:
    entry = pair_entry(hass, {
        const.CONF_BED_TYPE: "richmat_nisco", const.CONF_PROTOCOL_VARIANT: "model_cfrm",
    }, {
        const.CONF_BED_TYPE: "richmat_mlily_supreme", const.CONF_PROTOCOL_VARIANT: "model_3i",
    })
    _async_sync_profile_ids(hass, entry)
    right_before = child(entry, "right")
    form = await receiver_form(hass, entry, "left")
    assert receiver_fields(form)[const.CONF_PROTOCOL_VARIANT].default() == "model_cfrm"
    result = await hass.config_entries.options.async_configure(form["flow_id"], {
        **form["data_schema"]({}), const.CONF_PROTOCOL_VARIANT: "model_garm",
    })
    assert result["type"] is FlowResultType.CREATE_ENTRY
    _async_sync_profile_ids(hass, entry)
    left, right = child(entry, "left"), child(entry, "right")
    assert left[const.CONF_PROTOCOL_VARIANT] == "model_garm"
    assert profile_route(left[const.CONF_PROFILE_ID]).bed_type == "richmat_nisco"
    assert right == right_before
    assert profile_route(right[const.CONF_PROFILE_ID]).variant == "model_3i"


async def test_actual_two_address_pair_has_native_side_safe_devices(hass) -> None:
    entry = pair_entry(hass, {
        const.CONF_BED_TYPE: "richmat_nisco", const.CONF_PROTOCOL_VARIANT: "model_cfrm",
    }, {
        const.CONF_BED_TYPE: "richmat_mlily_supreme", const.CONF_PROTOCOL_VARIANT: "model_3i",
    })
    paired = PairedBedCoordinator(hass, entry, _build_paired_children(hass, entry))
    _async_ensure_paired_device_registry(hass, entry, paired)
    async_register_children(hass, paired)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = paired
    children = dr.async_child_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    left = next(row for row in children if side_identifier(paired, "left") in row.identifiers)
    right = next(row for row in children if side_identifier(paired, "right") in row.identifiers)
    assert left.parent_device_id == right.parent_device_id
    assert _get_support_bundle_target_from_device(hass, left.id)[0] == paired.children["left"].address
    entry.mock_state(hass, ConfigEntryState.LOADED)
    try:
        assert _resolve_sided_targets(hass, [left.id], None)[0] == [(paired, "left")]
        assert _resolve_sided_targets(hass, [right.id], None)[0] == [(paired, "right")]
        assert _resolve_sided_targets(hass, [left.parent_device_id], None)[0] == [(paired, "both")]
        with pytest.raises(ServiceValidationError, match="conflicts"):
            _resolve_sided_targets(hass, [left.id], "right")
        with pytest.raises(ServiceValidationError):
            _get_support_bundle_target_from_device(hass, left.parent_device_id)
    finally:
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await paired.async_shutdown()


async def test_runtime_mode_and_group_snapshots_persist_on_only_their_physical_side(hass) -> None:
    entry = pair_entry(hass, {
        const.CONF_BED_TYPE: "richmat_nisco", const.CONF_PROTOCOL_VARIANT: "model_cfrm",
    }, {
        const.CONF_BED_TYPE: "richmat_mlily_supreme", const.CONF_PROTOCOL_VARIANT: "model_3i",
    })
    _async_sync_profile_ids(hass, entry)
    children = _build_paired_children(hass, entry)
    paired = PairedBedCoordinator(hass, entry, children)
    try:
        left = await create_controller(children["left"], "richmat_nisco", "model_cfrm", None)
        right = await create_controller(children["right"], "richmat_mlily_supreme", "model_3i", None)
        left.set_transmit_mode("2")
        left_saved = child(entry, "left")
        right.set_transmit_mode("1")
        right.set_group_type("GROUP_SPLIT")
        assert child(entry, "left") == left_saved
        snapshots = {side: child(entry, side)["capabilities"]["richmat_mh"] for side in children}
        assert snapshots["left"]["app"] == "nisco"
        assert snapshots["left"]["transmit_mode"] == 2
        assert snapshots["left"]["group_type"] is None
        assert snapshots["right"]["app"] == "mlily_supreme"
        assert snapshots["right"]["transmit_mode"] == 1
        assert snapshots["right"]["group_type"] == "GROUP_SPLIT"
        restored = await create_controller(children["right"], "richmat_mlily_supreme", "model_3i", None)
        assert restored._transmit_mode == 1 and restored._group_type == "GROUP_SPLIT"
        assert profile_route(child(entry, "left")[const.CONF_PROFILE_ID]).bed_type == "richmat_nisco"
        assert profile_route(child(entry, "right")[const.CONF_PROFILE_ID]).bed_type == "richmat_mlily_supreme"
    finally:
        await paired.async_shutdown()


async def test_disconnected_app_mode_calls_keep_the_offline_controller(hass) -> None:
    from custom_components.adjustable_bed.beds.richmat_mh import app_services as actions
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    data = {
        CONF_ADDRESS: "11:22:33:44:55:77",
        const.CONF_BED_TYPE: "richmat_mlily_supreme",
        const.CONF_PROTOCOL_VARIANT: "model_3i",
        "capabilities": {"richmat_mh": {"app": "mlily_supreme", "model": "3i"}},
    }
    data[const.CONF_PROFILE_ID] = resolve_profile_id(data)
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    offline = coordinator.capability_controller
    assert isinstance(offline, RichmatMHAppController) and coordinator.controller is None
    await async_register_services(hass)
    with (
        patch.object(coordinator, "_schedule_pending_capability_reload"),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
    ):
        for fields in ({"transmit_mode": "1"}, {"motor_group": "group_split"}):
            await hass.services.async_call(const.DOMAIN, actions.SERVICE, {
                "device_id": ["bed"], "action": "app_mode", **fields,
            }, blocking=True)
    assert coordinator.capability_controller is offline
    assert offline._transmit_mode == 1 and offline._group_type == "GROUP_SPLIT"
    assert entry.data["capabilities"]["richmat_mh"]["group_type"] == "GROUP_SPLIT"

