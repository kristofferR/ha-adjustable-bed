"""iFit's connection and gestures, sharing the Okin 5A controller and codec."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_HIDDEN, CARD_LIGHTING
from ...codec.okin_5a import TRANSPORTS
from ...controller_state import StateUpdate
from ...errors import BedCommandTimedOutError, BedNotConnectedError
from ...profiles.ifit import IFIT, MOTORS
from ...profiles.okin_5a import Action
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..catalog_buttons import Kind, catalog_button, save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..okin_7byte import Okin7ByteController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic


class _Elapsed(Exception):
    """A queued frame outlived its gesture."""


def _press(action: Action):
    async def press(controller: BedController) -> None:
        await cast(IfitController, controller).perform_action(action)

    return press


def _save(action: Action):
    async def save(controller: BedController) -> None:
        await cast(IfitController, controller).save_named_preset(action)

    return save


class IfitController(Okin7ByteController):
    """No response parser, inferred state, app name matching or side selector."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=IFIT)
        self._link: _Link | None = None
        self._ready = False
        self._epoch = 0

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        # Release only ends refresh; a later explicit Stop must reach the bed.
        return not CONTROLLER_GESTURE_RELEASE.get()

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return True

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
        ):
            raise BedNotConnectedError()
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()
        transport = TRANSPORTS[IFIT.transport]
        for service in client.services:
            if service.uuid.lower() != transport.service_uuid:
                continue
            write = service.get_characteristic(transport.write_uuid)
            if write is not None and {"write", "write-without-response"} <= set(write.properties):
                self._link = _Link(client, write)
                return
        raise BedNotConnectedError()

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await self._frame(
            link, IFIT.wake[0], asyncio.Event(), self._epoch, response=False, startup=True
        )
        self._live(link)
        if not session.is_current():
            raise BedNotConnectedError()
        self._ready = True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    def on_disconnect(self) -> None:
        self._epoch += 1
        self._link = None
        self._ready = False

    def on_app_state_replaced(self) -> None:
        self.on_disconnect()

    async def stop_notify(self) -> None:
        # Diagnostic capture only installs callbacks; it does not end this link.
        await super().stop_notify()

    async def _frame(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        epoch: int,
        *,
        response: bool = True,
        deadline: float | None = None,
        startup: bool = False,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def check() -> None:
            self._live(link)
            if not startup and not self._ready:
                raise BedNotConnectedError()
            if (
                epoch != self._epoch
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            ):
                raise _Elapsed

        written = False

        def record_write() -> None:
            nonlocal written
            written = True
            if on_write is not None:
                on_write()

        with self.sent_state(
            *self._light_intent(frame),
            is_current=lambda: (
                written
                and self._link is link
                and self.client is link.client
                and link.client.is_connected
                and self._coordinator.controller is self
                and self._epoch == epoch
            ),
        ):
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                frame,
                cancel_event=cancel,
                response=response,
                expected_client=link.client,
                characteristic=link.write,
                before_write=check,
                settle_write=True,
                write_timeout=15,
                track_command_write=not startup,
                on_write=record_write,
            )
        self._live(link)

    def _light_intent(self, frame: bytes) -> tuple[StateUpdate, ...]:
        if frame == IFIT.frame("light_on"):
            return (UNDER_BED_LIGHTS_ON(True),)
        if frame == IFIT.frame("light_off"):
            return (UNDER_BED_LIGHTS_ON(False),)
        if frame == IFIT.frame("light_toggle"):
            known = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
            return (UNDER_BED_LIGHTS_ON(not known if isinstance(known, bool) else None),)
        return ()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        link, epoch = self._live(), self._epoch
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for n in range(repeat_count):
            if n and await self._pause(cancel, repeat_delay_ms / 1000):
                return
            if cancel.is_set():
                return
            await self._frame(link, command, cancel, epoch, on_write=on_write)

    @staticmethod
    async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
        if seconds <= 0:
            return cancel.is_set()
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            return False
        return True

    async def perform_action(self, action: Action, *, fresh: bool = False) -> None:
        """Direct voice forwarding: first write at 250 ms, one toggle or three others."""
        frame = IFIT.frame(action)
        link, epoch = self._live(), self._epoch
        cancel = asyncio.Event() if fresh else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        for tick in range(1, (1 if action == "light_toggle" else IFIT.voice_repeats) + 1):
            if await self._pause(cancel, start + tick * IFIT.voice_tick_ms / 1000 - loop.time()):
                return
            await self._frame(link, frame, cancel, epoch)

    async def _send(self, action: Action) -> None:
        if action in IFIT.refresh_ms and action.startswith("massage_"):
            await self.hold_control(action, 100)
        else:
            await self.perform_action(action)

    async def _recall(self, action: Action) -> None:
        await self.perform_action(action)

    async def _move(self, action: Action) -> None:
        if action not in IFIT.refresh_ms:
            raise NotImplementedError(f"Unsupported iFit movement: {action}")
        await self.hold_control(
            action, self._coordinator.motor_pulse_count * IFIT.refresh_ms[action]
        )

    async def move_legs_up(self) -> None:
        await self._move("legs_up")

    async def move_legs_down(self) -> None:
        await self._move("legs_down")

    async def preset_reading(self) -> None:
        await self._recall("incline")

    async def massage_on(self) -> None:
        await self.perform_action("massage_wave_1")

    async def massage_head_up(self) -> None:
        await self._send("massage_head_up")

    async def massage_head_down(self) -> None:
        await self._send("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self._send("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self._send("massage_foot_down")

    async def lights_off(self) -> None:
        await self.perform_action("light_off")

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            # The card's UP/CANCEL only ends refresh. Explicit Stop is separate.
            self._epoch += 1
            return
        await self._send_stop()

    async def _send_stop(self) -> None:
        self._epoch += 1
        await self.perform_action("stop", fresh=True)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*IFIT.refresh_ms, "light_position", "light_massage")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unsupported iFit held control")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 100 <= duration_ms <= 60000
        ):
            raise ValueError("Choose a duration from 0.1 to 60 seconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = cast(Action, "light_toggle" if control.startswith("light_") else control)
        duration_ms = self.leased_hold_ms(duration_ms)
        loop = asyncio.get_running_loop()
        start = loop.time()
        end = start + duration_ms / 1000
        interval = IFIT.refresh_ms[action] / 1000
        threshold = (
            IFIT.light_massage_threshold_ms
            if control == "light_massage"
            else IFIT.light_position_threshold_ms
        ) / 1000
        link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
        tick = 0
        try:
            while loop.time() < end and not cancel.is_set():
                elapsed = loop.time() - start
                if action == "flat" and elapsed >= IFIT.flat_threshold_ms / 1000:
                    break
                frame_action = (
                    "light_off" if action == "light_toggle" and elapsed >= threshold else action
                )
                frame_end = end
                if action == "flat":
                    frame_end = min(end, start + IFIT.flat_threshold_ms / 1000)
                elif frame_action == "light_toggle":
                    frame_end = min(end, start + threshold)
                try:
                    await self._frame(
                        link, IFIT.frame(frame_action), cancel, epoch, deadline=frame_end
                    )
                except _Elapsed:
                    if (
                        frame_action == "light_toggle"
                        and self._epoch == epoch
                        and loop.time() < end
                    ):
                        # A queued toggle crossed the page's off threshold.
                        continue
                    return
                if frame_action == "light_toggle" and loop.time() >= start + threshold:
                    # The off event became due while the prior toggle settled.
                    continue
                tick = max(tick + 1, ceil((loop.time() - start) / interval))
                if await self._pause(cancel, min(end, start + tick * interval) - loop.time()):
                    break
        except _Elapsed:
            return
        # Screen UP/CANCEL ends refresh. There is no trailing wire release.

    def validate_save(self, preset: str) -> None:
        if preset not in IFIT.save_actions:
            raise ValueError("Choose zero_g, anti_snore, lounge or incline")

    async def save_named_preset(self, preset: str) -> None:
        """Hold Flat and the chosen preset together through its three-second save event."""
        self.validate_save(preset)
        action = cast(Action, preset)
        link, epoch, cancel = self._live(), self._epoch, self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        save_at = start + IFIT.save_threshold_ms / 1000
        # This scope is the app's flat-held latch. Never retain it for a later call.
        tick = 0
        try:
            while loop.time() < save_at and not cancel.is_set():
                if await self._pause(cancel, min(save_at, start + tick * 0.05) - loop.time()):
                    return
                if loop.time() >= save_at:
                    break
                elapsed_ms = tick * 50
                if elapsed_ms % 250 == 0:
                    await self._frame(link, IFIT.frame("flat"), cancel, epoch, deadline=save_at)
                if elapsed_ms % IFIT.refresh_ms[action] == 0:
                    await self._frame(link, IFIT.frame(action), cancel, epoch, deadline=save_at)
                # Do not replay timer slots that elapsed while a write settled.
                tick = max(tick + 1, ceil((loop.time() - start) / 0.05))
        except _Elapsed:
            if self._epoch != epoch:
                raise BedNotConnectedError from None
            # The last refresh waited past the threshold; SAVE is still due.
        if await self._pause(cancel, save_at - loop.time()):
            return

        saved = False

        def record_save() -> None:
            nonlocal saved
            saved = True

        try:
            await self._frame(
                link, IFIT.frame(IFIT.save_actions[action]), cancel, epoch, on_write=record_save
            )
        except _Elapsed:
            raise BedNotConnectedError from None
        if not saved and not cancel.is_set():
            raise BedCommandTimedOutError
        # Both virtual pointers release here, including cancellation or write failure.

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=lambda c, a=axis: cast(IfitController, c)._move(cast(Action, f"{a}_up")),
                close_fn=lambda c, a=axis: cast(IfitController, c)._move(cast(Action, f"{a}_down")),
                stop_fn=lambda c: c.stop_all(),
                scheduler_resource="*",
                timed_move_fn=lambda c, up, ms, a=axis: cast(IfitController, c).hold_control(
                    f"{a}_{'up' if up else 'down'}", ms
                ),
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                    release_button_key="ifit_release",
                ),
            )
            for axis in MOTORS
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        controls = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_anti_snore": "anti_snore",
            "preset_lounge": "lounge",
            "preset_incline": "incline",
            "preset_reading": "incline",
            "massage_all_off": "massage_off",
            "toggle_light": "light_position",
        }
        controls.update(
            {
                f"massage_{zone}_{direction}": f"massage_{zone}_{direction}"
                for zone in ("head", "foot")
                for direction in ("up", "down")
            }
        )
        if (control := controls.get(key)) is not None:
            return ControllerHoldSpec(control, release_button_key="ifit_release")
        return None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "ifit_release",
                "Release held control",
                lambda c: cast(IfitController, c)._noop(),
                release_only=True,
                translation_key="ifit_release",
                card=CARD_HIDDEN,
            )
        ]
        for action in (
            "inverse",
            "stretch",
            "massage_wave_1",
            "massage_wave_2",
            "massage_wave_3",
            "head_up_max",
            "head_down_max",
            "feet_up_max",
            "feet_down_max",
            "legs_up_max",
            "legs_down_max",
        ):
            key = cast(Action, action)
            spec = catalog_button(
                key,
                key.replace("_", " "),
                _press(key),
                kind=Kind.MASSAGE if key.startswith("massage") else Kind.PRESET,
                hold=ControllerHoldSpec(key, release_button_key="ifit_release")
                if key in IFIT.refresh_ms
                else None,
            )
            assert spec is not None
            specs.append(spec)
        for action in IFIT.save_actions:
            specs.append(
                save_button(
                    f"ifit_save_{action}", f"Save {action.replace('_', ' ')}", _save(action)
                )
            )
        for control, label in (
            ("light_position", "Light (position page)"),
            ("light_massage", "Light (massage page)"),
        ):
            specs.append(
                ControllerButtonSpec(
                    control,
                    label,
                    _press("light_toggle"),
                    card=CARD_LIGHTING,
                    translation_key="catalog_light",
                    translation_placeholders={"action": label},
                    hold=ControllerHoldSpec(control, release_button_key="ifit_release"),
                )
            )
        return tuple(specs)

    async def _noop(self) -> None:
        return None
