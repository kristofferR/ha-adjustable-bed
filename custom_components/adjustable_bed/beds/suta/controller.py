"""SUTA's data-driven BED controller with one fenced physical BLE session."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_PRESETS, CARD_UTILITY
from ...codec import suta as codec
from ...command_scheduler import current_command_context
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.suta import (
    BINARY,
    FLAT_EFFECT,
    SHARED,
    SHORT_NAME,
    SNORE_EFFECT,
    Command,
    profile_for_name,
    service_for_name,
)
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .receive import TextReceiver, moon, temp

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext

MODEL: Final = StateKey[str]("suta_model")
OBSERVATIONS: Final = StateKey[dict[str, object]]("suta_observations")
LEFT_SETPOINT: Final = StateKey[int | None]("suta_left_setpoint")
RIGHT_SETPOINT: Final = StateKey[int | None]("suta_right_setpoint")
_LOGGER = logging.getLogger(__name__)
WRITE_TIMEOUT: Final = 5.0  # HA transport bound, not a firmware timing claim.


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notifications: tuple[BleakGATTCharacteristic, ...]
    owner: AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Request:
    action: str
    suffix: str = ""
    logical_side: int | None = None
    value: int | None = None
    weekdays: tuple[int, ...] = ()
    time: str = "0630"
    loop: str = "00"


class SutaController(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, name: str | None = None) -> None:
        super().__init__(coordinator)
        # Display titles never override an explicit BLE identity. The saved
        # name is a legacy migration fallback, only for SUTA-prefixed names.
        stored = coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
        legacy = coordinator.entry.data.get("name", "")
        self.name = name if name is not None else stored if isinstance(stored, str) else legacy if isinstance(legacy, str) and legacy.startswith("SUTA-") else ""
        self.profile = profile_for_name(self.name) or SHORT_NAME
        self.family = "MOON" if self.profile.key == "IMattressFragment" else "TEMP" if self.profile.key == "TempControllerFragment" else "P1"
        self._link: Link | None = None
        self._receiver = TextReceiver()
        self.observations: dict[str, object] = {}
        self._cycles: dict[str, str] = {}
        self._gesture_released = False
        self._cleanup_context = None

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        # No guessed FFF2 fallback. An empty offline role cannot be written.
        return self._link.write.uuid if self._link else ""

    @property
    def commands_share_timer(self) -> bool:
        return True

    def standard_button_requires_confirmation(self, key: str) -> bool:
        return key.startswith("program_memory_")

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = {"preset_tv": "both_set_tv", "preset_anti_snore": "both_set_snore",
                  "preset_zero_g": "set_mode_zerog"}.get(key)
        if key.startswith("preset_memory_"):
            action = "set_mode_both_m" + key.removeprefix("preset_memory_")
        return ControllerHoldSpec(action, release_button_key="suta_release") if action in self.held_control_options else None

    @property
    def supports_single_address_pairing(self) -> bool:
        # Controls already name their logical side. Whole-device heating and
        # queries must not be presented as side-isolated operations.
        return False

    @property
    def supports_motor_control(self) -> bool:
        return any(c.kind == "motion" for c in self.profile.commands.values())

    @property
    def supports_stop_all(self) -> bool:
        return "both_stop" in self.profile.commands

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        return max((n for n in range(1, 5) if f"mode_both_m{n}" in self.profile.commands), default=0)

    @property
    def supports_memory_programming(self) -> bool:
        return any(k.startswith("set_mode_both_m") for k in self.profile.commands)

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return f"set_mode_both_m{memory_num}" in self.profile.commands

    def validate_memory_recall(self, memory_num: int) -> None:
        if f"mode_both_m{memory_num}" not in self.profile.commands:
            raise ValueError("This SUTA layout does not expose that memory recall")

    @property
    def supports_preset_flat(self) -> bool:
        return "mode_flat" in self.profile.commands

    @property
    def supports_preset_zero_g(self) -> bool:
        return "mode_zerog" in self.profile.commands

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "both_snore" in self.profile.commands

    @property
    def supports_preset_tv(self) -> bool:
        return "both_tv" in self.profile.commands

    @property
    def supports_lights(self) -> bool:
        return "light_enable" in self.profile.commands

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_position_feedback(self) -> bool:
        return self.profile.key == "MattressControllerMotorFragment"

    @property
    def position_number_specs(self) -> tuple[()]:
        # Raw RBHC feedback proves no target-angle command or seek calibration.
        return ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(k for k, c in self.profile.commands.items() if c.kind in ("motion", "save"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or isinstance(duration_ms, bool) or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose a SUTA layout control and duration from 1 to 60000 ms")

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, self.profile.refresh_ms or 150

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # BOTT/TWO/HTWO remain app-labelled controls; they prove no anatomy.
        axes = (("back", "back"), ("legs", "foot"), ("head", "head"), ("lumbar", "tl"))
        return tuple(
            MotorControlSpec(
                axis, axis, partial(_action, key="ctrl_" + remote + "_up"),
                partial(_action, key="ctrl_" + remote + "_down"), lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec("ctrl_" + remote + "_up", "ctrl_" + remote + "_down", press_is_native=True, stop_scope="side"),
            )
            for axis, remote in axes
            if all("ctrl_" + remote + "_" + direction in self.profile.commands for direction in ("up", "down"))
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec] = []
        standard = {"mode_flat", "mode_zerog", "both_tv", "both_snore", "both_stop", "light_enable", "light_disable",
                    *(f"mode_both_m{i}" for i in range(1, 5)), *(f"set_mode_both_m{i}" for i in range(1, 5))}
        standard.update(control for spec in self.motor_control_specs if spec.hold is not None for control in (spec.hold.up_control, spec.hold.down_control))
        commands = self.commands
        for key, command in commands.items():
            if key in standard or key == "mass_foot_lv":
                continue
            suffixes = command.suffixes or ("",)
            for suffix in suffixes:
                label = ("Massage level" if command.kind == "lv" else key.replace("_", " ").title()) + (" " + suffix if suffix else "")
                result.append(ControllerButtonSpec(
                    "suta_" + key + suffix, label, partial(_action, key=key, suffix=suffix),
                    translation_key="suta_preset" if command.text.startswith(("AT+MODE", "AT+SETMODE")) else "suta_action", translation_placeholders={"action": label},
                    hold=ControllerHoldSpec(key, release_button_key="suta_release") if command.kind in ("motion", "save") else None,
                    requires_confirmation=command.kind == "save" or key == "reset_on",
                    invalidates_position=command.kind in ("motion", "save") or command.text.startswith("AT+MODE"),
                    card=CARD_PRESETS if command.text.startswith(("AT+MODE", "AT+SETMODE")) else CARD_UTILITY,
                ))
        for action in BINARY.values():
            if self.family not in action.controllers or action.key == "temperature_setpoint":
                continue
            for prefix in action.prefixes:
                payload = prefix[6:]
                side = ("Left " if payload[0] == 1 else "Right ") if len(payload) == 2 else ""
                label = side + action.label.title()
                if action.key in ("heating_power", "heating_light"):
                    label += ": " + ("On" if payload[-1] else "Off")
                elif action.key in ("heating_timer", "automatic_adjustment_switch"):
                    label += ": " + str(payload[-1])
                result.append(ControllerButtonSpec(
                    "suta_" + action.key + "_" + prefix[6:].hex(), label,
                    partial(_binary_action, action=action.key, payload=prefix[6:]),
                    translation_key="suta_action", translation_placeholders={"action": label},
                ))
        if self.supports_stop_all:
            result.append(ControllerButtonSpec("suta_release", "Release", lambda c: c.stop_all(), release_only=True, translation_key="suta_release"))
        if self.family == "P1" and commands:
            result.append(ControllerButtonSpec("suta_snore_cycle", "Snore then flat", partial(_action, key="snore_cycle"), translation_key="suta_action", translation_placeholders={"action": "Snore then flat"}))
        if "mass_head_dt" in commands and "mass_foot_dt" in commands:
            result.append(ControllerButtonSpec("suta_massage_off", "Stop massage", partial(_action, key="massage_off"), translation_key="suta_action", translation_placeholders={"action": "Stop massage"}))
        return tuple(result)

    def controller_button_available(self, key: str) -> bool:
        if key.startswith("suta_mass_head_lv"):
            return any(self._cycles.get(zone, "00") != "00" for zone in ("mass_head_dt", "mass_foot_dt"))
        for action in BINARY.values():
            prefix = "suta_" + action.key + "_"
            if key.startswith(prefix) and action.key.startswith("adaptive_") and not action.key.endswith("_soft"):
                payload = bytes.fromhex(key.removeprefix(prefix))
                return self.observations.get(f"side_{payload[0]}_adaptive") == int(action.key.split("_")[1])
        return True

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.family != "TEMP":
            return ()
        return tuple(
            ControllerNumberSpec(f"suta_{side}_setpoint", f"suta_{side}_setpoint", state_key,
                                 22, 40, 1, partial(_setpoint, side=side), "°C")
            for side, state_key in ((1, LEFT_SETPOINT), (2, RIGHT_SETPOINT))
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (ControllerStateSensorSpec("suta", "suta", MODEL, "mdi:bed", attribute_keys=(OBSERVATIONS,)),)

    @property
    def commands(self) -> dict[str, Command]:
        if self.profile.key in ("short-name", "MattressControllerDrawerFragment"):
            return {}
        return {**SHARED, **self.profile.commands}

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if current is None or link is not None and current is not link or self._coordinator is not current.owner or self._coordinator.controller is not self or self.client is not current.client or not current.client.is_connected:
            raise ConnectionError("SUTA physical session changed")
        if self.command_side is not None:
            raise ValueError("SUTA controls require an explicit command's logical side")
        return current

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is not None:
            self._notify_callback = callback
            return
        self.on_disconnect()
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("SUTA is disconnected")
        if self.profile.key in ("short-name", "MattressControllerDrawerFragment"):
            raise ValueError("Supply the complete supported SUTA Bluetooth name; drawer controls are excluded")
        service = client.services.get_service(service_for_name(self.name))
        if service is None:
            raise ValueError("SUTA's name-selected GATT service is missing")
        write = None
        notifications = []
        for characteristic in service.characteristics:
            properties = set(characteristic.properties)
            if properties & {"write", "write-without-response"}:
                write = characteristic
            elif properties & {"notify", "indicate"}:
                notifications.append(characteristic)
        if write is None:
            raise ValueError("SUTA's selected service has no writable characteristic")
        link = self._link = Link(client, write, tuple(notifications), self._coordinator)

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self._live(link)
            except (ConnectionError, ValueError):
                return
            packet = bytes(data)
            self.forward_raw_notification(sender.uuid, packet)
            if self.family == "MOON":
                state = moon(packet)
            elif self.family == "TEMP":
                state = temp(packet)
            elif self.name.startswith("SUTA-RBHC"):
                state = {}
                if len(packet) >= 9:
                    import struct
                    back, extra1, foot, extra2 = struct.unpack(">hhhh", packet[1:9])
                    state = {"back": back, "foot": foot, "extra_1_raw": extra1, "extra_2_raw": extra2}
                    if self._notify_callback:
                        self._notify_callback("back", float(back))
                        self._notify_callback("legs", float(foot))
            else:
                state = self._receiver.feed(packet)
            self.observations.update(state)
            self._publish()

        for characteristic in link.notifications:
            try:
                await client.start_notify(characteristic, receive)
            except BleakError:
                _LOGGER.warning("SUTA notification subscription failed on %s", characteristic.uuid)
            self._live(link)
        # Bleak's BlueZ helper negotiates MTU. MTU success is not an app gate.
        acquire = getattr(getattr(client, "_backend", None), "_acquire_mtu", None)
        if callable(acquire):
            try:
                result = acquire()
                if inspect.isawaitable(result):
                    await result
            except (AssertionError, BleakError, OSError, TimeoutError):
                pass
        self._live(link)
        self._publish()

    async def async_after_connect(self, session: ControllerSession) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        if self.family == "TEMP":
            for action in ("temperature_controller_state", "firmware_version"):
                if await pause(0.3, cancel):
                    return
                await self._send(link, codec.from_prefix(BINARY[action].prefixes[0]), cancel)
        elif self.family == "MOON":
            if await pause(0.3, cancel):
                return
            # The child pages' three jobs have unspecified relative order.
            # HA needs one observation per field, without duplicate page jobs.
            for action in ("current_mattress_state", "mattress_temperature", "firmware_version"):
                await self._send(link, codec.from_prefix(BINARY[action].prefixes[0]), cancel)

    def on_disconnect(self) -> None:
        self._link = None
        self._receiver = TextReceiver()
        self.observations.clear()
        self._cycles.clear()
        self._gesture_released = False
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            for characteristic in link.notifications:
                await link.client.stop_notify(characteristic)

    def _publish(self) -> None:
        left, right = self.observations.get("side_1_setpoint"), self.observations.get("side_2_setpoint")
        self.forward_controller_state_updates(
            MODEL(self.name), OBSERVATIONS(dict(self.observations)),
            LEFT_SETPOINT(left if isinstance(left, int) else None),
            RIGHT_SETPOINT(right if isinstance(right, int) else None),
        )

    async def _send(self, link: Link, packet: bytes, cancel: asyncio.Event, *, deadline: float | None = None) -> float | None:
        """Settle a submitted write, with no retry FIFO or stale refresh backfill."""
        stamp: float | None = None

        async def write() -> None:
            nonlocal stamp
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set() or deadline is not None and monotonic() >= deadline:
                    return
                stamp = monotonic()
                # Normal BED h writes retain Android WRITE_TYPE_DEFAULT (2).
                self._record_command_trace(link.write.uuid, packet, response=True, characteristic=link.write)
                async with asyncio.timeout(WRITE_TIMEOUT):
                    await link.client.write_gatt_char(link.write, packet, response=True)

        task = asyncio.create_task(write())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
            except Exception:
                break
        if interrupted:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()
        return stamp

    async def _schedule(self, link: Link, command: Command, suffix: str, cancel: asyncio.Event) -> None:
        for index in range(command.count):
            delay = command.delay_ms if index == 0 else command.interval_ms
            if delay and await pause(delay / 1000, cancel):
                return
            await self._send(link, codec.text(command.text + suffix), cancel)

    async def _release(self, link: Link) -> None:
        command = self.profile.commands.get("both_stop")
        if command is None or self._link is not link:
            return

        async def release() -> None:
            await self._schedule(link, command, "", asyncio.Event())

        task = asyncio.create_task(release())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
            except Exception:
                break
        task.result()
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            self._cleanup_context = context
        if interrupted:
            raise asyncio.CancelledError

    def on_gesture_release(self) -> None:
        self._gesture_released = True

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._run_control(control, duration_ms)

    async def _run_control(self, control: str, duration_ms: int | None) -> None:
        """Run a finite gesture, or a dedicated save's complete bounded burst."""
        command = self.profile.commands[control]
        link, cancel = self._live(), self._coordinator.cancel_command
        self._gesture_released = False
        if command.kind == "motion":
            assert duration_ms is not None
            duration_ms = self.leased_hold_ms(duration_ms)
            try:
                stamp = await self._send(link, codec.text(command.text), cancel)
                if stamp is None:
                    return
                deadline = stamp + duration_ms / 1000
                for _ in range(999):
                    remaining = deadline - monotonic()
                    if remaining <= 0 or await pause(min(self.profile.refresh_ms / 1000, remaining), cancel):
                        break
                    if await self._send(link, codec.text(command.text), cancel, deadline=deadline) is None:
                        break
            finally:
                await self._release(link)
            return
        threshold = self.profile.threshold_s
        started = monotonic()
        programmed = False
        try:
            cancelled = await pause(threshold if duration_ms is None else min(duration_ms / 1000, threshold), cancel)
            if not cancelled and (duration_ms is None or duration_ms >= threshold * 1000) and monotonic() - started >= threshold:
                programmed = True
                if duration_ms is None:
                    # The finite packet count and per-write timeout bound this
                    # explicit save. Radio latency must not turn it into a tap.
                    await self._schedule(link, command, "", cancel)
                else:
                    deadline = started + duration_ms / 1000
                    for index in range(command.count):
                        delay = command.delay_ms if index == 0 else command.interval_ms
                        if delay and await pause(min(delay / 1000, max(0, deadline - monotonic())), cancel):
                            break
                        if monotonic() > deadline or index and monotonic() >= deadline:
                            break
                        await self._send(link, codec.text(command.text), cancel, deadline=deadline if delay else None)
            elif duration_ms is not None and (not cancelled or self._gesture_released):
                recall = self._recall_for(command)
                if recall is not None:
                    await self._schedule(link, recall, "", asyncio.Event() if cancelled else cancel)
        except asyncio.CancelledError:
            if duration_ms is not None and not programmed and self._gesture_released and self._link is link:
                recall = self._recall_for(command)
                if recall is not None:
                    await self._schedule(link, recall, "", asyncio.Event())
            raise
        finally:
            if self.profile.key == "MattressControllerES204Fragment":
                await self._release(link)

    def _recall_for(self, command: Command) -> Command | None:
        text = command.text.replace("AT+SETMODE=", "AT+MODE=", 1)
        return next((c for c in self.profile.commands.values() if c.text == text and c.kind != "save"), None)

    def validate_request(self, request: Request, *, live: bool = True) -> None:
        if request.action not in BINARY and (request.logical_side is not None or request.value is not None):
            raise ValueError("ASCII SUTA commands have no logical-side or numeric selector")
        if request.action in ("alarm_set", "alarm_disable", "alarm_delete", "snore_cycle", "massage_off") and request.suffix:
            raise ValueError("This compound SUTA action has no text suffix")
        if request.action in ("alarm_set", "alarm_disable", "alarm_delete"):
            if self.family != "P1" or "get_alarm" not in self.commands:
                raise ValueError("SUTA text alarms require a direct BED text layout")
            if not request.weekdays or len(set(request.weekdays)) != len(request.weekdays) or any(isinstance(day, bool) or day not in range(7) for day in request.weekdays):
                raise ValueError("Choose unique weekdays from Sunday 0 through Saturday 6")
            if len(request.time) != 4 or not request.time.isdecimal() or int(request.time[:2]) > 23 or int(request.time[2:]) > 59 or request.loop not in ("00", "01"):
                raise ValueError("Choose a four-digit HHmm and loop 00 or 01")
            return
        if request.action in ("snore_cycle", "massage_off"):
            required = () if request.action == "snore_cycle" else ("mass_head_dt", "mass_foot_dt")
            if not self.commands or self.family != "P1" or not all(key in self.profile.commands for key in required):
                raise ValueError("This SUTA layout does not expose that compound action")
            return
        if request.action in BINARY and self.family in BINARY[request.action].controllers:
            prefix = self._binary_prefix(request)
            if live and request.action.startswith("adaptive_") and not request.action.endswith("_soft"):
                current = self.observations.get(f"side_{request.logical_side}_adaptive")
                if current not in (4, 5, 6, 7, 14) or current != prefix[3]:
                    raise ValueError("Receive the current MOON adaptive mode before changing its stiffness")
            return
        command = self.commands.get(request.action)
        if command is None:
            raise ValueError("This SUTA layout does not expose that command")
        clock_suffix = command.kind == "clock" and len(request.suffix) == 10 and request.suffix.isdecimal()
        if command.suffixes and request.suffix not in command.suffixes or not command.suffixes and request.suffix and not clock_suffix:
            raise ValueError("Choose a proven SUTA command parameter")
        if request.logical_side is not None or request.value is not None:
            raise ValueError("ASCII SUTA commands have no logical-side or numeric selector")
        if live and command.kind == "lv":
            if not any(self._cycles.get(zone, "00") != "00" for zone in ("mass_head_dt", "mass_foot_dt")):
                raise ValueError("Enable that massage zone before choosing its level")

    def _binary_prefix(self, request: Request) -> bytes:
        action = BINARY[request.action]
        options = action.prefixes
        if request.suffix:
            raise ValueError("Binary SUTA controls do not accept text suffixes")
        side_owned = len(options[0][6:]) == 2
        if side_owned:
            if request.logical_side not in (1, 2):
                raise ValueError("Select logical side 1 or 2 for this SUTA control")
            options = tuple(p for p in options if p[6] == request.logical_side)
        elif request.logical_side is not None:
            raise ValueError("This SUTA control applies to the complete device")
        if request.value is not None:
            options = tuple(p for p in options if p[-1] == request.value)
        if len(options) != 1:
            raise ValueError("Choose a proven SUTA value for that action")
        return options[0]

    async def execute_request(self, request: Request) -> None:
        self.validate_request(request)
        link, cancel = self._live(), self._coordinator.cancel_command
        if request.action in ("alarm_set", "alarm_disable", "alarm_delete"):
            operation = {"alarm_set": "SA", "alarm_disable": "CA", "alarm_delete": "DA"}[request.action]
            for index, day in enumerate(request.weekdays):
                if index and await pause(1, cancel):
                    return
                text = f"AT+{operation}=0{day}{request.time}" + ("01" if operation == "DA" else request.loop)
                await self._schedule(link, Command(text, "tap", 3, 100, 100, (), "VM"), "", cancel)
            await self._schedule(link, self.commands["get_alarm"], "", cancel)
            return
        if request.action in BINARY and self.family in BINARY[request.action].controllers:
            await self._send(link, codec.from_prefix(self._binary_prefix(request)), cancel)
            return
        if request.action == "snore_cycle":
            # Direct BLE consequence of the excluded phone detector. This
            # admitted HA operation owns both halves and never reconnects later.
            await self._schedule(link, SNORE_EFFECT, "", cancel)
            if not await pause(60, cancel):
                await self._schedule(link, FLAT_EFFECT, "", cancel)
            return
        if request.action == "massage_off":
            started = monotonic()
            for offset, key, suffix in ((0.1, "both_stop", ""), (0.4, "mass_head_dt", "00"), (0.7, "mass_foot_dt", "00")):
                if await pause(max(0, started + offset - monotonic()), cancel):
                    return
                await self._send(link, codec.text(self.commands[key].text + suffix), cancel)
                if suffix:
                    self._cycles[key] = suffix
                    self._publish()
            return
        command = self.commands[request.action]
        if command.kind == "lv":
            zones = [key for key in ("mass_head_dt", "mass_foot_dt") if self._cycles.get(key, "00") != "00"]
            started = monotonic()
            for index, zone in enumerate(zones):
                if await pause(max(0, started + (0.1 if index == 0 else 0.3) - monotonic()), cancel):
                    return
                level = self.commands[zone.replace("_dt", "_lv")]
                await self._send(link, codec.text(level.text + request.suffix), cancel)
            return
        if command.kind == "motion":
            await self.hold_control(request.action, self._coordinator.motor_pulse_count * self.profile.refresh_ms)
        elif command.kind == "save":
            await self._run_control(request.action, None)
        else:
            suffix = (request.suffix or dt_util.now().strftime("%y%m%d%H%M")) if command.kind == "clock" else request.suffix
            await self._schedule(link, command, suffix, cancel)
            if command.kind in ("dt", "lv", "fan") and not cancel.is_set():
                self._cycles[request.action] = suffix
                self._publish()

    async def write_command(self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100, cancel_event: asyncio.Event | None = None) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if index and await pause(repeat_delay_ms / 1000, cancel):
                break
            await self._send(link, command, cancel)

    async def action(self, key: str, suffix: str = "") -> None:
        await self.execute_request(Request(key, suffix))

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent and preempted is self._cleanup_context:
                    preempted.cleanup_stop_sent = False
                    self._cleanup_context = None
                    return
        await self._release(self._live())

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = move_lumbar_stop = stop_all

    async def move_back_up(self) -> None:
        await self.action("ctrl_back_up")

    async def move_back_down(self) -> None:
        await self.action("ctrl_back_down")

    async def move_legs_up(self) -> None:
        await self.action("ctrl_foot_up")

    async def move_legs_down(self) -> None:
        await self.action("ctrl_foot_down")

    async def move_head_up(self) -> None:
        await self.action("ctrl_head_up")

    async def move_head_down(self) -> None:
        await self.action("ctrl_head_down")

    async def move_lumbar_up(self) -> None:
        await self.action("ctrl_tl_up")

    async def move_lumbar_down(self) -> None:
        await self.action("ctrl_tl_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def preset_flat(self) -> None:
        await self.action("mode_flat")

    async def preset_zero_g(self) -> None:
        await self.action("mode_zerog")

    async def preset_anti_snore(self) -> None:
        await self.action("both_snore")

    async def preset_tv(self) -> None:
        await self.action("both_tv")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"mode_both_m{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if not self.is_memory_slot_programmable(memory_num):
            raise ValueError("This SUTA layout does not program that memory")
        await self.action(f"set_mode_both_m{memory_num}")

    async def lights_on(self) -> None:
        await self.action("light_enable")

    async def lights_off(self) -> None:
        await self.action("light_disable")


async def _action(controller: BedController, key: str, suffix: str = "") -> None:
    if not isinstance(controller, SutaController):
        raise ValueError("SUTA controller required")
    await controller.action(key, suffix)


async def _binary_action(controller: BedController, action: str, payload: bytes) -> None:
    if not isinstance(controller, SutaController):
        raise ValueError("SUTA controller required")
    await controller.execute_request(Request(action, logical_side=payload[0] if len(payload) == 2 else None, value=payload[-1]))


async def _setpoint(controller: BedController, value: float, *, side: int) -> None:
    if not isinstance(controller, SutaController) or not float(value).is_integer():
        raise ValueError("Choose an integral SUTA temperature")
    await controller.execute_request(Request("temperature_setpoint", logical_side=side, value=int(value)))


async def pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def build_controller(ctx: BuildContext) -> SutaController:
    stored = ctx.data.get(CONF_BLE_DEVICE_NAME)
    name = stored if isinstance(stored, str) else ctx.advertisement_name or ctx.live_device_name
    return SutaController(ctx.coordinator, name=name)
