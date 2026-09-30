"""Explicit profiles from the frozen Customatic Clarity/Jerome's/Remedy apps."""

from __future__ import annotations

import asyncio
import logging
from itertools import combinations, product
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from .base import (
    POSITION_AXIS_COMMANDS,
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
COMMAND_SERVICE: Final = "62741523-52f9-8864-b1ab-3b3a8d65950b"
COMMAND_CHARACTERISTIC: Final = "62741525-52f9-8864-b1ab-3b3a8d65950b"
DEVICE_INFO_SERVICE: Final = "0000180a-0000-1000-8000-00805f9b34fb"
DEVICE_INFO_FIELDS: Final = (
    ("manufacturer", "00002a29-0000-1000-8000-00805f9b34fb"),
    ("hardware_revision", "00002a27-0000-1000-8000-00805f9b34fb"),
    ("software_revision", "00002a28-0000-1000-8000-00805f9b34fb"),
    ("firmware_revision", "00002a26-0000-1000-8000-00805f9b34fb"),
    ("model", "00002a24-0000-1000-8000-00805f9b34fb"),
)
MEMORY_BITS: Final = {
    "flat": 0x08000000,
    "zg": 0x00001000,
    "anti": 0x00008000,
    "program": 0x80000000,
    "incline": 0x00004000,
}
MOTOR_BITS: Final = {
    "back_up": 0x01,
    "back_down": 0x02,
    "legs_up": 0x04,
    "legs_down": 0x08,
    "lumbar_up": 0x10,
    "lumbar_down": 0x20,
}


def command_frame(mask: int) -> bytes:
    """The APK transmits six bytes, discarding its temporary checksum buffer."""
    if isinstance(mask, bool) or not isinstance(mask, int) or not 0 <= mask <= 0xFFFFFFFF:
        raise ValueError("Command mask must be an unsigned 32-bit integer")
    return b"\x04\x02" + mask.to_bytes(4, "big")


def _button_callback(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        if not isinstance(controller, CustomaticController) and not (
            isinstance(controller, SideBoundController)
            and isinstance(controller._controller, CustomaticController)
        ):
            raise TypeError("This action requires a Customatic app profile")
        await controller.execute_app_control(action)

    return invoke


class CustomaticController(BedController):
    """Keep app reachability independent of shared UUIDs or reported DIS strings."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: str) -> None:
        super().__init__(coordinator)
        if profile not in {"clarity", "jeromes", "remedy"}:
            raise ValueError("Customatic profile must be clarity, jeromes or remedy")
        self.profile = profile
        self._device_info: dict[str, str | None] = {field: None for field, _ in DEVICE_INFO_FIELDS}
        self._info_lock = asyncio.Lock()

    @property
    def control_characteristic_uuid(self) -> str:
        return COMMAND_CHARACTERISTIC

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"profile": self.profile, "device_info": dict(self._device_info)}

    def _write_response(self) -> bool:
        client = self.client
        if client is None or not client.is_connected or not client.services:
            raise ConnectionError("Customatic requires discovered GATT services")
        matches = [
            char
            for service in client.services
            if service.uuid.lower() == COMMAND_SERVICE
            for char in service.characteristics
            if char.uuid.lower() == COMMAND_CHARACTERISTIC
        ]
        if len(matches) != 1:
            raise ValueError("Customatic requires one command characteristic in its service")
        # The APK inherits the characteristic's write mode. This is HA's policy,
        # not evidence of the Android runtime mode on a particular physical bed.
        if "write" in matches[0].properties:
            return True
        if "write-without-response" in matches[0].properties:
            return False
        raise ValueError("Customatic command characteristic is not writable")

    async def async_discover_capabilities(self) -> None:
        self._write_response()
        # This hook runs even when angle sensing (and therefore notify) is off.
        await self.refresh_device_info()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 120,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            COMMAND_CHARACTERISTIC,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_response(),
            wall_clock_pacing=True,
        )

    async def refresh_device_info(self, *, only_if_missing: bool = False) -> None:
        """Read the whole five-field batch; missing DIS never blocks controls."""
        async with self._info_lock:
            if only_if_missing and all(value is not None for value in self._device_info.values()):
                return
            client = self.client
            if client is None or not client.is_connected:
                return
            for index, (field, uuid) in enumerate(DEVICE_INFO_FIELDS):
                if index:
                    # Safe serial reads preserve the minimum 120 ms spacing;
                    # unlike Android's posted callbacks, batches cannot overlap.
                    await asyncio.sleep(0.12)
                chars = [
                    char
                    for service in client.services or ()
                    if service.uuid.lower() == DEVICE_INFO_SERVICE
                    for char in service.characteristics
                    if char.uuid.lower() == uuid and "read" in char.properties
                ]
                if len(chars) != 1:
                    continue
                try:
                    async with asyncio.timeout(2):
                        async with self._ble_lock:
                            raw = await client.read_gatt_char(chars[0])
                    # Java's UTF-8 constructor replaces malformed sequences.
                    value = bytes(raw).decode("utf-8", errors="replace")
                except BleakError, TimeoutError, OSError:
                    _LOGGER.debug("Could not read Customatic %s", field, exc_info=True)
                    continue
                self._device_info[field] = value
                self.forward_controller_state_update(f"customatic_{field}", value)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                key=f"customatic_{field}",
                translation_key=f"customatic_{field}",
                state_key=f"customatic_{field}",
                icon="mdi:information-outline",
            )
            for field, _ in DEVICE_INFO_FIELDS
        )

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        return ("back", "legs", "lumbar") if self.profile == "remedy" else ("back", "legs")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=POSITION_AXIS_COMMANDS[axis][0],
                close_fn=POSITION_AXIS_COMMANDS[axis][1],
                stop_fn=POSITION_AXIS_COMMANDS[axis][2],
                max_angle=45 if axis == "legs" else 68,
                scheduler_resource="*",
            )
            for axis in self.simultaneous_movement_axes
        )

    @property
    def supports_simultaneous_movement(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        axes = self.simultaneous_movement_axes
        motor_options = tuple(
            "+".join(
                f"{axis}_{direction}"
                for axis, direction in zip(axes, directions, strict=True)
                if direction
            )
            for directions in product(("", "up", "down"), repeat=len(axes))
            if any(directions)
        )
        memory_options = (
            tuple(
                "+".join(subset)
                for size in range(1, 6)
                for subset in combinations(MEMORY_BITS, size)
            )
            if self.profile != "jeromes"
            else ()
        )
        return motor_options + memory_options

    def _control_mask(self, control: str) -> tuple[int, bool]:
        tokens = control.split("+")
        if not tokens or len(tokens) != len(set(tokens)) or "" in tokens:
            raise ValueError("Controls must contain distinct nonempty actions")
        memory = all(token in MEMORY_BITS for token in tokens)
        if memory:
            if self.profile == "jeromes":
                raise ValueError("Jerome's profile has no memory page")
            return sum(MEMORY_BITS[token] for token in tokens), False
        if not all(token in MOTOR_BITS for token in tokens):
            raise ValueError("Unknown control or mixed motor and memory actions")
        axes = [token.rsplit("_", 1)[0] for token in tokens]
        if len(axes) != len(set(axes)) or not set(axes) <= set(self.simultaneous_movement_axes):
            raise ValueError("Unsupported axis or opposing directions on the same motor")
        return sum(MOTOR_BITS[token] for token in tokens), True

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 120

    @staticmethod
    def _validate_duration(duration_ms: int) -> None:
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be a positive integer, at most 60000 ms")

    async def _hold(self, mask: int, *, motor: bool, duration_ms: int | None) -> None:
        count, delay = self.motor_pulse_settings()
        if duration_ms is not None:
            self._validate_duration(duration_ms)
            count = self.timed_move_repeat_count(duration_ms, delay)
        deadline = asyncio.timeout(None if duration_ms is None else duration_ms / 1000)
        controller_timed_out = False
        try:
            try:
                async with deadline:
                    try:
                        await self.write_command(
                            command_frame(mask), repeat_count=count, repeat_delay_ms=delay
                        )
                    except TimeoutError:
                        controller_timed_out = True
                        raise
            except TimeoutError:
                if controller_timed_out or not deadline.expired():
                    raise
        finally:
            if motor:
                release = asyncio.create_task(self._release_motion())
                try:
                    await asyncio.shield(release)
                except asyncio.CancelledError:
                    await release
                    raise
            # Memory's independent refresh lane ends without a release packet.

    async def _release_motion(self) -> None:
        await asyncio.sleep(0.1)
        await self.stop_all()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        mask, motor = self._control_mask(control)
        await self._hold(mask, motor=motor, duration_ms=duration_ms)

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        if not isinstance(first_up, bool) or not isinstance(second_up, bool):
            raise ValueError("Motor directions must be booleans")
        mask, motor = self._control_mask(
            f"{first_axis}_{'up' if first_up else 'down'}+"
            f"{second_axis}_{'up' if second_up else 'down'}"
        )
        await self._hold(mask, motor=motor, duration_ms=duration_ms)

    async def _move_axis(self, axis: str, up: bool) -> None:
        mask, motor = self._control_mask(f"{axis}_{'up' if up else 'down'}")
        await self._hold(mask, motor=motor, duration_ms=None)

    async def move_head_up(self) -> None:
        await self.move_back_up()

    async def move_head_down(self) -> None:
        await self.move_back_down()

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move_axis("back", True)

    async def move_back_down(self) -> None:
        await self._move_axis("back", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self._move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self._move_axis("legs", False)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self._move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move_axis("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        if "lumbar" not in self.simultaneous_movement_axes:
            raise ValueError("This app profile has no lumbar control")
        await self.stop_all()

    async def stop_all(self) -> None:
        await self.write_command(command_frame(0), cancel_event=asyncio.Event())

    async def preset_flat(self) -> None:
        mask = 0x10000000 if self.profile == "jeromes" else 0x08000000
        await self.write_command(
            command_frame(mask),
            repeat_count=3 if self.profile == "jeromes" else 1,
            repeat_delay_ms=0,
        )

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    async def preset_memory(self, memory_num: int) -> None:
        raise ValueError("Customatic app profiles have no numbered recall slots")

    async def program_memory(self, memory_num: int) -> None:
        raise ValueError("Use the app-labelled Customatic save controls")

    @property
    def supports_lights(self) -> bool:
        return self.profile != "jeromes"

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise ValueError("Jerome's profile has no light control")
        await self.write_command(command_frame(0x00020000))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = [
            ControllerButtonSpec(
                "customatic_refresh_device_info",
                "Refresh Device Information",
                _button_callback("refresh_device_info"),
                "mdi:refresh",
            )
        ]
        if self.profile == "jeromes":
            buttons.append(
                ControllerButtonSpec(
                    "customatic_restored_flat",
                    "Restored Flat",
                    _button_callback("restored_flat"),
                    "mdi:bed",
                )
            )
        else:
            for action, name in (
                ("zg", "ZG"),
                ("anti", "ANTI"),
                ("incline", "Incline"),
                ("program", "Program"),
                ("program+zg", "Save ZG"),
                ("program+incline", "Save Incline"),
                ("flat+program", "Reset"),
            ):
                buttons.append(
                    ControllerButtonSpec(
                        f"customatic_{name.lower().replace(' ', '_')}",
                        name,
                        _button_callback(action),
                    )
                )
        return tuple(buttons)

    async def execute_app_control(self, action: str) -> None:
        if action == "refresh_device_info":
            await self.refresh_device_info()
        elif action == "restored_flat":
            if self.profile != "jeromes":
                raise ValueError("Restored flat belongs to the Jerome's app profile")
            await self.write_command(command_frame(0x08000000))
        elif action in {
            "zg",
            "anti",
            "incline",
            "program",
            "program+zg",
            "program+incline",
            "flat+program",
        }:
            # 2700 ms is the app's confirmation threshold, not a hardware ACK.
            await self.hold_control(action, 2700)
        else:
            raise ValueError(f"Unknown Customatic app action: {action}")
