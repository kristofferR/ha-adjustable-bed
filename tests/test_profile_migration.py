"""Shared guided-change transaction: snapshot, control changes and review handoff (#676)."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedOptionsFlow,
    _vibradorm_app_data,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profile_migration import (
    LEGGETT_FAMILY,
    OKIN_FAMILY,
    VIBRADORM_FAMILY,
    MigrationSnapshot,
    async_control_changes,
    managed_family,
    reconfigure_family,
)
from custom_components.adjustable_bed.profile_review import (
    carry_profile_review,
    profile_review_mark,
)
from tests.test_vibradorm_family_flow import bluetooth_patches, client_for, select_app

ADDRESS = "11:22:33:44:55:66"


def _entry(hass, data=None, options=None) -> MockConfigEntry:
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
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


def _caresse() -> dict:
    return _vibradorm_app_data(
        {
            CONF_ADDRESS: ADDRESS,
            const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
            const.CONF_VIBRADORM_APP_PROFILE: "caresse",
        },
        {},
    )


async def test_control_changes_compare_entity_sets_and_name_automations(
    hass, enable_custom_integrations
):
    entry = _entry(hass)
    registry = er.async_get(hass)
    memory = registry.async_get_or_create(
        "button", const.DOMAIN, f"{ADDRESS}_preset_memory_1", config_entry=entry
    )
    registry.async_get_or_create("cover", const.DOMAIN, f"{ADDRESS}_back", config_entry=entry)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "Bedtime routine",
                "triggers": {"trigger": "event", "event_type": "bedtime"},
                "actions": {"action": "button.press", "target": {"entity_id": memory.entity_id}},
            }
        },
    )
    await hass.async_block_till_done()

    changes = await async_control_changes(hass, entry, {**_caresse(), CONF_NAME: "Bedroom"})

    assert changes.known
    assert "Memory 1" in changes.removed and "Under Bed Lights" in changes.removed
    assert "Hold all controls down" in changes.added
    # Kept controls (address-based IDs) are neither added nor removed.
    assert "Back" not in changes.added + changes.removed
    assert changes.unchanged == 6
    assert changes.references == ("Bedtime routine",)
    # Listing controls never changes the registry or the saved entry.
    assert registry.async_get(memory.entity_id) is not None
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_VIBRADORM


async def test_control_changes_say_when_staged_controls_are_unknown(
    hass, enable_custom_integrations
):
    entry = _entry(hass)
    with patch.object(AdjustableBedCoordinator, "async_prime_offline_controller", AsyncMock()):
        changes = await async_control_changes(hass, entry, _caresse())
    assert not changes.known
    assert changes.added == changes.removed == ()


async def test_confirm_lists_changes_and_the_physical_validation_note(
    hass, enable_custom_integrations
):
    entry = _entry(hass)
    before = dict(entry.data)
    with ExitStack() as stack:
        bluetooth_patches(stack, client_for("caresse"))
        result = await select_app(hass, entry, "caresse")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "migration_confirm"
        placeholders = result["description_placeholders"]
        assert "**Removed:**" in placeholders["summary"]
        assert "- Memory 1" in placeholders["summary"]
        assert placeholders["current"].startswith("Vibradorm")
        assert placeholders["selection"].startswith("Caresse")
        assert entry.data == before
        hass.config_entries.flow.async_abort(result["flow_id"])
    assert entry.data == before


def test_snapshot_detects_a_label_change_that_resolves_to_the_saved_route():
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bedroom",
        data={CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM},
        options={const.CONF_IDLE_DISCONNECT_SECONDS: 60},
    )
    snapshot = MigrationSnapshot.of(entry)
    staged = snapshot.staged(entry.title)
    assert staged[CONF_NAME] == "Bedroom"
    assert snapshot.is_unchanged_by(staged)
    staged[const.CONF_BED_TYPE] = const.BED_TYPE_VMATBASIC
    assert not snapshot.is_unchanged_by(staged)
    assert snapshot.data[const.CONF_BED_TYPE] == const.BED_TYPE_VIBRADORM


def test_managed_family_covers_either_paired_side():
    data = {
        const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
        const.CONF_PAIR_ID: "pair",
        const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
        const.CONF_PAIR_CHILDREN: [
            {const.CONF_SIDE: const.SIDE_LEFT, CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: "keeson"},
            {
                const.CONF_SIDE: const.SIDE_RIGHT,
                CONF_ADDRESS: "11:22:33:44:55:77",
                const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM,
            },
        ],
    }
    assert managed_family(data) is VIBRADORM_FAMILY
    assert managed_family({const.CONF_BED_TYPE: const.BED_TYPE_LINAK}) is None


def test_a_route_another_familys_question_chooses_reconfigures_but_keeps_its_review():
    """Reconfigure asks the question; Repairs keeps the path the review's apps need."""
    for data, family in (
        ({const.CONF_BED_TYPE: const.BED_TYPE_OKIN_CST}, OKIN_FAMILY),
        ({const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_LP_LEGACY}, LEGGETT_FAMILY),
        (
            {
                const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
                const.CONF_RICHMAT_REMOTE: const.RICHMAT_REMOTE_LP_QRRM,
            },
            LEGGETT_FAMILY,
        ),
    ):
        assert reconfigure_family(data) is family
        assert managed_family(data) is None
    assert reconfigure_family({const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT}) is None


def test_split_carries_an_open_review_and_an_earlier_keep_to_each_bed():
    single = {CONF_ADDRESS: ADDRESS, const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT}
    pair = {
        **single,
        const.CONF_PAIR_ID: "pair",
        const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
        const.CONF_PAIR_CHILDREN: [
            {const.CONF_SIDE: const.SIDE_LEFT, **single},
            {
                const.CONF_SIDE: const.SIDE_RIGHT,
                CONF_ADDRESS: "11:22:33:44:55:77",
                const.CONF_BED_TYPE: const.BED_TYPE_RICHMAT,
            },
        ],
    }
    pair[const.CONF_PROFILE_REVIEW_PENDING] = profile_review_mark(pair)
    target = dict(single)
    carry_profile_review(pair, target)
    assert target[const.CONF_PROFILE_REVIEW_PENDING] == "richmat:auto"

    kept = {k: v for k, v in pair.items() if k != const.CONF_PROFILE_REVIEW_PENDING}
    kept[const.CONF_PROFILE_REVIEW_KEPT] = {
        "route": profile_review_mark(pair),
        "apps": ["richmat_revive"],
    }
    target = dict(single)
    carry_profile_review(kept, target)
    assert target == {
        **single,
        const.CONF_PROFILE_REVIEW_KEPT: {"route": "richmat:auto", "apps": ["richmat_revive"]},
    }


async def test_configure_offers_one_generic_change_item(hass):
    entry = _entry(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass
    menu = await flow.async_step_init()
    assert "change_app" in menu["menu_options"]
    assert "vibradorm_setup" not in menu["menu_options"]
    form = await flow.async_step_change_app()
    assert form["description_placeholders"]["current"].startswith("Vibradorm")
    result = await flow.async_step_change_app({})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "migration_reconfigure_required"

    other = MockConfigEntry(
        domain=const.DOMAIN,
        data={CONF_ADDRESS: "11:22:33:44:55:99", const.CONF_BED_TYPE: const.BED_TYPE_LINAK},
    )
    other.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(other)
    flow.handler, flow.hass = other.entry_id, hass
    assert "change_app" not in (await flow.async_step_init())["menu_options"]


async def test_preview_never_touches_the_live_app_session(hass, enable_custom_integrations):
    from custom_components.adjustable_bed.vibradorm_app_state import (
        get_vibradorm_app_session_intent,
    )

    werkmeister = _vibradorm_app_data(
        {
            CONF_ADDRESS: ADDRESS,
            const.CONF_BED_TYPE: const.BED_TYPE_VIBRADORM_APP,
            const.CONF_VIBRADORM_APP_PROFILE: "werkmeister",
        },
        {},
    )
    entry = _entry(hass, werkmeister)
    control = int(werkmeister[const.CONF_VIBRADORM_CONTROL_TYPE])
    intent = get_vibradorm_app_session_intent(
        hass, ADDRESS, app_profile="werkmeister", control_type=control, remembered_floor_default=6
    )
    intent.floor.level = 4

    changes = await async_control_changes(hass, entry, _caresse())

    assert changes.known
    same = get_vibradorm_app_session_intent(
        hass, ADDRESS, app_profile="werkmeister", control_type=control, remembered_floor_default=6
    )
    assert same is intent
    assert same.floor.level == 4


async def test_guided_change_saves_the_new_routes_profile_id(hass, enable_custom_integrations):
    from custom_components.adjustable_bed.profile_id import resolve_profile_id

    entry = _entry(hass)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, const.CONF_PROFILE_ID: resolve_profile_id(entry.data)}
    )
    assert entry.data[const.CONF_PROFILE_ID] == const.BED_TYPE_VIBRADORM
    with ExitStack() as stack:
        bluetooth_patches(stack, client_for("caresse"))
        result = await select_app(hass, entry, "caresse")
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"action": "apply"}
        )
    assert result["reason"] == "migration_applied"
    # Derived from the new route, never copied from the staged saved setup.
    assert entry.data[const.CONF_PROFILE_ID] == resolve_profile_id(entry.data)
    assert entry.data[const.CONF_PROFILE_ID] == f"{const.BED_TYPE_VIBRADORM_APP}@caresse"
