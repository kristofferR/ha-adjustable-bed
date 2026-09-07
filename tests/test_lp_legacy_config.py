"""Explicit legacy L&P app configuration never guesses model or transport."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
    _lp_legacy_schema,
    _validate_lp_legacy_settings,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_LP_LEGACY,
    BED_TYPE_RICHMAT,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_READ_UUID,
    CONF_LP_LEGACY_WRITE_UUID,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PAIR_CHILDREN,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.lp_legacy_profiles import LP_LEGACY_PROFILE_CODES
from custom_components.adjustable_bed.pairing import build_pair_entry_data

_WRITE_UUID = "11111111-2222-3333-4444-555555555555"
_READ_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _settings() -> dict[str, str]:
    return {
        CONF_LP_LEGACY_MODEL: LP_LEGACY_PROFILE_CODES[0],
        CONF_LP_LEGACY_MODE: "framed",
        CONF_LP_LEGACY_WRITE_UUID: _WRITE_UUID,
        CONF_LP_LEGACY_READ_UUID: _READ_UUID,
    }


def test_explicit_choices_have_no_guessed_defaults() -> None:
    """Required settings must be supplied even when a model seems familiar."""
    errors = _validate_lp_legacy_settings({})
    assert set(errors) == {
        CONF_LP_LEGACY_MODEL,
        CONF_LP_LEGACY_MODE,
        CONF_LP_LEGACY_WRITE_UUID,
    }
    assert _lp_legacy_schema({})
    options = {option["value"]: option["label"] for option in get_bed_type_options()}
    assert options[BED_TYPE_LEGGETT_LP_LEGACY] == "L&P Adjustable Base (legacy app)"
    assert BED_TYPE_RICHMAT in options


@pytest.mark.parametrize(
    ("key", "value", "error"),
    [
        (CONF_LP_LEGACY_MODEL, "ZZZZ", "invalid_lp_legacy_model"),
        (CONF_LP_LEGACY_MODE, "auto", "invalid_lp_legacy_mode"),
        (CONF_LP_LEGACY_WRITE_UUID, "ffe1", "invalid_characteristic_uuid"),
        (CONF_LP_LEGACY_READ_UUID, "not-a-uuid", "invalid_characteristic_uuid"),
    ],
)
def test_invalid_explicit_settings(key: str, value: str, error: str) -> None:
    data = {**_settings(), key: value}
    assert _validate_lp_legacy_settings(data) == {key: error}


async def test_manual_entry_collects_and_saves_legacy_settings(hass: HomeAssistant) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow._selected_bed_type = BED_TYPE_LEGGETT_LP_LEGACY
    result = await flow.async_step_manual_entry(
        {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Legacy app bed",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_LP_LEGACY,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        }
    )
    assert result["step_id"] == "lp_legacy"
    invalid = await flow.async_step_lp_legacy({})
    assert invalid["step_id"] == "lp_legacy"
    assert CONF_LP_LEGACY_MODEL in invalid["errors"]
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await flow.async_step_lp_legacy(_settings())
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BED_TYPE] == BED_TYPE_LEGGETT_LP_LEGACY
    assert {key: result["data"][key] for key in _settings()} == _settings()


async def test_options_preserve_profile_and_validate_endpoints(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_LP_LEGACY,
            **_settings(),
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings({CONF_LP_LEGACY_WRITE_UUID: "unknown"})
    assert result["errors"] == {CONF_LP_LEGACY_WRITE_UUID: "invalid_characteristic_uuid"}
    result = await flow.async_step_settings({CONF_LP_LEGACY_MODE: "legacy"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_LP_LEGACY_MODEL] == _settings()[CONF_LP_LEGACY_MODEL]
    assert entry.data[CONF_LP_LEGACY_MODE] == "legacy"
    assert entry.data[CONF_LP_LEGACY_WRITE_UUID] == _WRITE_UUID


async def test_factory_uses_explicit_config_without_inspecting_advertisements(
    hass: HomeAssistant,
) -> None:
    coordinator = SimpleNamespace(hass=hass, entry=SimpleNamespace(data=_settings()))
    with patch(
        "custom_components.adjustable_bed.beds.leggett_lp_legacy.LeggettLpLegacyController"
    ) as constructor:
        await create_controller(
            coordinator,
            BED_TYPE_LEGGETT_LP_LEGACY,
            "auto",
            None,
            device_name="unrelated advertisement",
            manufacturer_data={123: b"ignored"},
        )
    constructor.assert_called_once_with(
        coordinator,
        model=_settings()[CONF_LP_LEGACY_MODEL],
        mode="framed",
        write_uuid=_WRITE_UUID,
        read_uuid=_READ_UUID,
    )


async def test_factory_rejects_missing_profile(hass: HomeAssistant) -> None:
    coordinator = SimpleNamespace(hass=hass, entry=SimpleNamespace(data={}))
    with pytest.raises(ValueError):
        await create_controller(coordinator, BED_TYPE_LEGGETT_LP_LEGACY, "auto", None)


async def test_paired_options_preserve_each_sides_profile_and_endpoints(
    hass: HomeAssistant,
) -> None:
    left = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
        CONF_BED_TYPE: BED_TYPE_LEGGETT_LP_LEGACY,
        **_settings(),
    }
    right = {
        **left,
        CONF_ADDRESS: "AA:BB:CC:DD:EE:02",
        CONF_LP_LEGACY_MODEL: "A7RM",
        CONF_LP_LEGACY_MODE: "legacy",
        CONF_LP_LEGACY_WRITE_UUID: _READ_UUID,
        CONF_LP_LEGACY_READ_UUID: "",
    }
    entry = MockConfigEntry(
        domain=DOMAIN, data=build_pair_entry_data(left, right, name="Paired LP")
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_settings()
    shown = {marker.schema for marker in result["data_schema"].schema}
    assert shown.isdisjoint(_settings())
    result = await flow.async_step_settings(
        {CONF_MOTOR_PULSE_COUNT: "20", **right}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    for child, original in zip(entry.data[CONF_PAIR_CHILDREN], (left, right), strict=True):
        assert {key: child[key] for key in _settings()} == {
            key: original[key] for key in _settings()
        }
        assert child[CONF_MOTOR_PULSE_COUNT] == 20
    assert set(entry.data).isdisjoint(_settings())


async def test_paired_type_change_cannot_create_unconfigured_lp_sides(hass: HomeAssistant) -> None:
    data = build_pair_entry_data(
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_RICHMAT},
        {CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_BED_TYPE: BED_TYPE_RICHMAT},
        name="Pair",
    )
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_settings({CONF_BED_TYPE: BED_TYPE_LEGGETT_LP_LEGACY})

    assert result["errors"] == {"base": "lp_legacy_pair_settings"}
    assert entry.data == data
