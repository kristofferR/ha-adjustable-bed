"""Real Serenity catalog, all-target preflight and paired service dispatch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.const import (
    BED_TYPE_SERENITY,
    CONF_PAIR_ID,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_paired_coordinator import RecordingChild
from tests.test_serenity import make_controller, written


def target(profile=BED_TYPE_SERENITY, *, record_only=True):
    controller = make_controller()
    if record_only:
        controller.hold_control = AsyncMock()
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Serenity"
    coordinator.bed_type = profile
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller


@pytest.mark.parametrize(
    "profile,control,error",
    [
        (BED_TYPE_SERENITY, "save_memory_1", None),
        (BED_TYPE_SERENITY, "head_up+foot_up", "does not support held control"),
    ],
)
async def test_serenity_hold_preflights_profile_and_literal_action(hass, profile, control, error):
    await async_register_services(hass)
    coordinator, controller = target(profile)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(
                    DOMAIN,
                    "hold_control",
                    {"device_id": "bed", "control": control, "duration": 1.001},
                    blocking=True,
                )
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": "bed", "control": control, "duration": 1.001},
                blocking=True,
            )
            controller.hold_control.assert_awaited_once_with("save_memory_1", 1001)
            assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


async def test_service_to_real_controller_emits_artifact_save_and_release(hass):
    await async_register_services(hass)
    coordinator, controller = target(record_only=False)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "save_memory_1", "duration": 0.1},
            blocking=True,
        )
    assert (
        written(controller)
        == ["0c02080100000000000000000000"] + ["0c02000000000000000000000000"] * 2
    )
    assert controller.protocol_diagnostics["save_pending_code"] == 4


async def test_later_incompatible_target_rejects_before_any_write(hass):
    await async_register_services(hass)
    first, controller = target()
    second, _ = target("okin_cst")
    second.capability_controller = SimpleNamespace(held_control_options=())
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError, match="has no held controls"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": ["first", "second"], "control": "head_up", "duration": 1},
            blocking=True,
        )
    controller.hold_control.assert_not_awaited()
    first.async_execute_controller_command.assert_not_awaited()
    second.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("side", [SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH])
async def test_real_pair_preserves_requested_side_and_literal_action(hass, side):
    await async_register_services(hass)
    log = []

    class SerenityChild(RecordingChild):
        def __init__(self, child_side):
            super().__init__(child_side, log)
            self.bed_type = BED_TYPE_SERENITY
            self.entry = SimpleNamespace(data={})
            _, self.controller = target()
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

    children = {key: SerenityChild(key) for key in (SIDE_LEFT, SIDE_RIGHT)}
    pair = PairedBedCoordinator(
        hass, SimpleNamespace(data={CONF_PAIR_ID: "serenity-pair"}), children
    )
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, side)], []),
    ) as resolve:
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "pair", "control": "selector_4_down", "duration": 1.001, "side": side},
            blocking=True,
        )
        assert resolve.call_args.args[2] == side
    for key, child in children.items():
        if side in (key, SIDE_BOTH):
            child.controller.hold_control.assert_awaited_once_with("selector_4_down", 1001)
        else:
            child.controller.hold_control.assert_not_awaited()
        assert child.connection_holds == 0


async def test_cancelled_dispatch_restores_later_preflighted_target_idle_timer(hass):
    await async_register_services(hass)
    first, _ = target()
    second, _ = target()
    for coordinator in (first, second):
        controller = coordinator.capability_controller
        coordinator.controller = None
        coordinator.capability_controller = None
        coordinator.is_connected = False

        async def connect(*, reset_timer, target=coordinator, connected_controller=controller):
            target.controller = connected_controller
            target.is_connected = True
            return True

        coordinator.async_ensure_connected = AsyncMock(side_effect=connect)
    running = asyncio.Event()

    async def execute_first(*args, **kwargs):
        running.set()
        await asyncio.Event().wait()

    first.async_execute_controller_command = AsyncMock(side_effect=execute_first)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
    ):
        call = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["first", "second"], "control": "head_up", "duration": 1},
                blocking=True,
            )
        )
        await running.wait()
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    second.async_execute_controller_command.assert_not_awaited()
    for coordinator in (first, second):
        assert [args.kwargs for args in coordinator.async_ensure_connected.await_args_list] == [
            {"reset_timer": False},
            {"reset_timer": True},
        ]


