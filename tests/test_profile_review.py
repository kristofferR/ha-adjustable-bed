"""Entries from before the app profiles are asked, once, whether one fits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import async_migrate_entry
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_COOLBASE,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_KEESON,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_OCTO,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_REVIVE,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROFILE_REVIEW_PENDING,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    KEESON_BASE_SERVICE_UUID,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_KSBT,
    NORDIC_UART_SERVICE_UUID,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_MODE_SINGLE_ADDRESS,
    SIDE_LEFT,
    SIDE_RIGHT,
    SOLACE_SERVICE_UUID,
)
from custom_components.adjustable_bed.detection import get_bed_type_options, resolve_bed_type_choice
from custom_components.adjustable_bed.pairing import supports_single_address_pairing
from custom_components.adjustable_bed.profile_review import (
    _ROUTE_APPS,
    ProfileReviewRepairFlow,
    async_refresh_profile_review_issue,
    choice_label,
    profile_review_mark,
)
from custom_components.adjustable_bed.repairs import async_create_fix_flow

ADDRESS = "AA:BB:CC:DD:EE:30"
_HISTORY = "custom_components.adjustable_bed.profile_review.bluetooth.async_last_service_info"


def _entry(hass: HomeAssistant, bed_type: str, *, variant: str | None = "auto", **data: Any) -> MockConfigEntry:
    entry_data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bedroom",
        CONF_BED_TYPE: bed_type,
        CONF_MOTOR_COUNT: 2,
        **data,
    }
    if variant is not None:
        entry_data[CONF_PROTOCOL_VARIANT] = variant
    entry_data[CONF_PROFILE_REVIEW_PENDING] = profile_review_mark(entry_data)
    entry = MockConfigEntry(
        domain=DOMAIN, title="Bedroom", unique_id=ADDRESS, data=entry_data, version=4, minor_version=3
    )
    entry.add_to_hass(hass)
    return entry


def _advertisement(name: str, *service_uuids: str) -> MagicMock:
    info = MagicMock()
    info.name = name
    info.address = ADDRESS
    info.manufacturer_data = {}
    info.service_data = {}
    info.service_uuids = list(service_uuids)
    return info


def _issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"app_profile_review_{entry.entry_id}")


async def _open(hass: HomeAssistant, entry: MockConfigEntry) -> tuple[ProfileReviewRepairFlow, Any]:
    issue = _issue(hass, entry)
    assert issue is not None
    flow = await async_create_fix_flow(hass, issue.issue_id, issue.data)
    assert isinstance(flow, ProfileReviewRepairFlow)
    flow.hass = hass
    # Home Assistant opens the flow with the issue ID, not a submitted form.
    return flow, await flow.async_step_init({"issue_id": issue.issue_id})


def _offered(form: dict[str, Any]) -> list[str]:
    return [option["value"] for option in form["data_schema"].schema["choice"].config["options"]]


@pytest.mark.parametrize(
    ("bed_type", "variant", "mark"),
    [
        (BED_TYPE_KEESON, "auto", "keeson:auto"),
        (BED_TYPE_RICHMAT, "auto", "richmat:auto"),
        (BED_TYPE_SOLACE, None, "solace:auto"),  # Motion Bed names need the advertisement
        (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA, None),  # already an app profile
        (BED_TYPE_LINAK, None, None),
    ],
)
async def test_migration_marks_only_routes_that_gained_app_profiles(
    hass: HomeAssistant, bed_type: str, variant: str | None, mark: str | None
) -> None:
    data = {CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: bed_type}
    if variant is not None:
        data[CONF_PROTOCOL_VARIANT] = variant
    entry = MockConfigEntry(domain=DOMAIN, data=data, version=4, minor_version=2)
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.minor_version == 3
    assert entry.data.get(CONF_PROFILE_REVIEW_PENDING) == mark


async def test_entries_created_now_are_never_marked(hass: HomeAssistant) -> None:
    """New entries start at minor version 3, so the migration never marks them."""
    assert AdjustableBedConfigFlow.MINOR_VERSION == 3
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: BED_TYPE_KEESON, CONF_PROTOCOL_VARIANT: "auto"},
        version=4,
        minor_version=3,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True
    async_refresh_profile_review_issue(hass, entry)

    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


async def test_offline_entry_gets_the_review_before_connecting(hass: HomeAssistant) -> None:
    entry = _entry(hass, BED_TYPE_LIMOSS, variant=None)
    from custom_components.adjustable_bed import async_setup_entry

    with (
        patch("custom_components.adjustable_bed.async_register_services", AsyncMock()),
        patch(
            "custom_components.adjustable_bed.AdjustableBedCoordinator",
            side_effect=RuntimeError("offline"),
        ),
        pytest.raises(RuntimeError, match="offline"),
    ):
        await async_setup_entry(hass, entry)

    issue = _issue(hass, entry)
    assert issue is not None and issue.is_fixable
    assert issue.translation_key == "app_profile_review"
    assert issue.translation_placeholders["apps"] == (
        "- FSM Relax app (explicit chair/bed profile)\n- Limoss Remote app (bed / chair)"
    )


async def test_keep_dismisses_the_review_for_good(hass: HomeAssistant) -> None:
    entry = _entry(hass, BED_TYPE_KEESON, variant=KEESON_VARIANT_KSBT)
    async_refresh_profile_review_issue(hass, entry)
    flow, form = await _open(hass, entry)
    assert _offered(form) == ["keeson:adjustable_lite", "keep"]
    before = {key: value for key, value in entry.data.items() if key != CONF_PROFILE_REVIEW_PENDING}

    result = await flow.async_step_init({"choice": "keep"})

    assert result["type"] == "create_entry"
    assert dict(entry.data) == before
    async_refresh_profile_review_issue(hass, entry)
    assert _issue(hass, entry) is None


async def test_switch_applies_the_app_through_the_options_flow(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    entry = _entry(hass, BED_TYPE_KEESON)
    entry_id = entry.entry_id
    entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    async_refresh_profile_review_issue(hass, entry)
    flow, form = await _open(hass, entry)
    choice = f"{BED_TYPE_KEESON}:{KEESON_VARIANT_INNOVA}"
    assert choice in _offered(form)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await flow.async_step_init({"choice": choice})

    assert result["type"] == "create_entry"
    reload.assert_called_once_with(entry_id)
    assert entry.entry_id == entry_id
    assert (entry.data[CONF_BED_TYPE], entry.data[CONF_PROTOCOL_VARIANT]) == (
        BED_TYPE_KEESON,
        KEESON_VARIANT_INNOVA,
    )
    assert _issue(hass, entry) is None
    # The reload's setup finds nothing left to review and retires the mark.
    async_refresh_profile_review_issue(hass, entry)
    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


@pytest.mark.parametrize(
    ("bed_type", "choice"),
    [
        # The app has settings only Configure collects.
        (BED_TYPE_LIMOSS, BED_TYPE_LIMOSS_REMOTE),
        # The options flow refuses: no stored raw name resolves the model.
        (BED_TYPE_RICHMAT, BED_TYPE_RICHMAT_REVIVE),
    ],
)
async def test_app_that_cannot_be_applied_here_points_to_configure(
    hass: HomeAssistant, enable_custom_integrations: None, bed_type: str, choice: str
) -> None:
    entry = _entry(hass, bed_type)
    before = dict(entry.data)
    async_refresh_profile_review_issue(hass, entry)
    flow, _form = await _open(hass, entry)

    result = await flow.async_step_init({"choice": choice})

    assert result["step_id"] == "configure"
    assert result["description_placeholders"]["app"] == choice_label(choice)
    assert dict(entry.data) == before
    assert not hass.config_entries.options.async_progress()
    await flow.async_step_configure({})
    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


async def test_detection_drift_names_the_matching_profile(hass: HomeAssistant) -> None:
    """v4.0.2 matched Cool Base only as a name prefix, so this bed stayed Keeson."""
    entry = _entry(hass, BED_TYPE_KEESON, variant=KEESON_VARIANT_KSBT)
    with patch(_HISTORY, return_value=_advertisement("Bed base-i5", KEESON_BASE_SERVICE_UUID)):
        async_refresh_profile_review_issue(hass, entry)
        flow, form = await _open(hass, entry)

    issue = _issue(hass, entry)
    assert issue is not None and issue.translation_key == "app_profile_review"
    assert _offered(form) == [BED_TYPE_COOLBASE, "keeson:adjustable_lite", "keep"]

    entry = _entry(hass, BED_TYPE_KEESON, variant="purple", **{CONF_ADDRESS: "AA:BB:CC:DD:EE:33"})
    with patch(_HISTORY, return_value=_advertisement("Bed base-i5", KEESON_BASE_SERVICE_UUID)):
        async_refresh_profile_review_issue(hass, entry)
    issue = _issue(hass, entry)
    assert issue is not None and issue.translation_key == "app_profile_match"
    assert issue.translation_placeholders["app"] == "Cool Base (BaseI5 with fan)"


async def test_switching_to_a_route_with_its_own_apps_does_not_ask_again(
    hass: HomeAssistant, enable_custom_integrations: None
) -> None:
    """Cool Base lists Restonic apps, but the user already answered the review."""
    entry = _entry(hass, BED_TYPE_KEESON, variant="purple")
    with patch(_HISTORY, return_value=_advertisement("Bed base-i5", KEESON_BASE_SERVICE_UUID)):
        async_refresh_profile_review_issue(hass, entry)
        flow, _form = await _open(hass, entry)
        result = await flow.async_step_init({"choice": BED_TYPE_COOLBASE})
        assert result["type"] == "create_entry"
        assert entry.data[CONF_BED_TYPE] == BED_TYPE_COOLBASE
        async_refresh_profile_review_issue(hass, entry)

    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


async def test_changing_the_bed_type_in_configure_answers_the_review(hass: HomeAssistant) -> None:
    entry = _entry(hass, BED_TYPE_RICHMAT)
    async_refresh_profile_review_issue(hass, entry)
    assert _issue(hass, entry) is not None

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_BED_TYPE: BED_TYPE_KEESON}
    )
    async_refresh_profile_review_issue(hass, entry)

    assert CONF_PROFILE_REVIEW_PENDING not in entry.data
    assert _issue(hass, entry) is None


async def test_advertised_app_candidates_join_the_review(hass: HomeAssistant) -> None:
    entry = _entry(hass, BED_TYPE_SLEEPYS_BOX25, variant=None)
    with patch(_HISTORY, return_value=_advertisement("STAR25A1", NORDIC_UART_SERVICE_UUID)):
        async_refresh_profile_review_issue(hass, entry)

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_placeholders["apps"] == (
        "- Adjustable bed (Lumbar) app\n"
        "- AdjustableM5X4 app (explicit profile)\n"
        "- AdjustableM5X5 app (CB25 / F23 / kneading)"
    )


async def test_review_waits_for_an_advertisement_that_could_add_an_app(hass: HomeAssistant) -> None:
    entry = _entry(hass, BED_TYPE_SOLACE, variant=None)
    with patch(_HISTORY, return_value=None):
        async_refresh_profile_review_issue(hass, entry)
    assert _issue(hass, entry) is None
    assert entry.data[CONF_PROFILE_REVIEW_PENDING] == "solace:auto"

    with patch(_HISTORY, return_value=_advertisement("QMS-IQ 1234", SOLACE_SERVICE_UUID)):
        async_refresh_profile_review_issue(hass, entry)
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.translation_placeholders["apps"] == "- Motion Bed app"

    other = _entry(hass, BED_TYPE_OCTO, variant=None, **{CONF_ADDRESS: "AA:BB:CC:DD:EE:31"})
    with patch(_HISTORY, return_value=_advertisement("RC2", "0000ffe0-0000-1000-8000-00805f9b34fb")):
        async_refresh_profile_review_issue(hass, other)
    # Nothing to offer once the advertisement is known: the mark is retired.
    assert _issue(hass, other) is None
    assert CONF_PROFILE_REVIEW_PENDING not in other.data


def _paired(hass: HomeAssistant, mode: str) -> MockConfigEntry:
    second = ADDRESS if mode == PAIR_MODE_SINGLE_ADDRESS else "AA:BB:CC:DD:EE:32"
    data: dict[str, Any] = {
        CONF_PAIR_ID: "pair_review",
        CONF_PAIR_MODE: mode,
        CONF_BED_TYPE: BED_TYPE_KEESON,
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: side, CONF_ADDRESS: address, CONF_BED_TYPE: BED_TYPE_KEESON,
             CONF_PROTOCOL_VARIANT: KEESON_VARIANT_KSBT, CONF_MOTOR_COUNT: 2}
            for side, address in ((SIDE_LEFT, ADDRESS), (SIDE_RIGHT, second))
        ],
    }
    data[CONF_PROFILE_REVIEW_PENDING] = profile_review_mark(data)
    assert data[CONF_PROFILE_REVIEW_PENDING] == "keeson:ksbt|keeson:ksbt"
    entry = MockConfigEntry(domain=DOMAIN, title="Pair", data=data, version=4, minor_version=3)
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("mode", [PAIR_MODE_SEPARATE_ADDRESS, PAIR_MODE_SINGLE_ADDRESS])
async def test_paired_bed_explains_splitting_instead_of_switching(
    hass: HomeAssistant, mode: str
) -> None:
    entry = _paired(hass, mode)
    async_refresh_profile_review_issue(hass, entry)
    before = {key: value for key, value in entry.data.items() if key != CONF_PROFILE_REVIEW_PENDING}
    flow, form = await _open(hass, entry)

    assert form["step_id"] == "unpair"
    assert form["data_schema"] is None
    assert form["description_placeholders"]["apps"] == "- Adjustable Lite app (Keeson)"
    result = await flow.async_step_unpair({})
    assert result["type"] == "create_entry"
    assert dict(entry.data) == before
    assert _issue(hass, entry) is None


def test_every_offered_app_is_a_selectable_profile() -> None:
    selectable = {option["value"] for option in get_bed_type_options()}
    offered = {choice for route in _ROUTE_APPS for choice in route.choices}
    from custom_components.adjustable_bed.const import (
        BED_TYPE_VIBRADORM,
        BED_TYPE_VIBRADORM_APP,
        BED_TYPE_VMATBASIC,
    )

    assert BED_TYPE_VIBRADORM in selectable
    assert offered - {BED_TYPE_VIBRADORM_APP, BED_TYPE_VMATBASIC} <= selectable
    # FurniMove's own repairs cover the routes its handsets used.
    assert not any(choice.startswith(BED_TYPE_FURNIMOVE) for choice in offered)
    # Why a paired bed is split first: no offered app keeps paired controls.
    assert not any(
        supports_single_address_pairing(*resolve_bed_type_choice(choice)) for choice in offered
    )


def test_review_text_is_translated_identically() -> None:
    root = Path("custom_components/adjustable_bed")
    strings, english = (
        json.loads((root / name).read_text()) for name in ("strings.json", "translations/en.json")
    )
    for key in ("app_profile_review", "app_profile_match"):
        issue = strings["issues"][key]
        assert issue == english["issues"][key]
        assert set(issue["fix_flow"]["step"]) == {"init", "configure", "unpair", "vibradorm"}
        assert "entry_missing" in issue["fix_flow"]["abort"]
        assert "—" not in json.dumps(issue, ensure_ascii=False)
    assert strings["selector"]["app_profile_review"] == {
        "options": {"keep": "Keep current configuration"}
    }
