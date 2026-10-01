"""Registered GAP rename persists only after its real scheduled BLE callback."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.command_scheduler import (
    CommandContext,
    CommandIntent,
    CommandOutcome,
    command_resources,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_vmatbasic import written
from tests.test_vmatbasic_paired import make_pair
from tests.test_vmatbasic_public import close, target


async def _receiver(hass: HomeAssistant) -> tuple[AdjustableBedCoordinator, str]:
    coordinator = await target(hass)
    coordinator.entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.data.setdefault(const.DOMAIN, {})[coordinator.entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id,
        identifiers={(const.DOMAIN, coordinator.address)},
        name="App receiver",
    )
    await async_register_services(hass)
    return coordinator, device.id


async def _rename(hass: HomeAssistant, device_id: str, name: str) -> None:
    await hass.services.async_call(
        const.DOMAIN,
        "vmatbasic_rename",
        {"device_id": device_id, "name": name},
        blocking=True,
    )


@pytest.mark.parametrize("outcome", [CommandOutcome.STOPPED, CommandOutcome.REPLACED])
async def test_registered_queued_rename_does_not_persist_without_execution(
    hass: HomeAssistant, outcome: CommandOutcome
) -> None:
    coordinator, device_id = await _receiver(hass)
    scheduler = coordinator._command_scheduler
    started = asyncio.Event()
    release = asyncio.Event()

    async def occupy_lane(_context: CommandContext) -> None:
        started.set()
        await release.wait()

    async def replacement(_context: CommandContext) -> None:
        return None

    blocker = await scheduler.enqueue(
        CommandIntent(
            occupy_lane,
            resources=command_resources("motor:back"),
            replacement_key="motor:back",
            cancel_running=False,
        )
    )
    await started.wait()
    pending = asyncio.create_task(_rename(hass, device_id, "Discarded"))
    try:
        async with asyncio.timeout(2):
            while not scheduler.has_pending:
                await asyncio.sleep(0)
        if outcome is CommandOutcome.STOPPED:
            epoch = scheduler.request_stop()
            scheduler.finish_stop(epoch)
        else:
            await scheduler.enqueue(
                CommandIntent(
                    replacement,
                    resources=command_resources("configuration"),
                    replacement_key="configuration",
                )
            )
        await asyncio.wait_for(pending, timeout=2)
        record = next(
            record for record in scheduler.recent_records if record.resources == ("configuration",)
        )
        assert record.outcome is outcome
        assert record.started_at is None
        assert written(coordinator.controller) == []
        assert coordinator.entry.data[CONF_NAME] == "App receiver"
        assert coordinator.name == "App receiver"
    finally:
        release.set()
        await blocker.future
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await close(coordinator)


async def test_registered_running_rename_gatt_failure_does_not_persist(
    hass: HomeAssistant,
) -> None:
    coordinator, device_id = await _receiver(hass)
    assert coordinator.client is not None
    try:
        with (
            patch.object(
                coordinator.client,
                "write_gatt_char",
                new=AsyncMock(side_effect=RuntimeError("rename GATT failure")),
            ),
            pytest.raises(RuntimeError, match="rename GATT failure"),
        ):
            await _rename(hass, device_id, "Rejected")
        assert coordinator.entry.data[CONF_NAME] == "App receiver"
        assert coordinator.name == "App receiver"
        assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.FAILED
    finally:
        await close(coordinator)


@pytest.mark.parametrize(
    "name,reason", [("x" * 21, "ten UTF-16"), ("😀" * 6, "ten UTF-16"), ("十" * 8, "twenty-byte")]
)
async def test_registered_overlong_rename_is_rejected_without_truncation(
    hass: HomeAssistant, name: str, reason: str
) -> None:
    coordinator, device_id = await _receiver(hass)
    try:
        with pytest.raises(ServiceValidationError, match=reason):
            await _rename(hass, device_id, name)
        assert written(coordinator.controller) == []
        assert coordinator.entry.data[CONF_NAME] == "App receiver"
    finally:
        await close(coordinator)


@pytest.mark.parametrize("side", [const.SIDE_LEFT, const.SIDE_RIGHT])
async def test_registered_paired_child_rename_persists_only_that_physical_receiver(
    hass: HomeAssistant, side: str
) -> None:
    pair, left, right = await make_pair(hass)
    pair.entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.data.setdefault(const.DOMAIN, {})[pair.entry.entry_id] = pair
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(
        config_entry_id=pair.entry.entry_id,
        **pair.device_info,
    )
    selected = pair.children[side]
    other = right if side == const.SIDE_LEFT else left
    device = registry.async_get_or_create_child(
        config_entry_id=pair.entry.entry_id,
        parent_device_id=parent.id,
        identifiers={(const.DOMAIN, selected.address)},
        name=selected.name,
    )
    await async_register_services(hass)
    try:
        with patch.object(
            selected, "remember_vmatbasic_name", wraps=selected.remember_vmatbasic_name
        ) as observed:
            await _rename(hass, device.id, "  Side  ")
        assert written(selected.controller) == [
            ("00002a00-0000-1000-8000-00805f9b34fb", b"Side", True)
        ]
        assert written(other.controller) == []
        observed.assert_called_once_with("Side")
        assert selected.entry.data[CONF_NAME] == "Side"
        assert other.entry.data[CONF_NAME] == "App receiver"
        assert CONF_NAME not in pair.entry.data
    finally:
        await close(left)
        await close(right)


@pytest.mark.parametrize(
    "name,packet", [("  New  ", b"New"), ("", b""), ("😀" * 5, "😀".encode() * 5)]
)
async def test_registered_successful_rename_persists_exact_decoded_name_once(
    hass: HomeAssistant, name: str, packet: bytes
) -> None:
    coordinator, device_id = await _receiver(hass)
    try:
        with patch.object(
            coordinator, "remember_vmatbasic_name", wraps=coordinator.remember_vmatbasic_name
        ) as observed:
            await _rename(hass, device_id, name)
        assert written(coordinator.controller) == [
            ("00002a00-0000-1000-8000-00805f9b34fb", packet, True)
        ]
        observed.assert_called_once_with(packet.decode("utf-8"))
        assert coordinator.entry.data[CONF_NAME] == packet.decode("utf-8")
        assert coordinator.name == packet.decode("utf-8")
        assert coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.COMPLETED
    finally:
        await close(coordinator)
