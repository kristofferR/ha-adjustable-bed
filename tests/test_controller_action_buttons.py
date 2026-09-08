"""Named remote actions retain their identity across controller reconnects."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import (
    BedController,
    ControllerButtonSpec,
    ProductButtonSpec,
)
from custom_components.adjustable_bed.button import (
    AdjustableBedProductButton,
    ControllerActionButton,
    _button_entities_for,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_LP_LEGACY,
    CONF_BED_TYPE,
    CONF_LP_LEGACY_MODE,
    CONF_LP_LEGACY_MODEL,
    CONF_LP_LEGACY_WRITE_UUID,
    DOMAIN,
)

from .conftest import make_controller_mock


async def test_remote_action_dispatches_to_current_controller(hass):
    """Entity callbacks must use the live controller supplied by the command lock."""
    previous = make_controller_mock()
    current = make_controller_mock()
    previous.stop_all = AsyncMock()
    current.stop_all = AsyncMock()

    async def action(controller: BedController) -> None:
        await controller.stop_all()

    previous.controller_button_specs = (
        ControllerButtonSpec("example_action", "Remote control", action),
        ProductButtonSpec("example_action", "Product control", action),
    )
    coordinator = MagicMock()
    coordinator.capability_controller = previous
    coordinator.has_massage = False
    coordinator.device_info = {}
    coordinator.entity_side = None
    coordinator.entity_unique_id.side_effect = lambda key: f"device_{key}"

    async def dispatch(command, *, cancel_running):
        assert cancel_running is True
        await command(current)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    entities = _button_entities_for(hass, coordinator)
    products = [entity for entity in entities if isinstance(entity, AdjustableBedProductButton)]
    assert len(products) == 1
    assert products[0].unique_id == "device_product_action_example_action"
    assert not products[0].entity_registry_enabled_default
    actions = [
        entity
        for entity in entities
        if isinstance(entity, ControllerActionButton)
    ]
    assert len(actions) == 1
    assert actions[0].unique_id == "device_example_action"
    assert actions[0].name == "Remote control"
    assert actions[0].translation_key == "remote_action"
    assert actions[0].entity_registry_enabled_default
    await actions[0].async_press()
    current.stop_all.assert_awaited_once()
    previous.stop_all.assert_not_awaited()


async def test_legacy_profile_exposes_app_actions_without_guessed_covers(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    """The real integration setup exposes the complete selected app surface."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Legacy app bed",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_LP_LEGACY,
            CONF_LP_LEGACY_MODEL: "6BRM",
            CONF_LP_LEGACY_MODE: "framed",
            CONF_LP_LEGACY_WRITE_UUID: "11111111-2222-3333-4444-555555555555",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    from homeassistant.helpers import entity_registry as er

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    actions = [entity for entity in entries if entity.translation_key == "remote_action"]
    assert len(actions) == 6
    assert all("6brm_framed" in entity.unique_id for entity in actions)
    assert not any(entity.domain == "cover" for entity in entries)
    assert any(entity.translation_key == "stop" for entity in entries)
    assert await hass.config_entries.async_unload(entry.entry_id)
