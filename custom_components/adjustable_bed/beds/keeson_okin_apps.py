"""Okin app profiles on the big-endian Keeson E5 frame.

Accepted clean-room audits (APK Protocol Audit cluster-012, row060):

- ``com.okin.simon`` 1.0.1 (2), "Simon Li" (chair, love seat and sofa seats)
- ``com.okin.healeverynight`` 1.0 (1), "Heal Every Night" (Healing 6/7/8 beds)
- ``com.okin.minghua.R`` 1.0.1 (2), "OKIN-Seating"

All three write ``E5 FE 16 || key_be32 || ~sum`` to the first FFE9
characteristic of the last service (in Java UUID order) that has one, and
enable notifications on every FFE4 characteristic, whose bytes they discard.
They differ in their key tables, release timing and features, so every control
is gated per app. None of them filters its scan, so the profiles are explicit
selections only.

Simon Li and OKIN-Seating stream held keys at 0 ms and then every 100 ms;
release sleeps 10 ms and writes the zero key. Heal Every Night streams movement
the same way but writes the zero key 100 ms after release; its presets, light
and massage are single writes with app-local state.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..app_session import app_session
from ..const import (
    KEESON_BASE_NOTIFY_CHAR_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_SIMON_LI,
    OKIN_APP_VARIANTS,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .keeson import KeesonController

_LOGGER = logging.getLogger(__name__)


ZERO_KEY: Final = 0x00000000
HOLD_INTERVAL_MS: Final = 100
# Simon Li / OKIN-Seating sendSingleMessage sleeps 10 ms before the zero key.
SEAT_RELEASE_DELAY_S: Final = 0.01
# Heal Every Night stopTimer posts the zero key 100 ms after release.
HEAL_RELEASE_DELAY_S: Final = 0.1
# Simon Li shows "Memory saved" after holding a memory key for 2100 ms; the
# bytes are the same memory stream, so saving is holding it that long.
SIMON_MEMORY_SAVE_HOLD_MS: Final = 2100
# A recall press stays below that threshold whatever the pulse settings.
SIMON_MEMORY_RECALL_MAX_MS: Final = 2000
HOLD_MIN_MS: Final = 100
HOLD_MAX_MS: Final = 60_000

# Simon Li held keys (ButtonListener tags).
SIMON_KEYS: Final[dict[str, int]] = {
    "foot_up": 0x01,
    "foot_down": 0x02,
    "back_up": 0x04,
    "back_down": 0x08,
    "lumbar_up": 0x10,
    "lumbar_down": 0x20,
    "home": 0x16,
    "memory_1": 0x40,
    "memory_2": 0x80,
}
# OKIN-Seating held keys. Its foot tags carry the opposite "union" artwork; the
# integration follows the tags, as the app's identifiers do.
SEATING_KEYS: Final[dict[str, int]] = {
    "back_up": 0x04,
    "back_down": 0x08,
    "foot_up": 0x01,
    "foot_down": 0x02,
    "home": 0x0A,
}

# Heal Every Night cmdarray: head_on, leg_on, tilt_on, lumbar_on, head_off,
# leg_off, tilt_off, lumbar_off.
HEAL_MOVEMENT_KEYS: Final = (0x01, 0x04, 0x10, 0x40, 0x02, 0x08, 0x20, 0x80)
HEAL_PRESET_STOP: Final = 0x01000000
HEAL_PRESETS: Final[dict[str, int]] = {
    "zero_g": 0x01000001,
    "flat": 0x01000002,
    "memory_1": 0x01000008,
    "memory_2": 0x01000009,
}
HEAL_MEMORY_SAVE: Final[dict[int, int]] = {1: 0x20000008, 2: 0x20000009}
HEAL_HEAD_MASSAGE: Final = 0x10000010  # + level 0..3 (0 is off)
HEAL_FOOT_MASSAGE: Final = 0x11000010  # + level 0..3
HEAL_WAVE: Final = 0x10000020  # + level - 1, levels 1..4
# Timer 10, 20 and 30 all send timer1; the app never reads timer2/timer3.
HEAL_TIMER: Final = 0x10000030
HEAL_TIMER_OPTIONS: Final = (10, 20, 30)
HEAL_LIGHT_ON: Final = 0x31000001
HEAL_LIGHT_OFF: Final = 0x31000000
HEAL_MASSAGE_STEP_DELAY_S: Final = 0.1
HEAL_ZONE_MAX: Final = 3
HEAL_WAVE_MAX: Final = 4

# Heal Every Night settings (Installation Mode, Actuator Direction 1/2).
SETTING_INSTALLATION: Final = "installation"
SETTING_ACTUATOR_1: Final = "actuator_1"
SETTING_ACTUATOR_2: Final = "actuator_2"
HEAL_SETTING_OPTIONS: Final[dict[str, tuple[str, str]]] = {
    SETTING_INSTALLATION: ("standard", "swapped"),
    SETTING_ACTUATOR_1: ("normal", "reversed"),
    SETTING_ACTUATOR_2: ("normal", "reversed"),
}

ACTION_NAMESPACE: Final = "okin_app_"
STATE_HEAL_MASSAGE: Final[dict[str, str]] = {
    "head": "okin_app_massage_head",
    "foot": "okin_app_massage_foot",
    "wave": "okin_app_massage_wave",
}
STATE_HEAL_TIMER: Final = "okin_app_massage_timer"


async def _run_to_completion(cleanup: Coroutine[Any, Any, None]) -> None:
    """Run a cleanup sequence to its end even if the caller is cancelled.

    The caller's cancellation is re-raised once the sequence has finished.
    """
    task = asyncio.ensure_future(cleanup)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:  # noqa: BLE001 - re-raised below unless cancelled
            break
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    task.result()


def okin_app_frame(key: int) -> bytes:
    """Build ``E5 FE 16 || low32(key) big-endian || ~sum``."""
    body = bytes((0xE5, 0xFE, 0x16)) + (key & 0xFFFFFFFF).to_bytes(4, "big")
    return body + bytes(((~sum(body)) & 0xFF,))


def heal_movement_key(
    control: str, *, installation: bool, actuator_1: bool, actuator_2: bool
) -> int:
    """Return the key a Heal Every Night movement button sends.

    Installation Mode swaps the head and foot buttons' actuators; each
    Actuator Direction setting reverses its actuator's pair. Tilt and lumbar
    never change.
    """
    head = (4, 0) if actuator_1 else (0, 4)
    foot = (5, 1) if actuator_2 else (1, 5)
    if installation:
        head, foot = foot, head
    index = {
        "head_up": head[0],
        "head_down": head[1],
        "foot_up": foot[0],
        "foot_down": foot[1],
        "tilt_up": 2,
        "tilt_down": 6,
        "lumbar_up": 3,
        "lumbar_down": 7,
    }[control]
    return HEAL_MOVEMENT_KEYS[index]


def java_uuid_order(uuid: str) -> tuple[int, int]:
    """Sort key of ``java.util.UUID.compareTo``: signed high, then low 64 bits."""
    value = int(uuid.replace("-", ""), 16)

    def signed(word: int) -> int:
        return word - (1 << 64) if word >= 1 << 63 else word

    return signed(value >> 64), signed(value & ((1 << 64) - 1))


@dataclass(slots=True)
class HealSession:
    """Heal Every Night page state for one bed for the config entry's life.

    The app keeps it in its fragments (selected preset, light button and
    massage page). Home Assistant rebuilds the controller on every connection,
    so it lives here to keep a reconnect from forgetting the preset to stop,
    the light state or the massage levels. ``settings`` is the persisted app
    state (Installation Mode and Actuator Direction).
    """

    selected_preset: str | None = None
    light_on: bool = False
    massage_enabled: bool = False
    head: int = 0
    foot: int = 0
    wave: int = 0
    timer_minutes: int | None = None
    settings: dict[str, bool] = field(
        default_factory=lambda: dict.fromkeys(HEAL_SETTING_OPTIONS, False)
    )


def _press(method: str, *args: Any) -> MotorCommandCallable:
    async def invoke(controller: Any) -> None:
        await getattr(controller, method)(*args)

    return invoke


class OkinAppKeesonController(KeesonController):
    """Explicit Simon Li, Heal Every Night and OKIN-Seating app profiles."""

    def __init__(self, coordinator: Any, variant: str) -> None:
        if variant not in OKIN_APP_VARIANTS:
            raise ValueError(f"Unsupported Okin app profile: {variant}")
        super().__init__(coordinator, variant=variant, char_uuid=KEESON_BASE_WRITE_CHAR_UUID)
        self._is_simon = variant == KEESON_VARIANT_SIMON_LI
        self._is_heal = variant == KEESON_VARIANT_HEAL_EVERY_NIGHT
        self._is_seating = variant == KEESON_VARIANT_OKIN_SEATING
        self._notify_char_uuid = KEESON_BASE_NOTIFY_CHAR_UUID
        self._session = HealSession()
        if self._is_heal:
            self._session = app_session(
                coordinator.hass, str(coordinator.address), ("okin_app", variant), HealSession
            )
            self.forward_controller_state_updates(self._published_state())

    # ------------------------------------------------------------- profile
    @property
    def _product(self) -> int:
        """Heal Every Night's Healing 6/7/8 picker, chosen with the motor count."""
        return min(4, max(2, self._coordinator.motor_count))

    @property
    def _heal_full(self) -> bool:
        """Healing 7 and 8 show tilt, lumbar and the light; Healing 6 does not."""
        return self._is_heal and self._product >= 3

    @property
    def _seat_keys(self) -> dict[str, int]:
        return SIMON_KEYS if self._is_simon else SEATING_KEYS

    def _settings(self) -> dict[str, bool]:
        return dict(self._session.settings)

    @property
    def persisted_app_state(self) -> dict[str, bool] | None:
        """Heal Every Night keeps its movement settings across restarts."""
        return self._settings() if self._is_heal else None

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        if set(state) - set(HEAL_SETTING_OPTIONS) or any(type(v) is not bool for v in state.values()):
            raise ValueError("Invalid Heal Every Night settings")
        self._session.settings = {key: state.get(key) is True for key in HEAL_SETTING_OPTIONS}
        self.forward_controller_state_updates(self._published_state())

    @property
    def supports_single_address_pairing(self) -> bool:
        """The frame has no side field; each seat or bed is its own address."""
        return False

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {"okin_app": self._variant}
        if self._is_heal:
            diagnostics["okin_app_product"] = f"Healing {self._product + 4}"
            diagnostics["okin_app_settings"] = self._settings()
        return diagnostics

    # -------------------------------------------------------------- motors
    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        return None

    @property
    def has_tilt_support(self) -> bool:
        return self._heal_full

    @property
    def has_lumbar_support(self) -> bool:
        return self._is_simon or self._heal_full

    def _axis(self, key: str, translation_key: str, up: str, down: str) -> MotorControlSpec:
        return MotorControlSpec(
            key=key,
            translation_key=translation_key,
            open_fn=_press("hold_app_control", up),
            close_fn=_press("hold_app_control", down),
            stop_fn=_press("release_now"),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if self._is_heal:
            specs = [
                self._axis("head", "head", "head_up", "head_down"),
                self._axis("feet", "feet", "foot_up", "foot_down"),
            ]
            if self._heal_full:
                specs.append(self._axis("tilt", "tilt", "tilt_up", "tilt_down"))
                specs.append(self._axis("lumbar", "lumbar", "lumbar_up", "lumbar_down"))
            return tuple(specs)
        specs = [
            self._axis("back", "back", "back_up", "back_down"),
            self._axis("feet", "feet", "foot_up", "foot_down"),
        ]
        if self._is_simon:
            specs.append(self._axis("lumbar", "lumbar", "lumbar_up", "lumbar_down"))
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset({"head", "back", "feet", "tilt", "lumbar"})

    @property
    def held_control_options(self) -> tuple[str, ...]:
        """Every streamed app control, for the ``hold_control`` action."""
        if not self._is_heal:
            return tuple(self._seat_keys)
        options = ["head_up", "head_down", "foot_up", "foot_down"]
        if self._heal_full:
            options += ["tilt_up", "tilt_down", "lumbar_up", "lumbar_down"]
        return tuple(options)

    def _held_key(self, control: str) -> int:
        if control not in self.held_control_options:
            raise NotImplementedError(f"This app has no held control '{control}'")
        if self._is_heal:
            return heal_movement_key(control, **self._settings())
        return self._seat_keys[control]

    def motor_pulse_settings(self) -> tuple[int, int]:
        """The configured repeat count at the apps' fixed 100 ms refresh."""
        count, _delay_ms = super().motor_pulse_settings()
        return count, HOLD_INTERVAL_MS

    async def hold_app_control(self, control: str) -> None:
        """Hold a control for the configured burst, as one app press."""
        repeat_count, repeat_delay_ms = self.motor_pulse_settings()
        await self._stream(self._held_key(control), repeat_count, repeat_delay_ms)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Hold one app control for ``duration_ms``, then release it like a touch-up."""
        key = self._held_key(control)
        if isinstance(duration_ms, bool) or not HOLD_MIN_MS <= duration_ms <= HOLD_MAX_MS:
            raise ValueError("Hold duration must be 100..60000 milliseconds")
        await self._hold_for(key, duration_ms)

    async def _hold_for(self, key: int, duration_ms: int) -> None:
        writes = -(-duration_ms // HOLD_INTERVAL_MS)
        tail = (duration_ms - (writes - 1) * HOLD_INTERVAL_MS) / 1000
        await self._stream(key, writes, HOLD_INTERVAL_MS, tail_s=tail)

    async def _stream(
        self,
        key: int,
        repeat_count: int,
        repeat_delay_ms: int,
        *,
        tail_s: float = 0,
        max_s: float | None = None,
    ) -> None:
        """Write a held key at 0 ms and every interval, then release it.

        ``max_s`` bounds the elapsed time, not the write count: each interval
        is the write's own latency plus the delay. Reaching it ends the stream
        at once, even during a refresh sleep or a write.
        """
        cancel_event = self._coordinator.cancel_command
        deadline = asyncio.timeout(max_s)
        try:
            async with deadline:
                await self.write_command(
                    okin_app_frame(key),
                    repeat_count=repeat_count,
                    repeat_delay_ms=repeat_delay_ms,
                    cancel_event=cancel_event,
                )
                if tail_s > 0 and not cancel_event.is_set():
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(cancel_event.wait(), tail_s)
        except TimeoutError:
            if not deadline.expired():
                raise
        finally:
            await self._release_motion()

    async def _release_motion(self, *, delay: bool = True) -> None:
        """Write the zero key after the app's release delay, even when cancelled."""
        seconds = (HEAL_RELEASE_DELAY_S if self._is_heal else SEAT_RELEASE_DELAY_S) if delay else 0
        delaying = False

        async def release() -> None:
            nonlocal delaying
            if seconds:
                # Only this sleep may be cut short; the write after it never is.
                delaying = True
                try:
                    await asyncio.sleep(seconds)
                except asyncio.CancelledError:
                    pass  # Skip the remaining delay, then still write the zero key.
                finally:
                    delaying = False
            await self.write_command(okin_app_frame(ZERO_KEY), cancel_event=asyncio.Event())

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
                if delaying:
                    # Skip the remaining delay; never cancel the zero-key write.
                    task.cancel()
            except Exception:  # noqa: BLE001 - re-raised below unless cancelled
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def release_now(self) -> None:
        """A motor stop: the app's movement release (zero key), written at once."""
        await self._release_motion(delay=False)

    async def stop_all(self) -> None:
        """Stop All: the zero key at once; Heal also stops a selected preset.

        Both frames are attempted even when the other fails or the caller is
        cancelled, because only preset STOP halts preset travel. The first
        error is raised afterwards.
        """
        errors: list[BaseException] = []
        try:
            await self.release_now()
        except BaseException as err:  # noqa: BLE001 - re-raised after preset STOP
            errors.append(err)
        if self._is_heal and self._session.selected_preset is not None:

            async def preset_stop() -> None:
                # The app stops preset travel by re-tapping the selected preset.
                # Deselect only once STOP is written, so a failure can be retried.
                if await self._write_key(HEAL_PRESET_STOP, cancel_event=asyncio.Event()):
                    self._session.selected_preset = None

            try:
                await _run_to_completion(preset_stop())
            except BaseException as err:  # noqa: BLE001 - the first error wins
                errors.append(err)
        if errors:
            raise errors[0]

    @property
    def supports_stop_all(self) -> bool:
        return True

    async def _seat_or_heal(self, seat: str, heal: str) -> None:
        await self.hold_app_control(heal if self._is_heal else seat)

    async def move_head_up(self) -> None:
        await self._seat_or_heal("back_up", "head_up")

    async def move_head_down(self) -> None:
        await self._seat_or_heal("back_down", "head_down")

    async def move_head_stop(self) -> None:
        await self.release_now()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.release_now()

    async def move_feet_up(self) -> None:
        await self.hold_app_control("foot_up")

    async def move_feet_down(self) -> None:
        await self.hold_app_control("foot_down")

    async def move_feet_stop(self) -> None:
        await self.release_now()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.release_now()

    async def move_tilt_up(self) -> None:
        await self.hold_app_control("tilt_up")

    async def move_tilt_down(self) -> None:
        await self.hold_app_control("tilt_down")

    async def move_tilt_stop(self) -> None:
        await self.release_now()

    async def move_lumbar_up(self) -> None:
        await self.hold_app_control("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.hold_app_control("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self.release_now()

    # ------------------------------------------------------------ transport
    def _build_command(self, command_value: int) -> bytes:
        return okin_app_frame(command_value)

    def _write_target(self) -> BleakGATTCharacteristic | None:
        """Return the app's write characteristic, or None before enumeration.

        The app walks services in Java UUID order and keeps the last FFE9
        match; Android then writes the first FFE9 of that service. Its SDK
        refuses a characteristic without the WRITE property.
        """
        client = self.client
        services = list(client.services) if client is not None and client.services else []
        if not services:
            return None
        matches = [
            (service, char)
            for service in services
            for char in service.characteristics
            if str(char.uuid).lower() == KEESON_BASE_WRITE_CHAR_UUID
        ]
        if not matches:
            raise BleakError("This app profile requires the FFE9 write characteristic")
        last = max(java_uuid_order(str(service.uuid)) for service, _char in matches)
        char = next(c for s, c in matches if java_uuid_order(str(s.uuid)) == last)
        if "write" not in {prop.lower() for prop in char.properties}:
            raise BleakError("The FFE9 characteristic does not allow writes")
        return char

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        """Write to the app's FFE9 with Android's default write type."""
        selected = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        if selected.is_set():
            return
        target = self._write_target()
        # Android defaults a characteristic that offers write-without-response
        # to that type, and the app never changes it.
        response = target is None or "write-without-response" not in {
            prop.lower() for prop in target.properties
        }
        await self._write_gatt_with_retry(
            KEESON_BASE_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=selected,
            response=response,
            characteristic=target,
            on_write=on_write,
        )

    async def _write_key(self, key: int, cancel_event: asyncio.Event | None = None) -> bool:
        """Write one key; True only when the frame went out.

        A cancelled command skips the write without an error, so app state is
        committed only on a confirmed write, never just on the absence of one.
        """
        written = False

        def confirm() -> None:
            nonlocal written
            written = True

        await self.write_command(okin_app_frame(key), cancel_event=cancel_event, on_write=confirm)
        return written

    async def _write_single_shot(self, command: bytes) -> None:
        await self.write_command(command)

    # -------------------------------------------------------- notifications
    @property
    def requires_notification_channel(self) -> bool:
        """The apps enable FFE4 notifications on every connection."""
        return True

    def _notify_targets(self) -> list[BleakGATTCharacteristic | str]:
        client = self.client
        services = list(client.services) if client is not None and client.services else []
        if not services:
            return [self._notify_char_uuid]
        return [
            char
            for service in services
            for char in service.characteristics
            if str(char.uuid).lower() == KEESON_BASE_NOTIFY_CHAR_UUID
            and "notify" in {prop.lower() for prop in char.properties}
        ]

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe every FFE4 like the app; the replies carry no app state."""
        self._notify_callback = callback
        if self.client is None or not self.client.is_connected:
            return
        for target in self._notify_targets():
            try:
                async with self._ble_lock:
                    await self.client.start_notify(target, self._on_notification)
            except BleakError:
                # The app ignores the subscription result, and controls never wait for it.
                _LOGGER.debug("Failed to enable FFE4 notifications on %s", target)

    async def stop_notify(self) -> None:
        if self.client is None or not self.client.is_connected:
            return
        for target in self._notify_targets():
            try:
                async with self._ble_lock:
                    await self.client.stop_notify(target)
            except BleakError:
                _LOGGER.debug("Failed to stop FFE4 notifications on %s", target)

    def _on_notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        # Simon Li and OKIN-Seating discard the bytes; Heal Every Night only
        # raises an event for an E2 FE 16 prefix that nothing consumes.
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))

    # -------------------------------------------------------------- presets
    @property
    def supports_preset_flat(self) -> bool:
        return self._is_heal

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._is_heal

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
    def supports_memory_presets(self) -> bool:
        return not self._is_seating

    @property
    def memory_slot_count(self) -> int:
        return 0 if self._is_seating else 2

    @property
    def supports_memory_programming(self) -> bool:
        return not self._is_seating

    async def _heal_preset(self, preset: str) -> None:
        """Tap a Heal preset: recall it, or stop it when it is already selected."""
        # The selection changes only once its frame is written, so a failed
        # recall is retried as a recall rather than turned into a STOP.
        if self._session.selected_preset == preset:
            if await self._write_key(HEAL_PRESET_STOP):
                self._session.selected_preset = None
            return
        if await self._write_key(HEAL_PRESETS[preset]):
            self._session.selected_preset = preset

    async def preset_flat(self) -> None:
        if not self._is_heal:
            raise NotImplementedError("This app has no Flat preset")
        await self._heal_preset("flat")

    async def preset_zero_g(self) -> None:
        if not self._is_heal:
            raise NotImplementedError("This app has no Zero G preset")
        await self._heal_preset("zero_g")

    async def preset_memory(self, memory_num: int) -> None:
        if self._is_seating:
            raise NotImplementedError("The OKIN-Seating app has no memory")
        if memory_num not in (1, 2):
            raise ValueError("This app has memory 1 and memory 2 only")
        if self._is_heal:
            await self._heal_preset(f"memory_{memory_num}")
        else:
            # Stay below the app's 2.1 s save hold on a recall: cap the writes
            # and, since write latency adds to every interval, the elapsed time.
            count, delay_ms = self.motor_pulse_settings()
            writes = min(count, SIMON_MEMORY_RECALL_MAX_MS // max(delay_ms, 1) + 1)
            await self._stream(
                SIMON_KEYS[f"memory_{memory_num}"],
                writes,
                delay_ms,
                max_s=SIMON_MEMORY_RECALL_MAX_MS / 1000,
            )

    async def program_memory(self, memory_num: int) -> None:
        if self._is_seating:
            raise NotImplementedError("The OKIN-Seating app has no memory")
        if memory_num not in (1, 2):
            raise ValueError("This app has memory 1 and memory 2 only")
        if self._is_heal:
            # The app sends the save once a two-second hold completes; the
            # release then skips the recall and the preset selection is unchanged.
            await self._write_key(HEAL_MEMORY_SAVE[memory_num])
        else:
            await self._hold_for(SIMON_KEYS[f"memory_{memory_num}"], SIMON_MEMORY_SAVE_HOLD_MS)

    async def preset_lounge(self) -> None:
        raise NotImplementedError("These apps have no lounge preset")

    async def preset_tv(self) -> None:
        raise NotImplementedError("These apps have no TV preset")

    async def preset_anti_snore(self) -> None:
        raise NotImplementedError("These apps have no anti-snore preset")

    async def preset_home(self) -> None:
        """Simon Li / OKIN-Seating Home: a held key whose posture is not established."""
        await self.hold_app_control("home")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self._is_heal:
            return ()
        return (
            ControllerButtonSpec(
                key=f"{ACTION_NAMESPACE}home",
                name="Home",
                translation_key=f"{ACTION_NAMESPACE}home",
                press_fn=_press("preset_home"),
                icon="mdi:home",
            ),
        )

    # ---------------------------------------------------------------- light
    @property
    def supports_lights(self) -> bool:
        return self._heal_full

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._heal_full

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def light_state_is_assumed(self) -> bool:
        """The light has no state feedback; the switch shows the commanded value."""
        return self._heal_full

    def _require_light(self) -> None:
        if not self._heal_full:
            raise NotImplementedError("Only Healing 7 and 8 have the light")

    async def lights_on(self) -> None:
        self._require_light()
        if await self._write_key(HEAL_LIGHT_ON):
            self._session.light_on = True

    async def lights_off(self) -> None:
        self._require_light()
        if await self._write_key(HEAL_LIGHT_OFF):
            self._session.light_on = False

    async def lights_toggle(self) -> None:
        """The app's light button: its local state picks on or off."""
        await (self.lights_off() if self._session.light_on else self.lights_on())

    # -------------------------------------------------------------- massage
    @property
    def auto_enable_massage(self) -> bool:
        return self._is_heal

    @property
    def supports_massage_toggle_control(self) -> bool:
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
        return self._is_heal

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self._is_heal

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    @property
    def supports_massage_off_control(self) -> bool:
        return self._is_heal

    @property
    def supports_massage_intensity_control(self) -> bool:
        return False

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self._is_heal

    @property
    def supports_massage_intensity_preset_control(self) -> bool:
        return False

    @property
    def supports_massage_timer(self) -> bool:
        return self._is_heal

    @property
    def massage_timer_options(self) -> list[int]:
        return list(HEAL_TIMER_OPTIONS) if self._is_heal else []

    def _published_state(self) -> dict[str, Any]:
        session = self._session
        state: dict[str, Any] = {
            STATE_HEAL_MASSAGE["head"]: session.head,
            STATE_HEAL_MASSAGE["foot"]: session.foot,
            # Wave levels are 1..4; before the first timer the app has none.
            STATE_HEAL_MASSAGE["wave"]: session.wave or None,
            STATE_HEAL_TIMER: session.timer_minutes,
        }
        settings = self._settings()
        for setting, options in HEAL_SETTING_OPTIONS.items():
            state[f"{ACTION_NAMESPACE}{setting}"] = options[settings[setting]]
        return state

    def _require_massage_page(self) -> None:
        if not self._is_heal:
            raise NotImplementedError("Only the Heal Every Night app has massage")
        if not self._session.massage_enabled:
            # The app enables the sliders and +/- buttons only after a timer.
            raise ValueError("Start the massage with a timer first")

    async def _send_massage_steps(self, keys: list[int]) -> bool:
        """Write a page sequence 100 ms apart; True only when every frame went out."""
        for index, key in enumerate(keys):
            if index:
                await asyncio.sleep(HEAL_MASSAGE_STEP_DELAY_S)
            if not await self._write_key(key):
                return False
        return True

    async def set_massage_timer(self, minutes: int) -> None:
        """Timer 10/20/30 start the massage page; Off is the app's STOP."""
        if not self._is_heal:
            raise NotImplementedError("Only the Heal Every Night app has a massage timer")
        if minutes == 0:
            await self.massage_off()
            return
        if minutes not in HEAL_TIMER_OPTIONS:
            raise ValueError("The app offers 10, 20 or 30 minutes")
        session = self._session
        # Zero levels become one, then timer1, the wave, head and foot follow.
        wave, head, foot = session.wave or 1, session.head or 1, session.foot or 1
        if not await self._send_massage_steps(
            [HEAL_TIMER, HEAL_WAVE + wave - 1, HEAL_HEAD_MASSAGE + head, HEAL_FOOT_MASSAGE + foot]
        ):
            return  # The page keeps its previous state until the whole start is written.
        session.wave, session.head, session.foot = wave, head, foot
        session.massage_enabled = True
        session.timer_minutes = minutes
        self.forward_controller_state_updates(self._published_state())

    async def massage_off(self) -> None:
        """The massage STOP button: both zones off; levels are kept."""
        if not self._is_heal:
            raise NotImplementedError("Only the Heal Every Night app has massage")

        async def zones_off() -> None:
            # Both zone-off frames are attempted even if one fails, each with a
            # fresh event; the page closes only once both are written.
            errors: list[BaseException] = []
            written = 0
            for index, key in enumerate((HEAL_HEAD_MASSAGE, HEAL_FOOT_MASSAGE)):
                if index:
                    await asyncio.sleep(HEAL_MASSAGE_STEP_DELAY_S)
                try:
                    written += await self._write_key(key, cancel_event=asyncio.Event())
                except Exception as err:  # noqa: BLE001 - raised after the other zone
                    errors.append(err)
            if written == 2:
                self._session.massage_enabled = False
                self._session.timer_minutes = None
                self.forward_controller_state_update(STATE_HEAL_TIMER, None)
            if errors:
                raise errors[0]

        await _run_to_completion(zones_off())

    async def set_heal_massage_level(self, zone: str, level: int) -> None:
        """A slider: head and foot 0..3 (0 is off), wave 1..4."""
        self._require_massage_page()
        low, high = (1, HEAL_WAVE_MAX) if zone == "wave" else (0, HEAL_ZONE_MAX)
        if zone not in STATE_HEAL_MASSAGE or not low <= level <= high:
            raise ValueError(f"Unsupported {zone} massage level {level}")
        await self._apply_massage_level(zone, level)

    async def _apply_massage_level(self, zone: str, level: int) -> None:
        base = {"head": HEAL_HEAD_MASSAGE, "foot": HEAL_FOOT_MASSAGE}.get(zone)
        if await self._write_key(HEAL_WAVE + level - 1 if base is None else base + level):
            # Only a written level moves the session, so +/- never steps from a phantom.
            setattr(self._session, zone, level)
            self.forward_controller_state_update(STATE_HEAL_MASSAGE[zone], level)

    async def _step_massage(self, zone: str, delta: int) -> None:
        """+/-: clamp, then send the level even when the clamp kept it."""
        self._require_massage_page()
        low, high = (1, HEAL_WAVE_MAX) if zone == "wave" else (0, HEAL_ZONE_MAX)
        level = getattr(self._session, zone) + delta
        await self._apply_massage_level(zone, min(high, max(low, level)))

    async def massage_head_up(self) -> None:
        await self._step_massage("head", 1)

    async def massage_head_down(self) -> None:
        await self._step_massage("head", -1)

    async def massage_foot_up(self) -> None:
        await self._step_massage("foot", 1)

    async def massage_foot_down(self) -> None:
        await self._step_massage("foot", -1)

    async def massage_wave_next(self) -> None:
        await self._step_massage("wave", 1)

    async def massage_wave_previous(self) -> None:
        await self._step_massage("wave", -1)

    async def massage_toggle(self) -> None:
        raise NotImplementedError("These apps have no massage toggle")

    async def massage_intensity_up(self) -> None:
        raise NotImplementedError("These apps have no combined massage step")

    async def massage_intensity_down(self) -> None:
        raise NotImplementedError("These apps have no combined massage step")

    async def massage_mode_step(self) -> None:
        raise NotImplementedError("These apps have no massage mode step")

    def get_massage_state(self) -> dict[str, Any]:
        session = self._session
        return {
            "head_intensity": session.head,
            "foot_intensity": session.foot,
            "wave_intensity": session.wave or None,
            "timer_mode": str(session.timer_minutes) if session.timer_minutes else None,
        }

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self._is_heal:
            return ()

        def number(zone: str, low: int, high: int) -> ControllerNumberSpec:
            async def set_level(ctrl: BedController, value: float) -> None:
                await ctrl.set_heal_massage_level(zone, int(value))  # type: ignore[attr-defined]

            return ControllerNumberSpec(
                key=STATE_HEAL_MASSAGE[zone],
                translation_key=f"massage_{zone}_intensity",
                state_key=STATE_HEAL_MASSAGE[zone],
                native_min_value=low,
                native_max_value=high,
                native_step=1,
                set_fn=set_level,
            )

        return (
            number("head", 0, HEAL_ZONE_MAX),
            number("foot", 0, HEAL_ZONE_MAX),
            number("wave", 1, HEAL_WAVE_MAX),
        )

    # ------------------------------------------------------------- settings
    def select_heal_setting(self, setting: str, option: str) -> None:
        """Change a Heal Every Night setting; it only remaps later presses (no write)."""
        options = HEAL_SETTING_OPTIONS.get(setting)
        if not self._is_heal or options is None or option not in options:
            raise ValueError(f"Unsupported Heal Every Night setting {setting}={option}")
        self._session.settings[setting] = option == options[1]
        self._coordinator.save_app_state(self)
        self.forward_controller_state_update(f"{ACTION_NAMESPACE}{setting}", option)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self._is_heal:
            return ()

        def select(setting: str) -> ControllerSelectSpec:
            async def apply(ctrl: BedController, option: str) -> None:
                ctrl.select_heal_setting(setting, option)  # type: ignore[attr-defined]

            return ControllerSelectSpec(
                key=f"{ACTION_NAMESPACE}{setting}",
                translation_key=f"{ACTION_NAMESPACE}{setting}",
                state_key=f"{ACTION_NAMESPACE}{setting}",
                options=HEAL_SETTING_OPTIONS[setting],
                select_fn=apply,
                local_select_fn=lambda option: self.select_heal_setting(setting, option),
            )

        return tuple(select(setting) for setting in HEAL_SETTING_OPTIONS)
