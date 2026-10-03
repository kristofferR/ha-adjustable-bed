"""INNOVA app profile (com.ore.sfm 2.0 (3)).

Accepted clean-room audit, APK Protocol Audit cluster-015 / row059
(docs/apk-analysis/dispositions/row059-ore-bedsense-innova.md). Its sibling,
Bedsense Bases, shares the ORE comfort-bed behavior in ``ore_comfort_bed.py``.
INNOVA differs materially: the frame ``E5 FE 16 k0 k1 k2 k3 ~sum`` carries the
standard Keeson 32-bit key in little-endian order, Memory A/B and the
memory-page timer stream while held, massage is relative, the app can rename
the bed, and 16/19-byte FFE4 notifications drive the lamp and timer icons.

The app scans without any name or service rule, so the profile is explicit
only. The user picks the 2M/3M/4M screen with the motor count.

Timing: held keys write at 0 ms and then every 100 ms; ``buttonUp`` cancels the
refresh and, 100 ms later, writes the zero key. Every single-shot write is
preceded by a 100 ms sleep in ``sendSingleMessage``.
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
    KEESON_VARIANT_INNOVA,
)
from .base import (
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .keeson import KeesonCommands, KeesonController, _wait_unless_cancelled

_LOGGER = logging.getLogger(__name__)

# sendSingleMessage sleeps 100 ms on the caller before each single write,
# including the zero key that buttonUp sends after cancelling a hold.
SINGLE_SEND_DELAY_S: Final = 0.1
HOLD_INTERVAL_MS: Final = 100
ZERO_KEY: Final = 0x00000000

COMBINED_UP: Final = 0x00000005  # 2M back and foot together.
COMBINED_DOWN: Final = 0x0000000A
MASSAGE_LEVEL: Final = 0x00000100
MASSAGE_TIMER: Final = 0x00000200
RENAME_MAX_UNITS: Final = 14
RENAME_FRAME_LENGTH: Final = 18

STATE_LIGHT: Final = "innova_light"
STATE_MASSAGE_TIMER: Final = "innova_massage_timer"
_TIMER_MINUTES: Final = {-1: 0, 1: 10, 2: 20, 3: 30}

BUTTON_MASSAGE_LEVEL: Final = "innova_massage_level"
BUTTON_MASSAGE_TIMER_HOLD: Final = "innova_massage_timer_hold"

# Controls the app streams while the finger is down, by screen (motor count).
# Names avoid every other profile's held-control names.
_COMMON_HELD: Final = {
    "back_up": KeesonCommands.MOTOR_HEAD_UP,
    "back_down": KeesonCommands.MOTOR_HEAD_DOWN,
    "legs_up": KeesonCommands.MOTOR_FEET_UP,
    "legs_down": KeesonCommands.MOTOR_FEET_DOWN,
    "memory_a": KeesonCommands.PRESET_MEMORY_1,
    "memory_b": KeesonCommands.PRESET_MEMORY_2,
    "memory_timer": MASSAGE_TIMER,
}
_LAYOUT_HELD: Final[dict[int, dict[str, int]]] = {
    2: {"combined_up": COMBINED_UP, "combined_down": COMBINED_DOWN},
    3: {
        "lumbar_up": KeesonCommands.MOTOR_LUMBAR_UP,
        "lumbar_down": KeesonCommands.MOTOR_LUMBAR_DOWN,
    },
    4: {
        "waist_up": KeesonCommands.MOTOR_TILT_UP,
        "waist_down": KeesonCommands.MOTOR_TILT_DOWN,
        "lumbar_up": KeesonCommands.MOTOR_LUMBAR_UP,
        "lumbar_down": KeesonCommands.MOTOR_LUMBAR_DOWN,
    },
}
HELD_CONTROLS: Final = tuple(
    dict.fromkeys([*_COMMON_HELD, *(c for layout in _LAYOUT_HELD.values() for c in layout)])
)


def innova_frame(key: int) -> bytes:
    """``E5 FE 16 || low32(key) little-endian || ~sum`` (buildBluetoothPackage)."""
    body = bytes((0xE5, 0xFE, 0x16)) + (key & 0xFFFFFFFF).to_bytes(4, "little")
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
    """Apply the Options editor: maxLength 14 UTF-16 units, then trim, non-empty."""
    if _utf16_units(name) > RENAME_MAX_UNITS:
        raise ValueError("The INNOVA app limits names to 14 characters")
    trimmed = _java_trim(name)
    if not trimmed:
        raise ValueError("The INNOVA app requires a non-empty name")
    return trimmed


def innova_rename_frame(name: str) -> bytes:
    """Build the app's 18-byte ``EF 02`` rename frame.

    The app copies ``String.length()`` bytes (UTF-16 units) from
    ``getBytes()`` (UTF-8 on Android), so multibyte names are truncated
    exactly as the app truncates them. Byte 16 stays zero; byte 17 is the
    complemented sum of bytes 0..16.
    """
    trimmed = validate_innova_name(name)
    frame = bytearray(RENAME_FRAME_LENGTH)
    frame[0:2] = b"\xef\x02"
    raw = trimmed.encode("utf-8")[: _utf16_units(trimmed)]
    frame[2 : 2 + len(raw)] = raw
    frame[17] = (~sum(frame[:17])) & 0xFF
    return bytes(frame)


def parse_innova_status(data: bytes) -> dict[str, Any] | None:
    """Decode a notification exactly as ``GattUpdateReceiver`` does.

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
    state: dict[str, Any] = {STATE_LIGHT: bool((flags >> 6) & 1)}
    signed = timer - 256 if timer > 127 else timer
    if signed in _TIMER_MINUTES:
        state[STATE_MASSAGE_TIMER] = _TIMER_MINUTES[signed]
    return state


def _action(method: str) -> MotorCommandCallable:
    async def invoke(controller: Any) -> None:
        await getattr(controller, method)()

    return invoke


class InnovaController(KeesonController):
    """Explicit INNOVA app profile."""

    def __init__(self, coordinator: Any) -> None:
        # The app selects FFE9 by UUID across every service; no fallback roles.
        super().__init__(
            coordinator, variant=KEESON_VARIANT_INNOVA, char_uuid=KEESON_BASE_WRITE_CHAR_UUID
        )
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID
        # Roles resolved for one connection: (client, last FFE9, last FFE4).
        self._roles: tuple[object, BleakGATTCharacteristic, BleakGATTCharacteristic] | None = None

    # ------------------------------------------------------------------ layout
    @property
    def _layout(self) -> int:
        """The app's bedding2/3/4 selector, chosen with the motor count."""
        return min(4, max(2, self._coordinator.motor_count))

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        return {"head": "keeson_back", "feet": "keeson_legs"}

    @property
    def has_tilt_support(self) -> bool:
        return self._layout == 4

    @property
    def has_lumbar_support(self) -> bool:
        return self._layout >= 3

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Covers for the selected screen; one global key, so any STOP ends all motion."""

        def spec(key: str, translation_key: str, up: str, down: str) -> MotorControlSpec:
            return MotorControlSpec(
                key=key,
                translation_key=translation_key,
                open_fn=_action(up),
                close_fn=_action(down),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
            )

        specs = [
            spec("head", "keeson_back", "move_head_up", "move_head_down"),
            spec("feet", "keeson_legs", "move_feet_up", "move_feet_down"),
        ]
        if self._layout == 2:
            specs.append(spec("back_legs", "back_legs", "move_union_up", "move_union_down"))
        if self._layout == 4:
            specs.append(spec("waist", "waist", "move_tilt_up", "move_tilt_down"))
        if self._layout >= 3:
            # 3M: the third actuator uses bedLumbar IDs (0x40/0x80); 4M: lumbar.
            specs.append(spec("lumbar", "lumbar", "move_lumbar_up", "move_lumbar_down"))
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"tilt", "lumbar", "waist", "back_legs"})

    # ------------------------------------------------------------- transport
    def _build_command(self, command_value: int) -> bytes:
        return innova_frame(command_value)

    def _resolve_roles(self) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
        """Return the app's write and notify roles, resolved once per connection.

        The app scans every service, ignores service UUIDs and properties, and
        keeps the last FFE9 and the last FFE4 it sees; controls stay disabled
        unless both exist. Writing to those exact objects avoids bleak's
        ambiguous-UUID error on beds exposing duplicates. The app never sets a
        write type, so Android's default applies: without response when the
        characteristic offers it.
        """
        client = self.client
        if client is None or not client.is_connected or client.services is None:
            raise ConnectionError("Not connected to bed")
        if self._roles is not None and self._roles[0] is client:
            return self._roles[1], self._roles[2]
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
            raise BleakError("INNOVA requires both the FFE9 write and FFE4 notify characteristics")
        props = {prop.lower() for prop in getattr(write, "properties", [])}
        self._write_with_response = "write-without-response" not in props
        self._roles = (client, write, notify)
        return write, notify

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write to the resolved FFE9 object with Android's default write type."""
        selected = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        if selected.is_set():
            return
        write, _notify = self._resolve_roles()
        await self._write_gatt_with_retry(
            KEESON_BASE_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=selected,
            response=self._write_with_response,
            characteristic=write,
        )

    async def _send_singles(self, *keys: int) -> None:
        """``sendSingleMessage``: sleep 100 ms, then write once, per key."""
        for key in keys:
            await asyncio.sleep(SINGLE_SEND_DELAY_S)
            await self.write_command(self._build_command(key))

    async def _write_single_shot(self, command: bytes) -> None:
        await asyncio.sleep(SINGLE_SEND_DELAY_S)
        await self.write_command(command)

    async def _release(self, *, delay: bool) -> None:
        """``buttonUp``: the zero key, normally 100 ms after the refresh ends.

        A Stop, a cancelled hold or a replacement sends it at once, and a Stop
        arriving during the wait ends the wait. The write runs on a fresh event
        in its own task, which is never cancelled and is awaited until it
        finishes, however often the caller is cancelled. The cancellation is
        re-raised afterwards, unless the write failed: that error wins.
        """
        stop_requested = self._coordinator.cancel_command
        interrupted: asyncio.CancelledError | None = None
        if delay and not stop_requested.is_set():
            try:
                await _wait_unless_cancelled(stop_requested, SINGLE_SEND_DELAY_S)
            except asyncio.CancelledError as err:
                interrupted = err
        release = asyncio.create_task(
            self.write_command(self._build_command(ZERO_KEY), cancel_event=asyncio.Event())
        )
        # asyncio.wait never cancels the task, so keep waiting for the write
        # through any number of cancellations of this caller.
        while not release.done():
            try:
                await asyncio.wait((release,))
            except asyncio.CancelledError:
                interrupted = interrupted or asyncio.CancelledError()
        if interrupted is not None:
            # A failed release must not hide behind the cancellation: like an
            # exception raised in a finally block, the write error wins.
            failure = None if release.cancelled() else release.exception()
            if failure is not None:
                raise failure from interrupted
            raise interrupted
        release.result()

    async def _release_motion(self, *, delay: bool = True) -> None:
        await self._release(delay=delay)

    async def _hold(self, key: int, repeat_count: int | None = None) -> None:
        """Stream a held key every 100 ms, then release with the zero key."""
        if repeat_count is None:
            repeat_count, _delay = self.motor_pulse_settings()
        completed = False
        try:
            await self.write_command(
                self._build_command(key),
                repeat_count=repeat_count,
                repeat_delay_ms=HOLD_INTERVAL_MS,
            )
            completed = True
        finally:
            self._motor_state = {}
            await self._release(delay=completed)

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        self._motor_state = {motor: direction}
        command = self._get_move_command()
        if command:
            await self._hold(command)
        else:
            self._motor_state = {}
            await self._release(delay=False)

    async def move_union_up(self) -> None:
        """2M combined back and legs up (``0x05``)."""
        await self._hold(COMBINED_UP)

    async def move_union_down(self) -> None:
        """2M combined back and legs down (``0x0A``)."""
        await self._hold(COMBINED_DOWN)

    async def stop_all(self) -> None:
        self._motor_state = {}
        await self._release(delay=False)

    @property
    def supports_stop_all(self) -> bool:
        """buttonUp sends the zero key; it is exposed as Stop."""
        return True

    # ---------------------------------------------------------- held controls
    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*_COMMON_HELD, *_LAYOUT_HELD[self._layout])

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Hold one streamed app control for a duration, then release it."""
        controls = {**_COMMON_HELD, **_LAYOUT_HELD[self._layout]}
        if control not in controls:
            raise ValueError(f"The INNOVA {self._layout}M screen has no held control {control}")
        if isinstance(duration_ms, bool) or not 100 <= duration_ms <= 60000:
            raise ValueError("Hold duration must be 100..60000 milliseconds")
        if self._coordinator.cancel_command.is_set():
            return
        await self._hold(controls[control], repeat_count=-(-duration_ms // HOLD_INTERVAL_MS))

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
        return 2

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    @property
    def supports_memory_programming(self) -> bool:
        return False

    async def preset_flat(self) -> None:
        await self._send_singles(KeesonCommands.PRESET_FLAT)

    async def preset_zero_g(self) -> None:
        await self._send_singles(KeesonCommands.PRESET_ZERO_G)

    async def preset_memory(self, memory_num: int) -> None:
        """Memory A/B stream while held; a press holds for one motor burst."""
        if memory_num not in (1, 2):
            raise ValueError("INNOVA has Memory A (1) and Memory B (2) only")
        await self._hold(
            KeesonCommands.PRESET_MEMORY_1 if memory_num == 1 else KeesonCommands.PRESET_MEMORY_2
        )

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("The INNOVA app has no memory programming command")

    async def preset_lounge(self) -> None:
        raise NotImplementedError("INNOVA has no lounge preset")

    async def preset_tv(self) -> None:
        raise NotImplementedError("INNOVA has no TV preset")

    async def preset_anti_snore(self) -> None:
        raise NotImplementedError("INNOVA has no anti-snore preset")

    # ----------------------------------------------------------------- lights
    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    async def lights_on(self) -> None:
        raise NotImplementedError("The INNOVA app has only a light toggle")

    async def lights_off(self) -> None:
        raise NotImplementedError("The INNOVA app has only a light toggle")

    async def lights_toggle(self) -> None:
        await self._send_singles(KeesonCommands.TOGGLE_LIGHTS)

    # ---------------------------------------------------------------- massage
    @property
    def auto_enable_massage(self) -> bool:
        return True  # Every screen shows the massage page.

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return False

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
        return True

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return True

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return True

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
        return False

    async def massage_head_up(self) -> None:
        await self._send_singles(KeesonCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        await self._send_singles(KeesonCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        await self._send_singles(KeesonCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        await self._send_singles(KeesonCommands.MASSAGE_FOOT_DOWN)

    async def massage_mode_step(self) -> None:
        """Massage-page timer button (one write)."""
        await self._send_singles(MASSAGE_TIMER)

    async def massage_level_step(self) -> None:
        """Massage level/pattern button (one write)."""
        await self._send_singles(MASSAGE_LEVEL)

    async def massage_timer_hold(self) -> None:
        """Memory-page timer button: streamed while held, then released."""
        await self._hold(MASSAGE_TIMER)

    async def massage_toggle(self) -> None:
        raise NotImplementedError("INNOVA has no massage toggle")

    async def massage_off(self) -> None:
        raise NotImplementedError("INNOVA has no massage off command")

    async def massage_intensity_up(self) -> None:
        raise NotImplementedError("INNOVA has no combined massage step")

    async def massage_intensity_down(self) -> None:
        raise NotImplementedError("INNOVA has no combined massage step")

    # ----------------------------------------------------------- app actions
    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                key=BUTTON_MASSAGE_LEVEL,
                name="Massage level",
                press_fn=_action("massage_level_step"),
                icon="mdi:sine-wave",
                translation_key=BUTTON_MASSAGE_LEVEL,
            ),
            ControllerButtonSpec(
                key=BUTTON_MASSAGE_TIMER_HOLD,
                name="Massage timer (memory page)",
                press_fn=_action("massage_timer_hold"),
                icon="mdi:timer-outline",
                translation_key=BUTTON_MASSAGE_TIMER_HOLD,
            ),
        )

    # ---------------------------------------------------------------- rename
    @property
    def supports_device_rename(self) -> bool:
        return True

    def validate_device_rename(self, name: str) -> None:
        validate_innova_name(name)

    async def rename_device(self, name: str) -> None:
        # The editor writes once, without the single-send sleep.
        await self.write_command(innova_rename_frame(name), cancel_event=asyncio.Event())

    # ---------------------------------------------------------- notifications
    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe FFE4: the app parses its replies (it enables them locally only)."""
        self._notify_callback = callback
        if self.client is None or not self.client.is_connected:
            return
        try:
            # The last FFE4 the app found; a UUID string is ambiguous on duplicates.
            _write, notify = self._resolve_roles()
            await self.client.start_notify(notify, self._on_notification)
        except BleakError, ConnectionError:
            # The app ignores the notification-enable result too.
            _LOGGER.warning("Failed to start INNOVA notifications")

    async def stop_notify(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            return
        roles = self._roles
        try:
            await client.stop_notify(
                roles[2] if roles is not None and roles[0] is client else self._notify_char_uuid
            )
        except BleakError:
            _LOGGER.debug("Failed to stop INNOVA notifications")

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))
        state = parse_innova_status(bytes(data))
        if state:
            self.forward_controller_state_updates(state)

    def invalidate_diagnostics(self) -> None:
        self.forward_controller_state_updates(dict.fromkeys((STATE_LIGHT, STATE_MASSAGE_TIMER)))

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                key=STATE_LIGHT,
                translation_key=STATE_LIGHT,
                state_key=STATE_LIGHT,
                icon="mdi:lightbulb",
            ),
        )

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key=STATE_MASSAGE_TIMER,
                translation_key=STATE_MASSAGE_TIMER,
                state_key=STATE_MASSAGE_TIMER,
                icon="mdi:timer-outline",
                native_unit_of_measurement="min",
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset()

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {"app": "INNOVA", "app_package": "com.ore.sfm 2.0 (3)", "layout": f"{self._layout}M"}
