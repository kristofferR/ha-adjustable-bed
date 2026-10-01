"""Offline capability minting requires a selector-invariant entity catalog."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import SELECTORS
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_starcode_abm5_4 import make_controller

POSITIVE = frozenset(("BOX1220", "BOX3633", "BOX25", "BOX25_STAR"))


async def test_display_alias_without_original_name_cannot_guess_offline_transport(hass):
    entry = make_entry(hass, "BOX25", "BOX3633", "BOX15")
    data = dict(entry.data)
    data.pop(const.CONF_STARCODE_TRANSPORT_SELECTOR)
    data[CONF_NAME] = "BLE misleading alias"
    hass.config_entries.async_update_entry(entry, data=data)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert coordinator.capability_controller is None
    with pytest.raises(ConnectionError, match="stored original BLE name"):
        await create_controller(coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, None)


def make_entry(hass: HomeAssistant, command: str, transport: str, ui: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:01",
            CONF_NAME: "App bed",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: command,
            const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
            const.CONF_STARCODE_UI_SELECTOR: ui,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.parametrize("command", SELECTORS)
@pytest.mark.parametrize("transport", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
@pytest.mark.parametrize("ui", ["BOX15", "BOX25_STAR"])
async def test_actual_offline_factory_only_mints_invariant_selector_catalog(
    hass, command, transport, ui
):
    entry = make_entry(hass, command, transport, ui)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    controller = coordinator.capability_controller
    stable = transport in ("BOX1220", "BOX3633") or command in POSITIVE
    if not stable:
        assert controller is None
        with pytest.raises(ConnectionError, match="manufacturer classification"):
            await create_controller(coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, None)
        return
    assert isinstance(controller, StarcodeAbm5_4Controller)
    assert controller.client is None and not controller._ready
    assert controller.controller_entity_discovery_complete
    assert controller.ui_selector == ui
    assert bool(controller.controller_select_specs) == (command in POSITIVE)
    assert bool(controller.controller_number_specs) == (command in POSITIVE)
    assert controller.get_light_state()["is_on"] is None
    assert not controller._massage_on and not controller._ui_state_observed
    if command in POSITIVE:
        with pytest.raises(ValueError, match="observed"):
            await controller.set_app_timer("20")


@pytest.mark.parametrize("manufacturer", [b"star", b"Star"])
@pytest.mark.parametrize("command", SELECTORS)
async def test_manufacturer_catalog_mutation_preserves_U_and_proves_offline_boundary(
    command, manufacturer
):
    controller = make_controller(command, ui="BOX15", device="BOX25")
    before = bool(controller.controller_number_specs)
    assert controller.controller_entity_discovery_complete == (command in POSITIVE)
    controller.client.read_gatt_char.return_value = manufacturer
    await controller._classify()
    assert controller.ui_selector == "BOX15"
    assert controller.command_selector == ("BOX25_STAR" if manufacturer == b"star" else "BOX25")
    assert controller.controller_number_specs and controller.controller_select_specs
    assert before == (command in POSITIVE)
    assert not controller._massage_on and not controller._ui_state_observed


@pytest.mark.parametrize(
    "offline_command,offline_transport",
    [("BOX25_STAR", "BOX25"), ("BOX15", "BOX1220"), ("BOX15", "BOX25"), ("BOX25_STAR", None)],
)
async def test_registered_pair_reload_restores_unreachable_invariant_side(
    hass: HomeAssistant,
    enable_custom_integrations,
    offline_command: str,
    offline_transport: str | None,
):
    left, right = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=4,
        unique_id="app-offline-pair",
        data={
            CONF_NAME: "App pair",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_PAIR_ID: "app-offline-pair",
            const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
            const.CONF_PAIR_SCHEMA_VERSION: 1,
            const.CONF_PAIR_MEMBER_ADDRESSES: [left, right],
            const.CONF_PAIR_CHILDREN: [
                {
                    CONF_ADDRESS: address,
                    CONF_NAME: side,
                    const.CONF_SIDE: side,
                    const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
                    const.CONF_MOTOR_COUNT: 2,
                    const.CONF_HAS_MASSAGE: True,
                    const.CONF_DISABLE_ANGLE_SENSING: True,
                    const.CONF_BLE_DEVICE_NAME: "Star original",
                    const.CONF_STARCODE_COMMAND_SELECTOR: command,
                    const.CONF_STARCODE_UI_SELECTOR: "BOX15",
                    const.CONF_STARCODE_TRANSPORT_SELECTOR: transport,
                }
                for side, address, command, transport in [
                    ("left", left, "BOX25", "BOX25"),
                    ("right", right, offline_command, offline_transport),
                ]
            ],
        },
    )
    descriptors = entry.data[const.CONF_PAIR_CHILDREN]
    assert isinstance(descriptors, list)
    if offline_transport is None:
        descriptors[1].pop(const.CONF_STARCODE_TRANSPORT_SELECTOR)
        descriptors[1][CONF_NAME] = "BLE display alias"
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "button", const.DOMAIN, right + "_starcode_abm5_4_wake", config_entry=entry
    )

    async def connect(child: AdjustableBedCoordinator) -> bool:
        if child.address == right:
            return False
        child._client = make_controller(device="BOX25").client
        child._controller = await create_controller(
            child, const.BED_TYPE_STARCODE_ABM5_4, None, child.client
        )
        await child._controller.start_notify()
        return True

    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
    ):
        if offline_transport == "BOX25" and offline_command not in POSITIVE:
            assert not await hass.config_entries.async_setup(entry.entry_id)
            assert entry.entry_id not in hass.data[const.DOMAIN]
            return
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        first = {
            row.unique_id: row.entity_id
            for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
            if row.unique_id.startswith(right)
        }
        assert any("_starcode_abm5_4_wake" in key for key in first)
        assert any("controller_number_starcode_abm5_4_light_level" in key for key in first) == (
            offline_command in POSITIVE
        )
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        second = {
            row.unique_id: row.entity_id
            for row in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
            if row.unique_id.startswith(right)
        }
        assert second == first
        controls = [
            entity_id
            for key, entity_id in first.items()
            if "starcode_abm5_4" in key and not entity_id.startswith("sensor.")
        ]
        assert controls
        for entity_id in controls:
            state = hass.states.get(entity_id)
            assert state is not None and state.state in ("unknown", "unavailable")
        wake_id = next(
            entity_id for key, entity_id in first.items() if key.endswith("_starcode_abm5_4_wake")
        )
        with pytest.raises(ConnectionError, match="Not connected"):
            await hass.services.async_call("button", "press", {"entity_id": wake_id}, blocking=True)
        assert await hass.config_entries.async_unload(entry.entry_id)
