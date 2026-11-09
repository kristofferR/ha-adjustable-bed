"""Reply-driven Paramount session and direct BLE controls.

Every writer runs in the coordinator command/query lane. Notification callbacks
only publish data and complete the current request; they never schedule writes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Final

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.components import bluetooth

from ...codec import paramount as codec
from ...controller_state import StateKey
from ...position_seek import PositionSeekPolicy
from ...profiles.paramount import PARAMOUNT
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

CAPABILITY: Final = StateKey[int | None]("paramount_capabilities")
HEIGHT: Final = StateKey[int | None]("paramount_height")
TILT: Final = StateKey[int | None]("paramount_tilt")
RSSI: Final = StateKey[int | None]("paramount_rssi")
SERIAL: Final = StateKey[str | None]("paramount_serial")
DEVICE_DATA: Final = StateKey[tuple[int, ...] | None]("paramount_device_data")
SESSION_STATE: Final = StateKey[int | None]("paramount_session_state")
REGISTRATION_RESULT: Final = StateKey[int | None]("paramount_registration_result")
SETTING_KEYS: Final = {
    name: StateKey[str | None]("paramount_" + name) for name in codec.SETTING_BITS
}
RANGE_KEYS: Final = {
    (axis, end): StateKey[int | None](f"paramount_{axis}_{end}")
    for axis in ("head", "legs", "height", "gearing")
    for end in ("min", "max")
}
RANGE_ENABLED_KEYS: Final = {
    axis: StateKey[str | None](f"paramount_{axis}_range")
    for axis in codec.CAPABILITIES
    if axis != "memory"
}
DURATION: Final = StateKey[str | None]("paramount_duration")


class ParamountPositionSeekPolicy(PositionSeekPolicy):
    """A slider step uses the app's one-second pulse, independent of tap preference."""

    def __init__(self, controller: ParamountController) -> None:
        super().__init__(controller)
        self._paramount = controller

    async def async_issue_step(
        self, position_key: str, moving_up: bool, default_step: Callable[[], Awaitable[None]]
    ) -> None:
        await self._paramount.hold_control(f"{position_key}_{'up' if moving_up else 'down'}", 1000)


class ParamountController(ProfileExecution, BedController):
    """One P1 profile, with live capability and settings discovery."""

    profile = PARAMOUNT

    def __init__(
        self, coordinator: AdjustableBedCoordinator, snapshot: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(coordinator)
        self._mask = 0
        self._height_bounds = (0, 0)
        if snapshot:
            mask, low, high = (snapshot.get(key) for key in ("mask", "height_min", "height_max"))
            if (
                isinstance(mask, int)
                and isinstance(low, int)
                and isinstance(high, int)
                and 0 <= mask <= 255
                and 0 <= low <= high <= 255
            ):
                self._mask = mask
                self._height_bounds = (low, high)
        self._settings: codec.Settings | None = None
        self._posture: codec.Posture | None = None
        self._serial: str | None = None
        self._pending: asyncio.Future[codec.Reply] | None = None
        self._expected: int | None = None
        self._generation = 0
        self._subscribed = False
        self._last_reply = 0.0
        self._idle_replies = 0
        self._ranges: dict[str, tuple[int, int]] = {}
        self._range_enabled: dict[str, bool] = {}
        self._duration = "1"

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self._mask & 16)

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.supports_memory_presets else 0

    @property
    def supports_position_feedback(self) -> bool:
        return bool(self._mask & 3)

    @property
    def supports_motor_control(self) -> bool:
        return bool(self._mask & 15)

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {
            "mask": self._mask,
            "height_min": self._height_bounds[0],
            "height_max": self._height_bounds[1],
        }

    @property
    def persisted_app_state(self) -> dict[str, object]:
        return {
            "ranges": {key: list(value) for key, value in self._ranges.items()},
            "range_enabled": dict(self._range_enabled),
            "duration": self._duration,
            "serial": self._serial,
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        ranges = state.get("ranges")
        if isinstance(ranges, dict):
            for axis, value in ranges.items():
                if (
                    axis in RANGE_ENABLED_KEYS
                    and isinstance(value, list)
                    and len(value) == 2
                    and all(
                        isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                        for v in value
                    )
                    and value[0] <= value[1]
                ):
                    self._ranges[axis] = (value[0], value[1])
        enabled = state.get("range_enabled")
        if isinstance(enabled, dict):
            self._range_enabled = {
                axis: value
                for axis, value in enabled.items()
                if axis in RANGE_ENABLED_KEYS and isinstance(value, bool)
            }
        if (duration := state.get("duration")) in ("hold", "1", "2", "3", "4"):
            self._duration = str(duration)
        if isinstance(serial := state.get("serial"), str):
            self._serial = serial
        self._publish_preferences()

    def _bounds(self, axis: str) -> tuple[int, int]:
        full = (
            self._height_bounds
            if axis == "height"
            else (0, self.profile.legs_max if axis == "legs" else self.profile.head_max)
        )
        low, high = self._ranges.get(axis, full)
        low = min(full[1], max(full[0], low))
        return low, max(low, min(full[1], high))

    def _publish_preferences(self) -> None:
        self.forward_controller_state_updates(DURATION(self._duration), SERIAL(self._serial))
        for axis in RANGE_ENABLED_KEYS:
            low, high = self._bounds(axis)
            self.forward_controller_state_updates(
                RANGE_ENABLED_KEYS[axis](
                    "enabled" if self._range_enabled.get(axis, True) else "disabled"
                ),
                RANGE_KEYS[axis, "min"](low),
                RANGE_KEYS[axis, "max"](high),
            )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            name for name in codec.OPERATIONS if name != "neutral" and self._control_enabled(name)
        ) + (("memory_1", "memory_2") if self.supports_memory_presets else ())

    def _control_enabled(self, control: str) -> bool:
        if control == "concurrent_push":
            return bool(self._mask & 15)
        return bool(self._mask & codec.CAPABILITIES.get(control.rsplit("_", 1)[0], 0))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or duration_ms <= 0:
            raise ValueError("Unavailable Paramount control or duration")
        if control.startswith("gearing_") and any(
            self._range_enabled.get(axis, True) and self._bounds(axis) != (0, maximum)
            for axis, maximum in (("head", self.profile.head_max), ("legs", self.profile.legs_max))
        ):
            raise ValueError(
                "Linked movement is unavailable while enabled head or leg ranges are narrowed"
            )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = []
        for axis in ("head", "legs", "height", "gearing"):
            if not self._mask & codec.CAPABILITIES[axis]:
                continue

            async def up(ctrl: BedController, name: str = axis + "_up") -> None:
                if isinstance(ctrl, ParamountController):
                    await ctrl._press(name)

            async def down(ctrl: BedController, name: str = axis + "_down") -> None:
                if isinstance(ctrl, ParamountController):
                    await ctrl._press(name)

            specs.append(
                MotorControlSpec(
                    axis,
                    {"height": "bed_height", "gearing": "paramount_gearing"}.get(axis, axis),
                    up,
                    down,
                    lambda ctrl: ctrl.stop_all(),
                    position_key=axis if axis in ("head", "legs") else None,
                    max_angle=self.profile.legs_max if axis == "legs" else self.profile.head_max,
                    hold=ControllerMotorHoldSpec(
                        axis + "_up", axis + "_down", stop_scope="side", press_hold_ms=None
                    ),
                )
            )
        return tuple(specs)

    @property
    def position_seek_policy(self) -> PositionSeekPolicy:
        return ParamountPositionSeekPolicy(self)

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return tuple(
            build_position_number_spec(
                axis,
                max_value=self.profile.legs_max if axis == "legs" else self.profile.head_max,
                unit="°",
            )
            for axis in ("head", "legs")
            if self._mask & codec.CAPABILITIES[axis]
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if self.supports_memory_presets and key in ("preset_memory_1", "preset_memory_2"):
            return ControllerHoldSpec(key.removeprefix("preset_"))
        return None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        async def register(ctrl: BedController) -> None:
            if isinstance(ctrl, ParamountController):
                await ctrl.enter_registration()

        async def concurrent(ctrl: BedController) -> None:
            if isinstance(ctrl, ParamountController):
                await ctrl._press("concurrent_push")

        result = [
            ControllerButtonSpec(
                "paramount_registration",
                "Enter registration mode",
                register,
                icon="mdi:bluetooth-connect",
            )
        ]
        if self._mask & 15:
            result.append(
                ControllerButtonSpec(
                    "paramount_concurrent_push",
                    "Concurrent push",
                    concurrent,
                    hold=ControllerHoldSpec("concurrent_push"),
                )
            )
        return tuple(result)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs = []
        for name, key in SETTING_KEYS.items():
            options = ("slow", "fast") if name == "speed" else ("allowed", "prohibited")

            async def select(
                ctrl: BedController,
                option: str,
                setting: str = name,
                choices: tuple[str, ...] = options,
            ) -> None:
                if isinstance(ctrl, ParamountController):
                    await ctrl._change_setting(setting, option == choices[1])

            specs.append(
                ControllerSelectSpec("paramount_" + name, "paramount_" + name, key, options, select)
            )

        async def duration(ctrl: BedController, option: str) -> None:
            if isinstance(ctrl, ParamountController):
                ctrl._duration = option
                ctrl._publish_preferences()

        specs.append(
            ControllerSelectSpec(
                "paramount_duration",
                "paramount_duration",
                DURATION,
                ("hold", "1", "2", "3", "4"),
                duration,
            )
        )
        for axis, key in RANGE_ENABLED_KEYS.items():
            if not self._mask & codec.CAPABILITIES[axis]:
                continue

            async def enabled(ctrl: BedController, option: str, name: str = axis) -> None:
                if isinstance(ctrl, ParamountController):
                    ctrl._range_enabled[name] = option == "enabled"
                    ctrl._publish_preferences()

            specs.append(
                ControllerSelectSpec(str(key), str(key), key, ("enabled", "disabled"), enabled)
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        for (axis, end), key in RANGE_KEYS.items():
            if not self._mask & codec.CAPABILITIES[axis]:
                continue

            async def set_range(
                ctrl: BedController, value: float, name: str = axis, limit: str = end
            ) -> None:
                if isinstance(ctrl, ParamountController):
                    low, high = ctrl._bounds(name)
                    low, high = (int(value), high) if limit == "min" else (low, int(value))
                    if low > high:
                        raise ValueError("Minimum must not exceed maximum")
                    ctrl._ranges[name] = (low, high)
                    ctrl._publish_preferences()

            max_value = (
                self._height_bounds[1]
                if axis == "height"
                else self.profile.legs_max
                if axis == "legs"
                else self.profile.head_max
            )
            specs.append(
                ControllerNumberSpec(
                    str(key),
                    str(key),
                    key,
                    self._height_bounds[0] if axis == "height" else 0,
                    max_value,
                    1,
                    set_range,
                    native_unit_of_measurement="cm" if axis == "height" else "°",
                )
            )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "paramount_capabilities",
                "paramount_capabilities",
                CAPABILITY,
                "mdi:bed",
                attribute_keys=(DEVICE_DATA,),
            ),
            ControllerStateSensorSpec(
                "paramount_height", "paramount_height", HEIGHT, "mdi:arrow-expand-vertical", "cm"
            ),
            ControllerStateSensorSpec("paramount_tilt", "paramount_tilt", TILT, "mdi:angle-acute"),
            ControllerStateSensorSpec(
                "paramount_rssi", "paramount_rssi", RSSI, "mdi:signal", "dBm"
            ),
            ControllerStateSensorSpec(
                "paramount_serial", "paramount_serial", SERIAL, "mdi:identifier"
            ),
            ControllerStateSensorSpec(
                "paramount_session_state", "paramount_session_state", SESSION_STATE, "mdi:bluetooth"
            ),
            ControllerStateSensorSpec(
                "paramount_registration_result",
                "paramount_registration_result",
                REGISTRATION_RESULT,
                "mdi:bluetooth-connect",
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._subscribed:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Paramount is disconnected")
        generation = self._generation

        def notify(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if generation == self._generation:
                self._notification(bytes(data))

        await client.start_notify(codec.NOTIFY_UUID, notify)
        self._subscribed = True

    def _notification(self, data: bytes) -> None:
        self.forward_raw_notification(codec.NOTIFY_UUID, data)
        reply = codec.parse(data)
        if reply is None:
            return
        if reply.opcode == 1:
            self.forward_controller_state_updates(SESSION_STATE(reply.payload[0]))
        elif reply.opcode == 2:
            self._mask = reply.payload[10]
            self._height_bounds = (reply.payload[6], reply.payload[7])
            self.forward_controller_state_updates(
                CAPABILITY(self._mask), DEVICE_DATA(tuple(reply.payload))
            )
            self._publish_preferences()
        elif reply.opcode == 3:
            self._settings = reply.settings
            for name, (index, mask) in codec.SETTING_BITS.items():
                enabled = bool(self._settings.flags[index] & mask)
                self.forward_controller_state_updates(
                    SETTING_KEYS[name](
                        ("fast" if enabled else "slow")
                        if name == "speed"
                        else ("prohibited" if enabled else "allowed")
                    )
                )
        elif reply.opcode == 4:
            self._posture = codec.posture(reply.payload[1:5])
            head, legs, height, tilt = self._posture
            if self._notify_callback:
                if self._mask & 1 and head != 255:
                    self._notify_callback("head", head)
                if self._mask & 2 and legs != 255:
                    self._notify_callback("legs", legs)
            self.forward_controller_state_updates(
                HEIGHT(None if height == 255 else height), TILT(tilt)
            )
            if reply.rssi is not None:
                self.forward_controller_state_updates(RSSI(reply.rssi))
        elif reply.opcode == 6:
            self.forward_controller_state_updates(REGISTRATION_RESULT(reply.payload[0]))
        if (
            self._pending is not None
            and not self._pending.done()
            and reply.opcode == self._expected
        ):
            self._last_reply = asyncio.get_running_loop().time()
            self._pending.set_result(reply)

    async def _exchange(self, command: bytes, cancel: asyncio.Event | None = None) -> codec.Reply:
        """One matched reply, no replay on missing response, and prompt cancellation."""
        event = cancel if cancel is not None else self._coordinator.cancel_command
        if event.is_set():
            raise asyncio.CancelledError
        delay = (
            self._last_reply
            + self.profile.response_delay_ms / 1000
            - asyncio.get_running_loop().time()
        )
        if delay > 0:
            try:
                await asyncio.wait_for(event.wait(), delay)
            except TimeoutError:
                pass
        if event.is_set():
            raise asyncio.CancelledError
        pending = asyncio.get_running_loop().create_future()
        self._pending, self._expected = pending, command[1] - 128
        cancelled = asyncio.create_task(event.wait())
        try:
            await self.write_command(command, cancel_event=event)
            done, _ = await asyncio.wait(
                (pending, cancelled),
                timeout=self.profile.response_timeout_ms / 1000,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled in done:
                raise asyncio.CancelledError
            if pending not in done:
                raise TimeoutError("Paramount did not reply; command was not replayed")
            return pending.result()
        finally:
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            pending.cancel()
            self._pending, self._expected = None, None

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        await asyncio.sleep(self.profile.initial_delay_ms / 1000)
        # A fresh connect-wait advertisement proves the registration phase, not
        # a requirement to bond. HA's optional bond flow owns OS pairing.
        info = bluetooth.async_last_service_info(session.hass, session.address, connectable=True)
        if info and codec.CONNECT_WAIT_UUID in {value.lower() for value in info.service_uuids}:
            await self.enter_registration()
            raise ConnectionError(
                "Paramount entered registration mode. Reconnect after its registration advertisement appears; use HA Bluetooth pairing if the bed requests it."
            )
        async with asyncio.timeout(30):
            while (await self._exchange(codec.frame(0x81), asyncio.Event())).payload[0] != 6:
                pass
        await self._exchange(codec.frame(0x82), asyncio.Event())
        await self._exchange(codec.frame(0x83), asyncio.Event())
        await self._exchange(codec.control(0), asyncio.Event())
        client = session.client
        if client is not None and client.services.get_characteristic(codec.SERIAL_UUID) is not None:
            await asyncio.sleep(self.profile.initial_delay_ms / 1000)
            async with self.ble_lock:
                self._serial = bytes(await client.read_gatt_char(codec.SERIAL_UUID)).hex()
            self.forward_controller_state_updates(SERIAL(self._serial))
        session.persist_capability_snapshot()

    async def enter_registration(self) -> None:
        """Send the app's fixed registration request, without inventing result meanings."""
        await self.write_command(codec.frame(0x86, b"AUTH_REQ"))

    async def stop_notify(self) -> None:
        client = self.client
        was_subscribed = self._subscribed
        self.on_disconnect()
        if was_subscribed and client is not None and client.is_connected:
            await client.stop_notify(codec.NOTIFY_UUID)
        self._notify_callback = None

    def on_disconnect(self) -> None:
        self._generation += 1
        self._subscribed = False
        self._settings = None
        self._posture = None
        if self._pending is not None and not self._pending.done():
            self._pending.set_exception(ConnectionError("Paramount disconnected"))
        self.forward_controller_state_updates(
            *(key(None) for key in (HEIGHT, TILT, RSSI, SESSION_STATE, REGISTRATION_RESULT)),
            *(key(None) for key in SETTING_KEYS.values()),
        )

    @property
    def diagnostic_poll_interval(self) -> float:
        return self.profile.response_delay_ms / 1000

    async def async_refresh_diagnostics(self) -> None:
        await self.read_positions()

    async def read_positions(self, motor_count: int = 2) -> None:
        await self._exchange(codec.control(0))
        self._idle_replies += 1
        if self._idle_replies >= 5:
            self._idle_replies = 0
            await self._exchange(codec.frame(0x83))

    async def _send_stop(self) -> None:
        # Release does not wait on the missing reply that may have stopped motion.
        await self.write_command(codec.control(0), cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        await self._send_stop()

    async def _press(self, control: str) -> None:
        await self.hold_control(
            control, 1000 if self._duration == "hold" else int(self._duration) * 1000
        )

    def _at_limit(self, name: str) -> bool:
        if name == "concurrent_push" or name.startswith("memory_"):
            return False
        axis, direction = name.rsplit("_", 1)
        if not self._range_enabled.get(axis, True):
            return True
        if self._posture is None:
            return False
        index = {"head": 0, "legs": 1, "height": 2, "gearing": 0}[axis]
        value = self._posture[index]
        low, high = self._bounds(axis)
        return value != 255 and (value >= high if direction == "up" else value <= low)

    def _memory_frame(self, slot: int) -> bytes:
        self.validate_memory_recall(slot)
        settings = self._settings
        if settings is None:
            raise ValueError("Read current Paramount settings before recall")
        values = list(settings.memory1 if slot == 1 else settings.memory2)
        for index, axis in enumerate(("head", "legs", "height")):
            low, high = self._bounds(axis)
            full = (
                self._height_bounds
                if axis == "height"
                else (0, self.profile.legs_max if axis == "legs" else self.profile.head_max)
            )
            values[index] = codec.clip_memory(
                values[index],
                low,
                high,
                self._range_enabled.get(axis, True) and (low, high) == full,
                height=axis == "height",
            )
        return codec.control(0x15 + slot, codec.posture(bytes(values)))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control.startswith("memory_"):
            await self._exchange(codec.frame(0x83))
        command = (
            self._memory_frame(int(control[-1]))
            if control.startswith("memory_")
            else codec.control(codec.OPERATIONS[control])
        )
        timeout = asyncio.timeout(duration_ms / 1000)
        try:
            try:
                async with timeout:
                    await asyncio.sleep(self.profile.press_delay_ms / 1000)
                    while not self._coordinator.cancel_command.is_set() and not self._at_limit(
                        control
                    ):
                        await self._exchange(command)
            except TimeoutError:
                if not timeout.expired():
                    raise
        finally:
            await self._send_stop()

    async def preset_memory(self, memory_num: int) -> None:
        await self._press(f"memory_{memory_num}")

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._exchange(codec.frame(0x83))
        await self._exchange(codec.control(0))
        if self._settings is None or self._posture is None:
            raise ValueError("Paramount needs fresh settings and positions to save memory")
        await self._save_settings(self._settings.save(memory_num, self._posture))

    async def _change_setting(self, name: str, enabled: bool) -> None:
        await self._exchange(codec.frame(0x83))
        if self._settings is None:
            raise ValueError("Paramount settings are unavailable")
        await self._save_settings(self._settings.setting(name, enabled))

    async def _save_settings(self, desired: codec.Settings) -> None:
        await self._exchange(desired.encode())
        actual = await self._exchange(codec.frame(0x83))
        # The app checks XOR equality, which can collide. Compare all fields.
        if actual.settings != desired:
            raise ValueError("Paramount settings readback did not match; write was not replayed")
        await self._exchange(codec.control(0))

    async def move_head_up(self) -> None:
        await self._press("head_up")

    async def move_head_down(self) -> None:
        await self._press("head_down")

    async def move_legs_up(self) -> None:
        await self._press("legs_up")

    async def move_legs_down(self) -> None:
        await self._press("legs_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        raise NotImplementedError("Paramount has no dedicated flat command")


async def build_controller(ctx: BuildContext) -> ParamountController:
    return ParamountController(ctx.coordinator, ctx.stored_capabilities("paramount"))
