"""Entities show only what was sent: a cancelled command keeps the previous state."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.entity_specs import ControllerSwitchSpec
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.light import (
    LIGHT_DESCRIPTION,
    AdjustableBedAssumedLight,
    AdjustableBedLight,
    AdjustableBedOnOffLight,
)
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

    def __init__(self, coordinator, capability):
        super().__init__(coordinator, capability)
        if self.client is not None:
            self.client.write_gatt_char = AsyncMock()

    @property
    def supports_synchro(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    @property
    def supported_color_modes(self) -> frozenset[str]:
        return frozenset({"rgb", "rgbw"})

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (MASSAGE,)

    async def _write(self, name: str) -> None:
        await self.bed.before_write(self)  # type: ignore[attr-defined]
        context = current_command_context()
        # Like the real writers: a cancelled command returns without sending.
        if context is not None and context.cancel_event.is_set():
            return
        await self._write_gatt_with_retry("test", name.encode())
        self.bed.sent.append(name)  # type: ignore[attr-defined]
        await self.bed.after_write(self)  # type: ignore[attr-defined]

    async def set_synchro(self, enabled: bool) -> None:
        await self._write(f"synchro {enabled}")

    async def lights_toggle(self) -> None:
        await self._write("toggle")

    async def lights_on(self) -> None:
        await self._write("on")

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self._write(f"rgb {rgb_color}")

    async def set_light_color_rgbw(
        self, rgbw_color: tuple[int, int, int, int], intensity: int | None = None
    ) -> None:
        await self._write(f"rgbw {rgbw_color}")


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
    bed.after_write = _nothing  # type: ignore[attr-defined]
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


@pytest.mark.parametrize(
    ("make", "action"),
    [
        (lambda bed: AdjustableBedSwitch(bed, SYNCHRO), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_toggle"),
    ],
)
@pytest.mark.parametrize("during_cleanup", [False, True])
async def test_cancellation_after_transmission_keeps_the_sent_state(
    hass, make, action, during_cleanup
):
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        entity = _entity(make(bed))

        async def write(*_args, **_kwargs):
            # The frame has reached the bed, but its await has not returned.
            bed.request_command_cancel()

        if during_cleanup:
            async def cleanup(controller):
                await write()
                raise asyncio.CancelledError

            bed.after_write = cleanup  # type: ignore[attr-defined]
        else:
            bed.client.write_gatt_char.side_effect = write
        with virtual_clock():
            await getattr(entity, action)()
        assert len(bed.sent) == 1  # type: ignore[attr-defined]
        assert entity.is_on is True
        bed.client.write_gatt_char.side_effect = None
        bed.after_write = _nothing  # type: ignore[attr-defined]
        with virtual_clock():
            await entity.async_turn_off()
        assert len(bed.sent) == 2  # type: ignore[attr-defined]
        assert entity.is_on is False


@pytest.mark.parametrize("preparation", [False, True])
async def test_cleanup_or_preparation_does_not_acknowledge_an_unsent_toggle(hass, preparation):
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedAssumedLight(bed))

        async def cancel_and_release(controller):
            if preparation:
                bed.client.write_gatt_char.side_effect = (
                    lambda *_args, **_kwargs: bed.request_command_cancel()
                )
                await controller._write_gatt_with_retry("test", b"probe", track_command_write=False)
            else:
                bed.request_command_cancel()
                await controller._write_gatt_with_retry(
                    "test", b"release", cancel_event=asyncio.Event()
                )

        bed.before_write = cancel_and_release  # type: ignore[attr-defined]
        with virtual_clock():
            await light.async_turn_on()
        bed.client.write_gatt_char.assert_awaited_once()
        assert light.is_on is False


@pytest.mark.parametrize("mode", [ColorMode.RGB, ColorMode.RGBW])
async def test_sent_power_on_does_not_acknowledge_a_cancelled_color(hass, mode):
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedLight(bed, LIGHT_DESCRIPTION))
        previous_mode = ColorMode.RGBW if mode == ColorMode.RGB else ColorMode.RGB
        light._attr_color_mode = previous_mode
        previous_rgb, previous_rgbw = light.rgb_color, light.rgbw_color

        async def write(*_args, **_kwargs):
            bed.request_command_cancel()

        bed.client.write_gatt_char.side_effect = write
        bed.controller.set_light_color = AsyncMock(wraps=bed.controller.set_light_color)
        bed.controller.set_light_color_rgbw = AsyncMock(wraps=bed.controller.set_light_color_rgbw)
        color = (
            {"rgb_color": (10, 20, 30)}
            if mode == ColorMode.RGB
            else {"rgbw_color": (1, 2, 3, 4)}
        )
        with (
            virtual_clock(),
            patch.object(
                SettingsController,
                "supports_explicit_light_on_control",
                new_callable=PropertyMock,
                return_value=True,
            ),
        ):
            await light.async_turn_on(**color)
        assert bed.sent == ["on"]  # type: ignore[attr-defined]
        assert light.is_on is True
        assert light.color_mode == previous_mode
        assert (light.rgb_color, light.rgbw_color) == (previous_rgb, previous_rgbw)
        bed.controller.set_light_color.assert_not_awaited()
        bed.controller.set_light_color_rgbw.assert_not_awaited()


@pytest.mark.parametrize("mode", [ColorMode.RGB, ColorMode.RGBW])
async def test_queued_turn_on_uses_the_last_sent_color_mode(hass, mode):
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedLight(bed, LIGHT_DESCRIPTION))
        light._attr_color_mode = ColorMode.RGBW if mode == ColorMode.RGB else ColorMode.RGB
        entered, release, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def write(*_args, **_kwargs):
            entered.set()
            await release.wait()

        bed.client.write_gatt_char.side_effect = write
        original_execute = bed.async_execute_controller_command

        async def execute(*args, **kwargs):
            queued.set()
            await original_execute(*args, **kwargs)

        color = (
            {"rgb_color": (10, 20, 30)}
            if mode == ColorMode.RGB
            else {"rgbw_color": (1, 2, 3, 4)}
        )
        with virtual_clock():
            first = asyncio.create_task(light.async_turn_on(**color))
            await entered.wait()
            bed.async_execute_controller_command = execute
            second = asyncio.create_task(light.async_turn_on())
            await queued.wait()
            release.set()
            await asyncio.gather(first, second)
        assert light.color_mode == mode
        assert bed.sent == [f"{mode} {next(iter(color.values()))}"] * 2  # type: ignore[attr-defined]


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
    cancelled.successful_writes = 0
    with patch(
        "custom_components.adjustable_bed.command_scheduler.current_command_context",
        return_value=cancelled,
    ):
        await ctrl.set_synchro(False)
    assert ctrl._coordinator.controller_state[SYNCHRO_MODE] is True


async def test_controller_publishes_setting_sent_during_cancellation() -> None:
    from custom_components.adjustable_bed.profiles import sophie as app
    from custom_components.adjustable_bed.state_keys import SYNCHRO_MODE
    from tests.test_sophie import controller as sophie

    ctrl = next(sophie.__wrapped__())
    ctrl._parse_notification(app.SYNC_ON)
    event = ctrl._coordinator.cancel_command
    context = MagicMock(cancel_event=event, successful_writes=0)
    ctrl.client.write_gatt_char.side_effect = lambda *_args, **_kwargs: event.set()
    with patch(
        "custom_components.adjustable_bed.command_scheduler.current_command_context",
        return_value=context,
    ):
        await ctrl.set_synchro(False)
    assert event.is_set()
    assert ctrl._coordinator.controller_state[SYNCHRO_MODE] is False


@pytest.mark.parametrize(
    "protocol", ["reverie", "jiecang", "rondure", "wilinke", "box25", "box25_legacy"]
)
async def test_production_light_distinguishes_a_toggle_from_a_wake(hass, protocol):
    from custom_components.adjustable_bed.beds.jiecang.controller import JiecangController
    from custom_components.adjustable_bed.beds.leggett.wilinke import LeggettWilinkeController
    from custom_components.adjustable_bed.beds.reverie.controller import ReverieController
    from custom_components.adjustable_bed.beds.rondure import RondureController
    from custom_components.adjustable_bed.beds.sleepys.box25 import (
        SleepysBox25Controller,
        SleepysBox25LegacyController,
    )
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        toggles = {
            "reverie": lambda: ReverieController(bed, model="3E"),
            "jiecang": lambda: JiecangController(bed),
            "rondure": lambda: RondureController(bed),
            "wilinke": lambda: LeggettWilinkeController(bed),
        }
        if protocol in toggles:
            bed._controller = toggles[protocol]()
            light = _entity(AdjustableBedAssumedLight(bed))
        elif protocol == "box25":
            bed._controller = SleepysBox25Controller(bed)
            light = _entity(AdjustableBedLight(bed, LIGHT_DESCRIPTION))
        else:
            bed._controller = SleepysBox25LegacyController(bed)
            light = _entity(AdjustableBedOnOffLight(bed, LIGHT_DESCRIPTION))
        before = light.is_on

        async def write(*_args, **_kwargs):
            bed.request_command_cancel()

        bed.client.write_gatt_char.side_effect = write
        with virtual_clock():
            await light.async_turn_on()
        bed.client.write_gatt_char.assert_awaited_once()
        if protocol in toggles:
            assert light.is_on is True
        else:
            assert light.is_on is before
            assert bed.controller_state.get(UNDER_BED_LIGHTS_ON) is not True
