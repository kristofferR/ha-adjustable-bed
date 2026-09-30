"""Opt-in, model-gated controller for the frozen Malouf/Lucid app profiles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ..malouf_app_protocol import (
    ALARM_TYPES,
    APP_MODEL_OPTIONS,
    MALOUF_APP_MODELS,
    OKIN_COMMANDS,
    RICHMAT_COMMANDS,
    SELECTOR_ACTIONS,
    TRANSPORTS,
    alarm_frame,
    clock_frame,
    command_frame,
    parse_notification,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


def _app_callback(action: str) -> MotorCommandCallable:
    """Resolve profile-specific controls against the current controller."""

    async def invoke(controller: BedController | SideBoundController) -> None:
        if not isinstance(controller, MaloufAppController) and not (
            isinstance(controller, SideBoundController)
            and isinstance(controller._controller, MaloufAppController)
        ):
            raise TypeError("This action requires a Malouf/Lucid app profile")
        await controller.execute_app_control(action)

    return invoke


class MaloufAppController(BedController):
    """Keep retail model, physical role, and GATT transport independent."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app_profile: str,
        model: str,
        transport: str = "auto",
        primary: bool = True,
    ) -> None:
        super().__init__(coordinator)
        if app_profile not in APP_MODEL_OPTIONS:
            raise ValueError("App profile must be malouf or lucid")
        if model not in MALOUF_APP_MODELS:
            raise ValueError(f"Unknown Malouf/Lucid model: {model}")
        if transport != "auto" and transport not in TRANSPORTS:
            raise ValueError(f"Unknown Malouf/Lucid transport: {transport}")
        if not isinstance(primary, bool):
            raise ValueError("Primary role must be a boolean")
        self.app_profile = app_profile
        self.model = model
        self._profile = MALOUF_APP_MODELS[model]
        self._configured_transport = transport
        self._transport: str | None = None if transport == "auto" else transport
        self._primary = primary
        self._notify_uuid: str | None = None
        self._massage_remaining: int | None = None
        self._light_status: int | None = None

    @property
    def transport(self) -> str | None:
        """Return the coherent transport selected for this connection."""
        return self._transport

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app_profile": self.app_profile,
            "model": self.model,
            "transport": self._transport,
            "configured_transport": self._configured_transport,
            "primary": self._primary,
            "massage_remaining_minutes": self._massage_remaining,
            "underbed_light_status": self._light_status,
        }

    @property
    def control_characteristic_uuid(self) -> str:
        if self._transport is None:
            raise ValueError("Malouf/Lucid app transport has not been discovered")
        return TRANSPORTS[self._transport].command_characteristic

    def _name_family(self) -> str:
        name = self._coordinator.observed_ble_device_name
        if name is None:
            return "okin"
        if "X1RM" in name or "QRRM" in name:
            return "richmat"
        if "OKIN" in name or "Smartbed" in name:
            return "okin"
        raise ValueError(
            "Device name does not identify a Malouf/Lucid app transport; select one explicitly"
        )

    @property
    def _family(self) -> str | None:
        if self._transport is not None:
            return TRANSPORTS[self._transport].family
        try:
            return self._name_family()
        except ValueError:
            return None

    def _resolve_transport(self) -> str:
        client = self.client
        if client is None or not client.is_connected or not client.services:
            raise ConnectionError("Malouf/Lucid app transport requires discovered GATT services")
        services = {service.uuid.lower(): service for service in client.services}

        def has_command_service(key: str) -> bool:
            spec = TRANSPORTS[key]
            return spec.command_service in services

        if self._configured_transport == "auto":
            family = self._name_family()
            candidates = [
                key
                for key, spec in TRANSPORTS.items()
                if spec.family == family and has_command_service(key)
            ]
            if len(candidates) != 1:
                self._transport = None
                raise ValueError(
                    "Ambiguous or missing Malouf/Lucid GATT transport; select the transport explicitly"
                )
            resolved = candidates[0]
        else:
            resolved = self._configured_transport
        spec = TRANSPORTS[resolved]

        def role(service_uuid: str, char_uuid: str, property_name: str) -> None:
            matches = [
                char
                for service in client.services
                if service.uuid.lower() == service_uuid
                for char in service.characteristics
                if char.uuid.lower() == char_uuid
            ]
            if len(matches) != 1 or property_name not in matches[0].properties:
                raise ValueError(
                    f"Transport {resolved} requires {property_name} characteristic {char_uuid} in service {service_uuid}"
                )

        # Numeric Android write type 2 is WRITE_TYPE_DEFAULT, not type 1.
        role(spec.command_service, spec.command_characteristic, "write")
        if spec.notify_service is not None and spec.notify_characteristic is not None:
            role(spec.notify_service, spec.notify_characteristic, "notify")
        self._transport = resolved
        return resolved

    async def async_discover_capabilities(self) -> None:
        self._resolve_transport()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 150,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        self._resolve_transport()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=True,
            wall_clock_pacing=True,
        )

    def _frames(self, action: str) -> tuple[bytes, ...]:
        transport = self._resolve_transport()
        commands = RICHMAT_COMMANDS if self._family == "richmat" else OKIN_COMMANDS
        if action not in commands:
            raise ValueError(f"Action {action} is unavailable on {transport}")
        # Native paired sides name physical devices, not P1 primary/secondary
        # roles. The configured role remains authoritative on bound children.
        selector = int(not self._primary) if action in SELECTOR_ACTIONS else 0
        return (command_frame(transport, commands[action], selector=selector),)

    async def _action(self, action: str) -> None:
        for frame in self._frames(action):
            await self.write_command(frame)
        if self._transport == "okin_new" and action in {
            "light",
            "massage_head",
            "massage_foot",
            "massage_wave",
            "massage_timer_step",
        }:
            await self.write_command(b"\x00\xb0")

    async def _send_stop(self) -> None:
        for frame in self._frames("stop"):
            await self.write_command(frame, cancel_event=asyncio.Event())

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 150

    async def _motion(self, action: str, duration_ms: int | None = None) -> None:
        frames = self._frames(action)
        count, delay = self.motor_pulse_settings()
        if duration_ms is not None:
            if duration_ms <= 0:
                raise ValueError("Movement duration must be positive")
            count = self.timed_move_repeat_count(duration_ms, delay)
        deadline = asyncio.timeout(None if duration_ms is None else duration_ms / 1000)
        controller_timed_out = False
        try:
            try:
                async with deadline:
                    try:
                        for frame in frames:
                            await self.write_command(
                                frame, repeat_count=count, repeat_delay_ms=delay
                            )
                    except TimeoutError:
                        controller_timed_out = True
                        raise
            except TimeoutError:
                if controller_timed_out or not deadline.expired():
                    raise
        finally:
            # The app releases 150 ms after its hold loop is cancelled.
            # The HA movement ceiling does not interrupt the release lane.
            stop_task = asyncio.create_task(self._release_motion())
            try:
                await asyncio.shield(stop_task)
            except asyncio.CancelledError:
                await stop_task
                raise

    async def _release_motion(self) -> None:
        await asyncio.sleep(0.15)
        await self._send_stop()

    async def _preset(self, action: str) -> None:
        frames = self._frames(action)
        transport = self._transport
        count = 3 if transport in {"okin_legacy", "okin_custom"} else 1
        stop = transport in {"richmat_single", "okin_custom", "okin_new"}
        try:
            for frame in frames:
                await self.write_command(frame, repeat_count=count, repeat_delay_ms=0)
        finally:
            if stop:
                await self._send_stop()

    def _require_manual(self, axis: str) -> None:
        if axis not in self._profile.manual:
            raise ValueError(f"Model {self.model} has no {axis} control")

    def _require_function(self, function: str) -> None:
        if function not in self._profile.functions:
            raise ValueError(f"Model {self.model} has no {function} control")

    def _has_preset(self, preset: str) -> bool:
        if preset not in self._profile.presets:
            return False
        # Lucid's persisted Good Life Oz-labelled presets are passed through
        # literally. They match Richmat, but not its Okin string switch.
        return not (
            self.app_profile == "lucid"
            and self.model.startswith("GoodLife")
            and self._family == "okin"
            and preset in {"zero_g", "anti_snore"}
        )

    async def move_head_up(self) -> None:
        self._require_manual("back")
        await self._motion("head_up")

    async def move_head_down(self) -> None:
        self._require_manual("back")
        await self._motion("head_down")

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        self._require_manual("legs")
        await self._motion("foot_up")

    async def move_feet_down(self) -> None:
        self._require_manual("legs")
        await self._motion("foot_down")

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def move_tilt_up(self) -> None:
        self._require_manual("tilt")
        await self._motion("tilt_up")

    async def move_tilt_down(self) -> None:
        self._require_manual("tilt")
        await self._motion("tilt_down")

    async def move_tilt_stop(self) -> None:
        await self._send_stop()

    async def move_lumbar_up(self) -> None:
        self._require_manual("lumbar")
        await self._motion("lumbar_up")

    async def move_lumbar_down(self) -> None:
        self._require_manual("lumbar")
        await self._motion("lumbar_down")

    async def move_lumbar_stop(self) -> None:
        await self._send_stop()

    async def move_tilt_head_up(self) -> None:
        self._require_manual("tilt_head")
        await self._motion("tilt_head_up")

    async def move_tilt_head_down(self) -> None:
        self._require_manual("tilt_head")
        await self._motion("tilt_head_down")

    async def move_full_tilt_up(self) -> None:
        self._require_manual("full_tilt")
        await self._motion("full_tilt_up")

    async def move_full_tilt_down(self) -> None:
        self._require_manual("full_tilt")
        await self._motion("full_tilt_down")

    async def stop_all(self) -> None:
        await self._send_stop()

    async def execute_app_control(self, action: str) -> None:
        """Dispatch only literal app controls that lack a standard base method."""
        if action == "read":
            await self.preset_read()
        elif action == "save_oz_memory_2":
            await self.save_oz_memory_position()
        elif action == "tilt_head_up":
            await self.move_tilt_head_up()
        elif action == "tilt_head_down":
            await self.move_tilt_head_down()
        elif action == "full_tilt_up":
            await self.move_full_tilt_up()
        elif action == "full_tilt_down":
            await self.move_full_tilt_down()
        else:
            raise ValueError(f"Unknown Malouf/Lucid app control: {action}")

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = [
            MotorControlSpec(
                "back",
                "back",
                lambda ctrl: ctrl.move_back_up(),
                lambda ctrl: ctrl.move_back_down(),
                lambda ctrl: ctrl.stop_all(),
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda ctrl: ctrl.move_legs_up(),
                lambda ctrl: ctrl.move_legs_down(),
                lambda ctrl: ctrl.stop_all(),
                max_angle=45,
            ),
        ]
        if "tilt" in self._profile.manual:
            specs.append(
                MotorControlSpec(
                    "tilt",
                    "tilt",
                    lambda ctrl: ctrl.move_tilt_up(),
                    lambda ctrl: ctrl.move_tilt_down(),
                    lambda ctrl: ctrl.stop_all(),
                )
            )
        if "lumbar" in self._profile.manual:
            specs.append(
                MotorControlSpec(
                    "lumbar",
                    "lumbar",
                    lambda ctrl: ctrl.move_lumbar_up(),
                    lambda ctrl: ctrl.move_lumbar_down(),
                    lambda ctrl: ctrl.stop_all(),
                )
            )
        if "tilt_head" in self._profile.manual and self._family == "richmat":
            specs.append(
                MotorControlSpec(
                    "malouf_tilt_head",
                    "malouf_tilt_head",
                    _app_callback("tilt_head_up"),
                    _app_callback("tilt_head_down"),
                    lambda ctrl: ctrl.stop_all(),
                )
            )
        if "full_tilt" in self._profile.manual and self._family == "richmat":
            specs.append(
                MotorControlSpec(
                    "malouf_full_tilt",
                    "malouf_full_tilt",
                    _app_callback("full_tilt_up"),
                    _app_callback("full_tilt_down"),
                    lambda ctrl: ctrl.stop_all(),
                )
            )
        return tuple(specs)

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        return frozenset(
            {"head", "feet", "tilt", "lumbar", "bed_height", "malouf_tilt_head", "malouf_full_tilt"}
            - {spec.key for spec in self.motor_control_specs}
        )

    @property
    def has_tilt_support(self) -> bool:
        return "tilt" in self._profile.manual

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self._profile.manual

    @property
    def supports_simultaneous_movement(self) -> bool:
        # Good Life's All label produces allUp/allDown, not dualUp/dualDown.
        # Only the Richmat string switch accepts those literal commands.
        return "dual" in self._profile.manual and not (
            self.model.startswith("GoodLife") and self._family != "richmat"
        )

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        return ("back", "legs") if self.supports_simultaneous_movement else ()

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        if (
            not self.supports_simultaneous_movement
            or {first_axis, second_axis} != {"back", "legs"}
            or first_up != second_up
        ):
            raise ValueError("This model can combine only back and legs in the same direction")
        await self._motion("dual_up" if first_up else "dual_down", duration_ms)

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._has_preset("zero_g")

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._has_preset("anti_snore")

    @property
    def supports_preset_tv(self) -> bool:
        return self._has_preset("tv")

    @property
    def supports_preset_lounge(self) -> bool:
        return self._has_preset("lounge")

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        if not self.supports_preset_zero_g:
            raise ValueError("Zero G preset is unavailable on this app/model/transport")
        await self._preset("zero_g")

    async def preset_anti_snore(self) -> None:
        if not self.supports_preset_anti_snore:
            raise ValueError("Anti Snore preset is unavailable on this app/model/transport")
        await self._preset("anti_snore")

    async def preset_tv(self) -> None:
        if not self.supports_preset_tv:
            raise ValueError("TV preset is unavailable on this model")
        await self._preset("tv")

    async def preset_lounge(self) -> None:
        if not self.supports_preset_lounge:
            raise ValueError("Lounge preset is unavailable on this model")
        await self._preset("lounge")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.app_profile == "lucid" and self.model == "Premium" and self._family == "okin":
            return (ControllerButtonSpec("malouf_read", "Read", _app_callback("read")),)
        if self._has_oz_memory_editor:
            return (
                ControllerButtonSpec(
                    "malouf_oz_save_memory_2", "Save Memory 2", _app_callback("save_oz_memory_2")
                ),
            )
        return ()

    async def preset_read(self) -> None:
        if not (self.app_profile == "lucid" and self.model == "Premium" and self._family == "okin"):
            raise ValueError("Read has no writable endpoint for this app/model/transport")
        await self._preset("lounge")

    @property
    def _has_oz_memory_editor(self) -> bool:
        return self.app_profile == "lucid" and self.model in {
            "GoodLifeBase",
            "GoodLifePremierBase",
            "GoodLifeProBase",
        }

    async def save_oz_memory_position(self) -> None:
        """Save slot 2 via Lucid's reachable Oz-preset long-hold editor."""
        if not self._has_oz_memory_editor:
            raise ValueError("This app/model has no Oz preset memory editor")
        await self._save_memory(2)

    @property
    def memory_slot_count(self) -> int:
        return self._profile.memory_slots

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    def _validate_memory(self, slot: int) -> None:
        if isinstance(slot, bool) or not 1 <= slot <= self.memory_slot_count:
            raise ValueError(f"Model {self.model} has no memory slot {slot}")

    async def preset_memory(self, memory_num: int) -> None:
        self._validate_memory(memory_num)
        await self._preset(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self._validate_memory(memory_num)
        await self._save_memory(memory_num)

    async def _save_memory(self, memory_num: int) -> None:
        """Deliver a validated standard save or the explicit Lucid editor save."""
        transport = self._resolve_transport()
        if self._family == "richmat":
            await self._action(f"save_{memory_num}")
            return
        command = 0x80040000 if memory_num == 2 else 0x10000
        name = self._coordinator.observed_ble_device_name
        if memory_num == 1 and name is not None and "smartbed238" in name.lower():
            command = 0x80010000
        count, delay = (55, 100) if transport == "okin_new" else (85, 150)
        await asyncio.sleep(delay / 1000)
        # The app's terminal "stopCommand" is unknown and emits no frame.
        await self.write_command(
            command_frame(transport, command), repeat_count=count, repeat_delay_ms=delay
        )

    @property
    def supports_lights(self) -> bool:
        return "light" in self._profile.functions

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights and self._transport in {"okin_legacy", "okin_new"}

    @property
    def requires_notification_channel(self) -> bool:
        """Keep massage/light telemetry active with angle sensing disabled."""
        return self._family == "okin"

    async def lights_on(self) -> None:
        self._require_function("light")
        if self._light_status is None:
            raise ValueError("Light state is unknown; use the native light toggle")
        if not self._light_status:
            await self.lights_toggle()

    async def lights_off(self) -> None:
        self._require_function("light")
        if self._light_status is None:
            raise ValueError("Light state is unknown; use the native light toggle")
        if self._light_status:
            await self.lights_toggle()

    async def lights_toggle(self) -> None:
        self._require_function("light")
        await self._action("light")

    @property
    def supports_massage(self) -> bool:
        return "massage" in self._profile.functions

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.supports_massage and self._family == "richmat"

    @property
    def supports_massage_toggle_control(self) -> bool:
        # OFF and TIMER labels share the same UI listener. The app remaps it
        # to massageOff only on Richmat; Okin always advances its timer.
        return self.supports_massage and self._family == "okin"

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return "massage_head" in self._profile.functions

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return "massage_foot" in self._profile.functions

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return "massage_wave" in self._profile.functions

    @property
    def supports_massage_timer(self) -> bool:
        return (
            self.supports_massage
            and self._family == "richmat"
            and (self.app_profile == "malouf" or "massage_timer_set" in self._profile.functions)
        )

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.supports_massage_timer else []

    async def massage_off(self) -> None:
        if not self.supports_massage_off_control:
            raise ValueError("This app profile has no reachable massage-off action")
        await self._action("massage_off")

    async def massage_toggle(self) -> None:
        if not self.supports_massage_toggle_control:
            raise ValueError("This model has no massage timer step control")
        await self._action("massage_timer_step")

    async def massage_head_toggle(self) -> None:
        self._require_function("massage_head")
        await self._action("massage_head")

    async def massage_foot_toggle(self) -> None:
        self._require_function("massage_foot")
        await self._action("massage_foot")

    async def massage_mode_step(self) -> None:
        self._require_function("massage_wave")
        await self._action("massage_wave")

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage_timer or minutes not in self.massage_timer_options:
            raise ValueError("This model supports only direct 10/20/30 minute massage timers")
        await self._action(f"massage_{minutes}")

    @property
    def supports_clock_alarm(self) -> bool:
        return "alarm" in self._profile.functions and self._family == "okin"

    @property
    def supports_clock_sync(self) -> bool:
        return self._family == "okin"

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        if not self.supports_clock_alarm:
            return ()
        return (
            "zero_g",
            "lounge",
            "tv",
            "anti_snore",
            *(f"memory_{slot}" for slot in range(1, self.memory_slot_count + 1)),
        )

    async def sync_clock(self) -> None:
        transport = self._resolve_transport()
        if not self.supports_clock_sync:
            raise ValueError("This app transport has no clock")
        await self.write_command(
            clock_frame(transport, dt_util.now()),
            repeat_count=1 if transport == "okin_new" else 3,
            repeat_delay_ms=0,
        )

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
        transport = self._resolve_transport()
        if not self.supports_clock_alarm:
            raise ValueError("This model/transport has no alarm control")
        if head_level != 0 or foot_level != 0:
            raise ValueError("These app alarms have no massage-intensity fields")
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("Invalid alarm time")
        if any(isinstance(day, bool) or not 0 <= day <= 6 for day in weekdays):
            raise ValueError("Alarm weekdays must use Monday=0 through Sunday=6")
        if preset not in ALARM_TYPES:
            raise ValueError("Alarm preset must be one of the six app alarm choices")
        if enabled and preset.startswith("memory_"):
            self._validate_memory(int(preset[-1]))
        if not enabled:
            frame = alarm_frame(transport, 0, 0, 0, 0)
        else:
            now = dt_util.now()
            repeats = 1 | sum(2 << day for day in set(weekdays))
            if not weekdays:
                day = now if (now.hour, now.minute) < (hour, minute) else now + timedelta(days=1)
                repeats = 2 << day.weekday()
            frame = alarm_frame(transport, hour, minute, ALARM_TYPES[preset], repeats)
            # The only app time-sync producer is immediately before setting
            # an active alarm. Do not inject time writes on BLE connection.
            await self.sync_clock()
        await self.write_command(
            frame, repeat_count=1 if transport == "okin_new" else 3, repeat_delay_ms=0
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.supports_massage and self._family == "okin":
            return (
                ControllerStateSensorSpec(
                    "malouf_massage_remaining",
                    "malouf_massage_remaining",
                    "massage_remaining_minutes",
                    "mdi:timer-outline",
                    native_unit_of_measurement="min",
                ),
            )
        return ()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        transport = self._resolve_transport()
        uuid = TRANSPORTS[transport].notify_characteristic
        if uuid is None:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Not connected to bed")
        async with self.ble_lock:
            await client.start_notify(uuid, self._notification_handler)
        self._notify_uuid = uuid

    async def stop_notify(self) -> None:
        uuid, self._notify_uuid = self._notify_uuid, None
        client = self.client
        if uuid is not None and client is not None and client.is_connected:
            async with self.ble_lock:
                await client.stop_notify(uuid)
        self._notify_callback = None

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        if self._transport is None:
            return
        state = parse_notification(self._transport, bytes(data))
        if state is None:
            return
        updates: dict[str, int | bool] = {}
        if state.massage_remaining_minutes != self._massage_remaining:
            self._massage_remaining = state.massage_remaining_minutes
            updates["massage_remaining_minutes"] = self._massage_remaining
        if self._transport != "okin_custom" and state.light_status != self._light_status:
            self._light_status = state.light_status
            # RemoteFragment.setLightStatus selects the light for every
            # nonzero integer, including signed legacy notification values.
            updates["underbed_light_on"] = bool(self._light_status)
        if updates:
            self.forward_controller_state_updates(updates)

    def get_massage_state(self) -> dict[str, object]:
        return (
            {}
            if self._massage_remaining is None
            else {"remaining_minutes": self._massage_remaining}
        )

    def get_light_state(self) -> dict[str, object]:
        return {} if self._light_status is None else {"is_on": bool(self._light_status)}
