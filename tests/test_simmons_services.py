"""SIMMONS hold and alarm actions: profile preflight before any write."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import BED_TYPE_SIMMONS, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_simmons import make_controller


def target(profile=BED_TYPE_SIMMONS, variant=None):
    controller = make_controller(variant)
    controller.hold_control = AsyncMock()
    controller.configure_simmons_alarm = AsyncMock()
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "SIMMONS"
    coordinator.bed_type = profile
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


def _targets(coordinator):
    return patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    )


@pytest.mark.parametrize(
    ("profile", "variant", "control", "error"),
    [
        (BED_TYPE_SIMMONS, None, "memory", None),
        (BED_TYPE_SIMMONS, None, "inclined_left", "combination"),
        (BED_TYPE_SIMMONS, "simmons_inclined", "zero_g", "combination"),
        ("okin_ffe", None, "memory", "SIMMONS action"),
    ],
)
async def test_hold_control_preflights_profile_and_layout(hass, profile, variant, control, error):
    await async_register_services(hass)
    coordinator, controller = target(profile, variant)
    call = {"device_id": "bed", "control": control, "duration": 5.5}
    with _targets(coordinator):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, "simmons_hold_control", call, blocking=True)
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, "simmons_hold_control", call, blocking=True)
            controller.hold_control.assert_awaited_once_with("memory", 5500)


async def test_set_alarm_passes_the_app_fields(hass):
    await async_register_services(hass)
    coordinator, controller = target()
    with _targets(coordinator):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {
                "device_id": "bed",
                "slot": "2",
                "enabled": True,
                "time": "07:30:00",
                "weekdays": ["monday", "sunday"],
                "mode": "custom_mode",
                "confirm_custom_mode": True,
            },
            blocking=True,
        )
    controller.configure_simmons_alarm.assert_awaited_once_with(
        slot=2,
        enabled=True,
        mode="custom_mode",
        confirm_custom_mode=True,
        hour=7,
        minute=30,
        weekdays=(0, 6),
    )
    assert coordinator.async_execute_controller_command.await_args.kwargs["resource"] == (
        "configuration"
    )


@pytest.mark.parametrize(
    ("variant", "fields", "error"),
    [
        (None, {"mode": "custom_mode"}, "Custom Mode"),
        ("simmons_inclined", {"mode": "anti_snore"}, "Alarm mode"),
        (None, {}, "Alarm mode"),
    ],
)
async def test_set_alarm_rejects_unconfirmed_or_unavailable_modes(hass, variant, fields, error):
    await async_register_services(hass)
    coordinator, controller = target(variant=variant)
    with _targets(coordinator), pytest.raises(ServiceValidationError, match=error):
        await hass.services.async_call(
            DOMAIN,
            "simmons_set_alarm",
            {"device_id": "bed", "slot": 1, "enabled": True, "time": "07:30:00", **fields},
            blocking=True,
        )
    controller.configure_simmons_alarm.assert_not_awaited()


async def test_set_alarm_requires_a_simmons_target(hass):
    await async_register_services(hass)
    coordinator, controller = target("okin_cb24")
    with _targets(coordinator), pytest.raises(ServiceValidationError, match="not a SIMMONS"):
        await hass.services.async_call(
            DOMAIN, "simmons_set_alarm", {"device_id": "bed", "slot": 1, "enabled": False},
            blocking=True,
        )
    controller.configure_simmons_alarm.assert_not_awaited()


def test_service_metadata_matches_every_layout_control():
    import json
    from pathlib import Path

    import yaml

    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    services = yaml.safe_load((root / "services.yaml").read_text())
    options = services["simmons_hold_control"]["fields"]["control"]["selector"]["select"]["options"]
    assert set(options) == {
        *make_controller().held_control_options,
        *make_controller("simmons_inclined").held_control_options,
    }
    for filename in ("strings.json", "translations/en.json"):
        metadata = json.loads((root / filename).read_text())
        for name in ("simmons_hold_control", "simmons_set_alarm"):
            assert set(metadata["services"][name]["fields"]) == set(services[name]["fields"])
        assert {"simmons_alarm_1", "simmons_alarm_2"} <= set(metadata["entity"]["sensor"])
