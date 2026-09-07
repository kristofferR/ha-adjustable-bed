"""Explicit app-profile controls from the frozen com.richmat.lp 2.2.1 report.

The app's control labels do not establish a common physical motor layout. Keep
its per-control packet mode and event states instead of assigning generic axes.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ..lp_legacy_profiles import LpLegacyAction, LpLegacyControl, get_lp_legacy_profile
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_TICK_SECONDS = 0.1
_LONG_PRESS_TICKS = 31
_NOTIFICATION_EFFECTS = {
    bytes.fromhex("6E 09 01 00 78"): "app_status_5",
    bytes.fromhex("6E 07 01 01 77"): "alarm_routine_1",
    bytes.fromhex("6E 07 01 02 78"): "alarm_routine_2",
}


def _button_callback(control_id: str, gesture: str) -> MotorCommandCallable:
    """Bind the action identity while resolving the current controller at call time."""

    async def press(controller: BedController) -> None:
        if not isinstance(controller, LeggettLpLegacyController):
            raise TypeError("LP legacy button requires its profile controller")
        await controller.execute_control(control_id, gesture)

    return press


class LeggettLpLegacyController(BedController):
    """Execute a user-selected app form against explicitly selected GATT endpoints."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        model: str,
        write_uuid: str,
        mode: str = "legacy",
        read_uuid: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        if mode not in ("legacy", "framed"):
            raise ValueError("LP legacy mode must be legacy or framed")
        self._profile = get_lp_legacy_profile(model)
        self._mode = mode
        self._write_uuid = str(UUID(write_uuid))
        self._read_uuid = str(UUID(read_uuid)) if read_uuid else None
        self._subscribed = False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_uuid

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        # The coordinator cancels the active gesture and awaits its own release.
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return self._read_uuid is not None

    def _packet(self, action: LpLegacyAction) -> bytes | None:
        return action.legacy if self._mode == "legacy" else action.framed

    def _gestures(self, control: LpLegacyControl) -> tuple[str, ...]:
        if self._packet(control.press) is None:
            return ()
        release = control.release
        if release is not None and self._packet(release) is None:
            return ()
        if control.press.state == 3:
            return ("press", "long_press") if release and release.state == 4 else ("long_press",)
        return ("press",)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        labels = Counter(control.label for control in self._profile.controls)
        specs = []
        for control in self._profile.controls:
            label = control.label
            if labels[label] > 1:
                label = f"{label} ({control.key})"
            for gesture in self._gestures(control):
                suffix = " (long press)" if gesture == "long_press" else ""
                specs.append(
                    ControllerButtonSpec(
                        key=f"lp_legacy_{self._profile.code.lower()}_{self._mode}_{control.key}_{gesture}",
                        name=f"{label}{suffix}",
                        press_fn=_button_callback(control.key, gesture),
                    )
                )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key="lp_legacy_notification",
                translation_key="lp_legacy_notification",
                state_key="lp_legacy_notification",
                icon="mdi:bluetooth",
                attribute_keys=("lp_legacy_notification_effect",),
                entity_registry_enabled_default=False,
            ),
        )

    def _characteristic(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        characteristic = client.services.get_characteristic(uuid)
        if characteristic is None:
            raise ValueError(f"Configured LP characteristic {uuid} is absent")
        return characteristic

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if not command:
            return
        characteristic = self._characteristic(self._write_uuid)
        properties = characteristic.properties
        if "write" not in properties and "write-without-response" not in properties:
            raise ValueError("Configured LP control characteristic is not writable")
        await self._write_gatt_with_retry(
            self._write_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response="write" in properties,
        )

    async def _wait_ticks(self, ticks: int) -> bool:
        """Return whether the requested app time elapsed without cancellation."""
        cancel = self._coordinator.cancel_command
        try:
            async with asyncio.timeout(ticks * _TICK_SECONDS):
                await cancel.wait()
        except TimeoutError:
            return True
        return False

    async def execute_control(self, control_id: str, gesture: str = "press") -> None:
        """Run one exact app gesture; callers must hold the coordinator command lock."""
        control = next((item for item in self._profile.controls if item.key == control_id), None)
        if control is None or gesture not in self._gestures(control):
            raise ValueError("Control gesture is not proven for this LP profile and packet mode")
        packet = self._packet(control.press)
        assert packet is not None
        release = control.release
        release_packet = self._packet(release) if release else None
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        ticks = 0
        completed = False
        try:
            if control.press.state == 1:
                for _ in range(self._coordinator.motor_pulse_count):
                    if cancel.is_set():
                        return
                    await self.write_command(packet)
                    ticks += 1
                    if not await self._wait_ticks(1):
                        return
                completed = True
            elif control.press.state == 3:
                if gesture == "long_press":
                    if not await self._wait_ticks(_LONG_PRESS_TICKS):
                        return
                    ticks = _LONG_PRESS_TICKS
                    await self.write_command(packet)
                completed = True
            elif control.press.state == 5:
                await self.write_command(packet)
                completed = await self._wait_ticks(1)
            else:
                raise ValueError("Unsupported LP press state")
        finally:
            if release is not None and release_packet is not None:
                if release.state == 2:
                    # Releases must survive the event/task cancellation that ended a hold.
                    await self.write_command(release_packet, cancel_event=asyncio.Event())
                elif release.state == 4 and completed and ticks <= 30 and not cancel.is_set():
                    await self.write_command(release_packet)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._read_uuid is None:
            return
        characteristic = self._characteristic(self._read_uuid)
        client = self.client
        assert client is not None
        if "notify" in characteristic.properties or "indicate" in characteristic.properties:
            await client.start_notify(self._read_uuid, self._notification_handler)
            self._subscribed = True
        elif "read" in characteristic.properties:
            self._notification_handler(characteristic, await client.read_gatt_char(self._read_uuid))
        else:
            raise ValueError("Configured LP read characteristic is neither readable nor notifiable")

    def _notification_handler(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        frame = bytes(data)
        self.forward_raw_notification(sender.uuid, frame)
        effect = _NOTIFICATION_EFFECTS.get(frame)
        if effect is not None:
            self.forward_controller_state_updates(
                {
                    "lp_legacy_notification": frame.hex(" ").upper(),
                    "lp_legacy_notification_effect": effect,
                }
            )

    async def stop_notify(self) -> None:
        client = self.client
        if self._subscribed and self._read_uuid and client and client.is_connected:
            await client.stop_notify(self._read_uuid)
        self._subscribed = False
        self._notify_callback = None

    async def move_head_up(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_head_down(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_head_stop(self) -> None:
        raise NotImplementedError("LP releases belong to individual app controls")

    async def move_back_up(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_back_down(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_back_stop(self) -> None:
        raise NotImplementedError("LP releases belong to individual app controls")

    async def move_legs_up(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_legs_down(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_legs_stop(self) -> None:
        raise NotImplementedError("LP releases belong to individual app controls")

    async def move_feet_up(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def move_feet_stop(self) -> None:
        raise NotImplementedError("LP releases belong to individual app controls")

    async def stop_all(self) -> None:
        """Finish coordinator cancellation without inventing a global STOP packet.

        The command lock is acquired after the active gesture has sent its own
        cleanup. This cannot stop movement initiated by another controller.
        """

    async def preset_flat(self) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the selected LP app control")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the selected LP app control")
