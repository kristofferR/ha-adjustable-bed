"""Casper Base app controller: drives ``codec/richmat.py`` from the selected profile."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import TYPE_CHECKING, ClassVar, Protocol

from homeassistant.util import dt as dt_util

from ..casper_base_protocol import (
    RGB_TIMERS,
    Event,
    MainReceive,
    Request,
    alarm_countdown,
    decode_main,
)
from ..codec import richmat as codec
from ..profiles.casper import (
    ACTIONS,
    ANTI_SNORE,
    LIGHT_OFF,
    MUSIC_BLUETOOTH,
    PROFILES,
    QUERIES,
    TRANSPORTS,
    Action,
    ProductRow,
    light_duration,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
# Service -> (write characteristic, bare opcodes), in the library's lookup order.
GATT = {
    transport.service_uuid: (transport.write_uuid, transport.single)
    for transport in (codec.TRANSPORTS[key] for key in TRANSPORTS)
}
TICK_S = 0.1
"""Every write, the first and each queued one, waits one tick."""
SOUNDTRACK_GUARD_S = 2
"""A soundtrack switch within this time of the last one is dropped."""
SOUNDTRACK_DELAY_S = 0.9
"""The soundtrack switch follows its Bluetooth switch after this delay."""
SNORE_POLL_S = 3
"""The external snore detector is sampled this often, first after one period."""


class ProductProfile(Protocol):
    """What this controller reads from a Casper Base or Hush Base profile."""

    @property
    def key(self) -> str: ...

    @property
    def row(self) -> ProductRow: ...


def action_label(name: str) -> str:
    return (
        re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", name)
        .replace("Lumber", "Lumbar")
        .replace("Instensity", "Intensity")
        .replace("Volumu", "Volume")
    )


async def invoke(
    controller: BedController, action: str, *, save: bool = False, music_page: bool = False
) -> None:
    target = controller._controller if isinstance(controller, SideBoundController) else controller
    if not isinstance(target, CasperBaseController):
        raise TypeError("Casper Base controller required")
    await controller.async_perform_casper_base_action(action, save=save, music_page=music_page)


class CasperBaseController(BedController):
    """Use selected product actions with live coherent service/characteristic pairing."""

    profiles: ClassVar[Mapping[str, ProductProfile]] = PROFILES
    action_catalog: ClassVar[Sequence[Action]] = ACTIONS

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator)
        profile = self.profiles.get(product)
        if profile is None:
            raise ValueError("Choose an explicit Casper Base product profile")
        self.profile = profile
        self.product = profile.row
        self.model = product
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._single = False
        self._receive = MainReceive()
        self.events: dict[str, object] = {}
        self.alarms: list[dict[str, object]] = []
        self._snore_poll: asyncio.Task[None] | None = None
        self._snore_count = 0
        self._music_debounce_until = 0.0
        self._music_bluetooth = False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_char.uuid if self._write_char else codec.TRANSPORTS["w1"].write_uuid

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.product[11] and self._write_char is not None and not self._single

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_casper_base_controls(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return "MotorReset" in self.actions

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        return max((i for i in range(1, 4) if f"MemoryPosition{i}" in self.actions), default=0)

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    def validate_memory_recall(self, memory_num: int) -> None:
        if f"MemoryPosition{memory_num}" not in self.actions:
            raise ValueError("This memory slot is unavailable")

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        item = self.actions.get(f"MemoryPosition{memory_num}")
        return item is not None and item[1] is not None

    @property
    def requires_persistent_connection(self) -> bool:
        return self._snore_poll is not None

    def controller_button_available(self, key: str) -> bool:
        return not key.startswith("casper_music_page_") or "music_available" in self.events

    @property
    def actions(self) -> dict[str, tuple[int, int | None]]:
        return {
            self.action_catalog[i][0]: (self.action_catalog[i][1], self.action_catalog[i][2])
            for group in self.product[1:6]
            for i in group
        }

    def _sides(self) -> tuple[int, ...]:
        side = self.command_side
        if side is None:
            return (0,)
        if not self.supports_single_address_pairing:
            raise ValueError("This profile has no one-address side selector")
        return (0, 1) if side == "both" else (1,) if side == "right" else (0,)

    async def _send(self, packet: bytes, *, cleanup: bool = False) -> None:
        await asyncio.sleep(TICK_S)
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            packet,
            response=self._write_with_response,
            characteristic=self._write_char,
            cancel_event=asyncio.Event() if cleanup else None,
        )

    async def _opcode(self, opcode: int, *, cleanup: bool = False) -> None:
        for side in self._sides():
            await self._send(codec.function(opcode, side, single=self._single), cleanup=cleanup)

    async def async_perform_casper_base_action(
        self, action: str, *, save: bool = False, music_page: bool = False
    ) -> None:
        item = self.actions.get(action)
        if music_page:
            item = None
            # Music page callbacks belong to its capability-gated page, not a product list.
            if self.product[8] and "music_available" in self.events and action.startswith("Music"):
                item = next(
                    ((short, long) for name, short, long in self.action_catalog if name == action),
                    None,
                )
        if item is None or (save and item[1] is None):
            raise ValueError("Action unavailable for the selected product")
        opcode = item[1] if save else item[0]
        assert opcode is not None
        if music_page:
            if action == "MusicSwitchSoundTrack":
                now = asyncio.get_running_loop().time()
                if now < self._music_debounce_until:
                    return
                self._music_debounce_until = now + SOUNDTRACK_GUARD_S
                if self._music_bluetooth:
                    self._music_bluetooth = False
                    self._publish()
                    await self._send(codec.function(MUSIC_BLUETOOTH, single=self._single))
                delay = now + SOUNDTRACK_DELAY_S - asyncio.get_running_loop().time()
                await asyncio.sleep(max(0, delay))
            elif action == "MusicBlueToothSwitch":
                self._music_bluetooth = not self._music_bluetooth
                self._publish()
            await self._send(codec.function(opcode, single=self._single))
            return
        moving = action.endswith(("Up", "Down")) and not action.startswith("Music")
        release = moving or action in (
            "MassageHeadInstensityStrengthen",
            "MassageFootInstensityStrengthen",
            "Fan1InstensityStrengthen",
            "Fan2InstensityStrengthen",
        )
        try:
            for _ in range(self._coordinator.motor_pulse_count if moving else 1):
                if self._coordinator.cancel_command.is_set():
                    break
                await self._opcode(opcode)
        finally:
            if release:
                await self._opcode(codec.STOP, cleanup=True)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        names = {
            "Head": ("back", "back"),
            "Foot": ("legs", "legs"),
            "Pillow": ("head", "head"),
            "Lumber": ("lumbar", "lumbar"),
            "HeadAndFoot": ("head_feet", "head_feet"),
            "Motor3": ("motor_3", "motor_3"),
        }
        return tuple(
            MotorControlSpec(
                key,
                translation,
                partial(invoke, action=axis + "Up"),
                partial(invoke, action=axis + "Down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
            )
            for axis, (key, translation) in names.items()
            if axis + "Up" in self.actions and axis + "Down" in self.actions
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        for name, (_short, long) in self.actions.items():
            if name.endswith(("Up", "Down")) and not name.startswith("Music"):
                continue
            for save in (False, True) if long is not None else (False,):
                key = name.lower() + ("_save" if save else "")
                label = ("Save " if save else "") + action_label(name)
                specs.append(
                    ControllerButtonSpec(
                        "casper_" + key,
                        label,
                        partial(invoke, action=name, save=save),
                        translation_key="casper_base_action",
                        translation_placeholders={"action": label},
                    )
                )
        if self.product[8]:
            for name, _, _ in self.action_catalog:
                if name.startswith("Music"):
                    label = action_label(name)
                    specs.append(
                        ControllerButtonSpec(
                            "casper_music_page_" + name.lower(),
                            label,
                            partial(invoke, action=name, music_page=True),
                            translation_key="casper_base_action",
                            translation_placeholders={"action": label},
                        )
                    )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "casper_base",
                "casper_base",
                "casper_base_model",
                "mdi:bed",
                attribute_keys=(
                    "casper_base_events",
                    "casper_base_alarms",
                    "casper_base_error",
                    "casper_base_music_bluetooth",
                ),
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self.client is None:
            raise ConnectionError("Not connected")
        for service in self.client.services:
            match = GATT.get(service.uuid.lower())
            if match is None:
                continue
            uuid, single = match
            write = next(
                (
                    c
                    for c in service.characteristics
                    if c.uuid.lower() == uuid and "write" in c.properties
                ),
                None,
            )
            notify = next((c for c in service.characteristics if "notify" in c.properties), None)
            if write is not None:
                self._write_char, self._notify_char, self._single = write, notify, single
                self._write_with_response = "write-without-response" not in write.properties
                break
        if self._write_char is None:
            raise ValueError("No supported writable Casper Base service")
        if self._notify_char is not None:
            await self.client.start_notify(self._notify_char, self._build_notification_callback())
        for action, code in QUERIES:
            await self._send(codec.function(code, action=action, single=self._single))
        if self.product[10]:
            await self._send(codec.calendar(dt_util.now(), build=codec.record_20_len))
        self._publish()

    def _build_notification_callback(self) -> Callable[[BleakGATTCharacteristic, bytearray], None]:
        return self._on_notification

    async def stop_notify(self) -> None:
        if self.client and self.client.is_connected and self._notify_char:
            await self.client.stop_notify(self._notify_char)
        self.on_disconnect()

    def on_disconnect(self) -> None:
        if self._snore_poll is not None:
            self._snore_poll.cancel()
            self._snore_poll = None
        self._receive = MainReceive()
        self._write_char = self._notify_char = None

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(
            self._notify_char.uuid if self._notify_char else "", bytes(data)
        )
        try:
            for packet in self._receive.feed(bytes(data)):
                if event := decode_main(packet):
                    self._consume(event)
        except (ValueError, IndexError) as err:
            self.forward_controller_state_update("casper_base_error", str(err))
        self._publish()

    def _consume(self, event: Event) -> None:
        self.events[event.name] = event.values
        if event.name == "accessories":
            self._music_bluetooth = event.values["bluetooth"] is True
        elif event.name == "music_bluetooth":
            self._music_bluetooth = event.values["value"] is True
        if event.name in ("clock_add_ok", "clock_cancel_ok"):
            self.events["clock_status"] = "set" if event.name == "clock_add_ok" else "cancelled"
        if event.name == "alarm_list":
            if event.values not in self.alarms:
                self.alarms.append(event.values)
        elif event.name == "alarm_update":
            for index, alarm in enumerate(self.alarms):
                if alarm["id"] == event.values["id"]:
                    self.alarms[index] = event.values
                    break
            else:
                self.alarms.append(event.values)

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            {
                "casper_base_model": self.product[0],
                "casper_base_events": dict(self.events),
                "casper_base_alarms": list(self.alarms),
                "casper_base_music_bluetooth": self._music_bluetooth,
            }
        )

    def validate_casper_base_request(self, request: Request) -> None:
        op = request.operation
        light_page = self.product[6] and "light_available" in self.events
        if op in ("light_rgb", "light_seconds", "light_off"):
            if not light_page or self.product[7]:
                raise ValueError("Ordinary light page unavailable")
        elif op.startswith("rgb_"):
            if not light_page or not self.product[7]:
                raise ValueError("RGB page unavailable")
            if op == "rgb_timer" and request.value not in RGB_TIMERS:
                raise ValueError("Unsupported RGB timer duration")
            if op == "rgb_mode" and request.value not in (2, 3, 5):
                raise ValueError("Unsupported colour mode")
            if op == "rgb_groove" and request.value not in (1, 2, 3, 4):
                raise ValueError("Unsupported groove mode")
        elif op in ("alarm", "alarm_cancel"):
            if not self.product[4] or "clock_available" not in self.events:
                raise ValueError("Alarm page unavailable")
        elif op in ("repeat_alarm", "repeat_delete", "repeat_query", "time_sync"):
            if not self.product[10] or "clock_available" not in self.events:
                raise ValueError("Repeating alarm page unavailable")
        elif op == "sleep_name":
            if not self.product[9]:
                raise ValueError("Sensor menu unavailable")
        elif op == "snore_detector":
            if request.enabled and not request.source:
                raise ValueError("Choose an external detector status entity")
        else:
            raise ValueError("Unknown Casper Base operation")
        if op in ("alarm", "repeat_alarm"):
            if not any(self.action_catalog[i][0] == request.mode for i in self.product[4]):
                raise ValueError("Alarm position not listed for this product")

    def alarm_opcode(self, mode: str) -> int:
        return self.actions[mode][0]

    async def async_execute_casper_base_request(self, request: Request) -> None:
        r = request
        self.validate_casper_base_request(r)
        op = r.operation
        if op == "snore_detector":
            if self._snore_poll is not None:
                self._snore_poll.cancel()
                self._snore_poll = None
            self._snore_count = 0
            if r.enabled:
                self._snore_poll = self._coordinator.hass.async_create_background_task(
                    self._poll_snore(r.source), "Casper Base external snore detector"
                )
            return
        packets: tuple[bytes, ...]
        record = codec.record_20_len
        if op == "sleep_name":
            packets = (record(6, 3, 0, (0,)),)
        elif op == "light_rgb":
            packets = (codec.rgb(*r.rgb),)
        elif op == "light_seconds":
            packets = (codec.light_timer(*light_duration(r.value)),)
        elif op == "light_off":
            packets = (codec.function(LIGHT_OFF, single=self._single),)
        elif op == "rgb_power":
            packets = (record(4, 4, 1, (0, int(r.enabled))),)
        elif op == "rgb_color":
            packets = (record(4, 1, 1, (0, *r.rgb)),)
        elif op == "rgb_timer":
            packets = (record(4, 2, 1, (0, r.value // 256, r.value & 255)),)
        elif op in ("rgb_mode", "rgb_groove"):
            packets = (record(4, 5, 1, (0, 2 if op == "rgb_groove" else 1, r.value)),)
        elif op == "rgb_breathe":
            packets = (record(4, 6, 1, (0,)),)
        elif op == "alarm_cancel":
            # The high and mode frame goes first.
            packets = codec.countdown(0, 0)[::-1]
        elif op == "alarm":
            now = dt_util.now()
            minutes = alarm_countdown(r.hour, r.minute, now)
            packets = codec.countdown(minutes, self.alarm_opcode(r.mode))[::-1]
        elif op == "repeat_alarm":
            mask = sum(1 << (7 - day) for day in set(r.days)) | int(r.enabled)
            existing = next((alarm for alarm in self.alarms if alarm["id"] == r.slot), {})
            reserved = existing.get("reserved", 0)
            if type(reserved) is not int:
                raise ValueError("Invalid stored alarm byte")
            fields = (r.slot, reserved, r.hour, r.minute, self.alarm_opcode(r.mode), mask)
            packets = (record(5, 1, 1, fields),)
        elif op == "repeat_delete":
            packets = (record(5, 2, 1, (r.slot,)),)
        elif op == "repeat_query":
            self.alarms.clear()
            self._publish()
            packets = (record(5, 1, 0, (0,)),)
        elif op == "time_sync":
            packets = (codec.calendar(dt_util.now(), build=record),)
        else:
            raise ValueError("Unknown Casper Base operation")
        for packet in packets:
            await self._send(packet)

    async def _poll_snore(self, source: str) -> None:
        try:
            while True:
                await asyncio.sleep(SNORE_POLL_S)
                state = self._coordinator.hass.states.get(source)
                try:
                    result = int(state.state) if state is not None else None
                except ValueError:
                    result = None
                await self._coordinator.async_execute_controller_command(
                    lambda _, value=result: self._snore_result(value),
                    cancel_running=False,
                    resource="configuration",
                )
        except asyncio.CancelledError:
            raise
        except ConnectionError, ValueError:
            _LOGGER.debug("External snore detector session stopped", exc_info=True)
        finally:
            if self._snore_poll is asyncio.current_task():
                self._snore_poll = None
                self._coordinator.resume_disconnect_timer()

    async def _snore_result(self, result: int | None) -> None:
        if result is None or result == 0:
            self._snore_count = 0
        elif result == 1:
            self._snore_count += 1
        if self._snore_count >= 5:
            # Automatic path always uses default left, independent of manual side.
            await self._send(codec.function(ANTI_SNORE, single=self._single))
            self._snore_count = 0

    async def _axis(self, name: str, direction: str) -> None:
        await self.async_perform_casper_base_action(name + direction)

    async def move_head_up(self) -> None:
        await self._axis("Pillow", "Up")

    async def move_head_down(self) -> None:
        await self._axis("Pillow", "Down")

    async def move_back_up(self) -> None:
        await self._axis("Head", "Up")

    async def move_back_down(self) -> None:
        await self._axis("Head", "Down")

    async def move_legs_up(self) -> None:
        await self._axis("Foot", "Up")

    async def move_legs_down(self) -> None:
        await self._axis("Foot", "Down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        await self._opcode(codec.STOP, cleanup=True)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        await self.async_perform_casper_base_action("MotorReset")

    async def preset_memory(self, memory_num: int) -> None:
        await self.async_perform_casper_base_action(f"MemoryPosition{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        await self.async_perform_casper_base_action(f"MemoryPosition{memory_num}", save=True)
