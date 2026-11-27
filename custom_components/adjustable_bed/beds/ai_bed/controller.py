"""Bounded AI Bed routes with captured-link writes and route-specific release."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_PRESET_SAVE, CARD_PRESETS, CARD_UTILITY
from ...codec import ai_bed as codec
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.ai_bed import PROFILES, Profile, esp_name
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
)
from ..lifecycle import ControllerSession
from .requests import Request

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

HEAT = StateKey[int | None]("ai_bed_heat")
LEFT = StateKey[int | None]("ai_bed_waist_left")
RIGHT = StateKey[int | None]("ai_bed_waist_right")
RAW = StateKey[str | None]("ai_bed_raw_state")
AUTH = StateKey[int | None]("ai_bed_auth")
CAPS = StateKey[int | None]("ai_bed_capabilities")
FIRMWARE = StateKey[str | None]("ai_bed_firmware")
TARGET = StateKey[str | None]("ai_bed_build_target")
CLOCK_ACK = StateKey[str | None]("ai_bed_clock_ack")
MASSAGE_MODE = StateKey[str | None]("ai_bed_massage_mode")
MASSAGE_HEAD = StateKey[bool | None]("ai_bed_massage_head")
MASSAGE_FOOT = StateKey[bool | None]("ai_bed_massage_foot")
MASSAGE_BOTH = StateKey[bool | None]("ai_bed_massage_both")


@dataclass(eq=False, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    dead: asyncio.Event = field(default_factory=asyncio.Event)
    chunks: dict[int, str] = field(default_factory=dict)
    chunk_count: int | None = None
    target_complete: bool = False
    pairing_sent: bool = False
    clock_pending: bool = False
    revision: int = 0
    strengths: dict[int, tuple[int, int]] = field(default_factory=dict)
    strength_reply: asyncio.Event = field(default_factory=asyncio.Event)
    schedule_reply: asyncio.Event = field(default_factory=asyncio.Event)
    schedules: dict[str, int] | None = None
    clock_done: asyncio.Event = field(default_factory=asyncio.Event)


async def pause(seconds: float, *events: asyncio.Event) -> bool:
    if any(event.is_set() for event in events):
        return True
    tasks = [asyncio.create_task(event.wait()) for event in events]
    try:
        done, _ = await asyncio.wait(tasks, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        return bool(done)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def press(controller: BedController, action: str) -> None:
    await require_controller(controller, AiBedController).action(action)


async def set_level(controller: BedController, value: float, *, name: str) -> None:
    await require_controller(controller, AiBedController).set_level(name, int(value))


async def set_massage(controller: BedController, on: bool, *, zone: str) -> None:
    await require_controller(controller, AiBedController).set_massage(zone, on)


async def select_massage_mode(controller: BedController, option: str) -> None:
    bed = require_controller(controller, AiBedController)
    link = bed._live()
    if option not in ("1", "2", "3"):
        raise ValueError("Select a supported massage mode")
    with bed.sent_state(MASSAGE_MODE(option), is_current=lambda: bed._current(link)):
        await bed.action(f"massage_mode_{option}")


class AiBedController(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, route: str, name: str = "") -> None:
        super().__init__(coordinator)
        self.profile: Profile = PROFILES[route]
        self.name = name
        self._link: Link | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._alarm_check: tuple[Link, int, AlarmRequest] | None = None
        self._active_motion: Link | None = None
        self._pump_cache: dict[str, int] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.write

    @property
    def supports_motor_control(self) -> bool:
        # App-labelled controls avoid assigning unknown physical axes or units.
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            k
            for k, v in self.profile.actions.items()
            if v.motion or self.profile.key == "limos" and not v.save
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                f"ai_bed_{key}",
                action.label,
                partial(press, action=key),
                translation_key=f"ai_bed_{key}",
                hold=ControllerHoldSpec(key) if key in self.held_control_options else None,
                requires_confirmation=action.save,
                card=CARD_UTILITY
                if action.motion
                else CARD_PRESET_SAVE
                if action.save
                else CARD_PRESETS,
            )
            for key, action in self.profile.actions.items()
        ]
        if self.profile.key == "305":
            for key, label in FIXED_LABELS.items():
                if key.startswith(("lamp_", "massage_")):
                    continue
                if key.startswith("qc_") and not (esp_name(self.name) and "M3" not in self.name):
                    continue
                specs.append(
                    ControllerButtonSpec(
                        f"ai_bed_{key}",
                        label,
                        partial(press, action=key),
                        translation_key=f"ai_bed_{key}",
                        diagnostic=key.startswith("qc_") or key in DIAGNOSTICS,
                        requires_confirmation=key == "calibrate",
                        card=CARD_UTILITY,
                    )
                )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.profile.key != "305":
            return ()
        return tuple(
            ControllerNumberSpec(
                f"ai_bed_{key}",
                f"ai_bed_{key}",
                state,
                low,
                high,
                step,
                partial(set_level, name=key),
                card=CARD_UTILITY,
            )
            for key, state, low, high, step in (
                ("heat", HEAT, 0, 4, 1),
                ("waist_left", LEFT, 5, 100, 5),
                ("waist_right", RIGHT, 5, 100, 5),
            )
        )

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        state = self._coordinator.controller_state
        return {str(key): state.get(key) for key in (RAW, AUTH, CAPS, FIRMWARE, TARGET, CLOCK_ACK)}

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.key == "305"

    @property
    def supports_lights(self) -> bool:
        return self.profile.key == "305"

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def lights_on(self) -> None:
        await self.action("lamp_on")

    async def lights_off(self) -> None:
        await self.action("lamp_off")

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if self.profile.key != "305":
            return ()
        return tuple(
            ControllerSwitchSpec(
                f"ai_bed_massage_{zone}",
                f"ai_bed_massage_{zone}",
                partial(set_massage, zone=zone),
                state_key=key,
                assumed_state=True,
                card=CARD_MASSAGE,
            )
            for zone, key in (
                ("head", MASSAGE_HEAD),
                ("foot", MASSAGE_FOOT),
                ("both", MASSAGE_BOTH),
            )
        )

    async def set_massage(self, zone: str, on: bool) -> None:
        if zone not in ("head", "foot", "both"):
            raise ValueError("Select a supported massage zone")
        link = self._live()
        state = self._coordinator.controller_state
        head = on if zone in ("head", "both") else state.get(MASSAGE_HEAD)
        foot = on if zone in ("foot", "both") else state.get(MASSAGE_FOOT)
        both = False if head is False or foot is False else True if head and foot else None
        with self.sent_state(
            MASSAGE_HEAD(head),
            MASSAGE_FOOT(foot),
            MASSAGE_BOTH(both),
            is_current=lambda: self._current(link),
        ):
            await self.action(f"massage_{zone}_{'on' if on else 'off'}")

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.profile.key != "305":
            return ()
        return (
            ControllerSelectSpec(
                "ai_bed_massage_mode",
                "ai_bed_massage_mode",
                MASSAGE_MODE,
                ("1", "2", "3"),
                select_massage_mode,
                card=CARD_MASSAGE,
            ),
        )

    @property
    def supports_massage(self) -> bool:
        return self.profile.key == "305"

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_timer(self) -> bool:
        return self.supports_massage

    @property
    def massage_timer_is_assumed(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise ValueError("Select a supported massage timer")
        link = self._live()
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._current(link)
        ):
            await self._send(
                link,
                codec.frame(*FIXED[f"massage_timer_{minutes}"]),
                self._coordinator.cancel_command,
            )

    def _live(self) -> Link:
        link = self._link
        if link is None or not self._current(link):
            raise BleakError("AI Bed connection changed")
        return link

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and not link.dead.is_set()
        )

    def _spawn(self, operation: Coroutine[Any, Any, None]) -> None:
        task = self._coordinator.hass.async_create_background_task(operation, "AI Bed session")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _send(
        self,
        link: Link,
        packet: bytes,
        cancel: asyncio.Event | None = None,
        *,
        reliable: bool = False,
        heartbeat: bool = False,
        mutation: bool = False,
        expected_revision: int | None = None,
        on_attempt: Callable[[], None] | None = None,
    ) -> bool:
        def skipped() -> bool:
            context = current_command_context()
            if context is not None and cancel is context.cancel_event and not heartbeat:
                note_frame_skipped()
            return False

        async with self._ble_lock:
            if not self._current(link) or cancel is not None and cancel.is_set():
                return skipped()
            if expected_revision is not None and link.revision != expected_revision:
                raise ValueError("AI Bed state changed after preflight")
            properties = link.write.properties
            response = (
                "write" in properties if reliable else "write-without-response" not in properties
            )
            if heartbeat:
                response = False
            if mutation:
                # Invalidate before the attempt, even if transport fails or is cancelled.
                link.revision += 1
                self._alarm_check = None
                link.schedules = None
                link.schedule_reply.clear()
            for _attempt in range(3 if reliable else 1):
                if not self._current(link) or cancel is not None and cancel.is_set():
                    return skipped()
                self._record_command_trace(
                    self.profile.write, packet, response=response, characteristic=link.write
                )
                try:

                    async def write() -> None:
                        if on_attempt is not None:
                            on_attempt()
                        async with asyncio.timeout(2 if reliable else 10):
                            await link.client.write_gatt_char(link.write, packet, response=response)
                        note_frame_written(cancel)

                    await settled(write())
                    if reliable and not response:
                        await pause(0.04, link.dead)
                    return True if self._current(link) else skipped()
                except BleakError, TimeoutError:
                    if not reliable:
                        raise
                    await pause(0.12, link.dead)
            return skipped()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self.profile.key == "unselected":
            raise ValueError("Choose an AI Bed route in Reconfigure")
        client = self.client
        if client is None or not client.is_connected:
            raise BleakError("AI Bed is disconnected")
        if self._link is not None and self._current(self._link):
            return
        service = client.services.get_service(self.profile.service)
        write = service.get_characteristic(self.profile.write) if service else None
        notify = service.get_characteristic(self.profile.notify) if service else None
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
        ):
            raise BleakError("AI Bed selected route GATT is unavailable")
        self.on_disconnect()
        link = self._link = Link(client, write, notify)

        def notification(_sender, value: bytearray) -> None:
            if self._current(link):
                self._receive(link, bytes(value))

        if {"notify", "indicate"}.intersection(notify.properties):
            await client.start_notify(notify, notification)
        if not self._current(link):
            raise BleakError("AI Bed changed during notification setup")
        if self.profile.key == "305":
            self._spawn(self._heartbeat(link))

    async def async_on_connect(self, session: ControllerSession) -> None:
        # Direct-bed notifications remain useful when position sensing is disabled.
        await self.start_notify()

    async def async_after_connect(self, session: ControllerSession) -> None:
        if self.profile.key == "305":
            link = self._live()
            self._spawn(self._initial_clock(link))

    async def _initial_clock(self, link: Link) -> None:
        try:
            if not await pause(1, link.dead):
                await self._sync_clock(link)
        finally:
            link.clock_done.set()

    async def _heartbeat(self, link: Link) -> None:
        while not await pause(15, link.dead):
            try:
                if not await self._send(link, codec.frame(0xC9, (0, 0, 0)), heartbeat=True):
                    return
            except BleakError, TimeoutError:
                return

    async def _sync_clock(self, link: Link, cancel: asyncio.Event | None = None) -> None:
        for _ in range(3):
            try:
                if not await self._send(link, codec.frame(0x22), cancel) or await pause(
                    0.5, link.dead, *((cancel,) if cancel is not None else ())
                ):
                    return
                link.clock_pending = True
                await self._send(link, codec.clock(dt_util.now()), cancel)
                return
            except BleakError, TimeoutError:
                if await pause(3, link.dead):
                    return

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.key == "305"

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise ValueError("Clock sync requires the AI Bed primary route")
        await self._sync_clock(self._live(), self._coordinator.cancel_command)

    def _receive(self, link: Link, data: bytes) -> None:
        self.forward_raw_notification(self.profile.notify, data)
        if self.profile.key not in ("305", "hj001"):
            return
        import json

        state = codec.parse_state(data)
        qc = codec.qc_sample(data) or codec.qc_stm32(data) or codec.qc_wave(data)
        if state is not None:
            self.forward_controller_state_updates(RAW(json.dumps(state, sort_keys=True)))
            if "heatLevel" in state:
                self.forward_controller_state_updates(HEAT(state["heatLevel"]))
            # Raw pressure reports are diagnostics, not commanded pump levels.
        if qc is not None:
            self.forward_controller_state_updates(RAW(json.dumps(qc, sort_keys=True)))
        if codec.valid(data, 0x23, 11) and data[3] == 2:
            link.schedules = {
                "inflation_hour": data[4],
                "inflation_minute": data[5],
                "inflation_week": data[6],
                "wake_hour": data[7],
                "wake_minute": data[8],
                "wake_week": data[9],
            }
            link.schedule_reply.set()
        elif codec.valid(data, 0xA2, 14) and data[1] == 14:
            link.strengths = {i: (data[7 + i], data[10 + i]) for i in range(3)}
            link.strength_reply.set()
        elif codec.valid(data, 0xA4, 6) and data[3] == 3 and len(data) >= data[4] + 6:
            self.forward_controller_state_updates(CAPS(data[5] if data[4] else 0))
        elif codec.valid(data, 0xA6, 8):
            self.forward_controller_state_updates(FIRMWARE(f"{data[4]}.{data[5]}.{data[6]}"))
        elif codec.valid(data, 0x55, 4):
            self.forward_controller_state_updates(FIRMWARE("".join(chr(v) for v in data[3:-1])))
        elif (
            codec.valid(data, 0xA8, 8)
            and data[5]
            and data[4] < data[5]
            and len(data) >= data[6] + 8
        ):
            if link.target_complete or link.chunk_count not in (None, data[5]):
                return
            link.chunk_count = data[5]
            link.chunks[data[4]] = "".join(chr(v) for v in data[7 : 7 + data[6]])
            if len(link.chunks) == link.chunk_count:
                link.target_complete = True
                self.forward_controller_state_updates(
                    TARGET("".join(link.chunks[i] for i in range(link.chunk_count)))
                )
        elif codec.valid(data, 5, 17) and data[1] == 0x11 and link.clock_pending:
            link.clock_pending = False
            self.forward_controller_state_updates(CLOCK_ACK(dt_util.now().isoformat()))
        elif codec.valid(data, 0x9C):
            self.forward_controller_state_updates(AUTH(data[3]))
            if data[3] == 1 and not link.pairing_sent:
                link.pairing_sent = True
                self._spawn(self._after_auth(link))

    def _format_command_trace_payload(self, command: bytes) -> dict[str, Any] | None:
        if len(command) >= 3 and command[0] == 0xAA and command[2] == 0x9D:
            return {"hex": "**REDACTED**", "action": "AI Bed privacy PIN"}
        return super()._format_command_trace_payload(command)

    async def _after_auth(self, link: Link) -> None:
        if not await pause(0.5, link.dead):
            await self._send(link, codec.frame(0x34), reliable=True)
        if self.profile.key == "305" and esp_name(self.name):
            await link.clock_done.wait()
            if not self._current(link):
                return
            await self._sync_clock(link)
            await self._send(link, codec.frame(0xA3))

    def on_disconnect(self) -> None:
        if self._link is not None:
            self._link.dead.set()
            self._link.clock_done.set()
        self._link = None
        self._alarm_check = None
        self._pump_cache.clear()
        self.forward_controller_state_updates(
            HEAT(None),
            LEFT(None),
            RIGHT(None),
            RAW(None),
            AUTH(None),
            CAPS(None),
            FIRMWARE(None),
            TARGET(None),
            CLOCK_ACK(None),
            MASSAGE_MODE(None),
            MASSAGE_HEAD(None),
            MASSAGE_FOOT(None),
            MASSAGE_BOTH(None),
            MASSAGE_TIMER_MINUTES(None),
        )

    async def stop_keepalive(self) -> None:
        self.on_disconnect()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_notify(self) -> None:
        link = self._link
        await self.stop_keepalive()
        if link is not None and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    async def _release(self, link: Link) -> None:
        error: Exception | None = None
        for _ in range(self.profile.release_count):
            try:
                await self._send(link, codec.frame(8, (0, 0, 0, 0)), asyncio.Event())
            except (BleakError, TimeoutError) as exc:
                error = exc
        if error is not None:
            raise error
        if context := current_command_context():
            context.cleanup_stop_sent = True

    async def hold_control(self, control: str, duration_ms: int) -> None:
        await self._hold_on_link(control, duration_ms, self._live())

    async def _hold_on_link(
        self, control: str, duration_ms: int, link: Link, *, started_at: float | None = None
    ) -> None:
        self.validate_hold_control(control, duration_ms)
        if not self._current(link):
            return
        action = self.profile.actions[control]
        cancel = self._coordinator.cancel_command
        start = monotonic() if started_at is None else started_at
        end = start + self.leased_hold_ms(duration_ms) / 1000
        self._active_motion = link
        try:
            # Periodic timers first emit on their scheduled tick, never eagerly.
            interval = self.profile.refresh_ms / 1000
            next_tick = start + interval
            while True:
                remaining = end - monotonic()
                if remaining <= 0:
                    break
                if next_tick > end:
                    await pause(remaining, link.dead, cancel)
                    break
                if await pause(max(0, next_tick - monotonic()), link.dead, cancel):
                    break
                if monotonic() > end:
                    break
                if not await self._send(link, self.profile.encode(action), cancel):
                    break
                next_tick += interval
        finally:
            await settled(self._release(link))
            if self._active_motion is link:
                self._active_motion = None

    async def action(self, key: str) -> None:
        link = self._live()
        started_at = monotonic()
        if action := self.profile.actions.get(key):
            if action.motion and self.profile.key == "305":
                await self._hold_on_link(key, 1000, link)
            else:
                sent = await self._send(
                    link, self.profile.encode(action), self._coordinator.cancel_command
                )
                if sent and self.profile.key == "limos" and key == "deep_program":
                    await self._hold_on_link("deep_recall", 1000, link, started_at=started_at)
            return
        if self.profile.key != "305" or key not in FIXED:
            raise ValueError("This control is not supported by the selected AI Bed route")
        if key.startswith("qc_") and not (esp_name(self.name) and "M3" not in self.name):
            raise ValueError("QC readings require an ESP bed other than M3")
        opcode, parameters = FIXED[key]
        if key == "qc_stm32":
            if not await self._send(
                link,
                codec.frame(0x46, (2,)),
                self._coordinator.cancel_command,
                reliable=True,
            ):
                return
        await self._send(
            link,
            codec.frame(opcode, parameters),
            self._coordinator.cancel_command,
            reliable=key.startswith("qc_"),
            mutation=key == "calibrate",
        )

    async def set_level(self, key: str, value: int) -> None:
        if self.profile.key != "305":
            raise ValueError("This control requires the primary AI Bed route")
        link = self._live()
        if key == "heat":
            if not 0 <= value <= 4:
                raise ValueError("Heat gear must be 0..4")
            self.forward_controller_state_updates(HEAT(None))
            await self._send(link, codec.heat(value), self._coordinator.cancel_command)
            return
        if key not in ("waist_left", "waist_right") or not 5 <= value <= 100 or value % 5:
            raise ValueError("Waist pump level must be 5..100 in steps of 5")
        # Channel 0 means unchanged. Never fill an unknown peer with a guessed value.
        cached = self._pump_cache.pop(key, None)
        amount = value if cached != value else 0
        left = amount if key == "waist_left" else 0
        right = amount if key == "waist_right" else 0
        self.forward_controller_state_updates(LEFT(None), RIGHT(None))
        if await self._send(link, codec.waist(left, right), self._coordinator.cancel_command):
            self._pump_cache[key] = value

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        return (
            AlarmCapability(weekdays=True, live_check=True) if self.profile.key == "305" else None
        )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if self.profile.key != "305" or alarm.enabled and not alarm.weekdays:
            raise ValueError("AI Bed wake schedules need at least one weekday")
        self._alarm_check = (self._live(), self._live().revision, alarm)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        stamp = self._alarm_check
        if stamp is None or stamp != (self._live(), self._live().revision, alarm):
            raise ValueError("AI Bed schedule changed after preflight")
        week = sum(1 << day for day in set(alarm.weekdays)) if alarm.enabled else 0
        packet = codec.schedule(
            0x20, alarm.hour if alarm.enabled else 0, alarm.minute if alarm.enabled else 0, week
        )
        await self._send(
            stamp[0],
            packet,
            self._coordinator.cancel_command,
            mutation=True,
            expected_revision=stamp[1],
        )

    def validate_request(self, request: Request) -> None:
        if self.profile.key != "305":
            raise ValueError("This action requires the primary AI Bed route")
        if request.action == "inflation":
            if (
                not 0 <= request.hour <= 23
                or not 0 <= request.minute <= 59
                or any(day not in range(7) for day in request.weekdays)
            ):
                raise ValueError("Invalid inflation schedule")
            if request.enabled and not request.weekdays:
                raise ValueError("Select at least one weekday")
        elif request.action in ("vibration_apply", "vibration_preview"):
            if not any(value in self.name for value in ("M2", "M3")):
                raise ValueError("Vibration strengths require the app's M2/M3 name gate")
            codec.vibration_both(
                request.mode, request.head, request.foot, request.action == "vibration_preview"
            )
            if request.seconds not in (3, 5, 10, 15, 30):
                raise ValueError("Preview duration must be 3,5,10,15 or 30 seconds")
        elif request.action == "privacy_pin":
            codec.privacy(request.pin)
        elif request.action != "settings_query":
            raise ValueError("Unknown AI Bed action")

    async def prepare_request(self, request: Request) -> tuple[Link, int]:
        self.validate_request(request)
        link = self._live()
        if request.action == "inflation" and not request.enabled:
            # Cached diagnostics do not authorize preserving a schedule's time.
            link.schedules = None
            link.schedule_reply.clear()
            if not await self._send(link, codec.frame(0x22), self._coordinator.cancel_command):
                raise ValueError("AI Bed schedule query was not delivered")
            if await pause(2, link.dead, self._coordinator.cancel_command, link.schedule_reply):
                if not self._current(link) or not link.schedule_reply.is_set():
                    raise ValueError("AI Bed schedule query cancelled")
            if link.schedules is None:
                raise ValueError("No fresh AI Bed schedule reply")
        if request.action == "vibration_preview" and request.mode not in link.strengths:
            # A sequential pair opens a fresh child session for each operation.
            # Hydrate rollback state on this same link before preview can mutate it.
            link.strength_reply.clear()
            await self.execute_request(Request(action="settings_query"), (link, link.revision))
            await pause(2, link.dead, self._coordinator.cancel_command, link.strength_reply)
            if (
                not self._current(link)
                or self._coordinator.cancel_command.is_set()
                or request.mode not in link.strengths
            ):
                raise ValueError("No fresh AI Bed vibration strengths for preview")
        return link, link.revision

    async def execute_request(self, request: Request, stamp: tuple[Link, int]) -> None:
        self.validate_request(request)
        link, revision = stamp
        if not self._current(link) or revision != link.revision:
            raise ValueError("AI Bed changed after preflight")
        cancel = self._coordinator.cancel_command
        if request.action == "inflation":
            if request.enabled:
                hour, minute = request.hour, request.minute
            else:
                if link.schedules is None:
                    raise ValueError("Inflation schedule is no longer fresh")
                hour, minute = link.schedules["inflation_hour"], link.schedules["inflation_minute"]
            week = sum(1 << day for day in set(request.weekdays)) if request.enabled else 0
            await self._send(
                link,
                codec.schedule(0x1E, hour, minute, week),
                cancel,
                mutation=True,
                expected_revision=revision,
            )
        elif request.action == "privacy_pin":
            if await self._send(
                link, codec.privacy(request.pin), cancel, mutation=True, expected_revision=revision
            ):
                if not await pause(0.3, link.dead, cancel) and self._current(link):
                    await link.client.disconnect()
        elif request.action == "settings_query":
            packages = (
                (2, 4, 5, 7)
                if any(value in self.name for value in ("MpeV3B-9", "MpeV3L-9"))
                else (2, 4, 7)
                if any(value in self.name for value in ("M1", "M2", "M3"))
                else ()
            )
            await self._send(
                link,
                codec.query(packages) if packages else codec.frame(0x22),
                cancel,
                reliable=True,
            )
        elif request.action == "vibration_apply":
            link.strengths.pop(request.mode, None)
            await self._send(
                link, codec.vibration_both(request.mode, request.head, request.foot, False), cancel
            )
        else:
            original = link.strengths.pop(request.mode)
            attempted = False

            def mark_attempt() -> None:
                nonlocal attempted
                attempted = True
                # Preview and its cleanup change the same controls as the
                # native entities, without supplying measured state.
                if self._current(link):
                    self.forward_controller_state_updates(
                        MASSAGE_HEAD(None),
                        MASSAGE_FOOT(None),
                        MASSAGE_BOTH(None),
                        MASSAGE_MODE(None),
                    )

            # Cancellation and dispose finish on the captured session only.
            try:
                if not await self._send(
                    link,
                    codec.vibration_both(request.mode, request.head, request.foot, True),
                    cancel,
                    expected_revision=revision,
                    on_attempt=mark_attempt,
                ):
                    return
                if await pause(0.06, link.dead, cancel):
                    return
                if not await self._send(
                    link, codec.frame(0x18, (request.mode,)), cancel
                ) or await pause(0.06, link.dead, cancel):
                    return
                if await self._send(link, codec.frame(0x16, (1, 1)), cancel):
                    await pause(request.seconds, link.dead, cancel)
            finally:

                async def cleanup() -> None:
                    error: Exception | None = None
                    for packet in (
                        codec.frame(0x16, (2, 2)),
                        codec.vibration_both(request.mode, *original, True),
                    ):
                        try:
                            await self._send(link, packet, asyncio.Event())
                        except (BleakError, TimeoutError) as exc:
                            error = exc
                    await pause(0.06, link.dead)
                    if error is not None:
                        raise error

                if attempted:
                    await settled(cleanup())

    async def stop_all(self) -> None:
        # Only the running hold owns cleanup, never a newly connected replacement.
        self._coordinator.cancel_command.set()

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def _unsupported(self, *args, **kwargs) -> None:
        raise NotImplementedError("Use the AI Bed app-labelled controls")

    move_head_up = _unsupported
    move_head_down = _unsupported
    move_back_up = _unsupported
    move_back_down = _unsupported
    move_legs_up = _unsupported
    move_legs_down = _unsupported
    move_feet_up = _unsupported
    move_feet_down = _unsupported
    preset_flat = _unsupported
    preset_memory = _unsupported
    program_memory = _unsupported


FIXED = {
    "lamp_on": (0x1C, (1,)),
    "lamp_off": (0x1C, (0,)),
    "massage_head_on": (0x16, (1, 0)),
    "massage_head_off": (0x16, (2, 0)),
    "massage_foot_on": (0x16, (0, 1)),
    "massage_foot_off": (0x16, (0, 2)),
    "massage_both_on": (0x16, (1, 1)),
    "massage_both_off": (0x16, (2, 2)),
    **{f"massage_mode_{i + 1}": (0x18, (i,)) for i in range(3)},
    **{f"massage_timer_{i * 10}": (0x1A, (i,)) for i in range(1, 4)},
    "status": (0x22, ()),
    "capabilities": (0xA3, ()),
    "firmware": (0xA5, ()),
    "build_target": (0xA7, ()),
    "calibrate": (0x26, ()),
    "sleep_aid_reset": (0x39, (15, 1, 1, 0, 0, 0)),
    "qc_sample": (0x46, ()),
    "qc_stm32": (0x47, ()),
    "qc_wave": (0x49, ()),
}
FIXED_LABELS = {key: key.replace("_", " ").capitalize() for key in FIXED}
DIAGNOSTICS = {"status", "capabilities", "firmware", "build_target"}


async def build_controller(ctx: BuildContext) -> AiBedController:
    route = ctx.variant if ctx.variant in PROFILES else "unselected"
    name = ctx.live_device_name or str(ctx.data.get(CONF_BLE_DEVICE_NAME, ""))
    return AiBedController(ctx.coordinator, route, name)
