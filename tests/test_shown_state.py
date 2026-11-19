"""Entities show only what was sent: a cancelled command keeps the previous state."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.entity_specs import ControllerSwitchSpec
from custom_components.adjustable_bed.command_scheduler import (
    CommandOutcome,
    Delivery,
    command_frames_counted,
    current_command_context,
)
from custom_components.adjustable_bed.light import (
    LIGHT_DESCRIPTION,
    AdjustableBedAssumedLight,
    AdjustableBedLight,
    AdjustableBedOnOffLight,
)
from custom_components.adjustable_bed.paired_coordinator import entity_runtimes
from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL
from custom_components.adjustable_bed.switch import (
    SWITCH_DESCRIPTIONS,
    AdjustableBedControllerSwitch,
    AdjustableBedSwitch,
)
from tests.hold_lease_wire import virtual_clock
from tests.test_shared_action_hardening import AlarmController, Bed, beds

SYNCHRO = next(item for item in SWITCH_DESCRIPTIONS if item.key == "synchro_mode")


class SettingsController(AlarmController):
    """A bed with lights, a sync setting and one no-readback switch."""

    sent: list[str]

    def __init__(self, coordinator: Any, capability: Any) -> None:
        super().__init__(coordinator, capability)
        if self.client is not None:
            self.client.write_gatt_char = AsyncMock(side_effect=self._frame)

    async def _frame(self, _char: str, data: bytes, **_kwargs: Any) -> None:
        self.bed.sent.append(data.decode())  # type: ignore[attr-defined]
        await self.bed.after_frame(self)  # type: ignore[attr-defined]

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
        """Send ``name`` through the shared writer, as many times as the bed repeats."""
        await self.bed.before_write(self)  # type: ignore[attr-defined]
        stop: asyncio.Event | None = self.bed.local_stop  # type: ignore[attr-defined]
        # The shared writer returns without sending once the command is cancelled,
        # or once the controller's own stop (which never cancels the scheduler) is set.
        with command_frames_counted() if stop is not None else contextlib.nullcontext():
            await self._write_gatt_with_retry(
                "0000fff1-0000-1000-8000-00805f9b34fb",
                name.encode(),
                repeat_count=self.bed.frames,  # type: ignore[attr-defined]
                repeat_delay_ms=0,
                cancel_event=stop,
            )
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
    bed.frames = 1  # type: ignore[attr-defined]
    bed.local_stop = None  # type: ignore[attr-defined]
    bed.before_write = bed.after_frame = bed.after_write = _nothing  # type: ignore[attr-defined]
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
    cancelled.frames_written = cancelled.frames_skipped = 0
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


async def _cancel_and_end_in_cleanup(controller: SettingsController) -> None:
    """STOP lands after the frame went out, and the command ends in its cleanup."""
    controller.bed.request_command_cancel()
    raise asyncio.CancelledError


@pytest.mark.parametrize(
    ("make", "action"),
    [
        (lambda bed: AdjustableBedSwitch(bed, SYNCHRO), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_turn_on"),
        (lambda bed: AdjustableBedAssumedLight(bed), "async_toggle"),
    ],
)
async def test_cancellation_during_cleanup_keeps_the_sent_state(hass, make, action) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        entity = _entity(make(bed))
        bed.after_write = _cancel_and_end_in_cleanup  # type: ignore[attr-defined]
        with virtual_clock():
            await getattr(entity, action)()
        assert len(bed.sent) == 1  # type: ignore[attr-defined]
        assert entity.is_on is True
        bed.after_write = _nothing  # type: ignore[attr-defined]
        with virtual_clock():
            await entity.async_turn_off()
        assert len(bed.sent) == 2  # type: ignore[attr-defined]
        assert entity.is_on is False


@pytest.mark.parametrize("preparation", [False, True])
async def test_cleanup_or_preparation_does_not_acknowledge_an_unsent_toggle(
    hass, preparation
) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedAssumedLight(bed))

        async def cancel_and_release(controller: SettingsController) -> None:
            if preparation:
                # A link probe goes out; STOP lands while it is on the wire.
                bed.after_frame = _cancel_while_writing  # type: ignore[attr-defined]
                await controller._write_gatt_with_retry(
                    "0000fff1-0000-1000-8000-00805f9b34fb", b"probe", track_command_write=False
                )
                bed.after_frame = _nothing  # type: ignore[attr-defined]
            else:
                # STOP, then a release frame with its own event during cleanup.
                bed.request_command_cancel()
                await controller._write_gatt_with_retry(
                    "0000fff1-0000-1000-8000-00805f9b34fb",
                    b"release",
                    cancel_event=asyncio.Event(),
                )

        bed.before_write = cancel_and_release  # type: ignore[attr-defined]
        with virtual_clock():
            await light.async_turn_on()
        assert bed.sent == ["probe" if preparation else "release"]  # type: ignore[attr-defined]
        assert light.is_on is False


@pytest.mark.parametrize("mode", [ColorMode.RGB, ColorMode.RGBW])
async def test_power_on_sent_without_its_color_leaves_the_light_unknown(hass, mode) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedLight(bed, LIGHT_DESCRIPTION))
        previous_mode = ColorMode.RGBW if mode == ColorMode.RGB else ColorMode.RGB
        light._attr_color_mode = previous_mode
        previous_rgb, previous_rgbw = light.rgb_color, light.rgbw_color
        # STOP lands while the power frame is on the wire.
        bed.after_frame = _cancel_while_writing  # type: ignore[attr-defined]
        color = (
            {"rgb_color": (10, 20, 30)} if mode == ColorMode.RGB else {"rgbw_color": (1, 2, 3, 4)}
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
        # The light came on, but its color never went out: show it as unknown.
        assert light.is_on is None
        assert light.color_mode == previous_mode
        assert (light.rgb_color, light.rgbw_color) == (previous_rgb, previous_rgbw)


@pytest.mark.parametrize("mode", [ColorMode.RGB, ColorMode.RGBW])
async def test_queued_turn_on_uses_the_last_sent_color_mode(hass, mode) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        light = _entity(AdjustableBedLight(bed, LIGHT_DESCRIPTION))
        light._attr_color_mode = ColorMode.RGBW if mode == ColorMode.RGB else ColorMode.RGB
        entered, release, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def hold(_controller: SettingsController) -> None:
            entered.set()
            await release.wait()

        bed.after_frame = hold  # type: ignore[attr-defined]
        original_execute = bed.async_execute_controller_command

        async def execute(*args: Any, **kwargs: Any) -> None:
            queued.set()
            await original_execute(*args, **kwargs)

        color = (
            {"rgb_color": (10, 20, 30)} if mode == ColorMode.RGB else {"rgbw_color": (1, 2, 3, 4)}
        )
        with virtual_clock():
            first = asyncio.create_task(light.async_turn_on(**color))
            await entered.wait()
            # A turn-on without a color while the colored one is still on the wire.
            bed.async_execute_controller_command = execute  # type: ignore[method-assign]
            second = asyncio.create_task(light.async_turn_on())
            await queued.wait()
            release.set()
            await asyncio.gather(first, second)
        assert light.color_mode == mode
        assert bed.sent == [f"{mode} {next(iter(color.values()))}"] * 2  # type: ignore[attr-defined]


async def test_controller_publishes_setting_sent_during_cancellation() -> None:
    from custom_components.adjustable_bed.profiles import sophie as app
    from custom_components.adjustable_bed.state_keys import SYNCHRO_MODE
    from tests.test_sophie import controller as sophie

    ctrl = next(sophie.__wrapped__())
    ctrl._parse_notification(app.SYNC_ON)
    event = ctrl._coordinator.cancel_command
    context = MagicMock(cancel_event=event, frames_written=0, frames_skipped=0)
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
async def test_production_light_distinguishes_a_toggle_from_a_wake(hass, protocol) -> None:
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

        async def write(*_args: Any, **_kwargs: Any) -> None:
            bed.request_command_cancel()

        assert bed.client is not None
        bed.client.write_gatt_char = AsyncMock(side_effect=write)
        with virtual_clock():
            await light.async_turn_on()
        bed.client.write_gatt_char.assert_awaited_once()
        if protocol in toggles:
            # The toggle went out: the estimate follows it.
            assert light.is_on is True
        else:
            # Only the wake that readies the link went out.
            assert light.is_on is before
            assert bed.controller_state.get(UNDER_BED_LIGHTS_ON) is not True


@pytest.mark.parametrize("startup", [True, False])
@pytest.mark.parametrize("cancelled", [True, False])
async def test_link_startup_on_reconnect_is_not_the_commands_frame(hass, startup, cancelled) -> None:
    async with beds(hass, 1, connected=False) as made:
        bed = made.items[0]
        _settings(bed)
        # The real connect path: the command has to open the link itself.
        del bed.async_ensure_connected

        async def connect_link(reset_timer: bool = True) -> bool:
            await bed.fake_connect()
            if startup:
                # A session open the link sends on connect, through the shared writer.
                await bed.controller._write_gatt_with_retry(  # type: ignore[union-attr]
                    "0000fff1-0000-1000-8000-00805f9b34fb", b"startup", repeat_delay_ms=0
                )
            return True

        bed._async_connect_link_locked = connect_link  # type: ignore[method-assign]
        if cancelled:
            # STOP lands after the link is up, before the command's own frame.
            bed.before_write = _cancel_while_writing  # type: ignore[attr-defined]
        light = _entity(AdjustableBedAssumedLight(bed))
        with virtual_clock():
            await light.async_turn_on()
        expected = (["startup"] if startup else []) + ([] if cancelled else ["toggle"])
        assert bed.sent == expected  # type: ignore[attr-defined]
        # Only the toggle itself moves the estimate.
        assert light.is_on is not cancelled


def _running_command(cancel: asyncio.Event) -> Any:
    from custom_components.adjustable_bed.command_scheduler import CommandContext, CommandKind

    return CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="test",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )


async def test_mlily_cleanup_stop_is_not_the_commands_frame() -> None:
    from custom_components.adjustable_bed.codec import richmat as codec
    from tests.test_mlily_remote import make

    controller, coordinator = make()
    with virtual_clock():
        await controller.start_notify()
        link = controller._current()
        command = _running_command(coordinator.cancel_command)
        with patch(
            "custom_components.adjustable_bed.command_scheduler.current_command_context",
            return_value=command,
        ):
            coordinator.cancel_command.set()
            stop = codec.function(codec.STOP, 0, single=link.legacy)
            assert await controller._write(stop, link, cleanup=True)
            assert command.frames_written == 0
            coordinator.cancel_command.clear()
            assert await controller._write(stop, link)
            assert command.frames_written == 1
        await controller.stop_notify()


async def test_svane_release_stop_is_not_the_commands_frame() -> None:
    from tests.test_svane import HEAD, UP, make_controller

    controller = make_controller()
    cancel = controller._coordinator.cancel_command
    command = _running_command(cancel)
    with patch(
        "custom_components.adjustable_bed.command_scheduler.current_command_context",
        return_value=command,
    ):
        controller._started[(HEAD, UP)] = None
        cancel.set()
        await controller._release(((HEAD, UP),))
        assert controller.client.write_gatt_char.await_count == 1
        assert command.frames_written == 0
        cancel.clear()
        await controller._write(HEAD, UP, b"\x01\x00")
        assert command.frames_written == 1


@pytest.mark.parametrize("cancelled", [True, False])
async def test_sent_state_helper_after_a_reconnect_publishes_only_the_commands_frame(
    hass, cancelled
) -> None:
    from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL

    async with beds(hass, 1, connected=False) as made:
        bed = made.items[0]
        _settings(bed)
        del bed.async_ensure_connected

        async def connect_link(reset_timer: bool = True) -> bool:
            await bed.fake_connect()
            await bed.controller._write_gatt_with_retry(  # type: ignore[union-attr]
                "0000fff1-0000-1000-8000-00805f9b34fb", b"startup", repeat_delay_ms=0
            )
            return True

        bed._async_connect_link_locked = connect_link  # type: ignore[method-assign]
        if cancelled:
            bed.before_write = _cancel_while_writing  # type: ignore[attr-defined]

        async def set_level(controller: SettingsController) -> None:
            # A select or number that publishes the value it commanded.
            with controller.sent_state(LIGHT_LEVEL(5)):
                await controller._write("level 5")

        bed.controller_state[LIGHT_LEVEL] = 3
        with virtual_clock():
            await bed.async_execute_controller_command(set_level, cancel_running=False)
        # Nothing of the command reached the bed: the previous value stays.
        assert bed.controller_state.get(LIGHT_LEVEL) == (3 if cancelled else 5)


async def _fail_after_frame(controller: SettingsController) -> None:
    """The link drops on the second frame of a two-frame value."""
    if len(controller.bed.sent) > 1:  # type: ignore[attr-defined]
        raise BleakError("link lost after the first frame")


async def _fail_after_frame_during_stop(controller: SettingsController) -> None:
    """STOP arrives while the second frame is in flight, and that write fails."""
    if len(controller.bed.sent) > 1:  # type: ignore[attr-defined]
        controller.bed.request_command_cancel()
        raise BleakError("link lost after the first frame")


def _on_off_light(bed: Bed) -> Any:
    light = _entity(AdjustableBedOnOffLight(bed, LIGHT_DESCRIPTION))
    light._attr_is_on = False
    return light


def _controller_switch(bed: Bed) -> Any:
    switch = _entity(AdjustableBedControllerSwitch(bed, MASSAGE))
    switch._commanded = False
    return switch


async def _turn_on(entity: Any) -> None:
    await entity.async_turn_on()


async def _set_level(bed: Bed) -> None:
    async def set_level(controller: SettingsController) -> None:
        # A select or number that publishes the value it commanded.
        with controller.sent_state(LIGHT_LEVEL(5)):
            await controller._write("level 5")

    await bed.async_execute_controller_command(set_level, cancel_running=False)


@pytest.mark.parametrize("site", ["on_off_light", "controller_switch", "published_setting"])
@pytest.mark.parametrize(
    ("ending", "shown"),
    # Cancelled after its only frame: sent. Failed after one of two frames,
    # with or without a STOP meanwhile: unknown.
    [("cancelled", "new"), ("failed", "unknown"), ("failed_during_stop", "unknown")],
)
async def test_a_command_that_raises_after_its_frame_still_shows_what_was_sent(
    hass, site, ending, shown
) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        bed.frames = 1 if ending == "cancelled" else 2  # type: ignore[attr-defined]
        if ending == "cancelled":
            bed.after_write = _cancel_and_end_in_cleanup  # type: ignore[attr-defined]
        elif ending == "failed":
            bed.after_frame = _fail_after_frame  # type: ignore[attr-defined]
        else:
            bed.after_frame = _fail_after_frame_during_stop  # type: ignore[attr-defined]
        bed.controller_state[LIGHT_LEVEL] = 3
        entity = (
            _on_off_light(bed)
            if site == "on_off_light"
            else _controller_switch(bed)
            if site == "controller_switch"
            else None
        )
        run = _set_level(bed) if entity is None else _turn_on(entity)
        with virtual_clock():
            if ending != "cancelled":
                # The failure still reaches the caller.
                with pytest.raises(BleakError):
                    await run
            else:
                await run
        # The frame went out (the failed second write was attempted, not sent).
        assert len(bed.sent) == (1 if ending == "cancelled" else 2)  # type: ignore[attr-defined]
        if entity is None:
            value = bed.controller_state.get(LIGHT_LEVEL)
            assert value == (5 if shown == "new" else None)
        else:
            assert entity.is_on is (True if shown == "new" else None)
        if ending == "cancelled":
            # The cancellation still ended the command: it did not complete.
            record = bed._command_scheduler.recent_records[-1]
            assert record.outcome is not CommandOutcome.COMPLETED


async def test_preparing_the_link_in_another_task_never_hides_the_commands_frame() -> None:
    from custom_components.adjustable_bed import command_scheduler as scheduler

    cancel = asyncio.Event()
    command = _running_command(cancel)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    try:
        preparing, release = asyncio.Event(), asyncio.Event()

        async def background_session_ping() -> None:
            # A task that inherited the command, preparing its link meanwhile.
            with scheduler.command_frames_not_counted():
                preparing.set()
                await release.wait()

        task = asyncio.create_task(background_session_ping())
        await preparing.wait()
        scheduler.note_frame_written(cancel)  # The command's own frame.
        assert command.frames_written == 1
        release.set()
        await task
        with scheduler.command_frames_not_counted():
            scheduler.note_frame_written(cancel)  # This task's own preparation.
        assert command.frames_written == 1
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)


@pytest.mark.parametrize(
    ("written", "skipped", "expected"),
    [
        (1, 1, Delivery.PARTIAL),
        (0, 1, Delivery.NONE),
        (1, 0, Delivery.SENT),
        # The controller chose to send nothing: nothing was held back.
        (0, 0, Delivery.SENT),
    ],
)
async def test_a_frame_held_back_without_a_cancellation_is_not_sent(
    written, skipped, expected
) -> None:
    from custom_components.adjustable_bed import command_scheduler as scheduler

    cancel = asyncio.Event()
    command = _running_command(cancel)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    shown: list[Delivery] = []
    try:
        with scheduler.delivered(shown.append):
            for _ in range(written):
                scheduler.note_frame_written(cancel)
            # A deadline or a reply ended the operation: the scheduler's
            # event stays clear.
            for _ in range(skipped):
                scheduler.note_frame_skipped()
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
    assert not cancel.is_set()
    assert shown == [expected]


async def test_a_controller_that_stops_itself_shows_only_what_reached_the_bed(hass) -> None:
    async with beds(hass, 1) as made:
        bed = made.items[0]
        _settings(bed)
        bed.frames = 2  # type: ignore[attr-defined]

        async def bed_reports_done(_controller: SettingsController) -> None:
            # A notification ends the operation after its first frame.
            bed.local_stop.set()  # type: ignore[attr-defined]

        bed.after_frame = bed_reports_done  # type: ignore[attr-defined]
        switch = _entity(AdjustableBedSwitch(bed, SYNCHRO))
        light = _entity(AdjustableBedAssumedLight(bed))
        bed.controller_state[LIGHT_LEVEL] = 3
        with virtual_clock():
            for run in (switch.async_turn_on, light.async_toggle, lambda: _set_level(bed)):
                bed.local_stop = asyncio.Event()  # type: ignore[attr-defined]
                await run()
        # One of each two frames went out, and nothing cancelled the commands.
        assert bed.sent == ["synchro True", "toggle", "level 5"]  # type: ignore[attr-defined]
        assert all(
            record.outcome is CommandOutcome.COMPLETED
            for record in bed._command_scheduler.recent_records
        )
        assert switch.is_on is None
        # The toggle is its first frame, so the light did change.
        assert light.is_on is True
        # The published value is unknown, not the one half sent.
        assert bed.controller_state.get(LIGHT_LEVEL) is None


async def test_a_write_the_link_preparation_hands_to_a_task_is_still_preparation() -> None:
    from custom_components.adjustable_bed import command_scheduler as scheduler

    cancel = asyncio.Event()
    command = _running_command(cancel)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    try:

        async def startup_write() -> None:
            # GoodVibe and SonicSleep shield each write in a task of its own.
            scheduler.note_frame_written(cancel)

        with scheduler.command_frames_not_counted():
            await asyncio.shield(asyncio.create_task(startup_write()))
        assert command.frames_written == 0
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
