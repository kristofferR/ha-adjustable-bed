"""ComfortBaseForBluetooth app behavior over Keeson's proven E6/clock/alarm codec.

Accepted row161, com.ore.yorkfeng.comfortbaseble2 1.1.2 (6).
Hardware movement mapping and memory persistence remain unverified.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE_TIMER, CARD_PRESETS
from ...codec import keeson as codec
from ...const import KEESON_BASE_NOTIFY_CHAR_UUID, KEESON_BASE_WRITE_CHAR_UUID
from ...profiles import comfortbase as app
from ...profiles.comfortbase import NOTIFY_SERVICE as NOTIFY_SERVICE
from ...profiles.comfortbase import WRITE_SERVICE as WRITE_SERVICE
from ...profiles.keeson import Preset
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .controller import KeesonController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

def _axis(axis: str, up: bool) -> MotorCommandCallable:
    async def move(controller: BedController) -> None:
        await cast(ComfortBaseController, controller)._move_motor(axis, up)

    return move


class ComfortBaseController(KeesonController):
    """One selected product, one global held key and cancellation-safe release."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        if product not in app.PRODUCTS:
            raise ValueError("Choose a ComfortBaseForBluetooth product")
        super().__init__(coordinator, variant="comfortbase")
        self.product = app.PRODUCTS[product]
        self._notify_char: BleakGATTCharacteristic | None = None
        self._assembler = codec.ComfortBaseAssembler()

    def _build_command(self, command_value: int) -> bytes:
        """Keep inherited helpers inside this product's proven action vocabulary."""
        allowed = {0, *app.PRESETS.values(), *app.MEMORY.values()}
        allowed.update(word for axis in self.product.axes for word in app.AXES[axis][1:])
        if self.product.massage_light:
            allowed.update((*app.MASSAGE.values(), app.LIGHT_TOGGLE))
        if command_value not in allowed:
            raise NotImplementedError("This ComfortBase product has no such command")
        return super()._build_command(command_value)

    def _role(self, service_uuid: str, char_uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("ComfortBase is disconnected")
        for service in client.services:
            if service.uuid.lower() == service_uuid:
                char = service.get_characteristic(char_uuid)
                if char is not None:
                    return char
        raise ConnectionError(f"ComfortBase requires {char_uuid} on service {service_uuid}")

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        char = self._role(WRITE_SERVICE, KEESON_BASE_WRITE_CHAR_UUID)
        # Runtime properties determine the available HA transport mode. The APK
        # does not embed Android's platform-populated writeType numeric value.
        await self._write_gatt_with_retry(
            KEESON_BASE_WRITE_CHAR_UUID, command, repeat_count, repeat_delay_ms,
            cancel_event=cancel_event, characteristic=char,
            response="write" in char.properties, wall_clock_pacing=True,
        )

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._role(WRITE_SERVICE, KEESON_BASE_WRITE_CHAR_UUID)
        char = self._role(NOTIFY_SERVICE, KEESON_BASE_NOTIFY_CHAR_UUID)
        if char is self._notify_char:
            return
        await self.stop_notify()
        if self.client is not None:
            await self.client.start_notify(char, self._notification)
            self._notify_char = char

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(KEESON_BASE_NOTIFY_CHAR_UUID, bytes(data))
        frame = self._assembler.feed(bytes(data))
        if frame is not None and self.product.massage_light:
            self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(codec.comfortbase_timer(frame)))

    async def stop_notify(self) -> None:
        char, self._notify_char = self._notify_char, None
        self._assembler = codec.ComfortBaseAssembler()
        if char is not None and self.client is not None and self.client.is_connected:
            await self.client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._notify_char = None
        self._assembler = codec.ComfortBaseAssembler()
        self._motor_state.clear()
        self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(None))

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    def _get_move_command(self) -> int:
        return next(
            ((app.AXES[axis][1] if direction else app.AXES[axis][2])
             for axis, direction in self._motor_state.items() if direction is not None), 0,
        )

    async def _move_motor(self, motor: str, direction: bool | None) -> None:
        if motor not in self.product.axes:
            raise NotImplementedError(f"{self.product.name} has no {motor} control")
        await super()._move_motor(motor, direction)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis, translation_key=app.AXES[axis][0],
                open_fn=_axis(axis, True), close_fn=_axis(axis, False),
                stop_fn=lambda c: c.stop_all(), scheduler_resource="*",
            ) for axis in self.product.axes
        )

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def has_tilt_support(self) -> bool:
        return "tilt" in self.product.axes

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("Memory A", "Memory B")

    async def _save(self, word: int) -> None:
        # Bound the save gesture itself, with no delayed callback that could
        # stop a later command. Cleanup completes before the command lock leaves.
        budget = asyncio.timeout(app.SAVE_SECONDS)
        try:
            async with budget:
                await self.write_command(self._build_command(word), 1_000_000, app.REFRESH_MS)
        except TimeoutError:
            if not budget.expired():
                raise
        finally:
            await self._release_motion(delay=False)

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in app.MEMORY:
            raise ValueError("ComfortBase has Memory A (1) and B (2)")
        await self._save(app.MEMORY[memory_num])

    async def save_preset(self, preset: Preset) -> None:
        if preset not in app.PRESETS:
            raise ValueError("Unknown ComfortBase preset")
        await self._save(app.PRESETS[preset])

    @property
    def supports_lights(self) -> bool:
        return self.product.massage_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise NotImplementedError("Freestyle has no light control")
        await self._write_single_shot(self._build_command(app.LIGHT_TOGGLE))

    async def lights_on(self) -> None:
        raise NotImplementedError("ComfortBase only exposes a light toggle")

    async def lights_off(self) -> None:
        raise NotImplementedError("ComfortBase only exposes a light toggle")

    @property
    def supports_massage(self) -> bool:
        return self.product.massage_light

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self.supports_massage:
            return ()
        return (ControllerStateSensorSpec(
            key="massage_timer", translation_key="massage_timer",
            state_key=MASSAGE_TIMER_MINUTES, icon="mdi:timer-outline",
            native_unit_of_measurement="min", card=CARD_MASSAGE_TIMER,
        ),)

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_wave_direction_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    async def _massage(self, action: str) -> None:
        if not self.supports_massage:
            raise NotImplementedError("Freestyle has no massage controls")
        await self._write_single_shot(self._build_command(app.MASSAGE[action]))

    async def massage_mode_step(self) -> None:
        await self._massage("timer")

    async def massage_intensity_up(self) -> None:
        await self._massage("intensity_up")

    async def massage_intensity_down(self) -> None:
        await self._massage("intensity_down")

    async def massage_wave_next(self) -> None:
        await self._massage("wave_next")

    async def massage_wave_previous(self) -> None:
        await self._massage("wave_previous")

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        # AlarmFragment reads local wall time separately for each write.
        for _ in range(2):
            await self.write_command(codec.clock(dt_util.now()))

    def validate_alarm(self, *, enabled: bool, hour: int, minute: int, memory: int) -> None:
        if not 0 <= hour <= 23 or not 0 <= minute <= 59 or memory not in app.MEMORY:
            raise ValueError("Choose a valid alarm time and Memory A (1) or B (2)")

    async def set_alarm(self, *, enabled: bool, hour: int, minute: int, memory: int) -> None:
        self.validate_alarm(enabled=enabled, hour=hour, minute=minute, memory=memory)
        if enabled:
            await self.sync_clock()
            await asyncio.sleep(app.ALARM_DELAY_SECONDS)
            # parameter3 is opaque. The app writes FF, no weekday semantics proven.
            fields = bytes((hour, minute, 0xFF, 0x0E if memory == 1 else 0x0F))
        else:
            fields = bytes(4)
        await self.write_command(codec.alarm_table(3, fields))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                key=f"comfortbase_save_{preset}", name=f"Save {preset.replace('_', ' ')}",
                press_fn=_save_button(preset), translation_key=f"comfortbase_save_{preset}",
                icon="mdi:content-save", card=CARD_PRESETS,
            ) for preset in app.PRESETS
        )


def _save_button(preset: Preset) -> MotorCommandCallable:
    async def save(controller: BedController) -> None:
        await cast(ComfortBaseController, controller).save_preset(preset)

    return save


async def build_controller(ctx: BuildContext) -> ComfortBaseController:
    return ComfortBaseController(ctx.coordinator, product=ctx.variant or "")
