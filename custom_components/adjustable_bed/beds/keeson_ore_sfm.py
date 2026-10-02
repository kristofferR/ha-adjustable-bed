"""ORE SFM app profiles: Bedsense Bases and INNOVA.

Accepted clean-room audits (APK Protocol Audit cluster-015, row059):

- ``com.ore.sfmc2bedsence`` 1.1 (3), "Bedsense Bases"
- ``com.ore.sfm`` 2.0 (3), "INNOVA"

Both apps write the eight-byte frame ``E5 FE 16 k0 k1 k2 k3 ~sum`` to FFE9 and
enable FFE4 notifications locally, but they differ in byte order, command keys,
preset programming, massage model, rename support and notification parsing, so
every behavior is gated per app. Neither app identifies the bed from its
advertisement, so both profiles are explicit selections only. The user picks
the app's 2M/3M/4M layout with the motor count.

Shared app timing: held controls write at 0 ms and then every 100 ms; release
cancels the refresh and, 100 ms later, writes the zero key. Every single-shot
write is preceded by a 100 ms sleep in ``sendSingleMessage``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_INNOVA,
)
from .base import (
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .keeson import KeesonCommands, KeesonController

_LOGGER = logging.getLogger(__name__)

# sendSingleMessage sleeps 100 ms on the caller before each single write,
# including the zero key that buttonUp sends after cancelling a hold.
SINGLE_SEND_DELAY_S: Final = 0.1
ZERO_KEY: Final = 0x00000000

# Bedsense Bases keys (big-endian in the frame).
BEDSENSE_PRESET_ZERO_G: Final = 0x01000001
BEDSENSE_PRESET_FLAT: Final = 0x01000002
BEDSENSE_PRESET_MEMORY_A: Final = 0x01000008
BEDSENSE_PRESET_MEMORY_B: Final = 0x01000009
# Long-click programs the same low byte with high byte 0x20 instead of 0x01.
BEDSENSE_SAVE_ZERO_G: Final = 0x20000001
BEDSENSE_SAVE_FLAT: Final = 0x20000002
BEDSENSE_SAVE_MEMORY_A: Final = 0x20000008
BEDSENSE_SAVE_MEMORY_B: Final = 0x20000009
BEDSENSE_MASSAGE_WAVE_BASE: Final = 0x10000020
BEDSENSE_MASSAGE_HEAD_BASE: Final = 0x10000010
BEDSENSE_MASSAGE_FOOT_BASE: Final = 0x11000010
BEDSENSE_MASSAGE_LEVEL_MAX: Final = 3  # Slider 0..39, sent as floor(progress / 10).
BEDSENSE_MASSAGE_DEFAULT_LEVEL: Final = 1  # Slider default progress 10.
BEDSENSE_MASSAGE_TIMERS: Final = {10: 0x10000030, 20: 0x10000031, 30: 0x10000032}
BEDSENSE_LIGHT_ON: Final = 0x31000001
BEDSENSE_LIGHT_OFF: Final = 0x31000000
BEDSENSE_UNION_UP: Final = 0x00000010  # 2M "combined" key; 3M head; 4M waist.
BEDSENSE_UNION_DOWN: Final = 0x00000020

# INNOVA keys (little-endian in the frame).
INNOVA_UNION_UP: Final = 0x00000005
INNOVA_UNION_DOWN: Final = 0x0000000A
INNOVA_MASSAGE_LEVEL: Final = 0x00000100
INNOVA_MASSAGE_TIMER: Final = 0x00000200
INNOVA_RENAME_MAX_UNITS: Final = 14
INNOVA_RENAME_FRAME_LENGTH: Final = 18

STATE_INNOVA_LIGHT: Final = "innova_light"
STATE_INNOVA_MASSAGE_TIMER: Final = "innova_massage_timer"
_INNOVA_TIMER_MINUTES: Final = {-1: 0, 1: 10, 2: 20, 3: 30}

# App actions without a generic entity share this button namespace.
ACTION_NAMESPACE: Final = "ore_sfm_"


def ore_sfm_frame(key: int, *, big_endian: bool) -> bytes:
    """Build ``E5 FE 16 || low32(key) || ~sum`` in the app's byte order."""
    body = bytes((0xE5, 0xFE, 0x16)) + (key & 0xFFFFFFFF).to_bytes(
        4, "big" if big_endian else "little"
    )
    return body + bytes(((~sum(body)) & 0xFF,))


def _java_trim(name: str) -> str:
    """Mirror ``String.trim()``: strip leading/trailing chars <= U+0020."""
    start, end = 0, len(name)
    while start < end and ord(name[start]) <= 0x20:
        start += 1
    while end > start and ord(name[end - 1]) <= 0x20:
        end -= 1
    return name[start:end]


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def validate_innova_name(name: str) -> str:
    """Apply the Options editor checks: trimmed, non-empty, at most 14 UTF-16 units."""
    trimmed = _java_trim(name)
    if not trimmed:
        raise ValueError("The INNOVA app requires a non-empty name")
    if _utf16_units(trimmed) > INNOVA_RENAME_MAX_UNITS:
        raise ValueError("The INNOVA app limits names to 14 characters")
    return trimmed


def innova_rename_frame(name: str) -> bytes:
    """Build the app's 18-byte ``EF 02`` rename frame.

    The app copies ``String.length()`` bytes (UTF-16 units) from
    ``getBytes()`` (UTF-8 on Android), so multibyte names are truncated
    exactly as the app truncates them. Byte 16 stays zero; byte 17 is the
    complemented sum of bytes 0..16.
    """
    trimmed = validate_innova_name(name)
    frame = bytearray(INNOVA_RENAME_FRAME_LENGTH)
    frame[0:2] = b"\xef\x02"
    raw = trimmed.encode("utf-8")[: _utf16_units(trimmed)]
    frame[2 : 2 + len(raw)] = raw
    frame[17] = (~sum(frame[:17])) & 0xFF
    return bytes(frame)


def parse_innova_status(data: bytes) -> dict[str, Any] | None:
    """Decode an INNOVA notification exactly as ``GattUpdateReceiver`` does.

    Only 16- and 19-byte values are read, with no header or checksum. The flag
    byte is 13 (or 14); ``(flags >> 5) & 1`` suppresses the update and
    ``(flags >> 6) & 1`` is the lamp icon. The signed timer byte is 14 (or 15):
    -1 clears the timer icon, 1/2/3 show 10/20/30 minutes and any other value
    leaves the indicator unchanged. Returns ``None`` for ignored payloads.
    """
    if len(data) == 16:
        flags, timer = data[13], data[14]
    elif len(data) == 19:
        flags, timer = data[14], data[15]
    else:
        return None
    if (flags >> 5) & 1:
        return None
    state: dict[str, Any] = {STATE_INNOVA_LIGHT: bool((flags >> 6) & 1)}
    signed = timer - 256 if timer > 127 else timer
    if signed in _INNOVA_TIMER_MINUTES:
        state[STATE_INNOVA_MASSAGE_TIMER] = _INNOVA_TIMER_MINUTES[signed]
    return state


def _action(method: str) -> MotorCommandCallable:
    async def invoke(controller: Any) -> None:
        await getattr(controller, method)()

    return invoke


class OreSfmKeesonController(KeesonController):
    """Explicit Bedsense Bases and INNOVA app profiles."""

    def __init__(self, coordinator: Any, variant: str) -> None:
        if variant not in (KEESON_VARIANT_BEDSENSE_BASES, KEESON_VARIANT_INNOVA):
            raise ValueError(f"Unsupported ORE SFM app profile: {variant}")
        # Both apps select FFE9 by UUID across every service; no fallback roles.
        super().__init__(coordinator, variant=variant, char_uuid=KEESON_BASE_WRITE_CHAR_UUID)
        self._is_bedsense = variant == KEESON_VARIANT_BEDSENSE_BASES
        self._is_innova = variant == KEESON_VARIANT_INNOVA
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID
        # Bedsense app-local state (sliders, timer label, isLightOn).
        self._massage_levels = dict.fromkeys(
            ("head", "foot", "wave"), BEDSENSE_MASSAGE_DEFAULT_LEVEL
        )
        self._timer_minutes: int | None = None

    # ------------------------------------------------------------------ layout
    @property
    def _layout(self) -> int:
        """The app's bedding2/3/4 selector, chosen with the motor count."""
        return min(4, max(2, self._coordinator.motor_count))

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        return {"head": "keeson_back", "feet": "keeson_legs", "tilt": "keeson_head"}

    @property
    def has_tilt_support(self) -> bool:
        return self._layout == 4 or (self._is_bedsense and self._layout == 3)

    @property
    def has_lumbar_support(self) -> bool:
        return self._layout == 4 or (self._is_innova and self._layout == 3)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = [
            MotorControlSpec(
                key="head",
                translation_key="keeson_back",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
            ),
            MotorControlSpec(
                key="feet",
                translation_key="keeson_legs",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                max_angle=45,
            ),
        ]
        tilt_up = lambda ctrl: ctrl.move_tilt_up()  # noqa: E731
        tilt_down = lambda ctrl: ctrl.move_tilt_down()  # noqa: E731
        tilt_stop = lambda ctrl: ctrl.move_tilt_stop()  # noqa: E731
        lumbar = MotorControlSpec(
            key="lumbar",
            translation_key="lumbar",
            open_fn=lambda ctrl: ctrl.move_lumbar_up(),
            close_fn=lambda ctrl: ctrl.move_lumbar_down(),
            stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
            max_angle=30,
        )
        if self._layout == 2:
            specs.append(
                MotorControlSpec(
                    key="back_legs",
                    translation_key="back_legs",
                    open_fn=_action("move_union_up"),
                    close_fn=_action("move_union_down"),
                    stop_fn=lambda ctrl: ctrl.stop_all(),
                )
            )
        elif self._layout == 3 and self._is_bedsense:
            # Bedsense 3M labels 0x10/0x20 "head".
            specs.append(
                MotorControlSpec(
                    key="tilt",
                    translation_key="keeson_head",
                    open_fn=tilt_up,
                    close_fn=tilt_down,
                    stop_fn=tilt_stop,
                    max_angle=45,
                )
            )
        elif self._layout == 3:
            # INNOVA 3M third actuator: bedLumbar IDs, 0x40/0x80.
            specs.append(lumbar)
        else:
            # 4M: both apps' bedWaist 0x10/0x20 plus bedLumbar 0x40/0x80.
            specs.append(
                MotorControlSpec(
                    key="waist",
                    translation_key="waist",
                    open_fn=tilt_up,
                    close_fn=tilt_down,
                    stop_fn=tilt_stop,
                    max_angle=45,
                )
            )
            specs.append(lumbar)
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"tilt", "lumbar", "waist", "back_legs"})

    # ------------------------------------------------------------- transport
    def _build_command(self, command_value: int) -> bytes:
        return ore_sfm_frame(command_value, big_endian=self._is_bedsense)

    def _refresh_write_mode(self) -> None:
        """Mirror Android: the app never sets a write type on the characteristic."""
        if self._write_mode_initialized:
            return
        client = self.client
        if client is None or client.services is None:
            return
        for service in client.services:
            for char in service.characteristics:
                if str(char.uuid).lower() == self._char_uuid:
                    props = {prop.lower() for prop in getattr(char, "properties", [])}
                    self._write_with_response = "write-without-response" not in props
        self._write_mode_initialized = True

    def _require_roles(self) -> None:
        """The app refuses to control the bed unless both FFE9 and FFE4 exist."""
        client = self.client
        if client is None or client.services is None:
            return
        uuids = {
            str(char.uuid).lower()
            for service in client.services
            for char in service.characteristics
        }
        # An empty enumeration means services are not resolved yet, not absent.
        if uuids and not {KEESON_BASE_WRITE_CHAR_UUID, KEESON_BASE_NOTIFY_CHAR_UUID} <= uuids:
            raise BleakError(
                "This app profile requires both the FFE9 write and FFE4 notify characteristics"
            )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._require_roles()
        await super().write_command(command, repeat_count, repeat_delay_ms, cancel_event)

    async def _send_singles(self, *keys: int, cancel_event: asyncio.Event | None = None) -> None:
        """``sendSingleMessage``: sleep 100 ms, then write once, per key."""
        for key in keys:
            await asyncio.sleep(SINGLE_SEND_DELAY_S)
            await self.write_command(self._build_command(key), cancel_event=cancel_event)

    async def _write_single_shot(self, command: bytes) -> None:
        await asyncio.sleep(SINGLE_SEND_DELAY_S)
        await self.write_command(command)

    async def _release_motion(self, *, delay: bool = True) -> None:
        """``buttonUp``: after the refresh ends, send the zero key 100 ms later."""
        await self._send_singles(ZERO_KEY, cancel_event=asyncio.Event())

    async def _hold(self, key: int) -> None:
        """Stream a held key at the app cadence, then release with the zero key."""
        repeat_count, repeat_delay_ms = self.motor_pulse_settings()
        try:
            await self.write_command(
                self._build_command(key),
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
            )
        finally:
            self._motor_state = {}
            await self._release_motion()

    async def move_union_up(self) -> None:
        """2M combined back and legs up (Bedsense 0x10, INNOVA 0x05)."""
        await self._hold(BEDSENSE_UNION_UP if self._is_bedsense else INNOVA_UNION_UP)

    async def move_union_down(self) -> None:
        """2M combined back and legs down (Bedsense 0x20, INNOVA 0x0A)."""
        await self._hold(BEDSENSE_UNION_DOWN if self._is_bedsense else INNOVA_UNION_DOWN)

    @property
    def supports_stop_all(self) -> bool:
        """Both apps send the zero key as release; Bedsense also on a repeated preset tap."""
        return True

    # ---------------------------------------------------------------- presets
    @property
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 2  # Memory A and Memory B.

    @property
    def supports_memory_programming(self) -> bool:
        return self._is_bedsense

    async def preset_flat(self) -> None:
        if self._is_bedsense:
            await self._send_singles(BEDSENSE_PRESET_FLAT)
        else:
            await self._send_singles(KeesonCommands.PRESET_FLAT)

    async def preset_zero_g(self) -> None:
        if self._is_bedsense:
            await self._send_singles(BEDSENSE_PRESET_ZERO_G)
        else:
            await self._send_singles(KeesonCommands.PRESET_ZERO_G)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("This app has Memory A (1) and Memory B (2) only")
        if self._is_bedsense:
            await self._send_singles(
                BEDSENSE_PRESET_MEMORY_A if memory_num == 1 else BEDSENSE_PRESET_MEMORY_B
            )
            return
        # INNOVA streams Memory A/B while the button is held, then releases.
        await self._hold(
            KeesonCommands.PRESET_MEMORY_1 if memory_num == 1 else KeesonCommands.PRESET_MEMORY_2
        )

    async def program_memory(self, memory_num: int) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has no memory programming command")
        if memory_num not in (1, 2):
            raise ValueError("This app has Memory A (1) and Memory B (2) only")
        await self._send_singles(
            BEDSENSE_SAVE_MEMORY_A if memory_num == 1 else BEDSENSE_SAVE_MEMORY_B
        )

    async def program_zero_g(self) -> None:
        """Bedsense long-click on Zero G."""
        await self._send_singles(BEDSENSE_SAVE_ZERO_G)

    async def program_flat(self) -> None:
        """Bedsense long-click on Flat."""
        await self._send_singles(BEDSENSE_SAVE_FLAT)

    async def preset_lounge(self) -> None:
        raise NotImplementedError("This app has no lounge preset")

    async def preset_tv(self) -> None:
        raise NotImplementedError("This app has no TV preset")

    async def preset_anti_snore(self) -> None:
        raise NotImplementedError("This app has no anti-snore preset")

    # ----------------------------------------------------------------- lights
    @property
    def supports_discrete_light_control(self) -> bool:
        return self._is_bedsense

    async def lights_on(self) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has only a light toggle")
        await self._send_singles(BEDSENSE_LIGHT_ON)
        self._led_on = True

    async def lights_off(self) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has only a light toggle")
        await self._send_singles(BEDSENSE_LIGHT_OFF)
        self._led_on = False

    async def lights_toggle(self) -> None:
        if self._is_bedsense:
            # The app toggles its local isLightOn and sends the matching frame.
            await (self.lights_off() if self._led_on else self.lights_on())
        else:
            await self._send_singles(KeesonCommands.TOGGLE_LIGHTS)

    # ---------------------------------------------------------------- massage
    @property
    def auto_enable_massage(self) -> bool:
        return True  # Every layout shows the massage page.

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return self._is_bedsense

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self._is_innova

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self._is_innova

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self._is_innova

    @property
    def massage_mode_step_is_timer(self) -> bool:
        return True

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return False

    @property
    def supports_massage_intensity_preset_control(self) -> bool:
        return False

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self._is_bedsense

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head", "foot", "wave"] if self._is_bedsense else []

    @property
    def massage_intensity_max(self) -> int:
        return BEDSENSE_MASSAGE_LEVEL_MAX

    @property
    def supports_massage_timer(self) -> bool:
        return self._is_bedsense

    @property
    def massage_timer_options(self) -> list[int]:
        return list(BEDSENSE_MASSAGE_TIMERS) if self._is_bedsense else []

    def _massage_key(self, zone: str, level: int) -> int:
        base = {
            "head": BEDSENSE_MASSAGE_HEAD_BASE,
            "foot": BEDSENSE_MASSAGE_FOOT_BASE,
            "wave": BEDSENSE_MASSAGE_WAVE_BASE,
        }[zone]
        return base + level

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has only relative massage controls")
        if zone not in self._massage_levels:
            raise ValueError(f"Unsupported massage zone: {zone}")
        if not 0 <= level <= BEDSENSE_MASSAGE_LEVEL_MAX:
            raise ValueError("Massage level must be between 0 and 3")
        await self._send_singles(self._massage_key(zone, level))
        self._massage_levels[zone] = level

    async def massage_start(self) -> None:
        """Bedsense start: wave, head, then foot at the current levels."""
        await self._send_singles(
            *(
                self._massage_key(zone, self._massage_levels[zone])
                for zone in ("wave", "head", "foot")
            )
        )

    async def massage_off(self) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has no massage off command")
        await self._send_singles(BEDSENSE_MASSAGE_HEAD_BASE, BEDSENSE_MASSAGE_FOOT_BASE)
        self._timer_minutes = None  # The app resets its timer label.

    async def set_massage_timer(self, minutes: int) -> None:
        if not self._is_bedsense:
            raise NotImplementedError("The INNOVA app has only a timer step button")
        if minutes not in BEDSENSE_MASSAGE_TIMERS:
            raise ValueError(
                "The Bedsense app selects 10, 20 or 30 minutes; it has no timer-off command"
            )
        await self._send_singles(BEDSENSE_MASSAGE_TIMERS[minutes])
        self._timer_minutes = minutes

    async def massage_head_up(self) -> None:
        await self._innova_single(KeesonCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        await self._innova_single(KeesonCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        await self._innova_single(KeesonCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        await self._innova_single(KeesonCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """INNOVA massage-page timer button (one write)."""
        await self._innova_single(INNOVA_MASSAGE_TIMER)

    async def massage_level_step(self) -> None:
        """INNOVA massage level/pattern button (one write)."""
        await self._innova_single(INNOVA_MASSAGE_LEVEL)

    async def massage_timer_hold(self) -> None:
        """INNOVA memory-page timer button, streamed while held then released."""
        if not self._is_innova:
            raise NotImplementedError("Only the INNOVA app streams the timer key")
        await self._hold(INNOVA_MASSAGE_TIMER)

    async def _innova_single(self, key: int) -> None:
        if not self._is_innova:
            raise NotImplementedError("This control belongs to the INNOVA app")
        await self._send_singles(key)

    async def massage_toggle(self) -> None:
        raise NotImplementedError("These apps have no massage toggle")

    async def massage_intensity_up(self) -> None:
        raise NotImplementedError("These apps have no combined massage step")

    async def massage_intensity_down(self) -> None:
        raise NotImplementedError("These apps have no combined massage step")

    def get_massage_state(self) -> dict[str, Any]:
        return {
            "head_intensity": self._massage_levels["head"],
            "foot_intensity": self._massage_levels["foot"],
            "wave_intensity": self._massage_levels["wave"],
            "timer_mode": str(self._timer_minutes) if self._timer_minutes else None,
        }

    # ----------------------------------------------------------- app actions
    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self._is_bedsense:
            return (
                ControllerButtonSpec(
                    key=f"{ACTION_NAMESPACE}program_zero_g",
                    name="Program Zero G",
                    press_fn=_action("program_zero_g"),
                    icon="mdi:content-save",
                ),
                ControllerButtonSpec(
                    key=f"{ACTION_NAMESPACE}program_flat",
                    name="Program Flat",
                    press_fn=_action("program_flat"),
                    icon="mdi:content-save",
                ),
                ControllerButtonSpec(
                    key=f"{ACTION_NAMESPACE}massage_start",
                    name="Massage start",
                    press_fn=_action("massage_start"),
                    icon="mdi:play",
                ),
            )
        return (
            ControllerButtonSpec(
                key=f"{ACTION_NAMESPACE}massage_level",
                name="Massage level",
                press_fn=_action("massage_level_step"),
                icon="mdi:sine-wave",
            ),
            ControllerButtonSpec(
                key=f"{ACTION_NAMESPACE}massage_timer_hold",
                name="Massage timer (memory page)",
                press_fn=_action("massage_timer_hold"),
                icon="mdi:timer-outline",
            ),
        )

    # ---------------------------------------------------------------- rename
    @property
    def supports_device_rename(self) -> bool:
        return self._is_innova

    def validate_device_rename(self, name: str) -> None:
        if not self._is_innova:
            raise ValueError("Only the INNOVA app renames the bed")
        validate_innova_name(name)

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        # The editor writes once, without the single-send sleep.
        await self.write_command(innova_rename_frame(name), cancel_event=asyncio.Event())

    # ---------------------------------------------------------- notifications
    @property
    def requires_notification_channel(self) -> bool:
        return self._is_innova

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """INNOVA reads FFE4 state; Bedsense discards every reply, so it never subscribes."""
        self._notify_callback = callback
        if not self._is_innova or self.client is None or not self.client.is_connected:
            return
        try:
            await self.client.start_notify(self._notify_char_uuid, self._on_notification)
        except BleakError:
            # The app ignores the notification-enable result too.
            _LOGGER.warning("Failed to start INNOVA notifications")

    async def stop_notify(self) -> None:
        if not self._is_innova or self.client is None or not self.client.is_connected:
            return
        try:
            await self.client.stop_notify(self._notify_char_uuid)
        except BleakError:
            _LOGGER.debug("Failed to stop INNOVA notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        state = parse_innova_status(bytes(data))
        if state:
            self.forward_controller_state_updates(state)

    def invalidate_diagnostics(self) -> None:
        if self._is_innova:
            self.forward_controller_state_updates(
                dict.fromkeys((STATE_INNOVA_LIGHT, STATE_INNOVA_MASSAGE_TIMER))
            )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self._is_innova:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key=STATE_INNOVA_LIGHT,
                translation_key=STATE_INNOVA_LIGHT,
                state_key=STATE_INNOVA_LIGHT,
                icon="mdi:lightbulb",
            ),
        )

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset() if self._is_innova else frozenset({STATE_INNOVA_LIGHT})

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self._is_innova:
            return ()
        return (
            ControllerStateSensorSpec(
                key=STATE_INNOVA_MASSAGE_TIMER,
                translation_key=STATE_INNOVA_MASSAGE_TIMER,
                state_key=STATE_INNOVA_MASSAGE_TIMER,
                icon="mdi:timer-outline",
                native_unit_of_measurement="min",
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset() if self._is_innova else frozenset({STATE_INNOVA_MASSAGE_TIMER})

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {"ore_sfm_app": self._variant, "ore_sfm_layout": f"{self._layout}M"}
