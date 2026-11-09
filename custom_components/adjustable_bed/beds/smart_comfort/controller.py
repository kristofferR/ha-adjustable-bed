"""Smart Comfort session and immutable, seat-scoped movement cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_PRESETS
from ...codec import smart_comfort as codec
from ...profiles.smart_comfort import HELD, SYNARGY, SYNERGY, SmartComfortProfile
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .state_keys import (
    COUNTER_1,
    COUNTER_2,
    COUNTER_3,
    CUP_ON,
    MODEL,
    READ_BRIGHTNESS,
    READ_ON,
    SEAT,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass
class SmartComfortSession:
    """Keep HA's chosen transport target across controller recreation."""

    seat: int = 0


class SmartComfortController(ProfileExecution[SmartComfortProfile], BedController):
    """One BLE peripheral with a model-selected logical seat selector."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: SmartComfortProfile = SYNARGY
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._model: int | None = None
        self._flags = (0, 0, 0)
        self.session = app_session(
            coordinator.hass,
            coordinator.address,
            ("smart_comfort", profile.key),
            SmartComfortSession,
        )
        self._system = asyncio.Event()
        self._subscribed = False
        self._ready = False
        self._device_state: codec.DeviceState | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE_UUID

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def selectable_seats(self) -> tuple[int, ...]:
        return codec.MODELS[self._model][3] if self._model in codec.MODELS else ()

    def _address(self, feature: int = 0) -> int:
        if not self._ready or self.session.seat not in self.selectable_seats:
            raise ValueError("Smart Comfort needs a recognized system reply and selected seat")
        if feature and not self._flags[self.session.seat] & feature:
            raise ValueError("This accessory is not available on the selected logical seat")
        return self.session.seat

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self._model is not None

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": self.profile.package,
            "model_code": self._model,
            "logical_seat": self.session.seat,
            "seat_flags": self._flags,
            "selectable_seats": self.selectable_seats,
            "device_state_scope": "group; reply has no verified seat discriminator",
        }

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        char = self._writable_characteristic(codec.WRITE_UUID)
        response = "write" in char.properties
        await self._write_gatt_with_retry(
            codec.WRITE_UUID,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
            response=response,
        )

    def _writable_characteristic(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Smart Comfort is disconnected")
        char = client.services.get_characteristic(uuid)
        if char is None or not {"write", "write-without-response"}.intersection(char.properties):
            raise ConnectionError("Smart Comfort characteristic is missing or not writable")
        return char

    async def async_on_connect(self, session: ControllerSession) -> None:
        self._ready = False
        self._subscribed = False
        self._system.clear()
        if self.profile.notify_delay_ms is not None:
            await asyncio.sleep(self.profile.notify_delay_ms / 1000)
        # Notifications carry capabilities/accessory state even with angles disabled.
        await self.start_notify()
        await self.write_command(codec.command("query_system"))
        async with asyncio.timeout(self.profile.system_timeout_ms / 1000):
            await self._system.wait()
        if not self.selectable_seats:
            raise ValueError("Unrecognized Smart Comfort model, no seat controls enabled")
        self._ready = True
        await self.write_command(codec.command("query_device", self.session.seat))

    @property
    def reads_light_state_on_connect(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._subscribed:
            return
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Smart Comfort is disconnected")
        async with self._ble_lock:
            await self.client.start_notify(codec.NOTIFY_UUID, self._notification)
        self._subscribed = True

    async def stop_notify(self) -> None:
        self._ready = False
        if self._subscribed and self.client is not None and self.client.is_connected:
            async with self._ble_lock:
                await self.client.stop_notify(codec.NOTIFY_UUID)
        self._subscribed = False

    def _notification(self, _sender: BleakGATTCharacteristic, payload: bytearray) -> None:
        self.forward_raw_notification(codec.NOTIFY_UUID, bytes(payload))
        state = codec.parse_notification(bytes(payload))
        if isinstance(state, codec.SystemState):
            if state.code in codec.MODELS:
                self._model = state.code
            self._flags = state.flags
            if self.selectable_seats and self.session.seat not in self.selectable_seats:
                self.session.seat = self.selectable_seats[0]
            self.forward_controller_state_updates(MODEL(self._model), SEAT(str(self.session.seat)))
            self._system.set()
        elif isinstance(state, codec.DeviceState):
            self._device_state = state
            self.forward_controller_state_updates(
                READ_ON(state.read_on),
                CUP_ON(state.cup_on),
                READ_BRIGHTNESS(state.read_brightness),
                LIGHT_LEVEL(state.base_brightness),
                UNDER_BED_LIGHTS_ON(
                    state.base_on if self._flags[self.session.seat] & 2 else state.cup_on
                ),
                UNDER_BED_LIGHTS_RGB(state.rgb),
            )
        elif isinstance(state, codec.RippleState):
            self.forward_controller_state_updates(
                COUNTER_1(state.counters[0]),
                COUNTER_2(state.counters[1]),
                COUNTER_3(state.counters[2]),
            )

    async def select_seat(self, option: str) -> None:
        address = int(option)
        if address not in self.selectable_seats:
            raise ValueError("Seat is not selectable for this Smart Comfort model")
        self.session.seat = address
        self.forward_controller_state_updates(SEAT(option))
        await self.write_command(codec.command("query_device", address))

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.selectable_seats:
            return ()
        return (
            ControllerSelectSpec(
                "smart_comfort_seat",
                "smart_comfort_seat",
                SEAT,
                tuple(str(a) for a in self.selectable_seats),
                lambda ctrl, option: require_controller(ctrl, SmartComfortController).select_seat(
                    option
                ),
            ),
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return HELD

    async def _move(self, action: str, *, duration_ms: int | None = None) -> None:
        address = self._address()
        frame = codec.command(action, address)
        count = self.leased_hold_refreshes(self.profile.refresh_ms)
        if duration_ms is not None:
            count = max(1, (duration_ms + self.profile.refresh_ms - 1) // self.profile.refresh_ms)
        if count is None:
            count = self._coordinator.motor_pulse_count
        try:
            await self.write_command(frame, count, self.profile.refresh_ms)
        finally:
            await self._release(address)

    async def _release(self, address: int) -> None:
        """Drain the delayed neutral write before cancellation frees serialization."""
        frame = codec.command("stop", address)

        async def release() -> None:
            await asyncio.sleep(self.profile.release_ms / 1000)
            await self.write_command(frame, cancel_event=asyncio.Event())

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

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in HELD:
            raise ValueError("Unknown Smart Comfort held control")
        await self._move(control, duration_ms=duration_ms)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec(
                "head",
                "head",
                lambda c: c.move_head_up(),
                lambda c: c.move_head_down(),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec("head_up", "head_down"),
            ),
            MotorControlSpec(
                "back",
                "smart_comfort_reclining",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec("reclining_up", "reclining_down"),
            ),
            MotorControlSpec(
                "lumbar",
                "lumbar",
                lambda c: c.move_lumbar_up(),
                lambda c: c.move_lumbar_down(),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec("lumbar_up", "lumbar_down"),
            ),
        )

    async def move_head_up(self) -> None:
        await self._move("head_up")

    async def move_head_down(self) -> None:
        await self._move("head_down")

    async def move_back_up(self) -> None:
        await self._move("reclining_up")

    async def move_back_down(self) -> None:
        await self._move("reclining_down")

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar_down")

    async def stop_all(self) -> None:
        await self.write_command(
            codec.command("stop", self._address()), cancel_event=asyncio.Event()
        )

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_lumbar_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def move_legs_up(self) -> None:
        raise NotImplementedError("Use the Smart Comfort reclining control")

    async def move_legs_down(self) -> None:
        raise NotImplementedError("Use the Smart Comfort reclining control")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    @property
    def supports_preset_flat(self) -> bool:
        return False  # Home is held, not an autonomous flat preset.

    async def preset_flat(self) -> None:
        await self._move("home")

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    async def _memory(self, slot: int, save: bool) -> None:
        if isinstance(slot, bool) or slot not in (1, 2):
            raise ValueError("Smart Comfort has two memories")
        address = self._address()
        await self.write_command(codec.command("memory_prepare", address))
        await self.write_command(codec.command(f"{'save' if save else 'recall'}_{slot}", address))

    async def preset_memory(self, memory_num: int) -> None:
        await self._memory(memory_num, False)

    async def program_memory(self, memory_num: int) -> None:
        await self._memory(memory_num, True)

    async def accessory(self, action: str, *, value: int = 30) -> None:
        feature = 1 if action.startswith("cup_") else 4 if action.startswith("read_") else 2
        address = self._address(feature)
        await self.write_command(codec.command(action, address, value=value))

    @property
    def supports_light_color_control(self) -> bool:
        return any(self._flags[a] & 3 for a in self.selectable_seats)

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_light_level_control(self) -> bool:
        return self.supports_light_color_control

    @property
    def light_level_min(self) -> int:
        return 4

    @property
    def light_level_max(self) -> int:
        return 100

    async def lights_on(self) -> None:
        await self.accessory("base_on" if self._flags[self._address()] & 2 else "cup_on")

    async def lights_off(self) -> None:
        await self.accessory("base_off" if self._flags[self._address()] & 2 else "cup_off")

    async def set_light_level(self, level: int) -> None:
        self._address()
        if not self._flags[self.session.seat] & 3:
            raise ValueError("Seat has no base/cup color controls")
        await self.write_command(
            codec.command(
                "base_brightness",
                self.session.seat,
                value=max(4, level) if 1 <= level <= 100 else level,
            )
        )

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        address = self._address()
        if not self._flags[address] & 3:
            raise ValueError("Seat has no base/cup color controls")
        await self.write_command(codec.command("color", address, rgb=rgb_color))

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        return self._device_state.rgb if self._device_state else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "smart_comfort_home",
                "Home",
                lambda c: require_controller(c, SmartComfortController)._move("home"),
                translation_key="smart_comfort_home",
                hold=ControllerHoldSpec("home"),
                card=CARD_PRESETS,
            )
        ]
        for action in codec.ACCESSORIES:
            feature = 1 if action.startswith("cup_") else 4 if action.startswith("read_") else 2
            if not any(self._flags[a] & feature for a in self.selectable_seats):
                continue
            specs.append(
                ControllerButtonSpec(
                    f"smart_comfort_{action}",
                    action.replace("_", " ").title(),
                    lambda c, action=action: require_controller(
                        c, SmartComfortController
                    ).accessory(action),
                    translation_key=f"smart_comfort_{action}",
                    card=CARD_LIGHTING,
                )
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not any(self._flags[address] & 4 for address in self.selectable_seats):
            return ()
        return (
            ControllerNumberSpec(
                "smart_comfort_read_brightness",
                "smart_comfort_read_brightness",
                READ_BRIGHTNESS,
                4,
                100,
                1,
                lambda c, value: require_controller(c, SmartComfortController).accessory(
                    "read_brightness", value=int(value)
                ),
                card=CARD_LIGHTING,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "smart_comfort_read", "smart_comfort_read", READ_ON, "mdi:lightbulb"
            ),
            ControllerStateBinarySensorSpec(
                "smart_comfort_cup", "smart_comfort_cup", CUP_ON, "mdi:cup"
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(name, name, key, "mdi:counter")
            for name, key in (
                ("smart_comfort_model", MODEL),
                ("smart_comfort_counter_1", COUNTER_1),
                ("smart_comfort_counter_2", COUNTER_2),
                ("smart_comfort_counter_3", COUNTER_3),
            )
        )

    def validate_device_rename(self, name: str) -> None:
        codec.rename(name)

    def controller_button_available(self, key: str) -> bool:
        action = key.removeprefix("smart_comfort_")
        if action not in codec.ACCESSORIES:
            return True
        feature = 1 if action.startswith("cup_") else 4 if action.startswith("read_") else 2
        return self._ready and bool(self._flags[self.session.seat] & feature)

    @property
    def supports_device_rename(self) -> bool:
        return True

    async def rename_device(self, name: str) -> None:
        data = codec.rename(name)
        char = self._writable_characteristic(codec.NAME_UUID)
        await self._write_gatt_with_retry(
            codec.NAME_UUID, data, response="write" in char.properties
        )


async def build_controller(ctx: BuildContext) -> SmartComfortController:
    return SmartComfortController(
        ctx.coordinator, SYNERGY if ctx.bed_type == "smart_comfort_synergy" else SYNARGY
    )
