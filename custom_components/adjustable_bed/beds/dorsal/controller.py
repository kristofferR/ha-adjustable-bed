"""Dorsal and Roomi sessions over the Richmat 6E codec."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from functools import cached_property, partial
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from bleak.exc import BleakError

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE
from ...codec import richmat as codec
from ...command_scheduler import note_frame_skipped
from ...const import CONF_PRODUCT_TYPE
from ...errors import failed, invalid
from ...execution import STREAM_HOLD, ExecutionCapabilities
from ...profiles import dorsal as app
from ...state_keys import (
    FAN_LEVEL,
    MASSAGE_ACTIVE,
    MASSAGE_TIMER_MINUTES,
    REMOTE_CONTROL_LOCK,
    SYNCHRO_MODE,
    UNDER_BED_LIGHTS_ON,
    massage_intensity,
)
from ..base import BedController, require_controller
from ..cancellation import settled
from ..catalog_buttons import (
    Kind,
    catalog_button,
    classify,
    save_button,
    unique_buttons,
)
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..richmat.transport import AppLink
from . import controls
from .receive import Alarm, Status, Stream, decode
from .transport import select_link, validate_name

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..base import ControllerSession
    from ..builder import BuildContext

_LOGGER = logging.getLogger(__name__)
_SERVICE_CHANGED = "00002a05-0000-1000-8000-00805f9b34fb"
_GENERIC_ATTRIBUTE = "00001801-0000-1000-8000-00805f9b34fb"
_admitted: WeakKeyDictionary[AdjustableBedCoordinator, str] = WeakKeyDictionary()
_STANDARD_PRESETS = {
    "preset_flat": "MotorReset",
    "preset_zero_g": "ZeroGravity",
    "preset_anti_snore": "AntiSnoring",
    "preset_tv": "TVPosition",
}
_MOTOR_TRANSLATIONS = {
    "lumbar_pillow": "dorsal_lumbar_pillow",
    "pillow_2": "dorsal_second_pillow",
    "motor_4": "dorsal_motor_4",
    "motor_5": "richmat_mh_motor_5",
    "zero_gravity": "dorsal_zero_gravity",
}
_MASSAGE_LEVEL = {
    "head_massage_level": massage_intensity("head"),
    "foot_massage_level": massage_intensity("foot"),
}


def _call(
    control: app.Control, *, save: bool = False
) -> Callable[[BedController], Coroutine[Any, Any, None]]:
    async def run(controller: BedController) -> None:
        await require_controller(controller, DorsalController).run_control(control.key, save=save)

    return run


async def _stop(controller: BedController) -> None:
    await controller.stop_all()


class DorsalController(BedController):
    """Use only the controls declared for the selected product or Roomi page."""

    def __init__(self, coordinator: AdjustableBedCoordinator, route: str, code: str | None) -> None:
        super().__init__(coordinator)
        self.route = route
        self.code = code
        product = app.products().get(code) if code is not None else None
        self.controls = (
            app.ROOMI + (app.ROOMI_SNORE,)
            if route == "roomi"
            else (product.controls if product is not None else ())
        )
        self._controls = {item.key: item for item in self.controls}
        self._modes = controls.wake_modes(product.alarm_modes) if product else {}
        self._link: AppLink | None = None
        self._subscriptions: list[BleakGATTCharacteristic] = []
        self._stream = Stream()
        self._expiry: asyncio.TimerHandle | None = None
        self._status: Status = {}
        self._massage_reports = 0
        self._alarms: dict[int, Alarm] = {}
        self._alarm_updated = asyncio.Event()

    @property
    def execution(self) -> ExecutionCapabilities:
        return STREAM_HOLD

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def supports_preset_flat(self) -> bool:
        return self._named("MotorReset") is not None

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._named("ZeroGravity") is not None

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._named("AntiSnoring") is not None

    @property
    def supports_preset_tv(self) -> bool:
        return self._named("TVPosition") is not None

    async def _run_named(self, name: str) -> None:
        if (item := self._named(name)) is None:
            raise invalid("dorsal_control_unavailable")
        await self.run_control(item.key)

    async def preset_flat(self) -> None:
        await self._run_named("MotorReset")

    async def preset_zero_g(self) -> None:
        await self._run_named("ZeroGravity")

    async def preset_anti_snore(self) -> None:
        await self._run_named("AntiSnoring")

    async def preset_tv(self) -> None:
        await self._run_named("TVPosition")

    async def _move(self, axis: str, direction: str) -> None:
        if (item := self._motors.get(axis, {}).get(direction)) is None:
            raise invalid("dorsal_control_unavailable")
        await self.run_control(item.key)

    async def move_head_up(self) -> None:
        await self._move("head", "up")

    async def move_head_down(self) -> None:
        await self._move("head", "down")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_back_stop = move_head_stop

    async def move_feet_up(self) -> None:
        await self._move("feet", "up")

    async def move_feet_down(self) -> None:
        await self._move("feet", "down")

    move_feet_stop = move_head_stop
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_legs_stop = move_head_stop

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        name = _STANDARD_PRESETS.get(key)
        item = self._named(name) if name else None
        return ControllerHoldSpec(item.key) if item and item.sustain else None

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.motor_control_specs)

    @property
    def supports_stop_all(self) -> bool:
        return bool(self.controls)

    @property
    def supports_massage(self) -> bool:
        return any(controls.kind(item) is Kind.MASSAGE for item in self.controls)

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    def _named(self, name: str) -> app.Control | None:
        return next(
            (item for item in self.controls if controls.action_name(item.action) == name), None
        )

    @cached_property
    def _motors(self) -> dict[str, dict[str, app.Control]]:
        result: dict[str, dict[str, app.Control]] = {}
        for item in self.controls:
            shape = classify(controls.label(item), kind=controls.kind(item))
            if shape and shape.kind is Kind.MOTOR and shape.card.motor and shape.card.role:
                result.setdefault(shape.card.motor, {}).setdefault(shape.card.role.value, item)
        return {
            axis: directions
            for axis, directions in result.items()
            if "up" in directions and "down" in directions
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                _MOTOR_TRANSLATIONS.get(axis, axis),
                _call(up),
                _call(down),
                _stop,
                stop_scope="side",
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    up.key, down.key, stop_scope="side", press_hold_ms=None
                )
                if self._held(up) and self._held(down)
                else None,
            )
            for axis, directions in self._motors.items()
            for up, down in [(directions["up"], directions["down"])]
        )

    @cached_property
    def _recalls(self) -> dict[int, app.Control]:
        result: dict[int, app.Control] = {}
        for item in self.controls:
            name = controls.action_name(item.action)
            if (
                name.startswith("MemoryPosition")
                and name[-1].isdigit()
                and (item.short or item.sustain)
            ):
                result.setdefault(int(name[-1]), item)
        return result

    @cached_property
    def _saves(self) -> dict[int, app.Control]:
        result: dict[int, app.Control] = {}
        for item in self.controls:
            name = controls.action_name(item.action)
            if name.startswith("MemoryPosition") and name[-1].isdigit() and item.long:
                result.setdefault(int(name[-1]), item)
        return result

    @property
    def memory_slot_count(self) -> int:
        return max(self._recalls.keys() | self._saves.keys(), default=0)

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self._recalls)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self._saves)

    @property
    def memory_slots_recalled_by_presets(self) -> frozenset[int]:
        # Catalog buttons carry each exact slot, including sparse layouts.
        return frozenset(self._recalls)

    @property
    def memory_slots_programmed_by_presets(self) -> frozenset[int]:
        return frozenset(self._saves)

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return memory_num in self._saves

    def validate_memory_recall(self, memory_num: int) -> None:
        if memory_num not in self._recalls:
            raise invalid("dorsal_control_unavailable")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.run_control(self._recalls[memory_num].key)

    async def program_memory(self, memory_num: int) -> None:
        if (item := self._saves.get(memory_num)) is None:
            raise invalid("dorsal_control_unavailable")
        await self.run_control(item.key, save=True)

    @property
    def supports_lights(self) -> bool:
        return self._named("BedLight") is not None

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        if (item := self._named("BedLight")) is None:
            raise invalid("dorsal_control_unavailable")
        await self.run_control(item.key)

    async def lights_off(self) -> None:
        if (item := self._named("BedLightClose")) is not None:
            with self.sent_state(UNDER_BED_LIGHTS_ON(False)):
                await self.run_control(item.key)
        else:
            await super().lights_off()

    @cached_property
    def _timers(self) -> dict[int, app.Control]:
        result: dict[int, app.Control] = {}
        for item in self.controls:
            if (minutes := controls.timer_minutes(item)) is not None and (
                item.short or item.sustain
            ):
                result.setdefault(minutes, item)
        return result

    @cached_property
    def _levels(self) -> dict[str, dict[int, app.Control]]:
        zones: dict[str, dict[int, app.Control]] = {}
        for item in self.controls:
            level = controls.massage_level(item)
            if level is not None and item.short is not None:
                zone, value = level
                zones.setdefault(zone, {}).setdefault(value, item)
        return {zone: levels for zone, levels in zones.items() if {1, 2, 3} <= levels.keys()}

    @property
    def supports_massage_intensity_control(self) -> bool:
        return bool(self._levels)

    @property
    def massage_intensity_zones(self) -> list[str]:
        return list(self._levels)

    @property
    def massage_intensity_max(self) -> int:
        return 3

    def massage_intensity_min(self, zone: str) -> int:
        return min(self._levels.get(zone, {1: None}))

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if (item := self._levels.get(zone, {}).get(level)) is None:
            raise invalid("dorsal_control_unavailable")
        with self.sent_state(massage_intensity(zone)(level)):
            await self.run_control(item.key)

    @property
    def supports_massage_timer(self) -> bool:
        return bool(self._timers)

    @property
    def massage_timer_options(self) -> list[int]:
        return sorted(self._timers)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if (item := self._timers.get(minutes)) is None:
            raise invalid("dorsal_control_unavailable")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self.run_control(item.key)

    @property
    def supports_synchro(self) -> bool:
        return bool(self._named("SyncOn") and self._named("SyncOff"))

    async def set_synchro(self, enabled: bool) -> None:
        if (item := self._named("SyncOn" if enabled else "SyncOff")) is None:
            raise invalid("dorsal_control_unavailable")
        with self.sent_state(SYNCHRO_MODE(enabled)):
            await self.run_control(item.key)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        on, off = self._named("MassageModeAllOn"), self._named("MassageModeAllOff")
        if (
            on is None
            or off is None
            or not (on.short or on.sustain)
            or not (off.short or off.sustain)
        ):
            return ()
        return (
            ControllerSwitchSpec(
                "dorsal_massage",
                "dorsal_massage",
                lambda controller, enabled: require_controller(
                    controller, DorsalController
                ).set_massage_power(enabled),
                state_key=MASSAGE_ACTIVE,
                card=CARD_MASSAGE,
            ),
        )

    async def set_massage_power(self, enabled: bool) -> None:
        link = self._live()
        report = self._massage_reports
        with self.sent_state(
            MASSAGE_ACTIVE(enabled),
            is_current=lambda: self._current(link) and self._massage_reports == report,
        ):
            await self._run_named("MassageModeAllOn" if enabled else "MassageModeAllOff")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        represented = {
            item.key for direction in self._motors.values() for item in direction.values()
        }
        represented.update(item.key for item in self._timers.values())
        represented.update(item.key for zone in self._levels.values() for item in zone.values())
        represented.update(
            item.key for name in _STANDARD_PRESETS.values() if (item := self._named(name))
        )
        if self.supports_synchro:
            represented.update(
                item.key for name in ("SyncOn", "SyncOff") if (item := self._named(name))
            )
        if self.controller_switch_specs:
            represented.update(
                item.key
                for name in ("MassageModeAllOn", "MassageModeAllOff")
                if (item := self._named(name))
            )
        result: list[ControllerButtonSpec | None] = []
        for item in self.controls:
            name = controls.label(item)
            action = controls.action_name(item.action)
            shape = classify(name, kind=controls.kind(item))
            if item.key not in represented and (item.short or item.sustain):
                if action != "BedLightClose" or not self.supports_lights:
                    result.append(
                        catalog_button(
                            item.key,
                            name,
                            _call(item),
                            kind=controls.kind(item),
                            hold=ControllerHoldSpec(item.key) if self._held(item) else None,
                            invalidates_position=bool(
                                item.sustain
                                or shape
                                and shape.kind
                                in (
                                    Kind.MOTOR,
                                    Kind.MEMORY,
                                    Kind.PRESET,
                                )
                            ),
                        )
                    )
            if item.long is not None and item.long != item.short:
                # Preset and memory alternates are offered on separate confirmed buttons.
                if shape and shape.kind in (Kind.PRESET, Kind.MEMORY):
                    result.append(
                        save_button(
                            item.key + "_save",
                            f"Save {name.lower()}",
                            _call(item, save=True),
                            requires_confirmation=True,
                        )
                    )
                elif item.key not in represented or item.short is not None:
                    result.append(
                        catalog_button(
                            item.key + "_long",
                            f"{name} (alternate)" if item.short else name,
                            _call(item, save=True),
                            kind=controls.kind(item),
                            requires_confirmation=True,
                        )
                    )
        return unique_buttons(result)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.controls if self._held(item))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 100 <= duration_ms <= 60000:
            raise invalid("dorsal_hold_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.run_control(control, duration_ms=duration_ms)

    def _live(self) -> AppLink:
        if (link := self._link) is None or not self._current(link):
            raise failed("dorsal_receiver_unavailable")
        return link

    def _current(self, link: AppLink) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    async def _send(
        self,
        link: AppLink,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        counted: bool = True,
        on_attempt: Callable[[], None] | None = None,
    ) -> None:
        await settled(
            self._write_gatt_with_retry(
                link.tx.uuid,
                frame,
                cancel_event=cancel,
                characteristic=link.tx,
                expected_client=link.client,
                response="write-without-response" not in link.tx.properties,
                track_command_write=counted,
                before_write=on_attempt,
            )
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        for i in range(repeat_count):
            if i and not await self._delay(repeat_delay_ms / 1000, cancel):
                note_frame_skipped()
                break
            await self._send(link, command, cancel)
            if cancel.is_set():
                break

    @staticmethod
    async def _delay(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            return not cancel.is_set()
        return False

    @staticmethod
    def _wire(opcode: app.Opcode, link: AppLink, *, fixed: bool = False) -> bytes:
        if fixed:
            return codec.command(opcode[1])
        return codec.function(
            opcode[0] if link.query_single else opcode[1], single=link.query_single
        )

    async def run_control(
        self, key: str, *, save: bool = False, duration_ms: int | None = None
    ) -> None:
        item = self._controls.get(key)
        if item is None:
            raise invalid("dorsal_control_unavailable")
        opcode = item.long if save else item.sustain or item.short or item.long
        if opcode is None:
            raise invalid("dorsal_control_unavailable")
        link = self._live()
        cancel = self._coordinator.cancel_command
        wire = self._wire(opcode, link, fixed=item.fixed)
        sustain = not save and item.sustain is not None
        attempted = False

        def on_attempt() -> None:
            nonlocal attempted
            attempted = True

        try:
            if not sustain:
                await self._send(link, wire, cancel, on_attempt=on_attempt)
                if attempted and not save and self._manual_motor(item):
                    active_ms = (
                        duration_ms
                        if duration_ms is not None
                        else self.leased_hold_ms(100 * self._coordinator.motor_pulse_count)
                    )
                    await self._delay(active_ms / 1000, cancel)
                return
            duration = (
                duration_ms
                if duration_ms is not None
                else self.leased_hold_ms(100 * self._coordinator.motor_pulse_count)
            )
            loop = asyncio.get_running_loop()
            start = loop.time()
            tick = 1
            while tick * 100 <= duration:
                if not await self._delay(
                    max(0, start + tick * app.REFRESH_SECONDS - loop.time()), cancel
                ):
                    note_frame_skipped()
                    break
                # Skip elapsed refreshes rather than queueing them behind a slow GATT write.
                if loop.time() >= start + (duration + 100) / 1000:
                    note_frame_skipped()
                    break
                await self._send(link, wire, cancel, on_attempt=on_attempt)
                tick = max(tick + 1, int((loop.time() - start) / app.REFRESH_SECONDS) + 1)
        finally:
            if attempted and (
                item.fixed or (not save and item.release in ("stop_always", "stop_if_ticked"))
            ):
                if self._current(link):
                    await self._send(
                        link,
                        self._wire((codec.STOP, codec.STOP), link, fixed=item.fixed),
                        asyncio.Event(),
                        counted=False,
                    )

    def _held(self, item: app.Control) -> bool:
        return item.sustain is not None or self._manual_motor(item)

    @staticmethod
    def _manual_motor(item: app.Control) -> bool:
        return (
            item.short is not None
            and item.release == "stop_always"
            and controls.is_directional(item)
        )

    async def stop_all(self) -> None:
        link = self._live()
        await self._send(
            link,
            self._wire((codec.STOP, codec.STOP), link, fixed=self.route == "roomi"),
            self._coordinator.cancel_command,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise failed("dorsal_receiver_unavailable")
        if self._link is None:
            service = next(
                (s for s in client.services if s.uuid.lower() == _GENERIC_ATTRIBUTE), None
            )
            changed = (
                next(
                    (c for c in service.characteristics if c.uuid.lower() == _SERVICE_CHANGED), None
                )
                if service
                else None
            )
            if changed is not None and {"indicate", "notify"}.intersection(changed.properties):
                await client.start_notify(changed, self._service_changed)
                self._subscriptions.append(changed)
            self._link = select_link(client)
        link = self._live()
        if link.rx is not None and link.rx not in self._subscriptions:
            await client.start_notify(link.rx, partial(self._receive, link))
            self._live()
            self._subscriptions.append(link.rx)

    @staticmethod
    def _service_changed(_sender: BleakGATTCharacteristic, _data: bytearray) -> None:
        """The Bluetooth stack owns its service cache and connection lifecycle."""

    def _receive(self, link: AppLink, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if not self._current(link):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        for frame in self._stream.feed(bytes(data)):
            result = decode(frame)
            if isinstance(result, Alarm):
                self._alarms[result.slot] = result
                self._alarm_updated.set()
            else:
                self._status.update(
                    {key: value for key, value in result.items() if key != "sleep_name"}
                )
                self._publish(result)
        if self._stream.pending:
            self._expiry = asyncio.get_running_loop().call_later(0.5, self._expire)

    def _expire(self) -> None:
        self._expiry = None
        self._stream.pending = b""

    def _publish(self, status: Status) -> None:
        if isinstance(light := status.get("bed_light"), bool):
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(light))
        if isinstance(locked := status.get("locked"), bool):
            self.forward_controller_state_updates(REMOTE_CONTROL_LOCK(locked))
        if isinstance(active := status.get("massage_on"), bool):
            self._massage_reports += 1
            self.forward_controller_state_updates(MASSAGE_ACTIVE(active))
        if type(fan := status.get("fan_level")) is int:
            self.forward_controller_state_updates(FAN_LEVEL(fan))
        for key, state in _MASSAGE_LEVEL.items():
            if type(intensity := status.get(key)) is int:
                self.forward_controller_state_updates(state(intensity))

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "dorsal": {"project": self.code, **self._status, "alarm_slots": sorted(self._alarms)}
        }

    async def stop_notify(self) -> None:
        client = self.client
        subscriptions, self._subscriptions = self._subscriptions, []
        if client is not None and client.is_connected:
            for char in reversed(subscriptions):
                try:
                    await client.stop_notify(char)
                except BleakError:
                    _LOGGER.debug("Could not release Dorsal subscription", exc_info=True)

    def on_disconnect(self) -> None:
        if self._expiry is not None:
            self._expiry.cancel()
        self._expire()
        self._subscriptions.clear()
        self._alarms.clear()
        self._status.clear()
        self._alarm_updated.set()
        self._link = None

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        cancel = asyncio.Event()
        exit_action, exit_opcode = app.PROFILE_PROBES[0]
        await self._send(
            link,
            codec.function(exit_opcode, action=exit_action, single=link.query_single),
            cancel,
            counted=False,
        )
        if self.code is not None and _admitted.get(self._coordinator) != self.code:
            for action, opcode in app.PROFILE_PROBES:
                await asyncio.sleep(app.PROBE_SECONDS)
                if not self._current(link):
                    return
                await self._send(
                    link,
                    codec.function(opcode, action=action, single=link.query_single),
                    cancel,
                    counted=False,
                )
            _admitted[self._coordinator] = self.code

    async def async_refresh_diagnostics(self) -> None:
        link = self._live()
        action, opcode = app.PROFILE_PROBES[2]
        await self._send(
            link,
            codec.function(opcode, action=action, single=link.query_single),
            self._coordinator.cancel_command,
            counted=False,
        )

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self._modes:
            return None
        return AlarmCapability(
            wake_actions=("none", *self._modes),
            weekdays=True,
            slots=7,
            requires_slot=True,
            live_check=True,
            confirm_actions=frozenset(name for name in self._modes if name.startswith("memory_")),
        )

    async def refresh_alarms(self) -> dict[int, Alarm]:
        link = self._live()
        if link.rx is None:
            raise failed("dorsal_alarm_report_missing")
        self._alarms.clear()
        self._alarm_updated.clear()
        await self._send(
            link,
            codec.record_20_len(5, 1, 0, (0,)),
            self._coordinator.cancel_command,
            counted=False,
        )
        cancel = self._coordinator.cancel_command
        # There is no terminal list record. Wait for a bounded quiet window.
        try:
            async with asyncio.timeout(1):
                while self._current(link) and not cancel.is_set():
                    try:
                        await asyncio.wait_for(self._alarm_updated.wait(), 0.25)
                    except TimeoutError:
                        break
                    self._alarm_updated.clear()
        except TimeoutError:
            pass
        if not self._current(link):
            raise failed("dorsal_receiver_unavailable")
        if cancel.is_set():
            raise asyncio.CancelledError
        return dict(self._alarms)

    def _alarm_record(
        self,
        alarm: AlarmRequest,
        current: Alarm | None,
        *,
        create_or_replace: bool = False,
    ) -> Alarm:
        if current is None and not create_or_replace:
            raise failed("dorsal_alarm_report_missing")
        if not alarm.enabled:
            assert current is not None
            return replace(current, repeat=current.repeat & 0xFE)
        repeat = 1 | sum(1 << (7 - day) for day in alarm.weekdays)
        if alarm.wake_action == "none":
            if current is None:
                raise invalid("dorsal_alarm_choose_mode")
            return replace(current, hour=alarm.hour, minute=alarm.minute, repeat=repeat)
        if current is not None and (current.kind != 0 or current.selector == 0xFF):
            raise invalid("dorsal_alarm_opaque")
        if (selector := self._modes.get(alarm.wake_action)) is None:
            raise invalid("dorsal_control_unavailable")
        return Alarm(alarm.slot, 0, alarm.hour, alarm.minute, selector, repeat)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self._alarm_record(alarm, (await self.refresh_alarms()).get(alarm.slot))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        if not self._modes:
            raise invalid("dorsal_control_unavailable")
        record = self._alarm_record(alarm, (await self.refresh_alarms()).get(alarm.slot))
        await self._send(self._live(), record.encode(), self._coordinator.cancel_command)

    async def create_or_replace_alarm(self, alarm: AlarmRequest) -> None:
        current = (await self.refresh_alarms()).get(alarm.slot)
        record = self._alarm_record(alarm, current, create_or_replace=True)
        await self._send(self._live(), record.encode(), self._coordinator.cancel_command)

    async def change_stored_alarm(self, slot: int, enabled: bool | None) -> None:
        current = (await self.refresh_alarms()).get(slot)
        if current is None:
            raise failed("dorsal_alarm_report_missing")
        wire = (
            codec.record_20_len(5, 2, 1, (slot,))
            if enabled is None
            else replace(current, repeat=(current.repeat & 0xFE) | int(enabled)).encode()
        )
        await self._send(self._live(), wire, self._coordinator.cancel_command)


async def build_controller(ctx: BuildContext) -> DorsalController:
    route = ctx.variant if ctx.variant and ctx.variant in app.ROUTES else "cprn"
    exact = ctx.data.get(CONF_PRODUCT_TYPE)
    code = app.code_for(route, exact)
    if (route == "restored" or route == "roomi" and exact) and code is None:
        raise invalid("dorsal_project_code")
    if ctx.client is not None:
        validate_name(ctx.coordinator.hass, ctx.coordinator.address, route, ctx.live_device_name)
    return DorsalController(ctx.coordinator, route, code)
