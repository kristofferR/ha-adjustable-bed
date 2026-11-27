"""Comfort Bed's bounded enum86 controls over the shared Richmat motion path."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from functools import partial
from typing import TYPE_CHECKING, Final

from ...card import CARD_LIGHT_TOGGLE, CARD_PRESET_SAVE, CARD_UTILITY
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped, note_frame_written
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, failed, invalid
from ...profiles.comfort_bed import (
    LONG_PRESS_MS,
    MENU_DELAY_S,
    PROFILE,
    QUERIES,
    RX_TIMEOUT_S,
    SAVES,
    TEXT_LONG,
    TICK_S,
    TIMER_CONTROLS,
)
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerSelectSpec,
    MotorControlSpec,
)
from ..richmat.atlas_lift import AtlasLiftController, _Link
from .receive import EXACT, CommonReceive

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

SIDE: Final = StateKey[str | None]("comfort_bed_side")
_SIDE: ContextVar[tuple[BedController, int] | None] = ContextVar(
    "comfort_bed_motion_side", default=None
)


def select_link(client: BleakClient) -> _Link:
    """Reject mixed services rather than pairing one route's encoder with another TX."""
    routes = {
        codec.TRANSPORTS[key].service_uuid: codec.TRANSPORTS[key] for key in PROFILE.transports
    }
    matches = [(s, routes[s.uuid.lower()]) for s in client.services if s.uuid.lower() in routes]
    if len(matches) != 1:
        raise failed("comfort_bed_gatt")
    service, route = matches[0]
    writes = [
        c
        for c in service.characteristics
        if c.uuid.lower() == route.write_uuid and "write" in c.properties
    ]
    notify = next((c for c in service.characteristics if "notify" in c.properties), None)
    if len(writes) != 1 or notify is None:
        raise failed("comfort_bed_gatt")
    return _Link(client, writes[0], notify, route.single)


async def invoke(controller: BedController, code: int) -> None:
    if not isinstance(controller, ComfortBedController):
        raise invalid("option_unavailable")
    await controller.write_command(controller._build_command(code))


class ComfortBedController(AtlasLiftController):
    """One explicit product, with session-bound writes, cleanup and observations."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=PROFILE)
        self._is_current: Callable[[], bool] = lambda: False
        self._side = 0
        self._receive = CommonReceive()
        self._features: dict[str, bool] = {}
        self._rx_expiry: asyncio.TimerHandle | None = None
        self._next_write = 0.0
        self.forward_controller_state_updates(SIDE("left"), MASSAGE_TIMER_MINUTES(None))

    def _current_link(self, expected: _Link | None = None) -> _Link:
        link = super()._current_link(expected)
        if not self._is_current():
            raise BedNotConnectedError
        return link

    def _encode(self, link: _Link, command_byte: int) -> bytes:
        scope = _SIDE.get()
        side = scope[1] if scope is not None and scope[0] is self else self._side
        return codec.function(command_byte, side, single=link.single)

    async def async_on_connect(self, session: ControllerSession) -> None:
        client = session.client
        if client is None or not session.is_current():
            raise BedNotConnectedError
        self.on_disconnect()
        self._is_current = session.is_current
        self._link = link = select_link(client)
        self._next_write = asyncio.get_running_loop().time() + TICK_S
        try:
            await session.async_start_notify()
            await self._startup(link, 0)
            await asyncio.sleep(MENU_DELAY_S)
            self._current_link(link)
            for index in (1, 2):
                await self._startup(link, index)
        except BaseException:
            # Revoke callbacks and pending commands even when notify/initialization fails.
            self.on_disconnect()
            raise

    async def _startup(self, link: _Link, index: int) -> None:
        action, code = QUERIES[index]
        await self._write_on(
            link,
            codec.function(code, action=action, single=link.single),
            asyncio.Event(),
            track_command_write=False,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._current_link()
        assert link.notify is not None

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or not self._notifying
                or not self._is_current()
                or not link.client.is_connected
                or self.client is not link.client
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for frame in self._receive.feed(bytes(data)):
                if event := EXACT.get(frame):
                    self._features[event] = True
            if self._rx_expiry is not None:
                self._rx_expiry.cancel()
            self._rx_expiry = asyncio.get_running_loop().call_later(
                RX_TIMEOUT_S, self._receive.expire
            )

        async with self.ble_lock:
            self._current_link(link)
            if self._notifying:
                return
            self._notifying = True
            try:
                await link.client.start_notify(link.notify, receive)
                self._current_link(link)
            except BaseException:
                self._notifying = False
                raise

    async def stop_notify(self) -> None:
        try:
            await super().stop_notify()
        finally:
            self.on_disconnect()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._is_current = lambda: False
        if self._rx_expiry is not None:
            self._rx_expiry.cancel()
            self._rx_expiry = None
        self._receive.expire()
        self._features.clear()
        self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, None)

    async def _write_on(
        self,
        link: _Link,
        command: bytes,
        cancel: asyncio.Event,
        *,
        before_write: Callable[[], None] | None = None,
        track_command_write: bool = True,
    ) -> None:
        caller = asyncio.current_task()
        self._current_link(link)
        await cancellable(
            asyncio.sleep(max(0, self._next_write - asyncio.get_running_loop().time())), cancel
        )

        async def write() -> None:
            async with self.ble_lock:
                self._current_link(link)
                if cancel.is_set() or caller is not None and caller.cancelling():
                    note_frame_skipped()
                    raise asyncio.CancelledError
                if before_write is not None:
                    before_write()
                response = "write-without-response" not in link.tx.properties
                self._record_command_trace(
                    link.tx.uuid, command, response=response, characteristic=link.tx
                )
                self._next_write = asyncio.get_running_loop().time() + TICK_S
                # A failed app FIFO item is not retried. Drain an admitted ATT write
                # before movement cleanup; never send a stale frame on a replacement.
                await link.client.write_gatt_char(link.tx, command, response=response)
                if track_command_write:
                    note_frame_written(cancel)

        await settled(write(), eager_start=True)

    async def _move_with_stop(self, command_byte: int, *, duration_ms: int | None = None) -> None:
        token = _SIDE.set((self, self._side))
        try:
            await super()._move_with_stop(command_byte, duration_ms=duration_ms)
        finally:
            _SIDE.reset(token)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            *super().motor_control_specs,
            MotorControlSpec(
                "head_feet",
                "head_feet",
                lambda c: _combined(c, True, None),
                lambda c: _combined(c, False, None),
                lambda c: c.stop_all(),
                stop_scope="side",
                timed_move_fn=lambda c, up, ms: _combined(c, up, ms),
            ),
        )

    async def move_head_and_feet_up(self) -> None:
        await self._move("head_feet_up")

    async def move_head_and_feet_down(self) -> None:
        await self._move("head_feet_down")

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return False  # A button does not prove a stateful light or RGB page.

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(TEXT_LONG)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in TEXT_LONG:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        link, side = self._current_link(), self._side
        await cancellable(
            asyncio.sleep(min(duration_ms, LONG_PRESS_MS) / 1000), self._coordinator.cancel_command
        )
        if duration_ms >= LONG_PRESS_MS:
            await self._write_on(
                link,
                codec.function(TEXT_LONG[control], side, single=link.single),
                self._coordinator.cancel_command,
            )

    @property
    def persisted_app_state_key(self) -> str:
        return "comfort_bed:86"

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {"side": "right" if self._side else "left"}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        side = state.get("side", "left")
        if not isinstance(side, str) or side not in ("left", "right"):
            # The coordinator resets a rejected stored record to this profile's default.
            raise ValueError
        self._select_side(side)

    def _select_side(self, side: str) -> None:
        if side not in ("left", "right"):
            raise invalid("option_unavailable")
        selected = int(side == "right")
        if self._side != selected:
            self.forward_controller_state_update(MASSAGE_TIMER_MINUTES, None)
        self._side = selected
        self.forward_controller_state_update(SIDE, side)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                "comfort_bed_side",
                "comfort_bed_side",
                SIDE,
                ("left", "right"),
                lambda c, value: _select(c, value),
                local_select_fn=self._select_side,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"comfort_bed_capability_replies": dict(self._features)}

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return sorted(TIMER_CONTROLS)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in TIMER_CONTROLS:
            raise invalid("option_unavailable")
        link, side = self._current_link(), self._side
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes),
            is_current=lambda: (
                self._link is link
                and self.client is link.client
                and link.client.is_connected
                and self._is_current()
                and self._side == side
            ),
        ):
            await self._write_on(
                link,
                codec.function(self._code(TIMER_CONTROLS[minutes]), side, single=link.single),
                self._coordinator.cancel_command,
            )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        saves = tuple(
            ControllerButtonSpec(
                "comfort_bed_save_" + key,
                "Save " + key.replace("_", " "),
                partial(invoke, code=code),
                translation_key="catalog_save",
                translation_placeholders={"preset": key.replace("_", " ")},
                card=CARD_PRESET_SAVE,
                requires_confirmation=True,
                combine_sides=True,
            )
            for key, code in SAVES.items()
        )
        assert PROFILE.codes is not None
        buttons = tuple(
            catalog_button(
                "comfort_bed_" + key,
                key.replace("_", " ").capitalize(),
                partial(invoke, code=PROFILE.codes[key]),
                kind=Kind.MASSAGE,
                combine_sides=True,
            )
            for key in (
                "massage_head_up",
                "massage_foot_up",
                "massage_mode",
                "massage_off",
            )
        )
        return (
            *saves,
            *(spec for spec in buttons if spec is not None),
            ControllerButtonSpec(
                "comfort_bed_light_toggle",
                "Bed light",
                partial(invoke, code=self._code("light_toggle")),
                translation_key="lights_toggle",
                card=CARD_LIGHT_TOGGLE,
            ),
            ControllerButtonSpec(
                "comfort_bed_reset",
                "Reset",
                partial(invoke, code=self._code("flat")),
                hold=ControllerHoldSpec("reset"),
                card=CARD_UTILITY,
            ),
            ControllerButtonSpec(
                "comfort_bed_sync",
                "Sync on",
                partial(invoke, code=self._code("sync_on")),
                hold=ControllerHoldSpec("sync"),
                card=CARD_UTILITY,
            ),
        )


async def _combined(controller: BedController, up: bool, duration_ms: int | None) -> None:
    if not isinstance(controller, ComfortBedController):
        raise invalid("option_unavailable")
    await controller._move_with_stop(
        controller._code("head_feet_up" if up else "head_feet_down"), duration_ms=duration_ms
    )


async def _select(controller: BedController, side: str) -> None:
    if not isinstance(controller, ComfortBedController):
        raise invalid("option_unavailable")
    controller._select_side(side)
