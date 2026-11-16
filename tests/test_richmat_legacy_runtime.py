"""Real HA coordinator, scheduler, entities and public timed/held callers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat_legacy import controller as bed
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_casper_base import char


@pytest.fixture
async def runtime(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:86",
            "bed_type": "sleep_evolution",
            "protocol_variant": "A1",
            "disconnect_after_command": False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    route = bed.TRANSPORTS["n1"]
    client = MagicMock(is_connected=True, disconnect=AsyncMock(), stop_notify=AsyncMock())
    client.services = [
        SimpleNamespace(uuid=route.service_uuid, characteristics=[char(route.write_uuid, "write")])
    ]
    client.write_gatt_char = AsyncMock()
    coordinator._client = client
    ctrl = bed.RichmatLegacyController(coordinator)
    coordinator._controller = coordinator._offline_controller = ctrl
    await async_register_services(hass)
    with (
        virtual_clock() as clock,
        patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock()),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ),
    ):
        monkeypatch.setattr(bed, "monotonic", clock.time)
        await ctrl.start_notify()
        yield hass, coordinator, ctrl, client, clock
    client.is_connected = False
    await coordinator.async_shutdown()


def values(client):
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("caller", ("cover", "button", "timed", "hold"))
async def test_actual_coordinator_entity_and_finite_callers(runtime, caller):
    hass, c, ctrl, client, _clock = runtime
    if caller == "cover":
        spec = next(s for s in ctrl.motor_control_specs if s.key == "back")
        entity = AdjustableBedCover(c, _build_cover_description(spec))
        entity.async_write_ha_state = MagicMock()
        assert entity.extra_state_attributes["hold_lease_mode"] == "stream"
        await entity.async_open_cover()
    elif caller == "button":
        spec = next(s for s in ctrl.controller_button_specs if s.key == "richmat_legacy_h26_hdup")
        entity = ControllerActionButton(c, spec)
        assert entity.extra_state_attributes["hold_lease_mode"] == "stream"
        await entity.async_press()
    elif caller == "timed":
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 100},
            blocking=True,
        )
    else:
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "h26_hdup", "duration": 0.1},
            blocking=True,
        )
    assert values(client)[0] == "24"
    assert values(client)[-1] == "6e"
    assert set(values(client)) == {"24", "6e"}
    if caller in ("timed", "hold"):
        assert values(client) == ["24", "6e"] or values(client) == ["24", "24", "6e"]
    assert c._command_scheduler.recent_records


async def test_renewable_motion_expires_but_programming_never_renews(runtime):
    hass, c, ctrl, client, _clock = runtime

    async def hold():
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": "bed",
                "control": "h26_hdup",
                "duration": 0.75,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    task = asyncio.create_task(hold())
    await asyncio.sleep(0.25)
    before = len(values(client))
    await hold()  # Renewal returns without another DOWN.
    assert len(values(client)) == before
    assert not task.done()
    await task
    assert values(client)[-1] == "6e"
    record = c._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD and record.outcome is CommandOutcome.EXPIRED
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="renewable"):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": "bed",
                "control": "h26_lounge",
                "duration": 0.75,
                "hold_owner": "card",
                "hold_generation": 2,
            },
            blocking=True,
        )
    assert values(client) == []
    await hass.services.async_call(
        DOMAIN,
        "richmat_legacy",
        {"device_id": "bed", "control": "h26_lounge", "operation": "program"},
        blocking=True,
    )
    assert values(client) == ["2b", "6e"]
