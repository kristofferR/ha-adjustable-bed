"""Model-gated controls from the accepted Malouf and Lucid application reports."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.util import dt as dt_util

from ..malouf_app_protocol import (
    TRANSPORT_PROFILES,
    encode_alarm,
    encode_command,
    encode_time,
    get_profile,
    parse_notification,
    query_after,
)
from .base import (
    BedController,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_HOLD_INTERVAL = 0.15
_ALL_AXES = frozenset({"back", "legs", "head", "lumbar", "dual", "full_tilt"})
_MINUTES_KEY = "malouf_app_massage_minutes"
_LIGHT_KEY = "malouf_app_under_bed_light"
_ALARM_TYPES = {
    "zero_g": 13,
    "lounge": 14,
    "tv": 15,
    "anti_snore": 16,
    "memory_1": 17,
    "memory_2": 18,
    "massage": 20,
    "flat": 21,
}
_WEEKDAY_BITS = (2, 4, 8, 16, 32, 64, 128)


def _manual_callback(action: str) -> MotorCommandCallable:
    """Bind only the action; a reconnect supplies the current controller."""

    async def execute(controller: BedController) -> None:
        if not isinstance(controller, MaloufAppController):
            raise TypeError("Malouf app action requires its configured controller")
        await controller.execute_action(action)

    return execute


class MaloufAppController(BedController):
    """Keep model capability gates separate from explicit GATT transport choice."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app_profile: str,
        model: str,
        transport: str,
        primary: bool = True,
    ) -> None:
        super().__init__(coordinator)
        self._profile = get_profile(app_profile, model, transport)
        self._transport = transport
        self._gatt = TRANSPORT_PROFILES[transport]
        self._app_profile = app_profile
        self._model = model
        self._primary = primary
        self._subscribed = False
        self._massage_minutes: int | None = None
        self._light: int | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._gatt.write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return self._gatt.notify_uuid is not None

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 150

    async def async_discover_capabilities(self) -> None:
        """Validate the selected coherent service profile before application commands."""
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        services = client.services
        write_service = services.get_service(self._gatt.service_uuid)
        write_char = (
            write_service.get_characteristic(self._gatt.write_uuid) if write_service else None
        )
        if write_char is None or "write-without-response" not in write_char.properties:
            raise ValueError(
                "Configured app write characteristic does not support unacknowledged writes"
            )
        if self._gatt.notify_uuid:
            notify_service_uuid = self._gatt.notify_service_uuid
            if notify_service_uuid is None:
                raise ValueError("Configured app notification service is absent")
            notify_service = services.get_service(notify_service_uuid)
            notify_char = (
                notify_service.get_characteristic(self._gatt.notify_uuid)
                if notify_service
                else None
            )
            if notify_char is None or "notify" not in notify_char.properties:
                raise ValueError(
                    "Configured app notification characteristic is absent or not notifiable"
                )

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def allow_position_polling_during_commands(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        mappings = (
            ("back", "headUp", "headDown"),
            ("legs", "footUp", "footDown"),
            ("head", "headTiltUp", "headTiltDown"),
            ("head", "tiltHeadUp", "tiltHeadDown"),
            ("lumbar", "lumbarUp", "lumbarDown"),
            ("dual", "dualUp", "dualDown"),
            ("dual", "allUp", "allDown"),
            ("full_tilt", "fullTiltUp", "fullTiltDown"),
        )
        specs: dict[str, MotorControlSpec] = {}
        for key, up, down in mappings:
            if up in self._profile.manual and down in self._profile.manual:
                specs[key] = MotorControlSpec(
                    key=key,
                    translation_key=key,
                    open_fn=_manual_callback(up),
                    close_fn=_manual_callback(down),
                    stop_fn=lambda controller: controller.stop_all(),
                )
        return tuple(specs.values())

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return _ALL_AXES - {spec.key for spec in self.motor_control_specs}

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbarUp" in self._profile.manual

    @property
    def supports_preset_flat(self) -> bool:
        return "allFlat" in self._profile.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zeroG" in self._profile.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "antiSnore" in self._profile.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tvRead" in self._profile.presets

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self._profile.presets

    @property
    def supports_preset_read(self) -> bool:
        return "read" in self._profile.presets

    @property
    def memory_slot_count(self) -> int:
        return self._profile.memory_slots

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_massage(self) -> bool:
        return any(action.startswith("massage") for action in self._profile.other)

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return "massageOff" in self._profile.other

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return "massageHead" in self._profile.other

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return "massageFoot" in self._profile.other

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return "massageWave" in self._profile.other

    @property
    def supports_massage_timer_cycle_control(self) -> bool:
        return "massageTimer" in self._profile.other

    @property
    def supports_massage_timer(self) -> bool:
        return "massageTimerSet" in self._profile.other

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage_timer else []

    @property
    def supports_lights(self) -> bool:
        return "lightSwitch" in self._profile.other

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self.requires_notification_channel or not self.supports_massage:
            return ()
        return (
            ControllerStateSensorSpec(
                key=_MINUTES_KEY,
                translation_key=_MINUTES_KEY,
                state_key=_MINUTES_KEY,
                icon="mdi:timer-outline",
                native_unit_of_measurement="min",
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if not self.supports_lights or self._transport not in {"command32_legacy", "command32_new"}:
            return ()
        return (
            ControllerStateBinarySensorSpec(
                key=_LIGHT_KEY,
                translation_key=_LIGHT_KEY,
                state_key=_LIGHT_KEY,
                icon="mdi:led-strip-variant",
                attribute_keys=("malouf_app_light_raw",),
            ),
        )

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset({_MINUTES_KEY}) - {spec.key for spec in self.controller_state_sensor_specs}

    @property
    def stale_controller_state_binary_sensor_entity_keys(self) -> frozenset[str]:
        return frozenset({_LIGHT_KEY}) - {
            spec.key for spec in self.controller_state_binary_sensor_specs
        }

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "app_profile": self._app_profile,
            "model": self._model,
            "transport": self._transport,
            "primary": self._primary,
        }

    def _packet(self, action: str, *, primary: bool | None = None) -> bytes:
        return encode_command(
            action,
            self._transport,
            primary=self._primary if primary is None else primary,
            device_name=self._coordinator.ble_device_name or "",
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 0,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    async def _wait(self, delay: float, cancel: asyncio.Event) -> bool:
        try:
            async with asyncio.timeout(delay):
                await cancel.wait()
        except TimeoutError:
            return True
        return False

    async def _hold(self, action: str, *, primary: bool | None = None) -> None:
        cancel = self._coordinator.cancel_command
        packet = self._packet(action, primary=primary)
        if cancel.is_set():
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        try:
            for index in range(self._coordinator.motor_pulse_count):
                if cancel.is_set():
                    return
                await self.write_command(packet, cancel_event=cancel)
                if index < self._coordinator.motor_pulse_count - 1:
                    deadline += _HOLD_INTERVAL
                    if not await self._wait(max(0, deadline - loop.time()), cancel):
                        return
        finally:
            # The app delays its explicit release by one 150 ms tick on UP/CANCEL.
            await asyncio.sleep(_HOLD_INTERVAL)
            await self.write_command(
                self._packet("stopDriver", primary=primary), cancel_event=asyncio.Event()
            )

    async def _preset(self, action: str, *, primary: bool | None = None) -> None:
        repeats = 3 if self._transport in {"command32_legacy", "command32_middle"} else 1
        release = self._transport in {"opcode_legacy", "command32_middle", "command32_new"}
        failed = True
        try:
            await self.write_command(self._packet(action, primary=primary), repeat_count=repeats)
            failed = self._coordinator.cancel_command.is_set()
        finally:
            if release or failed:
                await self.write_command(
                    self._packet("stopDriver", primary=primary), cancel_event=asyncio.Event()
                )

    @property
    def app_action_options(self) -> tuple[str, ...]:
        return (
            "stopDriver",
            *self._profile.manual,
            *self._profile.presets,
            *(
                action
                for action in self._profile.other
                if action not in {"alarm", "massageTimerSet"}
            ),
            *(f"memory{slot}" for slot in range(1, self.memory_slot_count + 1)),
            *(f"setMemory{slot}" for slot in self._profile.programming_slots),
        )

    async def execute_app_action(self, action: str, *, primary: bool | None = None) -> None:
        if action not in self.app_action_options:
            raise ValueError(f"Action {action!r} is not supported by this app/model/transport")
        if primary is not None and not isinstance(primary, bool):
            raise ValueError("Primary selector must be boolean")
        if action == "stopDriver":
            await self.write_command(
                self._packet(action, primary=primary), cancel_event=asyncio.Event()
            )
        elif action.startswith("setMemory"):
            await self._program_memory(int(action[-1]), primary=primary)
        elif action in self._profile.manual:
            await self._hold(action, primary=primary)
        elif action in self._profile.presets or action.startswith("memory"):
            await self._preset(action, primary=primary)
        else:
            await self.write_command(self._packet(action, primary=primary))
            if query_after(action, self._transport):
                await self.write_command(bytes.fromhex("00 b0"))

    async def execute_action(self, action: str) -> None:
        """Execute only a reachable action from the explicitly selected model."""
        await self.execute_app_action(action)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._gatt.notify_uuid is None or self._subscribed:
            return
        await self.async_discover_capabilities()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        await client.start_notify(self._gatt.notify_uuid, self._notification_handler)
        self._subscribed = True

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        state = parse_notification(self._transport, bytes(data))
        if state is None:
            return
        updates: dict[str, Any] = {}
        if self.controller_state_sensor_specs and state.massage_minutes != self._massage_minutes:
            updates[_MINUTES_KEY] = state.massage_minutes
        if self.controller_state_binary_sensor_specs and state.light != self._light:
            updates[_LIGHT_KEY] = state.light == 1
            updates["malouf_app_light_raw"] = state.light
            updates["under_bed_lights_on"] = state.light == 1
        self._massage_minutes = state.massage_minutes
        self._light = state.light
        if updates:
            self.forward_controller_state_updates(updates)

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if self._subscribed and self._gatt.notify_uuid and client and client.is_connected:
                await client.stop_notify(self._gatt.notify_uuid)
        finally:
            self._subscribed = False
            self._notify_callback = None

    @property
    def supports_clock_alarm(self) -> bool:
        return self._transport.startswith("command32_")

    @property
    def clock_alarm_presets(self) -> tuple[str, ...]:
        # Persisted alarm records are independent of the ordinary model controls.
        return tuple(_ALARM_TYPES) if self.supports_clock_alarm else ()

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        if not self.supports_clock_alarm:
            raise NotImplementedError("This transport has no clock alarm")
        if not isinstance(enabled, bool) or head_level != 0 or foot_level != 0:
            raise ValueError("Clock alarms require a boolean enabled flag and no massage levels")
        clear = encode_alarm(self._transport, 0, 0, 0, 0)
        copies = 1 if self._transport == "command32_new" else 3
        if not enabled:
            await self.write_command(clear, repeat_count=copies)
            return
        if preset not in self.clock_alarm_presets:
            raise ValueError("Unsupported clock alarm preset")
        if any(type(day) is not int or not 0 <= day <= 6 for day in weekdays):
            raise ValueError("Weekdays must be integers from Monday zero to Sunday six")
        now = dt_util.now()
        repeats = 0
        if weekdays:
            repeats = 1
            for day in weekdays:
                repeats |= _WEEKDAY_BITS[day]
        else:
            # Validate before comparing time components or sending the clear command.
            encode_alarm(self._transport, hour, minute, _ALARM_TYPES[preset], 0)
            target = now + timedelta(days=int((now.hour, now.minute) >= (hour, minute)))
            repeats = _WEEKDAY_BITS[target.weekday()]
        alarm = encode_alarm(self._transport, hour, minute, _ALARM_TYPES[preset], repeats)
        clock = encode_time(self._transport, now)
        await self.write_command(clear, repeat_count=copies)
        await self.write_command(clock, repeat_count=copies)
        await self.write_command(alarm, repeat_count=copies)

    async def stop_all(self) -> None:
        await self.write_command(self._packet("stopDriver"), cancel_event=asyncio.Event())

    async def move_back_up(self) -> None:
        await self.execute_action("headUp")

    async def move_back_down(self) -> None:
        await self.execute_action("headDown")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.execute_action("footUp")

    async def move_legs_down(self) -> None:
        await self.execute_action("footDown")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self.execute_action(
            "tiltHeadUp" if "tiltHeadUp" in self._profile.manual else "headTiltUp"
        )

    async def move_head_down(self) -> None:
        await self.execute_action(
            "tiltHeadDown" if "tiltHeadDown" in self._profile.manual else "headTiltDown"
        )

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("This app has no separate fourth foot actuator")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("This app has no separate fourth foot actuator")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.execute_action("lumbarUp")

    async def move_lumbar_down(self) -> None:
        await self.execute_action("lumbarDown")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.execute_action("allFlat")

    async def preset_zero_g(self) -> None:
        await self.execute_action("zeroG")

    async def preset_anti_snore(self) -> None:
        await self.execute_action("antiSnore")

    async def preset_tv(self) -> None:
        await self.execute_action("tvRead")

    async def preset_lounge(self) -> None:
        await self.execute_action("lounge")

    async def preset_read(self) -> None:
        await self.execute_action("read")

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Memory slot is not exposed by this model")
        await self._preset(f"memory{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Memory slot is not exposed by this model")
        await self._program_memory(memory_num)

    async def _program_memory(self, memory_num: int, *, primary: bool | None = None) -> None:
        if memory_num not in self._profile.programming_slots:
            raise ValueError("Memory slot is not exposed by this model")
        packet = self._packet(f"setMemory{memory_num}", primary=primary)
        if self._transport.startswith("opcode_"):
            await self.write_command(packet)
            return
        repeats, delay = (55, 0.1) if self._transport == "command32_new" else (85, 0.15)
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        # The app waits before the first write and ends refresh without a release.
        # Its terminal string is not a valid command; never invent that packet.
        for _ in range(repeats):
            deadline += delay
            if not await self._wait(max(0, deadline - loop.time()), cancel):
                return
            await self.write_command(packet, cancel_event=cancel)

    async def lights_toggle(self) -> None:
        await self.execute_action("lightSwitch")

    async def massage_head_toggle(self) -> None:
        await self.execute_action("massageHead")

    async def massage_foot_toggle(self) -> None:
        await self.execute_action("massageFoot")

    async def massage_mode_step(self) -> None:
        await self.execute_action("massageWave")

    async def massage_timer_cycle(self) -> None:
        await self.execute_action("massageTimer")

    async def massage_off(self) -> None:
        await self.execute_action("massageOff")

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise ValueError("Massage duration is not exposed by this model")
        await self.write_command(self._packet(f"massage{minutes}"))

    def get_massage_state(self) -> dict[str, Any]:
        return (
            {"timer_mode": str(self._massage_minutes)} if self._massage_minutes is not None else {}
        )

    def get_light_state(self) -> dict[str, Any]:
        if self._light is None or not self.controller_state_binary_sensor_specs:
            return {}
        return {"is_on": self._light == 1}
