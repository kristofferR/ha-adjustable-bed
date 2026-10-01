"""Public STOP cleanup and feedback-only light actions after PR review."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.starcode_m5x5 import StarcodeM5X5Controller
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.starcode_accessory_group import _tasks
from tests.test_starcode_accessory_group import group, target
from tests.test_starcode_m5x5 import VECTORS, make_controller


@pytest.mark.parametrize("missing", [0, 1, 2, 3])
async def test_registered_stop_cancels_then_attempts_every_reachable_member(
    hass: HomeAssistant, missing: int
) -> None:
    members = group(hass)
    main = members[0]
    main.entry.mock_state(hass, ConfigEntryState.LOADED)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=main.entry.entry_id, identifiers={(DOMAIN, main.address)}
    )
    entered = asyncio.Event()

    async def retained() -> None:
        entered.set()
        await asyncio.Event().wait()

    pending = asyncio.create_task(retained())
    await entered.wait()
    for member in members:
        _tasks(hass).setdefault(member.entry.entry_id, set()).add(pending)

        async def stop() -> None:
            assert pending.cancelling()

        member.async_stop_command = AsyncMock(side_effect=stop)
    hass.data[DOMAIN].pop(members[missing].entry.entry_id)
    await async_register_services(hass)
    try:
        with pytest.raises(ExceptionGroup):
            await hass.services.async_call(
                DOMAIN,
                "starcode_move_lifts",
                {CONF_DEVICE_ID: device.id, "action": "stop"},
                blocking=True,
            )
        with pytest.raises(asyncio.CancelledError):
            await pending
        for index, member in enumerate(members):
            assert member.async_stop_command.await_count == int(index != missing)
            assert member.controller.write_command.await_count == 0
    finally:
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending


async def test_registered_stop_transport_failure_does_not_skip_other_members(
    hass: HomeAssistant,
) -> None:
    main, *lifts = group(hass)
    main.entry.mock_state(hass, ConfigEntryState.LOADED)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=main.entry.entry_id, identifiers={(DOMAIN, main.address)}
    )
    lifts[0].async_stop_command.side_effect = ConnectionError("lift transport lost")
    await async_register_services(hass)
    with pytest.raises(ExceptionGroup):
        await hass.services.async_call(
            DOMAIN,
            "starcode_move_lifts",
            {CONF_DEVICE_ID: device.id, "action": "stop"},
            blocking=True,
        )
    assert all(member.async_stop_command.await_count == 1 for member in (main, *lifts))


@pytest.mark.parametrize("behavior", ["catalog", "toggle"])
@pytest.mark.parametrize("profile", ["cb25", "f23", "kneading"])
@pytest.mark.parametrize("platforms", [("switch", "light"), ("light", "switch")])
async def test_actual_feedback_light_catalog_and_toggle(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    profile: str,
    platforms: tuple[str, str],
    behavior: str,
) -> None:
    coordinator = target(hass, 10, profile)
    entry = coordinator.entry
    hass.config_entries.async_update_entry(entry, version=4)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "switch",
        DOMAIN,
        coordinator.entity_unique_id("under_bed_lights"),
        config_entry=coordinator.entry,
        suggested_object_id="old_floor_light",
    )

    async def connect(runtime: AdjustableBedCoordinator) -> bool:
        runtime._client = make_controller(hass, profile, "star").client
        runtime._client.disconnect = AsyncMock()
        runtime._controller = StarcodeM5X5Controller(runtime, profile=profile)
        runtime._controller.write_command = AsyncMock()
        await runtime._controller.start_notify()
        return True

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
        patch.object(AdjustableBedCoordinator, "_schedule_controller_state_refresh"),
        patch("custom_components.adjustable_bed.PLATFORMS", [Platform(p) for p in platforms]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    controller = coordinator.controller
    assert isinstance(controller, StarcodeM5X5Controller)
    try:
        rows = er.async_entries_for_config_entry(registry, entry.entry_id)
        lights = [row for row in rows if row.domain == "light"]
        assert len(lights) == 1
        if behavior == "catalog":
            assert registry.async_get(stale.entity_id) is None
            assert not any(
                row.domain == "switch" and row.translation_key == "under_bed_lights" for row in rows
            )
            return
        light_id = lights[0].entity_id
        writes = controller.write_command
        writes.reset_mock()
        assert hass.states.get(light_id).state == "unknown"
        with pytest.raises(ServiceValidationError, match="Light state is unknown"):
            await hass.services.async_call(
                "light", "toggle", {"entity_id": light_id}, blocking=True
            )
        writes.assert_not_awaited()
        receive = coordinator.client.start_notify.await_args.args[1]
        for is_on in (True, False):
            # Accepted normal-feedback byte 14 owns on/off, independent of requested writes.
            packet = bytearray.fromhex(
                "a5 0b 00 00 00 00 00 00 00 00 00 00 00 00 01 00 00 00 00 00"
            )
            packet[14] = int(is_on)
            receive(None, packet)
            await hass.async_block_till_done()
            observed = "on" if is_on else "off"
            assert hass.states.get(light_id).state == observed
            writes.reset_mock()
            await hass.services.async_call(
                "light", "toggle", {"entity_id": light_id}, blocking=True
            )
            vector = next(
                row
                for row in VECTORS
                if row["profile"] == profile
                and (row["dialect"] == "star" or profile != "cb25")
                and row["action"] == ("light_off" if is_on else "light_on")
            )
            actual = [
                call.args[0]
                for call in writes.await_args_list
                for _ in range(call.kwargs.get("repeat_count", 1))
            ]
            assert actual == [bytes.fromhex(raw) for raw in vector["vector"].split(";")]
            assert hass.states.get(light_id).state == observed
        coordinator._notify_connection_state_change(False)
        assert hass.states.get(light_id).state == "unknown"
        writes.reset_mock()
        with pytest.raises(ServiceValidationError, match="Light state is unknown"):
            await hass.services.async_call(
                "light", "toggle", {"entity_id": light_id}, blocking=True
            )
        writes.assert_not_awaited()
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
