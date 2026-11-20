"""Super Colchones product controls on one captured direct BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.const import STATE_UNKNOWN

from ...codec import richmat as codec
from ...command_scheduler import (
    current_command_context,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...const import CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...profiles.super_colchones import (
    ACTIONS,
    DIRECTIONS,
    PROFILES,
    ROUTES,
    STARTUP,
    TICK_S,
    SuperColchonesProfile,
)
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .receive import Receiver, decode

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator

PRODUCT: Final = StateKey[str]("super_colchones_product")
OBSERVATIONS: Final = StateKey[dict[str, object]]("super_colchones_observations")
# HA scheduling allowance at a tick exactly on the requested end boundary.
# This is not a hardware timing value; delayed ordinary ticks still expire.
DISPATCH_JITTER_S: Final = 0.005



@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    raw: bool
    owner: AdjustableBedCoordinator
    product: str


class SuperColchonesController(ProfileExecution[SuperColchonesProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str | None = None) -> None:
        super().__init__(coordinator)
        self._configured_variant = coordinator.entry.data.get(CONF_PROTOCOL_VARIANT)
        key = product or self._configured_variant or "afeg302"
        if key == "auto":
            key = "afeg302"
        if key not in PROFILES:
            raise invalid("super_colchones_control")
        self.profile = PROFILES[key]
        self._link: Link | None = None
        self._receiver = Receiver()
        self._observations: dict[str, object] = {}
        self._cleanup_context: CommandContext | None = None


    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.TRANSPORTS["n1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        # Held motion owns its release; a second generic release is unnecessary.
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        """Proven alternate bytes, with qualified programming intent."""
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2 if "memory_2" in self.profile.actions else 1

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return "light" in self.profile.actions

    @property
    def supports_light_toggle_control(self) -> bool:
        return "light" in self.profile.actions

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    @property
    def replaced_standard_button_keys(self) -> frozenset[str]:
        return frozenset(f"program_memory_{slot}" for slot in range(1, self.memory_slot_count + 1))

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return "timer_10" in self.profile.actions

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage_timer else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        # All-off is a distinct massage action, not a timer duration.
        return False

    @property
    def position_number_specs(self) -> tuple[()]:
        return ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in DIRECTIONS if key in self.profile.actions)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key, key, partial(_action, action=axis + "_up"), partial(_action, action=axis + "_down"),
                lambda c: c.stop_all(), scheduler_resource="*",
                hold=ControllerMotorHoldSpec(axis + "_up", axis + "_down", press_is_native=True, stop_scope="side"),
            )
            for key, axis in (("back", "head"), ("legs", "foot"), ("lumbar", "lumbar"))
            if axis + "_up" in self.profile.actions
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        for key in self.profile.actions:
            if key in DIRECTIONS or key in ("flat", "light", "massage_off") or key.startswith("timer_"):
                continue
            action = ACTIONS[key]
            # Numbered recalls use the standard memory service/entity surface.
            if not key.startswith("memory_") and key not in ("zero_gravity", "anti_snore"):
                kind = Kind.MASSAGE if key.startswith("massage_") else Kind.LIGHT if key == "light" else Kind.PRESET
                spec = catalog_button("super_colchones_" + key, action.label, partial(_action, action=key), kind=kind)
                if spec is not None:
                    specs.append(spec)
            if action.alternate is not None:
                spec = catalog_button(
                    "program_memory_" + key[-1] if key.startswith("memory_") else "super_colchones_save_" + key,
                    "Save " + action.label, partial(_action, action=key, alternate=True), kind=Kind.SAVE,
                )
                if spec is not None:
                    specs.append(spec)
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (ControllerStateSensorSpec("super_colchones", "super_colchones", PRODUCT, "mdi:bed", attribute_keys=(OBSERVATIONS,), entity_registry_enabled_default=False),)

    def _current(self, link: Link) -> bool:
        return (
            self._link is link and self._coordinator is link.owner
            and self._coordinator.controller is self and self.client is link.client
            and link.client.is_connected and self.profile.key == link.product
            and self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT) == self._configured_variant
            and self.command_side is None
        )

    def _live(self, link: Link | None = None) -> Link:
        current = link or self._link
        if current is None or not self._current(current):
            raise failed("super_colchones_session")
        return current

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise failed("super_colchones_session")
        write = notify = None
        raw = False
        routes = {codec.TRANSPORTS[key].service_uuid.lower(): (key, codec.TRANSPORTS[key]) for key in ROUTES}
        for service in client.services:
            match = routes.get(service.uuid.lower())
            if match is None:
                continue
            key, route = match
            raw = key != "n1"
            if write is None:
                write = next((c for c in service.characteristics if c.uuid.lower() == route.write_uuid.lower() and "write" in c.properties), None)
            if notify is None:
                notify = next((c for c in service.characteristics if "notify" in c.properties), None)
        if write is None or notify is None:
            raise failed("super_colchones_route")
        link = self._link = Link(client, write, notify, raw, self._coordinator, self.profile.key)

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(link):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for frame in self._receiver.feed(bytes(data)):
                for event in decode(frame):
                    self._observations[event.name] = event.value if event.value is not None else True
            self.forward_controller_state_updates(PRODUCT(self.profile.label), OBSERVATIONS(dict(self._observations)))

        await client.start_notify(notify, receive)
        self._live(link)
        for name, code in STARTUP:
            await self._send(link, self.profile.frame(code, raw=raw, action=name), asyncio.Event(), count=False)
        self._live(link)
        self.forward_controller_state_updates(PRODUCT(self.profile.label), OBSERVATIONS(dict(self._observations)), MASSAGE_TIMER_MINUTES(STATE_UNKNOWN))

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._cleanup_context = None
        self._receiver.close()
        self._observations.clear()
        if self._coordinator.controller is self:
            self.forward_controller_state_updates(OBSERVATIONS({}), MASSAGE_TIMER_MINUTES(STATE_UNKNOWN))

    async def _send(self, link: Link, packet: bytes, cancel: asyncio.Event, *, count: bool = True, before_write: Callable[[], None] | None = None, expires_at: float | None = None) -> bool:
        async def write() -> bool:
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set() or expires_at is not None and monotonic() > expires_at:
                    if count:
                        note_frame_skipped()
                    return False
                response = "write-without-response" not in link.write.properties
                self._record_command_trace(link.write.uuid, packet, response=response, characteristic=link.write)
                if before_write is not None:
                    before_write()
                async with asyncio.timeout(5):
                    await link.client.write_gatt_char(link.write, packet, response=response)
                if count:
                    note_frame_written(cancel)
                else:
                    note_write_not_counted()
                return True
        return await settled(write())

    async def action(self, action: str, *, alternate: bool = False) -> None:
        if action not in self.profile.actions or alternate and ACTIONS[action].alternate is None:
            raise invalid("super_colchones_control")
        if action in DIRECTIONS:
            await self.hold_control(action, self.leased_hold_ms(self._coordinator.motor_pulse_count * 100))
            return
        link = self._live()
        item = ACTIONS[action]
        code = item.alternate if alternate else item.code
        assert code is not None
        await self._send(link, self.profile.frame(code, raw=link.raw), self._coordinator.cancel_command)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or isinstance(duration_ms, bool) or not 0 < duration_ms <= 60000:
            raise invalid("super_colchones_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        cancel = self._coordinator.cancel_command
        started = monotonic()
        hold_ms = self.leased_hold_ms(duration_ms)
        deadline = started + hold_ms / 1000
        tick = 1
        next_tick = started + TICK_S
        context = current_command_context()
        attempted = False

        def mark_attempted() -> None:
            nonlocal attempted
            attempted = True

        try:
            while True:
                try:
                    await _pause(max(0, min(next_tick, deadline) - monotonic()), cancel)
                except asyncio.CancelledError:
                    if not attempted:
                        note_frame_skipped()  # The intended first motion frame was held back.
                    raise
                if tick * 100 > hold_ms:
                    break
                expires_at = deadline + (DISPATCH_JITTER_S if tick * 100 == hold_ms else 0)
                if cancel.is_set() or monotonic() > expires_at:
                    note_frame_skipped()
                    break
                self._live(link)
                if not await self._send(link, self.profile.frame(ACTIONS[control].code, raw=link.raw), cancel, before_write=mark_attempted, expires_at=expires_at):
                    break
                # Stay on the source's periodic cadence. A slow write never
                # builds a backlog of old ticks to replay on the radio.
                tick = max(tick + 1, int((monotonic() - started) / TICK_S) + 1)
                next_tick = started + tick * TICK_S
        finally:
            if attempted and self._current(link):
                await self._send(link, self.profile.frame(codec.STOP, raw=link.raw), asyncio.Event(), count=False)
                if context is not None:
                    context.cleanup_stop_sent = True
                    self._cleanup_context = context

    async def stop_all(self) -> None:
        """A scheduler STOP cancels/drains its owner; local STOP never cancels a pair."""
        link = self._live()
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted is self._cleanup_context and preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    self._cleanup_context = None
                    return
        await self._send(link, self.profile.frame(codec.STOP, raw=link.raw), asyncio.Event(), count=False)

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = move_lumbar_stop = stop_all

    async def move_back_up(self) -> None:
        await self.action("head_up")

    async def move_back_down(self) -> None:
        await self.action("head_down")

    move_head_up = move_back_up
    move_head_down = move_back_down

    async def move_legs_up(self) -> None:
        await self.action("foot_up")

    async def move_legs_down(self) -> None:
        await self.action("foot_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def move_lumbar_up(self) -> None:
        await self.action("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.action("lumbar_down")

    async def preset_flat(self) -> None:
        await self.action("flat")

    async def preset_zero_g(self) -> None:
        await self.action("zero_gravity")

    async def preset_anti_snore(self) -> None:
        await self.action("anti_snore")

    async def lights_toggle(self) -> None:
        await self.action("light")

    def validate_memory_recall(self, memory_num: int) -> None:
        if isinstance(memory_num, bool) or not 1 <= memory_num <= self.memory_slot_count:
            raise invalid("super_colchones_control")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_{memory_num}", alternate=True)

    @property
    def supports_massage_off_control(self) -> bool:
        return "massage_off" in self.profile.actions

    async def massage_off(self) -> None:
        await self.action("massage_off")

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid("super_colchones_control")
        link = self._live()
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._current(link)):
            await self.action(f"timer_{minutes}")


async def _action(controller: BedController, action: str, *, alternate: bool = False) -> None:
    if not isinstance(controller, SuperColchonesController):
        raise invalid("super_colchones_control")
    await controller.action(action, alternate=alternate)


async def _pause(seconds: float, cancel: asyncio.Event) -> None:
    await cancellable(asyncio.sleep(seconds), cancel)


async def build_controller(ctx: BuildContext) -> SuperColchonesController:
    return SuperColchonesController(ctx.coordinator, product=ctx.variant)
