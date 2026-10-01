"""All-target preflight and actual own-address app control dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import BED_TYPE_STARCODE_ABM5_4, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_abm5_4 import make_controller


def target(*, active=True, profile=BED_TYPE_STARCODE_ABM5_4):
    ctrl = make_controller()
    ctrl._massage_on = active
    ctrl.hold_control = AsyncMock()
    co = MagicMock(spec=AdjustableBedCoordinator)
    co.name = "App bed"
    co.bed_type = profile
    co.entry = SimpleNamespace(data={})
    co.capability_controller = ctrl

    async def execute(command, **kwargs):
        await command(ctrl)

    co.async_execute_controller_command = AsyncMock(side_effect=execute)
    return co, ctrl


async def test_registered_service_routes_literal_hold_and_seconds(hass):
    await async_register_services(hass)
    co, ctrl = target()
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(co, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "starcode_abm5_4_hold_control",
            {"device_id": "bed", "control": "wave_up", "duration": 1.001},
            blocking=True,
        )
    ctrl.hold_control.assert_awaited_once_with("wave_up", 1001)
    assert co.async_execute_controller_command.await_args.kwargs["cancel_running"]


@pytest.mark.parametrize(
    "control,active,profile",
    [
        ("wave_up", False, BED_TYPE_STARCODE_ABM5_4),
        ("memory_2", True, BED_TYPE_STARCODE_ABM5_4),
        ("head_up+foot_up", True, BED_TYPE_STARCODE_ABM5_4),
        ("head_up", True, "sleepys_box25"),
    ],
)
async def test_later_invalid_profile_action_or_observed_gate_prevents_every_write(
    hass, control, active, profile
):
    await async_register_services(hass)
    first, ctrl = target()
    second, _ = target(active=active, profile=profile)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "starcode_abm5_4_hold_control",
            {"device_id": ["first", "second"], "control": control, "duration": 1},
            blocking=True,
        )
    ctrl.hold_control.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


def test_service_catalog_and_translation_fields_match_actual_controller():
    import json
    from pathlib import Path

    import yaml

    root = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
    metadata = yaml.safe_load((root / "services.yaml").read_text())["starcode_abm5_4_hold_control"]
    assert metadata["fields"]["control"]["selector"]["select"]["options"] == list(
        make_controller().held_control_options
    )
    for filename in ("strings.json", "translations/en.json"):
        translated = json.loads((root / filename).read_text())["services"][
            "starcode_abm5_4_hold_control"
        ]
        assert set(translated["fields"]) == set(metadata["fields"])


@pytest.mark.parametrize("side", ["left", "right", "both"])
async def test_real_two_address_pair_dispatch_preserves_side_and_independent_C(hass, side):
    from custom_components.adjustable_bed.const import CONF_PAIR_ID
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from tests.test_paired_coordinator import RecordingChild

    await async_register_services(hass)
    log = []

    class AppChild(RecordingChild):
        def __init__(self, child_side):
            super().__init__(child_side, log)
            self.bed_type = BED_TYPE_STARCODE_ABM5_4
            self.entry = SimpleNamespace(data={})
            self.controller = make_controller("BOX15" if child_side == "left" else "BOX25_STAR")
            self.controller._coordinator.address = self.address
            self.controller._owner_address = self.address
            self.controller.hold_control = AsyncMock()
            self.capability_controller = self.controller

        async def async_execute_controller_command(
            self,
            command_fn,
            cancel_running=True,
            skip_disconnect=False,
            resource=None,
            resources=None,
        ):
            await command_fn(self.controller)

    children = {key: AppChild(key) for key in ("left", "right")}
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "app-pair"}), children)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, side)], []),
    ) as resolve:
        await hass.services.async_call(
            DOMAIN,
            "starcode_abm5_4_hold_control",
            {"device_id": "pair", "control": "head_up", "duration": 1.001, "side": side},
            blocking=True,
        )
        assert resolve.call_args.args[2] == side
    for key, child in children.items():
        if side in (key, "both"):
            child.controller.hold_control.assert_awaited_once_with("head_up", 1001)
        else:
            child.controller.hold_control.assert_not_awaited()
        assert child.connection_holds == 0
    assert children["left"].controller.command_selector == "BOX15"
    assert children["right"].controller.command_selector == "BOX25_STAR"
