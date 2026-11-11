"""Luuna + products over the proven Richmat codec and shared product controller."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_PRESETS
from ...codec import richmat as codec
from ...controller_state import StateKey
from ...profiles.luuna import (
    ACTIONS,
    LIGHT_COLORS,
    LIGHT_DURATIONS,
    PROFILES,
    QUERIES,
    QUERY_INTERVAL_S,
    TICK_S,
)
from ..builder import BuildContext
from ..casper_base.controller import CasperBaseController
from ..casper_base.protocol import Event, Request, alarm_countdown
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec
from .protocol import decode

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

LUUNA_MODEL: Final = StateKey[str]("luuna_model")
LUUNA_EVENTS: Final = StateKey[dict[str, object]]("luuna_events")
LUUNA_ERROR: Final = StateKey[str]("luuna_error")
CAPABILITY_WAIT_S: Final = 3
"""HA service admission budget for an asynchronous reply, not a wire cadence."""


def brightness_rgb(rgb: tuple[int, int, int], brightness: float) -> tuple[int, int, int]:
    """Dart truncates the slider percentage and rounds positive channel halves up."""
    opacity = max(0, min(100, math.trunc(brightness))) / 100
    red, green, blue = (math.floor((v / 255 * opacity) * 255 + 0.5) for v in rgb)
    return red, green, blue


class LuunaController(CasperBaseController):
    """Only Luuna's catalog, startup and notification-gated configuration actions."""

    profiles = PROFILES
    action_catalog = ACTIONS

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator, product=product)
        self._generation = 0
        self._capabilities_changed = asyncio.Event()
        self.forward_controller_state_update(LUUNA_ERROR, "")

    @property
    def supports_casper_base_controls(self) -> bool:
        return False

    @property
    def auto_stops_on_idle(self) -> bool:
        """Release ends refresh; the artifact has no live STOP caller."""
        return True

    async def _send(self, packet: bytes, *, cleanup: bool = False) -> None:
        client, characteristic, generation = self.client, self._write_char, self._generation
        await asyncio.sleep(TICK_S)
        if (
            client is None
            or characteristic is None
            or not client.is_connected
            or self.client is not client
            or generation != self._generation
        ):
            raise ConnectionError("Luuna operation lost its physical connection")
        await self._write_gatt_with_retry(
            characteristic.uuid,
            packet,
            response=self._write_with_response,
            characteristic=characteristic,
            expected_client=client,
        )

    async def _initialize(self) -> None:
        if self._notify_char is None:
            raise ValueError("Luuna requires a notification characteristic")
        generation = self._generation
        await self._send(
            codec.function(0, action="deviceFunctionItemExitLimit", single=self._single)
        )
        if generation != self._generation:
            raise ConnectionError("Luuna initialization lost its connection")
        started = asyncio.get_running_loop().time()
        await self._send(codec.calendar(dt_util.now(), build=codec.record_20_len))
        if generation != self._generation:
            raise ConnectionError("Luuna initialization lost its connection")
        if self.product[9]:
            await self._send(codec.record_20_len(6, 3, 0, (0,)))
        for index, (action, code) in enumerate(QUERIES, 1):
            deadline = started + index * QUERY_INTERVAL_S
            await asyncio.sleep(max(0, deadline - asyncio.get_running_loop().time()))
            if generation != self._generation:
                raise ConnectionError("Luuna initialization belongs to a previous connection")
            await self._send(codec.function(code, action=action, single=self._single))

    def on_disconnect(self) -> None:
        self._generation += 1
        self.events.clear()
        self._capabilities_changed.set()
        super().on_disconnect()

    def _build_notification_callback(self) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
        client, generation = self.client, self._generation

        def notify(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self.client is client
                and self._generation == generation
                and self._coordinator.controller is self
            ):
                self._on_notification(sender, data)

        return notify

    def _notification_error(self, message: str) -> None:
        self.forward_controller_state_update(LUUNA_ERROR, message)

    def _decode_notification(self, packet: bytes) -> Event | None:
        return decode(packet)

    def _consume(self, event: Event) -> None:
        # Only these two exact announcements insert pages in Luuna. Other
        # decoded events remain observations, never motors or outgoing commands.
        if event.name == "light_available" and not self.product[6]:
            return
        if event.name == "clock_available" and not self.product[4]:
            return
        self.events[event.name] = event.values
        if event.name in ("clock_available", "light_available"):
            self._capabilities_changed.set()
        if event.name in ("clock_add_ok", "clock_cancel_ok"):
            self.events["clock_status"] = "set" if event.name == "clock_add_ok" else "cancelled"

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            LUUNA_MODEL(self.product[0]),
            LUUNA_EVENTS(dict(self.events)),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "luuna",
                "luuna",
                LUUNA_MODEL,
                "mdi:bed",
                attribute_keys=(LUUNA_EVENTS, LUUNA_ERROR),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            replace(
                spec,
                key=spec.key.replace("casper_", "luuna_", 1),
                translation_key="luuna_massage" if "massage" in spec.key else "luuna_preset",
                card=CARD_MASSAGE if "massage" in spec.key else CARD_PRESETS,
            )
            for spec in super().controller_button_specs
        )

    async def async_perform_casper_base_action(
        self,
        action: str,
        *,
        save: bool = False,
        music_page: bool = False,
    ) -> None:
        item = self.actions.get(action)
        if music_page or item is None or (save and item[1] is None):
            raise ValueError("Action unavailable for this Luuna product")
        code = item[1] if save else item[0]
        assert code is not None
        moving = action.endswith(("Up", "Down"))
        count = (
            (self.leased_hold_refreshes(100) or self._coordinator.motor_pulse_count)
            if moving
            else 1
        )
        generation = self._generation
        # Await each write rather than recreating the app's overlapping timer
        # queue. Ending this cancellable refresh is the complete release.
        for _ in range(count):
            if generation != self._generation:
                raise ConnectionError("Luuna action belongs to a previous connection")
            if self._coordinator.cancel_command.is_set():
                break
            await self._opcode(code)

    async def stop_all(self) -> None:
        """The coordinator cancels the running refresh before calling STOP."""

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    def validate_casper_base_request(self, request: Request) -> None:
        if request.operation not in (
            "alarm",
            "alarm_cancel",
            "light_rgb",
            "light_seconds",
            "light_off",
            "light_warm",
            "light_cold",
            "sleep_name",
            "time_sync",
        ):
            raise ValueError("Unsupported Luuna operation")
        if request.operation == "time_sync":
            return  # Every Luuna product has nonempty alarm actions.
        if request.operation == "light_seconds" and request.value not in LIGHT_DURATIONS:
            raise ValueError("Choose 0, 300, 600 or 900 seconds")
        if request.operation in ("light_warm", "light_cold"):
            if not 0 <= request.value <= 100:
                raise ValueError("Brightness must be 0-100 percent")
            super().validate_casper_base_request(replace(request, operation="light_rgb"))
            return
        super().validate_casper_base_request(request)

    async def async_prepare_request(self, request: Request) -> None:
        """Await this connection's announcement before validating a gated action."""
        gate = (
            "light_available"
            if request.operation.startswith("light_")
            else "clock_available"
            if request.operation in ("alarm", "alarm_cancel")
            else None
        )
        if gate == "light_available" and not self.product[6]:
            self.validate_casper_base_request(request)
        generation = self._generation
        try:
            async with asyncio.timeout(CAPABILITY_WAIT_S):
                while gate is not None and gate not in self.events:
                    self._capabilities_changed.clear()
                    await self._capabilities_changed.wait()
                    if generation != self._generation:
                        raise ConnectionError("Luuna capability preflight lost its connection")
        except TimeoutError:
            raise ValueError(
                "Luuna has not reported the requested capability on this connection"
            ) from None
        self.validate_casper_base_request(request)

    async def async_execute_casper_base_request(self, request: Request) -> None:
        await self.async_prepare_request(request)
        generation = self._generation
        if request.operation in ("alarm", "alarm_cancel"):
            minutes = (
                alarm_countdown(request.hour, request.minute, dt_util.now())
                if request.operation == "alarm"
                else 0
            )
            code = self.alarm_opcode(request.mode) if request.operation == "alarm" else 0
            for packet in codec.countdown(minutes, code):
                if generation != self._generation:
                    raise ConnectionError("Luuna alarm belongs to a previous connection")
                await self._send(packet)
        elif request.operation in ("light_warm", "light_cold"):
            color = LIGHT_COLORS[request.operation.removeprefix("light_")]
            await self._send(codec.rgb(*brightness_rgb(color, request.value)))
        else:
            await super().async_execute_casper_base_request(request)


async def build_controller(ctx: BuildContext) -> LuunaController:
    """The product is explicit, independent of the common transport and name."""
    return LuunaController(ctx.coordinator, product=ctx.variant or "")
