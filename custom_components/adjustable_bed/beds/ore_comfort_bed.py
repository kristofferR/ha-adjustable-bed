"""ORE comfort-bed app family controller (MaxCoil Una, Dynasty Bases).

Implements the accepted clean-room reports for com.ore.maxcoil 1.1.0 (5) and
com.ore.Dynasty 1.0.2 (3), formal cluster-013
(docs/apk-analysis/dispositions/row056-ore-maxcoil-dynasty.md). Both apps ship
the same ``com.ore.okincomfortbed`` code base; they differ only in launcher,
Back navigation and artwork, so they share one behavior here.

Every command is ``E5 FE 16`` + a big-endian 32-bit word + the complement of the
byte sum, written to the last FFE9 characteristic found in any service. The app
picks a 2-, 3- or 4-motor screen by hand; the configured motor count selects the
same screen. Holds write the key at 0 ms and then every 100 ms; every other
action, including the release zero word, sleeps 100 ms and is written once.

Hardware is unverified: the frames come from the artifact, not captures.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_MAXCOIL_UNA,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OreComfortBedApp:
    """One accepted app built on the shared code base."""

    name: str
    package: str
    version: str


# Sibling apps of this code base register their own entry here.
ORE_COMFORT_BED_APPS: Final[dict[str, OreComfortBedApp]] = {
    KEESON_VARIANT_MAXCOIL_UNA: OreComfortBedApp("MaxCoil Una", "com.ore.maxcoil", "1.1.0 (5)"),
    KEESON_VARIANT_DYNASTY_BASES: OreComfortBedApp("Dynasty Bases", "com.ore.Dynasty", "1.0.2 (3)"),
}

# Action words (MainActivity key codes).
STOP: Final = 0x00000000
BACK_UP: Final = 0x00000001
BACK_DOWN: Final = 0x00000002
FOOT_UP: Final = 0x00000004
FOOT_DOWN: Final = 0x00000008
# Combined back+foot on the 2-motor screen, head on 3-motor, waist on 4-motor.
THIRD_UP: Final = 0x00000010
THIRD_DOWN: Final = 0x00000020
LUMBAR_UP: Final = 0x00000040
LUMBAR_DOWN: Final = 0x00000080
RECALL_ZERO_G: Final = 0x01000001
RECALL_FLAT: Final = 0x01000002
RECALL_MEMORY: Final = {1: 0x01000008, 2: 0x01000009}
SAVE_ZERO_G: Final = 0x20000001
SAVE_FLAT: Final = 0x20000002
SAVE_MEMORY: Final = {1: 0x20000008, 2: 0x20000009}
LIGHT_ON: Final = 0x31000001
LIGHT_OFF: Final = 0x31000000
# Slider word = base + progress // 10 for progress 0..39, i.e. level 0..3.
MASSAGE_BASE: Final = {"wave": 0x10000020, "head": 0x10000010, "foot": 0x11000010}
MASSAGE_LEVEL_MAX: Final = 3
# Fresh install restores slider progress 10, i.e. level 1.
MASSAGE_DEFAULT_LEVEL: Final = 1
MASSAGE_TIMER: Final = {"10": 0x10000030, "20": 0x10000031, "30": 0x10000032}

# sendSingleMessage sleeps 100 ms before every single write; holds repeat 100 ms
# after each write.
SINGLE_SEND_DELAY_S: Final = 0.1
HOLD_INTERVAL_MS: Final = 100

STATE_LEVEL: Final = {zone: f"ore_comfort_massage_{zone}_level" for zone in MASSAGE_BASE}
STATE_TIMER: Final = "ore_comfort_massage_timer"

# (cover key, translation key, up word, down word) for each app screen.
_Axis = tuple[str, str, int, int]
_BACK: Final[_Axis] = ("back", "back", BACK_UP, BACK_DOWN)
_FOOT: Final[_Axis] = ("feet", "feet", FOOT_UP, FOOT_DOWN)
LAYOUTS: Final[dict[int, tuple[_Axis, ...]]] = {
    2: (_BACK, _FOOT, ("both", "both", THIRD_UP, THIRD_DOWN)),
    3: (_BACK, _FOOT, ("head", "head", THIRD_UP, THIRD_DOWN)),
    4: (
        _BACK,
        _FOOT,
        ("waist", "waist", THIRD_UP, THIRD_DOWN),
        ("lumbar", "lumbar", LUMBAR_UP, LUMBAR_DOWN),
    ),
}
_LAYOUT_NAMES: Final = {2: "bedding2 (2M)", 3: "bedding3 (3M)", 4: "bedding4 (4M)"}


def build_frame(word: int) -> bytes:
    """Encode an action word exactly as MainActivity.buildBluetoothPackage does."""
    body = bytes((0xE5, 0xFE, 0x16)) + (word & 0xFFFFFFFF).to_bytes(4, "big")
    return body + bytes(((~sum(body)) & 0xFF,))


class OreComfortBedController(BedController):
    """Controller for the MaxCoil Una / Dynasty Bases app protocol."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str) -> None:
        super().__init__(coordinator)
        self._app = ORE_COMFORT_BED_APPS[app]
        motor_count = coordinator.motor_count
        self._motor_count = motor_count if motor_count in LAYOUTS else 2
        self._axes = {key: (up, down) for key, _tk, up, down in LAYOUTS[self._motor_count]}
        self._levels = dict.fromkeys(MASSAGE_BASE, MASSAGE_DEFAULT_LEVEL)
        self._write_char: BleakGATTCharacteristic | None = None
        self._write_with_response = True

    # ------------------------------------------------------------ transport
    @property
    def control_characteristic_uuid(self) -> str:
        return KEESON_BASE_WRITE_CHAR_UUID

    def _resolve_write_characteristic(self) -> BleakGATTCharacteristic:
        """Return the app's write role, discovered once per connection.

        The app scans every service, ignores service UUIDs and properties, and
        keeps the last FFE9 and the last FFE4 it sees. Controls stay disabled
        unless both exist. It never sets a write type, so Android's default
        applies: write-without-response when the characteristic offers it.
        """
        if self._write_char is not None:
            return self._write_char
        client = self.client
        if client is None or not client.is_connected or client.services is None:
            raise ConnectionError("Not connected to bed")
        write: BleakGATTCharacteristic | None = None
        notify: BleakGATTCharacteristic | None = None
        for service in client.services:
            for char in service.characteristics:
                uuid = str(char.uuid).lower()
                if uuid == KEESON_BASE_WRITE_CHAR_UUID:
                    write = char
                elif uuid == KEESON_BASE_NOTIFY_CHAR_UUID:
                    notify = char
        if write is None or notify is None:
            self.log_discovered_services(level=logging.INFO)
            raise HomeAssistantError(
                f"{self._app.name}: the bed must expose both FFE9 and FFE4 characteristics"
            )
        props = {prop.lower() for prop in write.properties}
        self._write_with_response = "write-without-response" not in props
        self._write_char = write
        return write

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write to the resolved FFE9 instance with Android's default write type."""
        characteristic = self._resolve_write_characteristic()
        await self._write_gatt_with_retry(
            KEESON_BASE_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
            characteristic=characteristic,
        )

    async def _send_single(self, word: int) -> None:
        """sendSingleMessage: sleep 100 ms, then write the frame once."""
        await asyncio.sleep(SINGLE_SEND_DELAY_S)
        await self.write_command(build_frame(word))

    async def _send_release(self) -> None:
        """buttonUp: the zero word after 100 ms, never suppressed by cancellation."""
        try:
            await asyncio.sleep(SINGLE_SEND_DELAY_S)
        finally:
            await self.write_command(build_frame(STOP), cancel_event=asyncio.Event())

    async def _hold(self, word: int) -> None:
        """Repeat a held key every 100 ms, then release with the zero word."""
        repeat_count, repeat_delay_ms = self.motor_pulse_settings()
        try:
            await self.write_command(
                build_frame(word), repeat_count=repeat_count, repeat_delay_ms=repeat_delay_ms
            )
        finally:
            await self._send_release()

    async def _move_axis(self, key: str, up: bool) -> None:
        if key not in self._axes:
            raise NotImplementedError(
                f"The {_LAYOUT_NAMES[self._motor_count]} screen has no {key} control"
            )
        up_word, down_word = self._axes[key]
        await self._hold(up_word if up else down_word)

    def motor_pulse_settings(self) -> tuple[int, int]:
        """The configured hold length at the app's fixed 100 ms refresh."""
        return self._coordinator.motor_pulse_count, HOLD_INTERVAL_MS

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """The app enables FFE4 locally only: it writes no CCCD and parses nothing."""

    async def stop_notify(self) -> None:
        """No subscription exists to stop."""

    async def read_positions(self, motor_count: int = 2) -> None:
        """The app has no position feedback."""

    # ------------------------------------------------------------- motors
    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # One global key and a global zero release: any STOP ends every motion.
        return tuple(
            MotorControlSpec(
                key=key,
                translation_key=translation_key,
                open_fn=_axis_command(key, True),
                close_fn=_axis_command(key, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
            )
            for key, translation_key, _up, _down in LAYOUTS[self._motor_count]
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        # Covers from the other screens and from the generic Keeson profiles.
        return frozenset({"back", "feet", "both", "head", "waist", "lumbar", "tilt", "legs"})

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self._axes

    async def move_head_up(self) -> None:
        await self._move_axis("head", True)

    async def move_head_down(self) -> None:
        await self._move_axis("head", False)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move_axis("back", True)

    async def move_back_down(self) -> None:
        await self._move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("feet", True)

    async def move_legs_down(self) -> None:
        await self._move_axis("feet", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self._move_axis("feet", True)

    async def move_feet_down(self) -> None:
        await self._move_axis("feet", False)

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        """The zero word: movement release and the second tap of a running preset."""
        await self._send_release()

    # ------------------------------------------------------- presets/memory
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    async def preset_flat(self) -> None:
        await self._send_single(RECALL_FLAT)

    async def preset_zero_g(self) -> None:
        await self._send_single(RECALL_ZERO_G)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in RECALL_MEMORY:
            raise ValueError(f"{self._app.name} has memory slots 1 (A) and 2 (B) only")
        await self._send_single(RECALL_MEMORY[memory_num])

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in SAVE_MEMORY:
            raise ValueError(f"{self._app.name} has memory slots 1 (A) and 2 (B) only")
        await self._send_single(SAVE_MEMORY[memory_num])

    async def program_flat(self) -> None:
        """Long-press Flat: the app saves this preset like a memory slot."""
        await self._send_single(SAVE_FLAT)

    async def program_zero_g(self) -> None:
        """Long-press ZG: the app saves this preset like a memory slot."""
        await self._send_single(SAVE_ZERO_G)

    # -------------------------------------------------------------- light
    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    async def lights_on(self) -> None:
        await self._send_single(LIGHT_ON)

    async def lights_off(self) -> None:
        await self._send_single(LIGHT_OFF)

    # ------------------------------------------------------------ massage
    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        """Every app screen includes the massage page."""
        return True

    async def set_massage_level(self, zone: str, level: int) -> None:
        """A slider change: send the zone's level word and keep it for Start."""
        if zone not in MASSAGE_BASE or not 0 <= level <= MASSAGE_LEVEL_MAX:
            raise ValueError(f"Invalid massage level {zone}={level}")
        # Like the app's preference, the level is kept even if the write fails.
        self._levels[zone] = level
        self.forward_controller_state_updates({STATE_LEVEL[zone]: level})
        await self._send_single(MASSAGE_BASE[zone] + level)

    async def massage_start(self) -> None:
        """Start: the current wave, head and foot levels, in that order."""
        for zone in ("wave", "head", "foot"):
            await self._send_single(MASSAGE_BASE[zone] + self._levels[zone])

    async def massage_off(self) -> None:
        """Stop: head then foot level zero; the timer indicator resets locally."""
        await self._send_single(MASSAGE_BASE["head"])
        await self._send_single(MASSAGE_BASE["foot"])
        self.forward_controller_state_updates({STATE_TIMER: None})

    async def set_massage_timer_option(self, option: str) -> None:
        """One of the 10/20/30 minute words the timer button cycles through."""
        if option not in MASSAGE_TIMER:
            raise ValueError(f"Invalid massage timer {option}")
        await self._send_single(MASSAGE_TIMER[option])
        self.forward_controller_state_updates({STATE_TIMER: option})

    @property
    def persisted_app_state(self) -> Mapping[str, Any] | None:
        """The app keeps slider levels in its preferences across restarts."""
        return dict(self._levels)

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        if set(state) - set(MASSAGE_BASE):
            raise ValueError("Unknown massage preference")
        levels = {zone: state.get(zone, MASSAGE_DEFAULT_LEVEL) for zone in MASSAGE_BASE}
        if any(type(v) is not int or not 0 <= v <= MASSAGE_LEVEL_MAX for v in levels.values()):
            raise ValueError("Invalid massage level preference")
        self._levels = levels
        self.forward_controller_state_updates({STATE_LEVEL[z]: v for z, v in levels.items()})

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(
            ControllerNumberSpec(
                key=f"ore_comfort_massage_{zone}",
                translation_key=f"massage_{zone}_intensity",
                state_key=STATE_LEVEL[zone],
                native_min_value=0,
                native_max_value=MASSAGE_LEVEL_MAX,
                native_step=1,
                set_fn=_level_setter(zone),
            )
            for zone in ("head", "foot", "wave")
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                key=STATE_TIMER,
                translation_key=STATE_TIMER,
                state_key=STATE_TIMER,
                options=tuple(MASSAGE_TIMER),
                select_fn=lambda ctrl, option: cast(
                    OreComfortBedController, ctrl
                ).set_massage_timer_option(option),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def spec(
            key: str, name: str, icon: str, press: Callable[[OreComfortBedController], Any]
        ) -> ControllerButtonSpec:
            return ControllerButtonSpec(
                key,
                name,
                lambda ctrl: press(cast(OreComfortBedController, ctrl)),
                icon,
                translation_key=key,
            )

        return (
            spec(
                "ore_comfort_program_flat",
                "Save Flat",
                "mdi:content-save",
                lambda c: c.program_flat(),
            ),
            spec(
                "ore_comfort_program_zero_g",
                "Save Zero G",
                "mdi:content-save",
                lambda c: c.program_zero_g(),
            ),
            spec(
                "ore_comfort_massage_start",
                "Start massage",
                "mdi:play",
                lambda c: c.massage_start(),
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "app": self._app.name,
            "app_package": f"{self._app.package} {self._app.version}",
            "layout": _LAYOUT_NAMES[self._motor_count],
        }


def _axis_command(key: str, up: bool) -> MotorCommandCallable:
    async def command(ctrl: BedController) -> None:
        await cast(OreComfortBedController, ctrl)._move_axis(key, up)

    return command


def _level_setter(zone: str) -> Callable[[BedController, float], Awaitable[None]]:
    async def set_level(ctrl: BedController, value: float) -> None:
        await cast(OreComfortBedController, ctrl).set_massage_level(zone, int(value))

    return set_level
