"""Richmat MH alarm and aroma actions validate every target before writing."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import BED_TYPE_RICHMAT_REVIVE, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.richmat_mh_services import (
    SERVICE_RICHMAT_MH_ALARM,
    SERVICE_RICHMAT_MH_AROMA,
    SERVICE_RICHMAT_MH_WAIST_ALARM,
)
from custom_components.adjustable_bed.services import async_register_services

ROOT = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"


def _target(name: str = "Bed") -> tuple[MagicMock, SimpleNamespace]:
    controller = SimpleNamespace(
        supports_richmat_mh_alarm=True,
        supports_richmat_mh_aroma=True,
        supports_richmat_mh_waist_alarm=True,
        richmat_mh_waist_alarm=AsyncMock(),
        validate_richmat_mh_alarm=MagicMock(),
        richmat_mh_alarm=AsyncMock(),
        richmat_mh_aroma=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = name
    coordinator.bed_type = BED_TYPE_RICHMAT_REVIVE
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.fixture
async def targets(hass: HomeAssistant):
    await async_register_services(hass)
    first, second = _target("First"), _target("Second")
    with patch(
        "custom_components.adjustable_bed.richmat_mh_services._resolve_sided_targets",
        return_value=([(first[0], SIDE_BOTH), (second[0], SIDE_BOTH)], []),
    ):
        yield first, second


async def test_alarm_sends_the_countdown_from_local_time(hass, targets) -> None:
    (coordinator, controller), _ = targets
    now = datetime(2026, 10, 2, 22, 30)
    with patch("custom_components.adjustable_bed.richmat_mh_services.dt_util.now", return_value=now):
        await hass.services.async_call(DOMAIN, SERVICE_RICHMAT_MH_ALARM, {
            "device_id": "bed", "enabled": True, "time": "06:45:00",
            "position": "tv", "massage": ["head_massage"],
        }, blocking=True)
    controller.richmat_mh_alarm.assert_awaited_once_with(
        enabled=True, minutes=495, position="tv", massage=["head_massage"], slot=None
    )
    kwargs = coordinator.async_execute_controller_command.await_args.kwargs
    assert kwargs["cancel_running"] is False and kwargs["resource"] == "configuration"


async def test_alarm_is_validated_on_every_target_before_any_write(hass, targets) -> None:
    (first, first_ctrl), (second, second_ctrl) = targets
    second_ctrl.validate_richmat_mh_alarm.side_effect = ValueError("not on this model")
    with pytest.raises(ServiceValidationError, match="not on this model"):
        await hass.services.async_call(DOMAIN, SERVICE_RICHMAT_MH_ALARM, {
            "device_id": ["a", "b"], "enabled": False, "slot": 2,
        }, blocking=True)
    first_ctrl.validate_richmat_mh_alarm.assert_called_once_with(
        enabled=False, position=None, massage=[], slot=2
    )
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"enabled": True}, "requires a time"),
        ({"enabled": True, "time": "06:45:30", "position": "tv"}, "minute precision"),
    ],
)
async def test_alarm_time_rules(hass, targets, data, message) -> None:
    (coordinator, _), _ = targets
    with pytest.raises(ServiceValidationError, match=message):
        await hass.services.async_call(
            DOMAIN, SERVICE_RICHMAT_MH_ALARM, {"device_id": "bed", **data}, blocking=True
        )
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_aroma_triplet_and_capability_gate(hass, targets) -> None:
    (_, first_ctrl), (second, second_ctrl) = targets
    await hass.services.async_call(DOMAIN, SERVICE_RICHMAT_MH_AROMA, {
        "device_id": "bed", "mode2_startup_minutes": 5, "mode3_startup_minutes": 60,
        "mode3_pause_hours": 1,
    }, blocking=True)
    first_ctrl.richmat_mh_aroma.assert_awaited_once_with(5, 60, 1)
    second_ctrl.richmat_mh_aroma.assert_awaited_once_with(5, 60, 1)
    second_ctrl.supports_richmat_mh_aroma = False
    with pytest.raises(ServiceValidationError, match="does not support"):
        await hass.services.async_call(DOMAIN, SERVICE_RICHMAT_MH_AROMA, {
            "device_id": "bed", "mode2_startup_minutes": 5, "mode3_startup_minutes": 6,
            "mode3_pause_hours": 2,
        }, blocking=True)
    assert second.async_execute_controller_command.await_count == 1


def test_service_descriptions_and_translations_cover_the_schema() -> None:
    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    for name, fields in (
        (SERVICE_RICHMAT_MH_ALARM, {"device_id", "enabled", "time", "position", "massage", "slot", "side"}),
        (SERVICE_RICHMAT_MH_AROMA, {"device_id", "mode2_startup_minutes", "mode3_startup_minutes",
                                    "mode3_pause_hours", "side"}),
        (SERVICE_RICHMAT_MH_WAIST_ALARM, {"device_id", "enabled", "waist_side", "time", "repeat",
                                          "intensity", "side"}),
    ):
        assert set(services[name]["fields"]) == fields
        for filename in ("strings.json", "translations/en.json"):
            strings = yaml.safe_load((ROOT / filename).read_text())
            assert set(strings["services"][name]["fields"]) == fields


async def test_waist_alarm_sends_the_current_local_time(hass, targets) -> None:
    (_, controller), _ = targets
    now = datetime(2026, 10, 2, 23, 59)
    with patch("custom_components.adjustable_bed.richmat_mh_services.dt_util.now", return_value=now):
        await hass.services.async_call(DOMAIN, SERVICE_RICHMAT_MH_WAIST_ALARM, {
            "device_id": "bed", "enabled": True, "waist_side": "both", "time": "06:45:00",
            "intensity": 2,
        }, blocking=True)
    controller.richmat_mh_waist_alarm.assert_awaited_once_with(
        enabled=True, waist_side="both", hour=6, minute=45, now_hour=23, now_minute=59,
        repeat="once", intensity=2,
    )
