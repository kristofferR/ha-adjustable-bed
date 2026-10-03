"""Standalone-main public memory boundaries without an FSM dependency."""

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.button import AdjustableBedButton, _button_entities_for
from custom_components.adjustable_bed.limoss_remote_state import (
    LimossRemoteMemory,
    get_limoss_remote_session,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_entities import runtime
from tests.test_limoss_remote_review_lifecycle import live_controller


@pytest.mark.parametrize("invalid", ["missing", "different_layout"])
async def test_actual_generic_memory_preflight_rejects_second_target_before_any_write(
    hass, invalid
):
    targets = []
    for index in range(2):
        coordinator = actual_coordinator(
            hass,
            **{
                CONF_ADDRESS: f"AA:BB:CC:DD:EE:{index + 1:02X}",
                const.CONF_DISCONNECT_AFTER_COMMAND: False,
                const.CONF_LIMOSS_REMOTE_STATE: {
                    "capabilities": {
                        "key_count": 8,
                        "system": 0x12,
                        "vibration": 0,
                        "configuration": 0,
                        "memory_count": 8,
                    }
                },
            },
        )
        await live_controller(coordinator)
        targets.append(coordinator)
    first, second = targets
    get_limoss_remote_session(first.hass, first.address).memories.slots[8] = LimossRemoteMemory("Eight", ((0, -1),))
    if invalid == "different_layout":
        get_limoss_remote_session(second.hass, second.address).memories.slots[8] = LimossRemoteMemory(
            "Other layout", ((0, -1), (3, 2147483647))
        )
    await async_register_services(hass)
    try:
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(item, const.SIDE_BOTH) for item in targets], []),
            ),
            pytest.raises(ServiceValidationError),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "goto_preset",
                {"device_id": ["first", "second"], "preset": 8},
                blocking=True,
            )
        for item in targets:
            assert item.client is not None
            item.client.write_gatt_char.assert_not_awaited()
    finally:
        for item in targets:
            item._cancel_disconnect_timer()
            item._cancel_diagnostic_polling()
            await item._command_scheduler.async_shutdown()


@pytest.mark.parametrize(
    ("capacity", "extra_slots"), [(0, set()), (6, set()), (7, {7}), (8, {7, 8})]
)
def test_slot7_and8_entity_creation_requires_reported_capacity(hass, capacity, extra_slots):
    controller = make_controller(memory=capacity)
    entities = _button_entities_for(hass, runtime(controller))
    assert {
        item.entity_description.memory_slot
        for item in entities
        if isinstance(item, AdjustableBedButton) and item.entity_description.memory_slot in {7, 8}
    } == extra_slots
    for slot in {7, 8} - extra_slots:
        with pytest.raises(ValueError):
            controller.validate_memory_recall(slot)
    controller.client.write_gatt_char.assert_not_called()
