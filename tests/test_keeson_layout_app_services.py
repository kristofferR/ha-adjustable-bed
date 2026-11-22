"""Whole-target alarm validation, app-owned configuration and entity routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmCapability
from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.keeson.layout_app import AppController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.profiles.keeson import APP_LAYOUTS, APP_NAMES, app_profile
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES

from .test_keeson_layout_app import NOW, coordinator, ready


@pytest.fixture
async def services(hass):
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets") as resolve:
        yield resolve


def target(spec):
    ctrl = MagicMock(
        spec=AppController,
        alarm_table_schedule_spec=spec,
        configure_alarm_table_schedule=AsyncMock(),
        alarm_capability=None if spec is None else AlarmCapability(weekdays=True, massage=True),
    )
    # The controller's own request-to-table mapping, on a mock bed.
    ctrl._alarm_schedule = AppController._alarm_schedule
    for name in ("validate_alarm", "configure_alarm"):
        setattr(ctrl, name, getattr(AppController, name).__get__(ctrl))
    coord = MagicMock(spec=AdjustableBedCoordinator)
    coord.name = "App bed"
    coord.controller_side = None
    coord.capability_controller = ctrl

    async def execute(command, **kwargs):
        await command(ctrl)

    coord.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coord, ctrl


async def test_set_alarm_uses_one_local_reference_and_the_configuration_lane(hass, services):
    one, c1 = target(app_profile("tempur_curve").alarm)
    two, c2 = target(app_profile("qplus_app").alarm)
    one.operation_identity, two.operation_identity = 1, 2
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with patch("custom_components.adjustable_bed.services.dt_util.now", return_value=NOW) as now:
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {
                "device_id": ["one", "two"],
                "enabled": True,
                "time": "07:15:00",
                "weekdays": ["monday", "sunday"],
                "massage": True,
            },
            blocking=True,
        )
    now.assert_called_once()
    first = c1.configure_alarm_table_schedule.await_args.args[0]
    assert first == c2.configure_alarm_table_schedule.await_args.args[0]
    assert first.reference_time is NOW and first.dispatch == "weekly" and not first.one_time
    assert first.weekly[0].weekdays == (0, 6) and first.weekly[0].wake is True
    for coord in (one, two):
        kw = coord.async_execute_controller_command.await_args.kwargs
        assert kw["cancel_running"] is False
        assert kw["resource"] == "configuration"


async def test_set_alarm_off_clears_both_tables(hass, services):
    one, ctrl = target(app_profile("tempur_curve").alarm)
    services.return_value = ([(one, SIDE_BOTH)], [])
    await hass.services.async_call(
        DOMAIN, "set_alarm", {"device_id": "one", "enabled": False}, blocking=True
    )
    schedule = ctrl.configure_alarm_table_schedule.await_args.args[0]
    assert (schedule.weekly, schedule.one_time, schedule.dispatch) == ((), (), "both")


@pytest.mark.parametrize("bad_spec", [None, app_profile("serta_mp_remote").alarm])
async def test_profile_without_alarm_tables_blocks_every_target(hass, services, bad_spec):
    one, c1 = target(app_profile("tempur_curve").alarm)
    two, _ = target(bad_spec)
    one.operation_identity, two.operation_identity = 1, 2
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="has no alarm"):
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": ["one", "two"], "enabled": False}, blocking=True
        )
    c1.configure_alarm_table_schedule.assert_not_awaited()
    one.async_execute_controller_command.assert_not_awaited()


async def test_second_target_validation_aborts_first_before_any_checksum(hass, services):
    one, c1 = target(app_profile("tempur_curve").alarm)
    spec = MagicMock(wraps=app_profile("qplus_app").alarm)
    spec.validate.side_effect = ValueError("second target refused")
    two, c2 = target(spec)
    one.operation_identity, two.operation_identity = 1, 2
    services.return_value = ([(one, SIDE_BOTH), (two, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="second target"):
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": ["one", "two"], "enabled": False}, blocking=True
        )
    c1.configure_alarm_table_schedule.assert_not_awaited()
    c2.configure_alarm_table_schedule.assert_not_awaited()
    spec.encode.assert_not_called()


async def test_one_time_alarm_must_be_later_today(hass, services):
    one, ctrl = target(app_profile("tempur_curve").alarm)
    services.return_value = ([(one, SIDE_BOTH)], [])
    earlier = f"{NOW.hour - 1:02d}:00:00"
    with (
        patch("custom_components.adjustable_bed.services.dt_util.now", return_value=NOW),
        pytest.raises(ServiceValidationError, match="later today"),
    ):
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": "one", "enabled": True, "time": earlier}, blocking=True
        )
    ctrl.configure_alarm_table_schedule.assert_not_awaited()


@pytest.mark.parametrize("app,layouts", APP_LAYOUTS.items())
def test_findable_app_and_side_owned_options(app, layouts):
    assert any(
        option["value"] == app and APP_NAMES[app] in option["label"]
        for option in get_bed_type_options()
    )
    assert "product_type" in per_side_profile(app, None).keys
    # Q-Plus's P1 beds report positions, so reading them is its user's choice.
    assert {
        "motor_count",
        "has_massage",
        *(("disable_angle_sensing",) if app != "qplus_app" else ()),
        "protocol_variant",
        "motor_pulse_delay_ms",
    } <= hidden_generic_fields(app, None)
    profile = SETUP_PROFILES[app]
    assert profile.questions[0].key == "product_type"
    assert profile.validate is not None
    for layout in layouts:
        data = {"bed_type": app, "product_type": layout}
        assert profile.validate(data) == {}
        settled = profile.settled(data)
        assert settled["motor_count"] == 2
        if app == "qplus_app":
            # Only the MX remote reports no position, so only it is saved unread.
            expected = True if layout == "MX" else None
        else:
            expected = app != "serta_mp_remote"
        assert settled.get("disable_angle_sensing") is expected
    assert profile.validate({"bed_type": app, "product_type": "Not a layout"}) == {
        "base": "keeson_app_layout"
    }


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
    # Only Q-Plus P1 frames carry a selector for the two halves of one receiver.
    assert ctrl.supports_single_address_pairing is (app == "qplus_app" and layout != "MX")
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
    assert button.translation_key == "catalog_preset"
    assert button.unique_id == "bed_mx_memory1"


def test_alarm_tables_stay_off_the_base_controller():
    assert not hasattr(BedController, "alarm_table_schedule_spec")
