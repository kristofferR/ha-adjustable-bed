"""OKIN Motion Bed 1.0 (2): the fixed app grid over the gateway codec.

The middle column has lumbar icons but head-named constants. Its mechanics
and the bed light's polarity are unverified, so controls retain neutral labels.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..card import CARD_HIDDEN, CARD_LIGHTING, CARD_PRESETS
from ..codec import okin_nframe as codec
from ..const import KEESON_BASE_NOTIFY_CHAR_UUID, KEESON_BASE_WRITE_CHAR_UUID
from ..profiles.okin_nframe import OKIN_MOTIONBED, OkinNFrameProfile
from .base import CONTROLLER_GESTURE_RELEASE, ProfileExecution
from .entity_specs import ControllerButtonSpec, ControllerMotorHoldSpec, MotorControlSpec
from .lifecycle import ControllerSession
from .okin_nframe import OkinNFrameController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def _service_order(uuid: str) -> tuple[int, int]:
    """Android UUID.compareTo orders two signed longs, not UUID text."""
    value = UUID(uuid).int
    high, low = value >> 64, value & ((1 << 64) - 1)
    return (
        high - (1 << 64) if high & (1 << 63) else high,
        low - (1 << 64) if low & (1 << 63) else low,
    )


async def _pause(cancel: asyncio.Event, seconds: float) -> bool:
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


class OkinMotionBedController(ProfileExecution[OkinNFrameProfile], OkinNFrameController):
    """One explicit app choice; no advertisement identifies this protocol."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = OKIN_MOTIONBED
        self._session_client: BleakClient | None = None
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._subscribed = False
        self._write_with_response = True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        """No Device Information reads are part of this app's startup."""
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        return KEESON_BASE_WRITE_CHAR_UUID

    def _build_command(self, command_value: int) -> bytes:
        return codec.gateway_frame(command_value)

    def _resolve(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        if self._session_client is client and self._write_char is not None:
            return
        self.on_disconnect()
        write = notify = None
        for service in sorted(client.services, key=lambda s: _service_order(s.uuid)):
            for char in service.characteristics:
                if char.uuid.lower() == self.control_characteristic_uuid:
                    write = char
                elif char.uuid.lower() == KEESON_BASE_NOTIFY_CHAR_UUID:
                    notify = char
        # The app's SDK requires PROPERTY_WRITE; shared UUIDs alone grant no route.
        if write is None or "write" not in write.properties:
            raise ConnectionError("OKIN Motion Bed requires a writable FFE9 characteristic")
        self._write_char, self._notify_char = write, notify
        self._session_client = client

    @property
    def write_characteristic(self) -> BleakGATTCharacteristic:
        self._resolve()
        assert self._write_char is not None
        return self._write_char

    async def async_discover_capabilities(self) -> None:
        # Clear even when the same client wrapper is reused for a new GATT session.
        self.on_disconnect()
        self._resolve()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._resolve()
        client, char = self._session_client, self._notify_char
        if client is None or char is None or "notify" not in char.properties or self._subscribed:
            return

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self.client is client
                and self._session_client is client
                and self._notify_char is char
            ):
                # E2FE16 is only forwarded to an unconsumed Android event. Keep
                # diagnostic bytes; do not invent position, alarm or light state.
                self.forward_raw_notification(char.uuid, bytes(data))

        try:
            await client.start_notify(char, received)
        except BleakError, TimeoutError:
            # Subscription success is not an app command-readiness barrier.
            _LOGGER.debug("OKIN Motion Bed notification subscription failed", exc_info=True)
        else:
            if self._session_client is client and self._notify_char is char:
                self._subscribed = True

    async def stop_notify(self) -> None:
        client, char, subscribed = self._session_client, self._notify_char, self._subscribed
        self.on_disconnect()
        if client is not None and client.is_connected and char is not None and subscribed:
            await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._session_client = None
        self._write_char = self._notify_char = None
        self._subscribed = False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key="motionbed_middle" if axis == "middle" else axis,
                open_fn=lambda ctrl, a=axis: cast(OkinMotionBedController, ctrl)._move(a, True),
                close_fn=lambda ctrl, a=axis: cast(OkinMotionBedController, ctrl)._move(a, False),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                    release_button_key="motionbed_release",
                ),
            )
            for axis in self.profile.axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}" for axis in self.profile.axes for direction in ("up", "down")
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported OKIN Motion Bed control: {control}")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 100 <= duration_ms <= 60000
        ):
            raise ValueError("Hold duration must be 100..60000 milliseconds")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        duration_ms = self.leased_hold_ms(duration_ms)
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        self._resolve()
        client = self._session_client
        interval = self.profile.hold.repeat_ms
        assert interval is not None
        remaining = duration_ms
        try:
            while remaining > 0 and not cancel.is_set() and self.client is client:
                await self.write_command(
                    self._build_command(self.profile.keys[control]), cancel_event=cancel
                )
                wait_ms = min(remaining, interval)
                if await _pause(cancel, wait_ms / 1000):
                    break
                remaining -= wait_ms
        finally:
            # Never retarget an old gesture's release to a replacement session.
            if self.client is client and self._session_client is client:
                await self._send_stop()

    async def _move(self, axis: str, up: bool) -> None:
        interval = self.profile.hold.repeat_ms
        assert interval is not None
        await self.hold_control(
            f"{axis}_{'up' if up else 'down'}", self._coordinator.motor_pulse_count * interval
        )

    async def move_head_up(self) -> None:
        raise NotImplementedError("The middle column's physical head mapping is unverified")

    async def move_head_down(self) -> None:
        raise NotImplementedError("The middle column's physical head mapping is unverified")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            # The held task's finally owns the manual UP/CANCEL release.
            return
        # Manual release and preset STOP are different commands. A global STOP
        # covers either without guessing which movement the hardware is running.
        try:
            await self._send_stop()
        finally:
            await self.stop_preset()

    async def stop_preset(self) -> None:
        await self.write_command(
            self._build_command(self.profile.keys["preset_stop"]), cancel_event=asyncio.Event()
        )

    async def _action(self, key: str) -> None:
        await self.write_command(self._build_command(self.profile.keys[key]))

    async def preset_flat(self) -> None:
        await self._action("flat")

    async def preset_zero_g(self) -> None:
        await self._action("zero_g")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._action(f"save_memory_{memory_num}")

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                key="motionbed_preset_stop",
                name="Stop preset",
                translation_key="motionbed_preset_stop",
                press_fn=lambda ctrl: cast(OkinMotionBedController, ctrl).stop_preset(),
                icon="mdi:stop",
                scheduler_resource="*",
                card=CARD_PRESETS,
            ),
            *(
                ControllerButtonSpec(
                    key=f"motionbed_light_parameter_{parameter}",
                    name=f"Bed light parameter {parameter}",
                    translation_key=f"motionbed_light_parameter_{parameter}",
                    press_fn=lambda ctrl, p=parameter: cast(OkinMotionBedController, ctrl)._action(
                        f"light_parameter_{p}"
                    ),
                    icon="mdi:lightbulb-outline",
                    scheduler_resource="*",
                    card=CARD_LIGHTING,
                )
                for parameter in (0, 1)
            ),
            ControllerButtonSpec(
                key="motionbed_release",
                name="Release held control",
                translation_key="motionbed_release",
                press_fn=lambda ctrl: ctrl.stop_all(),
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )
