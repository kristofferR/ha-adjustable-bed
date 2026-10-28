"""Whole-target alarm validation, app-owned configuration and entity routing."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.cluster033_profiles import APP_LAYOUTS, APP_NAMES, app_profile
from custom_components.adjustable_bed.config_flow import (
    _add_cluster033_schema_fields,
    _normalize_cluster033_data,
)
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.services import async_register_services

from .test_cluster033 import NOW, coordinator, ready


@pytest.fixture
async def services(hass):
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as resolve:
        yield resolve


def target(spec):
    ctrl = SimpleNamespace(
        alarm_table_schedule_spec=spec,
        configure_alarm_table_schedule=AsyncMock(),
        supports_alarm=True,
    )
    coord = MagicMock(spec=AdjustableBedCoordinator)
    coord.name = "App bed"
    coord.capability_controller = ctrl

    async def execute(command, **kwargs):
        await command(ctrl)

    coord.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coord, ctrl


async def test_service_uses_single_local_reference_and_current_configuration_scheduler(
    hass, services
):
    one, c1 = target(app_profile("tempur_curve").alarm)
    two, c2 = target(app_profile("qplus_app").alarm)
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with patch("custom_components.adjustable_bed.services.dt_util.now", return_value=NOW) as now:
        await hass.services.async_call(
            DOMAIN,
            "configure_alarm_schedule",
            {
                "device_id": ["one", "two"],
                "weekly": [{"enabled": True, "weekdays": [0, 6], "wake": True}],
                "one_time": [{"enabled": True, "hour": 12}],
                "dispatch": "weekly",
            },
            blocking=True,
        )
    now.assert_called_once()
    first = c1.configure_alarm_table_schedule.await_args.args[0]
    assert first is c2.configure_alarm_table_schedule.await_args.args[0]
    assert first.reference_time is NOW
    assert first.weekly[0].minute == 0 and first.one_time[0].wake is False
    for coord in (one, two):
        kw = coord.async_execute_controller_command.await_args.kwargs
        assert kw["cancel_running"] is False
        assert kw["resource"] == "configuration"


@pytest.mark.parametrize("bad_spec", [None, app_profile("serta_mp_remote").alarm])
async def test_supports_alarm_does_not_grant_table_capability_or_open_link(
    hass, services, bad_spec
):
    one, c1 = target(app_profile("tempur_curve").alarm)
    two, _ = target(bad_spec)
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="contract"):
        await hass.services.async_call(
            DOMAIN,
            "configure_alarm_schedule",
            {"device_id": ["one", "two"], "weekly": [], "one_time": [], "dispatch": "both"},
            blocking=True,
        )
    c1.configure_alarm_table_schedule.assert_not_awaited()
    one.async_execute_controller_command.assert_not_awaited()
    two.async_ensure_connected.assert_not_called()


async def test_second_target_validation_aborts_first_before_any_checksum(hass, services):
    one, c1 = target(app_profile("tempur_curve").alarm)
    spec = MagicMock(wraps=app_profile("qplus_app").alarm)
    spec.validate.side_effect = ValueError("second target refused")
    two, c2 = target(spec)
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="second target"):
        await hass.services.async_call(
            DOMAIN,
            "configure_alarm_schedule",
            {"device_id": ["one", "two"], "weekly": [], "one_time": [], "dispatch": "weekly"},
            blocking=True,
        )
    c1.configure_alarm_table_schedule.assert_not_awaited()
    c2.configure_alarm_table_schedule.assert_not_awaited()
    spec.encode.assert_not_called()


@pytest.mark.parametrize(
    "weekly,one_time",
    [
        ([{"enabled": True, "weekdays": [0, 0]}], []),
        ([{"enabled": True, "weekdays": []}], []),
        ([], [{"enabled": True, "hour": 9}]),
        ([], [{"enabled": True, "hour": 10}]),
        ([{"enabled": False, "hour": 24}], []),
    ],
)
async def test_service_rejects_invalid_complete_tables_before_scheduling(
    hass, services, weekly, one_time
):
    one, ctrl = target(app_profile("tempur_curve").alarm)
    services.return_value = ([(one, SIDE_BOTH)], [])
    with (
        patch("custom_components.adjustable_bed.services.dt_util.now", return_value=NOW),
        pytest.raises((ServiceValidationError, __import__("voluptuous").Invalid)),
    ):
        await hass.services.async_call(
            DOMAIN,
            "configure_alarm_schedule",
            {"device_id": "one", "weekly": weekly, "one_time": one_time, "dispatch": "weekly"},
            blocking=True,
        )
    ctrl.configure_alarm_table_schedule.assert_not_awaited()
    one.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("app,layouts", APP_LAYOUTS.items())
def test_findable_app_and_side_owned_options(app, layouts):
    assert any(
        option["value"] == app and APP_NAMES[app] in option["label"]
        for option in get_bed_type_options()
    )
    assert "product_type" in per_side_profile(app, None).keys
    assert {
        "motor_count",
        "has_massage",
        "disable_angle_sensing",
        "protocol_variant",
        "motor_pulse_delay_ms",
    } <= hidden_generic_fields(app, None)
    for layout in layouts:
        data = {"bed_type": app, "product_type": layout}
        _normalize_cluster033_data(data)
        assert data["motor_count"] == 2
        assert data["disable_angle_sensing"] is (app != "serta_mp_remote")
        schema = {}
        _add_cluster033_schema_fields(schema, data)
        assert "product_type" in {marker.schema for marker in schema}
    with pytest.raises(ValueError):
        _normalize_cluster033_data({"bed_type": app, "product_type": "Not a layout"})


@pytest.mark.parametrize(
    "app,layout", [(app, layout) for app, layouts in APP_LAYOUTS.items() for layout in layouts]
)
async def test_factory_builds_exact_app_profile_lazily(hass, app, layout):
    coord = coordinator()
    coord.hass = hass
    coord.entry.data = {"bed_type": app, "product_type": layout}
    ctrl = await create_controller(coord, app, protocol_variant="side_a", client=None)
    assert ctrl.profile.app == APP_NAMES[app]
    assert ctrl.profile.layout == layout
    assert ctrl.requires_notification_channel
    assert not ctrl.supports_single_address_pairing
    assert ctrl.supports_memory_presets is (app == "serta_mp_remote")


async def test_action_button_uses_current_controller_and_existing_scheduler():
    ctrl, coord = await ready("qplus_app", "MX")
    old, _ = await ready("qplus_app", "MX")
    spec = next(s for s in old.controller_button_specs if s.key == "mx_memory1")
    coord.entity_unique_id.side_effect = lambda key: "bed_" + key
    coord.entity_side = None
    coord.device_info = {}

    async def dispatch(command, **kwargs):
        await command(ctrl)

    coord.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    button = ControllerActionButton(coord, spec)
    await button.async_press()
    assert coord.async_execute_controller_command.await_args.kwargs["cancel_running"] is True
    assert button.translation_key == "remote_action"
    assert button.unique_id == "bed_mx_memory1"


def test_service_entity_strings_and_yaml_are_consistent():
    import yaml

    root = Path(__file__).parents[1] / "custom_components/adjustable_bed"
    strings = json.loads((root / "strings.json").read_text())
    assert strings == json.loads((root / "translations/en.json").read_text())
    service = yaml.safe_load((root / "services.yaml").read_text())["configure_alarm_schedule"]
    assert set(service["fields"]) == set(strings["services"]["configure_alarm_schedule"]["fields"])
    getter = BedController.alarm_table_schedule_spec.fget
    assert getter is not None
    assert getter(MagicMock()) is None
