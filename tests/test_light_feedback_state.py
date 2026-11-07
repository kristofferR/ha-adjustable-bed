"""Feedback on/off lights follow the published ``UNDER_BED_LIGHTS_ON`` key."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.codec.malouf import TRANSPORTS
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedOnOffLight
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests import test_leggett_app_controller as leggett
from tests import test_malouf_app as malouf
from tests.state_helpers import state_writer


def _runtime(state: ControllerState) -> MagicMock:
    controller = MagicMock(supports_light_state_feedback=True, light_state_starts_off=False)
    runtime = MagicMock(capability_controller=controller, controller=None, controller_state=state)
    runtime.entity_unique_id.side_effect = lambda key: f"bed_{key}"
    return runtime


async def test_feedback_light_is_unknown_offline_and_follows_published_state() -> None:
    state = ControllerState({UNDER_BED_LIGHTS_ON: True})
    runtime = _runtime(state)
    light = AdjustableBedOnOffLight(runtime, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()

    light._handle_controller_state_update(state)
    assert light.is_on is None  # Stored, but no controller is connected.

    runtime.controller = runtime.capability_controller
    light._handle_connection_state_update(True)
    assert light.is_on is True

    light._handle_controller_state_update(ControllerState({"light_level": 3}))
    assert light.is_on is True
    light._handle_controller_state_update(ControllerState({UNDER_BED_LIGHTS_ON: False}))
    assert light.is_on is False

    runtime.controller = None
    light._handle_connection_state_update(False)
    assert light.is_on is None


async def test_feedback_light_stays_unknown_on_connect_without_a_report() -> None:
    runtime = _runtime(ControllerState())
    light = AdjustableBedOnOffLight(runtime, LIGHT_DESCRIPTION)
    light.async_write_ha_state = MagicMock()
    runtime.controller = runtime.capability_controller

    light._handle_connection_state_update(True)
    assert light.is_on is None


def _capture(controller: BedController) -> ControllerState:
    """Store every publish, single or batched, into one state mapping."""
    state = ControllerState()
    coordinator = controller._coordinator
    assert isinstance(coordinator, MagicMock)
    coordinator.handle_controller_state_updates.side_effect = state_writer(state)
    coordinator.handle_controller_state_update.side_effect = lambda key, value: state.update(
        {key: value}
    )
    return state


def _malouf() -> tuple[BedController, Callable[[], None]]:
    controller = malouf.make_controller("okin_legacy", "S750")
    sender = MagicMock(uuid=TRANSPORTS["okin_legacy"].notify_characteristic)
    data = bytearray(10)
    data[7] = 64
    return controller, lambda: controller._notification_handler(sender, data)


def _leggett() -> tuple[BedController, Callable[[], None]]:
    controller = leggett.make_controller()
    return controller, lambda: leggett.report_cu170(controller, 0x20000)


@pytest.mark.parametrize("family", ["malouf", "leggett"])
async def test_link_scoped_light_report_is_cleared_on_disconnect(family: str) -> None:
    controller, report = {"malouf": _malouf, "leggett": _leggett}[family]()
    state = _capture(controller)
    assert UNDER_BED_LIGHTS_ON not in state

    report()
    assert state[UNDER_BED_LIGHTS_ON] is True

    controller.on_disconnect()
    assert state[UNDER_BED_LIGHTS_ON] is None
