"""Enso 2 layout dispatch, GATT session and companion accessory controls."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final, cast

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability
from ...card import CARD_CONTROLLED_SIDE, CARD_LIGHTING, CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import richmat
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME, CONF_ENSO2_PROPERTY_FALLBACK
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, failed, invalid
from ...execution import ExecutionCapabilities
from ...profiles import enso2 as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, classify, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from . import receive as rx

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...alarm import AlarmRequest
    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator
    from ..base import ControllerSession
    from ..builder import BuildContext

_MODE: Final = StateKey[str | None]("enso2_mode")
_LIGHT_TIMER: Final = StateKey[int | None]("enso2_light_timer")
_LIGHT_TIMER_ENTITY_KEY: Final = f"controller_number_{_LIGHT_TIMER}"
_ALARM_STATUS: Final = StateKey[str | None]("enso2_alarm_status")
_AROMA_STATUS: Final = StateKey[str | None]("enso2_aroma_status")
_WRITE: Final = {"write", "write-without-response"}
_NOTIFY: Final = {"notify", "indicate"}


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    raw: bool

    @property
    def notifiable(self) -> bool:
        return bool(_NOTIFY.intersection(self.notify.properties))


def _select_link(client: BleakClient, fallback: bool) -> Link:
    services = list(client.services)
    for route in app.TRANSPORTS:
        service = next((item for item in services if item.uuid.lower() == route.service_uuid), None)
        if service is None:
            continue
        write = service.get_characteristic(route.write_uuid)
        notify = service.get_characteristic(route.notify_uuid)
        if (
            write is None
            or notify is None
            or not _WRITE.intersection(write.properties)
            or not _NOTIFY.intersection(notify.properties)
        ):
            raise failed("enso2_gatt_missing")
        return Link(client, write, notify, route.single)

    if fallback and len(services) >= 3:
        service = services[2]
        if service.uuid.lower() != richmat.TRANSPORTS["w3"].service_uuid:
            write = notify = None
            for characteristic in service.characteristics:
                if _WRITE.intersection(characteristic.properties):
                    write = characteristic
                if (
                    _NOTIFY.intersection(characteristic.properties)
                    or "read" in characteristic.properties
                ):
                    notify = characteristic
            if write is not None and notify is not None:
                return Link(client, write, notify, True)
    raise failed("enso2_gatt_missing")


def _parse_motor(label: str) -> tuple[str, bool] | None:
    match = re.fullmatch(
        r"(Motor [1-7](?:\+[1-7])?|Motors [1-7] and [1-7](?: tilt)?|Selected motor) (up|down)",
        label,
    )
    if not match:
        return None
    axis = match[1].lower().replace(" and ", "_").replace(" ", "_")
    if "+" in axis:
        axis = "motors_" + axis.removeprefix("motor_").replace("+", "_")
    return axis, match[2] == "up"


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    """Return true if stopped before the next frame is due."""
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def _press(controller: BedController, key: str, *, alternate: bool = False) -> None:
    await cast("Enso2Controller", controller).press(key, alternate=alternate)


class Enso2Controller(BedController):
    """One remote layout, one physical key stream and its leased END."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        layout: app.Layout,
        name: str | None,
        property_fallback: bool = False,
    ) -> None:
        super().__init__(coordinator)
        self.layout = layout
        self.name = name
        self._property_fallback = property_fallback
        self._link: Link | None = None
        self._raw: bool | None = None
        self._receiver = rx.Receiver()
        self._subscription: object | None = None
        self._cleanup: tuple[Link, int, CommandContext] | None = None
        self._alarm_present = self._light_present = self._aroma_present = False
        self._mode = 0
        self._hold_selection = False
        self._selected_motor = 53

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link is not None else app.TRANSPORTS[0].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return self._link is None or self._link.notifiable

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.layout.execution

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Keep the local choice through HA's quick BLE handoff.
        return {
            "mode": self._mode,
            "hold": self._hold_selection,
            "selected_motor": self._selected_motor,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        mode = state.get("mode")
        self._mode = mode if type(mode) is int and 0 <= mode < self.layout.mode_count else 0
        self._hold_selection = state.get("hold") is True
        motor = state.get("selected_motor")
        self._selected_motor = (
            motor
            if self.layout.name == "U3RM"
            and type(motor) is int
            and motor in app.SELECTED_MOTOR_KEYS
            else 53
        )

    @property
    def mode(self) -> int:
        return self._mode if self._raw is not True else 0

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        if (
            link is None
            or (expected is not None and expected is not link)
            or not link.client.is_connected
            or self.client is not link.client
        ):
            raise BedNotConnectedError
        return link

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        self._link = _select_link(client, self._property_fallback)
        self._raw = self._link.raw

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if not link.notifiable or self._subscription is not None:
            return
        token = object()
        self._subscription = token

        def received(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription is not token
                or self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
                or sender.handle != link.notify.handle
                or sender.uuid.lower() != link.notify.uuid.lower()
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for frame in self._receiver.feed(data):
                self._received(frame)

        try:
            await link.client.start_notify(link.notify, received)
            self._live(link)
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise

    def _received(self, frame: bytes) -> None:
        if frame == rx.ALARM_PRESENT and self.layout.alarm_tags:
            self._alarm_present = True
        elif frame in (rx.LIGHT_OFF, rx.LIGHT_ON):
            self._light_present = True
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(frame == rx.LIGHT_ON))
        elif frame == rx.AROMA_PRESENT:
            self._aroma_present = True
        elif frame in (rx.ALARM_SET, rx.ALARM_CANCELLED) and self.layout.alarm_tags:
            self.forward_controller_state_updates(
                _ALARM_STATUS("set" if frame == rx.ALARM_SET else "cancelled")
            )
        elif frame in (rx.AROMA_SAVED, rx.AROMA_REJECTED) and self._aroma_present:
            self.forward_controller_state_updates(
                _AROMA_STATUS("accepted" if frame == rx.AROMA_SAVED else "rejected")
            )

    async def stop_notify(self) -> None:
        link = self._link
        subscribed = self._subscription is not None
        self._subscription = None
        self._receiver.buffer.clear()
        if subscribed and link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._subscription = None
        self._receiver.buffer.clear()
        self._cleanup = None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            _ALARM_STATUS(None),
            _AROMA_STATUS(None),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()
        link = self._live()
        cancel = asyncio.Event()
        if not link.raw:
            await asyncio.sleep(0.3)
            await self._send(link, app.INIT, cancel, track=False)
        if link.notifiable:
            await self._query_accessories(link, cancel)
        self._live(link)
        # Local gesture changes must remain visible to offline all-target preflight.
        self._coordinator.cache_capability_controller()
        self.forward_controller_state_updates(_MODE(f"mode_{self.mode + 1}"))

    async def _query_accessories(self, link: Link, cancel: asyncio.Event) -> None:
        frames = (
            (app.ALARM_QUERY, app.LED_QUERY, app.AROMA_QUERY)
            if self.layout.alarm_tags
            else (app.LED_QUERY, app.AROMA_QUERY)
        )
        for index, frame in enumerate(frames):
            if index:
                await asyncio.sleep(0.5)
            await self._send(link, frame, cancel, track=False)
        # Allow the final accessory query the same response window as its predecessors.
        await asyncio.sleep(0.5)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def _send(
        self, link: Link, frame: bytes, cancel: asyncio.Event, *, track: bool = True
    ) -> None:
        def check() -> None:
            self._live(link)

        # Drain an already-submitted write before releasing the command lane.
        async def write() -> None:
            async with asyncio.timeout(5):
                await self._write_gatt_with_retry(
                    link.write.uuid,
                    frame,
                    cancel_event=cancel,
                    response="write" in link.write.properties,
                    characteristic=link.write,
                    expected_client=link.client,
                    before_write=check,
                    track_command_write=track,
                )

        await settled(write())

    async def _end(
        self, link: Link, mode: int, delay: float, context: CommandContext | None
    ) -> None:
        async def release() -> None:
            if delay:
                await asyncio.sleep(delay)
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            await self._send(
                link, app.key_frame(richmat.STOP, mode, raw=link.raw), asyncio.Event(), track=False
            )
            if context is not None:
                context.cleanup_stop_sent = True
                self._cleanup = (link, mode, context)

        await settled(release())

    @property
    def _controls(self) -> Mapping[str, app.Control]:
        return self.layout.raw_controls if self._raw else self.layout.controls

    def _active(self, control: app.Control) -> bool:
        return control.behavior != "hold_only" or self._hold_selection

    def _available(self, control: app.Control) -> bool:
        return self._active(control) and (
            control.is_axis_selector
            or control.alternate is not None
            or (self._raw is not True and control.framed is not None)
            or (self._raw is not False and control.raw is not None)
        )

    def _held(self, control: app.Control) -> bool:
        return control.can_hold and (control.behavior != "selectable" or self._hold_selection)

    def _key(self, link: Link, control: app.Control) -> int | None:
        if control.is_axis_selector:
            return app.SELECTED_MOTOR_KEYS[self._selected_motor][int(control.tag == "52")]
        return control.key(link.raw)

    async def press(
        self,
        name: str,
        *,
        alternate: bool = False,
        duration_ms: int | None = None,
    ) -> None:
        control = self._controls.get(name)
        if control is None or not self._available(control):
            raise invalid("enso2_control_unavailable")
        link = self._live()
        mode = self.mode
        tick = app.tick_ms(self.name, raw=link.raw)
        cancel = self._coordinator.cancel_command
        context = current_command_context()
        if cancel.is_set():
            note_frame_skipped()
            return
        self._cleanup = None
        key = self._key(link, control)
        is_long = alternate
        stream = not is_long and (
            control.status == 1 or control.behavior == "armed" or self._held(control)
        )
        if is_long:
            if control.alternate is None:
                raise invalid("enso2_control_unavailable")
            threshold = 0 if control.behavior == "armed" else control.threshold_ms // tick * tick
            if threshold and await _pause(threshold / 1000, cancel):
                note_frame_skipped()
                return
        code = control.alternate if is_long else key
        if code is None:
            raise invalid("enso2_control_unavailable")

        # Immutable command bytes and END mode are owned by this command until it settles.
        frame = app.key_frame(code, mode, raw=link.raw)
        release = (
            stream or not is_long or not link.raw or key is not None or control.behavior == "armed"
        )
        delay = 0.05 if stream or control.behavior == "armed" or is_long and key is None else 0.15
        loop = asyncio.get_running_loop()
        requested_duration = duration_ms if duration_ms is not None else 1000
        deadline = loop.time() + requested_duration / 1000
        try:
            while True:
                started = loop.time()
                await self._send(link, frame, cancel)
                if not stream:
                    break
                wait = min(started + tick / 1000, deadline) - loop.time()
                if wait > 0 and await _pause(wait, cancel):
                    break
                if cancel.is_set() or loop.time() >= deadline:
                    break
            if not cancel.is_set():
                if control.tag in ("53", "54", "55"):
                    self._selected_motor = int(control.tag)
                    self._coordinator.save_app_state(self)
                if control.behavior in ("hold", "release"):
                    self._hold_selection = control.behavior == "hold"
                    self._coordinator.save_app_state(self)
                    self.forward_controller_state_updates(_MODE(f"mode_{mode + 1}"))
        finally:
            if release:
                await self._end(link, mode, delay, context)

    async def stop_all(self) -> None:
        link = self._live()
        mode = self.mode
        context = current_command_context()
        cleanup = self._cleanup
        self._cleanup = None
        if cleanup is not None and context is not None:
            owner_link, owner_mode, owner = cleanup
            if (
                owner_link is link
                and owner_mode == mode
                and owner.scheduler_token is context.scheduler_token
                and any(owner is prior for prior in context.preempted_contexts)
                and owner.cleanup_stop_sent
            ):
                owner.cleanup_stop_sent = False
                return
        await self._send(link, app.key_frame(richmat.STOP, mode, raw=link.raw), asyncio.Event())

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, control in self._controls.items()
            if self._available(control) and self._held(control)
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 100 <= duration_ms <= 60000:
            raise invalid("enso2_control_unavailable")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.press(control, duration_ms=self.leased_hold_ms(duration_ms))

    @property
    def _directions(self) -> dict[tuple[str, bool], str]:
        return {
            motor: key
            for key, control in self._controls.items()
            if self._available(control)
            and self._held(control)
            and (motor := _parse_motor(control.label)) is not None
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        dirs = self._directions
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                partial(_press, key=up),
                partial(_press, key=down),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(up, down, stop_scope="side", press_is_native=True),
            )
            for (axis, rising), up in dirs.items()
            if rising and (down := dirs.get((axis, False))) is not None
        )

    @property
    def supports_motor_control(self) -> bool:
        return bool(self._directions)

    async def _move(self, axis: str, up: bool) -> None:
        key = self._directions.get((axis, up))
        if key is None:
            raise invalid("enso2_control_unavailable")
        await self.press(key)

    async def move_head_up(self) -> None:
        await self._move("motor_1", True)

    async def move_head_down(self) -> None:
        await self._move("motor_1", False)

    async def move_legs_up(self) -> None:
        await self._move("motor_2", True)

    async def move_legs_down(self) -> None:
        await self._move("motor_2", False)

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    @property
    def supports_preset_flat(self) -> bool:
        return False  # The layout button owns its exact hold metadata.

    async def preset_flat(self) -> None:
        if "flat" not in self._controls:
            raise NotImplementedError
        await self.press("flat")

    @property
    def memory_slot_count(self) -> int:
        return max((n for n in range(1, 7) if f"memory_{n}" in self._controls), default=0)

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.memory_slot_count)

    @property
    def supports_memory_programming(self) -> bool:
        return any(
            self.is_memory_slot_programmable(n) for n in range(1, self.memory_slot_count + 1)
        )

    def validate_memory_recall(self, memory_num: int) -> None:
        control = self._controls.get(f"memory_{memory_num}")
        if (
            control is None
            or not self._available(control)
            or (self._raw is not None and control.key(self._raw) is None)
        ):
            raise invalid("enso2_control_unavailable")

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        control = self._controls.get(f"memory_{memory_num}")
        save = self._controls.get(f"save_memory_{memory_num}")
        return bool(
            control is not None
            and control.alternate is not None
            or save is not None
            and self._available(save)
        )

    async def preset_memory(self, memory_num: int) -> None:
        if not self.supports_memory_presets:
            raise NotImplementedError
        self.validate_memory_recall(memory_num)
        await self.press(f"memory_{memory_num}")

    @property
    def supports_held_memory_recall(self) -> bool:
        return any(
            self.supports_memory_recall_duration(slot)
            for slot in range(1, self.memory_slot_count + 1)
        )

    def supports_memory_recall_duration(self, slot: int) -> bool:
        control = self._controls.get(f"memory_{slot}")
        return control is not None and self._available(control) and self._held(control)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        if not self.supports_memory_recall_duration(slot):
            raise invalid("preset_duration_not_supported", device_name=self._coordinator.name)
        await self.press(f"memory_{slot}", duration_ms=hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        if not self.supports_memory_programming:
            raise NotImplementedError
        key = f"save_memory_{memory_num}"
        save = self._controls.get(key)
        if save is not None and self._available(save):
            await self.press(key)
        elif self.is_memory_slot_programmable(memory_num):
            await self.press(f"memory_{memory_num}", alternate=True)
        else:
            raise invalid("enso2_control_unavailable")

    @property
    def replaced_standard_button_keys(self) -> frozenset[str]:
        return frozenset(
            key
            for n in range(1, self.memory_slot_count + 1)
            for key in (f"preset_memory_{n}", f"program_memory_{n}")
        )

    def _button_keys(self) -> dict[str, str]:
        return (
            {f"enso2_{key}": key for key in self._controls}
            | {
                f"enso2_{key}_held": key
                for key, control in self._controls.items()
                if control.behavior == "selectable"
            }
            | {
                f"enso2_{key}_alternate": key
                for key, control in self._controls.items()
                if control.alternate is not None
            }
        )

    def controller_button_available(self, key: str) -> bool:
        source = self._button_keys().get(key)
        if source is None:
            return not key.startswith("enso2_")
        control = self._controls[source]
        if not self._available(control):
            return False
        if key.endswith("_alternate"):
            return not (
                self._hold_selection
                and control.behavior == "selectable"
                and any(
                    other.label == control.alternate_label and other.behavior == "hold_only"
                    for other in self._controls.values()
                )
            )
        if control.behavior == "selectable":
            return key.endswith("_held") == self._hold_selection
        return self._raw is None or control.is_axis_selector or control.key(self._raw) is not None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Standard covers own each uniquely identified motor direction.
        covered = {
            key
            for spec in self.motor_control_specs
            if spec.hold is not None
            for key in (spec.hold.up_control, spec.hold.down_control)
        }
        specs: list[ControllerButtonSpec | None] = []
        for key, control in self._controls.items():
            if not self._available(control):
                continue
            held = self._held(control)
            if key not in covered and (
                control.framed is not None or control.raw is not None or control.is_axis_selector
            ):
                button_key = f"enso2_{key}"
                if control.behavior == "selectable" and held:
                    button_key += "_held"
                if self.controller_button_available(button_key):
                    shape = classify(control.label)
                    moves = shape is not None and shape.kind in (
                        Kind.MOTOR,
                        Kind.PRESET,
                        Kind.MEMORY,
                    )
                    specs.append(
                        catalog_button(
                            button_key,
                            control.label,
                            partial(_press, key=key),
                            hold=ControllerHoldSpec(key) if held else None,
                            requires_confirmation=control.is_save or control.label == "Reset",
                            invalidates_position=held or moves,
                            scheduler_resource="*",
                        )
                    )
            if control.alternate is not None and self.controller_button_available(
                f"enso2_{key}_alternate"
            ):
                specs.append(
                    catalog_button(
                        f"enso2_{key}_alternate",
                        control.alternate_label,
                        partial(_press, key=key, alternate=True),
                        requires_confirmation=control.alternate_label.startswith("Save "),
                        scheduler_resource="*",
                    )
                )
        return unique_buttons(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs: list[ControllerSelectSpec] = []
        if self.layout.mode_count > 1 and self._raw is not True:
            # The app labels a two-mode layout's tabs Left and Right.
            sides = self.layout.mode_count == 2
            specs.append(
                ControllerSelectSpec(
                    _MODE,
                    "enso2_side" if sides else _MODE,
                    _MODE,
                    tuple(f"mode_{i + 1}" for i in range(self.layout.mode_count)),
                    lambda c, option: cast(Enso2Controller, c).set_mode(option),
                    card=CARD_CONTROLLED_SIDE if sides else CARD_UTILITY,
                )
            )
        if self.layout.name == "Y6RM":
            specs.append(
                ControllerSelectSpec(
                    "enso2_timer_options",
                    "enso2_timer_options",
                    _TIMER_CHOICE,
                    ("toggle", "10", "20", "30"),
                    lambda c, option: cast(Enso2Controller, c).set_timer_option(option),
                    card=CARD_MASSAGE_TIMER,
                )
            )
        return tuple(specs)

    async def set_mode(self, option: str) -> None:
        choices = tuple(f"mode_{i + 1}" for i in range(self.layout.mode_count))
        if self._live().raw or option not in choices or len(choices) == 1:
            raise invalid("enso2_control_unavailable")
        self._mode = choices.index(option)
        self.forward_controller_state_updates(_MODE(option))

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self._light_present:
            specs.append(
                ControllerNumberSpec(
                    _LIGHT_TIMER,
                    _LIGHT_TIMER,
                    _LIGHT_TIMER,
                    0,
                    300,
                    1,
                    lambda c, value: cast(Enso2Controller, c).set_light_duration(int(value)),
                    native_unit_of_measurement="s",
                    card=CARD_LIGHTING,
                )
            )
        return tuple(specs)

    # D1RM and D9RM have the massage slider: four stops, the first is off.
    @property
    def supports_massage_timer(self) -> bool:
        return self.layout.name in ("D1RM", "D9RM")

    @property
    def auto_enable_massage(self) -> bool:
        return super().auto_enable_massage or self.supports_massage_timer

    @property
    def massage_timer_options(self) -> list[int]:
        if not self.supports_massage_timer:
            return []
        return [minutes for minutes in app.MASSAGE_SLIDER_MINUTES if minutes]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return self.supports_massage_timer

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage_timer or minutes not in app.MASSAGE_SLIDER_MINUTES:
            raise invalid("enso2_control_unavailable")
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self._direct(
                app.massage_timer_frame(self.layout.name, app.MASSAGE_SLIDER_MINUTES[minutes])
            )

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        gesture_buttons = {
            ("button", key)
            for key, source in self._button_keys().items()
            if self._controls[source].behavior in ("selectable", "hold_only")
        }
        return frozenset(
            {("number", _LIGHT_TIMER_ENTITY_KEY), ("binary_sensor", "enso2_light_on")}
            | gesture_buttons
        )

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return () if self._light_present else (_LIGHT_TIMER_ENTITY_KEY,)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            (
                ControllerStateBinarySensorSpec(
                    "enso2_light_on",
                    "enso2_light_on",
                    UNDER_BED_LIGHTS_ON,
                    "mdi:lightbulb",
                    entity_registry_enabled_default=True,
                ),
            )
            if self._light_present
            else ()
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                _ALARM_STATUS,
                _ALARM_STATUS,
                _ALARM_STATUS,
                "mdi:alarm",
                entity_registry_enabled_default=bool(self.layout.alarm_tags),
            ),
            ControllerStateSensorSpec(
                _AROMA_STATUS,
                _AROMA_STATUS,
                _AROMA_STATUS,
                "mdi:scent",
                entity_registry_enabled_default=False,
            ),
        )

    async def set_timer_option(self, option: str) -> None:
        if self.layout.name != "Y6RM" or option not in ("toggle", "10", "20", "30"):
            raise invalid("enso2_control_unavailable")
        with self.sent_state(_TIMER_CHOICE(option)):
            await self._direct(
                app.massage_timer_frame("Y6RM", 0 if option == "toggle" else int(option))
            )

    async def set_light_duration(self, value: int) -> None:
        if not self._light_present or not 0 <= value <= 300:
            raise invalid("enso2_light_unavailable")
        with self.sent_state(_LIGHT_TIMER(value)):
            await self._direct(richmat.light_timer(value >> 8, value & 0xFF))

    def check_light(self) -> None:
        if not self._light_present:
            raise invalid("enso2_light_unavailable")

    def check_aroma(self) -> None:
        if not self._aroma_present:
            raise invalid("enso2_aroma_unavailable")

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        self.check_light()
        with self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._direct(richmat.rgb(*rgb_color))

    async def set_aroma(self, mode_2_minutes: int, mode_3_minutes: int, pause_hours: int) -> None:
        self.check_aroma()
        if not (1 <= mode_2_minutes <= 60 and 1 <= mode_3_minutes <= 60 and 1 <= pause_hours <= 12):
            raise invalid("enso2_aroma_range")
        await self._sequence(app.aroma_frames(mode_2_minutes, mode_3_minutes, pause_hours), 0.15)

    async def _direct(self, frame: bytes) -> None:
        await self._send(self._live(), frame, self._coordinator.cancel_command)

    async def _sequence(self, frames: tuple[bytes, ...], delay: float) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        for index, frame in enumerate(frames):
            if index:
                await asyncio.sleep(delay)
            await self._send(link, frame, cancel)

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        tags = self.layout.alarm_tags
        wake = tuple(action for action, code in app.ALARM_ACTIONS.items() if code in tags)
        zones = tuple(
            zone
            for zone, code in app.ALARM_MASSAGE.items()
            if code in tags or (zone == "both" and {0x4C, 0x4E} <= tags)
        )
        if not wake and not zones:
            return None
        return AlarmCapability(
            wake_actions=("none", *wake) if wake else (),
            massage_zones=zones,
            default_massage_zone=False,
            live_check=True,
            resource="*",
        )

    def _alarm_key(self, alarm: AlarmRequest) -> int:
        if not alarm.enabled:
            return 0
        tags = self.layout.alarm_tags
        action = app.ALARM_ACTIONS.get(alarm.wake_action, 0)
        if alarm.wake_action != "none" and (not action or action not in tags):
            raise invalid("enso2_alarm_unavailable")
        zone = alarm.massage_zone
        if zone is None:
            if action:
                return action
            raise invalid("alarm_needs_effect")
        massage = app.ALARM_MASSAGE.get(zone, 0)
        if not (massage in tags or zone == "both" and {0x4C, 0x4E} <= tags):
            raise invalid("enso2_alarm_unavailable")
        if not action:
            return massage
        combined = app.ALARM_COMBINED.get(action)
        if combined is None:
            raise invalid("enso2_alarm_combination")
        return combined[("both", "head", "feet").index(zone)]

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        self._alarm_key(alarm)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self._live()
        if not self.layout.direct_alarm and not self._alarm_present:
            raise invalid("enso2_alarm_unavailable")
        self._alarm_key(alarm)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        minutes = alarm.minutes_until(dt_util.now()) if alarm.enabled else 0
        await self._sequence(richmat.countdown(minutes, self._alarm_key(alarm)), 0.3)


_TIMER_CHOICE: Final = StateKey[str | None]("enso2_timer_options")


async def build_controller(ctx: BuildContext) -> BedController:
    layout = app.LAYOUTS.get(ctx.variant or "")
    if layout is None or layout.name not in app.LAYOUT_CHOICES:
        raise failed("enso2_layout_required")
    name = ctx.advertisement_name or ctx.live_device_name or ctx.data.get(CONF_BLE_DEVICE_NAME)
    return Enso2Controller(
        ctx.coordinator, layout, name, bool(ctx.data.get(CONF_ENSO2_PROPERTY_FALLBACK))
    )
