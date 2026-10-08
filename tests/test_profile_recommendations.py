"""Observed profile mismatches, persistent decisions and non-mutating review."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import probatio
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.app_state_store import AppStateStore, app_state_storage_key
from custom_components.adjustable_bed.const import (
    ADJUSTABLE_LUMBAR_VARIANT_OKIN,
    ADJUSTABLE_LUMBAR_VARIANT_STAR,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_KEESON,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    NORDIC_UART_SERVICE_UUID,
    PAIR_MODE_SEPARATE_ADDRESS,
    SUPPORTED_BED_TYPES,
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


@pytest.fixture
def tempur_processor_available(monkeypatch):
    """Exercise the companion profile's registration without depending on PR order."""
    monkeypatch.setattr(
        "custom_components.adjustable_bed.profile_recommendations.SUPPORTED_BED_TYPES",
        [*SUPPORTED_BED_TYPES, "sleeptracker"],
    )


@pytest.mark.parametrize(
    "name", ["KSSF05C201000322", "KSSF05C201000282", "kssf05c201000001"]
)
def test_reported_tempur_lite_entries_offer_separate_processor_guidance(
    tempur_processor_available, name
):
    result = recommend_profile(
        {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ADJUSTABLE_LITE},
        info(name),
        {},
    )
    assert result is not None
    assert result.rule == result.translation_key == "tempur_sleeptracker_processor"
    assert result.current == "keeson:adjustable_lite"
    assert result.choices == ("sleeptracker",)
    assert result.suggested is None  # A different endpoint cannot be preselected in Configure.


@pytest.mark.parametrize(
    ("name", "bed_type", "variant", "services"),
    [
        ("KSSF05C201000001", "keeson", "ksbt", [NORDIC_UART_SERVICE_UUID]),
        ("KSSF05C201000001", "keeson", "auto", [NORDIC_UART_SERVICE_UUID]),
        ("KSSF05C201000001", "sleeptracker", "auto", [NORDIC_UART_SERVICE_UUID]),
        ("KSSF05C201000001", "keeson", "adjustable_lite", []),
        ("KSSF05C", "keeson", "adjustable_lite", [NORDIC_UART_SERVICE_UUID]),
        ("KSSF05C201000001extra", "keeson", "adjustable_lite", [NORDIC_UART_SERVICE_UUID]),
        ("KSSF06C201000001", "keeson", "adjustable_lite", [NORDIC_UART_SERVICE_UUID]),
        ("KSBT03C201000001", "keeson", "adjustable_lite", [NORDIC_UART_SERVICE_UUID]),
    ],
)
def test_other_identities_do_not_get_the_tempur_processor_notice(
    tempur_processor_available, name, bed_type, variant, services
):
    observed = info(name)
    observed.service_uuids = services
    result = recommend_profile(
        {CONF_BED_TYPE: bed_type, CONF_PROTOCOL_VARIANT: variant}, observed, {}
    )
    assert result is None or result.rule != "tempur_sleeptracker_processor"


def test_tempur_processor_notice_waits_until_the_profile_is_registered(monkeypatch):
    monkeypatch.setattr(
        "custom_components.adjustable_bed.profile_recommendations.SUPPORTED_BED_TYPES",
        [bed_type for bed_type in SUPPORTED_BED_TYPES if bed_type != "sleeptracker"],
    )
    result = recommend_profile(
        {CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "adjustable_lite"},
        info("KSSF05C201000001"),
        {},
    )
    assert result is None or result.rule != "tempur_sleeptracker_processor"


async def test_tempur_review_guides_new_setup_and_acknowledges_without_reconfiguring_uart(
    hass, tempur_processor_available
):
    config_entry = entry(
        hass, **{CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "adjustable_lite"}
    )
    observed = info("KSSF05C201000001")
    target = await watch(hass, config_entry)
    target.seen(observed, MagicMock())
    assert issue(hass, target).translation_key == "tempur_sleeptracker_processor"
    original = dict(config_entry.data)
    flow = await open_flow(hass, target)
    with (
        patch(HISTORY, return_value=observed),
        patch.object(hass.config_entries.options, "async_init", AsyncMock()) as configure,
    ):
        result = await flow.async_step_init({"action": "review"})
        assert result["type"] == "form" and result["step_id"] == "processor"
        assert result["data_schema"] is None
        assert result["description_placeholders"]["processor_guide_url"].endswith(
            "/docs/beds/sleeptracker.md"
        )
        assert config_entry.data == original
        assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}
        result = await flow.async_step_processor({})
        configure.assert_not_called()
    assert result["type"] == "create_entry"
    assert config_entry.data == original
    assert issue(hass, target) is None
    target.coordinator.async_connect.assert_not_called()
    target.coordinator.async_execute_controller_command.assert_not_called()
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    record = decisions["history"][0]
    assert record["decision"] == "dismissed" and record["source"] == "keep"
    assert record["choices"] == ["sleeptracker"]
    assert record["previous_profile"] == record["selected_profile"]


async def test_tempur_processor_guide_rejects_a_changed_configuration(
    hass, tempur_processor_available
):
    config_entry = entry(
        hass, **{CONF_BED_TYPE: "keeson", CONF_PROTOCOL_VARIANT: "adjustable_lite"}
    )
    observed = info("KSSF05C201000001")
    target = await watch(hass, config_entry)
    target.seen(observed, MagicMock())
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=observed):
        await flow.async_step_init({"action": "review"})
        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data, CONF_PROTOCOL_VARIANT: "ksbt"}
        )
        result = await flow.async_step_processor({})
    assert result["reason"] == "recommendation_changed"
    assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}


async def test_tempur_pair_notice_guides_each_side_without_splitting(
    hass, tempur_processor_available
):
    config_entry = entry(
        hass,
        **{
            CONF_BED_TYPE: "keeson",
            CONF_PROTOCOL_VARIANT: "adjustable_lite",
            CONF_PAIR_ID: "pair",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: "left", CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: "keeson"},
                {CONF_SIDE: "right", CONF_ADDRESS: OTHER, CONF_BED_TYPE: "keeson"},
            ],
        },
    )
    left = await watch(hass, config_entry, coordinator(), "left")
    right = await watch(hass, config_entry, coordinator(OTHER), "right")
    left_info = info("KSSF05C201000001")
    right_info = info("KSSF05C201000002", OTHER)
    left.seen(left_info, MagicMock())
    right.seen(right_info, MagicMock())
    before = dict(config_entry.data)
    flow = await open_flow(hass, left)
    with patch(HISTORY, return_value=left_info):
        form = await flow.async_step_init()
        assert form["step_id"] == "paired"
        assert form["description_placeholders"]["side"] == "left"
        result = await flow.async_step_paired({"action": "review"})
        assert result["step_id"] == "processor"
        await flow.async_step_processor({})
    assert config_entry.data == before
    assert issue(hass, left) is None
    assert issue(hass, right) is not None


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


@pytest.mark.parametrize("tempur", [False, True])
async def test_repair_action_form_serializes_a_required_choice(
    hass, tempur_processor_available, tempur
):
    config_entry = entry(hass, **{
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_PROTOCOL_VARIANT: KEESON_VARIANT_ADJUSTABLE_LITE,
    }) if tempur else entry(hass)
    target = await watch(hass, config_entry)
    observed = info("KSSF05C201000001") if tempur else info()
    target.seen(observed, MagicMock())
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=observed):
        form = await flow.async_step_init()
    schema = form["data_schema"]
    assert schema is not None
    fields = probatio.to_field_list(schema, custom_serializer=cv.custom_serializer)
    assert len(fields) == 1
    assert fields[0]["name"] == "action" and fields[0]["required"] is True
    assert fields[0]["selector"]["select"]["options"] == ["review", "keep"]
    assert schema({"action": "review"}) == {"action": "review"}
    with pytest.raises(probatio.Invalid):
        schema({})
    with pytest.raises(probatio.Invalid):
        schema({"action": "automatic_switch"})


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
    assert decisions["lumbar_star254202_box25"] is True
    record = decisions["history"][0]
    assert record["decision"] == "dismissed" and record["source"] == "keep"
    assert record["current"] == BED_TYPE_ADJUSTABLE_LUMBAR
    assert record["suggested"] == BED_TYPE_SLEEPYS_BOX25
    assert record["previous_profile"] == record["selected_profile"]
    assert datetime.fromisoformat(record["decided_at"]).utcoffset() == timedelta(0)
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
    assert decisions["lumbar_star254202_box25"] is True
    assert decisions["history"][0]["source"] == "ignore"
    assert decisions["history"][0]["decision"] == "dismissed"


async def test_failed_native_ignore_restores_notice_and_can_be_retried(hass):
    target = await watch(hass)
    with patch(HISTORY, return_value=info()):
        with patch.object(Store, "async_save", side_effect=OSError):
            ir.async_ignore_issue(hass, DOMAIN, target.issue_id, True)
            await hass.async_block_till_done()
        current = issue(hass, target)
        assert current is not None and current.dismissed_version is None
        assert target.dismissed == {}
        assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}
        ir.async_ignore_issue(hass, DOMAIN, target.issue_id, True)
        await hass.async_block_till_done()
    assert issue(hass, target) is None
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert len(decisions["history"]) == 1
    assert decisions["history"][0]["source"] == "ignore"


async def test_failed_save_keeps_the_notice_open(hass):
    target = await watch(hass)
    flow = await open_flow(hass, target)
    with (
        patch(HISTORY, return_value=info()),
        patch.object(Store, "async_save", side_effect=OSError),
    ):
        result = await flow.async_step_init({"action": "keep"})
    assert result["errors"] == {"base": "save_failed"}
    assert issue(hass, target) is not None
    assert target.dismissed == {}
    assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}


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
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    record = decisions["history"][0]
    assert record["decision"] == "accepted" and record["source"] == "configure"
    assert record["rule"] == "lumbar_star254202_box25"
    assert record["previous_profile"][CONF_BED_TYPE] == BED_TYPE_ADJUSTABLE_LUMBAR
    assert record["selected_profile"][CONF_BED_TYPE] == BED_TYPE_SLEEPYS_BOX25
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
    assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}
    assert issue(hass, target) is not None


async def test_accepted_unique_match_is_recorded_even_when_selected_profile_has_no_assessment(
    hass, enable_custom_integrations
):
    from custom_components.adjustable_bed.const import LINAK_CONTROL_SERVICE_UUID

    config_entry = entry(hass, **{CONF_BED_TYPE: "richmat", CONF_MOTOR_COUNT: 2})
    coord = coordinator()
    coord.controller.protocol_diagnostics = {}
    observed = advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID])
    with patch(HISTORY, return_value=observed), patch(REGISTER):
        await async_watch_profile_recommendations(hass, config_entry, ((None, coord),))
        target = _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_standalone"]
        original = target.recommendation
        assert original is not None
        flow = await open_flow(hass, target)
        result = await flow.async_step_init({"action": "review"})
        with patch.object(hass.config_entries, "async_schedule_reload"):
            result = await hass.config_entries.options.async_configure(result["next_flow"][1], {})
        target.refresh()
    assert result["type"] == "create_entry"
    assert config_entry.data[CONF_BED_TYPE] == "linak"
    assert target.recommendation is None
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert decisions[original.rule] is True
    record = decisions["history"][0]
    assert record["decision"] == "accepted" and record["suggested"] == "linak"
    assert record["previous_profile"][CONF_BED_TYPE] == "richmat"
    assert record["selected_profile"][CONF_BED_TYPE] == "linak"


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
    assert decisions["lumbar_star254202_box25"] is True
    assert decisions["history"][0]["previous_profile"][CONF_BED_TYPE] == BED_TYPE_ADJUSTABLE_LUMBAR
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


def advertisement(name, services):
    observed = info(name)
    observed.service_uuids = services
    return observed


@pytest.mark.parametrize(
    "selected", ["adjustable_lumbar", "keeson", "richmat", "vibradorm_app", "sleepys_box25"]
)
def test_dedicated_identity_assesses_unrelated_configured_profiles(selected):
    from custom_components.adjustable_bed.const import LINAK_CONTROL_SERVICE_UUID

    result = recommend_profile(
        {CONF_BED_TYPE: selected}, advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID]), {}
    )
    assert result is not None
    assert result.translation_key == "profile_mismatch"
    assert result.suggested == "linak"


def test_already_matching_dedicated_profile_is_quiet():
    from custom_components.adjustable_bed.const import LINAK_CONTROL_SERVICE_UUID

    assert (
        recommend_profile(
            {CONF_BED_TYPE: "linak"}, advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID]), {}
        )
        is None
    )


def test_shared_named_identity_offers_app_review_without_a_winner():
    result = recommend_profile({CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25}, info(), {})
    assert result is not None
    assert result.translation_key == "profile_ambiguous"
    assert result.suggested is None
    assert "starcode_abm5_4" in result.choices
    assert BED_TYPE_ADJUSTABLE_LUMBAR in result.choices


@pytest.mark.parametrize("selected", [BED_TYPE_ADJUSTABLE_LUMBAR, "starcode_abm5_4"])
def test_explicit_matching_app_is_not_overridden_by_generic_detection(selected):
    assert recommend_profile({CONF_BED_TYPE: selected}, info(), {}) is None


def test_explicit_app_variant_resolves_its_generic_route():
    from custom_components.adjustable_bed.const import REMACRO_SERVICE_UUID

    assert (
        recommend_profile(
            {CONF_BED_TYPE: "remacro", CONF_PROTOCOL_VARIANT: "the_brick"},
            advertisement("Remacro", [REMACRO_SERVICE_UUID]),
            {},
        )
        is None
    )


@pytest.mark.parametrize("services", [[], [NORDIC_UART_SERVICE_UUID]])
def test_unknown_name_and_shared_transport_do_not_question_a_profile(services):
    assert (
        recommend_profile({CONF_BED_TYPE: "linak"}, advertisement("Unknown", services), {}) is None
    )


@pytest.mark.parametrize("gateway", [False, True])
def test_bare_dewertokin_services_do_not_offer_ambiguous_profiles(gateway):
    from custom_components.adjustable_bed.const import (
        DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
        DEWERTOKIN_SERVICE_UUID,
    )

    service = DEWERTOKIN_RF_GATEWAY_SERVICE_UUID if gateway else DEWERTOKIN_SERVICE_UUID
    assert (
        recommend_profile({CONF_BED_TYPE: "dewertokin"}, advertisement("", [service]), {}) is None
    )


@pytest.mark.parametrize("variant", [None, "auto", "json"])
def test_matching_keeson_json_does_not_offer_other_transport_apps(variant):
    from custom_components.adjustable_bed.const import KEESON_JSON_SERVICE_UUID

    assert (
        recommend_profile(
            {CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: variant},
            advertisement("", [KEESON_JSON_SERVICE_UUID]),
            {},
        )
        is None
    )


def test_keeson_json_mismatch_offers_only_its_detected_route():
    from custom_components.adjustable_bed.const import KEESON_JSON_SERVICE_UUID

    result = recommend_profile(
        {CONF_BED_TYPE: "linak"}, advertisement("", [KEESON_JSON_SERVICE_UUID]), {}
    )
    assert result is not None
    assert result.suggested == BED_TYPE_KEESON
    assert result.choices == (BED_TYPE_KEESON,)


def test_legacy_alias_does_not_offer_the_same_controller_as_an_improvement():
    from custom_components.adjustable_bed.const import OKIMAT_SERVICE_UUID

    assert (
        recommend_profile(
            {CONF_BED_TYPE: "okin_7byte"}, advertisement("Nectar bed", [OKIMAT_SERVICE_UUID]), {}
        )
        is None
    )


def test_generic_decision_survives_name_changes_but_not_changed_profile():
    from custom_components.adjustable_bed.const import LINAK_CONTROL_SERVICE_UUID

    original = recommend_profile(
        {CONF_BED_TYPE: "richmat"}, advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID]), {}
    )
    renamed = recommend_profile(
        {CONF_BED_TYPE: "richmat"}, advertisement("Bed 4321", [LINAK_CONTROL_SERVICE_UUID]), {}
    )
    changed = recommend_profile(
        {CONF_BED_TYPE: "keeson"}, advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID]), {}
    )
    assert original is not None and renamed is not None and changed is not None
    assert original.rule == renamed.rule
    assert original.rule != changed.rule


async def test_non_lumbar_observer_and_ambiguous_handoff_do_not_save_or_preselect(
    hass, enable_custom_integrations
):
    config_entry = entry(hass, **{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25})
    coord = coordinator()
    coord.bed_type = BED_TYPE_SLEEPYS_BOX25
    coord.controller.protocol_diagnostics = {}
    target = await watch(hass, config_entry, coord)
    assert issue(hass, target).translation_key == "profile_ambiguous"
    before = dict(config_entry.data)
    flow = await open_flow(hass, target)
    manager = hass.config_entries.options
    with (
        patch(HISTORY, return_value=info()),
        patch.object(manager, "async_configure", wraps=manager.async_configure) as configure,
    ):
        result = await flow.async_step_init({"action": "review"})
    configure.assert_called_once_with(result["next_flow"][1], {"next_step_id": "settings"})
    assert config_entry.data == before
    manager.async_abort(result["next_flow"][1])


@pytest.mark.parametrize(
    "selected,variant,name", [("octo", "standard", "DA1458x"), ("richmat", "auto", "QRRM106475")]
)
async def test_variant_and_remote_reviews_open_valid_settings_without_submitting_candidate_values(
    hass, enable_custom_integrations, selected, variant, name
):
    from custom_components.adjustable_bed.const import OCTO_STAR2_SERVICE_UUID

    config_entry = entry(hass, **{CONF_BED_TYPE: selected, CONF_PROTOCOL_VARIANT: variant})
    coord = coordinator()
    coord.bed_type = selected
    coord.controller.protocol_diagnostics = {}
    observed = advertisement(name, [OCTO_STAR2_SERVICE_UUID] if selected == "octo" else [])
    with patch(HISTORY, return_value=observed), patch(REGISTER):
        await async_watch_profile_recommendations(hass, config_entry, ((None, coord),))
        target = _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_standalone"]
        assert target.recommendation is not None
        assert any(":" in choice for choice in target.recommendation.choices)
        flow = await open_flow(hass, target)
        before = dict(config_entry.data)
        manager = hass.config_entries.options
        with patch.object(manager, "async_configure", wraps=manager.async_configure) as configure:
            result = await flow.async_step_init({"action": "review"})
        configure.assert_called_once_with(result["next_flow"][1], {"next_step_id": "settings"})
        assert config_entry.data == before
        manager.async_abort(result["next_flow"][1])


async def test_explicit_remote_change_reassesses_unchanged_qrrm_advertisement(hass):
    config_entry = entry(hass, **{CONF_BED_TYPE: "richmat", "richmat_remote": "auto"})
    coord = coordinator()
    coord.controller.protocol_diagnostics = {}
    observed = advertisement("QRRM106475", [])
    with patch(HISTORY, return_value=observed), patch(REGISTER):
        await async_watch_profile_recommendations(hass, config_entry, ((None, coord),))
        target = _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_standalone"]
        assert "richmat_remote:LP-QRRM" in target.recommendation.choices
        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data, "richmat_remote": "LP-QRRM"}
        )
        target.refresh(observed)
    assert not any(choice.startswith("richmat_remote:") for choice in target.recommendation.choices)


async def test_new_notice_suppresses_duplicate_upgrade_review_even_after_keep(hass):
    from custom_components.adjustable_bed.profile_review import (
        CONF_PROFILE_REVIEW_PENDING,
        async_refresh_profile_review_issue,
        profile_review_mark,
    )

    config_entry = entry(hass, **{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25})
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_PROFILE_REVIEW_PENDING: profile_review_mark(config_entry.data),
        },
    )
    coord = coordinator()
    coord.bed_type = BED_TYPE_SLEEPYS_BOX25
    coord.controller.protocol_diagnostics = {}
    target = await watch(hass, config_entry, coord)
    with patch(HISTORY, return_value=info()):
        await target.async_keep(target.recommendation)
        async_refresh_profile_review_issue(hass, config_entry)
    assert issue(hass, target) is None
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"app_profile_review_{config_entry.entry_id}")
        is None
    )
    await config_entry._async_process_on_unload(hass)
    hass.data[DOMAIN]["app_state_stores"].clear()
    with patch(HISTORY, return_value=None), patch(REGISTER):
        async_refresh_profile_review_issue(hass, config_entry)
        await async_watch_profile_recommendations(hass, config_entry, ((None, coord),))
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"app_profile_review_{config_entry.entry_id}")
        is None
    )


async def test_pending_upgrade_review_returns_when_replacement_evidence_changes(hass):
    from custom_components.adjustable_bed.profile_review import (
        CONF_PROFILE_REVIEW_PENDING,
        profile_review_mark,
    )

    config_entry = entry(hass, **{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25})
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_PROFILE_REVIEW_PENDING: profile_review_mark(config_entry.data),
        },
    )
    target = await watch(hass, config_entry)
    old_id = f"app_profile_review_{config_entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, old_id) is None
    changed = advertisement("unknown", [])
    with patch(HISTORY, return_value=changed):
        target.seen(changed, MagicMock())
    assert target.recommendation is None and issue(hass, target) is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, old_id) is not None


@pytest.mark.parametrize("observed", [None, "unknown"])
async def test_pending_upgrade_review_survives_without_a_replacement(hass, observed):
    from custom_components.adjustable_bed.profile_review import (
        CONF_PROFILE_REVIEW_PENDING,
        async_refresh_profile_review_issue,
        profile_review_mark,
    )

    config_entry = entry(hass, **{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25})
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_PROFILE_REVIEW_PENDING: profile_review_mark(config_entry.data),
        },
    )
    coord = coordinator()
    coord.bed_type = BED_TYPE_SLEEPYS_BOX25
    coord.controller.protocol_diagnostics = {}
    with patch(HISTORY, return_value=info(observed) if observed else None), patch(REGISTER):
        async_refresh_profile_review_issue(hass, config_entry)
        await async_watch_profile_recommendations(hass, config_entry, ((None, coord),))
        async_refresh_profile_review_issue(hass, config_entry)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"app_profile_review_{config_entry.entry_id}")
        is not None
    )
    assert all(watch.recommendation is None for watch in _watches(hass).values())


async def test_pair_upgrade_review_remains_for_an_unassessed_physical_side(hass):
    from custom_components.adjustable_bed.profile_review import (
        CONF_PROFILE_REVIEW_PENDING,
        async_refresh_profile_review_issue,
        profile_review_mark,
    )

    config_entry = entry(
        hass,
        **{
            CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
            CONF_PAIR_ID: "review_pair",
            CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
            CONF_PAIR_CHILDREN: [
                {CONF_SIDE: side, CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25}
                for side, address in (("left", ADDRESS), ("right", OTHER))
            ],
        },
    )
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            **config_entry.data,
            CONF_PROFILE_REVIEW_PENDING: profile_review_mark(config_entry.data),
        },
    )
    left, right = coordinator(), coordinator(OTHER)
    for coord in (left, right):
        coord.bed_type = BED_TYPE_SLEEPYS_BOX25
        coord.controller.protocol_diagnostics = {}
    with (
        patch(
            HISTORY,
            side_effect=lambda _hass, address, connectable: info() if address == ADDRESS else None,
        ),
        patch(REGISTER),
    ):
        async_refresh_profile_review_issue(hass, config_entry)
        await async_watch_profile_recommendations(
            hass, config_entry, (("left", left), ("right", right))
        )
        async_refresh_profile_review_issue(hass, config_entry)
    old_id = f"app_profile_review_{config_entry.entry_id}"
    assert ir.async_get(hass).async_get_issue(DOMAIN, old_id) is not None
    right_watch = _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_right"]
    right_watch.seen(info(address=OTHER), MagicMock())
    assert ir.async_get(hass).async_get_issue(DOMAIN, old_id) is None


async def test_partial_advertisement_cannot_break_setup(hass):
    config_entry = entry(hass)
    observed = info()
    observed.service_uuids = None
    observed.manufacturer_data = None
    observed.service_data = None
    with patch(HISTORY, return_value=observed), patch(REGISTER):
        await async_watch_profile_recommendations(hass, config_entry, ((None, coordinator()),))
    target = _watches(hass)[f"{ISSUE_PREFIX}{config_entry.entry_id}_standalone"]
    assert issue(hass, target) is None


async def test_expired_history_still_allows_review_and_keep(hass):
    target = await watch(hass)
    with patch(HISTORY, return_value=None):
        flow = await open_flow(hass, target)
        form = await flow.async_step_init()
        assert form["type"] == "form"
        result = await flow.async_step_init({"action": "keep"})
    assert result["type"] == "create_entry"
    assert issue(hass, target) is None


async def test_same_mac_with_different_case_keeps_the_recommendation(hass):
    target = await watch(hass)
    hass.config_entries.async_update_entry(
        target.entry, data={**target.entry.data, CONF_ADDRESS: ADDRESS.lower()}
    )
    target.seen(info(address=ADDRESS.lower()), MagicMock())
    assert issue(hass, target) is not None


@pytest.mark.parametrize("selected", [BED_TYPE_SLEEPYS_BOX25, BED_TYPE_ADJUSTABLE_LUMBAR])
async def test_single_address_pair_has_one_physical_notice(
    hass, enable_custom_integrations, selected
):
    import json
    from pathlib import Path

    from custom_components.adjustable_bed.const import PAIR_MODE_SINGLE_ADDRESS

    config_entry = entry(
        hass,
        **{
            CONF_BED_TYPE: selected,
            CONF_PAIR_ID: "single",
            CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS,
        },
    )
    coord = coordinator()
    coord.bed_type = selected
    coord.controller.protocol_diagnostics = STATE if selected == BED_TYPE_ADJUSTABLE_LUMBAR else {}
    target = await watch(hass, config_entry, coord)
    assert len(_watches(hass)) == 1
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        form = await flow.async_step_init()
        result = await flow.async_step_paired({"action": "review"})
    assert form["step_id"] == "paired"
    placeholders = form["description_placeholders"]
    assert placeholders is not None
    assert placeholders["pair_action"] == "Restore standalone controls"
    assert placeholders["target"] == "Bedroom"
    assert target.recommendation is not None
    for path in ("strings.json", "translations/en.json"):
        strings = json.loads((Path("custom_components/adjustable_bed") / path).read_text())
        step = strings["issues"][target.recommendation.translation_key]["fix_flow"]["step"]["paired"]
        assert step["title"].format(**placeholders) == "Review the profile for Bedroom"
        description = step["description"].format(**placeholders)
        assert "Restore standalone controls" in description
        assert "Split into two beds" not in description
        assert ",  side" not in description
    hass.config_entries.options.async_abort(result["next_flow"][1])


async def test_saving_ambiguous_review_confirms_current_route(hass, enable_custom_integrations):
    config_entry = entry(hass, **{CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25})
    # Populate the normal options defaults before testing a truly unchanged save.
    initial = await hass.config_entries.options.async_init(config_entry.entry_id)
    await hass.config_entries.options.async_configure(
        initial["flow_id"], {"next_step_id": "settings"}
    )
    await hass.config_entries.options.async_configure(initial["flow_id"], {})
    coord = coordinator()
    coord.bed_type = BED_TYPE_SLEEPYS_BOX25
    coord.controller.protocol_diagnostics = {}
    target = await watch(hass, config_entry, coord)
    config_entry.mock_state(hass, ConfigEntryState.LOADED)
    before = dict(config_entry.data)
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        result = await flow.async_step_init({"action": "review"})
        with patch.object(hass.config_entries, "async_schedule_reload"):
            result = await hass.config_entries.options.async_configure(result["next_flow"][1], {})
    config_entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    assert result["type"] == "create_entry"
    assert config_entry.data == before
    assert config_entry.data[CONF_BED_TYPE] == BED_TYPE_SLEEPYS_BOX25
    assert issue(hass, target) is None
    decisions = await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations")
    assert decisions["history"][0]["decision"] == "dismissed"
    assert decisions["history"][0]["source"] == "configure"


async def test_failed_history_write_does_not_abort_committed_settings(
    hass, enable_custom_integrations
):
    from custom_components.adjustable_bed.app_state_store import app_state_store
    from custom_components.adjustable_bed.profile_decisions import async_profile_decision_history

    target = await watch(hass)
    flow = await open_flow(hass, target)
    with patch(HISTORY, return_value=info()):
        result = await flow.async_step_init({"action": "review"})
        flow_id = result["next_flow"][1]
        with (
            patch.object(Store, "async_save", side_effect=OSError),
            patch(
                "custom_components.adjustable_bed.config_flow.async_set_discovery_disabled"
            ) as change_discovery,
        ):
            result = await hass.config_entries.options.async_configure(
                flow_id, {"disable_discovery": True}
            )
        change_discovery.assert_awaited_once_with(hass, True)
    assert result["type"] == "create_entry"
    assert target.entry.data[CONF_BED_TYPE] == BED_TYPE_SLEEPYS_BOX25
    assert issue(hass, target) is None
    # Immediate exports include the completed choice, and the retry makes it durable.
    history = (await async_profile_decision_history(hass, ADDRESS))["history"]
    assert len(history) == 1 and history[0]["decision"] == "accepted"
    await app_state_store(hass, ADDRESS).async_save()
    assert (await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations"))[
        "history"
    ] == history


async def test_failed_hardware_commit_leaves_review_and_history_unconfirmed(
    hass, enable_custom_integrations
):
    from custom_components.adjustable_bed.const import CONF_HAS_LIGHT, LINAK_CONTROL_SERVICE_UUID
    from tests.test_coordinator_limoss_remote import actual_coordinator

    coord = actual_coordinator(hass, **{CONF_ADDRESS: ADDRESS, CONF_HAS_LIGHT: True})
    coord.entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    observed = advertisement("Bed 1234", [LINAK_CONTROL_SERVICE_UUID])
    with patch(HISTORY, return_value=observed), patch(REGISTER):
        await async_watch_profile_recommendations(hass, coord.entry, ((None, coord),))
        target = _watches(hass)[f"{ISSUE_PREFIX}{coord.entry.entry_id}_standalone"]
        flow = await open_flow(hass, target)
        result = await flow.async_step_init({"action": "review"})
        before = dict(coord.entry.data)
        with patch.object(
            coord, "async_execute_controller_command", new=AsyncMock(side_effect=ConnectionError)
        ):
            result = await hass.config_entries.options.async_configure(result["next_flow"][1], {})
        assert result["errors"] == {"base": "limoss_remote_feature_update_failed"}
        assert coord.entry.data == before
        assert target.dismissed == {}
        assert await AppStateStore(hass, ADDRESS).async_slot("profile_recommendations") == {}
        target.refresh()
        assert issue(hass, target) is not None
        hass.config_entries.options.async_abort(result["flow_id"])
