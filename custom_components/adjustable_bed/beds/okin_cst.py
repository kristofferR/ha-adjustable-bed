"""OKIN CSTProtocol bed controller implementation.

CSTProtocol uses a 14-byte command format with two separate 32-bit fields:
- Primary field (bytes 2-5): Motor control and several remote button actions
- Secondary field (bytes 6-9): Discrete light and massage-wave actions

Format: [0x0C, 0x02, motor[4], control[4], 0x00, 0x00, 0x00, 0x00]

Most command values are identical to existing OKIN UUID values, but the MFirm
app routes remote actions across both CST fields. Do not infer field placement
from the feature type alone.

Protocol and fixed product profiles come from the nine accepted Phase 4 cluster
011 reports. Known devices include Rize Sanctuary, Resident, Aviada, Bob,
Contempo, Carefree, Clarity II, MF900, and Support.

Uses standard OKIN service: 62741523-52f9-8864-b1ab-3b3a8d65950b
Requires BLE pairing before use (same as OkinUuidController).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from bleak.exc import BleakError

from ..const import (
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_CST_VARIANT_AVIADA,
    OKIN_CST_VARIANT_BOB,
    OKIN_CST_VARIANT_CAREFREE,
    OKIN_CST_VARIANT_CLARITY,
    OKIN_CST_VARIANT_CONTEMPO,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_RESIDENT,
    OKIN_CST_VARIANT_SANCTUARY,
    OKIN_CST_VARIANT_SUPPORT,
    VARIANT_AUTO,
)
from .base import BedController, MotorControlSpec
from .okin_protocol import build_cst_command

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_PRESET_REPEAT_COUNT = 6
_PRESET_REPEAT_DELAY_MS = 100
_BUTTON_PRESS_REPEAT_COUNT = 6
_BUTTON_PRESS_REPEAT_DELAY_MS = 100
_STOP_REPEAT_COUNT = 2
_STOP_REPEAT_DELAY_MS = 100


class CstMotorCommands:
    """Motor field command values (bytes 2-5)."""

    STOP = 0x00000000
    HEAD_UP = 0x00000001
    HEAD_DOWN = 0x00000002
    FOOT_UP = 0x00000004
    FOOT_DOWN = 0x00000008
    LUMBAR_UP = 0x00000010
    LUMBAR_DOWN = 0x00000020


class CstRemoteCommands:
    """Remote action command values.

    The CST app chooses the first or second 32-bit field per action. Call sites
    pass these values to build_cst_command() using the matching field.
    """

    STOP = 0x00000000
    FLAT = 0x08000000
    ZERO_G = 0x00001000
    LOUNGE = 0x00002000
    INCLINE = 0x00004000
    ANTI_SNORE = 0x00008000
    SAVE_ZERO_G = FLAT | ZERO_G
    SAVE_LOUNGE = FLAT | LOUNGE
    SAVE_INCLINE = FLAT | INCLINE
    LIGHT_TOGGLE = 0x00020000
    LIGHT_ON = 0x00000040
    LIGHT_OFF = 0x00000080
    MASSAGE_OFF = 0x02000000
    MASSAGE_INTENSITY = 0x00000C00
    MASSAGE_INTENSITY_MINUS = 0x01800000
    MASSAGE_WAVE_1 = 0x00080000
    MASSAGE_WAVE_2 = 0x00100000
    MASSAGE_WAVE_3 = 0x00200000
    MASSAGE_FULL_BODY = 0x00000100
    MASSAGE_HEAD_UP = 0x00000800
    MASSAGE_HEAD_DOWN = 0x00800000
    MASSAGE_FOOT_UP = 0x00000400
    MASSAGE_FOOT_DOWN = 0x01000000
    MASSAGE_TIMER_STEP = 0x00000200
    MEMORY_M = 0x00010000
    SAVE_MEMORY_M = FLAT | MEMORY_M


CstControlCommands = CstRemoteCommands


@dataclass(frozen=True)
class CstFields:
    """The two independently routed 32-bit fields in a CST frame."""

    primary: int = 0
    secondary: int = 0


@dataclass(frozen=True)
class CstMemorySlot:
    """A product profile's named recall/program pair."""

    name: str
    recall: int
    program: int


@dataclass(frozen=True)
class CstProfile:
    """Capabilities and product-specific command routing for one CST app."""

    key: str
    motors: tuple[str, ...]
    lounge: bool
    incline: bool
    memory_slots: tuple[CstMemorySlot, ...]
    lights: bool
    massage_style: Literal["none", "global", "zoned"]
    massage_toggle: CstFields | None = None
    massage_head_up: CstFields | None = None
    massage_head_down: CstFields | None = None
    massage_foot_up: CstFields | None = None
    massage_foot_down: CstFields | None = None
    massage_timer_step: CstFields | None = None


_MEMORY_ZERO_G = CstMemorySlot(
    "Zero Gravity", CstRemoteCommands.ZERO_G, CstRemoteCommands.SAVE_ZERO_G
)
_MEMORY_INCLINE = CstMemorySlot(
    "Incline", CstRemoteCommands.INCLINE, CstRemoteCommands.SAVE_INCLINE
)
_MEMORY_LOUNGE = CstMemorySlot(
    "Lounge", CstRemoteCommands.LOUNGE, CstRemoteCommands.SAVE_LOUNGE
)
_MEMORY_M = CstMemorySlot(
    "M", CstRemoteCommands.MEMORY_M, CstRemoteCommands.SAVE_MEMORY_M
)
_THREE_MEMORIES = (_MEMORY_ZERO_G, _MEMORY_INCLINE, _MEMORY_LOUNGE)

_ZONED_SANCTUARY = {
    "massage_head_up": CstFields(primary=CstRemoteCommands.MASSAGE_HEAD_UP),
    "massage_head_down": CstFields(primary=CstRemoteCommands.MASSAGE_HEAD_DOWN),
    "massage_foot_up": CstFields(primary=CstRemoteCommands.MASSAGE_FOOT_UP),
    "massage_foot_down": CstFields(primary=CstRemoteCommands.MASSAGE_FOOT_DOWN),
}
_ZONED_BOB = {
    **_ZONED_SANCTUARY,
    "massage_head_down": CstFields(
        primary=CstRemoteCommands.MASSAGE_HEAD_DOWN,
        secondary=CstRemoteCommands.MASSAGE_HEAD_DOWN,
    ),
    "massage_foot_down": CstFields(
        primary=CstRemoteCommands.MASSAGE_FOOT_DOWN,
        secondary=CstRemoteCommands.MASSAGE_FOOT_DOWN,
    ),
}
_ZONED_SUPPORT = {
    **_ZONED_BOB,
    "massage_foot_down": CstFields(secondary=CstRemoteCommands.MASSAGE_FOOT_DOWN),
}

_CST_PROFILES: dict[str, CstProfile] = {
    OKIN_CST_VARIANT_SANCTUARY: CstProfile(
        key=OKIN_CST_VARIANT_SANCTUARY,
        motors=("head", "feet"),
        lounge=True,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G, _MEMORY_LOUNGE),
        lights=True,
        massage_style="zoned",
        massage_toggle=CstFields(secondary=CstRemoteCommands.MASSAGE_FULL_BODY),
        **_ZONED_SANCTUARY,
    ),
    OKIN_CST_VARIANT_RESIDENT: CstProfile(
        key=OKIN_CST_VARIANT_RESIDENT,
        motors=("head", "feet"),
        lounge=True,
        incline=True,
        memory_slots=(*_THREE_MEMORIES, _MEMORY_M),
        lights=False,
        massage_style="zoned",
        massage_timer_step=CstFields(primary=CstRemoteCommands.MASSAGE_TIMER_STEP),
        **_ZONED_SANCTUARY,
    ),
    OKIN_CST_VARIANT_AVIADA: CstProfile(
        key=OKIN_CST_VARIANT_AVIADA,
        motors=("head", "feet", "lumbar"),
        lounge=True,
        incline=True,
        memory_slots=_THREE_MEMORIES,
        lights=True,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_BOB: CstProfile(
        key=OKIN_CST_VARIANT_BOB,
        motors=("head", "feet"),
        lounge=True,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G, _MEMORY_LOUNGE),
        lights=True,
        massage_style="zoned",
        massage_toggle=CstFields(secondary=CstRemoteCommands.MASSAGE_FULL_BODY),
        **_ZONED_BOB,
    ),
    OKIN_CST_VARIANT_CONTEMPO: CstProfile(
        key=OKIN_CST_VARIANT_CONTEMPO,
        motors=("head", "feet", "lumbar"),
        lounge=True,
        incline=True,
        memory_slots=_THREE_MEMORIES,
        lights=True,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_CAREFREE: CstProfile(
        key=OKIN_CST_VARIANT_CAREFREE,
        motors=("head", "feet"),
        lounge=False,
        incline=False,
        memory_slots=(_MEMORY_ZERO_G,),
        lights=True,
        massage_style="none",
    ),
    OKIN_CST_VARIANT_CLARITY: CstProfile(
        key=OKIN_CST_VARIANT_CLARITY,
        motors=("head", "feet"),
        lounge=True,
        incline=True,
        memory_slots=_THREE_MEMORIES,
        lights=True,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_MF900: CstProfile(
        key=OKIN_CST_VARIANT_MF900,
        motors=("head", "feet", "lumbar"),
        lounge=True,
        incline=True,
        memory_slots=_THREE_MEMORIES,
        lights=True,
        massage_style="global",
    ),
    OKIN_CST_VARIANT_SUPPORT: CstProfile(
        key=OKIN_CST_VARIANT_SUPPORT,
        motors=("head", "feet", "lumbar"),
        lounge=True,
        incline=True,
        memory_slots=_THREE_MEMORIES,
        lights=True,
        massage_style="zoned",
        **_ZONED_SUPPORT,
    ),
}


class OkinCstController(BedController):
    """Controller for OKIN CSTProtocol beds (Rize MF900, etc.).

    Uses 14-byte packets with separate motor and control fields.
    Requires BLE pairing before use.
    """

    def __init__(
        self, coordinator: AdjustableBedCoordinator, variant: str = VARIANT_AUTO
    ) -> None:
        """Initialize the OKIN CST controller."""
        super().__init__(coordinator)
        self._motor_state: dict[str, int] = {}
        self._massage_wave_index: int | None = None
        profile_key = OKIN_CST_VARIANT_MF900 if variant == VARIANT_AUTO else variant
        self._profile = _CST_PROFILES.get(
            profile_key, _CST_PROFILES[OKIN_CST_VARIANT_MF900]
        )

        _LOGGER.debug("OkinCstController initialized with profile %s", self._profile.key)

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return OKIMAT_WRITE_CHAR_UUID

    # Capability properties

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return self._profile.lounge

    @property
    def supports_preset_incline(self) -> bool:
        return self._profile.incline

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self._profile.memory_slots)

    @property
    def memory_slot_count(self) -> int:
        return len(self._profile.memory_slots)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self._profile.memory_slots)

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return tuple(slot.name for slot in self._profile.memory_slots)

    @property
    def supports_lights(self) -> bool:
        return self._profile.lights

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._profile.lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._profile.lights

    @property
    def supports_massage(self) -> bool:
        return self._profile.massage_style != "none"

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._profile.massage_toggle is not None

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_style == "global"

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_head_up is not None

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_foot_up is not None

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def massage_mode_step_is_timer(self) -> bool:
        return self._profile.massage_timer_step is not None

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self._profile.massage_timer_step is not None

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self._profile.motors

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose only the axes present in the selected product app."""
        specs = (
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                max_angle=45,
            ),
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                max_angle=30,
            ),
        )
        return tuple(spec for spec in specs if spec.key in self._profile.motors)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove aliases and axes absent from the selected product profile."""
        stale = {"back", "legs", "tilt"}
        if "lumbar" not in self._profile.motors:
            stale.add("lumbar")
        return frozenset(stale)

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        """Report the explicitly resolved fixed CST product profile."""
        return {
            "cst_profile": self._profile.key,
            "cst_motors": self._profile.motors,
            "cst_massage_style": self._profile.massage_style,
        }

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Subscribe to CST notifications for raw diagnostic capture."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot start CST notifications: not connected")
            return

        try:
            async with self._ble_lock:
                await client.start_notify(
                    OKIMAT_NOTIFY_CHAR_UUID,
                    self._handle_notification,
                )
        except BleakError as err:
            _LOGGER.debug("Could not start CST notifications: %s", err)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        """Forward CST notifications without interpreting them as positions."""
        self.forward_raw_notification(OKIMAT_NOTIFY_CHAR_UUID, bytes(data))

    async def stop_notify(self) -> None:
        """Stop the raw CST diagnostic notification subscription."""
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            async with self._ble_lock:
                await client.stop_notify(OKIMAT_NOTIFY_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not stop CST notifications: %s", err)

    # Motor movement helpers

    def _get_motor_command(self) -> int:
        """Calculate combined motor command from active motor states."""
        command = 0
        for value in self._motor_state.values():
            command |= value
        return command

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        """Move a motor or stop it."""
        if command_value is None or command_value == 0:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = command_value

        combined = self._get_motor_command()
        pulse_count, pulse_delay = self.motor_pulse_settings()

        try:
            if combined:
                await self.write_command(
                    build_cst_command(motor_value=combined),
                    repeat_count=pulse_count,
                    repeat_delay_ms=pulse_delay,
                )
        finally:
            self._motor_state.pop(motor, None)
            if not self._motor_state:
                await self._send_stop_sequence()

    async def _send_stop_sequence(self) -> None:
        """Send the app-style CST STOP sequence."""
        stop_event = asyncio.Event()
        for _ in range(_STOP_REPEAT_COUNT):
            await asyncio.sleep(_STOP_REPEAT_DELAY_MS / 1000)
            await self.write_command(build_cst_command(), cancel_event=stop_event)

    async def _send_repeated_command(
        self,
        *,
        motor_value: int = 0,
        control_value: int = 0,
        repeat_count: int,
        repeat_delay_ms: int,
    ) -> None:
        """Send a CST command with stop cleanup."""
        try:
            await self.write_command(
                build_cst_command(motor_value=motor_value, control_value=control_value),
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
            )
        finally:
            try:
                await self._send_stop_sequence()
            except (TimeoutError, BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP during CST cleanup", exc_info=True)

    async def _send_preset(self, motor_value: int) -> None:
        """Send a long-running preset recall command."""
        await self._send_repeated_command(
            motor_value=motor_value,
            repeat_count=_PRESET_REPEAT_COUNT,
            repeat_delay_ms=_PRESET_REPEAT_DELAY_MS,
        )

    async def _send_button_press(
        self, *, motor_value: int = 0, control_value: int = 0
    ) -> None:
        """Send a short app-style button press."""
        await self._send_repeated_command(
            motor_value=motor_value,
            control_value=control_value,
            repeat_count=_BUTTON_PRESS_REPEAT_COUNT,
            repeat_delay_ms=_BUTTON_PRESS_REPEAT_DELAY_MS,
        )

    # Motor control - Back/Head (primary)

    async def move_head_up(self) -> None:
        """Move head/back up."""
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head/back down."""
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head/back motor."""
        await self._move_motor("back", None)

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self._move_motor("back", None)

    # Motor control - Legs/Feet

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self._move_motor("legs", None)

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self._move_motor("legs", None)

    # Motor control - Lumbar

    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        await self._move_motor("lumbar", None)

    async def stop_all(self) -> None:
        """Stop all motors."""
        self._motor_state = {}
        await self._send_stop_sequence()

    # Presets

    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset(CstRemoteCommands.FLAT)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position."""
        await self._send_preset(CstRemoteCommands.ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position."""
        await self._send_preset(CstRemoteCommands.ANTI_SNORE)

    async def preset_lounge(self) -> None:
        """Go to lounge position."""
        await self._send_preset(CstRemoteCommands.LOUNGE)

    async def preset_incline(self) -> None:
        """Go to incline/TV position."""
        await self._send_preset(CstRemoteCommands.INCLINE)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to a user-programmable preset memory."""
        if 1 <= memory_num <= len(self._profile.memory_slots):
            await self._send_preset(self._profile.memory_slots[memory_num - 1].recall)
            return
        _LOGGER.warning(
            "Invalid memory number %d (valid: 1-%d)",
            memory_num,
            len(self._profile.memory_slots),
        )

    async def program_memory(self, memory_num: int) -> None:
        """Program the current position to a user-programmable preset memory."""
        if 1 <= memory_num <= len(self._profile.memory_slots):
            await self._send_button_press(
                motor_value=self._profile.memory_slots[memory_num - 1].program
            )
            return
        _LOGGER.warning(
            "Invalid memory number %d (valid: 1-%d)",
            memory_num,
            len(self._profile.memory_slots),
        )

    # Lights

    async def lights_on(self) -> None:
        """Turn on lights."""
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_ON)

    async def lights_off(self) -> None:
        """Turn off lights."""
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_OFF)

    async def lights_toggle(self) -> None:
        """Toggle lights."""
        await self._send_button_press(motor_value=CstRemoteCommands.LIGHT_TOGGLE)

    # Massage

    async def massage_off(self) -> None:
        """Turn massage off."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_OFF)

    async def massage_toggle(self) -> None:
        """Start full-body massage on profiles with the reachable voice action."""
        await self._send_profile_fields(self._profile.massage_toggle)

    async def massage_intensity_up(self) -> None:
        """Increase overall massage intensity."""
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_INTENSITY)

    async def massage_intensity_down(self) -> None:
        """Decrease overall massage intensity."""
        await self._send_button_press(
            motor_value=CstRemoteCommands.MASSAGE_INTENSITY_MINUS
        )

    async def massage_head_up(self) -> None:
        """Increase head-zone massage intensity."""
        await self._send_profile_fields(self._profile.massage_head_up)

    async def massage_head_down(self) -> None:
        """Decrease head-zone massage intensity."""
        await self._send_profile_fields(self._profile.massage_head_down)

    async def massage_foot_up(self) -> None:
        """Increase foot-zone massage intensity."""
        await self._send_profile_fields(self._profile.massage_foot_up)

    async def massage_foot_down(self) -> None:
        """Decrease foot-zone massage intensity."""
        await self._send_profile_fields(self._profile.massage_foot_down)

    async def _send_profile_fields(self, fields: CstFields | None) -> None:
        """Send a command proven for the selected profile."""
        if fields is None:
            raise NotImplementedError(
                f"Command is not supported by CST profile {self._profile.key}"
            )
        await self._send_button_press(
            motor_value=fields.primary,
            control_value=fields.secondary,
        )

    async def massage_mode_step(self) -> None:
        """Step the timer on Resident, otherwise cycle the three wave modes."""
        if self._profile.massage_timer_step is not None:
            await self._send_profile_fields(self._profile.massage_timer_step)
            return
        await self._send_next_wave(1)

    async def massage_wave_next(self) -> None:
        """Select the next direct wave on profiles that also need timer step."""
        await self._send_next_wave(1)

    async def massage_wave_previous(self) -> None:
        """Select the previous direct wave on profiles that also need timer step."""
        await self._send_next_wave(-1)

    async def _send_next_wave(self, direction: int) -> None:
        """Cycle the three directly addressable wave frames."""
        commands = (
            CstRemoteCommands.MASSAGE_WAVE_1,
            CstRemoteCommands.MASSAGE_WAVE_2,
            CstRemoteCommands.MASSAGE_WAVE_3,
        )
        if self._massage_wave_index is None:
            self._massage_wave_index = 0 if direction > 0 else len(commands) - 1
        else:
            self._massage_wave_index = (
                self._massage_wave_index + direction
            ) % len(commands)
        command = commands[self._massage_wave_index]
        await self._send_button_press(control_value=command)
