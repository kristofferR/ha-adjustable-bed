"""Failure injection for durable paired-bed ownership transfers."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.paired_registry import (
    _DeviceMove,
    _RegistryOwnership,
    async_has_side_controller_entities,
    async_unpair_entry,
)

from .test_paired_setup import LEFT_ADDR, PAIR_ID, RIGHT_ADDR, _paired_entry


@pytest.mark.parametrize("domain", ["climate", "light", "select"])
def test_controller_entity_check_is_scoped_to_its_side_and_integration(
    hass: HomeAssistant, domain: str,
) -> None:
    entry = _paired_entry(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        domain, DOMAIN, f"{LEFT_ADDR}_control", config_entry=entry,
    )
    registry.async_get_or_create(
        domain, "other_integration", f"{RIGHT_ADDR}_control", config_entry=entry,
    )
    assert async_has_side_controller_entities(hass, entry, LEFT_ADDR)
    assert not async_has_side_controller_entities(hass, entry, RIGHT_ADDR)


def _registered_pair(hass):
    entry = _paired_entry(hass)
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    parent = devices.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, PAIR_ID)}
    )
    rows = []
    children = []
    for address in (LEFT_ADDR, RIGHT_ADDR):
        device = devices.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, address)}, via_device_id=parent.id
        )
        device = devices.async_update_device(device.id, name_by_user=f"Custom {address}")
        row = entities.async_get_or_create(
            "cover", DOMAIN, f"{address}_back", config_entry=entry, device_id=device.id
        )
        row = entities.async_update_entity(row.entity_id, name=f"Custom {address}")
        rows.append(row)
        children.append(device)
    # A combined entity without a device must stay with the pair, not match a
    # missing side device merely because both device_id values are None.
    entities.async_get_or_create("button", DOMAIN, f"{PAIR_ID}_stop", config_entry=entry)
    return entry, rows, children


@pytest.mark.parametrize(
    "stage,index",
    [
        ("add", 1),
        ("add", 2),
        ("entity", 1),
        ("entity", 2),
        ("device", 1),
        ("device", 2),
        ("enable", 1),
        ("enable", 2),
        ("remove", 1),
    ],
)
@pytest.mark.parametrize("after", [False, True])
async def test_unpair_failure_preserves_registry_identity_and_customizations(
    hass: HomeAssistant,
    enable_custom_integrations,
    stage: str,
    index: int,
    after: bool,
) -> None:
    entry, rows, devices = _registered_pair(hass)
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    calls = 0
    original_data = dict(entry.data)
    target, name = {
        "add": (hass.config_entries, "async_add"),
        "entity": (ent_reg, "async_update_entity"),
        "device": (dev_reg, "async_update_device"),
        "enable": (hass.config_entries, "async_set_disabled_by"),
        "remove": (hass.config_entries, "async_remove"),
    }[stage]
    original = getattr(target, name)

    def should_fail():
        nonlocal calls
        calls += 1
        return calls == index

    def sync_failure(*args, **kwargs):
        fail = should_fail()
        if fail and not after:
            raise RuntimeError("injected ownership failure")
        result = original(*args, **kwargs)
        if fail:
            raise RuntimeError("injected ownership failure")
        return result

    async def async_failure(*args, **kwargs):
        fail = should_fail()
        if fail and not after:
            raise RuntimeError("injected ownership failure")
        result = True if stage == "enable" else await original(*args, **kwargs)
        if fail:
            raise RuntimeError("injected ownership failure")
        return result

    with (
        patch.object(hass.config_entries, "async_unload", return_value=True),
        patch.object(hass.config_entries, "async_setup", return_value=True),
        patch.object(
            hass.config_entries, "async_set_disabled_by", new_callable=AsyncMock, return_value=True
        )
        if stage != "enable"
        else patch.object(hass.config_entries, "async_setup", return_value=True),
        patch.object(
            target,
            name,
            side_effect=sync_failure if stage in ("entity", "device") else async_failure,
        ),
        pytest.raises(RuntimeError, match="injected ownership failure"),
    ):
        await async_unpair_entry(hass, entry)

    if stage == "remove" and after:
        # Source removal is the commit point. A post-removal exception must not
        # move user rows to the now-missing pair or delete the restored singles.
        assert hass.config_entries.async_get_entry(entry.entry_id) is None
        assert len(hass.config_entries.async_entries(DOMAIN)) == 2
        for row, device in zip(rows, devices, strict=True):
            restored_row = ent_reg.async_get(row.entity_id)
            restored_device = dev_reg.async_get(device.id)
            assert restored_row.config_entry_id == restored_device.config_entry_id
            assert hass.config_entries.async_get_entry(restored_row.config_entry_id) is not None
        return
    assert hass.config_entries.async_get_entry(entry.entry_id) is entry
    assert entry.data == original_data
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    for row, device in zip(rows, devices, strict=True):
        restored_row = ent_reg.async_get(row.entity_id)
        restored_device = dev_reg.async_get(device.id)
        assert restored_row.id == row.id
        assert restored_row.unique_id == row.unique_id
        assert restored_row.name == row.name
        assert restored_row.config_entry_id == entry.entry_id
        assert restored_row.device_id == device.id
        assert restored_device.identifiers == device.identifiers
        assert restored_device.name_by_user == device.name_by_user
        assert restored_device.via_device_id == device.via_device_id
        assert restored_device.config_entry_id == entry.entry_id


async def test_ownership_plan_validates_all_targets_before_mutating(hass: HomeAssistant) -> None:
    entry, rows, devices = _registered_pair(hass)
    plan = _RegistryOwnership(((rows[0], entry.entry_id), (rows[1], "missing")), ())
    with (
        patch.object(er.async_get(hass), "async_update_entity") as update,
        pytest.raises(Exception, match="Target config entry missing is missing"),
    ):
        plan.apply(hass)
    update.assert_not_called()


async def test_rollback_is_idempotent_and_keeps_a_failed_row_with_its_device(
    hass: HomeAssistant,
    caplog,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry, rows, devices = _registered_pair(hass)
    target = MockConfigEntry(domain=DOMAIN)
    target.add_to_hass(hass)
    plan = _RegistryOwnership(
        ((rows[0], target.entry_id),),
        (_DeviceMove(devices[0], entry.entry_id, target.entry_id, (DOMAIN, LEFT_ADDR), None),),
    )
    plan.apply(hass)
    with patch.object(
        er.async_get(hass), "async_update_entity", side_effect=RuntimeError("rollback blocked")
    ):
        assert plan.rollback(hass) is False
    assert "Could not restore entity ownership" in caplog.text
    assert "Device rollback would delete an unrestored entity" in caplog.text
    assert er.async_get(hass).async_get(rows[0].entity_id) is not None
    assert dr.async_get(hass).async_get(devices[0].id).config_entry_id == target.entry_id
    assert plan.rollback(hass) is True
    assert plan.rollback(hass) is True
    assert er.async_get(hass).async_get(rows[0].entity_id).config_entry_id == entry.entry_id
    assert dr.async_get(hass).async_get(devices[0].id).via_device_id == devices[0].via_device_id


@pytest.mark.parametrize("failure", ["detach_placeholder", "move_device", "none"])
async def test_rollback_restores_replaced_placeholder_and_original_device(
    hass: HomeAssistant,
    failure: str,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry, rows, devices = _registered_pair(hass)
    target = MockConfigEntry(domain=DOMAIN)
    target.add_to_hass(hass)
    registry = dr.async_get(hass)
    placeholder = registry.async_get_or_create(
        config_entry_id=target.entry_id, identifiers={(DOMAIN, LEFT_ADDR)}
    )
    placeholder = registry.async_update_device(placeholder.id, name_by_user="Placeholder name")
    plan = _RegistryOwnership(
        ((rows[0], target.entry_id),),
        (_DeviceMove(devices[0], entry.entry_id, target.entry_id, (DOMAIN, LEFT_ADDR), None),),
    )
    if failure == "none":
        plan.apply(hass)
    else:
        name = "async_update_device"
        fail_at = 1 if failure == "detach_placeholder" else 2
        calls = 0
        original = getattr(registry, name)

        def fail_after_mutation(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == fail_at:
                raise RuntimeError("mutated before failure")
            return result

        with (
            patch.object(registry, name, side_effect=fail_after_mutation),
            pytest.raises(RuntimeError),
        ):
            plan.apply(hass)
    assert plan.rollback(hass) is True
    assert plan.rollback(hass) is True
    assert registry.async_get(placeholder.id).name_by_user == "Placeholder name"
    assert registry.async_get(placeholder.id).config_entry_id == target.entry_id
    assert registry.async_get(devices[0].id).config_entry_id == entry.entry_id
    assert er.async_get(hass).async_get(rows[0].entity_id).config_entry_id == entry.entry_id


@pytest.mark.parametrize("failure", ["update", "setup", "rollback_setup"])
async def test_single_address_unpair_restores_config_and_preserves_original_error(
    hass: HomeAssistant,
    failure: str,
    caplog,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    original = {"address": LEFT_ADDR, "bed_type": "sbi", "protocol_variant": "both"}
    data = build_single_address_pair_entry_data(
        original,
        name="Paired",
        origin_title="Original",
        origin_unique_id=LEFT_ADDR,
        origin_options={"motor_count": 4},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        title="Paired",
        unique_id=LEFT_ADDR,
        options={"motor_count": 2},
        version=4,
    )
    entry.add_to_hass(hass)
    original_update = hass.config_entries.async_update_entry
    calls = 0

    def update(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original_update(*args, **kwargs)
        if failure == "update" and calls == 1:
            raise RuntimeError("original update failure")
        return result

    with (
        patch.object(hass.config_entries, "async_unload", return_value=True),
        patch.object(hass.config_entries, "async_update_entry", side_effect=update),
        patch.object(
            hass.config_entries,
            "async_setup",
            side_effect=(
                [True]
                if failure == "update"
                else [False, RuntimeError("rollback setup failure")]
                if failure == "rollback_setup"
                else [False, True]
            ),
        ),
        pytest.raises(RuntimeError, match="original update failure|standalone entry setup failed"),
    ):
        await async_unpair_entry(hass, entry)
    assert entry.data == data
    assert entry.options == {"motor_count": 2}
    assert entry.title == "Paired"
    assert entry.unique_id == LEFT_ADDR
    if failure == "rollback_setup":
        assert "Could not restore paired configuration" in caplog.text
        assert "rollback setup failure" in caplog.text


@pytest.mark.parametrize("stage", ["add", "enable"])
async def test_cancelled_unpair_restores_pair_ownership(
    hass: HomeAssistant,
    enable_custom_integrations,
    stage: str,
) -> None:
    import asyncio

    entry, rows, devices = _registered_pair(hass)
    original_add = hass.config_entries.async_add
    added = 0

    async def add(single):
        nonlocal added
        await original_add(single)
        added += 1
        if stage == "add" and added == 2:
            raise asyncio.CancelledError

    with (
        patch.object(hass.config_entries, "async_unload", return_value=True),
        patch.object(hass.config_entries, "async_setup", return_value=True),
        patch.object(hass.config_entries, "async_add", side_effect=add),
        patch.object(
            hass.config_entries, "async_set_disabled_by", side_effect=asyncio.CancelledError
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await async_unpair_entry(hass, entry)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    for row, device in zip(rows, devices, strict=True):
        assert er.async_get(hass).async_get(row.entity_id).config_entry_id == entry.entry_id
        assert dr.async_get(hass).async_get(device.id).config_entry_id == entry.entry_id
