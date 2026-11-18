"""The Bluetooth connection mode decides how long a bed keeps its link (issue #700)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

from .conftest import TEST_ADDRESS, TEST_NAME


def _keeson_entry(hass: HomeAssistant, **settings: object) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=TEST_NAME,
        data={
            CONF_ADDRESS: TEST_ADDRESS,
            CONF_NAME: TEST_NAME,
            const.CONF_BED_TYPE: const.BED_TYPE_KEESON,
            const.CONF_PROTOCOL_VARIANT: const.KEESON_VARIANT_ERGOMOTION,
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_PREFERRED_ADAPTER: "auto",
            **settings,
        },
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    ("mode", "keeps_link", "handoff"),
    [
        (const.CONNECTION_MODE_ALWAYS, True, False),
        (const.CONNECTION_MODE_RELEASE, False, True),
        (const.CONNECTION_MODE_IDLE, False, False),
    ],
)
async def test_connection_mode_sets_the_link_lifetime(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mode: str,
    keeps_link: bool,
    handoff: bool,
) -> None:
    del mock_coordinator_connected
    coordinator = AdjustableBedCoordinator(
        hass,
        _keeson_entry(
            hass, **{const.CONF_CONNECTION_MODE: mode, const.CONF_IDLE_DISCONNECT_SECONDS: 25}
        ),
    )

    assert await coordinator.async_connect()
    assert (coordinator._disconnect_timer is None) is keeps_link
    assert coordinator._disconnect_after_operation_enabled() is handoff
    if mode == const.CONNECTION_MODE_IDLE:
        assert coordinator._idle_disconnect_delay() == 25

    # Command completion re-arms the idle timer through the same path.
    coordinator._reset_disconnect_timer()
    assert (coordinator._disconnect_timer is None) is keeps_link
    coordinator._cancel_disconnect_timer()


async def test_kept_link_reconnects_on_demand_after_drop(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
) -> None:
    """A dropped kept link waits for the next command, like persistent controllers.

    Some Keeson receivers drop idle links and stop advertising after repeated
    timer reconnects (#369), so no reconnect timer may be scheduled.
    """
    del mock_coordinator_connected
    coordinator = AdjustableBedCoordinator(
        hass, _keeson_entry(hass, **{const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_ALWAYS})
    )
    assert await coordinator.async_connect()
    mock_bleak_client.is_connected = False

    coordinator._on_disconnect(mock_bleak_client)

    assert coordinator._reconnect_timer is None
    assert coordinator.client is None


async def test_options_save_the_connection_mode_and_its_seconds(hass: HomeAssistant) -> None:
    entry = _keeson_entry(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass

    rendered = await flow.async_step_settings()
    fields = {marker.schema for marker in rendered["data_schema"].schema}
    assert {const.CONF_CONNECTION_MODE, const.CONF_IDLE_DISCONNECT_SECONDS} <= fields
    assert "disconnect_after_command" not in fields

    result = await flow.async_step_settings(
        {const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE, const.CONF_IDLE_DISCONNECT_SECONDS: 90.0}
    )

    assert result["type"] == "create_entry"
    assert entry.data[const.CONF_CONNECTION_MODE] == const.CONNECTION_MODE_IDLE
    assert entry.data[const.CONF_IDLE_DISCONNECT_SECONDS] == 90


async def test_options_reject_seconds_out_of_range(hass: HomeAssistant) -> None:
    entry = _keeson_entry(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass

    result = await flow.async_step_settings({const.CONF_IDLE_DISCONNECT_SECONDS: 301})

    assert result["errors"] == {const.CONF_IDLE_DISCONNECT_SECONDS: "invalid_number"}


@pytest.mark.parametrize("bed_type", ["doublesleep", "sleep_number_mcr", "okin_rf_eco_bt"])
async def test_beds_that_hold_their_link_hide_the_connection_mode(
    hass: HomeAssistant, bed_type: str
) -> None:
    entry = _keeson_entry(hass, **{const.CONF_BED_TYPE: bed_type})
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass

    rendered = await flow.async_step_settings()

    fields = {marker.schema for marker in rendered["data_schema"].schema}
    assert const.CONF_CONNECTION_MODE not in fields
    assert const.CONF_IDLE_DISCONNECT_SECONDS not in fields
