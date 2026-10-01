"""Rendered options distinguish artifact cadence from user pulse choices."""

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow


def options_flow(hass: HomeAssistant, data: dict[str, object]) -> AdjustableBedOptionsFlow:
    """Open a real options flow against a stored entry."""
    entry = MockConfigEntry(domain=const.DOMAIN, data=data)
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass
    return flow


@pytest.mark.parametrize("profile", ["basic", "cbi", "xtbox"])
async def test_hidden_artifact_cadence_remains_generated_on_repeated_options_saves(
    hass: HomeAssistant, profile: str
) -> None:
    flow = options_flow(
        hass,
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_NAME: "App receiver",
            const.CONF_BED_TYPE: const.BED_TYPE_VMATBASIC,
            const.CONF_VMATBASIC_PROFILE: profile,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_MOTOR_PULSE_COUNT: 34,
            const.CONF_MOTOR_PULSE_DELAY_MS: 30,
            const.CONF_MOTOR_PULSE_USER_SET: False,
        },
    )
    for timeout in (45, 50):
        rendered = await flow.async_step_settings()
        schema = rendered["data_schema"]
        assert isinstance(schema, vol.Schema)
        submitted = schema({const.CONF_IDLE_DISCONNECT_SECONDS: timeout})
        assert isinstance(submitted, dict)
        assert const.CONF_MOTOR_PULSE_COUNT not in submitted
        assert const.CONF_MOTOR_PULSE_DELAY_MS not in submitted
        result = await flow.async_step_settings(submitted)
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert flow.config_entry.data[const.CONF_IDLE_DISCONNECT_SECONDS] == timeout
        assert flow.config_entry.data[const.CONF_MOTOR_PULSE_COUNT] == 34
        assert flow.config_entry.data[const.CONF_MOTOR_PULSE_DELAY_MS] == 30
        assert flow.config_entry.data[const.CONF_MOTOR_PULSE_USER_SET] is False


async def test_displayed_explicit_pulse_values_are_user_owned(hass: HomeAssistant) -> None:
    flow = options_flow(
        hass,
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_NAME: "Generic receiver",
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_MOTOR_PULSE_USER_SET: False,
        },
    )
    rendered = await flow.async_step_settings()
    schema = rendered["data_schema"]
    assert isinstance(schema, vol.Schema)
    submitted = schema({const.CONF_MOTOR_PULSE_COUNT: "17", const.CONF_MOTOR_PULSE_DELAY_MS: "90"})
    assert isinstance(submitted, dict)
    result = await flow.async_step_settings(submitted)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_COUNT] == 17
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_DELAY_MS] == 90
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_USER_SET] is True


async def test_unrelated_save_preserves_existing_user_pulse_override(hass: HomeAssistant) -> None:
    flow = options_flow(
        hass,
        {
            CONF_ADDRESS: "11:22:33:44:55:66",
            CONF_NAME: "Generic receiver",
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_MOTOR_PULSE_COUNT: 17,
            const.CONF_MOTOR_PULSE_DELAY_MS: 90,
            const.CONF_MOTOR_PULSE_USER_SET: True,
        },
    )
    result = await flow.async_step_settings({const.CONF_IDLE_DISCONNECT_SECONDS: 55})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert flow.config_entry.data[const.CONF_IDLE_DISCONNECT_SECONDS] == 55
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_COUNT] == 17
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_DELAY_MS] == 90
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_USER_SET] is True


async def test_paired_displayed_pulse_override_updates_both_children(hass: HomeAssistant) -> None:
    flow = options_flow(
        hass,
        {
            CONF_NAME: "Pair",
            const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_PAIR_ID: "pulse_pair",
            const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
            const.CONF_PAIR_MEMBER_ADDRESSES: ["11:22:33:44:55:66", "11:22:33:44:55:77"],
            const.CONF_PAIR_CHILDREN: [
                {
                    const.CONF_SIDE: side,
                    CONF_ADDRESS: address,
                    CONF_NAME: side,
                    const.CONF_BED_TYPE: const.BED_TYPE_LEGGETT_OKIN,
                    const.CONF_MOTOR_COUNT: 4,
                    const.CONF_DISABLE_ANGLE_SENSING: True,
                    const.CONF_MOTOR_PULSE_COUNT: 10,
                    const.CONF_MOTOR_PULSE_DELAY_MS: 100,
                }
                for side, address in (
                    (const.SIDE_LEFT, "11:22:33:44:55:66"),
                    (const.SIDE_RIGHT, "11:22:33:44:55:77"),
                )
            ],
        },
    )
    rendered = await flow.async_step_settings()
    schema = rendered["data_schema"]
    assert isinstance(schema, vol.Schema)
    submitted = schema({const.CONF_MOTOR_PULSE_COUNT: "17", const.CONF_MOTOR_PULSE_DELAY_MS: "90"})
    assert isinstance(submitted, dict)
    result = await flow.async_step_settings(submitted)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert flow.config_entry.data[const.CONF_MOTOR_PULSE_USER_SET] is True
    for child in flow.config_entry.data[const.CONF_PAIR_CHILDREN]:
        assert child[const.CONF_MOTOR_PULSE_COUNT] == 17
        assert child[const.CONF_MOTOR_PULSE_DELAY_MS] == 90
