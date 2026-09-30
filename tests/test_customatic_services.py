"""Customatic action preflight, exact selection and paired target routing."""

from itertools import combinations, product
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_LINAK,
    DOMAIN,
    SIDE_BOTH,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import (
    CUSTOMATIC_MEMORY_ACTIONS,
    SERVICE_CUSTOMATIC_HOLD_MEMORY,
    SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY,
    async_register_services,
)

MEMORY_SELECTIONS = [list(selection) for size in range(1, 6)
                     for selection in combinations(CUSTOMATIC_MEMORY_ACTIONS, size)]
MOTOR_SELECTIONS = [dict(zip(("back", "legs", "lumbar"), directions, strict=True))
                    for directions in product((None, "up", "down"), repeat=3)
                    if any(directions)]
MOTOR_SELECTIONS = [{axis: direction for axis, direction in selection.items()
                     if direction is not None} for selection in MOTOR_SELECTIONS]


def target(profile=BED_TYPE_CUSTOMATIC_REMEDY):
    controller = SimpleNamespace(
        supports_held_control=True,
        held_control_options=tuple("+".join(selection) for selection in MEMORY_SELECTIONS) + tuple(
            "+".join(f"{axis}_{direction}" for axis, direction in selection.items())
            for selection in MOTOR_SELECTIONS
        ),
        hold_control=AsyncMock(),
    )
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Customatic bed"
    coordinator.bed_type = profile
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.fixture
async def service_target(hass: HomeAssistant):
    await async_register_services(hass)
    coordinator, controller = target()
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])) as resolve:
        yield coordinator, controller, resolve


@pytest.mark.parametrize("actions", MEMORY_SELECTIONS)
async def test_all_31_memory_subsets_dispatch_canonical_mask(
    hass: HomeAssistant, service_target, actions
):
    coordinator, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN, SERVICE_CUSTOMATIC_HOLD_MEMORY,
        {"device_id": "bed", "actions": list(reversed(actions)), "duration": 1.001},
        blocking=True,
    )
    controller.hold_control.assert_awaited_once_with("+".join(actions), 1001)
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


@pytest.mark.parametrize("actions", MOTOR_SELECTIONS)
async def test_all_26_safe_remedy_motor_subsets_dispatch(
    hass: HomeAssistant, service_target, actions
):
    _, controller, _ = service_target
    await hass.services.async_call(
        DOMAIN, SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY,
        {"device_id": "bed", "actions": dict(reversed(list(actions.items()))), "duration": 0.12},
        blocking=True,
    )
    controller.hold_control.assert_awaited_once_with(
        "+".join(f"{axis}_{direction}" for axis, direction in actions.items()), 120
    )


@pytest.mark.parametrize(("service", "data"), [
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": []}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["program", "program"]}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["unknown"]}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": "zg"}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": [True]}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["zg"], "duration": True}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["zg"], "duration": 0.099}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["zg"], "duration": 60.001}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["zg"], "duration": 1.0001}),
    (SERVICE_CUSTOMATIC_HOLD_MEMORY, {"actions": ["zg"], "duration": float("nan")}),
    (SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY, {"actions": {}}),
    (SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY, {"actions": {"back": ["up", "down"]}}),
    (SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY, {"actions": {"back": "both"}}),
    (SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY, {"actions": {"head": "up"}}),
    (SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY, {"actions": ["back_up"]}),
])
async def test_invalid_schema_stops_before_resolving_targets(
    hass: HomeAssistant, service_target, service, data
):
    _, _, resolve = service_target
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, service, {"device_id": "bed", "duration": 1, **data}, blocking=True
        )
    resolve.assert_not_called()


@pytest.mark.parametrize("profile", [BED_TYPE_CUSTOMATIC_JEROMES, BED_TYPE_LINAK])
async def test_memory_rejects_incompatible_later_target_before_first_write(
    hass: HomeAssistant, service_target, profile
):
    coordinator, controller, resolve = service_target
    other, other_controller = target(profile)
    resolve.return_value = ([(coordinator, SIDE_BOTH), (other, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="does not support this Customatic"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CUSTOMATIC_HOLD_MEMORY,
            {"device_id": ["bed", "other"], "actions": ["zg"], "duration": 1}, blocking=True,
        )
    controller.hold_control.assert_not_awaited()
    other_controller.hold_control.assert_not_awaited()
    coordinator.async_execute_controller_command.assert_not_awaited()


async def test_lumbar_preflight_rejects_two_motor_profile_before_any_write(
    hass: HomeAssistant, service_target
):
    coordinator, controller, resolve = service_target
    other, other_controller = target(BED_TYPE_CUSTOMATIC_CLARITY)
    other_controller.held_control_options = ("back_up+legs_down",)
    resolve.return_value = ([(coordinator, SIDE_BOTH), (other, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="does not support combination"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CUSTOMATIC_MOVE_SIMULTANEOUSLY,
            {"device_id": ["bed", "other"], "actions": {"lumbar": "up"}, "duration": 1},
            blocking=True,
        )
    controller.hold_control.assert_not_awaited()
    other_controller.hold_control.assert_not_awaited()


async def test_each_valid_physical_target_receives_same_mask(
    hass: HomeAssistant, service_target
):
    coordinator, controller, resolve = service_target
    other, other_controller = target(BED_TYPE_CUSTOMATIC_CLARITY)
    resolve.return_value = ([(coordinator, SIDE_BOTH), (other, SIDE_BOTH)], [])
    await hass.services.async_call(
        DOMAIN, SERVICE_CUSTOMATIC_HOLD_MEMORY,
        {"device_id": ["bed", "other"], "actions": ["program", "zg"], "duration": 2.7},
        blocking=True,
    )
    controller.hold_control.assert_awaited_once_with("zg+program", 2700)
    other_controller.hold_control.assert_awaited_once_with("zg+program", 2700)


async def test_real_pair_preflights_later_side_before_either_command(
    hass: HomeAssistant, service_target
):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID, SIDE_LEFT, SIDE_RIGHT
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_paired_coordinator import RecordingChild

    _, controller, resolve = service_target
    log = []
    left = RecordingChild(SIDE_LEFT, log)
    right = RecordingChild(SIDE_RIGHT, log)
    for child, profile in [(left, BED_TYPE_CUSTOMATIC_REMEDY), (right, BED_TYPE_CUSTOMATIC_JEROMES)]:
        child.bed_type = profile
        child.entry = SimpleNamespace(data={})
        child.capability_controller = controller
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "customatic-pair"}),
                                {SIDE_LEFT: left, SIDE_RIGHT: right})
    resolve.return_value = ([(pair, SIDE_BOTH)], [])
    with pytest.raises(ServiceValidationError, match="does not support this Customatic"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CUSTOMATIC_HOLD_MEMORY,
            {"device_id": "pair", "actions": ["zg"], "duration": 1}, blocking=True,
        )
    assert not any(action == "command" for _, action in log)
    controller.hold_control.assert_not_awaited()


@pytest.mark.parametrize("failing_side", [None, "right"])
async def test_real_pair_fans_out_and_stops_both_after_partial_failure(
    hass: HomeAssistant, service_target, failing_side
):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID, SIDE_LEFT, SIDE_RIGHT
    from custom_components.adjustable_bed.paired_coordinator import (
        PairedBedCoordinator,
        PairedSideError,
    )
    from tests.test_paired_coordinator import RecordingChild

    _, _, resolve = service_target
    log = []

    class CustomaticChild(RecordingChild):
        def __init__(self, side):
            super().__init__(side, log)
            self.bed_type = BED_TYPE_CUSTOMATIC_CLARITY
            self.entry = SimpleNamespace(data={})
            _, self.controller = target(BED_TYPE_CUSTOMATIC_CLARITY)
            self.capability_controller = self.controller

        async def async_execute_controller_command(
            self, command_fn, cancel_running=True, skip_disconnect=False,
            resource=None, resources=None,
        ):
            self.log.append((self.side, "command"))
            await command_fn(self.controller)
            if self.side == failing_side:
                raise RuntimeError("write failed")

    left, right = CustomaticChild(SIDE_LEFT), CustomaticChild(SIDE_RIGHT)
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "customatic-pair"}),
                                {SIDE_LEFT: left, SIDE_RIGHT: right})
    resolve.return_value = ([(pair, SIDE_BOTH)], [])

    async def call():
        await hass.services.async_call(
            DOMAIN, SERVICE_CUSTOMATIC_HOLD_MEMORY,
            {"device_id": "pair", "actions": ["zg", "program"], "duration": 2.7}, blocking=True,
        )

    if failing_side:
        with pytest.raises(PairedSideError):
            await call()
        assert (SIDE_LEFT, "stop") in log
        assert (SIDE_RIGHT, "stop") in log
    else:
        await call()
    for child in (left, right):
        child.controller.hold_control.assert_awaited_once_with("zg+program", 2700)
        assert child.connection_holds == 0
