"""Focused service exposure tests for OCTO PIN enrollment and reset."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import ControllerHoldSpec
from custom_components.adjustable_bed.beds.octo import OctoController
from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_OCTO_PIN,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_VARIANT_STANDARD,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.services import async_register_services


async def _target(
    hass: HomeAssistant,
) -> tuple[MockConfigEntry, AdjustableBedCoordinator, OctoController]:
    """Create a disconnected controller fixture; service writes are mocked."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="OCTO test",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "OCTO test",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_OCTO_PIN: "",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = OctoController(coordinator)
    controller._session_ready = True
    controller._pin_feature_active = True
    controller._has_pin = False
    controller._pin_locked = False
    coordinator._controller = controller

    async def execute(command, **_kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return entry, coordinator, controller


async def test_octo_enroll_pin_requires_matching_four_ascii_digits(
    hass: HomeAssistant,
) -> None:
    await async_register_services(hass)
    _entry, coordinator, controller = await _target(hass)
    write = AsyncMock()
    controller._write_octo_command = write

    with patch(
        "custom_components.adjustable_bed.services._call_targets",
        return_value=[(coordinator, SIDE_BOTH)],
    ):
        with pytest.raises(ServiceValidationError, match="do not match"):
            await hass.services.async_call(
                DOMAIN,
                "octo_enroll_pin",
                {
                    "device_id": "octo-device",
                    CONF_OCTO_PIN: "1234",
                    "octo_pin_confirmation": "1235",
                },
                blocking=True,
            )

        with pytest.raises(ServiceValidationError, match="ASCII digits"):
            await hass.services.async_call(
                DOMAIN,
                "octo_enroll_pin",
                {
                    "device_id": "octo-device",
                    CONF_OCTO_PIN: "１２３４",
                    "octo_pin_confirmation": "１２３４",
                },
                blocking=True,
            )

    write.assert_not_awaited()
    assert _entry.data[CONF_OCTO_PIN] == ""


async def test_octo_enroll_pin_sends_and_persists_one_physical_receiver(
    hass: HomeAssistant,
) -> None:
    await async_register_services(hass)
    entry, coordinator, controller = await _target(hass)
    write = AsyncMock()
    controller._write_octo_command = write

    with patch(
        "custom_components.adjustable_bed.services._call_targets",
        return_value=[(coordinator, SIDE_BOTH)],
    ):
        await hass.services.async_call(
            DOMAIN,
            "octo_enroll_pin",
            {
                "device_id": "octo-device",
                CONF_OCTO_PIN: "0369",
                "octo_pin_confirmation": "0369",
            },
            blocking=True,
        )

    write.assert_awaited_once()
    assert write.await_args.args == ([0x20, 0x41], [0, 3, 6, 9])
    assert isinstance(write.await_args.kwargs["cancel_event"], asyncio.Event)
    assert entry.data[CONF_OCTO_PIN] == "0369"
    assert coordinator._octo_pin == "0369"
    assert controller._pin == "0369"
    command_kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert command_kwargs["cancel_running"] is False
    assert command_kwargs["resource"] == "configuration"


async def test_octo_enroll_pin_from_single_address_side_updates_physical_owner(
    hass: HomeAssistant,
) -> None:
    """The side proxy authenticates, while PIN state belongs to its physical link."""
    await async_register_services(hass)
    entry, inner, controller = await _target(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PAIR_ID: "paired-octo"},
    )
    paired = SingleAddressPairedCoordinator(hass, entry, inner)
    write = AsyncMock()
    controller._write_octo_command = write

    with patch(
        "custom_components.adjustable_bed.services._call_targets",
        return_value=[(paired, SIDE_LEFT)],
    ):
        await hass.services.async_call(
            DOMAIN,
            "octo_enroll_pin",
            {
                "device_id": "octo-device",
                CONF_OCTO_PIN: "0420",
                "octo_pin_confirmation": "0420",
            },
            blocking=True,
        )

    write.assert_awaited_once()
    assert entry.data[CONF_OCTO_PIN] == "0420"
    assert inner._octo_pin == "0420"
    assert controller._pin == "0420"


async def test_octo_enroll_pin_is_not_persisted_when_scheduler_skips_callback(
    hass: HomeAssistant,
) -> None:
    """A normal scheduler return without executing the write is not completion."""
    await async_register_services(hass)
    entry, coordinator, controller = await _target(hass)
    controller._write_octo_command = AsyncMock()
    coordinator.async_execute_controller_command = AsyncMock(return_value=None)

    with (
        patch(
            "custom_components.adjustable_bed.services._call_targets",
            return_value=[(coordinator, SIDE_BOTH)],
        ),
        pytest.raises(ServiceValidationError, match="cancelled before the PIN was sent"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "octo_enroll_pin",
            {
                "device_id": "octo-device",
                CONF_OCTO_PIN: "0369",
                "octo_pin_confirmation": "0369",
            },
            blocking=True,
        )

    controller._write_octo_command.assert_not_awaited()
    assert entry.data[CONF_OCTO_PIN] == ""
    assert coordinator._octo_pin == ""
    assert controller._pin == ""


async def test_octo_memory_action_specs_publish_card_metadata_for_standalone_and_side(
    hass: HomeAssistant,
) -> None:
    """Real Octo slots feed stable memory buckets and bounded held recall."""
    entry, coordinator, controller = await _target(hass)
    controller._memory_count = 9
    controller._features_complete.set()

    recall_spec = next(
        spec for spec in controller.controller_button_specs if spec.key == "preset_memory_9"
    )
    save_spec = next(
        spec for spec in controller.controller_button_specs if spec.key == "program_memory_9"
    )
    assert recall_spec.translation_key == "preset_memory_9"
    assert recall_spec.hold == ControllerHoldSpec(
        control="memory_9", start_delay_ms=100, release_delay_ms=200
    )
    assert save_spec.translation_key == "program_memory_9"
    assert save_spec.hold is None

    standalone = ControllerActionButton(coordinator, recall_spec)
    assert standalone.unique_id.endswith("_preset_memory_9")
    assert standalone.extra_state_attributes == {
        "held_control": "memory_9",
        "hold_start_delay_ms": 100,
        "hold_release_delay_ms": 200,
    }

    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PAIR_ID: "paired-octo"},
    )
    paired = SingleAddressPairedCoordinator(hass, entry, coordinator)
    left = paired.children[SIDE_LEFT]
    side_button = ControllerActionButton(left, recall_spec)
    assert side_button.unique_id.endswith("_preset_memory_9_left")
    assert side_button.translation_key == "preset_memory_9_left"
    assert {
        key: side_button.extra_state_attributes[key] for key in standalone.extra_state_attributes
    } == standalone.extra_state_attributes
    assert side_button.extra_state_attributes["bed_side"] == SIDE_LEFT


async def test_complete_memory_loss_retires_only_the_selected_octo_side_ids(
    hass: HomeAssistant,
) -> None:
    """Every dynamic slot above eight retires while its paired peer stays owned."""
    from homeassistant.helpers import entity_registry as er

    entry, inner, controller = await _target(hass)
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_PAIR_ID: "paired-octo"},
    )
    paired = SingleAddressPairedCoordinator(hass, entry, inner)
    left = paired.children[SIDE_LEFT]
    right = paired.children[SIDE_RIGHT]
    registry = er.async_get(hass)
    for runtime, slot in ((left, 9), (right, 9)):
        for key in (f"preset_memory_{slot}", f"program_memory_{slot}"):
            registry.async_get_or_create(
                "button",
                DOMAIN,
                runtime.entity_unique_id(key),
                config_entry=entry,
                suggested_object_id=f"octo_{runtime.entity_side}_{key}",
            )

    controller._memory_count = 1
    controller._features_complete.set()
    _button_entities_for(hass, left)

    for key in ("preset_memory_9", "program_memory_9"):
        assert registry.async_get_entity_id("button", DOMAIN, left.entity_unique_id(key)) is None
        assert (
            registry.async_get_entity_id("button", DOMAIN, right.entity_unique_id(key)) is not None
        )

    slot_one = next(
        spec for spec in controller.controller_button_specs if spec.key == "preset_memory_1"
    )
    assert slot_one.translation_key == "preset_memory_1"


def test_combined_motor_button_keeps_controller_hold_metadata() -> None:
    """Paired motor buttons expose the same bounded hold contract as each side."""
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.beds.base import (
        ControllerMotorHoldSpec,
        MotorControlSpec,
    )
    from custom_components.adjustable_bed.button import PairedBedCombinedMotorButton

    coordinator = MagicMock(pair_id="paired-octo", device_info={}, connection_mode="concurrent")
    coordinator.children = {
        SIDE_LEFT: SimpleNamespace(bed_type=BED_TYPE_OCTO),
        SIDE_RIGHT: SimpleNamespace(bed_type=BED_TYPE_OCTO),
    }
    hold = ControllerMotorHoldSpec(
        up_control="back_up",
        down_control="back_down",
        start_delay_ms=100,
        release_delay_ms=100,
    )
    spec = MotorControlSpec(
        key="back",
        translation_key="back",
        open_fn=AsyncMock(),
        close_fn=AsyncMock(),
        stop_fn=AsyncMock(),
        hold=hold,
    )

    button = PairedBedCombinedMotorButton(coordinator, spec, "up")

    assert button.extra_state_attributes == {
        "paired_hold_motor": "back",
        "held_control": "back_up",
        "hold_start_delay_ms": 100,
        "hold_release_delay_ms": 100,
    }


async def test_octo_enroll_pin_rejects_multiple_selected_receivers(
    hass: HomeAssistant,
) -> None:
    await async_register_services(hass)
    _entry, coordinator, controller = await _target(hass)
    controller._write_octo_command = AsyncMock()

    with (
        patch(
            "custom_components.adjustable_bed.services._call_targets",
            return_value=[(coordinator, SIDE_BOTH), (coordinator, SIDE_BOTH)],
        ),
        pytest.raises(ServiceValidationError, match="exactly one"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "octo_enroll_pin",
            {
                "device_id": ["octo-device", "second-device"],
                CONF_OCTO_PIN: "1234",
                "octo_pin_confirmation": "1234",
            },
            blocking=True,
        )

    controller._write_octo_command.assert_not_awaited()


async def test_octo_reset_requires_true_confirmation_and_routes_once(
    hass: HomeAssistant,
) -> None:
    await async_register_services(hass)
    _entry, coordinator, controller = await _target(hass)
    controller.reset_defaults = AsyncMock()

    with patch(
        "custom_components.adjustable_bed.services._call_targets",
        return_value=[(coordinator, SIDE_BOTH)],
    ):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN,
                "octo_reset_defaults",
                {"device_id": "octo-device", "confirmed": False},
                blocking=True,
            )
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN,
                "octo_reset_defaults",
                {"device_id": "octo-device"},
                blocking=True,
            )
        await hass.services.async_call(
            DOMAIN,
            "octo_reset_defaults",
            {"device_id": "octo-device", "confirmed": True},
            blocking=True,
        )

    controller.reset_defaults.assert_awaited_once_with()
