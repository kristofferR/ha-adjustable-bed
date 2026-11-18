"""Public services admit all physical targets before dispatch or lazy loading."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.richmat_mh import app_services as actions
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services
from tests.test_richmat_cluster022 import frames, make
from tests.test_richmat_mh import sleeps as sleeps


def target(controller):
    coordinator = controller._coordinator
    coordinator.name = controller.app
    coordinator.stop_epoch = 0
    coordinator.async_execute_controller_command = AsyncMock()
    return coordinator


@pytest.fixture
async def targets(hass):
    await async_register_services(hass)
    controllers = (make("nisco", "cfrm"), make("mlily_supreme", "cfrm"))
    coordinators = tuple(target(controller) for controller in controllers)

    async def validation(_parent, child, _preflighted):
        return controllers[coordinators.index(child)]

    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, "both") for coordinator in coordinators], [])),
        patch("custom_components.adjustable_bed.services._validation_controller", side_effect=validation),
    ):
        yield coordinators, controllers


async def test_nisco_only_catalog_lock_rejects_mixed_call_before_either_dispatch(hass, targets) -> None:
    coordinators, controllers = targets
    with pytest.raises(ServiceValidationError, match="declared"):
        await hass.services.async_call(DOMAIN, actions.SERVICE, {
            "device_id": ["left", "right"], "action": "press", "opcode": 0x84,
        }, blocking=True)
    for coordinator, controller in zip(coordinators, controllers, strict=True):
        coordinator.async_execute_controller_command.assert_not_awaited()
        assert not frames(controller)


async def test_stop_epochs_are_captured_for_all_targets_before_first_import(hass, targets) -> None:
    coordinators, _controllers = targets
    imported = False

    async def importing(*_args):
        nonlocal imported
        imported = True
        # A STOP arrives while loading the module. Both admissions must already
        # contain the old epoch, rather than refreshing it after this await.
        for coordinator in coordinators:
            coordinator.stop_epoch += 1

    with patch.object(actions, "async_import_modules", side_effect=importing):
        await hass.services.async_call(DOMAIN, actions.SERVICE, {
            "device_id": ["left", "right"], "action": "query", "query": "version",
        }, blocking=True)
    assert imported
    for coordinator in coordinators:
        call = coordinator.async_execute_controller_command.call_args
        assert call.kwargs["expected_stop_epoch"] == 0
        assert coordinator.stop_epoch == 1


async def test_registered_query_uses_bed_probe_and_explicit_response(hass, targets) -> None:
    coordinators, controllers = targets
    for coordinator, controller in zip(coordinators, controllers, strict=True):
        async def execute(command, _controller=controller, **_kwargs):
            await command(_controller)
        coordinator.async_execute_controller_command.side_effect = execute
    await hass.services.async_call(DOMAIN, actions.SERVICE, {
        "device_id": ["left", "right"], "action": "query", "query": "mattress",
    }, blocking=True)
    for controller in controllers:
        assert frames(controller) == ["5e1a000179"]
        assert controller.client.write_gatt_char.call_args.kwargs["response"] is True


async def test_mode_alarm_rejects_sibling_before_any_target_is_programmed(hass, targets) -> None:
    coordinators, controllers = targets
    for controller in controllers:
        controller._dev["alarm"] = True
    with pytest.raises(ServiceValidationError, match="only for Nisco"):
        await hass.services.async_call(DOMAIN, actions.MODE_ALARM_SERVICE, {
            "device_id": ["left", "right"], "enabled": False,
        }, blocking=True)
    for coordinator in coordinators:
        coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("stop_during_import", [False, True])
async def test_real_pair_captures_both_physical_stop_epochs_before_import(hass, monkeypatch, stop_during_import) -> None:
    from custom_components.adjustable_bed import services
    from tests.test_paired_coordinator import RecordingChild, _make

    log = []
    children = {side: RecordingChild(side, log) for side in ("left", "right")}
    pair = _make(children)
    controllers = {"left": make("nisco"), "right": make("mlily_supreme")}
    for side, child in children.items():
        controller = controllers[side]
        child.controller = child.capability_controller = controller
        child.bed_type = f"richmat_{controller.app}"

        async def execute(command, _controller=controller, **_kwargs):
            await command(_controller)

        child.async_execute_controller_command = execute
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_args: ([(pair, "both")], []))

    async def importing(*_args):
        if stop_during_import:
            await children["left"].async_stop_command()

    monkeypatch.setattr(actions, "async_import_modules", importing)
    await async_register_services(hass)
    try:
        await hass.services.async_call(DOMAIN, actions.SERVICE, {
            "device_id": "parent", "action": "query", "query": "version",
        }, blocking=True)
        expected = [] if stop_during_import else ["6e9a000008"]
        assert frames(controllers["left"]) == expected
        assert frames(controllers["right"]) == expected
    finally:
        await pair.async_shutdown()


async def test_app_mode_action_sets_local_pickers_without_the_scheduler(hass, targets) -> None:
    coordinators, controllers = targets
    for coordinator, controller in zip(coordinators, controllers, strict=True):
        coordinator.capability_controller = controller
    await hass.services.async_call(DOMAIN, actions.SERVICE, {
        "device_id": ["left", "right"], "action": "app_mode", "transmit_mode": "2",
    }, blocking=True)
    for coordinator, controller in zip(coordinators, controllers, strict=True):
        assert controller._transmit_mode == 2 and not frames(controller)
        coordinator.async_execute_controller_command.assert_not_awaited()
    with pytest.raises(ServiceValidationError, match="app_mode"):
        await hass.services.async_call(DOMAIN, actions.SERVICE, {
            "device_id": ["left"], "action": "press", "opcode": 1, "transmit_mode": "1",
        }, blocking=True)
    # cfrm declares no motor groups, so a group is refused before any target changes.
    with pytest.raises(ServiceValidationError, match="motor group"):
        await hass.services.async_call(DOMAIN, actions.SERVICE, {
            "device_id": ["left", "right"], "action": "app_mode", "transmit_mode": "1",
            "motor_group": "group_sync",
        }, blocking=True)
    assert all(controller._transmit_mode == 2 for controller in controllers)


async def test_real_button_entity_dispatches_through_runtime(hass, sleeps) -> None:
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.select import _select_entities_for
    from tests.test_malouf_app_entities import configure_entity_runtime

    controller = make("mlily_supreme", "cfrm")
    controller._dev["led"] = True
    runtime = configure_entity_runtime(hass, controller, "richmat_mlily_supreme")
    # The app's transmit mode and motor group pickers are not entities.
    assert not any(key in entity.unique_id for entity in _select_entities_for(hass, runtime)
                   for key in ("transmit_mode", "group_type"))
    button = next(entity for entity in _button_entities_for(hass, runtime)
                  if "richmat_mh_toggle_smart_light_lock" in entity.unique_id)
    button.hass = hass

    async def execute(command, **_kwargs):
        await command(controller)

    runtime.async_execute_controller_command = AsyncMock(side_effect=execute)
    await button.async_press()
    assert frames(controller) == ["6e0100c02f"]
    runtime.async_execute_controller_command.assert_awaited_once()
