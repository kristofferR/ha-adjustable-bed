"""Entities show only what was sent: a cancelled command keeps the previous state."""

from __future__ import annotations

import asyncio
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
        """Send ``name`` through the shared writer, as many times as the bed repeats."""
        await self.bed.before_write(self)  # type: ignore[attr-defined]
        client = self.client
        assert client is not None

        async def frame(_char: str, data: bytes, **_kwargs: Any) -> None:
            self.bed.sent.append(data.decode())  # type: ignore[attr-defined]
            await self.bed.after_frame(self)  # type: ignore[attr-defined]

        client.write_gatt_char = AsyncMock(side_effect=frame)
        # The shared writer returns without sending once the command is cancelled.
        await self._write_gatt_with_retry(
            "0000fff1-0000-1000-8000-00805f9b34fb",
            name.encode(),
            repeat_count=self.bed.frames,  # type: ignore[attr-defined]
            repeat_delay_ms=0,
        )

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
    bed.frames = 1  # type: ignore[attr-defined]
    bed.before_write = bed.after_frame = _nothing  # type: ignore[attr-defined]
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


async def test_controller_publishes_no_setting_after_its_command_was_cancelled() -> None:
    from custom_components.adjustable_bed.profiles import sophie as app
    from custom_components.adjustable_bed.state_keys import SYNCHRO_MODE
    from tests.test_sophie import controller as sophie

    ctrl = next(sophie.__wrapped__())
    ctrl._parse_notification(app.SYNC_ON)
    cancelled = MagicMock()
    cancelled.cancel_event.is_set.return_value = True
    cancelled.frames_written = 0
    with patch(
        "custom_components.adjustable_bed.command_scheduler.current_command_context",
        return_value=cancelled,
    ):
        await ctrl.set_synchro(False)
    assert ctrl._coordinator.controller_state[SYNCHRO_MODE] is True


@pytest.mark.parametrize(
    ("frames", "switch_state"),
    # STOP after the only frame: the bed has the new value. STOP between two
    # frames of one value: it may not, so the switch is unknown.
    [(1, True), (2, None)],
)
async def test_stop_after_a_frame_went_out_shows_what_reached_the_bed(
    hass, frames, switch_state
) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        bed.frames = frames  # type: ignore[attr-defined]
        bed.after_frame = _cancel_while_writing  # type: ignore[attr-defined]
        switch = _entity(AdjustableBedSwitch(bed, SYNCHRO))
        light = _entity(AdjustableBedAssumedLight(bed))
        with virtual_clock():
            await switch.async_turn_on()
            await light.async_turn_on()
        assert switch.is_on is switch_state
        # The toggle's first frame is the toggle, so the light did change.
        assert light.is_on is True
        assert bed.sent == ["synchro True", "toggle"]  # type: ignore[attr-defined]


async def test_turn_on_without_a_color_follows_a_pending_color_request() -> None:
    from homeassistant.components.light import ColorMode

    from custom_components.adjustable_bed.command_scheduler import Delivery
    from tests.test_ergomotion4 import _rgb_entity, ready

    ctrl, coord = await ready("M19")
    light = _rgb_entity(ctrl, coord)
    light._attr_supported_color_modes = {ColorMode.RGB, ColorMode.RGBW}
    light._attr_color_mode = ColorMode.RGBW
    entered, release = asyncio.Event(), asyncio.Event()
    sent: list[ColorMode] = []

    async def send(mode: ColorMode) -> Delivery:
        if not sent and not entered.is_set():
            entered.set()
            await release.wait()
        sent.append(mode)
        light._attr_color_mode = mode
        return Delivery.SENT

    with (
        patch.object(light, "_turn_on_rgb", side_effect=lambda **_: send(ColorMode.RGB)),
        patch.object(light, "_turn_on_rgbw", side_effect=lambda **_: send(ColorMode.RGBW)),
    ):
        first = asyncio.create_task(light.async_turn_on(rgb_color=(10, 20, 30)))
        await entered.wait()
        # A plain turn-on while the RGB request still waits for the link.
        second = asyncio.create_task(light.async_turn_on())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
    assert sent == [ColorMode.RGB, ColorMode.RGB]
    assert light._attr_color_mode == ColorMode.RGB
