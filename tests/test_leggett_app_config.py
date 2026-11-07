"""Explicit Leggett app profiles preserve legacy defaults and per-side choices."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_LINAK,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_LEGGETT_APP_PROFILE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    LEGGETT_APP_DEFAULT_PROFILE,
    LEGGETT_APP_MOTOR_COUNTS,
    LEGGETT_VARIANT_OKIN,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from custom_components.adjustable_bed.profile_migration import _async_preview_labels
from tests.form_helpers import finish_new_bed, start_new_bed


@pytest.mark.parametrize(
    "route,pairing",
    [
        ("typed", "manual_pairing"),
        ("picked", "manual_pairing"),
        ("discovered", "bluetooth_pairing"),
    ],
)
async def test_setup_collects_app_then_preserves_pairing(
    hass, mock_bluetooth_service_info, route, pairing
):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    settings = {CONF_NAME: "Prodigy", CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: True, CONF_DISCONNECT_AFTER_COMMAND: False, CONF_PREFERRED_ADAPTER: "auto"}
    result = await start_new_bed(flow, route, BED_TYPE_LEGGETT_OKIN)
    # The L&P question names each app, which picks its own layout.
    assert result["step_id"] == "leggett_family"
    with patch.object(flow, f"async_step_{pairing}", new=AsyncMock()) as resume:
        await finish_new_bed(flow, await flow.async_step_leggett_family({"choice": "prodigy2l"}), settings)
    resume.assert_awaited_once_with()
    assert flow._manual_data[CONF_LEGGETT_APP_PROFILE] == "prodigy2l"
    assert flow._manual_data[CONF_MOTOR_COUNT] == 3
    assert requires_pairing(BED_TYPE_LEGGETT_OKIN)


@pytest.mark.parametrize("profile", LEGGETT_APP_MOTOR_COUNTS)
async def test_options_send_a_profile_change_to_the_guided_change(hass, profile):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings(
        {CONF_LEGGETT_APP_PROFILE: profile, CONF_MOTOR_COUNT: 2}
    )
    if profile == LEGGETT_APP_DEFAULT_PROFILE:
        # An entry saved before app profiles already runs the default one.
        assert result["type"] == FlowResultType.CREATE_ENTRY
    else:
        assert result["errors"] == {"base": "migration_reconfigure_required"}
        assert CONF_LEGGETT_APP_PROFILE not in entry.data


async def test_legacy_options_without_profile_keep_existing_motor_count(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN, CONF_MOTOR_COUNT: 2}
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "12"})
    assert CONF_LEGGETT_APP_PROFILE not in entry.data
    assert entry.data[CONF_MOTOR_COUNT] == 2


@pytest.mark.parametrize(
    "bed_type,variant",
    [(BED_TYPE_LEGGETT_OKIN, None), (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN)],
)
async def test_factory_routes_profile_and_legacy_default(hass, bed_type, variant):
    for data, expected in [({}, "prodigy4"), ({CONF_LEGGETT_APP_PROFILE: "useries"}, "useries")]:
        coordinator = SimpleNamespace(hass=hass, entry=SimpleNamespace(data=data))
        with patch(
            "custom_components.adjustable_bed.beds.leggett.okin.LeggettOkinController"
        ) as controller:
            await create_controller(coordinator, bed_type, variant, None)
        controller.assert_called_once_with(coordinator, app_profile=expected)


async def test_pair_common_options_preserve_distinct_profiles(hass):
    left = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
        CONF_MOTOR_COUNT: 3,
        CONF_LEGGETT_APP_PROFILE: "prodigy2l",
    }
    right = {**left, CONF_ADDRESS: "11:22:33:44:55:77", CONF_LEGGETT_APP_PROFILE: "useries"}
    entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings()
    assert CONF_LEGGETT_APP_PROFILE not in {
        marker.schema for marker in result["data_schema"].schema
    }
    await flow.async_step_settings({CONF_MOTOR_PULSE_COUNT: "12"})
    assert [child[CONF_LEGGETT_APP_PROFILE] for child in entry.data[CONF_PAIR_CHILDREN]] == [
        "prodigy2l",
        "useries",
    ]
    assert CONF_LEGGETT_APP_PROFILE not in entry.data


async def test_pair_cannot_switch_to_leggett_app_without_unpairing(hass):
    left = {CONF_ADDRESS: "11:22:33:44:55:66", CONF_BED_TYPE: BED_TYPE_LINAK, CONF_MOTOR_COUNT: 2}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(left, {**left, CONF_ADDRESS: "11:22:33:44:55:77"}, name="Pair"),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN})
    assert result["errors"] == {CONF_BED_TYPE: "app_profile_unpair_first"}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_LINAK
    assert flow._pending_data == {}


async def test_legacy_umbrella_variant_change_uses_the_guided_change(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_LEGGETT_PLATT,
            CONF_PROTOCOL_VARIANT: "gen2",
            CONF_MOTOR_COUNT: 2,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: LEGGETT_VARIANT_OKIN})
    assert result["errors"] == {"base": "migration_reconfigure_required"}
    assert entry.data[CONF_PROTOCOL_VARIANT] == "gen2"


async def test_stored_explicit_profile_keeps_its_motor_count(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
            CONF_LEGGETT_APP_PROFILE: "prodigy2l",
            CONF_MOTOR_COUNT: 3,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    result = await flow.async_step_settings({CONF_MOTOR_COUNT: 2})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_MOTOR_COUNT] == 3


@pytest.mark.parametrize(
    ("bed_type", "variant"),
    [(BED_TYPE_LEGGETT_OKIN, None), (BED_TYPE_LEGGETT_PLATT, LEGGETT_VARIANT_OKIN)],
)
async def test_untouched_configure_form_keeps_a_legacy_entrys_controls(
    hass, enable_custom_integrations, bed_type, variant
):
    """#676: Configure shows an absent app profile as the default four-motor one.

    Saving the ordinary form unchanged must keep the controls the entry already
    runs: the factory runs that same default profile for an absent one.
    """
    data = {
        CONF_ADDRESS: "11:22:33:44:55:66",
        CONF_NAME: "Prodigy",
        CONF_BED_TYPE: bed_type,
        CONF_MOTOR_COUNT: 2,
    }
    if variant is not None:
        data[CONF_PROTOCOL_VARIANT] = variant
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    before = await _async_preview_labels(hass, entry, dict(entry.data))
    assert before

    menu = await hass.config_entries.options.async_init(entry.entry_id)
    form = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"}
    )
    shown = form["data_schema"]({})
    assert shown[CONF_LEGGETT_APP_PROFILE] == LEGGETT_APP_DEFAULT_PROFILE
    result = await hass.config_entries.options.async_configure(form["flow_id"], shown)

    assert result["type"] == FlowResultType.CREATE_ENTRY, result
    saved = {**entry.data, **entry.options}
    assert saved[CONF_BED_TYPE] == bed_type
    assert saved.get(CONF_PROTOCOL_VARIANT) == variant
    # The saved profile and its motor count are the ones the entry already ran.
    assert saved[CONF_LEGGETT_APP_PROFILE] == LEGGETT_APP_DEFAULT_PROFILE
    assert saved[CONF_MOTOR_COUNT] == LEGGETT_APP_MOTOR_COUNTS[LEGGETT_APP_DEFAULT_PROFILE]
    assert await _async_preview_labels(hass, entry, saved) == before
