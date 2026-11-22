"""Public service admission, real controller writes, and real paired dispatch."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.service import async_get_all_descriptions

from custom_components.adjustable_bed.const import (
    CONF_PAIR_ID,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_casper_base import frames
from tests.test_paired_coordinator import RecordingChild
from tests.test_richmat_legacy import clock as clock
from tests.test_richmat_legacy import make


def target(app="sleep_evolution", code="GV"):
    controller, owner = make(app, code)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Fixed ASCII bed"
    coordinator.bed_type = app
    coordinator.entry = owner.entry
    coordinator.controller_side = None
    coordinator.capability_controller = controller
    coordinator.stop_epoch = 0
    coordinator.pairlink_peripheral = False

    async def execute(command, **kwargs):
        expected = kwargs.get("expected_stop_epoch")
        if expected is None or expected == coordinator.stop_epoch:
            await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator, controller, owner


@pytest.mark.parametrize("app,expected", [("sleep_evolution", "33"), ("wsilver_legacy", "24")])
async def test_public_service_uses_selected_app_default(clock, hass, app, expected):
    await async_register_services(hass)
    coord, ctrl, owner = target(app)
    await ctrl.start_notify()
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coord, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "richmat_legacy",
            {"device_id": "bed", "control": "btn_posup", "duration_ms": 1},
            blocking=True,
        )
    assert frames(owner) == ["6d", expected, "6e"]
    assert coord.async_execute_controller_command.await_args.kwargs["cancel_running"] is True


async def test_whole_batch_invalid_profile_has_no_writes(clock, hass):
    await async_register_services(hass)
    first, a, owner_a = target(code="A1")
    second, b, owner_b = target(code="B2")
    await a.start_notify()
    await b.start_notify()
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "richmat_legacy",
            {"device_id": ["a", "b"], "control": "h26_lounge", "operation": "program"},
            blocking=True,
        )
    assert frames(owner_a) == frames(owner_b) == []
    first.async_execute_controller_command.assert_not_awaited()


async def test_stop_during_lazy_import_fences_every_target(clock, hass):
    from custom_components.adjustable_bed.beds.richmat_legacy import services as svc

    await async_register_services(hass)
    first, a, owner_a = target()
    second, b, owner_b = target()
    await a.start_notify()
    await b.start_notify()

    async def importing(*args):
        first.stop_epoch = second.stop_epoch = 1

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(first, SIDE_BOTH), (second, SIDE_BOTH)], []),
        ),
        patch.object(svc, "async_import_modules", importing),
    ):
        await hass.services.async_call(
            DOMAIN,
            "richmat_legacy",
            {"device_id": ["a", "b"], "control": "btn_posup"},
            blocking=True,
        )
    assert frames(owner_a) == frames(owner_b) == []


@pytest.mark.parametrize(
    "side,fallback",
    [
        (SIDE_LEFT, False),
        (SIDE_RIGHT, False),
        (SIDE_BOTH, False),
        (SIDE_BOTH, True),
        (SIDE_LEFT, True),
        (SIDE_RIGHT, True),
    ],
)
async def test_real_pair_preserves_app_and_side(clock, hass, side, fallback):
    await async_register_services(hass)
    log = []

    class Child(RecordingChild):
        def __init__(self, child_side):
            super().__init__(child_side, log)
            self.bed_type = "sleep_evolution" if child_side == SIDE_LEFT else "wsilver_legacy"
            _, self.controller, self.owner = target(self.bed_type)
            self.entry = self.owner.entry
            self.capability_controller = self.controller

        async def async_execute_controller_command(
            self,
            command_fn,
            cancel_running=True,
            skip_disconnect=False,
            resource=None,
            resources=None,
            **kwargs,
        ):
            await command_fn(self.controller)

    children = {key: Child(key) for key in (SIDE_LEFT, SIDE_RIGHT)}
    for child in children.values():
        await child.controller.start_notify()
    pair = PairedBedCoordinator(hass, SimpleNamespace(data={CONF_PAIR_ID: "legacy-pair"}), children)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, side)], []),
    ):

        async def invoke():
            await hass.services.async_call(
                DOMAIN,
                "richmat_legacy",
                {"device_id": "pair", "control": "btn_posup", "duration_ms": 1},
                blocking=True,
            )

        if fallback and side == SIDE_BOTH:
            entered = asyncio.Event()
            run = pair._run

            async def queued(*args, **kwargs):
                entered.set()
                await run(*args, **kwargs)

            await pair._lanes.group_lock.acquire()
            with patch.object(pair, "_run", side_effect=queued):
                task = asyncio.create_task(invoke())
                try:
                    await entered.wait()
                    pair._connection_mode = PAIR_CONNECTION_MODE_SEQUENTIAL
                finally:
                    pair._lanes.group_lock.release()
                with pytest.raises(PairedSideError) as rejected:
                    await task
                error = rejected.value.side_errors[SIDE_LEFT]
                assert isinstance(error, ServiceValidationError)
                assert error.translation_key == "hold_needs_concurrent"
        else:
            if fallback:
                pair._connection_mode = PAIR_CONNECTION_MODE_SEQUENTIAL
            await invoke()
    for child_side, child in children.items():
        assert frames(child.owner) == (
            ["6d", "33" if child_side == SIDE_LEFT else "24", "6e"]
            if side in (child_side, SIDE_BOTH) and not (fallback and side == SIDE_BOTH)
            else []
        )


async def test_action_editor_fields(enable_custom_integrations, hass):
    await async_register_services(hass)
    fields = (await async_get_all_descriptions(hass))[DOMAIN]["richmat_legacy"]["fields"]
    assert set(fields) == {"device_id", "control", "operation", "duration_ms", "side"}
    assert fields["device_id"]["required"] and fields["control"]["required"]
    assert fields["device_id"]["selector"]["device"]["multiple"] is True
    assert "text" in fields["control"]["selector"]
    assert fields["operation"]["default"] == "gesture"
    assert fields["operation"]["selector"]["select"]["options"] == ["gesture", "program"]
    duration = fields["duration_ms"]
    assert duration["default"] == 1000
    assert duration["selector"]["number"]["min"] == 1
    assert duration["selector"]["number"]["max"] == 60000
    assert fields["side"]["selector"]["select"]["options"] == ["both", "left", "right"]
