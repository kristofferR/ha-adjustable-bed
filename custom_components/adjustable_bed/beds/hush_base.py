"""Hush Base 1.0.5, explicit row126 product and auxiliary policies."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import replace
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ..casper_base_protocol import RGB_TIMERS, Request, alarm_countdown
from ..codec.casper import MUSIC_BLUETOOTH, STOP, alarm_pair, control
from ..hush_protocol import HushMainReceive, decode
from ..profiles.hush import ACTIONS, PROFILES
from .base import ControllerButtonSpec
from .casper_base import CasperBaseController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator


class HushBaseController(CasperBaseController):
    """Reuse proven shared frames with the Hush catalog and page predicates."""

    profiles = PROFILES
    action_catalog = ACTIONS

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator, product=product)
        self._generation = 0
        self._operation_generation: ContextVar[int | None] = ContextVar(
            "hush_operation_generation", default=None
        )
        self._receive = HushMainReceive()
        self._light_seconds = 300
        self._light_color = (255, 255, 255)

    @property
    def supports_hush_base_controls(self) -> bool:
        return True

    @property
    def supports_casper_base_controls(self) -> bool:
        return False

    @property
    def actions(self) -> dict[str, tuple[int, int | None]]:
        return {
            self.action_catalog[i][0]: (self.action_catalog[i][1], self.action_catalog[i][2])
            for group in (self.product[1], self.product[2], self.product[3], self.product[5])
            for i in group
            if self.action_catalog[i][0] != "PhoneLight"
        }

    def alarm_opcode(self, mode: str) -> int:
        for index in self.product[4]:
            name, short, _ = self.action_catalog[index]
            if name == mode:
                return short
        raise ValueError("Alarm position not listed for this product")

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"light_seconds": self._light_seconds, "light_color": list(self._light_color)}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        seconds, rgb = state.get("light_seconds", 300), state.get("light_color", [255] * 3)
        if type(seconds) is not int or not 0 <= seconds <= 65535:
            raise ValueError("Invalid saved light duration")
        if (
            not isinstance(rgb, list)
            or len(rgb) != 3
            or any(type(x) is not int or not 0 <= x <= 255 for x in rgb)
        ):
            raise ValueError("Invalid saved light color")
        self._light_seconds = seconds
        self._light_color = (rgb[0], rgb[1], rgb[2])

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            replace(spec, translation_key="hush_base_action")
            for spec in super().controller_button_specs
        )

    async def _send(self, packet: bytes, *, cleanup: bool = False) -> None:
        client, characteristic, generation = self.client, self._write_char, self._generation
        admitted = self._operation_generation.get()
        if admitted is not None and admitted != generation:
            raise ConnectionError("Hush operation belongs to a previous connection")
        await asyncio.sleep(0.1)
        if (
            client is None
            or characteristic is None
            or not client.is_connected
            or self.client is not client
            or generation != self._generation
        ):
            raise ConnectionError("Hush operation lost its physical connection")
        await self._write_gatt_with_retry(
            characteristic.uuid,
            packet,
            response=self._write_with_response,
            characteristic=characteristic,
            expected_client=client,
            cancel_event=asyncio.Event() if cleanup else None,
        )

    def on_disconnect(self) -> None:
        self._generation += 1
        super().on_disconnect()
        self._receive = HushMainReceive()

    def _build_notification_callback(self) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
        client, generation = self.client, self._generation

        def notify(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self.client is client and self._generation == generation:
                self._on_notification(sender, data)

        return notify

    def _on_notification(self, sender, data: bytearray) -> None:
        if (
            self._notify_char is None
            or self.client is None
            or not self.client.is_connected
            or self._coordinator.controller is not self
        ):
            return
        self.forward_raw_notification(
            self._notify_char.uuid if self._notify_char else "", bytes(data)
        )
        try:
            for packet in self._receive.feed(bytes(data)):
                if event := decode(packet):
                    self._consume(event)
        except (ValueError, IndexError) as err:
            self.forward_controller_state_update("casper_base_error", str(err))
        self._publish()

    def validate_casper_base_request(self, request: Request) -> None:
        op = request.operation
        if op in ("light_rgb", "light_seconds", "light_off") or op.startswith("rgb_"):
            if "light_available" not in self.events:
                raise ValueError("Light page has not been reported")
            if op.startswith("rgb_") != self.product[6]:
                raise ValueError("Operation does not match the Hush light page")
            if op == "rgb_timer" and request.value not in RGB_TIMERS:
                raise ValueError("Unsupported RGB timer duration")
            if op == "rgb_mode" and request.value not in (2, 3, 5):
                raise ValueError("Unsupported colour mode")
            if op == "rgb_groove" and request.value not in (1, 2, 3, 4):
                raise ValueError("Unsupported groove mode")
            return
        super().validate_casper_base_request(request)

    async def async_execute_casper_base_request(self, request: Request) -> None:
        self.validate_casper_base_request(request)
        op = request.operation
        if op in ("alarm", "alarm_cancel"):
            minutes = (
                alarm_countdown(request.hour, request.minute, dt_util.now()) if op == "alarm" else 0
            )
            # Hush save/cancel queues the low frame before the high/mode frame.
            mode = self.alarm_opcode(request.mode) if op == "alarm" else 0
            for packet in reversed(alarm_pair(minutes, mode)):
                await self._send(packet)
        else:
            await super().async_execute_casper_base_request(request)
        if op == "light_seconds":
            self._light_seconds = request.value
        elif op == "light_rgb":
            self._light_color = request.rgb
        self._publish()

    async def async_perform_casper_base_action(
        self, action: str, *, save: bool = False, music_page: bool = False
    ) -> None:
        token = self._operation_generation.set(self._generation)
        try:
            await self._perform_action(action, save=save, music_page=music_page)
        finally:
            self._operation_generation.reset(token)

    async def _perform_action(self, action: str, *, save: bool, music_page: bool) -> None:
        if music_page and action == "MusicSwitchSoundTrack":
            if not self.product[8] or "music_available" not in self.events or save:
                raise ValueError("Music page unavailable")
            now = asyncio.get_running_loop().time()
            if now < self._music_debounce_until:
                return
            self._music_debounce_until = now + 2
            generation = self._generation
            if not self._music_bluetooth:
                await self._send(control(MUSIC_BLUETOOTH, single=self._single, side=0))
            await asyncio.sleep(max(0, now + 0.9 - asyncio.get_running_loop().time()))
            if generation != self._generation:
                raise ConnectionError("Music operation belongs to a previous connection")
            sound_track = next(short for name, short, _ in self.action_catalog if name == action)
            await self._send(control(sound_track, single=self._single, side=0))
            return
        # Every fan icon releases, including modes/timers; text null-long commands
        # are intentionally unavailable instead of emitting the ambiguous zero.
        fan = any(self.action_catalog[i][0] == action for i in self.product[5])
        if not fan:
            await super().async_perform_casper_base_action(action, save=save, music_page=music_page)
            return
        if save:
            raise ValueError("Fan action has no program command")
        try:
            await self._opcode(self.actions[action][0])
        finally:
            await self._opcode(STOP, cleanup=True)

    async def _poll_snore(self, source: str) -> None:
        try:
            while True:
                await asyncio.sleep(3)
                state = self._coordinator.hass.states.get(source)
                try:
                    result = int(state.state) if state is not None else None
                except ValueError:
                    result = None

                async def sample(controller, value=result):
                    if controller is self:
                        await self._snore_result(value)

                await self._coordinator.async_execute_controller_command(
                    sample, cancel_running=False, resource="configuration"
                )
        except ConnectionError, ValueError:
            pass
        finally:
            if self._snore_poll is asyncio.current_task():
                self._snore_poll = None
                self._coordinator.resume_disconnect_timer()
