"""SUTA's data-driven BED controller with one fenced physical BLE session."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_HIDDEN, CARD_MASSAGE
from ...codec import suta as codec
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
    note_frame_written,
)
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey, StateUpdate
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
from ...state_keys import massage_intensity
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .receive import TextReceiver, moon, temp

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext

# The shared command that sets the bed clock; the Set bed clock action owns it.
CLOCK_COMMAND: Final = "set_date"
LEFT_SETPOINT: Final = StateKey[int | None]("suta_left_setpoint")
RIGHT_SETPOINT: Final = StateKey[int | None]("suta_right_setpoint")
HEATING_ON: Final = StateKey[bool | None]("suta_heating_on")
HEATING_LIGHT_ON: Final = StateKey[bool | None]("suta_heating_light_on")
AUTOMATIC_ADJUSTMENT: Final = {
    side: StateKey[bool | None](f"suta_side_{side}_automatic_adjustment") for side in (1, 2)
}
_SIDE_NAMES: Final = {1: "Left", 2: "Right"}
# Each step command sets its zone's level (00 is off), so they are massage numbers.
_MASSAGE_STEPS: Final = {"head": "mass_head_dt", "foot": "mass_foot_dt", "all": "mass_head_lv"}
# MOON's per-side massage strength, 1-3; the bed reports it in its full state.
MASSAGE_STRENGTH: Final = {
    side: StateKey[int | None](f"suta_side_{side}_massage_strength") for side in (1, 2)
}
# Entity labels from the app's own button text. Keys absent here and from the
# standard buttons are reachable only through the SUTA action.
_TEXT_LABELS: Final = {
    "beep_enable": "Enable beep",
    "set_date": "Sync clock",
    "both_open_all": "Open all",
    "both_close_all": "Close all",
    "mode_open_bk": "Open back",
    "mode_close_bk": "Close back",
    "mode_open_hd": "Open head",
    "mode_close_hd": "Close head",
    "mode_open_ft": "Open foot",
    "mode_close_ft": "Close foot",
    "mode_m8": "M8",
    "mode_bed": "Bed",
    "mode_bed_flat": "Bed flat",
    "mode_chair": "Chair",
    "mode_sofa": "Sofa",
    "mode_sofa_bed": "Sofa bed",
    "mode_swing": "Swing",
    "mode_pilates": "Pilates",
    "mode_read": "Read",
    "mode_both_pull": "Pull",
    "mode_both_yoga": "Yoga",
    "both_set_tv": "Save TV position",
    "both_set_snore": "Save anti-snore position",
    "set_mode_zerog": "Save zero-gravity position",
    "mode_set_pilates": "Save Pilates position",
    "mode_set_read": "Save read position",
    "reset_on": "Reset",
    # B702 places BOTT under its storage icon, beside separate back+foot keys.
    "ctrl_bott_up": "Storage lift up",
    "ctrl_bott_down": "Storage lift down",
}
# Cycled steps: DT and fan 00 stops the zone, other values are app steps 1-3.
_STEP_ZONES: Final = {
    "mode_fans_top_dt": "Top fan",
    "mode_fans_middle_dt": "Middle fan",
    "mode_fans_bottom_dt": "Bottom fan",
    "mode_fans_all_on_dt": "All fans",
}
_BINARY_LABELS: Final = {
    "waist_massage": "waist massage",
    "back_massage": "back massage",
    "leg_massage": "leg massage",
    "surge_massage": "surge massage",
    "undulate_massage": "undulating massage",
}
_ADAPTIVE_MODES: Final = (4, 5, 6, 7, 14)
# Queries run after connect; switches replace the on/off binary pairs.
_BINARY_WITHOUT_BUTTON: Final = frozenset({
    "temperature_setpoint", "current_mattress_state", "mattress_temperature", "firmware_version",
    "temperature_controller_state", "heating_power", "heating_light", "automatic_adjustment_switch",
})
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
        self._clear_massage_levels()

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
    def reports_angles(self) -> bool:
        # RBHC notifications carry BACK and FOOT degrees; no other layout reports angles.
        return self.supports_position_feedback

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

    def _text_label(self, key: str, suffix: str) -> str | None:
        if key in _STEP_ZONES:
            steps = self.profile.commands.get(key, SHARED.get(key))
            index = steps.suffixes.index(suffix) if steps is not None else 0
            return f"{_STEP_ZONES[key]} off" if index == 0 else f"{_STEP_ZONES[key]} {index}"
        if key in ("ctrl_two_up", "ctrl_two_down"):
            # TWO drives back and foot together; alone it is the panel's only motion.
            direction = "up" if key.endswith("_up") else "down"
            both = all(f"ctrl_{axis}_up" in self.profile.commands for axis in ("back", "foot"))
            return f"{'Back and foot' if both else 'Whole bed'} {direction}"
        return _TEXT_LABELS.get(key)

    @staticmethod
    def _binary_label(key: str, payload: bytes) -> str:
        side = _SIDE_NAMES[payload[0]]
        if key in _BINARY_LABELS:
            return f"{side} {_BINARY_LABELS[key]}"
        if key.startswith("massage_timer_"):
            return f"{side} massage timer {key.removeprefix('massage_timer_')} min"
        if key.startswith("adaptive_"):
            _, mode, stiffness = key.split("_")
            return f"{side} adaptive mode {_ADAPTIVE_MODES.index(int(mode)) + 1}: {stiffness}"
        if key == "heating_timer":
            return f"{side} heating timer {payload[-1]} h"
        raise ValueError(f"No SUTA entity label for {key}")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result: list[ControllerButtonSpec | None] = []
        standard = {"mode_flat", "mode_zerog", "both_tv", "both_snore", "both_stop", "light_enable", "light_disable",
                    *(f"mode_both_m{i}" for i in range(1, 5)), *(f"set_mode_both_m{i}" for i in range(1, 5))}
        standard.update(control for spec in self.motor_control_specs if spec.hold is not None for control in (spec.hold.up_control, spec.hold.down_control))
        commands = self.commands
        for key, command in commands.items():
            if key in standard or key in _MASSAGE_STEPS.values():
                continue
            for suffix in command.suffixes or ("",):
                label = self._text_label(key, suffix)
                if label is None:
                    continue
                spec = catalog_button(
                    "suta_" + key + suffix, label, partial(_action, key=key, suffix=suffix),
                    kind=Kind.SAVE if command.text.startswith("AT+SETMODE")
                    else Kind.PRESET if command.text.startswith("AT+MODE")
                    else Kind.MOTOR if command.kind == "motion" else None,
                    # The card confirms a save and sends it whole; hold_control still runs saves.
                    hold=ControllerHoldSpec(key, release_button_key="suta_release") if command.kind == "motion" else None,
                    requires_confirmation=command.kind == "save" or key == "reset_on",
                    invalidates_position=command.kind in ("motion", "save") or command.text.startswith("AT+MODE"),
                )
                if spec is not None and key == "beep_enable":
                    # The app has no command that turns the beep off again.
                    spec = replace(spec, diagnostic=True)
                result.append(spec)
        for action in BINARY.values():
            if (
                self.family not in action.controllers
                or action.key in _BINARY_WITHOUT_BUTTON
                or action.key.startswith("massage_strength_")
            ):
                continue
            for prefix in action.prefixes:
                label = self._binary_label(action.key, prefix[6:])
                result.append(catalog_button(
                    "suta_" + action.key + "_" + prefix[6:].hex(), label,
                    partial(_binary_action, action=action.key, payload=prefix[6:]),
                ))
        if self.supports_stop_all:
            # The card presses this when a held gesture ends.
            result.append(ControllerButtonSpec("suta_release", "Release held control", lambda c: c.stop_all(), release_only=True, translation_key="suta_release", card=CARD_HIDDEN))
        if self.family == "P1" and {"both_snore", "mode_flat"} <= commands.keys():
            result.append(catalog_button("suta_snore_cycle", "Anti-snore then flat", partial(_action, key="snore_cycle"), kind=Kind.PRESET))
        if "mass_head_dt" in commands and "mass_foot_dt" in commands:
            result.append(catalog_button("suta_massage_off", "Stop massage", partial(_action, key="massage_off")))
        return unique_buttons(result)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if self.family == "TEMP":
            return (
                ControllerSwitchSpec("suta_heating", "suta_heating", partial(_binary_switch, action="heating_power"),
                                     state_key=HEATING_ON, icon="mdi:radiator"),
                ControllerSwitchSpec("suta_heating_light", "suta_heating_light", partial(_binary_switch, action="heating_light"),
                                     state_key=HEATING_LIGHT_ON, icon="mdi:lightbulb"),
            )
        if self.family == "MOON":
            return tuple(
                ControllerSwitchSpec(f"suta_automatic_adjustment_{side}", f"suta_{_SIDE_NAMES[side].lower()}_automatic_adjustment",
                                     partial(_binary_switch, action="automatic_adjustment_switch", side=side),
                                     state_key=AUTOMATIC_ADJUSTMENT[side], icon="mdi:tune-variant")
                for side in (1, 2)
            )
        if "set_lock_on" in self.commands and "set_lock_off" in self.commands:
            # The bed reports no lock state, so the switch shows the last command.
            return (ControllerSwitchSpec("suta_lock", "suta_lock", _lock, icon="mdi:lock"),)
        return ()

    def controller_button_available(self, key: str) -> bool:
        for action in BINARY.values():
            prefix = "suta_" + action.key + "_"
            if key.startswith(prefix) and action.key.startswith("adaptive_") and not action.key.endswith("_soft"):
                payload = bytes.fromhex(key.removeprefix(prefix))
                return self.observations.get(f"side_{payload[0]}_adaptive") == int(action.key.split("_")[1])
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        return [zone for zone, key in _MASSAGE_STEPS.items() if key in self.commands]

    @property
    def supports_massage_intensity_control(self) -> bool:
        return bool(self.massage_intensity_zones)

    @property
    def massage_intensity_max(self) -> int:
        return 3

    @property
    def auto_enable_massage(self) -> bool:
        # The app always shows its massage levels.
        return super().auto_enable_massage or bool(
            self.massage_intensity_zones or self._strength_sides
        )

    def massage_intensity_available(self, zone: str) -> bool:
        # A level is sent to the zones running, so it needs one running.
        return zone != "all" or any(
            self._cycles.get(step, "00") != "00" for step in ("mass_head_dt", "mass_foot_dt")
        )

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        key = _MASSAGE_STEPS.get(zone)
        command = self.commands.get(key) if key is not None else None
        if key is None or command is None or not 0 <= level < len(command.suffixes):
            raise ValueError("This SUTA layout has no such massage level")
        # The command shows the level it sent.
        await self.action(key, command.suffixes[level])

    @property
    def _strength_sides(self) -> tuple[int, ...]:
        """The sides whose massage strength the layout sets, 1-3 with no off."""
        sides: set[int] = set()
        for action in BINARY.values():
            if self.family in action.controllers and action.key.startswith("massage_strength_"):
                sides.update(prefix[6] for prefix in action.prefixes)
        return tuple(sorted(sides))

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.family != "TEMP":
            return tuple(
                ControllerNumberSpec(
                    f"suta_{_SIDE_NAMES[side].lower()}_massage_strength",
                    f"massage_{_SIDE_NAMES[side].lower()}_intensity",
                    MASSAGE_STRENGTH[side],
                    1,
                    3,
                    1,
                    partial(_massage_strength, side=side),
                    card=CARD_MASSAGE,
                )
                for side in self._strength_sides
            )
        return tuple(
            ControllerNumberSpec(f"suta_{side}_setpoint", f"suta_{side}_setpoint", state_key,
                                 22, 40, 1, partial(_setpoint, side=side), "°C")
            for side, state_key in ((1, LEFT_SETPOINT), (2, RIGHT_SETPOINT))
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        # Decoded notifications stay out of entities; diagnostics and the support bundle keep them.
        return {"device_name": self.name, "layout": self.profile.key, "observations": dict(self.observations)}

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
        self._clear_massage_levels()

    def _clear_massage_levels(self) -> None:
        """The bed reports no massage level: unknown until one is sent."""
        self.forward_controller_state_updates(
            *(massage_intensity(zone)(None) for zone in self.massage_intensity_zones)
        )

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            for characteristic in link.notifications:
                await link.client.stop_notify(characteristic)

    def _publish(self) -> None:
        left, right = self.observations.get("side_1_setpoint"), self.observations.get("side_2_setpoint")
        power, light = self.observations.get("power"), self.observations.get("light")
        automatic = {side: self.observations.get(f"side_{side}_automatic_checked") for side in (1, 2)}
        self.forward_controller_state_updates(
            LEFT_SETPOINT(left if isinstance(left, int) else None),
            RIGHT_SETPOINT(right if isinstance(right, int) else None),
            HEATING_ON(power == 1 if power in (0, 1) else None),
            HEATING_LIGHT_ON(light == 1 if light in (0, 1) else None),
            *(AUTOMATIC_ADJUSTMENT[side](value if isinstance(value, bool) else None) for side, value in automatic.items()),
            *(
                MASSAGE_STRENGTH[side](value if value in (1, 2, 3) else None)
                for side in (1, 2)
                for value in (self.observations.get(f"side_{side}_strength"),)
            ),
        )

    async def _send(self, link: Link, packet: bytes, cancel: asyncio.Event, *, deadline: float | None = None) -> float | None:
        """Settle a submitted write, with no retry FIFO or stale refresh backfill."""
        stamp: float | None = None

        async def write() -> None:
            nonlocal stamp
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set() or deadline is not None and monotonic() >= deadline:
                    note_frame_skipped()
                    return
                stamp = monotonic()
                # Normal BED h writes retain Android WRITE_TYPE_DEFAULT (2).
                self._record_command_trace(link.write.uuid, packet, response=True, characteristic=link.write)
                async with asyncio.timeout(WRITE_TIMEOUT):
                    await link.client.write_gatt_char(link.write, packet, response=True)
                    note_frame_written(cancel)

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
        if request.action in ("snore_cycle", "massage_off") and request.suffix:
            raise ValueError("This compound SUTA action has no text suffix")
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
        if request.action in BINARY and self.family in BINARY[request.action].controllers:
            side = request.logical_side
            strength = request.action.startswith("massage_strength_") and side in (1, 2)

            def show(delivery: Delivery) -> None:
                # A strength shows as far as its write reached this link's bed, also when
                # cancelled after it, until the bed's next full-state report replaces it.
                if not strength or self._link is not link or delivery is Delivery.NONE:
                    return
                self.observations[f"side_{side}_strength"] = (
                    request.value if delivery is Delivery.SENT else None
                )
                self._publish()

            with delivered(show):
                sent = await self._send(link, codec.from_prefix(self._binary_prefix(request)), cancel)
            if sent is not None and request.action == "automatic_adjustment_switch" and self._link is link:
                # The bed does not echo this write; like the app's checkbox, show the sent value
                # until the next full-state report replaces it.
                self.observations[f"side_{request.logical_side}_automatic_checked"] = request.value == 1
                self._publish()
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
                # The zone's level shows as off, as far as the stop reached the bed.
                with self.sent_state(*self._massage_step(key, suffix)):
                    await self._send(link, codec.text(self.commands[key].text + suffix), cancel)
                    if suffix:
                        self._cycles[key] = suffix
            return
        command = self.commands[request.action]
        if command.kind == "lv":
            zones = [key for key in ("mass_head_dt", "mass_foot_dt") if self._cycles.get(key, "00") != "00"]
            started = monotonic()
            with self.sent_state(*self._massage_step(request.action, request.suffix)):
                for index, zone in enumerate(zones):
                    if await pause(max(0, started + (0.1 if index == 0 else 0.3) - monotonic()), cancel):
                        # The zones not reached keep their old level: only partly sent.
                        note_frame_skipped()
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
            # A massage step shows as its zone's level, as far as it reached the bed.
            step = self._massage_step(request.action, suffix)
            with self.sent_state(*step):
                await self._schedule(link, command, suffix, cancel)
                stepped = command.kind in ("dt", "lv", "fan") and not cancel.is_set()
                if stepped:
                    self._cycles[request.action] = suffix
            if stepped and not step:
                self._publish()

    def _massage_step(self, key: str, suffix: str) -> tuple[StateUpdate, ...]:
        """A massage step command's level, as its zone's massage level."""
        zone = next((zone for zone, step in _MASSAGE_STEPS.items() if step == key), None)
        if zone is None:
            return ()
        return (massage_intensity(zone)(self.commands[key].suffixes.index(suffix)),)

    @property
    def supports_clock_sync(self) -> bool:
        return CLOCK_COMMAND in self.commands

    async def sync_clock(self) -> None:
        # An empty suffix makes the clock command send Home Assistant's local time.
        await self.execute_request(Request(CLOCK_COMMAND))

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        # Text layouts keep one alarm per weekday and time; the app lists them with get_alarm.
        if self.family != "P1" or "get_alarm" not in self.commands:
            return None
        return AlarmCapability(weekdays=True, time_to_turn_off=True)

    def _alarm_texts(self, alarm: AlarmRequest) -> tuple[str, ...]:
        """One frame per weekday, Sunday 0. The app's Loop switch repeats the days weekly."""
        if alarm.weekdays:
            days, loop = sorted((day + 1) % 7 for day in alarm.weekdays), "01"
        else:
            days, loop = [(alarm.occurrence().weekday() + 1) % 7], "00"
        # The app turns an alarm off (CA) with the same day, time and loop it set (SA).
        operation = "SA" if alarm.enabled else "CA"
        return tuple(f"AT+{operation}=0{day}{alarm.hour:02d}{alarm.minute:02d}{loop}" for day in days)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        for index, text in enumerate(self._alarm_texts(alarm)):
            if index and await pause(1, cancel):
                return
            await self._schedule(link, Command(text, "tap", 3, 100, 100, (), "VM"), "", cancel)
        await self._schedule(link, self.commands["get_alarm"], "", cancel)

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


async def _massage_strength(controller: BedController, value: float, *, side: int) -> None:
    if not isinstance(controller, SutaController):
        raise ValueError("SUTA controller required")
    level = int(value)
    await controller.execute_request(
        Request(f"massage_strength_{level}", logical_side=side, value=level)
    )


async def _binary_switch(controller: BedController, enabled: bool, *, action: str, side: int | None = None) -> None:
    if not isinstance(controller, SutaController):
        raise ValueError("SUTA controller required")
    await controller.execute_request(Request(action, logical_side=side, value=int(enabled)))


async def _lock(controller: BedController, enabled: bool) -> None:
    await _action(controller, "set_lock_on" if enabled else "set_lock_off")


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
