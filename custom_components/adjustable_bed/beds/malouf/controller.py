"""Malouf bed controller implementations.

Reverse-engineered from Malouf Base app v2.4.3; verified against a fresh
decompile of Lucid Base v1.3.3 (com.lucid.bedbase, shared
com.malouf.adjustablebasebluetooth library) on 2026-07-10.

Malouf beds use two distinct protocols:
- NEW_OKIN: 8-byte ``05 02`` frames via Nordic UART, advertises unique service UUID.
  It is the ``NEW_OKIN`` profile over the Malouf codec (``codec/malouf.py``).
- LEGACY_OKIN: 9-byte commands with checksum via FFE5 service

Both protocols share the same command values but differ in encoding.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ...codec import malouf as malouf_codec
from ...const import (
    CONF_MALOUF_LAYOUT,
    CONF_MALOUF_MEMORY_SLOTS,
    MALOUF_LAYOUT_AUTO,
    MALOUF_LAYOUT_FOUR_MOTOR,
    MALOUF_LAYOUT_HEAD_TILT,
    MALOUF_LAYOUT_HILO,
    MALOUF_LAYOUT_LUMBAR,
    MALOUF_LAYOUT_TWO_MOTOR,
    MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID,
    MALOUF_MEMORY_SLOTS_AUTO,
)
from ...profiles import keeson as keeson_profiles
from ...profiles.malouf import NEW_OKIN
from ..base import BedController, MotorControlSpec

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class MaloufCommands:
    """Malouf command constants (32-bit values).

    These values are shared by both NEW_OKIN and LEGACY_OKIN protocols.
    The encoding differs but the command semantics are identical.
    """

    # Motors
    HEAD_UP = 0x1
    HEAD_DOWN = 0x2
    FOOT_UP = 0x4
    FOOT_DOWN = 0x8
    HEAD_TILT_UP = 0x10
    HEAD_TILT_DOWN = 0x20
    LUMBAR_UP = 0x40
    LUMBAR_DOWN = 0x80
    DUAL_UP = 0x5  # HEAD_UP | FOOT_UP
    DUAL_DOWN = 0xA  # HEAD_DOWN | FOOT_DOWN
    STOP = 0x0

    # Presets
    ALL_FLAT = 0x8000000
    ZERO_G = 0x1000
    LOUNGE = 0x2000
    ANTI_SNORE = 0x8000
    TV_READ = 0x4000
    MEMORY_1 = 0x10000
    MEMORY_2 = 0x40000

    # Memory programming (hold-to-save). The app emulates holding the
    # remote's memory button: it streams the save command at the protocol's
    # repeat interval for the full repeat window. Slot 1 reuses the recall
    # value (the sustained stream is what signals "save"); beds named
    # "Smartbed238" use a dedicated value with the save bit set.
    SAVE_MEMORY_1 = 0x10000
    SAVE_MEMORY_1_SMARTBED238 = 0x80010000
    SAVE_MEMORY_2 = 0x80040000

    # Lights & Massage
    LIGHT_SWITCH = 0x20000
    MASSAGE_HEAD = 0x800
    MASSAGE_FOOT = 0x400
    MASSAGE_HEAD_MINUS = 0x800000
    MASSAGE_FOOT_MINUS = 0x1000000
    MASSAGE_TIMER = 0x200
    MASSAGE_OFF = 0x2000000

    # Hi-Lo beds with two independent lift columns expose column motors as
    # "tilt" (head end) and "lumbar" (foot end). Raise/lower whole-bed
    # movement is both columns moving together.
    BED_HEIGHT_UP = HEAD_TILT_UP | LUMBAR_UP
    BED_HEIGHT_DOWN = HEAD_TILT_DOWN | LUMBAR_DOWN


def _malouf_motor_control_specs(layout: str) -> tuple[MotorControlSpec, ...]:
    """Return entities for the configured physical actuator layout."""
    specs = [
        MotorControlSpec(
            key="back",
            translation_key="back",
            open_fn=lambda ctrl: ctrl.move_back_up(),
            close_fn=lambda ctrl: ctrl.move_back_down(),
            stop_fn=lambda ctrl: ctrl.move_back_stop(),
        ),
        MotorControlSpec(
            key="legs",
            translation_key="legs",
            open_fn=lambda ctrl: ctrl.move_legs_up(),
            close_fn=lambda ctrl: ctrl.move_legs_down(),
            stop_fn=lambda ctrl: ctrl.move_legs_stop(),
            max_angle=45,
        ),
    ]
    if layout in {MALOUF_LAYOUT_HEAD_TILT, MALOUF_LAYOUT_FOUR_MOTOR}:
        specs.append(
            MotorControlSpec(
                key="tilt",
                translation_key="tilt",
                open_fn=lambda ctrl: ctrl.move_tilt_up(),
                close_fn=lambda ctrl: ctrl.move_tilt_down(),
                stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                max_angle=45,
            )
        )
    if layout in {MALOUF_LAYOUT_LUMBAR, MALOUF_LAYOUT_FOUR_MOTOR}:
        specs.append(
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                max_angle=30,
            )
        )
    if layout == MALOUF_LAYOUT_HILO:
        specs.extend(
            (
                MotorControlSpec(
                    key="tilt",
                    translation_key="head_end_tilt",
                    open_fn=lambda ctrl: ctrl.move_tilt_up(),
                    close_fn=lambda ctrl: ctrl.move_tilt_down(),
                    stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                    max_angle=45,
                ),
                MotorControlSpec(
                    key="lumbar",
                    translation_key="foot_end_tilt",
                    open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                    close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                    stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                    max_angle=30,
                ),
                MotorControlSpec(
                    key="bed_height",
                    translation_key="bed_height",
                    open_fn=lambda ctrl: ctrl.move_bed_height_up(),
                    close_fn=lambda ctrl: ctrl.move_bed_height_down(),
                    stop_fn=lambda ctrl: ctrl.move_bed_height_stop(),
                ),
            )
        )
    return tuple(specs)


def _resolve_malouf_layout(coordinator: AdjustableBedCoordinator) -> str:
    """Resolve an actuator layout without using a retail model as a protocol."""
    configured: str = coordinator.entry.data.get(CONF_MALOUF_LAYOUT, MALOUF_LAYOUT_AUTO)
    if configured != MALOUF_LAYOUT_AUTO:
        return configured
    if coordinator.motor_count <= 2:
        return MALOUF_LAYOUT_TWO_MOTOR
    if coordinator.motor_count == 3:
        return MALOUF_LAYOUT_HEAD_TILT
    return MALOUF_LAYOUT_FOUR_MOTOR


def _resolve_malouf_memory_slots(coordinator: AdjustableBedCoordinator, layout: str) -> int:
    """Resolve memory capacity independently from command protocol."""
    configured = int(coordinator.entry.data.get(CONF_MALOUF_MEMORY_SLOTS, MALOUF_MEMORY_SLOTS_AUTO))
    if configured != MALOUF_MEMORY_SLOTS_AUTO:
        return configured
    return 1 if layout == MALOUF_LAYOUT_TWO_MOTOR else 2


def _save_memory_command(memory_num: int, device_name: str | None) -> int | None:
    """Return the hold-to-save command value for a memory slot.

    Matches the app's setMemory1/setMemory2 handling: slot 1 uses the recall
    value (or the save-bit variant on beds named "Smartbed238"), slot 2 always
    carries the save bit.
    """
    smartbed238 = bool(device_name) and "smartbed238" in device_name.lower()
    if memory_num == 1:
        return (
            MaloufCommands.SAVE_MEMORY_1_SMARTBED238
            if smartbed238
            else MaloufCommands.SAVE_MEMORY_1
        )
    if memory_num == 2:
        return MaloufCommands.SAVE_MEMORY_2
    return None


class MaloufNewOkinController(BedController):
    """Malouf NEW_OKIN route: ``05 02`` key-word frames over Nordic UART.

    The bed advertises service 01000001-0000-1000-8000-00805f9b34fb. Frames come
    from ``codec/malouf.py``; words, recall and save timing from the ``NEW_OKIN``
    profile in ``profiles/malouf.py``. See ``docs/beds/malouf.md``.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Malouf NEW_OKIN controller."""
        super().__init__(coordinator)
        self.profile = NEW_OKIN

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return malouf_codec.TRANSPORTS[self.profile.transport].command_characteristic

    def _frame(self, action: str) -> bytes:
        return malouf_codec.command(self.profile.transport, self.profile.words[action])

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return self._layout in {MALOUF_LAYOUT_LUMBAR, MALOUF_LAYOUT_FOUR_MOTOR, MALOUF_LAYOUT_HILO}

    @property
    def has_tilt_support(self) -> bool:
        return self._layout in {
            MALOUF_LAYOUT_HEAD_TILT,
            MALOUF_LAYOUT_FOUR_MOTOR,
            MALOUF_LAYOUT_HILO,
        }

    @property
    def has_bed_height_support(self) -> bool:
        return self._layout == MALOUF_LAYOUT_HILO

    @property
    def supports_lights(self) -> bool:
        """Return True - these beds support lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only toggle control available."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return whether at least one memory position is configured."""
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        """Return the configured physical remote's memory capacity."""
        return _resolve_malouf_memory_slots(self._coordinator, self._layout)

    @property
    def supports_memory_programming(self) -> bool:
        """Return True; the official app programs memory by a timed long press."""
        return self.memory_slot_count > 0

    @property
    def _layout(self) -> str:
        """Return the resolved physical actuator layout."""
        return _resolve_malouf_layout(self._coordinator)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return controls for the selected physical actuator layout."""
        return _malouf_motor_control_specs(self._layout)

    async def _send_stop(self) -> None:
        await self.write_command(self._frame("stop"), cancel_event=asyncio.Event())

    async def _move_with_stop(self, command: bytes) -> None:
        """Repeat a movement frame at the pulse settings, then always send STOP."""
        try:
            pulse_count, pulse_delay = self.motor_pulse_settings()
            # A leased hold (#483) refreshes until its lease ends.
            pulse_count = self.leased_hold_refreshes(pulse_delay) or pulse_count
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    async def _move(self, action: str) -> None:
        await self._move_with_stop(self._frame(action))

    # Motor control methods
    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        await self._move("foot_up")

    async def move_feet_down(self) -> None:
        await self._move("foot_down")

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    async def move_tilt_up(self) -> None:
        await self._move("tilt_up")

    async def move_tilt_down(self) -> None:
        await self._move("tilt_down")

    async def move_tilt_stop(self) -> None:
        await self._send_stop()

    async def move_bed_height_up(self) -> None:
        """Raise entire bed by lifting both head and foot columns."""
        await self._move("bed_height_up")

    async def move_bed_height_down(self) -> None:
        """Lower entire bed by dropping both head and foot columns."""
        await self._move("bed_height_down")

    async def move_bed_height_stop(self) -> None:
        await self._send_stop()

    async def stop_all(self) -> None:
        await self._send_stop()

    # Preset methods
    async def _send_preset(self, action: str) -> None:
        """Send a preset frame as the profile's recall, then STOP."""
        recall = self.profile.recall
        await self.write_command(self._frame(action), repeat_count=recall.repeats)
        try:
            await self._send_stop()
        except BleakError, ConnectionError:
            _LOGGER.debug("Failed to send STOP after preset", exc_info=True)

    async def preset_flat(self) -> None:
        await self._send_preset("flat")

    async def preset_zero_g(self) -> None:
        await self._send_preset("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._send_preset("anti_snore")

    async def preset_tv(self) -> None:
        await self._send_preset("tv")

    async def preset_lounge(self) -> None:
        await self._send_preset("lounge")

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning("Memory slot %d not supported on this Malouf layout", memory_num)
            return
        if (action := f"memory_{memory_num}") not in self.profile.words:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)
            return
        await self._send_preset(action)

    async def program_memory(self, memory_num: int) -> None:
        """Program memory with the official app's hold-to-save stream."""
        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning("Memory slot %d not supported on this Malouf layout", memory_num)
            return
        if memory_num not in self.profile.save_words.slots:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)
            return
        word = self.profile.save_words.word(memory_num, self._coordinator.ble_device_name)
        save = self.profile.save
        # The APK schedules the first write after one interval. Its final
        # "stopCommand" string is not recognized by the dispatcher, so no STOP
        # packet is actually emitted.
        await asyncio.sleep(save.interval_ms / 1000)
        await self.write_command(
            malouf_codec.command(self.profile.transport, word),
            repeat_count=save.repeats,
            repeat_delay_ms=save.interval_ms,
        )

    # Light control (toggle only)
    async def lights_toggle(self) -> None:
        await self.write_command(self._frame("light"))

    async def lights_on(self) -> None:
        await self.lights_toggle()

    async def lights_off(self) -> None:
        await self.lights_toggle()

    # Massage control
    async def massage_head_toggle(self) -> None:
        await self.write_command(self._frame("massage_head"))

    async def massage_foot_toggle(self) -> None:
        await self.write_command(self._frame("massage_foot"))

    async def massage_head_up(self) -> None:
        await self.write_command(self._frame("massage_head"))

    async def massage_head_down(self) -> None:
        await self.write_command(self._frame("massage_head_minus"))

    async def massage_foot_up(self) -> None:
        await self.write_command(self._frame("massage_foot"))

    async def massage_foot_down(self) -> None:
        await self.write_command(self._frame("massage_foot_minus"))

    async def massage_off(self) -> None:
        await self.write_command(self._frame("massage_off"))

    async def massage_toggle(self) -> None:
        """Step the massage timer."""
        await self.write_command(self._frame("massage_timer_step"))


class MaloufLegacyOkinController(BedController):
    """Controller for Malouf beds using LEGACY_OKIN protocol.

    Protocol characteristics:
    - Service: 0000ffe5-0000-1000-8000-00805f9b34fb
    - Write characteristic: 0000ffe9-0000-1000-8000-00805f9b34fb
    - Command format: the nine-byte Keeson E6 frame, side byte 0x00
      (``profiles/keeson.py`` MALOUF_LEGACY_OKIN)
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Malouf LEGACY_OKIN controller."""
        super().__init__(coordinator)
        self.profile = keeson_profiles.MALOUF_LEGACY_OKIN
        _LOGGER.debug("MaloufLegacyOkinController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return MALOUF_LEGACY_OKIN_WRITE_CHAR_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return self._layout in {MALOUF_LAYOUT_LUMBAR, MALOUF_LAYOUT_FOUR_MOTOR, MALOUF_LAYOUT_HILO}

    @property
    def has_tilt_support(self) -> bool:
        return self._layout in {
            MALOUF_LAYOUT_HEAD_TILT,
            MALOUF_LAYOUT_FOUR_MOTOR,
            MALOUF_LAYOUT_HILO,
        }

    @property
    def has_bed_height_support(self) -> bool:
        return self._layout == MALOUF_LAYOUT_HILO

    @property
    def supports_lights(self) -> bool:
        """Return True - these beds support lighting."""
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return False - only toggle control available."""
        return False

    @property
    def supports_memory_presets(self) -> bool:
        """Return whether at least one memory position is configured."""
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        """Return the configured physical remote's memory capacity."""
        return _resolve_malouf_memory_slots(self._coordinator, self._layout)

    @property
    def supports_memory_programming(self) -> bool:
        """Return True; the official app programs memory by a timed long press."""
        return self.memory_slot_count > 0

    @property
    def _layout(self) -> str:
        """Return the resolved physical actuator layout."""
        return _resolve_malouf_layout(self._coordinator)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return controls for the selected physical actuator layout."""
        return _malouf_motor_control_specs(self._layout)

    def _build_command(self, command_value: int) -> bytes:
        """Build a nine-byte E6 frame through the Keeson codec (side byte ``00``)."""
        return keeson_profiles.encode(self.profile, command_value & 0xFFFFFFFF)

    async def _move_with_stop(self, command_value: int) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Execute a movement command and always send STOP at the end."""
        command = self._build_command(command_value)
        try:
            pulse_delay = self._coordinator.motor_pulse_delay_ms
            # A leased hold (#483) refreshes until its lease ends.
            pulse_count = (
                self.leased_hold_refreshes(pulse_delay) or self._coordinator.motor_pulse_count
            )
            await self.write_command(command, repeat_count=pulse_count, repeat_delay_ms=pulse_delay)
        finally:
            try:
                await self.write_command(
                    self._build_command(MaloufCommands.STOP),
                    cancel_event=asyncio.Event(),
                )
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP command during cleanup", exc_info=True)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        await self._move_with_stop(MaloufCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down."""
        await self._move_with_stop(MaloufCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back movement."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up (same as feet)."""
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        """Move legs down (same as feet)."""
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        """Stop legs movement."""
        await self.move_feet_stop()

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_with_stop(MaloufCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_with_stop(MaloufCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Lumbar control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_with_stop(MaloufCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_with_stop(MaloufCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Tilt control
    async def move_tilt_up(self) -> None:
        """Move tilt up."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Move tilt down."""
        await self._move_with_stop(MaloufCommands.HEAD_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop tilt movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Bed height (Hi-Lo) control
    async def move_bed_height_up(self) -> None:
        """Raise entire bed by lifting both head and foot columns."""
        await self._move_with_stop(MaloufCommands.BED_HEIGHT_UP)

    async def move_bed_height_down(self) -> None:
        """Lower entire bed by dropping both head and foot columns."""
        await self._move_with_stop(MaloufCommands.BED_HEIGHT_DOWN)

    async def move_bed_height_stop(self) -> None:
        """Stop Hi-Lo movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    async def stop_all(self) -> None:
        """Stop all movement."""
        await self.write_command(
            self._build_command(MaloufCommands.STOP), cancel_event=asyncio.Event()
        )

    # Preset methods
    async def _send_preset(self, command_value: int) -> None:
        """Queue the same preset command three times.

        LEGACY_OKIN requires triple-send for reliable preset reception.
        No STOP is sent after presets (APK sets shouldSendStopAfterPreset=false).
        """
        await self.write_command(
            self._build_command(command_value), repeat_count=3, repeat_delay_ms=0
        )

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset(MaloufCommands.ALL_FLAT)

    async def preset_zero_g(self) -> None:
        """Go to zero-G position."""
        await self._send_preset(MaloufCommands.ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._send_preset(MaloufCommands.ANTI_SNORE)

    async def preset_tv(self) -> None:
        """Go to TV/reading position."""
        await self._send_preset(MaloufCommands.TV_READ)

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self._send_preset(MaloufCommands.LOUNGE)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning("Memory slot %d not supported on this Malouf layout", memory_num)
            return
        commands = {
            1: MaloufCommands.MEMORY_1,
            2: MaloufCommands.MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self._send_preset(command)
        else:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program memory using the official app's 85 x 150 ms hold sequence."""
        if memory_num < 1 or memory_num > self.memory_slot_count:
            _LOGGER.warning("Memory slot %d not supported on this Malouf layout", memory_num)
            return
        command_value = _save_memory_command(memory_num, self._coordinator.ble_device_name)
        if command_value is None:
            _LOGGER.warning("Memory slot %d not supported on Malouf beds", memory_num)
            return
        # Match the APK's delayed first write and exact repeat count. The APK's
        # trailing "stopCommand" is a dead string, not a STOP transmission.
        await asyncio.sleep(0.15)
        await self.write_command(
            self._build_command(command_value), repeat_count=85, repeat_delay_ms=150
        )

    # Light control
    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self.write_command(self._build_command(MaloufCommands.LIGHT_SWITCH))

    async def lights_on(self) -> None:
        """Turn on lights (toggle only)."""
        await self.lights_toggle()

    async def lights_off(self) -> None:
        """Turn off lights (toggle only)."""
        await self.lights_toggle()

    # Massage control
    async def massage_head_toggle(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_foot_toggle(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_HEAD_MINUS))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_FOOT_MINUS))

    async def massage_off(self) -> None:
        """Turn off massage."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_OFF))

    async def massage_toggle(self) -> None:
        """Toggle massage timer."""
        await self.write_command(self._build_command(MaloufCommands.MASSAGE_TIMER))
