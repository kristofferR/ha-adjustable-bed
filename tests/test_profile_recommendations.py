"""Observed profile mismatches, persistent decisions and non-mutating review."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.app_state_store import AppStateStore, app_state_storage_key
from custom_components.adjustable_bed.const import (
    ADJUSTABLE_LUMBAR_VARIANT_OKIN,
    ADJUSTABLE_LUMBAR_VARIANT_STAR,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    NORDIC_UART_SERVICE_UUID,
    PAIR_MODE_SEPARATE_ADDRESS,
)
from custom_components.adjustable_bed.profile_recommendations import (
    ISSUE_PREFIX,
    ProfileRecommendationRepairFlow,
    _watches,
    async_watch_profile_recommendations,
    recommend_profile,
)
from custom_components.adjustable_bed.repairs import async_create_fix_flow

ADDRESS = "AA:BB:CC:DD:EE:30"
OTHER = "AA:BB:CC:DD:EE:31"
HISTORY = (
    "custom_components.adjustable_bed.profile_recommendations.bluetooth.async_last_service_info"
)
REGISTER = (
    "custom_components.adjustable_bed.profile_recommendations.bluetooth.async_register_callback"
)
STATE = {
    "adjustable_lumbar_branch": "star",
    "adjustable_lumbar_table": "35_22_01",
    "adjustable_lumbar_manufacturer": "53 54 41 52",
}


def info(name: str = "Star254202000001", address: str = ADDRESS) -> MagicMock:
    result = MagicMock(
        address=address,
        service_uuids=[NORDIC_UART_SERVICE_UUID],
        manufacturer_data={},
        service_data={},
    )
    result.name = name
    return result


def entry(hass: HomeAssistant, **changes: object) -> MockConfigEntry:
    result = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom",
        unique_id=ADDRESS,
        version=4,
        minor_version=3,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Bedroom",
            CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR,
            CONF_PROTOCOL_VARIANT: "auto",
            CONF_MOTOR_COUNT: 3,
            **changes,
        },
    )
    result.add_to_hass(hass)
    result.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    return result


def coordinator(address: str = ADDRESS) -> MagicMock:
    result = MagicMock(address=address, bed_type=BED_TYPE_ADJUSTABLE_LUMBAR, is_connected=True)
    result.controller.protocol_diagnostics = dict(STATE)
    return result


async def watch(hass, config_entry=None, coord=None, side=None):
    config_entry = config_entry or entry(hass)
    coord = coord or coordinator()
    with patch(HISTORY, return_value=info(address=coord.address)), patch(REGISTER):
        await async_watch_profile_recommendations(hass, config_entry, ((side, coord),))
    return _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_{side or 'standalone'}"]


def issue(hass, target):
    return ir.async_get(hass).async_get_issue(DOMAIN, target.issue_id)


async def open_flow(hass, target):
    current = issue(hass, target)
    assert current is not None
    flow = await async_create_fix_flow(hass, current.issue_id, current.data)
    assert isinstance(flow, ProfileRecommendationRepairFlow)
    flow.hass = hass
    return flow


@pytest.mark.parametrize("variant", [None, "auto", ADJUSTABLE_LUMBAR_VARIANT_STAR])
def test_reported_identity_suggests_box25_despite_known_app_ambiguity(variant):
    suggestion = recommend_profile(
        {CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR, CONF_PROTOCOL_VARIANT: variant}, info(), STATE
    )
    assert suggestion is not None
    assert suggestion.suggested == BED_TYPE_SLEEPYS_BOX25


@pytest.mark.parametrize(
    ("name", "variant", "state", "services"),
    [
        ("Star250000000001", "auto", STATE, [NORDIC_UART_SERVICE_UUID]),
        ("Star254202", "auto", STATE, [NORDIC_UART_SERVICE_UUID]),
        ("Star254202000001", ADJUSTABLE_LUMBAR_VARIANT_OKIN, STATE, [NORDIC_UART_SERVICE_UUID]),
        (
            "Star254202000001",
            "auto",
            {**STATE, "adjustable_lumbar_manufacturer": "53 54 41 52 00"},
            [NORDIC_UART_SERVICE_UUID],
        ),
        (
            "Star254202000001",
            "auto",
            {**STATE, "adjustable_lumbar_table": "25_42_02"},
            [NORDIC_UART_SERVICE_UUID],
        ),
        ("Star254202000001", "auto", {}, [NORDIC_UART_SERVICE_UUID]),
        ("Star254202000001", "auto", STATE, []),
    ],
)
def test_shared_names_services_or_incomplete_connection_are_insufficient(
    name, variant, state, services
):
    observed = info(name)
    observed.service_uuids = services
    assert (
        recommend_profile(
            {CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR, CONF_PROTOCOL_VARIANT: variant},
            observed,
            state,
        )
        is None
    )


async def test_watch_uses_existing_evidence_without_connecting_or_writing(hass):
    config_entry = entry(hass)
    coord = coordinator()
    before = dict(config_entry.data)
    target = await watch(hass, config_entry, coord)
    assert issue(hass, target).translation_key == "lumbar_star254202_box25"
    coord.async_connect.assert_not_called()
    coord.async_execute_controller_command.assert_not_called()
    assert config_entry.data == before
    coord.register_connection_state_callback.assert_called_once_with(target.connected)


async def test_idle_disconnect_keeps_evidence_but_a_new_connection_replaces_it(hass):
    coord = coordinator()
    target = await watch(hass, coord=coord)
    coord.is_connected = False
    coord.controller = None
    target.seen(info(), MagicMock())
    assert issue(hass, target) is not None
    coord.controller = MagicMock(
        protocol_diagnostics={**STATE, "adjustable_lumbar_manufacturer": None}
    )
    coord.is_connected = True
    with patch(HISTORY, return_value=info()):
        target.connected(True)
    assert issue(hass, target) is None


async def test_new_advertisement_withdraws_suggestion_and_unload_unregisters(hass):
    target = await watch(hass)
    target.seen(info("Star250000000001"), MagicMock())
    assert issue(hass, target) is None
    target.seen(info(), MagicMock())
    assert issue(hass, target) is not None
    await target.entry._async_process_on_unload(hass)
    assert target.issue_id not in _watches(hass)
    assert issue(hass, target) is None


async def test_keep_survives_storage_reload_without_changing_configuration(hass):
    target = await watch(hass)
    before = dict(target.entry.data)
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        result = await flow.async_step_init({"action": "keep"})
    assert result["type"] == "create_entry"
    assert issue(hass, target) is None
    assert target.entry.data == before
    # New store instance reads the disk-backed HA storage, not watcher memory.
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert decisions == {"lumbar_star254202_box25": True}
    await target.entry._async_process_on_unload(hass)
    hass.data[DOMAIN]["app_state_stores"].clear()
    target = await watch(hass, target.entry, target.coordinator)
    assert issue(hass, target) is None


async def test_native_ignore_persists_the_same_decision(hass):
    target = await watch(hass)
    with patch(HISTORY, return_value=info()):
        ir.async_ignore_issue(hass, DOMAIN, target.issue_id, True)
        await hass.async_block_till_done()
    assert issue(hass, target) is None
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert decisions == {"lumbar_star254202_box25": True}


async def test_failed_save_keeps_the_notice_open(hass):
    target = await watch(hass)
    flow = await open_flow(hass, target)
    with (
        patch(HISTORY, return_value=info()),
        patch.object(AppStateStore, "async_write", side_effect=OSError),
    ):
        result = await flow.async_step_init({"action": "keep"})
    assert result["errors"] == {"base": "save_failed"}
    assert issue(hass, target) is not None
    assert target.dismissed == {}


async def test_review_hands_off_without_saving_and_options_confirms(
    hass, enable_custom_integrations
):
    target = await watch(hass)
    before = dict(target.entry.data)
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        form = await flow.async_step_init({"issue_id": target.issue_id})
        result = await flow.async_step_init({"action": "review"})
    assert form["step_id"] == "init"
    assert result["type"] == "abort" and result["reason"] == "review_started"
    assert target.entry.data == before
    assert issue(hass, target) is not None
    kind, flow_id = result["next_flow"]
    assert kind == "options_flow"
    manager = hass.config_entries.options
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await manager.async_configure(flow_id, {})
    assert result["type"] == "create_entry"
    assert target.entry.data[CONF_BED_TYPE] == BED_TYPE_SLEEPYS_BOX25
    with patch(HISTORY, return_value=info()):
        target.refresh()
    assert issue(hass, target) is None


async def test_cancelled_review_keeps_configuration_and_suggestion(
    hass, enable_custom_integrations
):
    target = await watch(hass)
    before = dict(target.entry.data)
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        result = await flow.async_step_init({"action": "review"})
    hass.config_entries.options.async_abort(result["next_flow"][1])
    assert target.entry.data == before
    assert issue(hass, target) is not None


@pytest.mark.parametrize("change", [{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25}, {CONF_ADDRESS: OTHER}])
async def test_stale_repair_cannot_change_a_new_configuration(hass, change):
    target = await watch(hass)
    flow = await open_flow(hass, target)
    hass.config_entries.async_update_entry(target.entry, data={**target.entry.data, **change})
    with patch(HISTORY, return_value=info()):
        result = await flow.async_step_init({"action": "review"})
    assert result["reason"] == "recommendation_changed"
    assert not hass.config_entries.options.async_progress()


async def test_pair_reviews_and_dismissals_are_per_physical_side(hass, enable_custom_integrations):
    config_entry = entry(
        hass,
        **{
            CONF_PAIR_ID: "pair",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_CHILDREN: [
                {
                    CONF_SIDE: "left",
                    CONF_ADDRESS: ADDRESS,
                    CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR,
                },
                {
                    CONF_SIDE: "right",
                    CONF_ADDRESS: OTHER,
                    CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR,
                },
            ],
        },
    )
    left = await watch(hass, config_entry, coordinator(), "left")
    right = await watch(hass, config_entry, coordinator(OTHER), "right")
    before = dict(config_entry.data)
    flow = await open_flow(hass, left)
    with patch(HISTORY, return_value=info()):
        form = await flow.async_step_init()
        result = await flow.async_step_paired({"action": "review"})
    assert form["step_id"] == "paired"
    assert form["description_placeholders"]["side"] == "left"
    assert config_entry.data == before
    hass.config_entries.options.async_abort(result["next_flow"][1])
    with patch(HISTORY, return_value=info()):
        await flow.async_step_paired({"action": "keep"})
    assert issue(hass, left) is None
    assert issue(hass, right) is not None
    assert config_entry.data == before
    # Split/recombine does not alter the physical bed's decision.
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert decisions == {"lumbar_star254202_box25": True}
    assert await AppStateStore(hass, OTHER).async_slot("profile_recommendations") == {}


async def test_only_a_materially_new_rule_can_ask_after_a_dismissal(hass, hass_storage):
    hass_storage[app_state_storage_key(ADDRESS)] = {
        "version": 1,
        "minor_version": 1,
        "key": app_state_storage_key(ADDRESS),
        "data": {"profile_recommendations": {"an_older_different_recommendation": True}},
    }
    target = await watch(hass)
    assert issue(hass, target) is not None


async def test_first_normal_connection_supplies_missing_evidence(hass):
    coord = coordinator()
    coord.is_connected = False
    coord.controller = None
    target = await watch(hass, coord=coord)
    assert issue(hass, target) is None
    coord.controller = MagicMock(protocol_diagnostics=dict(STATE))
    coord.is_connected = True
    with patch(HISTORY, return_value=info()):
        target.connected(True)
    assert issue(hass, target) is not None


async def test_repeated_advertisements_do_not_repeat_detection(hass):
    target = await watch(hass)
    with patch(
        "custom_components.adjustable_bed.profile_recommendations.detect_bed_type_detailed"
    ) as detect:
        for rssi in (-55, -56, -57):
            observation = info()
            observation.rssi = rssi
            target.seen(observation, MagicMock())
    detect.assert_not_called()
    assert issue(hass, target) is not None


@pytest.mark.parametrize(
    "field,value", [("requires_characteristic_check", True), ("ambiguous_types", ["starcode_m5x5"])]
)
def test_new_detection_ambiguity_does_not_reuse_the_old_recommendation(field, value):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    detected = detect_bed_type_detailed(info())
    setattr(detected, field, value)
    with patch(
        "custom_components.adjustable_bed.profile_recommendations.detect_bed_type_detailed",
        return_value=detected,
    ):
        assert recommend_profile({CONF_BED_TYPE: BED_TYPE_ADJUSTABLE_LUMBAR}, info(), STATE) is None


def test_notice_describes_the_actual_controls_lost_and_gained():
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.beds.adjustable_lumbar import AdjustableLumbarController
    from custom_components.adjustable_bed.beds.sleepys_box25 import SleepysBox25Controller

    current = AdjustableLumbarController(MagicMock(), device_name="Star254202000001")
    suggested = SleepysBox25Controller(MagicMock())
    root = Path("custom_components/adjustable_bed")
    strings = json.loads((root / "strings.json").read_text())
    english = json.loads((root / "translations/en.json").read_text())
    notice = strings["issues"]["lumbar_star254202_box25"]
    assert notice == english["issues"]["lumbar_star254202_box25"]
    text = notice["fix_flow"]["step"]["init"]["description"]
    assert not current.supports_memory_presets
    assert suggested.supports_memory_presets and suggested.supports_memory_programming
    assert current.supports_preset_incline and not suggested.supports_preset_incline
    assert suggested.supports_preset_tv
    for button in current.controller_button_specs:
        assert button.key not in {other.key for other in suggested.controller_button_specs}
        assert button.name in text


async def test_configuration_change_during_handoff_aborts_without_submitting_profile(
    hass, enable_custom_integrations
):
    target = await watch(hass)
    flow = await open_flow(hass, target)
    manager = hass.config_entries.options
    configure = manager.async_configure
    submissions = []

    async def concurrently_changed(flow_id, user_input):
        submissions.append(user_input)
        result = await configure(flow_id, user_input)
        hass.config_entries.async_update_entry(
            target.entry, data={**target.entry.data, CONF_ADDRESS: OTHER}
        )
        return result

    with (
        patch(HISTORY, return_value=info()),
        patch.object(manager, "async_configure", side_effect=concurrently_changed),
    ):
        result = await flow.async_step_init({"action": "review"})
    assert result["reason"] == "recommendation_changed"
    assert submissions == [{"next_step_id": "settings"}]
    assert target.entry.data[CONF_ADDRESS] == OTHER
    assert target.entry.data[CONF_BED_TYPE] == BED_TYPE_ADJUSTABLE_LUMBAR
    assert not manager.async_progress()
