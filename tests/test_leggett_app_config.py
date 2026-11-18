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
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_HAS_MASSAGE,
    CONF_LEGGETT_APP_PROFILE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
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
    settings = {CONF_NAME: "Prodigy", CONF_MOTOR_COUNT: 2, CONF_HAS_MASSAGE: True, CONF_CONNECTION_MODE: "idle", CONF_PREFERRED_ADAPTER: "auto"}
    result = await start_new_bed(flow, route, BED_TYPE_LEGGETT_OKIN)
    # The L&P question names each app, which picks its own layout.
    assert result["step_id"] == "leggett_family"
    with patch.object(flow, f"async_step_{pairing}", new=AsyncMock()) as resume:
        await finish_new_bed(flow, await flow.async_step_leggett_family({"choice": "prodigy2l"}), settings)
    resume.assert_awaited_once_with()
    assert flow._manual_data[CONF_LEGGETT_APP_PROFILE] == "prodigy2l"
    assert flow._manual_data[CONF_MOTOR_COUNT] == 3
    assert requires_pairing(BED_TYPE_LEGGETT_OKIN)


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
    """#676: saving the ordinary form unchanged keeps the controls the entry runs."""
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
    # The app is chosen in Reconfigure's guided change, never Configure.
    assert CONF_LEGGETT_APP_PROFILE not in shown
    result = await hass.config_entries.options.async_configure(form["flow_id"], shown)

    assert result["type"] == FlowResultType.CREATE_ENTRY, result
    saved = {**entry.data, **entry.options}
    assert saved[CONF_BED_TYPE] == bed_type
    assert saved.get(CONF_PROTOCOL_VARIANT) == variant
    assert CONF_LEGGETT_APP_PROFILE not in saved
    assert await _async_preview_labels(hass, entry, saved) == before
