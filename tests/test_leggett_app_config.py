"""Explicit Leggett app profiles preserve legacy defaults and per-side choices."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    LEGGETT_APP_MOTOR_COUNTS,
    LEGGETT_VARIANT_OKIN,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.pairing import build_pair_entry_data


@pytest.mark.parametrize(
    "step,pairing",
    [
        ("manual_entry", "manual_pairing"),
        ("manual_config", "manual_pairing"),
        ("bluetooth_confirm", "bluetooth_pairing"),
    ],
)
async def test_setup_collects_app_then_preserves_pairing(
    hass, mock_bluetooth_service_info, step, pairing
):
    flow = AdjustableBedConfigFlow()
    flow.context = {}
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    flow._disconnect_choice_confirmed = True
    result = await getattr(flow, f"async_step_{step}")(
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
            CONF_NAME: "Prodigy",
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            CONF_PREFERRED_ADAPTER: "auto",
        }
    )
    assert result["step_id"] == "leggett_app"
    with patch.object(flow, f"async_step_{pairing}", new=AsyncMock()) as resume:
        await flow.async_step_leggett_app({CONF_LEGGETT_APP_PROFILE: "prodigy2l"})
    resume.assert_awaited_once_with()
    assert flow._manual_data[CONF_LEGGETT_APP_PROFILE] == "prodigy2l"
    assert flow._manual_data[CONF_MOTOR_COUNT] == 3
    assert requires_pairing(BED_TYPE_LEGGETT_OKIN)


@pytest.mark.parametrize("profile,count", LEGGETT_APP_MOTOR_COUNTS.items())
async def test_options_derive_motor_count_from_profile(hass, profile, count):
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
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LEGGETT_APP_PROFILE] == profile
    assert entry.data[CONF_MOTOR_COUNT] == count


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
async def test_factory_routes_profile_and_legacy_default(bed_type, variant):
    for data, expected in [({}, "prodigy4"), ({CONF_LEGGETT_APP_PROFILE: "useries"}, "useries")]:
        coordinator = SimpleNamespace(entry=SimpleNamespace(data=data))
        with patch(
            "custom_components.adjustable_bed.beds.leggett_okin.LeggettOkinController"
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
    assert result["errors"] == {CONF_BED_TYPE: "leggett_app_unpair_first"}
    assert entry.data[CONF_BED_TYPE] == BED_TYPE_LINAK
    assert flow._pending_data == {}


async def test_legacy_umbrella_variant_change_collects_profile(hass):
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
    assert result["type"] == FlowResultType.FORM
    assert CONF_LEGGETT_APP_PROFILE in {marker.schema for marker in result["data_schema"].schema}
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
