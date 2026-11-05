"""Exercise native child conversion against HA's real registries."""

import asyncio
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed import _build_paired_children
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import (
    KEY_PHYSICAL_DEVICES,
    async_register_children,
    async_restore_full_device,
)

from .test_paired_registry import _registered_pair


def migrated_pair(hass):
    entry, rows, original_devices = _registered_pair(hass)
    registry = dr.async_get(hass)
    registry.async_update_device(
        original_devices[0].id, manufacturer="Bed maker", model="Model 1", serial_number="serial"
    )
    registry.async_config_entry_unloaded(entry.entry_id)
    coordinator = PairedBedCoordinator(hass, entry, _build_paired_children(hass, entry))
    async_register_children(hass, coordinator)
    return entry, rows, original_devices, coordinator


async def test_native_conversion_and_restore_preserve_identity(hass):
    entry, rows, originals, coordinator = migrated_pair(hass)
    registry = dr.async_get(hass)
    await hass.async_block_till_done()
    async_register_children(hass, coordinator)
    for original, side in zip(originals, ("left", "right"), strict=True):
        child = registry.async_get(original.id)
        assert isinstance(child, dr.ChildDeviceEntry)
        assert child.name_by_user == original.name_by_user
        assert child.created_at == original.created_at
        assert not hasattr(child, "manufacturer")
        # Reload is idempotent and cannot erase the saved physical metadata.
        registry.async_config_entry_unloaded(entry.entry_id)
        restored = await async_restore_full_device(hass, entry, child, side)
        assert isinstance(restored, dr.DeviceEntry)
        assert restored.id == original.id
        assert restored.name_by_user == original.name_by_user
        assert restored.created_at == original.created_at
    assert registry.async_get(originals[0].id).manufacturer == "Bed maker"
    assert entry.data[KEY_PHYSICAL_DEVICES]["left"]["serial_number"] == "serial"
    await hass.async_block_till_done()
    for row in rows:
        current = er.async_get(hass).async_get(row.entity_id)
        for key in (
            "id",
            "entity_id",
            "unique_id",
            "device_id",
            "config_entry_id",
            "name",
            "created_at",
        ):
            assert getattr(current, key) == getattr(row, key)


@pytest.mark.parametrize("after", [False, True])
async def test_failed_full_restore_keeps_entity_rows(hass, after):
    entry, rows, originals, _ = migrated_pair(hass)
    registry = dr.async_get(hass)
    child = registry.async_get(originals[0].id)
    original_create = registry.async_get_or_create

    def fail(**kwargs):
        if after:
            original_create(**kwargs)
        raise RuntimeError("restore failed")

    registry.async_config_entry_unloaded(entry.entry_id)
    with (
        patch.object(registry, "async_get_or_create", side_effect=fail),
        pytest.raises(RuntimeError, match="restore failed"),
    ):
        await async_restore_full_device(hass, entry, child, "left")
    await hass.async_block_till_done()
    assert registry.async_get(child.id).name_by_user == child.name_by_user
    for row in rows:
        current = er.async_get(hass).async_get(row.entity_id)
        for key in (
            "id",
            "entity_id",
            "unique_id",
            "device_id",
            "config_entry_id",
            "name",
            "created_at",
        ):
            assert getattr(current, key) == getattr(row, key)


async def test_cancelled_restore_reattaches_entities_after_removal_event(hass):
    entry, rows, originals, _ = migrated_pair(hass)
    registry = dr.async_get(hass)
    child = registry.async_get(originals[0].id)
    original_remove = registry.async_remove_device

    def cancel_after_remove(device_id):
        original_remove(device_id)
        asyncio.current_task().cancel()

    registry.async_config_entry_unloaded(entry.entry_id)
    with patch.object(registry, "async_remove_device", side_effect=cancel_after_remove):
        task = hass.async_create_task(async_restore_full_device(hass, entry, child, "left"))
        with pytest.raises(asyncio.CancelledError):
            await task
    await hass.async_block_till_done()
    assert registry.async_get(child.id).name_by_user == child.name_by_user
    for row in rows:
        current = er.async_get(hass).async_get(row.entity_id)
        for key in (
            "id",
            "entity_id",
            "unique_id",
            "device_id",
            "config_entry_id",
            "name",
            "created_at",
        ):
            assert getattr(current, key) == getattr(row, key)


async def test_restore_rejects_already_removed_child_without_waiting(hass):
    entry, _, originals, _ = migrated_pair(hass)
    registry = dr.async_get(hass)
    child = registry.async_get(originals[0].id)
    registry.async_remove_device(child.id)
    with pytest.raises(ValueError, match="no longer exists"):
        async with asyncio.timeout(1):
            await async_restore_full_device(hass, entry, child, "left")


async def test_restore_times_out_missing_removal_event_and_recovers_rows(hass):
    entry, rows, originals, _ = migrated_pair(hass)
    registry = dr.async_get(hass)
    child = registry.async_get(originals[0].id)
    fire = hass.bus.async_fire_internal

    def omit_remove(event_type, data=None, *args, **kwargs):
        if event_type == dr.EVENT_DEVICE_REGISTRY_UPDATED and data["action"] == "remove":
            return
        fire(event_type, data, *args, **kwargs)

    registry.async_config_entry_unloaded(entry.entry_id)
    with (
        patch("custom_components.adjustable_bed.paired_devices.DEVICE_REMOVAL_TIMEOUT", 0.01),
        patch.object(type(hass.bus), "async_fire_internal", side_effect=omit_remove),
        pytest.raises(TimeoutError),
    ):
        await async_restore_full_device(hass, entry, child, "left")
    assert isinstance(registry.async_get(child.id), dr.ChildDeviceEntry)
    for row in rows:
        assert er.async_get(hass).async_get(row.entity_id).device_id == row.device_id


@pytest.mark.parametrize("after", [False, True])
async def test_child_rollback_failure_preserves_original_error_and_entity_rows(hass, after):
    entry, rows, originals, _ = migrated_pair(hass)
    registry = dr.async_get(hass)
    child = registry.async_get(originals[0].id)
    create_child = registry.async_get_or_create_child

    def fail(**kwargs):
        if after:
            create_child(**kwargs)
        raise RuntimeError("rollback failed")

    registry.async_config_entry_unloaded(entry.entry_id)
    with (
        patch.object(registry, "async_get_or_create", side_effect=RuntimeError("original failure")),
        patch.object(registry, "async_get_or_create_child", side_effect=fail),
        pytest.raises(RuntimeError, match="original failure"),
    ):
        await async_restore_full_device(hass, entry, child, "left")
    await hass.async_block_till_done()
    for row in rows:
        current = er.async_get(hass).async_get(row.entity_id)
        assert current.id == row.id
        assert current.unique_id == row.unique_id
        if after or row.device_id != child.id:
            assert current.device_id == row.device_id
        else:
            # An absent device cannot own rows. Keep them for the caller's reload.
            assert current.device_id is None


@pytest.mark.parametrize("single_address", [False, True])
async def test_native_child_service_targets_are_side_safe(hass, single_address):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.const import (
        CONF_PAIR_MODE,
        DOMAIN,
        PAIR_MODE_SINGLE_ADDRESS,
    )
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.services import (
        _get_support_bundle_target_from_device,
        _resolve_sided_targets,
    )

    from .test_paired_setup import LEFT_ADDR, _paired_entry

    entry = _paired_entry(hass)
    if single_address:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_PAIR_MODE: PAIR_MODE_SINGLE_ADDRESS, "address": LEFT_ADDR},
        )
        coordinator = SingleAddressPairedCoordinator(
            hass, entry, AdjustableBedCoordinator(hass, entry)
        )
    else:
        coordinator = PairedBedCoordinator(hass, entry, _build_paired_children(hass, entry))
    _async_ensure_paired_device_registry(hass, entry, coordinator)
    async_register_children(hass, coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    registry = dr.async_get(hass)
    children = dr.async_child_entries_for_config_entry(registry, entry.entry_id)
    left = next(child for child in children if child.name == coordinator.children["left"].name)
    right = next(child for child in children if child.id != left.id)
    # Diagnostics still work when setup is unavailable, movement never does.
    assert _get_support_bundle_target_from_device(hass, left.id)[0] == LEFT_ADDR
    with pytest.raises(ServiceValidationError) as error:
        _resolve_sided_targets(hass, [left.id], None)
    assert error.value.translation_key == "service_config_entry_not_loaded"
    entry.mock_state(hass, ConfigEntryState.LOADED)
    try:
        assert _resolve_sided_targets(hass, [left.id], None)[0] == [(coordinator, "left")]
        assert _resolve_sided_targets(hass, [left.parent_device_id], None)[0] == [
            (coordinator, "both")
        ]
        assert _resolve_sided_targets(hass, [left.id, right.id], None)[0] == [(coordinator, "both")]
        with pytest.raises(ServiceValidationError, match="conflicts") as error:
            _resolve_sided_targets(hass, [left.id], "right")
        assert error.value.translation_key == "side_selection_conflict"
        assert error.value.translation_placeholders == {"inferred_side": "left", "side": "right"}
        with pytest.raises(ServiceValidationError, match="conflicts"):
            _resolve_sided_targets(hass, [left.id], "both")
        with pytest.raises(ServiceValidationError) as error:
            _resolve_sided_targets(hass, [left.id, "missing"], None)
        assert error.value.translation_key == "service_device_not_found"
        await coordinator.async_remove_child("left")
        with pytest.raises(ServiceValidationError, match="side is unavailable") as error:
            _resolve_sided_targets(hass, [left.id], None)
        assert error.value.translation_key == "side_unavailable"
    finally:
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await coordinator.async_shutdown()


async def test_registry_failure_after_connect_shuts_down_pair(
    hass,
    mock_coordinator_connected,
    enable_custom_integrations,
):
    from custom_components.adjustable_bed.const import DOMAIN

    from .test_paired_setup import _paired_entry

    entry = _paired_entry(hass)
    calls = 0

    def fail_after_connect(hass, coordinator):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("registry unavailable")
        async_register_children(hass, coordinator)

    with (
        patch(
            "custom_components.adjustable_bed.async_register_children",
            side_effect=fail_after_connect,
        ),
        patch.object(
            PairedBedCoordinator,
            "async_shutdown",
            autospec=True,
            side_effect=PairedBedCoordinator.async_shutdown,
        ) as shutdown,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    shutdown.assert_awaited_once()
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.parametrize("child", [False, True])
async def test_service_rejects_devices_owned_by_another_domain(hass, child):
    from homeassistant.exceptions import ServiceValidationError
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.services import _resolve_sided_targets

    entry = MockConfigEntry(domain="other_integration")
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("other_integration", "parent")}
    )
    if child:
        device = registry.async_get_or_create_child(
            config_entry_id=entry.entry_id,
            identifiers={("other_integration", "side")},
            parent_device_id=device.id,
        )
    with pytest.raises(ServiceValidationError) as error:
        _resolve_sided_targets(hass, [device.id], None)
    assert error.value.translation_key == "service_device_wrong_domain"
