"""The on/off light and the controllers' commanded timers show only what was sent."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.command_scheduler import Delivery
from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedOnOffLight
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.hold_lease_wire import virtual_clock
from tests.test_shared_action_hardening import beds
from tests.test_shown_state import (
    SettingsController,
    _cancel_while_writing,
    _entity,
    _nothing,
    _settings,
)


class OnOffController(SettingsController):
    """A bed that switches its light on and off but never reports it."""

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def supported_color_modes(self) -> frozenset[str]:
        return frozenset()

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def lights_off(self) -> None:
        await self._write("off")


def _on_off(bed: Any) -> None:
    _settings(bed)
    bed.controller_class = OnOffController
    for name in ("_controller", "_offline_controller"):
        if getattr(bed, name) is not None:
            setattr(bed, name, OnOffController(bed, bed.capability))


@pytest.mark.parametrize(
    ("frames", "cancel_at", "expected"),
    [
        # Cancelled before any frame: the light keeps its previous state.
        (1, "before_write", None),
        # The only frame went out, then STOP: the light did change.
        (1, "after_frame", True),
        # Cut off between the two frames of one value: unknown.
        (2, "after_frame", None),
    ],
)
async def test_on_off_light_shows_what_reached_the_bed(hass, frames, cancel_at, expected) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _on_off(bed)
        bed.frames = frames  # type: ignore[attr-defined]
        light = _entity(AdjustableBedOnOffLight(bed, LIGHT_DESCRIPTION))
        assert light.is_on is None
        setattr(bed, cancel_at, _cancel_while_writing)
        with virtual_clock():
            await light.async_turn_on()
        assert light.is_on is expected
        setattr(bed, cancel_at, _nothing)
        with virtual_clock():
            await light.async_turn_on()
        assert light.is_on is True
        # A turn-off cancelled before any frame keeps it on.
        bed.before_write = _cancel_while_writing  # type: ignore[attr-defined]
        with virtual_clock():
            await light.async_turn_off()
        assert light.is_on is True


@pytest.mark.parametrize(
    ("delivery", "published"),
    [(Delivery.SENT, [20]), (Delivery.PARTIAL, [None]), (Delivery.NONE, [])],
)
def test_a_commanded_timer_is_published_only_as_far_as_it_was_sent(delivery, published) -> None:
    coordinator = MagicMock()
    controller = MagicMock(spec=BedController)
    controller._coordinator = coordinator
    controller.forward_controller_state_updates = lambda *updates: (
        BedController.forward_controller_state_updates(controller, *updates)
    )
    with patch(
        "custom_components.adjustable_bed.beds.base.command_delivery", return_value=delivery
    ):
        BedController.forward_sent_state_updates(controller, MASSAGE_TIMER_MINUTES(20))
    sent = [
        update.value
        for call in coordinator.handle_controller_state_updates.call_args_list
        for update in call.args
        if update.key == MASSAGE_TIMER_MINUTES
    ]
    assert sent == published
