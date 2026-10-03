"""Generic hold_control, rename, sync_clock and goto_preset duration actions."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_SVANE,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services

ROOT = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"


def target(bed_type: str = BED_TYPE_KEESON, name: str = "Bed", **capabilities: object):
    """A coordinator whose capability controller declares only ``capabilities``."""
    controller = SimpleNamespace(
        held_control_options=(),
        validate_hold_control=MagicMock(),
        hold_control=AsyncMock(),
        supports_device_rename=False,
        disconnects_after_rename=False,
        validate_device_rename=MagicMock(),
        rename_device=AsyncMock(),
        supports_clock_sync=False,
        sync_clock=AsyncMock(),
        supports_memory_presets=True,
        memory_slot_count=4,
        supports_held_memory_recall=False,
        validate_memory_recall=MagicMock(),
        preset_memory=AsyncMock(),
        recall_memory=AsyncMock(),
    )
    vars(controller).update(capabilities)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = name
    coordinator.bed_type = bed_type
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.fixture
async def resolve(hass: HomeAssistant):
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as patched:
        yield patched


def select(resolve, *targets) -> None:
    resolve.return_value = ([(coordinator, SIDE_BOTH) for coordinator, _ in targets], [])


async def test_service_text_lives_only_in_translations() -> None:
    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    strings = json.loads((ROOT / "strings.json").read_text())
    assert strings == json.loads((ROOT / "translations" / "en.json").read_text())
    translated = strings["services"]
    assert set(translated) == set(services)
    for name, spec in services.items():
        assert not {"name", "description"} & set(spec), name
        assert translated[name]["name"] and translated[name]["description"], name
        fields = spec.get("fields") or {}
        assert set(translated[name].get("fields", {})) == set(fields), name
        for field, field_spec in fields.items():
            assert not {"name", "description"} & set(field_spec), (name, field)
            assert translated[name]["fields"][field]["name"], (name, field)


async def test_every_registered_action_is_described(hass: HomeAssistant) -> None:
    await async_register_services(hass)
    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    assert set(hass.services.async_services()[DOMAIN]) == set(services)


async def test_hold_control_runs_a_declared_control(hass: HomeAssistant, resolve) -> None:
    coordinator, controller = target(held_control_options=("head_up", "flat"))
    select(resolve, (coordinator, controller))
    await hass.services.async_call(
        DOMAIN, "hold_control",
        {"device_id": "bed", "control": "flat", "duration": 1.25}, blocking=True,
    )
    controller.validate_hold_control.assert_called_once_with("flat", 1250)
    controller.hold_control.assert_awaited_once_with("flat", 1250)
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


async def test_hold_control_lists_valid_controls_before_any_write(
    hass: HomeAssistant, resolve
) -> None:
    first, first_controller = target(held_control_options=("head_up", "flat"))
    second, second_controller = target(name="Other", held_control_options=("head_up",))
    select(resolve, (first, first_controller), (second, second_controller))
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "hold_control",
            {"device_id": ["bed", "other"], "control": "flat", "duration": 1}, blocking=True,
        )
    assert raised.value.translation_key == "held_control_not_supported"
    assert raised.value.translation_placeholders == {
        "device_name": "Other", "control": "flat", "valid_controls": "head_up",
    }
    first_controller.hold_control.assert_not_awaited()


async def test_hold_control_rejects_a_bed_without_held_controls(
    hass: HomeAssistant, resolve
) -> None:
    select(resolve, target())
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "hold_control",
            {"device_id": "bed", "control": "flat", "duration": 1}, blocking=True,
        )
    assert raised.value.translation_key == "held_controls_not_supported"


async def test_hold_control_profile_constraint_becomes_validation_error(
    hass: HomeAssistant, resolve
) -> None:
    coordinator, controller = target(
        held_control_options=("wave_up",),
        validate_hold_control=MagicMock(side_effect=ValueError("needs active massage")),
    )
    select(resolve, (coordinator, controller))
    with pytest.raises(ServiceValidationError, match="needs active massage"):
        await hass.services.async_call(
            DOMAIN, "hold_control",
            {"device_id": "bed", "control": "wave_up", "duration": 1}, blocking=True,
        )
    controller.hold_control.assert_not_awaited()


async def test_hold_control_cannot_mix_live_session_profiles(
    hass: HomeAssistant, resolve
) -> None:
    select(
        resolve,
        target(BED_TYPE_SVANE, held_control_options=("head_up",)),
        target(held_control_options=("head_up",)),
    )
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "hold_control",
            {"device_id": ["a", "b"], "control": "head_up", "duration": 1}, blocking=True,
        )
    assert raised.value.translation_key == "mixed_profile_targets"


async def test_released_leggett_alias_keeps_its_control_list(
    hass: HomeAssistant, resolve
) -> None:
    coordinator, controller = target(held_control_options=("flat", "head_up"))
    select(resolve, (coordinator, controller))
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "leggett_hold_control",
            {"device_id": "bed", "control": "head_up", "duration": 1}, blocking=True,
        )
    await hass.services.async_call(
        DOMAIN, "leggett_hold_control",
        {"device_id": "bed", "control": "flat", "duration": 0.5}, blocking=True,
    )
    controller.hold_control.assert_awaited_once_with("flat", 500)


async def test_rename_validates_every_target_before_writing(
    hass: HomeAssistant, resolve
) -> None:
    first, first_controller = target(supports_device_rename=True)
    second, second_controller = target(
        name="Other",
        supports_device_rename=True,
        validate_device_rename=MagicMock(side_effect=ValueError("too long")),
    )
    select(resolve, (first, first_controller), (second, second_controller))
    with pytest.raises(ServiceValidationError, match="too long"):
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": ["a", "b"], "name": "Bed"}, blocking=True,
        )
    first_controller.rename_device.assert_not_awaited()


async def test_rename_rejects_unsupported_bed(hass: HomeAssistant, resolve) -> None:
    select(resolve, target())
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": "bed", "name": "Bed"}, blocking=True,
        )
    assert raised.value.translation_key == "device_rename_not_supported"


@pytest.mark.parametrize(("service", "disconnects"), [("rename", False), ("linak_rename", True)])
async def test_rename_disconnects_only_where_the_controller_asks(
    hass: HomeAssistant, resolve, service, disconnects
) -> None:
    coordinator, controller = target(
        BED_TYPE_LINAK, supports_device_rename=True, disconnects_after_rename=disconnects
    )
    select(resolve, (coordinator, controller))
    await hass.services.async_call(
        DOMAIN, service, {"device_id": "bed", "name": "Bedroom"}, blocking=True,
    )
    controller.rename_device.assert_awaited_once_with("Bedroom")
    assert coordinator.async_execute_controller_command.await_args.kwargs["resource"] == (
        "configuration"
    )
    assert coordinator.async_disconnect.await_count == int(disconnects)


async def test_released_jiecang_alias_keeps_its_name_rule(hass: HomeAssistant, resolve) -> None:
    select(resolve, target(supports_device_rename=True))
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "jiecang_rename", {"device_id": "bed", "name": "Bed room"}, blocking=True,
        )


@pytest.mark.parametrize("service", ["sync_clock", "malouf_sync_clock"])
async def test_sync_clock_writes_through_configuration_lane(
    hass: HomeAssistant, resolve, service
) -> None:
    coordinator, controller = target(supports_clock_sync=True)
    select(resolve, (coordinator, controller))
    await hass.services.async_call(DOMAIN, service, {"device_id": "bed"}, blocking=True)
    controller.sync_clock.assert_awaited_once()
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["resource"] == "configuration" and kwargs["cancel_running"] is False


async def test_sync_clock_rejects_unsupported_bed(hass: HomeAssistant, resolve) -> None:
    select(resolve, target())
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(DOMAIN, "sync_clock", {"device_id": "bed"}, blocking=True)
    assert raised.value.translation_key == "clock_sync_not_supported"


async def test_goto_preset_duration_uses_held_recall(hass: HomeAssistant, resolve) -> None:
    coordinator, controller = target(supports_held_memory_recall=True)
    select(resolve, (coordinator, controller))
    await hass.services.async_call(
        DOMAIN, "goto_preset", {"device_id": "bed", "preset": 2, "duration": 1.5}, blocking=True,
    )
    controller.recall_memory.assert_awaited_once_with(2, hold_ms=1500)
    controller.preset_memory.assert_not_awaited()


async def test_goto_preset_duration_rejected_where_unsupported(
    hass: HomeAssistant, resolve
) -> None:
    coordinator, controller = target()
    select(resolve, (coordinator, controller))
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1, "duration": 1}, blocking=True,
        )
    assert raised.value.translation_key == "preset_duration_not_supported"
    controller.recall_memory.assert_not_awaited()
    await hass.services.async_call(
        DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1}, blocking=True,
    )
    controller.preset_memory.assert_awaited_once_with(1)
