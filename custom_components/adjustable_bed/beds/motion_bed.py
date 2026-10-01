"""Motion Bed app control, using one explicitly selected physical target."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Mapping
from contextlib import ExitStack
from contextvars import ContextVar
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING

from ..motion_bed_actions import ACTION_BY_KEY, MOTION_BED_ACTIONS, MotionBedAction
from ..motion_bed_models import MotionBedSelection
from ..motion_bed_protocol import SOURCE_COMMANDS, build_clock, build_thermal_clock
from ..motion_bed_requests import MotionBedWrite
from ..motion_bed_state import (
    MotionBedContext,
    MotionBedFollowup,
    MotionBedState,
    parse_motion_bed_notification,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

CHARACTERISTIC = "0000ffe1-0000-1000-8000-00805f9b34fb"
STOP = bytes.fromhex("FFFFFFFF0500000000D700")


def _action_callback(key: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        await controller.async_execute_motion_bed_action(key)
    return invoke


@dataclass(slots=True)
class _HeldSession:
    client: BleakClient
    characteristic: BleakGATTCharacteristic
    address: str
    released: bool = False


class MotionBedController(BedController):
    """Expose app controls without inferring motors or thermostat temperatures."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, selection: MotionBedSelection) -> None:
        super().__init__(coordinator)
        self.selection = selection
        self._state = MotionBedState()
        self._route = selection.route
        self._session_client: BleakClient | None = None
        self._characteristic: BleakGATTCharacteristic | None = None
        self._notifying = False
        self._target_address = coordinator.address
        self._generation = 0
        self._tasks: set[asyncio.Task[None]] = set()
        self._context_expiry: dict[MotionBedContext, float] = {}
        self._diagnostic_rejection: str | None = None
        self._receipts: tuple[str, ...] = ()
        self._operation_generation: ContextVar[int | None] = ContextVar("motion_bed_operation", default=None)
        self._started_modules: set[str] = set()
        self._network_queries = 0
        self._network_poll_active = False
        self._active_module: str | None = None
        self._audio_preference = False
        self._held_session: _HeldSession | None = None
        self._module_generation = 0
        self._thermal_task: asyncio.Task[None] | None = None
        self._network_generation = 0
        self._network_task: asyncio.Task[None] | None = None
        self._network_connection_hold: ExitStack | None = None
        self._module_capabilities: dict[str, bool] = {}
        previous = coordinator.capability_controller
        if (isinstance(previous, MotionBedController) and previous.selection == selection
                and previous._target_address == coordinator.address):
            self._module_capabilities = dict(previous._module_capabilities)

    def _remember_module_capabilities(self) -> None:
        for module in ("motor", "air", "thermal"):
            present = getattr(self._state, module + "_module_present")
            if isinstance(present, bool):
                self._module_capabilities[module] = present

    def _module_present(self, module: str) -> bool:
        if self._target_address != self._coordinator.address:
            return False
        present = getattr(self._state, module + "_module_present")
        return present if isinstance(present, bool) else self._module_capabilities.get(module, False)

    @property
    def control_characteristic_uuid(self) -> str:
        return CHARACTERISTIC

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        return self.selection.surface in ("home", "motor", "hub")

    @property
    def supports_preset_flat(self) -> bool:
        return False  # The complete named actions retain app-specific flat semantics.

    @property
    def supports_preset_zero_g(self) -> bool:
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_preset_tv(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_motion_bed_actions(self) -> bool:
        return True

    @property
    def motion_bed_local_state(self) -> dict[str, bool]:
        return {"audio_available": self._audio_preference}

    def restore_motion_bed_local_state(self, state: Mapping[str, bool]) -> None:
        if set(state) - {"audio_available"} or any(type(value) is not bool for value in state.values()):
            raise ValueError("Invalid Motion Bed audio preference")
        self._audio_preference = state.get("audio_available", False)

    @property
    def _has_audio(self) -> bool:
        reported = self._state.audio_available
        return reported if isinstance(reported, bool) else self._audio_preference

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": self.selection.surface,
            "preset_layout": self.selection.preset,
            "movement_layout": self.selection.movement,
            "alternate_identity": self.selection.alternate_identity,
            "audio_excluded": self.selection.audio_excluded,
            "write_policy_origin": "host: prefer write property, otherwise write-without-response",
            "last_notification_rejection": self._diagnostic_rejection,
            "receipts": self._receipts,
            "hardware_verified": False,
            "active_module": self._active_module,
            "remembered_audio_available": self._audio_preference,
            "remembered_module_capabilities": dict(self._module_capabilities),
            "actions": [{"key": action.key, "name": action.name, "kind": action.kind}
                        for action in self.actions],
            **self._state.to_updates(),
        }

    def _active_owners(self) -> frozenset[str]:
        owners: set[str] = {"Setting2Activity"}
        if self.selection.surface == "home":
            owners.update({
                f"Kuaijie{self.selection.preset}Fragment", f"Weitiao{self.selection.movement}Fragment",
                "HomeActivity", "AnmoFragment", "DengguangFragment", "SmartSleepFragment",
                "AlarmActivity", "SleepAdjustActivity", "SleepDataEntryActivity",
                "SleepDayReportActivity", "SleepFallTimerSelectActivity", "SleepMonthReportActivity",
                "SleepReportMainActivity", "SleepTimerSelectActivity", "NetworkActivity", "XinLvDaiActivity",
            })
        if self.selection.surface == "hub":
            owners.update({"MainMcuActivity", "ChangeDeviceActivity", "ConnectMcuActivity"})
        motor = self.selection.surface == "motor" or (self.selection.surface == "hub" and self._module_present("motor"))
        air = self.selection.surface == "air" or (self.selection.surface == "hub" and self._module_present("air"))
        thermal = self.selection.surface == "thermal" or (self.selection.surface == "hub" and self._module_present("thermal"))
        if motor:
            owners.update({"DiandongFragment", "DianDongSetActivity", "AlarmActivity"})
        if air:
            owners.update({"QinangFragment", "AnmoSetActivity", "PressSetActivity"})
        if thermal:
            owners.update({"LengnuanFragment", "TimeSettingActivity"})
        return frozenset(owners)

    @property
    def actions(self) -> tuple[MotionBedAction, ...]:
        owners = self._active_owners()
        return tuple(action for action in MOTION_BED_ACTIONS if action.owner in owners)

    def controller_button_available(self, key: str) -> bool:
        action = ACTION_BY_KEY.get(key.removeprefix("motion_bed_"))
        if action is None or action.owner not in self._active_owners():
            return False
        try:
            self.validate_motion_bed_action(action.key)
        except ValueError:
            return False
        return True

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                key="motion_bed_" + action.key,
                name=action.name,
                press_fn=_action_callback(action.key),
                translation_key=None,
            )
            for action in self.actions
            if action.kind not in ("persistent", "held", "query")
            # Programming is offered by the confirmed action service, never a one-tap erase.
            and action.kind != "program"
        ) + tuple(
            ControllerButtonSpec(
                key="motion_bed_" + action.key,
                name=action.name,
                press_fn=_action_callback(action.key),
                translation_key=None,
            )
            for action in self.actions
            if action.kind == "held" and action.owner in ("DiandongFragment", "SleepAdjustActivity")
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if self.selection.surface != "home":
            return ()  # Modular upper-arrow source callbacks are dead.
        movement = {action.key: action for action in self.actions if action.kind == "held" and action.owner.startswith("Weitiao")}
        controls: list[MotorControlSpec] = []
        for key in movement:
            if key.endswith("_up") and key[:-3] + "_down" in movement:
                controls.append(MotorControlSpec(
                    key="motion_bed_" + key[:-3], translation_key="motion_bed_" + key[:-3],
                    open_fn=_action_callback(key), close_fn=_action_callback(key[:-3] + "_down"),
                    stop_fn=lambda controller: controller.stop_all(),
                    scheduler_resource="motion_bed_motor",
                ))
        return tuple(controls)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.selection.surface != "hub":
            return ()
        async def select(controller: BedController, value: str) -> None:
            await controller.set_motion_bed_surface(value)
        return (ControllerSelectSpec("motion_bed_active_module", "motion_bed_active_module",
                                     "motion_bed_active_module", ("motor", "air", "thermal"), select),)

    async def set_motion_bed_surface(self, surface: str) -> None:
        if self.selection.surface != "hub" or surface not in ("motor", "air", "thermal"):
            raise ValueError("Choose a reported Motion Bed hub module")
        if not self._module_present(surface):
            raise ValueError("This hub has not reported the selected module")
        if self._active_module != surface:
            self._select_module(surface)
            self._started_modules.discard(surface)
            self._publish()
            self._spawn(self._start_present_modules)

    def _select_module(self, module: str | None) -> None:
        self._module_generation += 1
        if self._thermal_task is not None:
            self._thermal_task.cancel()
            self._thermal_task = None
        self._active_module = module

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                key="motion_bed_" + item.name, translation_key="motion_bed_" + item.name,
                state_key="motion_bed_" + item.name, icon="mdi:bed-outline",
                entity_registry_enabled_default=item.name in {
                    "brightness", "upper_massage", "lower_massage", "massage_timer", "thermal_temperature",
                    "thermal_water", "network_status", "fault", "fault_part", "raw_positions",
                },
            )
            for item in fields(self._state)
            if "bool" not in str(item.type)
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                key="motion_bed_" + item.name, translation_key="motion_bed_" + item.name,
                state_key="motion_bed_" + item.name, icon="mdi:bed-outline",
            )
            for item in fields(self._state)
            if "bool" in str(item.type)
        )

    def _publish(self) -> None:
        updates = {"motion_bed_" + key: value for key, value in self._state.to_updates().items()}
        updates["motion_bed_active_module"] = self._active_module
        self.forward_controller_state_updates(updates)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Motion Bed is not connected")
        characteristic: BleakGATTCharacteristic | None = None
        for service in client.services or ():
            for candidate in service.characteristics:
                if candidate.uuid.lower() == CHARACTERISTIC:
                    characteristic = candidate
        if characteristic is None:
            raise ValueError("Motion Bed requires its last FFE1 characteristic")
        if not {"write", "write-without-response"}.intersection(characteristic.properties):
            raise ValueError("The last FFE1 characteristic is not writable")
        if not {"notify", "indicate"}.intersection(characteristic.properties):
            raise ValueError("The last FFE1 characteristic has no notification support")
        binding_changed = (self._session_client is not client or self._target_address != self._coordinator.address
                           or self._characteristic is not characteristic)
        if self._notifying and binding_changed:
            await self.stop_notify()
        if binding_changed:
            self._remember_module_capabilities()
            if self._target_address != self._coordinator.address:
                self._module_capabilities.clear()
            self._generation += 1
            if self._held_session is not None:
                await self._release_held_session(self._held_session)
            self._cancel_background()
            self._context_expiry.clear()
            self._started_modules.clear()
            self._network_queries = 0
            self._network_poll_active = False
            self._active_module = None
            self._state = MotionBedState()
            self._route = self.selection.route
            self._publish()
        self._session_client, self._characteristic = client, characteristic
        self._target_address = self._coordinator.address

    def _current_session(self) -> tuple[BleakClient, BleakGATTCharacteristic]:
        client, characteristic = self._session_client, self._characteristic
        origin = self._operation_generation.get()
        if (origin is not None and origin != self._generation) or (client is None or characteristic is None or self.client is not client
                or not client.is_connected or self._coordinator.address != self._target_address):
            raise ConnectionError("Motion Bed target/session changed")
        return client, characteristic

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object]:
        if command.startswith(bytes.fromhex("FFFFFFFF02001813")):
            return {"hex": "**REDACTED**", "reason": "Motion Bed Wi-Fi provisioning"}
        return {"hex": command.hex()}

    async def write_command(self, command: bytes, repeat_count: int = 1,
                            repeat_delay_ms: int = 100,
                            cancel_event: asyncio.Event | None = None) -> None:
        if repeat_count != 1:
            raise ValueError("Motion Bed starts once; held motion does not repeat its start frame")
        cancel = cancel_event or self._coordinator.cancel_command
        async with self._ble_lock:
            client, characteristic = self._current_session()
            if cancel.is_set():
                return
            response = "write" in characteristic.properties
            self._coordinator.record_command_trace(
                payload=self._format_command_trace_payload(command),
                characteristic_uuid=CHARACTERISTIC, characteristic_handle=characteristic.handle,
                response=response, repeat_count=1, repeat_delay_ms=0,
                command_origin="motion_bed_current_target", controller_class=type(self).__name__,
            )
            await client.write_gatt_char(characteristic, command, response=response)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._notifying:
            await self.stop_notify()
        await self.async_discover_capabilities()
        self._notify_callback = callback
        client, characteristic = self._current_session()
        generation = self._generation
        address = self._target_address
        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (generation != self._generation or self.client is not client or sender is not characteristic
                    or not client.is_connected or self._coordinator.address != address):
                return
            self._handle_notification(bytes(data))
        async with self._ble_lock:
            self._current_session()
            await client.start_notify(characteristic, receive)
        self._notifying = True
        token = self._operation_generation.set(generation)
        try:
            await self._startup()
        except BaseException:
            await self.stop_notify()
            raise
        finally:
            self._operation_generation.reset(token)

    def on_disconnect(self) -> None:
        self._remember_module_capabilities()
        self._generation += 1
        self._cancel_background()
        self._notifying = False
        self._session_client = None
        self._characteristic = None
        self._notify_callback = None
        self._context_expiry.clear()
        self._started_modules.clear()
        self._network_poll_active = False
        self._active_module = None
        self._state = MotionBedState()
        self._publish()

    def _owned_session_current(self, generation: int) -> bool:
        if generation != self._generation or self._coordinator.controller is not self:
            return False
        try:
            self._current_session()
        except ConnectionError:
            return False
        return True

    async def _release_held_session(self, session: _HeldSession) -> None:
        # A started hold owns its original physical client even after a rebind.
        async with self._ble_lock:
            if session.released:
                return
            session.released = True
            if not session.client.is_connected:
                return
            response = "write" in session.characteristic.properties
            self._coordinator.record_command_trace(
                payload={"hex": STOP.hex(), "original_target_address": session.address},
                characteristic_uuid=CHARACTERISTIC, characteristic_handle=session.characteristic.handle,
                response=response, repeat_count=1, repeat_delay_ms=0,
                command_origin="motion_bed_original_hold_release", controller_class=type(self).__name__,
            )
            await session.client.write_gatt_char(session.characteristic, STOP, response=response)

    async def stop_notify(self) -> None:
        self._remember_module_capabilities()
        self._generation += 1
        self._cancel_background()
        try:
            if self._held_session is not None:
                await self._release_held_session(self._held_session)
            client, characteristic = self._session_client, self._characteristic
            if self._notifying and client is not None and client.is_connected and characteristic is not None:
                async with self._ble_lock:
                    await client.stop_notify(characteristic)
        finally:
            self._notifying = False
            self._session_client = None
            self._characteristic = None
            self._context_expiry.clear()
            self._started_modules.clear()
            self._network_queries = 0
            self._network_poll_active = False
            self._state = MotionBedState()
            self._publish()
            self._notify_callback = None

    def _cancel_background(self) -> None:
        self._module_generation += 1
        self._network_generation += 1
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._thermal_task = None
        self._network_task = None
        if self._network_connection_hold is not None:
            self._network_connection_hold.close()
            self._network_connection_hold = None

    def _spawn(self, operation: Callable[[], Coroutine[object, object, None]]) -> asyncio.Task[None]:
        # Coroutine functions below own session/generation checks before each write.
        generation = self._generation
        async def run() -> None:
            if generation != self._generation:
                return
            token = self._operation_generation.set(generation)
            try:
                await operation()
            finally:
                self._operation_generation.reset(token)
        task = self._coordinator.hass.async_create_task(run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _activate(self, context: MotionBedContext, seconds: float = 30) -> None:
        if context in ("day_report", "month_report", "sleep_report"):
            for previous in ("day_report", "month_report", "sleep_report"):
                self._context_expiry.pop(previous, None)
        self._context_expiry[context] = asyncio.get_running_loop().time() + seconds

    def _handle_notification(self, data: bytes) -> None:
        self.forward_raw_notification(CHARACTERISTIC, data)
        now = asyncio.get_running_loop().time()
        contexts = self.selection.route.contexts | frozenset(
            key for key, expiry in self._context_expiry.items() if expiry > now
        )
        if self.selection.surface == "hub":
            if self._state.motor_module_present is True:
                contexts |= frozenset({"motor"})
            if self._state.air_module_present is True:
                contexts |= frozenset({"air"})
            if self._state.thermal_module_present is True:
                contexts |= frozenset({"thermal"})
        route = replace(self._route, contexts=contexts)
        result = parse_motion_bed_notification(data, route, self._state)
        self._diagnostic_rejection = result.rejection
        self._state = result.state
        if "module_deleted" in result.receipts:
            self._module_capabilities.clear()
        else:
            self._remember_module_capabilities()
        if isinstance(self._state.audio_available, bool):
            self._audio_preference = self._state.audio_available
        self._receipts = result.receipts
        self._publish()
        if self.selection.surface == "hub":
            self._spawn(self._start_present_modules)
        effects = result.effects
        if ("module_deleted" in result.receipts and "module_change" in contexts
                and not any(effect.action == "module_status_query" for effect in effects)):
            # The delete receiver clears inventory; refresh it using the proven query.
            effects += (MotionBedFollowup("module_status_query"),)
        for effect in effects:
            if effect.action == "network_status_query" and self._network_poll_active and effect.delay_ms:
                continue
            network_generation = self._network_generation
            self._spawn(lambda effect=effect, network_generation=network_generation:
                        self._followup(effect, network_generation=network_generation))

    async def _followup(self, effect: MotionBedFollowup, *, network_generation: int | None = None) -> None:
        generation = self._generation
        attempt = self._network_generation if network_generation is None else network_generation
        def current() -> bool:
            return self._owned_session_current(generation) and (
                effect.action != "network_status_query" or attempt == self._network_generation
            )
        await asyncio.sleep(effect.delay_ms / 1000)
        if not current():
            return
        key = {
            "module_status_query": "main_mcu_activity_module_status",
            "sensor_query": "diandong_fragment_sensor_status",
            "position_query": "sleep_adjust_activity_raw_positions",
            "network_status_query": "network_activity_network_status",
        }[effect.action]
        async def execute(controller: BedController) -> None:
            if controller is not self or not current():
                return
            if effect.action == "network_status_query":
                await self._bounded_network_query()
            else:
                await controller.async_execute_motion_bed_internal_query(key)
        await self._coordinator.async_execute_controller_query(execute, cancel_running=False, skip_disconnect=True,
                                                                     run_if=current)

    async def async_execute_motion_bed_internal_query(self, key: str) -> None:
        action = ACTION_BY_KEY[key]
        if action.kind != "query":
            raise ValueError("Internal Motion Bed callback must be a query")
        self._activate(action.context)
        for command in dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in action.select(self._state, self.selection.alternate_identity)):
            await self.write_command(command)

    async def _send_sequence(self, commands: tuple[bytes, ...], *, spacing: float = 0) -> None:
        for index, command in enumerate(commands):
            if index and spacing:
                await asyncio.sleep(spacing)
            await self.write_command(command)

    async def _startup(self) -> None:
        from datetime import datetime
        surface = self.selection.surface
        if surface == "home":
            await asyncio.sleep(0.5)
            await self.write_command(SOURCE_COMMANDS["HomeActivity:321"])
            await asyncio.sleep(0.5)
            await self.write_command(build_clock(datetime.now().astimezone()))
            await asyncio.sleep(0.5)
            await self.write_command(SOURCE_COMMANDS["HomeActivity:311"])
            await asyncio.sleep(0.5)
            await asyncio.sleep(0.2)  # The inherited fragment event delays status requests.
            for action in self.actions:
                if action.kind == "query" and action.owner == f"Kuaijie{self.selection.preset}Fragment":
                    commands = tuple(dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in action.select(self._state, self.selection.alternate_identity)))
                    await self._send_sequence(commands, spacing=0.5)
        elif surface == "hub":
            await asyncio.sleep(0.3)
            await self.write_command(SOURCE_COMMANDS["MainMcuActivity:182"])
        else:
            await self._module_startup(surface)

    def _module_is_active(self, module: str) -> bool:
        return self.selection.surface == module or (
            self.selection.surface == "hub" and self._active_module == module
            and getattr(self._state, module + "_module_present") is True
        )

    async def _module_startup(self, module: str) -> None:
        from datetime import datetime
        module_generation = self._module_generation
        def current() -> bool:
            return module_generation == self._module_generation and self._module_is_active(module)
        await asyncio.sleep(0.2)
        if not current():
            return
        if module == "motor":
            await self.write_command(SOURCE_COMMANDS["DiandongFragment:319"])
            await asyncio.sleep(0.2)
            if not current():
                return
            await self.write_command(build_clock(datetime.now().astimezone()))
        elif module == "air":
            await self.write_command(SOURCE_COMMANDS["QinangFragment:133"])
        elif module == "thermal":
            await self.write_command(SOURCE_COMMANDS["LengnuanFragment:183"])
            await asyncio.sleep(0.2)
            if not current():
                return
            await self.write_command(build_thermal_clock(datetime.now().astimezone()))
            if not current():
                return
            if self._thermal_task is not None:
                self._thermal_task.cancel()
            self._thermal_task = self._spawn(lambda: self._thermal_poll(module_generation=module_generation))

    async def _start_present_modules(self) -> None:
        present = tuple(module for module in ("motor", "air", "thermal")
                        if getattr(self._state, module + "_module_present") is True)
        self._started_modules.intersection_update(present)
        if self._active_module not in present:
            self._select_module(present[0] if present else None)
            self._publish()
        module = self._active_module
        if module is None or module in self._started_modules:
            return
        self._started_modules.add(module)
        generation = self._generation
        module_generation = self._module_generation
        completed = False
        async def prepare(controller: BedController) -> None:
            nonlocal completed
            if (controller is not self or not self._owned_session_current(generation) or self._active_module != module
                    or module_generation != self._module_generation
                    or getattr(self._state, module + "_module_present") is not True):
                if module_generation == self._module_generation:
                    self._started_modules.discard(module)
                return
            await self._module_startup(module)
            completed = module_generation == self._module_generation and self._module_is_active(module)
        try:
            await self._coordinator.async_execute_controller_query(prepare, cancel_running=False, skip_disconnect=True,
                                                                     run_if=lambda: self._owned_session_current(generation) and module_generation == self._module_generation)
        finally:
            if not completed and module_generation == self._module_generation:
                self._started_modules.discard(module)

    async def _thermal_poll(self, *, module_generation: int | None = None) -> None:
        generation = self._generation
        if module_generation is None:
            module_generation = self._module_generation
        def current() -> bool:
            return self._owned_session_current(generation) and module_generation == self._module_generation and self._module_is_active("thermal")
        await asyncio.sleep(2)
        while current():
            async def query(controller: BedController) -> None:
                if controller is not self or not current():
                    return
                await self.write_command(SOURCE_COMMANDS["LengnuanFragment:58"])
            await self._coordinator.async_execute_controller_query(query, cancel_running=False, skip_disconnect=True,
                                                                         run_if=current)
            await asyncio.sleep(5)

    def validate_motion_bed_action(self, key: str, *, branch: str = "app",
                                  duration: float = 1, confirmed: bool = False) -> None:
        action = ACTION_BY_KEY.get(key)
        if action is None or action.owner not in self._active_owners():
            raise ValueError("Action is unavailable in the selected Motion Bed profile")
        if not 0 < duration <= 10:
            raise ValueError("Motion Bed bounded movement duration must be 0–10 seconds")
        if action.kind in ("program", "persistent") and not confirmed:
            raise ValueError("Confirm this persistent Motion Bed configuration change")
        selected = action.select(self._state, self.selection.alternate_identity, branch=branch)
        if not self._has_audio and any(
            SOURCE_COMMANDS[source_id].startswith(bytes.fromhex("FFFFFFFF0100130B"))
            or SOURCE_COMMANDS[source_id].startswith(bytes.fromhex("FFFFFFFF0100140B"))
            for source_id in selected
        ):
            raise ValueError("This physical target has not reported audio support")

    async def async_execute_motion_bed_action(self, key: str, *, branch: str = "app",
                                             duration: float = 1, confirmed: bool = False) -> None:
        token = self._operation_generation.set(self._generation)
        try:
            await self._execute_action(key, branch=branch, duration=duration, confirmed=confirmed)
        finally:
            self._operation_generation.reset(token)

    async def _execute_action(self, key: str, *, branch: str, duration: float, confirmed: bool) -> None:
        self.validate_motion_bed_action(key, branch=branch, duration=duration, confirmed=confirmed)
        action = ACTION_BY_KEY[key]
        self._activate(action.context)
        if self.selection.surface == "hub":
            module = "thermal" if action.owner == "LengnuanFragment" else "air" if action.owner in ("QinangFragment", "AnmoSetActivity", "PressSetActivity") else "motor" if action.owner in ("DiandongFragment", "DianDongSetActivity") else None
            if module is not None:
                await self.set_motion_bed_surface(module)
        source_ids = action.select(self._state, self.selection.alternate_identity, branch=branch)
        commands = tuple(dict.fromkeys(SOURCE_COMMANDS[source_id] for source_id in source_ids))
        if action.kind == "held":
            client, characteristic = self._current_session()
            session = _HeldSession(client, characteristic, self._target_address)
            self._held_session = session
            try:
                for command in commands:
                    await self.write_command(command)
                await self._hold(duration, sleep_adjust=action.context == "sleep_adjust")
            finally:
                try:
                    await self._release_held_session(session)
                finally:
                    if self._held_session is session:
                        self._held_session = None
                generation = self._operation_generation.get()
                if generation is not None and self._owned_session_current(generation) and action.context == "sleep_adjust":
                    await asyncio.sleep(0.1)
                    await self.write_command(SOURCE_COMMANDS["SleepAdjustActivity:255"], cancel_event=asyncio.Event())
        elif key == "sleep_data_entry_activity_capture_debug":
            for _ in range(10):
                try:
                    await asyncio.wait_for(self._coordinator.cancel_command.wait(), 2)
                    return
                except TimeoutError:
                    for command in commands:
                        await self.write_command(command)
        else:
            await self._send_sequence(commands, spacing=0.5 if action.kind == "query" and action.owner.startswith("Kuaijie") else 0)

    async def _hold(self, duration: float, *, sleep_adjust: bool = False) -> None:
        deadline = asyncio.get_running_loop().time() + duration
        while asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                await asyncio.wait_for(self._coordinator.cancel_command.wait(), min(remaining, 0.5))
                return
            except TimeoutError:
                if sleep_adjust and asyncio.get_running_loop().time() < deadline:
                    await self.write_command(SOURCE_COMMANDS["SleepAdjustActivity:281"])

    def validate_motion_bed_write(self, request: MotionBedWrite) -> None:
        available: set[str] = set()
        surface = self.selection.surface
        if surface == "home":
            available.update({"clock", "alarm", "sleep_angles", "calibration", "sleep_timer", "sleep_report", "provision_wifi"})
            if self.selection.preset == "K2M":
                available.add("audio")
        if surface == "motor" or (surface == "hub" and self._module_present("motor")):
            available.update({"clock", "alarm", "audio"})
        if surface == "air" or (surface == "hub" and self._module_present("air")):
            available.update({"air_setting", "pressure"})
        if surface == "thermal" or (surface == "hub" and self._module_present("thermal")):
            available.update({"clock", "thermal_schedule"})
        if surface == "hub":
            available.add("module")
        if request.name not in available:
            raise ValueError("Configuration is unavailable in this Motion Bed profile/module")
        if request.name == "clock":
            thermal = request.context == "thermal"
            if thermal:
                if not (surface == "thermal" or (surface == "hub" and self._module_present("thermal"))):
                    raise ValueError("Thermal clock requires the thermal module/profile")
            elif not (surface in ("home", "motor") or (surface == "hub" and self._module_present("motor"))):
                raise ValueError("P1 clock requires a motor/home profile")
        if request.name == "alarm":
            if request.alarm_audio != self._has_audio:
                raise ValueError("Alarm audio must match this physical target's reported audio capability")
            if surface == "home" and request.alarm_switch is not None:
                raise ValueError("Home alarms use the enabled flag, not the modular first-alarm switch")
            if request.alarm_switch == 0 and self._state.alarm_flag is not None:
                raise ValueError("Uninitialized alarm switch is unavailable after alarm state arrives")
        if request.name == "audio" and not self._has_audio:
            raise ValueError("This physical target has not reported audio support")
        if request.persistent and not request.confirmed:
            raise ValueError("Confirm this persistent Motion Bed configuration change")

    async def async_execute_motion_bed_write(self, request: MotionBedWrite) -> None:
        self.validate_motion_bed_write(request)
        token = self._operation_generation.set(self._generation)
        network_hold: ExitStack | None = None
        hold_transferred = False
        try:
            if request.network_poll:
                self._network_generation += 1
                if self._network_task is not None:
                    self._network_task.cancel()
                    self._network_task = None
                if self._network_connection_hold is not None:
                    self._network_connection_hold.close()
                network_hold = ExitStack()
                network_hold.enter_context(self._coordinator.hold_command_connection())
                self._network_connection_hold = network_hold
                self._network_queries = 0
                self._network_poll_active = False
            if self.selection.surface == "hub":
                module = "thermal" if request.context in ("thermal", "thermal_schedule") else "air" if request.name in ("air_setting", "pressure") else "motor" if request.name in ("alarm", "audio", "clock") else None
                if module is not None:
                    await self.set_motion_bed_surface(module)
            self._activate(request.context, 75 if request.network_poll else 30)
            if request.name == "sleep_report":
                fresh = MotionBedState()
                clean = {item.name: getattr(fresh, item.name) for item in fields(fresh)
                         if item.name.startswith(("day_", "app_day_", "month_"))}
                self._state = replace(self._state, **clean)
                self._publish()
                self._route = replace(self._route, historical_day=request.historical_day,
                                      day_window_offset=request.report_offset)
            if request.initial_delay_ms:
                try:
                    await asyncio.wait_for(self._coordinator.cancel_command.wait(), request.initial_delay_ms / 1000)
                    return
                except TimeoutError:
                    pass
            for index, frame in enumerate(request.frames):
                if index and request.spacing_ms:
                    try:
                        await asyncio.wait_for(self._coordinator.cancel_command.wait(), request.spacing_ms / 1000)
                        return
                    except TimeoutError:
                        pass
                await self.write_command(frame)
            if request.network_poll:
                self._network_queries = 0
                self._network_poll_active = True
                self._state = replace(self._state, network_poll_attempts=0, provisioning_status="waiting")
                self._publish()
                self._current_session()
                self._network_task = self._spawn(lambda: self._network_poll(connection_hold=network_hold))
                hold_transferred = True
        finally:
            if network_hold is not None and not hold_transferred:
                network_hold.close()
                if self._network_connection_hold is network_hold:
                    self._network_connection_hold = None
            self._operation_generation.reset(token)

    async def _bounded_network_query(self) -> None:
        if self._network_queries >= 10:
            return
        self._network_queries += 1
        await self.async_execute_motion_bed_internal_query("network_activity_network_status")

    async def _network_poll(self, *, connection_hold: ExitStack | None = None) -> None:
        generation = self._generation
        attempt = self._network_generation
        def current() -> bool:
            return self._owned_session_current(generation) and attempt == self._network_generation
        try:
            for _ in range(10):
                await asyncio.sleep(6)
                if not current() or self._state.provisioning_status in ("failed", "success"):
                    return
                async def query(controller: BedController) -> None:
                    if controller is self and current():
                        await self._bounded_network_query()
                await self._coordinator.async_execute_controller_query(query, cancel_running=False, skip_disconnect=True,
                                                                         run_if=current)
            if current() and self._state.provisioning_status == "waiting":
                self._state = replace(self._state, provisioning_status="timed_out")
                self._publish()
        finally:
            if connection_hold is not None:
                connection_hold.close()
                if self._network_connection_hold is connection_hold:
                    self._network_connection_hold = None
            if current():
                self._network_poll_active = False

    async def _send_stop(self) -> None:
        await self.write_command(STOP, cancel_event=asyncio.Event())

    async def stop_all(self) -> None:
        surface = self._active_module if self.selection.surface == "hub" else self.selection.surface
        if surface == "air":
            await self.write_command(SOURCE_COMMANDS["QinangFragment:302"], cancel_event=asyncio.Event())
        elif surface == "thermal":
            from ..motion_bed_protocol import build_thermal_gear
            await self.write_command(build_thermal_gear(4), cancel_event=asyncio.Event())
        else:
            await self._send_stop()

    async def _axis(self, axis: str, direction: str) -> None:
        candidates = [action for action in self.actions if action.kind == "held" and action.key.endswith("_" + axis + "_" + direction) and action.owner != "SleepAdjustActivity"]
        if len(candidates) != 1:
            raise ValueError("Use the explicitly named Motion Bed movement control")
        await self.async_execute_motion_bed_action(candidates[0].key)

    async def move_head_up(self) -> None: await self._axis("head", "up")
    async def move_head_down(self) -> None: await self._axis("head", "down")
    async def move_head_stop(self) -> None: await self.stop_all()
    async def move_back_up(self) -> None: await self._axis("back", "up")
    async def move_back_down(self) -> None: await self._axis("back", "down")
    async def move_back_stop(self) -> None: await self.stop_all()
    async def move_legs_up(self) -> None: await self._axis("legs", "up")
    async def move_legs_down(self) -> None: await self._axis("legs", "down")
    async def move_legs_stop(self) -> None: await self.stop_all()
    async def move_feet_up(self) -> None: raise NotImplementedError("No inferred feet axis")
    async def move_feet_down(self) -> None: raise NotImplementedError("No inferred feet axis")
    async def move_feet_stop(self) -> None: await self.stop_all()
    async def preset_flat(self) -> None: raise NotImplementedError("Use the app-labelled flat action")
    async def preset_memory(self, memory_num: int) -> None: raise NotImplementedError("Use the app-labelled memory action")
    async def program_memory(self, memory_num: int) -> None: raise NotImplementedError("Use confirmed Motion Bed programming")
