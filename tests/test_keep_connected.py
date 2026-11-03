"""An idle timeout of 0 keeps a bed connected (issue #700)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

from .conftest import TEST_ADDRESS, TEST_NAME


def _keeson_entry(
    hass: HomeAssistant, *, idle_seconds: int, disconnect_after_command: bool
) -> MockConfigEntry:
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
            const.CONF_DISCONNECT_AFTER_COMMAND: disconnect_after_command,
            const.CONF_IDLE_DISCONNECT_SECONDS: idle_seconds,
        },
        unique_id=TEST_ADDRESS,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize(
    ("idle_seconds", "disconnect_after_command", "keeps_link"),
    [
        (const.IDLE_DISCONNECT_KEEP_CONNECTED, False, True),
        # Disconnect After Command keeps priority over the idle timeout.
        (const.IDLE_DISCONNECT_KEEP_CONNECTED, True, False),
        (const.DEFAULT_IDLE_DISCONNECT_SECONDS, False, False),
    ],
)
async def test_zero_idle_timeout_skips_idle_disconnect(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    idle_seconds: int,
    disconnect_after_command: bool,
    keeps_link: bool,
) -> None:
    del mock_coordinator_connected
    coordinator = AdjustableBedCoordinator(
        hass,
        _keeson_entry(
            hass, idle_seconds=idle_seconds, disconnect_after_command=disconnect_after_command
        ),
    )

    assert await coordinator.async_connect()
    assert (coordinator._disconnect_timer is None) is keeps_link

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
        hass,
        _keeson_entry(
            hass,
            idle_seconds=const.IDLE_DISCONNECT_KEEP_CONNECTED,
            disconnect_after_command=False,
        ),
    )
    assert await coordinator.async_connect()
    mock_bleak_client.is_connected = False

    coordinator._on_disconnect(mock_bleak_client)

    assert coordinator._reconnect_timer is None
    assert coordinator.client is None


async def test_options_accept_zero_idle_timeout(hass: HomeAssistant) -> None:
    entry = _keeson_entry(
        hass,
        idle_seconds=const.DEFAULT_IDLE_DISCONNECT_SECONDS,
        disconnect_after_command=False,
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.handler, flow.hass = entry.entry_id, hass

    rendered = await flow.async_step_settings()
    schema = rendered["data_schema"]
    assert isinstance(schema, vol.Schema)
    submitted = schema({const.CONF_IDLE_DISCONNECT_SECONDS: "0"})
    with pytest.raises(vol.Invalid):
        schema({const.CONF_IDLE_DISCONNECT_SECONDS: -1})

    await flow.async_step_settings(submitted)

    assert entry.data[const.CONF_IDLE_DISCONNECT_SECONDS] == const.IDLE_DISCONNECT_KEEP_CONNECTED
