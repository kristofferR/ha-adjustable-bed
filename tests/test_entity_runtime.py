"""Entity runtimes preserve identity, subscriptions and config-entry ownership."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SBI,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PAIR_ID,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.controller_state import StateKey
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator, ChildEntryView
from custom_components.adjustable_bed.entity import AdjustableBedEntity
from custom_components.adjustable_bed.entity_runtime import EntityRuntime
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
    entity_runtimes,
)

from .test_paired_setup import LEFT_ADDR, _paired_entry

PLATFORMS = (
    "cover",
    "button",
    "number",
    "light",
    "switch",
    "select",
    "climate",
    "sensor",
    "binary_sensor",
)


@pytest.mark.parametrize("platform", PLATFORMS)
@pytest.mark.parametrize("topology", ("standalone", "separate_address", "single_address"))
async def test_every_platform_uses_typed_runtime_without_identity_changes(
    hass: HomeAssistant,
    platform: str,
    topology: str,
) -> None:
    """Every platform uses the shared views, retaining side IDs and availability."""
    if topology == "separate_address":
        entry = _paired_entry(hass)
        children = _build_paired_children(hass, entry)
        for child in children.values():
            await child.async_prime_offline_controller()
        owner = PairedBedCoordinator(hass, entry, children)
    else:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "address": LEFT_ADDR,
                CONF_BED_TYPE: BED_TYPE_SBI,
                CONF_MOTOR_COUNT: 2,
                CONF_PROTOCOL_VARIANT: "both",
                CONF_PAIR_ID: "pair_test",
                CONF_PAIR_MODE: topology,
            },
        )
        entry.add_to_hass(hass)
        physical = AdjustableBedCoordinator(hass, entry)
        await physical.async_prime_offline_controller()
        owner = (
            SingleAddressPairedCoordinator(hass, entry, physical)
            if topology == "single_address"
            else physical
        )
    if isinstance(owner, PairedBedCoordinator):
        _async_ensure_paired_device_registry(hass, entry, owner)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = owner
    runtimes = entity_runtimes(owner)
    entities = []
    module = importlib.import_module(f"custom_components.adjustable_bed.{platform}")
    # Use the same views for this platform so their actual routing can be asserted.
    with patch.object(module, "entity_runtimes", return_value=runtimes):
        await module.async_setup_entry(hass, entry, entities.extend)
    for entity in entities:
        if isinstance(entity, AdjustableBedEntity):
            assert entity._coordinator in runtimes
            assert entity.available
            assert entity.device_info == entity._coordinator.device_info
    assert len(runtimes) == (1 if topology == "standalone" else 2)
    for index, runtime in enumerate(runtimes):
        assert isinstance(runtime.entry, (MockConfigEntry, ChildEntryView))
        if topology == "single_address":
            side = (SIDE_LEFT, SIDE_RIGHT)[index]
            assert runtime.entity_unique_id("back") == f"{LEFT_ADDR}_back_{side}"
            assert runtime.entity_translation_key("back") == f"back_{side}"
        else:
            assert runtime.entity_unique_id("back") == f"{runtime.address}_back"
            assert runtime.entity_translation_key("back") == "back"
    await owner.async_shutdown()


async def test_view_state_subscriptions_and_connection_operations_follow_child(
    hass: HomeAssistant,
) -> None:
    entry = _paired_entry(hass)
    children = _build_paired_children(hass, entry)
    owner = PairedBedCoordinator(hass, entry, children)
    runtime: EntityRuntime = entity_runtimes(owner)[0]
    child = children[SIDE_LEFT]
    states = []
    positions = []
    unsubscribe_state = runtime.register_controller_state_callback(states.append)
    unsubscribe_position = runtime.register_position_callback(positions.append)
    child.handle_controller_state_update(StateKey[int]("test"), 7)
    child._handle_position_update("back", 12.0)
    assert runtime.controller_state["test"] == 7
    assert runtime.position_data["back"] == 12.0
    assert states[-1]["test"] == 7
    assert positions[-1]["back"] == 12.0
    assert children[SIDE_RIGHT].controller_state == {}
    unsubscribe_state()
    unsubscribe_position()
    with patch.object(child, "async_disconnect", new_callable=AsyncMock) as disconnect:
        await runtime.async_disconnect("user")
    disconnect.assert_awaited_once_with("user", serialize_with_commands=False)
    await owner.async_shutdown()


async def test_child_tasks_and_unload_callbacks_belong_to_real_entry(hass: HomeAssistant) -> None:
    entry = _paired_entry(hass)
    child = _build_paired_children(hass, entry)[SIDE_LEFT]
    finished = asyncio.Event()
    called = []

    async def background() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    task = child.entry.async_create_background_task(hass, background(), "child task")
    child.entry.async_on_unload(lambda: called.append("unloaded"))
    assert task in entry._background_tasks
    await entry._async_process_on_unload(hass)
    assert task.cancelled()
    assert finished.is_set()
    assert called == ["unloaded"]
    await child.async_shutdown()


async def test_single_address_support_capture_keeps_both_hydration_owners_paused(
    hass: HomeAssistant,
    enable_custom_integrations,
) -> None:
    """A logical capture view exposes diagnostics while pausing its whole link."""
    from custom_components.adjustable_bed.ble_diagnostics import BLEDiagnosticRunner
    from custom_components.adjustable_bed.support_bundle import generate_support_bundle

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": LEFT_ADDR,
            CONF_BED_TYPE: BED_TYPE_SBI,
            CONF_PROTOCOL_VARIANT: "both",
            CONF_PAIR_ID: "test_pair",
        },
    )
    entry.add_to_hass(hass)
    physical = AdjustableBedCoordinator(hass, entry)
    await physical.async_prime_offline_controller()
    owner = SingleAddressPairedCoordinator(hass, entry, physical)
    child = owner.children[SIDE_LEFT]

    async def unavailable() -> None:
        assert owner._single_position_hydration_pause_count == 1
        assert physical._position_hydration_pause_count == 1
        raise RuntimeError("test link unavailable")

    with (
        patch.object(BLEDiagnosticRunner, "_connect", side_effect=unavailable),
        patch(
            "custom_components.adjustable_bed.ble_diagnostics.get_service_info_snapshots_by_address",
            return_value=[],
        ),
        patch(
            "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
            return_value=[],
        ),
    ):
        report = await generate_support_bundle(
            hass,
            address=LEFT_ADDR,
            capture_duration=0,
            include_logs=False,
            coordinator=child,
            entry=entry,
        )
    assert owner._single_position_hydration_pause_count == 0
    assert physical._position_hydration_pause_count == 0
    assert report["command_trace"] == physical.command_trace
    assert child.client is physical.client
    assert child.pairing_diagnostics == physical.pairing_diagnostics
    await owner.async_shutdown()
