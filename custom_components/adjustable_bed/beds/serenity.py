"""Jordan's Serenity 1.0.1 app profile, independently frozen as S01."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .okin_cst import CstFields, CstMemorySlot, CstProfile, OkinCstController
from .okin_protocol import build_cst_command

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..coordinator import AdjustableBedCoordinator

_SERVICE = "62741523-52f9-8864-b1ab-3b3a8d65950b"
_NOTIFY = "62741625-52f9-8864-b1ab-3b3a8d65950b"
_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"
_ACTIONS = {
    "head_up": (1, 0),
    "head_down": (2, 0),
    "foot_up": (4, 0),
    "foot_down": (8, 0),
    "selector_4_up": (0x10, 0),
    "selector_4_down": (0x20, 0),
    "selector_5_up": (0x40, 0),
    "selector_5_down": (0x80, 0),
    "flat": (0x08000000, 0),
    "zero_g": (0x1000, 0),
    "memory_1": (0x10000, 0),
    "tv": (0x4000, 0),
    "memory_2": (0x40000, 0),
    "save_zero_g": (0x08001000, 0),
    "save_memory_1": (0x08010000, 0),
    "save_tv": (0x08004000, 0),
    "save_memory_2": (0x08040000, 0),
    "massage_head_cycle": (0x800, 0),
    "massage_foot_cycle": (0x400, 0),
    "massage_mode_cycle": (0x10000000, 0),
    "massage_timer_cycle": (0x200, 0),
    "massage_toggle": (0x100, 0),
    "light_toggle": (0x20000, 0),
    "leisure": (0x2000, 0),
    "anti_snore": (0x8000, 0),
    "wave_1": (0, 0x80000),
    "wave_2": (0, 0x100000),
    "wave_3": (0, 0x200000),
    "massage_off": (0x02000000, 0),
    "light_on": (0, 0x40),
    "light_off": (0, 0x80),
}
_SAVE_CODES = {"save_zero_g": 5, "save_memory_1": 4, "save_tv": 6, "save_memory_2": 8}
_SAVE_HOLD_MS = 5000  # The app's save-help gesture, not a hardware threshold.


def _callback(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        if not isinstance(controller, SerenityController) and not (
            isinstance(controller, SideBoundController)
            and isinstance(controller._controller, SerenityController)
        ):
            raise TypeError("This action requires the Serenity app profile")
        await controller.execute_app_control(action)

    return invoke


class SerenityController(OkinCstController):
    """Reuse the proven CST frame without inheriting another app's capabilities."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._profile = CstProfile(
            key="serenity",
            motors=("head", "feet"),
            lounge=True,
            incline=False,
            memory_slots=(
                CstMemorySlot("M1", 0x10000, 0x08010000),
                CstMemorySlot("M2", 0x40000, 0x08040000),
            ),
            lights=True,
            massage_style="zoned",
            massage_toggle=CstFields(primary=0x100),
        )
        self._has_explicit_profile = True
        self._status_code = 0
        self._timer_code = 0
        self._save_code = 0
        self._alarm_type = 0
        self._state: dict[str, object] = {}

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Every release is global, so another axis STOP must preempt this one.
        return tuple(replace(spec, scheduler_resource="*") for spec in super().motor_control_specs)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {**super().protocol_diagnostics, **self._state, "save_pending_code": self._save_code}

    def _publish(self, updates: dict[str, object]) -> None:
        self._state.update(updates)
        self.forward_controller_state_updates(updates)

    def _write_response(self) -> bool:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Serenity is not connected")
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == self.control_characteristic_uuid
        ]
        if len(matches) != 1:
            raise ValueError("Serenity requires its exact writable GATT role")
        # Artifact write type is inherited/unknown; this is HA's property policy.
        if "write" in matches[0].properties:
            return True
        if "write-without-response" in matches[0].properties:
            return False
        raise ValueError("Serenity command characteristic is not writable")

    async def async_discover_capabilities(self) -> None:
        self._write_response()
        client = self.client
        if client is None:
            raise ConnectionError("Serenity is not connected")
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == _NOTIFY and "notify" in char.properties
        ]
        if len(matches) != 1:
            raise ValueError("Serenity requires its notification characteristic")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_response(),
            wall_clock_pacing=True,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        await self.async_discover_capabilities()
        client = self.client
        if client is None:
            return
        self._notify_callback = callback
        async with self._ble_lock:
            await client.start_notify(_NOTIFY, self._handle_notification)
        await asyncio.sleep(1)
        await self.refresh_manufacturer()

    async def refresh_manufacturer(self) -> None:
        """Repeat the reachable on-resume read without selecting capabilities."""
        client = self.client
        if client is None or not client.is_connected:
            return
        matches = [
            char
            for service in client.services or ()
            if service.uuid.lower() == "0000180a-0000-1000-8000-00805f9b34fb"
            for char in service.characteristics
            if char.uuid.lower() == _MANUFACTURER and "read" in char.properties
        ]
        if len(matches) != 1:
            return
        try:
            async with asyncio.timeout(2):
                async with self._ble_lock:
                    value = await client.read_gatt_char(_MANUFACTURER)
            self._publish({"serenity_manufacturer": bytes(value).decode("utf-8", errors="replace")})
        except BleakError, OSError, TimeoutError:
            pass  # Missing diagnostic information does not block control.

    def _handle_notification(self, _: object, data: bytearray) -> None:
        self.forward_raw_notification(_NOTIFY, bytes(data))
        if len(data) <= 10:
            return

        def signed(value: int) -> int:
            return value if value < 128 else value - 256

        if data[1] == 12:
            self._alarm_type = {1: 9, 2: 17, 3: 18, 4: 16, 5: 20, 6: 19, 7: 18, 8: 9, 9: 21}.get(
                data[5], self._alarm_type
            )
            self._publish(
                {
                    "serenity_alarm_type": self._alarm_type,
                    "serenity_alarm_repeat": signed(data[4]),
                    "serenity_alarm_hour": signed(data[6]),
                    "serenity_alarm_minute": signed(data[7]),
                    "serenity_alarm_on": data[9] == 1,
                }
            )
            return
        code = signed(data[10])
        if code == self._status_code:
            return
        self._status_code = code
        updates: dict[str, object] = {"serenity_status_code": code}
        # HA supplies the active callback equivalent. The source treats any
        # status change during save as a local success, not a hardware ACK.
        if self._save_code:
            updates["serenity_save_event_code"] = self._save_code
            self._save_code = 0
        elif code != self._timer_code:
            self._timer_code = code
            updates.update(
                {
                    "serenity_massage_timer_code": code,
                    "serenity_massage_timer_minutes": {1: 10, 2: 20, 3: 30}.get(code),
                }
            )
        self._publish(updates)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        keys = (
            "manufacturer",
            "status_code",
            "massage_timer_code",
            "massage_timer_minutes",
            "save_event_code",
            "alarm_type",
        )
        return tuple(
            ControllerStateSensorSpec(
                key=f"serenity_{key}",
                translation_key=f"serenity_{key}",
                state_key=f"serenity_{key}",
                icon="mdi:information-outline",
                native_unit_of_measurement="min" if key == "massage_timer_minutes" else None,
                attribute_keys=(
                    "serenity_alarm_repeat",
                    "serenity_alarm_hour",
                    "serenity_alarm_minute",
                    "serenity_alarm_on",
                )
                if key == "alarm_type"
                else (),
            )
            for key in keys
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(_ACTIONS)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in _ACTIONS:
            raise ValueError("Unknown Serenity action")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Duration must be a positive integer, at most 60000 ms")
        primary, secondary = _ACTIONS[control]
        # The app records local save intent before writing, not a storage ACK.
        if control in _SAVE_CODES:
            self._save_code = _SAVE_CODES[control]
        elif control in {"flat", "zero_g", "memory_1", "tv", "memory_2", "leisure", "anti_snore"}:
            self._save_code = 0
        deadline = asyncio.timeout(duration_ms / 1000)
        controller_timeout = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            build_cst_command(primary, secondary),
                            repeat_count=self.timed_move_repeat_count(duration_ms, 100),
                            repeat_delay_ms=100,
                        )
                    except TimeoutError:
                        controller_timeout = True
                        raise
            except TimeoutError:
                if controller_timeout or not deadline.expired():
                    raise
        finally:
            await self._send_stop_sequence()

    async def _send_stop_sequence(self) -> None:
        async def release() -> None:
            event = asyncio.Event()
            failure: Exception | None = None
            loop = asyncio.get_running_loop()
            started = loop.time()
            for offset in (0.1, 0.2):
                await asyncio.sleep(max(0, started + offset - loop.time()))
                try:
                    await self.write_command(build_cst_command(), cancel_event=event)
                except Exception as error:
                    # The source schedules both releases independently.
                    failure = failure or error
            if failure is not None:
                raise failure

        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _send_repeated_command(
        self,
        *,
        motor_value: int = 0,
        control_value: int = 0,
        repeat_count: int,
        repeat_delay_ms: int,
    ) -> None:
        action = next(
            (key for key, fields in _ACTIONS.items() if fields == (motor_value, control_value)),
            None,
        )
        if action is None:
            raise ValueError("Command is not reachable in the Serenity app")
        # Inherited callers supply counts; this app defines a 500 ms deadline.
        await self.hold_control(action, 500)

    async def preset_flat(self) -> None:
        await self.hold_control("flat", 1500)

    async def preset_tv(self) -> None:
        await self.hold_control("tv", 500)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2) or isinstance(memory_num, bool):
            raise ValueError("Serenity has only M1 and M2")
        await self.hold_control(f"save_memory_{memory_num}", _SAVE_HOLD_MS)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2) or isinstance(memory_num, bool):
            raise ValueError("Serenity has only M1 and M2")
        await self.hold_control(f"memory_{memory_num}", 500)

    async def massage_mode_step(self) -> None:
        await self.hold_control("massage_mode_cycle", 500)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = (
            ("refresh_manufacturer", "Refresh Manufacturer"),
            ("selector_4_up", "Remote Selector 4 Up"),
            ("selector_4_down", "Remote Selector 4 Down"),
            ("selector_5_up", "Remote Selector 5 Up"),
            ("selector_5_down", "Remote Selector 5 Down"),
            ("save_zero_g", "Save Zero Gravity"),
            ("save_tv", "Save TV"),
            ("light_toggle", "Toggle Light"),
            ("massage_head_cycle", "Head Massage Cycle"),
            ("massage_foot_cycle", "Foot Massage Cycle"),
            ("massage_timer_cycle", "Massage Timer Cycle"),
            ("wave_1", "Wave 1"),
            ("wave_2", "Wave 2"),
            ("wave_3", "Wave 3"),
        )
        return tuple(
            ControllerButtonSpec(f"serenity_{action}", name, _callback(action))
            for action, name in actions
        )

    async def execute_app_control(self, action: str) -> None:
        if action == "refresh_manufacturer":
            await self.refresh_manufacturer()
            return
        await self.hold_control(action, _SAVE_HOLD_MS if action in _SAVE_CODES else 500)
