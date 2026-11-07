"""OKIN CSTProtocol bed controller implementation.

CSTProtocol uses a 14-byte command format with two separate 32-bit fields:
- Primary field (bytes 2-5): Motor control and several remote button actions
- Secondary field (bytes 6-9): Discrete light and massage-wave actions

Format: [0x0C, 0x02, motor[4], control[4], 0x00, 0x00, 0x00, 0x00]

Most command values are identical to existing OKIN UUID values, but the MFirm
app routes remote actions across both CST fields. Do not infer field placement
from the feature type alone.

Protocol and fixed product profiles come from the nine accepted APK Protocol Audit cluster
011 reports. Known devices include Rize Sanctuary, Resident, Aviada, Bob,
Contempo, Carefree, Clarity II, MF900, and Support.

Uses standard OKIN service: 62741523-52f9-8864-b1ab-3b3a8d65950b
Requires BLE pairing before use (same as OkinUuidController).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ..codec import okin_nframe as codec
from ..const import (
    CONF_BLE_BOND_ESTABLISHED,
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    OKIN_CST_VARIANTS,
    VARIANT_AUTO,
)
from ..controller_state import StateKey
from ..detection import is_okimat_bed_model
from ..furnimove_repair import CONF_OKIMAT_MODEL_ON_CST, async_refresh_furnimove_layout_issues
from ..profiles.okin_nframe import (
    CST_PROFILES,
    CstFields,
    CstMotorCommands,
    CstProduct,
    CstRemoteCommands,
    OkinNFrameProfile,
    Tap,
)
from .base import BedController, ControllerStateBinarySensorSpec, MotorControlSpec
from .builder import BuildContext

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _product(profile: OkinNFrameProfile) -> CstProduct:
    if profile.product is None:
        raise TypeError(f"{profile.key} is not a CST product profile")
    return profile.product


MEMORY_SAVE_RESPONSE_OBSERVED: Final = StateKey[bool]("memory_save_response_observed")


class OkinCstController(BedController):
    """Controller for OKIN CSTProtocol beds (Rize MF900, etc.).

    Uses 14-byte packets with separate motor and control fields.
    Pairing requirements and available controls vary by app profile.
    """

    def __init__(
        self, coordinator: AdjustableBedCoordinator, variant: str = VARIANT_AUTO
    ) -> None:
        super().__init__(coordinator)
        self._motor_state: dict[str, int] = {}
        self._massage_wave_index: int | None = None
        self._previous_status = 0
        self._pending_memory_save_code: int | None = None
        self._cleanup_stop_cancel_counter: int | None = None
        self._has_explicit_profile = variant in CST_PROFILES
        profile_key = OKIN_CST_VARIANT_MF900 if variant == VARIANT_AUTO else variant
        self._nframe_profile = CST_PROFILES.get(profile_key, CST_PROFILES[OKIN_CST_VARIANT_MF900])
        self._profile = _product(self._nframe_profile)
        self._memory_save_response_callback: Callable[[], None] | None = None
        if self._profile.memory_save_response_feedback:
            self.forward_controller_state_update(MEMORY_SAVE_RESPONSE_OBSERVED, False)

        _LOGGER.debug("OkinCstController initialized with profile %s", self._profile.key)

    @property
    def profile(self) -> OkinNFrameProfile:
        """The selected product's 96-bit profile: its words and timing."""
        return self._nframe_profile

    @property
    def control_characteristic_uuid(self) -> str:
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
    def supports_preset_reading(self) -> bool:
        return self._profile.reading

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
        return self._profile.lights and not self._profile.light_toggle_only

    @property
    def supports_massage(self) -> bool:
        return self._profile.massage_style != "none"

    @property
    def auto_enable_massage(self) -> bool:
        return self._has_explicit_profile and self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage and self._profile.massage_style != "increase_only"

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self._profile.massage_toggle is not None

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_style == "global"

    @property
    def supports_massage_intensity_up_control(self) -> bool:
        return self._profile.massage_style in {"global", "increase_only"}

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_head_up is not None

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self._profile.massage_foot_up is not None

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self._profile.massage_style in {"global", "zoned"}

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
    def requires_notification_channel(self) -> bool:
        return self._profile.memory_save_response_feedback

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self._profile.memory_save_response_feedback:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="memory_save_response_observed",
                translation_key="memory_save_response_observed",
                state_key=MEMORY_SAVE_RESPONSE_OBSERVED,
                icon="mdi:content-save-check-outline",
            ),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose only the axes present in the selected product app."""
        scheduler_resource = (
            "motor:*" if self._profile.key == OKIN_CST_VARIANT_NECTAR_MOVE else None
        )
        specs = (
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
                scheduler_resource=scheduler_resource,
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                max_angle=45,
                scheduler_resource=scheduler_resource,
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
        self._reset_memory_save_feedback()
        self._previous_status = 0
        client = self.client
        if client is None or not client.is_connected:
            if self.requires_notification_channel:
                raise ConnectionError("Cannot subscribe to Nectar Move notifications")
            _LOGGER.warning("Cannot start CST notifications: not connected")
            return

        try:
            async with self._ble_lock:
                await client.start_notify(
                    OKIMAT_NOTIFY_CHAR_UUID,
                    self._handle_notification,
                )
            if self._profile.memory_save_response_feedback:
                self._memory_save_response_callback = self._mark_memory_save_response_observed
        except BleakError as err:
            _LOGGER.debug("Could not start CST notifications: %s", err)
            if self.requires_notification_channel:
                raise

    def _handle_notification(self, _: object, data: bytearray) -> None:
        """Forward raw bytes and observe Nectar's pending-save status change."""
        self.forward_raw_notification(OKIMAT_NOTIFY_CHAR_UUID, bytes(data))
        if not self._profile.memory_save_response_feedback or len(data) <= 10:
            return

        status = data[10]
        if status >= 0x80:
            status -= 0x100
        if status == self._previous_status:
            return

        self._previous_status = status
        if (
            self._pending_memory_save_code is not None
            and self._memory_save_response_callback is not None
        ):
            self._pending_memory_save_code = None
            self._memory_save_response_callback()

    def _mark_memory_save_response_observed(self) -> None:
        """Publish an observed app response without claiming physical storage."""
        self.forward_controller_state_update(MEMORY_SAVE_RESPONSE_OBSERVED, True)

    def _reset_memory_save_feedback(self) -> None:
        """Clear response tracking at a new save or connection boundary."""
        self._pending_memory_save_code = None
        if self._profile.memory_save_response_feedback:
            self.forward_controller_state_update(MEMORY_SAVE_RESPONSE_OBSERVED, False)

    def on_disconnect(self) -> None:
        """Clear session-local notification and command state when the BLE link drops."""
        if self._profile.memory_save_response_feedback:
            self._reset_memory_save_feedback()
            self._previous_status = 0
            self._memory_save_response_callback = None
        self._cleanup_stop_cancel_counter = None
        self._motor_state.clear()

    async def stop_notify(self) -> None:
        """Stop the raw CST diagnostic notification subscription."""
        self._reset_memory_save_feedback()
        self._memory_save_response_callback = None
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            async with self._ble_lock:
                await client.stop_notify(OKIMAT_NOTIFY_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not stop CST notifications: %s", err)

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Keep the configured count; Nectar Move refreshes at the app's interval."""
        pulse_count, pulse_delay_ms = super().motor_pulse_settings()
        return pulse_count, self.profile.hold.repeat_ms or pulse_delay_ms

    # Motor movement helpers

    def _get_motor_command(self) -> int:
        command = 0
        for value in self._motor_state.values():
            command |= value
        return command

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        if self._profile.key == OKIN_CST_VARIANT_NECTAR_MOVE:
            if command_value is None:
                self._motor_state.pop(motor, None)
                await self._send_explicit_stop_sequence()
            else:
                await self._send_nectar_held_command(command_value)
            return

        if command_value is None or command_value == 0:
            self._motor_state.pop(motor, None)
        else:
            self._motor_state[motor] = command_value

        combined = self._get_motor_command()
        pulse_count, pulse_delay = self.motor_pulse_settings()

        try:
            if combined:
                await self.write_command(
                    codec.frame96(combined),
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
        for _ in range(self.profile.hold.releases):
            await asyncio.sleep(self.profile.hold.release_ms / 1000)
            await self.write_command(codec.frame96(0), cancel_event=stop_event)

    async def _send_stop_sequence_after_command(self) -> None:
        """Send cleanup STOPs and remember that an explicit STOP may follow."""
        await self._send_stop_sequence()
        self._cleanup_stop_cancel_counter = (
            self._coordinator._cancel_counter if self._coordinator.cancel_command.is_set() else None
        )

    async def _send_explicit_stop_sequence(self) -> None:
        """Avoid duplicating STOPs already sent by the canceled command's finally."""
        cleanup_cancel_counter = self._cleanup_stop_cancel_counter
        self._cleanup_stop_cancel_counter = None
        if (
            cleanup_cancel_counter is not None
            and cleanup_cancel_counter == self._coordinator._cancel_counter
        ):
            return
        await self._send_stop_sequence()

    async def _send_nectar_held_command(self, motor_value: int) -> None:
        """Refresh one Nectar Move axis for a bounded HA movement, then release.

        The app refreshes a held axis every 100 ms until release. HA movement
        commands are finite, so the configured pulse count bounds each one;
        the card's hold loop re-issues them while a control stays pressed.
        """
        pulse_count, refresh_delay_ms = self.motor_pulse_settings()
        self._cleanup_stop_cancel_counter = None
        try:
            await self.write_command(
                codec.frame96(motor_value),
                repeat_count=pulse_count,
                repeat_delay_ms=refresh_delay_ms,
            )
        finally:
            try:
                await self._send_stop_sequence_after_command()
            except TimeoutError, BleakError, ConnectionError:
                _LOGGER.debug("Failed to send Nectar Move STOP during cleanup", exc_info=True)

    async def _send_nectar_tap(self, *, motor_value: int = 0, control_value: int = 0) -> None:
        """Map a stateless HA press to one command and the bounded STOP pair."""
        self._cleanup_stop_cancel_counter = None
        try:
            await self.write_command(codec.frame96(motor_value, control_value))
        finally:
            try:
                await self._send_stop_sequence_after_command()
            except TimeoutError, BleakError, ConnectionError:
                _LOGGER.debug("Failed to send Nectar Move STOP during tap cleanup", exc_info=True)

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
                codec.frame96(motor_value, control_value),
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
            )
        finally:
            try:
                await self._send_stop_sequence()
            except (TimeoutError, BleakError, ConnectionError):
                _LOGGER.debug("Failed to send STOP during CST cleanup", exc_info=True)

    @staticmethod
    def _press_timing(tap: Tap | None) -> Tap:
        if tap is None:
            raise TypeError("CST profiles always define their press timing")
        return tap

    async def _send_preset(self, motor_value: int) -> None:
        """Send a long-running preset recall command."""
        if self._profile.key == OKIN_CST_VARIANT_NECTAR_MOVE:
            self._pending_memory_save_code = None
            await self._send_nectar_tap(motor_value=motor_value)
            return
        recall = self._press_timing(self.profile.recall)
        await self._send_repeated_command(
            motor_value=motor_value,
            repeat_count=recall.repeats,
            repeat_delay_ms=recall.repeat_ms,
        )

    async def _send_button_press(
        self, *, motor_value: int = 0, control_value: int = 0
    ) -> None:
        """Send a short app-style button press."""
        if self._profile.key == OKIN_CST_VARIANT_NECTAR_MOVE:
            await self._send_nectar_tap(
                motor_value=motor_value,
                control_value=control_value,
            )
            return
        await self._send_repeated_command(
            motor_value=motor_value,
            control_value=control_value,
            repeat_count=self.profile.tap.repeats,
            repeat_delay_ms=self.profile.tap.repeat_ms,
        )

    # Motor control - Back/Head (primary)

    async def move_head_up(self) -> None:
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_head_down(self) -> None:
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_head_stop(self) -> None:
        await self._move_motor("back", None)

    async def move_back_up(self) -> None:
        await self._move_motor("back", CstMotorCommands.HEAD_UP)

    async def move_back_down(self) -> None:
        await self._move_motor("back", CstMotorCommands.HEAD_DOWN)

    async def move_back_stop(self) -> None:
        await self._move_motor("back", None)

    # Motor control - Legs/Feet

    async def move_legs_up(self) -> None:
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_legs_down(self) -> None:
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_legs_stop(self) -> None:
        await self._move_motor("legs", None)

    async def move_feet_up(self) -> None:
        await self._move_motor("legs", CstMotorCommands.FOOT_UP)

    async def move_feet_down(self) -> None:
        await self._move_motor("legs", CstMotorCommands.FOOT_DOWN)

    async def move_feet_stop(self) -> None:
        await self._move_motor("legs", None)

    # Motor control - Lumbar

    async def move_lumbar_up(self) -> None:
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_UP)

    async def move_lumbar_down(self) -> None:
        await self._move_motor("lumbar", CstMotorCommands.LUMBAR_DOWN)

    async def move_lumbar_stop(self) -> None:
        await self._move_motor("lumbar", None)

    async def stop_all(self) -> None:
        self._motor_state = {}
        if self._profile.key == OKIN_CST_VARIANT_NECTAR_MOVE:
            await self._send_explicit_stop_sequence()
            return
        await self._send_stop_sequence()

    # Presets

    async def preset_flat(self) -> None:
        await self._send_preset(CstRemoteCommands.FLAT)

    async def preset_zero_g(self) -> None:
        await self._send_preset(CstRemoteCommands.ZERO_G)

    async def preset_anti_snore(self) -> None:
        await self._send_preset(CstRemoteCommands.ANTI_SNORE)

    async def preset_lounge(self) -> None:
        await self._send_preset(CstRemoteCommands.LOUNGE)

    async def preset_reading(self) -> None:
        """Go to the Nectar Move app's Reading position."""
        await self._send_preset(CstRemoteCommands.READING)

    async def preset_incline(self) -> None:
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
            if self._profile.memory_save_response_feedback:
                self._reset_memory_save_feedback()
                self._pending_memory_save_code = 3 if memory_num == 1 else 5
                try:
                    await self._send_button_press(
                        motor_value=self._profile.memory_slots[memory_num - 1].program
                    )
                    if self._coordinator.cancel_command.is_set():
                        self._reset_memory_save_feedback()
                except Exception, asyncio.CancelledError:
                    self._reset_memory_save_feedback()
                    raise
                return
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
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_ON)

    async def lights_off(self) -> None:
        await self._send_button_press(control_value=CstRemoteCommands.LIGHT_OFF)

    async def lights_toggle(self) -> None:
        await self._send_button_press(motor_value=CstRemoteCommands.LIGHT_TOGGLE)

    # Massage

    async def massage_off(self) -> None:
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_OFF)

    async def massage_toggle(self) -> None:
        """Start full-body massage on profiles with the reachable voice action."""
        await self._send_profile_fields(self._profile.massage_toggle)

    async def massage_intensity_up(self) -> None:
        await self._send_button_press(motor_value=CstRemoteCommands.MASSAGE_INTENSITY)

    async def massage_intensity_down(self) -> None:
        await self._send_button_press(
            motor_value=CstRemoteCommands.MASSAGE_INTENSITY_MINUS
        )

    async def massage_head_up(self) -> None:
        await self._send_profile_fields(self._profile.massage_head_up)

    async def massage_head_down(self) -> None:
        await self._send_profile_fields(self._profile.massage_head_down)

    async def massage_foot_up(self) -> None:
        await self._send_profile_fields(self._profile.massage_foot_up)

    async def massage_foot_down(self) -> None:
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
        if not self.supports_massage_wave_direction_control:
            raise NotImplementedError(
                f"Command is not supported by CST profile {self._profile.key}"
            )
        await self._send_next_wave(1)

    async def massage_wave_previous(self) -> None:
        """Select the previous direct wave on profiles that also need timer step."""
        if not self.supports_massage_wave_direction_control:
            raise NotImplementedError(
                f"Command is not supported by CST profile {self._profile.key}"
            )
        await self._send_next_wave(-1)

    async def _send_next_wave(self, direction: int) -> None:
        """Cycle the three directly addressable wave frames."""
        if not self.supports_massage:
            raise NotImplementedError(
                f"Command is not supported by CST profile {self._profile.key}"
            )
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


def _record_okimat_model(ctx: BuildContext) -> None:
    """Offer the route repair when an OKIMAT drive is configured as Okin CST (#555)."""
    coordinator = ctx.coordinator
    data = ctx.data
    if not is_okimat_bed_model(ctx.ble_model) or data.get(CONF_OKIMAT_MODEL_ON_CST) == ctx.ble_model:
        return
    # Internal write: keep this link instead of reloading the entry.
    coordinator._begin_internal_entry_update(bool(data.get(CONF_BLE_BOND_ESTABLISHED, False)))
    # Full data: a paired side's persist callback drops bond keys it is not sent.
    coordinator._async_persist_config({**data, CONF_OKIMAT_MODEL_ON_CST: ctx.ble_model})
    hass = coordinator.hass
    if (entry := hass.config_entries.async_get_entry(coordinator.entry.entry_id)) is not None:
        async_refresh_furnimove_layout_issues(hass, entry)


async def build_controller(ctx: BuildContext) -> OkinCstController:
    """Build the controller for the selected profile; a live OKIMAT drive offers its repair."""
    if ctx.client is not None:
        _record_okimat_model(ctx)
    variant = ctx.variant or VARIANT_AUTO
    if variant not in OKIN_CST_VARIANTS:
        _LOGGER.warning("Unknown Okin CST profile %s, using auto", variant)
        variant = VARIANT_AUTO
    return OkinCstController(ctx.coordinator, variant=variant)
