"""Sealy Posturematic: profile controls fenced to one physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.exceptions import HomeAssistantError

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...command_scheduler import (
    CommandContext,
    CommandKind,
    command_frames_counted,
    current_command_context,
    note_frame_skipped,
)
from ...const import CONF_BED_TYPE, CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...errors import failed, invalid
from ...profiles import sealy as app
from ...profiles.okin_5a import Action
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, massage_intensity
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, on_off_switch
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..okin_7byte import Okin7ByteController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

WAVE: Final = StateKey[int | None]("sealy_massage_wave")
MASSAGE_ON: Final = StateKey[bool | None]("sealy_massage_on")


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str
    generation: int | None


class SealyController(Okin7ByteController):
    """Use shared Okin methods, with only this app's actions and lifecycle."""

    profile: app.SealyProfile

    def __init__(self, coordinator: AdjustableBedCoordinator, layout: str = "0") -> None:
        if layout not in app.PROFILES:
            raise invalid("sealy_control_invalid")
        super().__init__(coordinator, app.PROFILES[layout])
        self._link: _Link | None = None
        self._subscribed: _Link | None = None
        self._token: object | None = None
        self._startup_cancel: asyncio.Event | None = None
        self._startup_epoch: int | None = None
        self._serial = 0
        self._wave = 0
        self._anti_pinch: int | None = None
        self._cleanup: tuple[_Link, CommandContext] | None = None

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        # One-shot motion has no source-proven halt on link loss.
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def has_lumbar_support(self) -> bool:
        return False

    @property
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        # Element's local voice-result dispatcher also reaches these commands.
        return True

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_massage_off_control(self) -> bool:
        return False

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            on_off_switch(
                "sealy_massage",
                "sealy_massage",
                lambda c: cast(SealyController, c).massage_on(),
                lambda c: c.massage_off(),
                state_key=MASSAGE_ON,
                assumed_state=True,
                card=CARD_MASSAGE,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "product": app.LAYOUTS[self.profile.layout],
            "anti_pinch_status": self._anti_pinch,
            "massage_wave": self._wave,
            "clock_conversion": "unverified",
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                label,
                lambda c, key=key: cast(SealyController, c)._move(f"{key}_up"),
                lambda c, key=key: cast(SealyController, c)._move(f"{key}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="motor:*",
                hold=ControllerMotorHoldSpec(f"{key}_up", f"{key}_down", stop_scope="side"),
            )
            for key, label in (("head", "head"), ("feet", "feet"), ("both", "back_legs"))
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            "head_up",
            "head_down",
            "feet_up",
            "feet_down",
            "both_up",
            "both_down",
            "flat",
            "zero_g",
            "tv",
            "anti_snore",
            "memory_1",
            "memory_2",
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = key.removeprefix("preset_")
        return ControllerHoldSpec(control) if control in self.held_control_options else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = {
            "save_zero_g": "Save zero gravity",
            "save_tv": "Save TV",
            "reset": "Reset preset memories",
            "force_flat": "Force flat",
            "massage_timer": "Cycle massage timer",
            "wave_up": "Cycle massage wave",
            "query_massage": "Refresh massage",
            "query_anti_pinch": "Refresh anti-pinch status",
            "voice_head_up": "Head up once",
            "voice_head_down": "Head down once",
            "voice_feet_up": "Foot up once",
            "voice_feet_down": "Foot down once",
            "voice_stop": "Stop one-touch movement",
            "once_flat": "Flat once",
            "once_tv": "TV once",
            "once_zero_g": "Zero gravity once",
            "once_anti_snore": "Anti-snore once",
            "once_memory_1": "Memory 1 once",
            "once_memory_2": "Memory 2 once",
            "once_both_down": "Head and foot down once",
        }
        specs: list[ControllerButtonSpec] = []
        for key, label in labels.items():
            extra = key.startswith(("query_", "voice_", "once_")) or key in ("reset", "force_flat")
            spec = catalog_button(
                f"sealy_{key}",
                label,
                lambda c, key=key: cast(SealyController, c).action(key),
                kind=Kind.EXTRA if extra else None,
                diagnostic=key.startswith("query_"),
                requires_confirmation=key in ("reset", "force_flat"),
            )
            if spec is not None:
                specs.append(spec)
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "sealy_massage_timer",
                "sealy_massage_timer",
                MASSAGE_TIMER_MINUTES,
                "mdi:timer",
                native_unit_of_measurement="min",
                card=CARD_MASSAGE_TIMER,
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
            *(
                ControllerStateSensorSpec(
                    f"sealy_massage_{zone}_level",
                    f"sealy_massage_{zone}_level",
                    massage_intensity(zone),
                    "mdi:vibrate",
                    card=CARD_MASSAGE,
                    entity_registry_enabled_default=True,
                    entity_category=None,
                )
                for zone in ("head", "foot")
            ),
        )

    @property
    def _cancel(self) -> asyncio.Event:
        context = current_command_context()
        return context.cancel_event if context is not None else self._coordinator.cancel_command

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        data = self._coordinator.entry.data
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != link.address
            or link.generation is not None
            and self._coordinator.connection_generation != link.generation
            or data.get(CONF_BED_TYPE) != "sealy_posturematic"
            or str(data.get(CONF_PRODUCT_TYPE, "0")) != self.profile.layout
        ):
            raise failed("sealy_session_changed")
        return link

    def _is_current(self, link: _Link) -> bool:
        try:
            self._live(link)
        except HomeAssistantError:
            return False
        return True

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise failed("sealy_session_changed")
        # The app lowercases configured UUIDs, then uses exact Guid.str equality.
        # Do not add short UUID, uppercase-receiver or cross-service fallbacks.
        from ...codec.okin_5a import TRANSPORTS

        roles = TRANSPORTS["nus"]
        write = notify = None
        for service in client.services:
            if service.uuid != roles.service_uuid:
                continue
            for char in service.characteristics:
                if write is None and char.uuid == roles.write_uuid:
                    write = char
                if notify is None and char.uuid == roles.notify_uuid:
                    notify = char
            break
        if write is None or notify is None:
            raise failed("sealy_gatt_missing")
        self._link = _Link(client, write, notify, self._coordinator.address.upper(), None)

    async def _frame(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        own: bool = True,
        response: bool = False,
        serial: int | None = None,
        stop_epoch: int | None = None,
        startup_epoch: int | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def check() -> None:
            self._live(link)
            if serial is not None and serial != self._serial:
                raise failed("sealy_session_changed")
            if stop_epoch is not None and stop_epoch != self._coordinator.cancel_counter:
                if own:
                    note_frame_skipped()
                raise asyncio.CancelledError
            if (
                startup_epoch is not None
                and startup_epoch != self._coordinator.command_scheduler.stop_epoch
            ):
                raise asyncio.CancelledError

        check()
        # Drain a dispatched write before release, even on task cancellation.
        try:
            await settled(
                self._write_gatt_with_retry(
                    link.write.uuid,
                    frame,
                    cancel_event=cancel,
                    response=response,
                    characteristic=link.write,
                    expected_client=link.client,
                    before_write=check,
                    track_command_write=own,
                    on_write=on_write,
                )
            )
        finally:
            self._live(link)

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._live()
        self._link = link = replace(link, generation=self._coordinator.connection_generation)
        context = current_command_context()
        owned = (
            context is not None
            and context.scheduler_token is self._coordinator.command_scheduler.token
        )
        stopping = owned and context is not None and context.kind is CommandKind.STOP
        self._startup_cancel = (
            context.cancel_event
            if owned and context is not None and not stopping
            else asyncio.Event()
        )
        # A STOP already owns its preparation. Movement admission must wait for
        # it, and cannot invalidate that preparation via the legacy counter.
        self._startup_epoch = None if stopping else self._coordinator.command_scheduler.stop_epoch
        await self._frame(
            link,
            app.FRAMES["initialize"],
            self._startup_cancel,
            own=False,
            response=True,
            startup_epoch=self._startup_epoch,
        )
        self._live(link)
        if self._startup_cancel.is_set():
            return
        await session.async_start_notify()
        self._live(link)

    async def async_after_connect(self, session: ControllerSession) -> None:
        link, cancel, epoch = self._live(), self._startup_cancel, self._startup_epoch
        if cancel is None:
            raise failed("sealy_session_changed")
        await cancellable(asyncio.sleep(app.QUERY_DELAY_MS / 1000), cancel)
        self._live(link)
        for key in ("query_anti_pinch", "query_massage"):
            await self._frame(link, app.FRAMES[key], cancel, own=False, startup_epoch=epoch)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        *,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        link, epoch = self._live(), self._coordinator.cancel_counter
        cancel = cancel_event if cancel_event is not None else self._cancel
        for index in range(repeat_count):
            if cancel.is_set():
                note_frame_skipped()
                return
            if index:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
            self._live(link)
            await self._frame(link, command, cancel, stop_epoch=epoch)
            if on_write is not None:
                on_write()

    async def _release(
        self,
        link: _Link,
        context: CommandContext | None = None,
        *,
        own: bool = False,
        key: str = "stop",
    ) -> None:
        async def send() -> None:
            failure: Exception | None = None
            for index in range(2):
                if index:
                    await asyncio.sleep(app.REFRESH_MS / 1000)
                try:
                    await self._frame(link, app.FRAMES[key], asyncio.Event(), own=own)
                except Exception as err:
                    failure = failure or err
            if failure is not None:
                raise failure
            if context is not None:
                context.cleanup_stop_sent = True
                self._cleanup = (link, context)

        await settled(send())

    async def _run(
        self,
        key: str,
        *,
        duration_ms: int = 0,
        repeats: int = 1,
        release: bool = False,
        delay_ms: int = 0,
    ) -> None:
        if key not in app.FRAMES:
            raise invalid("sealy_control_invalid")
        link, cancel = self._live(), self._cancel
        epoch = self._coordinator.cancel_counter
        self._serial += 1
        serial = self._serial
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        self._cleanup = None
        if cancel.is_set():
            note_frame_skipped()
            return
        loop = asyncio.get_running_loop()
        written = 0
        started = deadline = loop.time()

        def sent() -> None:
            nonlocal written
            written += 1

        try:
            if self._subscribed is not link:
                await self.start_notify()
                self._live(link)
            if delay_ms:
                await cancellable(asyncio.sleep(delay_ms / 1000), cancel)
                self._live(link)
            deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
            index = 0
            while True:
                if cancel.is_set():
                    note_frame_skipped()
                    return
                self._live(link)
                started = loop.time()
                await self._frame(
                    link, app.FRAMES[key], cancel, serial=serial, stop_epoch=epoch, on_write=sent
                )
                index += 1
                if not duration_ms and index >= repeats:
                    return
                wait = app.REFRESH_MS / 1000
                if duration_ms:
                    wait = min(deadline, started + wait) - loop.time()
                if wait > 0:
                    await cancellable(asyncio.sleep(wait), cancel)
                self._live(link)
                if duration_ms and loop.time() + 1e-6 >= deadline:
                    return
        except asyncio.CancelledError:
            # A dispatched write can finish while its caller is cancelled. The
            # final hold wait also has no pending refresh to count as missing.
            if (
                duration_ms and (not written or started + app.REFRESH_MS / 1000 + 1e-6 < deadline)
            ) or (not duration_ms and written < repeats):
                note_frame_skipped()
            if not cancel.is_set():
                raise
        finally:
            if release:
                await self._release(link, context)

    async def _move(self, action: str) -> None:
        if action not in self.profile.frames:
            raise NotImplementedError
        count, _ = self.motor_pulse_settings()
        await self._run(
            action, duration_ms=max(1, count) * app.REFRESH_MS, release=True, delay_ms=50
        )

    async def _recall(self, action: Action) -> None:
        if action not in self.profile.frames:
            raise NotImplementedError
        await self._run(action, duration_ms=600, release=True, delay_ms=50)

    async def _send(self, action: Action) -> None:
        if action not in self.profile.frames:
            raise NotImplementedError
        link = self._live()
        updates = (
            (UNDER_BED_LIGHTS_ON(action == "light_on"),)
            if action in ("light_on", "light_off")
            else ()
        )
        if action == "light_toggle":
            updates = (UNDER_BED_LIGHTS_ON(None),)
        elif action in ("massage_on", "massage_off", "massage_toggle"):
            with self.sent_state(
                MASSAGE_ON(None if action == "massage_toggle" else action == "massage_on"),
                is_current=lambda: self._is_current(link),
            ):
                await self._run(action, repeats=2)
            return
        with self.sent_state(*updates, is_current=lambda: self._is_current(link)):
            await self._run(
                action,
                repeats=2 if action in ("massage_toggle", "massage_on", "massage_off") else 1,
            )

    async def lights_off(self) -> None:
        await self._send("light_off")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._run(f"save_memory_{memory_num}", duration_ms=app.PROGRAM_MS, release=True)

    def validate_memory_recall(self, memory_num: int) -> None:
        if type(memory_num) is not int or memory_num not in (1, 2):
            raise invalid("sealy_control_invalid")

    async def preset_memory(self, memory_num: int) -> None:
        await self.recall_memory(memory_num, hold_ms=600)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        self.validate_hold_control(f"memory_{slot}", hold_ms)
        await self._run(f"memory_{slot}", duration_ms=hold_ms, release=True, delay_ms=50)

    async def massage_mode_step(self) -> None:
        link = self._live()
        key = f"mode_{self._wave}" if self._wave in (0, 1, 2) else "massage_off"
        with self.sent_state(
            *((MASSAGE_ON(False),) if key == "massage_off" else ()),
            is_current=lambda: self._is_current(link),
        ):
            await self._run(key)

    async def massage_head_up(self) -> None:
        await self._run("massage_head_up")

    async def massage_head_down(self) -> None:
        await self._run("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self._run("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self._run("massage_foot_down")

    async def action(self, key: str) -> None:
        if key in ("save_zero_g", "save_tv"):
            await self._run(key, duration_ms=app.PROGRAM_MS, release=True)
        elif key == "reset":
            if self.profile.layout == "0":
                link, cancel, epoch = self._live(), self._cancel, self._coordinator.cancel_counter
                await self._release(link)
                await cancellable(
                    asyncio.sleep(app.PROGRAM_MS / 1000 - app.REFRESH_MS / 1000), cancel
                )
                self._live(link)
                if epoch != self._coordinator.cancel_counter:
                    note_frame_skipped()
                    return
                await self._run("reset_element")
            else:
                await self._run("reset", duration_ms=app.PROGRAM_MS, release=True)
        elif key == "force_flat":
            await self._run(key, duration_ms=600, release=True)
        elif key.startswith("once_") and key.removeprefix("once_") in {
            "flat",
            "tv",
            "zero_g",
            "anti_snore",
            "memory_1",
            "memory_2",
            "both_down",
        }:
            await self._run(key.removeprefix("once_"))
        elif key == "voice_stop":
            await self._run(key, repeats=2)
        elif key.startswith("voice_") or key in (
            "query_massage",
            "query_anti_pinch",
            "wave_up",
            "massage_timer",
        ):
            await self._run(key)
        else:
            raise invalid("sealy_control_invalid")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("sealy_control_invalid")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._run(control, duration_ms=duration_ms, release=True, delay_ms=50)

    async def _send_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        link, context = self._live(), current_command_context()
        released = False
        if self._cleanup is not None and context is not None:
            owner_link, owner = self._cleanup
            if (
                owner_link is link
                and owner.scheduler_token is context.scheduler_token
                and any(owner is old for old in context.preempted_contexts)
                and owner.cleanup_stop_sent
            ):
                owner.cleanup_stop_sent = False
                released = True
        self._cleanup = None
        with command_frames_counted():
            try:
                if not released:
                    await self._release(link, own=True)
            finally:
                # The app ends a one-touch ("… once") movement with its own
                # one-touch STOP, never the ordinary one, so Stop sends both.
                await self._release(link, own=True, key="voice_stop")

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscribed is link:
            return
        token = self._token = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._token is not token or self._link is not link:
                return
            try:
                self._live(link)
            except Exception:
                return
            if sender.handle != link.notify.handle or sender.uuid != link.notify.uuid:
                return
            raw = bytes(data)
            self.forward_raw_notification(sender.uuid, raw)
            status = app.parse_massage(raw)
            if status is not None:
                self._wave = status.wave
                self.forward_controller_state_updates(
                    WAVE(status.wave),
                    massage_intensity("head")(status.head),
                    massage_intensity("foot")(status.foot),
                    massage_intensity("all")(max(status.head, status.foot)),
                    MASSAGE_TIMER_MINUTES(status.minutes),
                )
            anti_pinch = app.parse_anti_pinch(raw)
            if anti_pinch is not None:
                self._anti_pinch = anti_pinch

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            if self._token is token:
                self._subscribed = link
        except BaseException:
            if self._token is token:
                self._token = None
            raise

    async def stop_notify(self) -> None:
        link, self._subscribed = self._subscribed, None
        self._token = None
        if link is not None and link.client.is_connected:
            await settled(link.client.stop_notify(link.notify))

    def on_disconnect(self) -> None:
        self._link = self._subscribed = None
        self._token = None
        self._startup_cancel = None
        self._startup_epoch = None
        self._anti_pinch = None
        self._wave = 0
        self._cleanup = None
        self.forward_controller_state_updates(
            WAVE(None),
            MASSAGE_ON(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
            *(massage_intensity(zone)(None) for zone in ("head", "foot", "all")),
        )


async def build_controller(ctx: BuildContext) -> BedController:
    return SealyController(ctx.coordinator, str(ctx.data.get(CONF_PRODUCT_TYPE, "0")))
