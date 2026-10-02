"""Unresolved cached app products stay diagnostic until explicitly selected."""

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.limoss_remote import LimossRemoteController
from custom_components.adjustable_bed.button import AdjustableBedButton, _button_entities_for
from custom_components.adjustable_bed.cover import _cover_entities_for
from tests.test_coordinator_limoss_remote import actual_coordinator


@pytest.mark.parametrize("system", [0, 0x30, 0xFF])
async def test_missing_product_unknown_cache_supports_offline_entities_and_diagnostics(hass, system):
    coordinator = actual_coordinator(
        hass,
        **{
            const.CONF_LIMOSS_REMOTE_STATE: {
                "capabilities": {
                    "key_count": 8,
                    "system": system,
                    "vibration": 0,
                    "configuration": 0,
                    "memory_count": 8,
                }
            }
        },
    )
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={
            key: value
            for key, value in coordinator.entry.data.items()
            if key != const.CONF_LIMOSS_REMOTE_PRODUCT
        },
    )
    client = coordinator.client
    assert client is not None
    coordinator._client = None
    await coordinator.async_prime_offline_controller()
    controller = coordinator.capability_controller
    assert isinstance(controller, LimossRemoteController)
    assert controller.product_selection is None
    assert controller.layout is None
    assert controller.visible_opcodes == controller.held_control_options == ()
    assert controller.motor_control_specs == ()
    assert not controller.supports_memory_programming
    assert not controller.supports_memory_presets
    diagnostics_capabilities = controller.protocol_diagnostics["capabilities"]
    assert isinstance(diagnostics_capabilities, dict)
    assert diagnostics_capabilities["system"] == system
    assert controller.protocol_diagnostics["layout"] is None
    assert _cover_entities_for(hass, coordinator) == []
    assert not any(
        isinstance(button, AdjustableBedButton) and button.entity_description.memory_slot
        for button in _button_entities_for(hass, coordinator)
    )
    with pytest.raises(ValueError, match="not rendered"):
        await controller.hold_control("motor_1_up", 100)
    with pytest.raises(ValueError, match="Saving requires"):
        await controller.program_memory(1)
    with pytest.raises(ValueError, match="Recalling requires"):
        controller.validate_memory_recall(1)
    from unittest.mock import AsyncMock

    assert isinstance(client.write_gatt_char, AsyncMock)
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("selected", "system", "expected_layout"),
    [(None, 0x12, "gKey8"), (None, 0x22, "cKey8"), ("bed", 0, "gKey8"), ("chair", 0, "cKey8")],
)
def test_recognized_or_explicit_product_preserves_exact_layout(selected, system, expected_layout):
    from tests.test_limoss_remote import make_controller

    controller = make_controller(system=system)
    controller.product_selection = selected
    assert controller.layout == expected_layout
    assert controller.supports_memory_programming
    assert controller.supports_memory_presets
    assert controller.motor_control_specs
