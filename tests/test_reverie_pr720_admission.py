"""Registered comfort admission and nullable HomeID regressions."""

import asyncio
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.adjustable_bed.command_scheduler import PreparedCommandInvalidated
from custom_components.adjustable_bed.config_flow import (
    _pairlink_settings_schema,
    _validate_pairlink_option_values,
)
from custom_components.adjustable_bed.const import (
    CONF_PAIRLINK_HOME_ID,
    DOMAIN,
    PAIRLINK_ROLE_CENTRAL,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_reverie_local_send_guard import VALUES
from tests.test_reverie_pairlink import _controller, _join_central
from tests.test_reverie_pairlink_production import _entry


@pytest.mark.parametrize("action", ["reverie_set_comfort", "reverie_pairlink_alarm_comfort"])
@pytest.mark.parametrize("stop", [False, True])
async def test_registered_comfort_cannot_cross_stop_during_reconnect(
    hass, monkeypatch, action, stop
):
    controller, client, runtime, tasks = _controller()
    await _join_central(controller, client, runtime, tasks)
    entry = _entry(address=controller._coordinator.address, role=PAIRLINK_ROLE_CENTRAL)
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller
    coordinator._ready = True
    controller._coordinator = coordinator
    client.disconnect = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.device_info
    )
    await async_register_services(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    first_connect = True

    async def reconnect(**_kwargs):
        nonlocal first_connect
        coordinator._client = client
        if first_connect:
            first_connect = False
            entered.set()
            await release.wait()
        return True

    monkeypatch.setattr(coordinator, "async_ensure_connected", reconnect)
    call = asyncio.create_task(
        hass.services.async_call(
            DOMAIN, action, {"device_id": device.id, "comfort": VALUES}, blocking=True
        )
    )
    try:
        await entered.wait()
        if stop:
            await hass.services.async_call(
                DOMAIN, "stop_all", {"device_id": device.id}, blocking=True
            )
        client.writes.clear()
        release.set()
        result = (await asyncio.gather(call, return_exceptions=True))[0]
        if stop:
            assert isinstance(result, PreparedCommandInvalidated)
            assert client.writes == []
            # A new event captured after STOP remains admissible.
            await hass.services.async_call(
                DOMAIN, action, {"device_id": device.id, "comfort": VALUES}, blocking=True
            )
        else:
            assert result is None
        assert client.writes
    finally:
        release.set()
        if not call.done():
            call.cancel()
        await asyncio.gather(call, return_exceptions=True)
        await coordinator.async_shutdown()
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


@pytest.mark.parametrize("stored,expected", [(None, ""), (0, "0"), (12345, "12345")])
async def test_persisted_home_id_form_default_round_trips(hass, stored, expected):
    current = {CONF_PAIRLINK_HOME_ID: stored}
    schema = _pairlink_settings_schema(hass, current)
    field = next(key for key in schema if key.schema == CONF_PAIRLINK_HOME_ID)
    assert isinstance(field, vol.Optional)
    default = field.default
    assert callable(default)
    rendered = default()
    assert rendered == expected
    values = {CONF_PAIRLINK_HOME_ID: rendered}
    assert _validate_pairlink_option_values(hass, current, values) == {}
    assert values[CONF_PAIRLINK_HOME_ID] == stored
