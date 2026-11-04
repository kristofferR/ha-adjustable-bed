"""Controller for the FFE1/11-byte adjustable-bed protocol family.

Accepted APK analyses prove several overlapping device-name routes with
different motor and accessory surfaces.  Profiles keep those capabilities
separate instead of exposing the historical union to every bed.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Collection
from datetime import datetime
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..codec import ff_frame as codec
from ..const import SOLACE_CHAR_UUID
from ..execution import LATCHED_MAX_HOLD_MS, leased_hold_ms
from ..profiles.ff_frame import (
    SolaceCommands,
    SolaceProfile,
    resolve_solace_profile,
    solace_query_family,
)
from .base import (
    BedController,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_SOLACE_ALARM_MODES = {"zero_g": 0x01, "memory_1": 0x02, "no_action": 0x03}
_SOLACE_ALARM_SOUNDS = {
    "none": 0x00,
    "alarm": 0x01,
    "music_1": 0x11,
    "music_2": 0x12,
    "music_3": 0x13,
    "music_4": 0x14,
    "music_5": 0x15,
}
# Cover method stem and maximum angle for each axis a profile can list.
_AXES = {
    "back": ("back", 68),
    "legs": ("legs", 45),
    "head": ("head", 68),
    "hip": ("hip", 68),
    "lumbar": ("lumbar", 30),
    "bed_height": ("lift", 68),
    "tilt": ("tilt", 45),
}
__all__ = ["SolaceCommands", "SolaceController", "SolaceProfile", "resolve_solace_profile"]


def build_solace_clock_command(now: datetime) -> bytes:
    """Build the MotionFlex startup clock-sync frame."""
    return codec.clock(now, now.isoweekday())


def build_solace_alarm_command(
    *,
    enabled: bool,
    hour: int,
    minute: int,
    weekdays: Collection[int],
    mode: str,
    massage: bool,
    sound: str,
) -> bytes:
    """Build the MotionFlex alarm frame from user-facing values."""
    weekday_mask = 0
    for weekday in weekdays:
        weekday_mask |= 1 << weekday
    return codec.alarm(
        switch=0x01 if enabled else 0xA1,
        hour=hour,
        minute=minute,
        weekday_mask=weekday_mask,
        repeat=bool(weekdays),
        mode=_SOLACE_ALARM_MODES[mode],
        massage=massage,
        sound=_SOLACE_ALARM_SOUNDS[sound],
    )


class SolaceController(BedController):
    """Controller for Solace beds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the Solace controller."""
        super().__init__(coordinator)
        self._query_task: asyncio.Task[None] | None = None
        _LOGGER.debug("SolaceController initialized")

    @property
    def profile(self) -> SolaceProfile:
        """Return the profile for the latest observed BLE name."""
        return resolve_solace_profile(self._coordinator.ble_device_name)

    @property
    def protocol_diagnostics(self) -> dict[str, str]:
        """Expose the selected evidence profile in support bundles."""
        return {
            "solace_profile": self.profile.key,
            "solace_query_family": self._query_family or "none",
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        """Expose the result returned by MotionFlex audio-volume queries."""
        if not self.supports_solace_audio:
            return ()
        return (
            ControllerStateSensorSpec(
                key="solace_audio_volume",
                translation_key="solace_audio_volume",
                state_key="solace_audio_volume",
                icon="mdi:volume-high",
            ),
        )

    @property
    def controller_state_binary_sensor_specs(
        self,
    ) -> tuple[ControllerStateBinarySensorSpec, ...]:
        """Expose the decoded MotionFlex alarm reply and its configuration."""
        if not self.supports_solace_alarm:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key="solace_alarm_enabled",
                translation_key="solace_alarm_enabled",
                state_key="solace_alarm_enabled",
                icon="mdi:alarm",
                attribute_keys=(
                    "solace_alarm_time",
                    "solace_alarm_weekdays",
                    "solace_alarm_mode",
                    "solace_alarm_massage",
                    "solace_alarm_sound",
                    "solace_audio_available",
                ),
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        """Remove MotionFlex-only sensor entities from narrower profiles."""
        if self.supports_solace_audio:
            return frozenset()
        return frozenset({"solace_audio_volume"})

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        """Remove MotionFlex-only binary sensors from narrower profiles."""
        if self.supports_solace_alarm:
            return frozenset()
        return frozenset({"solace_alarm_enabled"})

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return SOLACE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        """Keep FFE1 subscribed where a route queries preset and accessory state."""
        return self.profile.queries is not None

    @property
    def _query_family(self) -> str | None:
        """Return the accepted preset-status query family for this name route."""
        return solace_query_family(self.profile, self._coordinator.ble_device_name)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to FFE1 and request the five preset-selection states."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot start Solace notifications: not connected")
            return

        try:
            await client.start_notify(SOLACE_CHAR_UUID, self._handle_notification)
        except BleakError as err:
            _LOGGER.debug("Could not start Solace notifications: %s", err)
            return
        query_family = self._query_family
        if query_family is None:
            return

        if self._query_task is not None:
            self._query_task.cancel()
        self._query_task = asyncio.create_task(
            self._async_query_preset_states(query_family),
            name=f"solace-preset-state-{self._coordinator.address}",
        )

    async def _async_query_preset_states(self, query_family: str) -> None:
        """Issue the app-proven startup query sequence without delaying setup."""
        if self._coordinator.controller is not self:
            return
        self.forward_controller_state_updates(
            {
                f"solace_{key}_selected": False
                for key in ("tv", "zero_g", "memory_1", "memory_2", "anti_snore")
            }
        )
        queries = SolaceCommands.QUERY_Q1 if query_family == "q1" else SolaceCommands.QUERY_Q2

        async def run_queries(controller: BedController) -> None:
            if controller is not self:
                return
            if self.profile.clock_sync:
                await controller.write_command(
                    build_solace_clock_command(dt_util.now()),
                    cancel_event=asyncio.Event(),
                )
                queries_with_accessories = (*queries, SolaceCommands.LIGHT_STATUS_QUERY)
            else:
                queries_with_accessories = queries
            for index, command in enumerate(queries_with_accessories):
                await controller.write_command(command, cancel_event=asyncio.Event())
                if index < len(queries_with_accessories) - 1:
                    await asyncio.sleep(self.profile.query_spacing_ms / 1000)

        try:
            await asyncio.sleep(self.profile.query_delay_ms / 1000)
            await self._coordinator.async_execute_controller_query(
                run_queries,
                skip_disconnect=True,
                preemptible=True,
                run_if=lambda: self._query_task is asyncio.current_task()
                and self._coordinator.controller is self,
            )
        except asyncio.CancelledError:
            raise
        except (BleakError, ConnectionError, RuntimeError) as err:
            # State is advisory. A failed query must not prevent bed controls.
            _LOGGER.debug("Solace preset-state query failed: %s", err)
        finally:
            if self._query_task is asyncio.current_task():
                self._query_task = None

    async def stop_notify(self) -> None:
        """Stop the FFE1 state subscription."""
        client = self.client
        if self._query_task is not None:
            self._query_task.cancel()
            self._query_task = None
        if client is None or not client.is_connected:
            return
        try:
            await client.stop_notify(SOLACE_CHAR_UUID)
        except BleakError as err:
            _LOGGER.debug("Could not stop Solace notifications: %s", err)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        """Forward and parse the app-proven substring-based state replies."""
        payload = bytes(data)
        self.forward_raw_notification(SOLACE_CHAR_UUID, payload)
        self._parse_notification(payload)

    def _parse_notification(self, data: bytes) -> None:
        """Update selected preset flags from Q1/Q2 replies and command echoes."""
        updates: dict[str, bool | int | str] = {}
        selectors = {
            0x05: "tv",
            0x09: "zero_g",
            0x0A: "memory_1",
            0x0B: "memory_2",
            0x0F: "anti_snore",
        }
        prefix = bytes.fromhex("FF FF FF FF 03 06 00")
        for selector, key in selectors.items():
            if prefix + bytes([selector]) in data:
                updates[f"solace_{key}_selected"] = True

        state_frames = {
            SolaceCommands.PROGRAM_MEMORY_1: ("memory_1", True),
            SolaceCommands.PROGRAM_MEMORY_1_SELECTED: ("memory_1", False),
            SolaceCommands.PROGRAM_MEMORY_2: ("memory_2", True),
            SolaceCommands.PROGRAM_MEMORY_2_SELECTED: ("memory_2", False),
            SolaceCommands.PROGRAM_TV: ("tv", True),
            SolaceCommands.PROGRAM_TV_DESELECTED: ("tv", False),
            SolaceCommands.PROGRAM_ZERO_G: ("zero_g", True),
            SolaceCommands.PROGRAM_ZERO_G_DESELECTED: ("zero_g", False),
            SolaceCommands.PROGRAM_ANTI_SNORE: ("anti_snore", True),
            SolaceCommands.PROGRAM_ANTI_SNORE_DESELECTED: ("anti_snore", False),
        }
        for frame, (key, selected) in state_frames.items():
            if frame in data:
                updates[f"solace_{key}_selected"] = selected

        volume_prefix = bytes.fromhex("FF FF FF FF 01 00 15 0B")
        if (volume_index := data.find(volume_prefix)) >= 0 and len(data) > volume_index + 8:
            updates["solace_audio_volume"] = data[volume_index + 8] & 0x0F

        light_prefix = bytes.fromhex("FF FF FF FF 05 00 01")
        if (light_index := data.find(light_prefix)) >= 0 and len(data) > light_index + 7:
            light_level = data[light_index + 7]
            if 0 <= light_level <= self.light_level_max:
                updates["light_level"] = light_level

        alarm_none_prefix = bytes.fromhex("FF FF FF FF 01 00 03 0B")
        if (alarm_none_index := data.find(alarm_none_prefix)) >= 0 and len(
            data
        ) > alarm_none_index + 8:
            updates.update(
                {
                    "solace_alarm_enabled": False,
                    "solace_audio_available": data[alarm_none_index + 8] != 0,
                }
            )

        alarm_prefix = bytes.fromhex("FF FF FF FF 01 00 04 13")
        if (alarm_index := data.find(alarm_prefix)) >= 0 and len(data) >= alarm_index + 17:
            payload = data[alarm_index + 8 : alarm_index + 17]
            enabled = payload[0] in {0x0F, 0x1F}
            weekdays = [str(day) for day in range(1, 8) if payload[4] & (1 << day)]
            mode = {value: key for key, value in _SOLACE_ALARM_MODES.items()}.get(
                payload[6], f"unknown_{payload[6]:02x}"
            )
            sound = {value: key for key, value in _SOLACE_ALARM_SOUNDS.items()}.get(
                payload[8], f"unknown_{payload[8]:02x}"
            )
            updates.update(
                {
                    "solace_alarm_enabled": enabled,
                    "solace_alarm_time": f"{payload[1]:02x}:{payload[2]:02x}",
                    "solace_alarm_weekdays": ",".join(weekdays),
                    "solace_alarm_mode": mode,
                    "solace_alarm_massage": payload[7] == 1,
                    "solace_alarm_sound": sound,
                }
            )
        if updates:
            self.forward_controller_state_updates(updates)

    # Capability properties
    @property
    def supports_preset_flat(self) -> bool:
        """Avoid sending either flat variant to an unidentified manual route."""
        return self.profile.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.profile.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile.presets

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile.presets

    @property
    def supports_preset_yoga(self) -> bool:
        # Yoga belongs to a different app whose APK Protocol Audit analysis is pending.
        return False

    @property
    def supports_relaxing_bedtime(self) -> bool:
        """Return whether MotionFlex exposes its relaxing-bedtime preset."""
        return self.profile.relaxing_bedtime

    @property
    def supports_solace_audio(self) -> bool:
        """Return whether MotionFlex exposes music and volume controls."""
        return self.profile.audio

    @property
    def supports_solace_alarm(self) -> bool:
        """Return whether the route exposes the alarm packet family."""
        return self.profile.alarm

    @property
    def supports_memory_presets(self) -> bool:
        """Return whether the identified route has numbered memories."""
        return self.profile.presets

    @property
    def memory_slot_count(self) -> int:
        """Return only the two slots that are not overloaded named presets."""
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        """Return whether the two numbered memories can be programmed."""
        return self.profile.presets

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return only the motors proven for the selected profile."""

        def spec(axis: str) -> MotorControlSpec:
            stem, max_angle = _AXES[axis]
            return MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=lambda ctrl: getattr(ctrl, f"move_{stem}_up")(),
                close_fn=lambda ctrl: getattr(ctrl, f"move_{stem}_down")(),
                stop_fn=lambda ctrl: getattr(ctrl, f"move_{stem}_stop")(),
                max_angle=max_angle,
            )

        return tuple(spec(axis) for axis in self.profile.axes)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove covers left behind by the former union/motor-count layout."""
        return frozenset({"back", "legs", "head", "feet", "hip", "lumbar", "bed_height", "tilt"})

    # HA cover actions have no button-release event. Keep the existing timeout as
    # an integration safety cap, while still allowing an explicit stop to cancel it.
    _MOVEMENT_SAFETY_TIMEOUT: float = 5.0

    async def _send_stop(self) -> None:
        """Send STOP command with fresh cancel event."""
        await self.write_command(SolaceCommands.MOTOR_STOP, cancel_event=asyncio.Event())

    async def _move_with_stop(self, command: bytes) -> None:
        """Send a press command and guarantee its protocol STOP cleanup."""
        try:
            # Send move command once (latched — controller holds motor state)
            await self.write_command(command, cancel_event=asyncio.Event())
            # Wait for movement duration, interruptible by coordinator's cancel event
            try:
                await asyncio.wait_for(
                    self._coordinator.cancel_command.wait(),
                    timeout=leased_hold_ms(
                        round(self._MOVEMENT_SAFETY_TIMEOUT * 1000), LATCHED_MAX_HOLD_MS
                    )
                    / 1000,
                )
            except TimeoutError:
                pass  # Normal: completed full movement duration
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP command during cleanup")

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up (separate pillow-top motor)."""
        await self._move_with_stop(SolaceCommands.MOTOR_HEAD_UP)

    async def move_head_down(self) -> None:
        """Move head down (separate pillow-top motor)."""
        await self._move_with_stop(SolaceCommands.MOTOR_HEAD_DOWN)

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_UP)

    async def move_back_down(self) -> None:
        """Move back down."""
        await self._move_with_stop(SolaceCommands.MOTOR_BACK_DOWN)

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_UP)

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_with_stop(SolaceCommands.MOTOR_LEGS_DOWN)

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        """Move feet up (same as legs for Solace)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down (same as legs for Solace)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_head_stop()

    async def stop_all(self) -> None:
        """Stop all motors."""
        await self.write_command(
            SolaceCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def _send_preset(self, command: bytes) -> None:
        """Send the accepted apps' single-write autonomous preset command."""
        await self.write_command(command, cancel_event=asyncio.Event())

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position (single-shot, bed moves autonomously)."""
        await self._send_preset(self.profile.flat)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (single-shot, bed moves autonomously)."""
        commands = {
            1: SolaceCommands.PRESET_MEMORY_1,
            2: SolaceCommands.PRESET_MEMORY_2,
        }
        if command := commands.get(memory_num):
            await self._send_preset(command)
        else:
            _LOGGER.warning("Invalid memory preset number: %d (valid: 1-2)", memory_num)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: (
                SolaceCommands.PROGRAM_MEMORY_1_SELECTED
                if self._preset_is_selected("memory_1")
                else SolaceCommands.PROGRAM_MEMORY_1
            ),
            2: (
                SolaceCommands.PROGRAM_MEMORY_2_SELECTED
                if self._preset_is_selected("memory_2")
                else SolaceCommands.PROGRAM_MEMORY_2
            ),
        }
        if command := commands.get(memory_num):
            await self.write_command(command)
        else:
            _LOGGER.warning("Invalid memory program number: %d (valid: 1-2)", memory_num)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_ZERO_G_SELECTED
            if self._preset_is_selected("zero_g")
            else SolaceCommands.PRESET_ZERO_G
        )
        await self._send_preset(command)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_ANTI_SNORE_SELECTED
            if self._preset_is_selected("anti_snore")
            else SolaceCommands.PRESET_ANTI_SNORE
        )
        await self._send_preset(command)

    async def preset_tv(self) -> None:
        """Go to TV position (single-shot, bed moves autonomously)."""
        command = (
            SolaceCommands.PRESET_TV_SELECTED
            if self._preset_is_selected("tv")
            else SolaceCommands.PRESET_TV
        )
        await self._send_preset(command)

    async def preset_relaxing_bedtime(self) -> None:
        """Run the MotionFlex relaxing-bedtime preset."""
        await self._send_preset(SolaceCommands.PRESET_RELAXING_BEDTIME)

    async def solace_music_toggle(self) -> None:
        """Send the MotionFlex short-press music action."""
        await self.write_command(SolaceCommands.MUSIC_TOGGLE, cancel_event=asyncio.Event())

    async def solace_music_off(self) -> None:
        """Send the MotionFlex long-press/dialog-save music action."""
        await self.write_command(SolaceCommands.MUSIC_OFF, cancel_event=asyncio.Event())

    async def solace_select_music(self, track: int, *, preview: bool = False) -> None:
        """Select one of the five MotionFlex tracks, optionally as an alarm preview."""
        value = track | (0x80 if preview else 0)
        await self.write_command(codec.summed(0x01, 0x13, bytes((value,))), cancel_event=asyncio.Event())

    async def solace_set_audio_volume(self, level: int) -> None:
        """Set the MotionFlex audio volume to an app-supported level (1-5)."""
        await self.write_command(codec.summed(0x01, 0x14, bytes((level,))), cancel_event=asyncio.Event())
        self.forward_controller_state_updates({"solace_audio_volume": level})

    async def solace_query_audio_volume(self) -> None:
        """Request the MotionFlex audio volume notification."""
        await self.write_command(
            SolaceCommands.AUDIO_VOLUME_QUERY,
            cancel_event=asyncio.Event(),
        )

    async def program_solace_alarm(
        self,
        *,
        enabled: bool,
        hour: int,
        minute: int,
        weekdays: Collection[int],
        mode: str,
        massage: bool,
        sound: str,
    ) -> None:
        """Program the MotionFlex alarm surface."""
        await self.write_command(
            build_solace_alarm_command(
                enabled=enabled,
                hour=hour,
                minute=minute,
                weekdays=weekdays,
                mode=mode,
                massage=massage,
                sound=sound,
            ),
            cancel_event=asyncio.Event(),
        )
        self.forward_controller_state_updates(
            {
                "solace_alarm_enabled": enabled,
                "solace_alarm_time": f"{hour:02d}:{minute:02d}",
                "solace_alarm_weekdays": ",".join(
                    str(day) for day in sorted(set(weekdays))
                ),
                "solace_alarm_mode": mode,
                "solace_alarm_massage": massage,
                "solace_alarm_sound": sound,
            }
        )

    def _preset_is_selected(self, key: str) -> bool:
        """Return the last state proven by a query response or command echo."""
        return bool(self._coordinator.controller_state.get(f"solace_{key}_selected", False))

    # Massage methods
    @property
    def supports_massage(self) -> bool:
        """Return whether the selected Home profile exposes massage."""
        return self.profile.massage

    @property
    def auto_enable_massage(self) -> bool:
        """Auto-enable massage only where the app proves it is always present."""
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        # The overall +/- label was historical; 0x14/0x15 are wave controls.
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_wave_frequency_control(self) -> bool:
        return self.supports_massage

    async def massage_wave_frequency_up(self) -> None:
        """Increase the Home profile's massage wave frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_UP)

    async def massage_wave_frequency_down(self) -> None:
        """Decrease the Home profile's massage wave frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_DOWN)

    async def massage_head_up(self) -> None:
        """Increase head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_UP)

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_HEAD_DOWN)

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_UP)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity."""
        await self.write_command(SolaceCommands.MASSAGE_FOOT_DOWN)

    async def massage_intensity_up(self) -> None:
        """Increase massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_UP)

    async def massage_intensity_down(self) -> None:
        """Decrease massage frequency."""
        await self.write_command(SolaceCommands.MASSAGE_FREQUENCY_DOWN)

    async def massage_off(self) -> None:
        """Stop all massage."""
        await self.write_command(SolaceCommands.MASSAGE_STOP)

    # Hip motor support — not all Solace/QMS beds have a hip motor.
    # The smartbed-mqtt reference only exposes Back, Legs, Lift, Tilt.
    # Hip commands (0x0D/0x0E) exist in the protocol but are model-specific.

    async def move_hip_up(self) -> None:
        """Move hip motor up."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_UP)

    async def move_hip_down(self) -> None:
        """Move hip motor down."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_DOWN)

    async def move_hip_stop(self) -> None:
        """Stop hip motor."""
        await self.move_head_stop()

    async def move_lumbar_up(self) -> None:
        """Raise the lumbar axis used by Home K2 layouts."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_UP)

    async def move_lumbar_down(self) -> None:
        """Lower the lumbar axis used by Home K2 layouts."""
        await self._move_with_stop(SolaceCommands.MOTOR_HIP_DOWN)

    async def move_lumbar_stop(self) -> None:
        """Stop the lumbar motor."""
        await self.move_head_stop()

    async def move_lift_up(self) -> None:
        """Raise the height axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_LIFT_UP)

    async def move_lift_down(self) -> None:
        """Lower the height axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_LIFT_DOWN)

    async def move_lift_stop(self) -> None:
        """Stop the height axis."""
        await self.move_head_stop()

    async def move_tilt_up(self) -> None:
        """Raise the tilt axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_TILT_UP)

    async def move_tilt_down(self) -> None:
        """Lower the tilt axis on the hardware-confirmed S4-Y layout."""
        await self._move_with_stop(SolaceCommands.MOTOR_TILT_DOWN)

    async def move_tilt_stop(self) -> None:
        """Stop the tilt axis."""
        await self.move_head_stop()

    # Light control
    @property
    def supports_lights(self) -> bool:
        """Return whether the route proves direct brightness control."""
        return self.profile.light_levels

    async def lights_on(self) -> None:
        """Turn lights on (set to max brightness)."""
        await self.write_command(SolaceCommands.LIGHT_LEVELS[10])
        self.forward_controller_state_update("light_level", 10)

    async def lights_off(self) -> None:
        """Turn lights off."""
        await self.write_command(SolaceCommands.LIGHT_LEVELS[0])
        self.forward_controller_state_update("light_level", 0)

    @property
    def supports_light_level_control(self) -> bool:
        """Return whether the route proves levels 0 through 10."""
        return self.profile.light_levels

    @property
    def light_level_max(self) -> int:
        """Return maximum light level (10)."""
        return 10

    async def set_light_level(self, level: int) -> None:
        """Set light level (0-10)."""
        if 0 <= level <= 10:
            await self.write_command(SolaceCommands.LIGHT_LEVELS[level])
            self.forward_controller_state_update("light_level", level)
        else:
            _LOGGER.warning("Invalid light level: %d (valid: 0-10)", level)

    # Light timer control
    @property
    def supports_light_timer(self) -> bool:
        """Return whether the accepted profile exposes the timer frames."""
        return self.profile.light_timer

    @property
    def light_timer_options(self) -> list[str]:
        """Return available light timer options."""
        options = ["10 min", "8 hours", "10 hours"]
        if self.profile.light_levels:
            return ["Off", *options]
        return options

    async def set_light_timer(self, timer_option: str) -> None:
        """Set light timer.

        Args:
            timer_option: One of "Off", "10 min", "8 hours", "10 hours"
        """
        commands = {
            "Off": SolaceCommands.LIGHT_LEVELS[0],  # Turn off light
            "10 min": SolaceCommands.LIGHT_TIMER_10_MIN,
            "8 hours": SolaceCommands.LIGHT_TIMER_8_HOURS,
            "10 hours": SolaceCommands.LIGHT_TIMER_10_HOURS,
        }
        if cmd := commands.get(timer_option):
            await self.write_command(cmd)
        else:
            _LOGGER.warning("Invalid light timer option: %s", timer_option)

    # Circulation massage support
    @property
    def supports_circulation_massage(self) -> bool:
        """Expose cycle labels only where the fourth zone is proven as hip."""
        return self.profile.circulation

    async def massage_circulation_full_body(self) -> None:
        """Start full body circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_FULL_BODY)

    async def massage_circulation_head(self) -> None:
        """Start head circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HEAD)

    async def massage_circulation_leg(self) -> None:
        """Start leg circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_LEG)

    async def massage_circulation_hip(self) -> None:
        """Start hip circulation massage."""
        await self.write_command(SolaceCommands.MASSAGE_CIRCULATION_HIP)

    # Massage timer support
    @property
    def supports_massage_timer(self) -> bool:
        """Return whether the selected Home profile exposes massage timers."""
        return self.supports_massage

    @property
    def massage_timer_options(self) -> list[int]:
        """Return available timer durations in minutes."""
        return [10, 20, 30]

    async def set_massage_timer(self, minutes: int) -> None:
        """Set massage auto-off timer (0=off, 10/20/30 minutes)."""
        commands = {
            0: SolaceCommands.MASSAGE_STOP,
            10: SolaceCommands.MASSAGE_TIMER_10_MIN,
            20: SolaceCommands.MASSAGE_TIMER_20_MIN,
            30: SolaceCommands.MASSAGE_TIMER_30_MIN,
        }
        if cmd := commands.get(minutes):
            await self.write_command(cmd)
        else:
            _LOGGER.warning("Invalid massage timer: %d min (valid: 0, 10, 20, 30)", minutes)
