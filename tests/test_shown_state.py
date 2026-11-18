"""Entities show only what was sent: a cancelled command keeps the previous state."""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.entity_specs import ControllerSwitchSpec
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.light import AdjustableBedAssumedLight
from custom_components.adjustable_bed.paired_coordinator import entity_runtimes
from custom_components.adjustable_bed.switch import (
    SWITCH_DESCRIPTIONS,
    AdjustableBedControllerSwitch,
    AdjustableBedSwitch,
)
from tests.hold_lease_wire import virtual_clock
from tests.test_shared_action_hardening import AlarmController, Bed, beds

SYNCHRO = next(item for item in SWITCH_DESCRIPTIONS if item.key == "synchro_mode")


class SettingsController(AlarmController):
    """A bed with a toggled light, a sync setting and one no-readback switch."""

    sent: list[str]

    @property
    def supports_synchro(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (MASSAGE,)

    async def _write(self, name: str) -> None:
        await self.bed.before_write(self)  # type: ignore[attr-defined]
        context = current_command_context()
        # Like the real writers: a cancelled command returns without sending.
        if context is not None and context.cancel_event.is_set():
            return
        self.bed.sent.append(name)  # type: ignore[attr-defined]

    async def set_synchro(self, enabled: bool) -> None:
        await self._write(f"synchro {enabled}")

    async def lights_toggle(self) -> None:
        await self._write("toggle")


async def _set_massage(controller: Any, on: bool) -> None:
    await controller._write(f"massage {on}")


MASSAGE = ControllerSwitchSpec("massage", "massage", _set_massage)


async def _nothing(_controller: SettingsController) -> None:
    return None


async def _cancel_while_writing(controller: SettingsController) -> None:
    """A replacing command cancels this one while it is on the wire."""
    controller.bed.request_command_cancel()
    context = current_command_context()
    assert context is not None and context.cancel_event.is_set()


def _settings(bed: Bed) -> None:
    bed.sent = []  # type: ignore[attr-defined]
    bed.before_write = _nothing  # type: ignore[attr-defined]
    bed.controller_class = SettingsController
    for name in ("_controller", "_offline_controller"):
        if getattr(bed, name) is not None:
            setattr(bed, name, SettingsController(bed, bed.capability))


def _entity(entity: Any) -> Any:
    entity.async_write_ha_state = MagicMock()
    return entity


@pytest.mark.parametrize(
    ("make", "action"),
    [
        (lambda bed: AdjustableBedSwitch(bed, SYNCHRO), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_toggle"),
    ],
)
async def test_cancelled_command_keeps_the_previous_state(hass, make, action) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        entity = _entity(make(bed))
        before = entity.is_on
        bed.before_write = _cancel_while_writing  # type: ignore[attr-defined]
        with virtual_clock():
            await getattr(entity, action)()
        assert bed.sent == []  # type: ignore[attr-defined]
        assert entity.is_on == before
        # The estimate still matches the light, so the next toggle is right.
        bed.before_write = _nothing  # type: ignore[attr-defined]
        with virtual_clock():
            await getattr(entity, action)()
        assert entity.is_on is True


@pytest.mark.parametrize("topology", [None, "sequential"])
async def test_switch_command_without_a_frame_is_an_error(hass, topology) -> None:
    async with beds(hass, topology=topology) as made:
        for bed in made.items:
            _settings(bed)
        runtime = made.items[0] if made.pair is None else entity_runtimes(made.pair)[0]

        async def unsupported(_controller: Any) -> None:
            raise NotImplementedError

        switch = _entity(
            AdjustableBedSwitch(runtime, dataclasses.replace(SYNCHRO, turn_on_fn=unsupported))
        )
        with virtual_clock(), pytest.raises(ServiceValidationError) as raised:
            await switch.async_turn_on()
        assert raised.value.translation_key == "feature_not_supported"
        assert switch.is_on is None


async def test_sequential_side_switch_is_unknown_after_its_release(hass) -> None:
    async with beds(hass, topology="sequential", connected=False) as made:
        for bed in made.items:
            _settings(bed)
        left = entity_runtimes(made.pair)[0]
        switch = _entity(AdjustableBedControllerSwitch(left, MASSAGE))
        switch._unregister_callbacks = [
            left.register_connection_state_callback(switch._handle_connection_state)
        ]
        with virtual_clock():
            await switch.async_turn_on()
        assert made.items[0].sent == ["massage True"]  # type: ignore[attr-defined]
        assert not made.items[0].is_connected
        # The bed may change while nobody watches, so the sent value is unknown.
        assert switch.is_on is None


async def test_cancelled_color_request_keeps_the_color_mode() -> None:
    from homeassistant.components.light import ColorMode

    from tests.test_ergomotion4 import _rgb_entity, ready

    ctrl, coord = await ready("M19")
    light = _rgb_entity(ctrl, coord)
    light._attr_supported_color_modes = {ColorMode.RGB, ColorMode.RGBW}
    light._attr_color_mode = ColorMode.RGBW
    # STOP drops the queued request before it runs.
    coord.async_execute_controller_command = AsyncMock()
    await light.async_turn_on(rgb_color=(10, 20, 30))
    assert light._attr_color_mode == ColorMode.RGBW


async def test_controller_publishes_no_setting_it_did_not_send() -> None:
    from custom_components.adjustable_bed.profiles import sophie as app
    from custom_components.adjustable_bed.state_keys import SYNCHRO_MODE
    from tests.test_sophie import controller as sophie

    ctrl = next(sophie.__wrapped__())
    ctrl._parse_notification(app.SYNC_ON)
    cancelled = MagicMock()
    cancelled.cancel_event.is_set.return_value = True
    with patch(
        "custom_components.adjustable_bed.command_scheduler.current_command_context",
        return_value=cancelled,
    ):
        await ctrl.set_synchro(False)
    assert ctrl._coordinator.controller_state[SYNCHRO_MODE] is True
