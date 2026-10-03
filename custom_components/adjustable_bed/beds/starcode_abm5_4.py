"""Address-owned AdjustableM5X4 BLE app runtime, independent of Sleepys."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..command_scheduler import copy_context_without_command
from ..const import CONF_BLE_DEVICE_NAME
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    SideBoundController,
)
from .starcode_abm5_4_profiles import (
    FIRMWARE_UUID,
    MANUFACTURER_UUID,
    STATE_KEYS,
    TRANSPORTS,
    RetainedAppState,
    build_frame,
    constructor_selector,
    initial_fields,
    manufacturer_selector,
    parse_fields,
    validate_selector,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_POSITIVE_SELECTORS = frozenset(("BOX1220", "BOX3633", "BOX25", "BOX25_STAR"))
_MOVEMENT = {
    "head_up": "headUp",
    "head_down": "headDown",
    "foot_up": "footUp",
    "foot_down": "footDown",
    "union_up": "unionUp",
    "union_down": "unionDown",
    "memory_1": "m1",
}
_PRESETS = {
    "flat": "flatPosition",
    "tv": "tv",
    "lounge": "lounge",
    "zero_g": "zeroGravity",
    "anti_snore": "anti",
}
_SAVES = {
    "memory_1": "saveM1",
    "tv": "saveTv",
    "lounge": "saveLounge",
    "zero_g": "saveZeroGravity",
    "reset": "resetMemory",
}
_MASSAGE = {
    "head_strength_up": "headStrengthAdd",
    "head_strength_down": "headStrengthReduce",
    "foot_strength_up": "footStrengthAdd",
    "foot_strength_down": "footStrengthReduce",
    "wave_up": "waveAdd",
    "wave_down": "waveReduce",
}


def _controller(controller: BedController) -> StarcodeAbm5_4Controller:
    target = controller._controller if isinstance(controller, SideBoundController) else controller
    if not isinstance(target, StarcodeAbm5_4Controller):
        raise TypeError("Requires an AdjustableM5X4 profile")
    if controller.command_side is not None:
        raise ValueError("This app has no one-address side selector")
    return target


def _button(action: str) -> Callable[[BedController], Coroutine[object, object, None]]:
    async def press(controller: BedController) -> None:
        await _controller(controller).app_action(action)

    return press


async def _timer(controller: BedController, option: str) -> None:
    await _controller(controller).set_app_timer(option)


async def _brightness(controller: BedController, value: float) -> None:
    await _controller(controller).set_app_brightness(value)


class StarcodeAbm5_4Controller(BedController):
    """C builds/parses, D selects roles/write mode, U consumes state/releases."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        command_selector: str = "none",
        ui_selector: str | None = None,
        transport_selector: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.command_selector = validate_selector(command_selector)
        self.ui_selector = validate_selector(ui_selector or command_selector)
        if coordinator.client is None and transport_selector is None:
            original_name = coordinator.entry.data.get(CONF_BLE_DEVICE_NAME)
            if not isinstance(original_name, str) or not original_name:
                raise ConnectionError("Offline app transport requires stored original BLE name")
        self.transport_selector = transport_selector or constructor_selector(
            coordinator.ble_device_name
        )
        if self.transport_selector not in TRANSPORTS:
            raise ValueError("No live app transport for this selector")
        self._transport = TRANSPORTS[self.transport_selector]
        if coordinator.client is None and not self._catalog_is_stable:
            raise ConnectionError("App entity catalog requires live manufacturer classification")
        self._owner_address = coordinator.address
        self._session_generation = 0
        self._operation_generation = 0
        self._notify_client: BleakClient | None = None
        self._notify_characteristic: BleakGATTCharacteristic | None = None
        self._write_characteristic: BleakGATTCharacteristic | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._initialization_lock = asyncio.Lock()
        self._startup_task: asyncio.Task[object] | None = None
        self._classification_complete = not self._transport.wake
        self._raw_fields = initial_fields()
        self._parser_state_observed = False
        self._ui_state_observed = False
        self._massage_on = False
        self._light_on = False
        self._level = 1
        self._timer_index = 0
        self._head_intensity: int | None = None
        self._wave: int | None = None
        self._low_4b: int | None = None
        self._automatic_white_flag: bool | None = None
        self._last_light_time_ms: int | None = None
        self._firmware: str | None = None
        self._manufacturer: str | None = None
        self._ready = False
        self._active_release: tuple[BleakClient, int, int, str] | None = None
        retained = coordinator.starcode_app_retained_state
        if isinstance(retained, RetainedAppState) and retained.address == self._owner_address:
            self._ui_state_observed = retained.observed
            self._massage_on = retained.massage_on
            self._light_on = retained.light_on
            self._level = retained.level
            self._timer_index = retained.timer_index
            self._head_intensity = retained.head_intensity
            self._wave = retained.wave
            self._low_4b = retained.low_4b
            self._automatic_white_flag = retained.automatic_white_flag
            self._last_light_time_ms = retained.last_light_time_ms

    def restore_retained_app_state(self, retained: RetainedAppState) -> bool:
        """Retain this owner's Home fields across an internal entity rebuild."""
        if (
            retained.address != self._owner_address
            or self._coordinator.address != self._owner_address
            or self._ui_state_observed
            or self._last_light_time_ms is not None
        ):
            return False
        self._ui_state_observed = retained.observed
        self._massage_on = retained.massage_on
        self._light_on = retained.light_on
        self._level = retained.level
        self._timer_index = retained.timer_index
        self._head_intensity = retained.head_intensity
        self._wave = retained.wave
        self._low_4b = retained.low_4b
        self._automatic_white_flag = retained.automatic_white_flag
        self._last_light_time_ms = retained.last_light_time_ms
        self._publish()
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._transport.write

    @property
    def requires_notification_channel(self) -> bool:
        return self._transport.subscribe

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self._catalog_is_stable or self._ready and self._classification_complete

    @property
    def _catalog_is_stable(self) -> bool:
        # UART can select C8/9. Both have positive controls and dedicated power
        # buttons when feedback is unavailable; offline catalogs must match both.
        feedback = self.supports_light_state_feedback
        return not self._transport.wake or self._entity_catalog_signature == (
            True,
            feedback,
            not feedback,
        )

    @property
    def _entity_catalog_signature(self) -> tuple[bool, bool, bool]:
        return (
            self.command_selector in _POSITIVE_SELECTORS,
            self.supports_light_state_feedback,
            self._native_light_power_buttons,
        )

    @property
    def _native_light_power_buttons(self) -> bool:
        return not self.supports_light_state_feedback and self.command_selector in (
            "BOX3633",
            "BOX25",
            "BOX25_STAR",
        )

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec(
                "back",
                "back",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
                scheduler_resource="*",
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
                scheduler_resource="*",
            ),
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        """Use the app's native held refresh cadence, retaining the repeat count."""
        return self._coordinator.motor_pulse_count, 100

    def timed_move_repeat_count(self, duration_ms: int, pulse_delay_ms: int) -> int:
        """Movement handlers use count times 100 ms as the entire held duration."""
        return max(1, (duration_ms + 99) // 100)

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_under_bed_lights(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.ui_selector in ("BOX25", "BOX25_STAR") and self._transport.subscribe

    def get_light_state(self) -> dict[str, object]:
        return {
            "is_on": self._light_on if self._ui_state_observed else None,
            "light_level": self._level,
        }

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_off_control(self) -> bool:
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.command_selector in _POSITIVE_SELECTORS

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.command_selector in _POSITIVE_SELECTORS

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.command_selector in _POSITIVE_SELECTORS

    @property
    def memory_slot_count(self) -> int:
        return 1

    @property
    def supports_memory_presets(self) -> bool:
        return True

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
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_preset_hold(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple(_MOVEMENT)
            + tuple(_PRESETS)
            + tuple("save_" + key for key in _SAVES)
            + (tuple(_MASSAGE) if self.command_selector in _POSITIVE_SELECTORS else ())
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = (
            "wake",
            "refresh",
            "firmware",
            "use_detected_profile",
            "massage_release",
            "union_up",
            "union_down",
            "light_plus",
            "light_minus",
            "save_tv",
            "save_lounge",
            "save_zero_g",
            "reset",
        )
        if self._native_light_power_buttons:
            actions += ("light_on", "light_off")
        return tuple(
            ControllerButtonSpec(
                "starcode_abm5_4_" + action,
                action.replace("_", " ").title(),
                _button(action),
                translation_key="starcode_abm5_4_" + action,
                cancel_movement=action not in ("light_plus", "light_minus", "light_on", "light_off"),
                scheduler_resource="lighting"
                if action in ("light_plus", "light_minus", "light_on", "light_off")
                else None,
            )
            for action in actions
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.command_selector not in _POSITIVE_SELECTORS:
            return ()
        return (
            ControllerSelectSpec(
                "starcode_abm5_4_massage_timer",
                "starcode_abm5_4_massage_timer",
                "starcode_abm5_4_massage_timer",
                ("10", "20", "30"),
                _timer,
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if self.command_selector not in _POSITIVE_SELECTORS:
            return ()
        return (
            ControllerNumberSpec(
                "starcode_abm5_4_light_level",
                "starcode_abm5_4_light_level",
                "starcode_abm5_4_light_level",
                1,
                6,
                1,
                _brightness,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                "starcode_abm5_4_" + key,
                "starcode_abm5_4_" + key,
                "starcode_abm5_4_" + key,
                "mdi:information-outline",
                entity_registry_enabled_default=not key.startswith("raw_"),
            )
            for key in STATE_KEYS
        )

    def _role(self, client: BleakClient, uuid: str) -> BleakGATTCharacteristic:
        service_uuid = (
            "0000180a-0000-1000-8000-00805f9b34fb"
            if uuid in (MANUFACTURER_UUID, FIRMWARE_UUID)
            else self._transport.service
        )
        for service in client.services:
            if service.uuid.lower() != service_uuid:
                continue
            for char in service.characteristics:
                if char.uuid.lower() == uuid:
                    return char
        raise ConnectionError("Required app characteristic is absent: " + uuid)

    def _session_valid(self, client: BleakClient, generation: int) -> bool:
        return (
            client is self.client
            and client.is_connected
            and generation == self._session_generation
            and self._coordinator.address == self._owner_address
        )

    async def _send(
        self,
        packet: bytes,
        event: asyncio.Event | None = None,
        *,
        client: BleakClient | None = None,
        response: bool | None = None,
    ) -> None:
        if self.command_side is not None:
            raise ValueError("This app has no one-address side selector")
        target = client or self.client
        if (
            target is None
            or not target.is_connected
            or self._coordinator.address != self._owner_address
        ):
            raise ConnectionError("Original physical app target is not connected")
        async with self.ble_lock:
            if (
                target is not self.client
                or not target.is_connected
                or self._coordinator.address != self._owner_address
            ):
                raise ConnectionError("Original physical app target changed before write")
            if event is not None and event.is_set():
                return
            role = self._write_characteristic if target is self._notify_client else None
            role = role or self._role(target, self._transport.write)
            write_response = self.transport_selector == "BOX3633" if response is None else response
            payload = self._format_command_trace_payload(packet)
            if payload is not None:
                self._coordinator.record_command_trace(
                    payload=payload,
                    characteristic_uuid=role.uuid,
                    characteristic_handle=role.handle,
                    response=write_response,
                    repeat_count=1,
                    repeat_delay_ms=100,
                    command_origin="app_control",
                    controller_class=type(self).__name__,
                )
            await target.write_gatt_char(role, packet, response=write_response)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        event = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if event.is_set():
                return
            await self._send(command, event)
            if index + 1 < repeat_count:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _wait(self, duration: float, event: asyncio.Event) -> bool:
        try:
            await asyncio.wait_for(event.wait(), timeout=duration)
            return False
        except TimeoutError:
            return True

    async def _send_refresh(
        self, packet: bytes, event: asyncio.Event, *, client: BleakClient
    ) -> None:
        """A failed app timer write does not trigger a retry or cancel later ticks."""
        try:
            await self._send(packet, event, client=client)
        except (BleakError, TimeoutError) as error:
            _LOGGER.warning("App control write failed without acknowledgement: %s", error)

    async def _stream(
        self, action: str, duration_ms: int, *, release: str = "stop", value: int = 0
    ) -> None:
        self._operation_generation += 1
        operation = self._operation_generation
        client = self.client
        session = self._session_generation
        if client is None or not self._session_valid(client, session):
            raise ConnectionError("No connected original app target")
        packet = build_frame(self.command_selector, action, value)
        self._active_release = (client, session, operation, release)
        event = self._coordinator.cancel_command
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        first = True
        try:
            while (
                (first or asyncio.get_running_loop().time() < deadline)
                and not event.is_set()
                and operation == self._operation_generation
                and self._session_valid(client, session)
            ):
                started = asyncio.get_running_loop().time()
                await self._send_refresh(packet, event, client=client)
                first = False
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                delay = min(max(0.0, started + 0.1 - asyncio.get_running_loop().time()), remaining)
                if delay and not await self._wait(delay, event):
                    break
        finally:
            if operation == self._operation_generation and self._session_valid(client, session):
                fresh = asyncio.Event()
                if release == "massage":
                    await asyncio.sleep(0.1)
                    if operation == self._operation_generation and self._session_valid(
                        client, session
                    ):
                        await self._send_refresh(
                            build_frame(self.command_selector, "stop"), fresh, client=client
                        )
                        await asyncio.sleep(0.2)
                        if operation == self._operation_generation and self._session_valid(
                            client, session
                        ):
                            await self._send_refresh(
                                build_frame(self.command_selector, "queryMassage"),
                                fresh,
                                client=client,
                            )
                elif (
                    release == "stop"
                    or release == "preset"
                    and self.ui_selector in ("BOX25", "BOX25_STAR")
                ):
                    await self._send_refresh(
                        build_frame(self.command_selector, "stop"), fresh, client=client
                    )

            if self._active_release is not None and self._active_release[2] == operation:
                self._active_release = None

    async def _once(self, action: str, value: int = 0, *, massage_release: bool = False) -> None:
        await self._stream(action, 0, release="massage" if massage_release else "none", value=value)

    def _require_positive(self, *, light: bool = False) -> None:
        if self.command_selector not in _POSITIVE_SELECTORS or not (
            self._light_on if light else self._massage_on
        ):
            raise ValueError("The app requires observed own-address active state for this control")

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if self.command_side is not None:
            raise ValueError("This app has no one-address side selector")
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise ValueError("Unsupported app held control or duration")
        if control in _MASSAGE:
            self._require_positive()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control in _MOVEMENT:
            await self._stream(_MOVEMENT[control], duration_ms)
        elif control in _PRESETS:
            await self._stream(
                _PRESETS[control],
                600 if control == "flat" else duration_ms,
                release="preset",
            )
        elif control.startswith("save_"):
            await self._stream(
                _SAVES[control[5:]],
                6000,
                release="stop" if control == "save_memory_1" else "preset",
            )
        else:
            self._require_positive()
            await self._stream(
                _MASSAGE[control],
                duration_ms if control.startswith("wave") else 0,
                release="massage",
            )

    async def app_action(self, action: str) -> None:
        if action == "wake":
            await self._once("keepConnect")
        elif action == "refresh":
            await self._once("queryMassage")
        elif action == "firmware":
            await self._read_firmware()
        elif action == "use_detected_profile":
            await self.adopt_transport_profile()
        elif action == "massage_release":
            await self.release_massage()
        elif action in ("union_up", "union_down"):
            await self.hold_control(action, self._coordinator.motor_pulse_count * 100)
        elif action == "light_on":
            await self.lights_on()
        elif action == "light_off":
            await self.lights_off()
        elif action in ("light_plus", "light_minus"):
            await self._light_step(1 if action == "light_plus" else -1)
        elif action == "reset":
            await self._stream("resetMemory", 6000, release="preset")
        elif action.startswith("save_") and action[5:] in _SAVES:
            await self._stream(_SAVES[action[5:]], 6000, release="preset")
        else:
            raise ValueError("Unreachable app action")

    async def release_massage(self) -> None:
        """A disabled custom hit still schedules STOP100ms and query300ms."""
        self._operation_generation += 1
        operation = self._operation_generation
        session = self._session_generation
        client = self.client
        if client is None or not self._session_valid(client, session):
            raise ConnectionError("No connected original app target")
        await asyncio.sleep(0.1)
        if operation == self._operation_generation and self._session_valid(client, session):
            await self._send_refresh(
                build_frame(self.command_selector, "stop"), asyncio.Event(), client=client
            )
            await asyncio.sleep(0.2)
            if operation == self._operation_generation and self._session_valid(client, session):
                await self._send_refresh(
                    build_frame(self.command_selector, "queryMassage"),
                    asyncio.Event(),
                    client=client,
                )

    async def set_app_timer(self, option: str) -> None:
        self._require_positive()
        if option not in ("10", "20", "30"):
            raise ValueError("App timer has only 10/20/30 minutes, no Off frame")
        await self._once("changeMassageTime", int(option) // 10, massage_release=True)

    async def set_app_brightness(self, value: float) -> None:
        self._require_positive(light=True)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or isinstance(value, float)
            and not value.is_integer()
        ):
            raise ValueError("Brightness is an exact integer app level")
        if not 1 <= value <= 6:
            raise ValueError("Brightness is outside 1..6")
        if not self._accept_light_action():
            return
        self._level = int(value)
        self._publish()
        await self._once("changeLightBrightness", self._level)

    def _accept_light_action(self) -> bool:
        """Level and status actions share the app's strict 500 ms gate."""
        now = int(asyncio.get_running_loop().time() * 1000)
        if self._last_light_time_ms is not None and now - self._last_light_time_ms <= 500:
            return False
        self._last_light_time_ms = now
        self._retain_ui_state()
        return True

    async def _light_step(self, direction: int) -> None:
        if not self._accept_light_action():
            return
        level = min(6, self._level + 1) if direction > 0 else self._level - 1
        if level <= 0:
            await self._once("turnoffUnderbedLighting")
        else:
            if self.command_selector not in _POSITIVE_SELECTORS:
                level = 2
            await self._once("changeLightBrightness", level)

    async def stop(self) -> None:
        self._operation_generation += 1
        await self._send(build_frame(self.command_selector, "stop"), asyncio.Event())

    async def lights_on(self) -> None:
        if self._accept_light_action():
            await self._once("turnonUnderbedLighting")

    async def lights_off(self) -> None:
        if self._accept_light_action():
            await self._once("turnoffUnderbedLighting")

    async def lights_toggle(self) -> None:
        if self._accept_light_action():
            await self._once("underbedLighting")

    async def underbed_lights_on(self) -> None:
        await self.lights_on()

    async def underbed_lights_off(self) -> None:
        await self.lights_off()

    async def underbed_lights_toggle(self) -> None:
        await self.lights_toggle()

    async def massage_toggle(self) -> None:
        await self._once("massageOnOff", massage_release=True)

    async def massage_head_up(self) -> None:
        self._require_positive()
        await self._once("headStrengthAdd", massage_release=True)

    async def massage_head_down(self) -> None:
        self._require_positive()
        await self._once("headStrengthReduce", massage_release=True)

    async def massage_foot_up(self) -> None:
        self._require_positive()
        await self._once("footStrengthAdd", massage_release=True)

    async def massage_foot_down(self) -> None:
        self._require_positive()
        await self._once("footStrengthReduce", massage_release=True)

    async def massage_wave_next(self) -> None:
        await self.hold_control("wave_up", self._coordinator.motor_pulse_count * 100)

    async def massage_wave_previous(self) -> None:
        await self.hold_control("wave_down", self._coordinator.motor_pulse_count * 100)

    async def preset_flat(self) -> None:
        await self.hold_control("flat", 600)

    async def preset_zero_g(self) -> None:
        await self.hold_control("zero_g", self._coordinator.motor_pulse_count * 100)

    async def preset_tv(self) -> None:
        await self.hold_control("tv", self._coordinator.motor_pulse_count * 100)

    async def preset_lounge(self) -> None:
        await self.hold_control("lounge", self._coordinator.motor_pulse_count * 100)

    async def preset_anti_snore(self) -> None:
        await self.hold_control("anti_snore", self._coordinator.motor_pulse_count * 100)

    async def preset_memory(self, memory_num: int = 1) -> None:
        if memory_num != 1:
            raise ValueError("Both app memory images recall only Memory A")
        await self.hold_control("memory_1", self._coordinator.motor_pulse_count * 100)

    async def program_memory(self, memory_num: int = 1) -> None:
        if memory_num != 1:
            raise ValueError("Only Memory A save is reachable")
        await self._stream("saveM1", 6000, release="stop")

    async def stop_all(self) -> None:
        await self.stop()

    async def move_head_stop(self) -> None:
        await self.stop()

    async def move_back_stop(self) -> None:
        await self.stop()

    async def move_legs_stop(self) -> None:
        await self.stop()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("The app has no separate feet actuator")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("The app has no separate feet actuator")

    async def move_feet_stop(self) -> None:
        await self.stop()

    async def move_head_up(self) -> None:
        await self.hold_control("head_up", self._coordinator.motor_pulse_count * 100)

    async def move_head_down(self) -> None:
        await self.hold_control("head_down", self._coordinator.motor_pulse_count * 100)

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_legs_up(self) -> None:
        await self.hold_control("foot_up", self._coordinator.motor_pulse_count * 100)

    async def move_legs_down(self) -> None:
        await self.hold_control("foot_down", self._coordinator.motor_pulse_count * 100)

    def _retain_ui_state(self) -> None:
        if self._coordinator.address != self._owner_address:
            return
        self._coordinator.starcode_app_retained_state = RetainedAppState(
            address=self._owner_address,
            observed=self._ui_state_observed,
            massage_on=self._massage_on,
            light_on=self._light_on,
            level=self._level,
            timer_index=self._timer_index,
            head_intensity=self._head_intensity,
            wave=self._wave,
            low_4b=self._low_4b,
            automatic_white_flag=self._automatic_white_flag,
            last_light_time_ms=self._last_light_time_ms,
        )

    def _publish(self) -> None:
        if self._coordinator.address != self._owner_address:
            return
        self._retain_ui_state()
        values: dict[str, str | int | bool | None] = {
            "raw_" + k: v if self._parser_state_observed else None
            for k, v in self._raw_fields.items()
        }
        values.update(
            {
                "command_selector": self.command_selector,
                "transport_selector": self.transport_selector,
                "ui_selector": self.ui_selector,
                "manufacturer": self._manufacturer,
                "firmware": self._firmware,
                "massage_timer": str(self._timer_index * 10) if self._timer_index else None,
                "light_level": self._level,
                "massage_on": self._massage_on if self._ui_state_observed else None,
                "light_on": self._light_on if self._ui_state_observed else None,
                "wave": self._wave,
                "head_intensity": self._head_intensity,
                "low_4b": self._low_4b,
                "automatic_white_flag": self._automatic_white_flag,
            }
        )
        self.forward_controller_state_updates(
            {"starcode_abm5_4_" + k: v for k, v in values.items()}
        )

    def _spawn(self, operation: Callable[[], Coroutine[object, object, None]]) -> None:
        async def run() -> None:
            try:
                result = operation()
                await result
            except ConnectionError, asyncio.CancelledError:
                pass
            except Exception:
                _LOGGER.debug("App delayed operation failed", exc_info=True)

        task = asyncio.create_task(run(), context=copy_context_without_command())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _notification(
        self, client: BleakClient, session: int, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if not self._session_valid(client, session):
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        updates = parse_fields(self.command_selector, bytes(data))
        if not updates:
            return
        first_observation = not self._parser_state_observed
        self._parser_state_observed = True
        if all(self._raw_fields[k] == v for k, v in updates.items()):
            if first_observation:
                self._publish()
            return
        self._raw_fields.update(updates)
        if self.ui_selector in ("BOX25", "BOX25_STAR"):
            self._ui_state_observed = True
            self._timer_index = int(self._raw_fields["b"])
            self._massage_on = self._timer_index > 0
            self._light_on = bool(self._raw_fields["43"])
            self._level = int(self._raw_fields["53"])
            self._head_intensity = max(int(self._raw_fields["13"]) - 1, 0)
            self._wave = int(self._raw_fields["23"])
            self._low_4b = int(self._raw_fields["4b"])
            self._automatic_white_flag = bool(self._raw_fields["47"])
            if self._raw_fields["47"]:
                generation = self._operation_generation

                async def white() -> None:
                    if generation != self._operation_generation or not self._session_valid(
                        client, session
                    ):
                        return

                    async def action(_controller: BedController) -> None:
                        if generation == self._operation_generation and self._session_valid(
                            client, session
                        ):
                            await self._stream("change2White", 5000, release="none")

                    await self._coordinator.async_execute_controller_command(
                        action, cancel_running=False
                    )

                self._spawn(white)
        self._publish()

    async def _read_optional(self, uuid: str, *, retry_delay: float | None = None) -> bytes | None:
        client = self.client
        if client is None:
            return None
        try:
            role = self._role(client, uuid)
        except ConnectionError:
            return None
        session = self._session_generation
        for attempt in range(2 if retry_delay is not None else 1):
            if not self._session_valid(client, session):
                return None
            try:
                async with self.ble_lock:
                    result = bytes(await client.read_gatt_char(role))
                return result if self._session_valid(client, session) else None
            except Exception:
                if attempt == 0 and retry_delay is not None:
                    await asyncio.sleep(retry_delay)
                else:
                    _LOGGER.debug("Optional app read failed", exc_info=True)
        return None

    async def _read_firmware(self) -> None:
        data = await self._read_optional(FIRMWARE_UUID)
        if data is not None:
            self._firmware = data.decode("utf-8", errors="replace")
            self._publish()

    def _persist_selectors(self, *, capabilities_changed: bool = False) -> None:
        data = dict(self._coordinator.entry.data)
        data["starcode_abm5_4_command_selector"] = self.command_selector
        data["starcode_abm5_4_ui_selector"] = self.ui_selector
        if data == dict(self._coordinator.entry.data):
            return
        from ..const import (
            CONF_BLE_BOND_ESTABLISHED,
            CONF_STARCODE_COMMAND_SELECTOR,
            CONF_STARCODE_UI_SELECTOR,
        )

        self._coordinator._begin_internal_entry_update(
            bool(data.get(CONF_BLE_BOND_ESTABLISHED, False))
        )
        if capabilities_changed and self._coordinator._pending_internal_bond_marker is not None:
            self._coordinator._pending_capability_reload = True
            self._coordinator._offline_controller = self
        self._coordinator._async_persist_config(
            data, keys={CONF_STARCODE_COMMAND_SELECTOR, CONF_STARCODE_UI_SELECTOR}
        )
        if capabilities_changed:
            self._coordinator._schedule_pending_capability_reload()

    async def adopt_transport_profile(self) -> None:
        """App AddDevice copies D into C/U, retaining this address's UI state."""
        if self._coordinator.address != self._owner_address:
            raise ValueError("Cannot move observed state to another physical bed")
        await self._cleanup_active()
        self._operation_generation += 1
        previous_catalog = self._entity_catalog_signature
        self.command_selector = self.transport_selector
        self.ui_selector = self.transport_selector
        self._persist_selectors(
            capabilities_changed=previous_catalog != self._entity_catalog_signature
        )
        self._publish()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.starcode.abm5_4",
            "address_owned_state": self._owner_address,
            "command_selector": self.command_selector,
            "transport_selector": self.transport_selector,
            "ui_selector": self.ui_selector,
            "raw_fields": dict(self._raw_fields),
            "manufacturer": self._manufacturer,
            "firmware": self._firmware,
            "observed_massage_on": self._massage_on,
            "observed_light_on": self._light_on,
            "ready": self._ready,
            "hardware_verified": False,
        }

    async def _classify(self) -> None:
        data = await self._read_optional(MANUFACTURER_UUID, retry_delay=0.2)
        if data is None:
            return
        self._manufacturer = data.decode("utf-8", errors="replace")
        if self._transport.wake:
            previous_catalog = self._entity_catalog_signature
            self.command_selector = manufacturer_selector(self._manufacturer)
            # Both manufacturer choices keep the same UART roles; D changes independently of U.
            self.transport_selector = self.command_selector
            self._persist_selectors(
                capabilities_changed=previous_catalog != self._entity_catalog_signature
            )
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        async with self._initialization_lock:
            self._startup_task = asyncio.current_task()
            try:
                await self._start_notify(callback)
            except asyncio.CancelledError:
                # Cancellation can also arrive while releasing an old session,
                # before _start_notify enters its new-session failure handler.
                await self.stop_notify()
                raise
            finally:
                self._startup_task = None

    async def _start_notify(self, callback: Callable[[str, float], None] | None) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("No app BLE client")
        if (
            self._notify_client is client
            and self._ready
            and self._session_valid(client, self._session_generation)
        ):
            return
        await self.stop_notify()
        self._session_generation += 1
        session = self._session_generation
        self._notify_callback = callback
        self._notify_client = client
        self._classification_complete = not self._transport.wake
        notify: BleakGATTCharacteristic | None = None
        subscription_attempted = False

        async def initialize_roles() -> None:
            nonlocal subscription_attempted
            if not self._session_valid(client, session):
                raise ConnectionError("App target changed before initialization")
            self._write_characteristic = self._role(client, self._transport.write)
            notify = self._role(client, self._transport.notify)
            if self._transport.wake:
                try:
                    await self._send(
                        build_frame(self.command_selector, "keepConnect"),
                        client=client,
                        response=True,
                    )
                except Exception:
                    if not self._session_valid(client, session):
                        raise ConnectionError("App target changed before wake retry") from None
                    await self._send(
                        build_frame(self.command_selector, "keepConnect"),
                        client=client,
                        response=True,
                    )
                if not self._session_valid(client, session):
                    raise ConnectionError("App target changed during wake initialization")
            if self._transport.subscribe:
                for attempt in range(2):
                    try:
                        subscription_attempted = True
                        await client.start_notify(
                            notify,
                            lambda sender, data: self._notification(client, session, sender, data),
                        )
                        if not self._session_valid(client, session):
                            raise ConnectionError(
                                "App target changed during notification initialization"
                            )
                        self._notify_characteristic = notify
                        break
                    except Exception:
                        if attempt or not self._session_valid(client, session):
                            raise
                        await asyncio.sleep(2)
                        if not self._session_valid(client, session):
                            raise ConnectionError(
                                "App target changed before notification retry"
                            ) from None

        async def classify() -> None:
            await self._classify()
            if self._session_valid(client, session):
                self._classification_complete = True
                self._publish()

        classification_task: asyncio.Task[None] | None = None
        if self._transport.wake:
            classification_task = asyncio.create_task(classify())
            self._tasks.add(classification_task)
            classification_task.add_done_callback(self._tasks.discard)
        else:
            self._spawn(classify)

        async def connected_reads() -> None:
            await asyncio.sleep(0.5)
            if not self._session_valid(client, session):
                return

            async def query(_controller: BedController) -> None:
                if self._session_valid(client, session):
                    await self._once("queryMassage")

            await self._coordinator.async_execute_controller_command(query, cancel_running=False)
            await asyncio.sleep(1)
            if self._session_valid(client, session):
                await self._read_firmware()

        self._spawn(connected_reads)
        try:
            notify = self._role(client, self._transport.notify)
            await initialize_roles()
            if classification_task is not None:
                await classification_task
            if not self._session_valid(client, session):
                raise ConnectionError("App target changed during initialization")
            self._ready = True
            self._publish()
        except Exception, asyncio.CancelledError:
            if classification_task is not None:
                classification_task.cancel()
                await asyncio.gather(classification_task, return_exceptions=True)
            if session == self._session_generation and self._notify_client is client:
                await self.stop_notify()
            # Also undo a partially-completed backend subscription. Initialization
            # is serialized, so cleanup cannot remove a newer subscription.
            if subscription_attempted and notify is not None and client.is_connected:
                try:
                    await client.stop_notify(notify)
                except Exception:
                    _LOGGER.debug("App failed-start notification cleanup failed", exc_info=True)
            raise

    async def _cleanup_active(self) -> None:
        active = self._active_release
        if active is None:
            return
        client, session, operation, release = active
        if (
            operation == self._operation_generation
            and self._session_valid(client, session)
            and (
                release in ("stop", "massage")
                or release == "preset"
                and self.ui_selector in ("BOX25", "BOX25_STAR")
            )
        ):
            self._operation_generation += 1
            try:
                await self._send(
                    build_frame(self.command_selector, "stop"), asyncio.Event(), client=client
                )
            except Exception:
                _LOGGER.debug("Original-owner app release failed during teardown", exc_info=True)
        self._active_release = None

    async def stop_notify(self) -> None:
        startup = self._startup_task
        if startup is not None and startup is not asyncio.current_task() and not startup.done():
            startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
            # Its cancellation handler owns cleanup. A waiting replacement may
            # already be starting, so this caller must not clear its resources.
            return
        client, role = self._notify_client, self._notify_characteristic
        await self._cleanup_active()
        self._session_generation += 1
        self._operation_generation += 1
        tasks = tuple(task for task in self._tasks if task is not asyncio.current_task())
        for task in tasks:
            task.cancel()
        self._tasks.clear()
        self._notify_client = None
        self._notify_characteristic = None
        self._write_characteristic = None
        self._notify_callback = None
        self._ready = False
        self._classification_complete = not self._transport.wake
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if client is not None and client.is_connected and role is not None:
            await client.stop_notify(role)

    async def read_positions(self, motor_count: int = 2) -> None:
        return None

    async def async_discover_capabilities(self) -> None:
        if not self._ready:
            await self.start_notify()
