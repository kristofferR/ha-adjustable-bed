"""The two apps' separate local sensing/intervention receiver policies."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS

from ...controller_state import StateKey
from ...profiles.richmat_mh_apps import APPS
from ..entity_specs import ControllerStateSensorSpec
from ..ruf_richmat.protocol import crc8, sleep_frame
from ..ruf_richmat.sleep import CHARACTERISTIC, RufRichmatSleepController

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

_STD_KEYS: Final = {
    side: StateKey[int](f"richmat_mh_sleep_{side}_state")
    for side in ("left", "right")
}


class RichmatMHAppSleepController(RufRichmatSleepController):
    """Reuse the family commands and entities with explicit app/session ownership."""

    app_labels = {app: profile.label for app, profile in APPS.items()}

    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str) -> None:
        super().__init__(coordinator, app=app)
        self._owner: BleakClient | None = None
        self._generation = 0
        self._next_write = 0.0

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        # MAC/CV/NV belong to excluded network/OTA metadata. Retain only local
        # bed settings, rates, occupancy, movement and the raw Std state.
        specs = tuple(spec for spec in super().controller_state_sensor_specs if spec.key != "ruf_richmat_sleep_attributes")
        return specs + tuple(
            ControllerStateSensorSpec(
                key, str(key), key, "mdi:bed", entity_registry_enabled_default=False
            )
            for key in _STD_KEYS.values()
        )

    @property
    def requires_persistent_connection(self) -> bool:
        return True

    def validate_direct_user_mode(self, option: str) -> None:
        if self.app != "nisco" or option not in ("single", "double"):
            raise ValueError("The direct user-mode caller is established only for Nisco")

    async def direct_user_mode(self, option: str) -> None:
        self.validate_direct_user_mode(option)
        # ChooseUserModeActivity is distinct from the settings canOperate guard.
        await self.write_command(sleep_frame(0x14, bytes((1, 3, 1 if option == "single" else 2))))

    async def set_sleep_option(self, setting: str, option: str) -> None:
        if not isinstance(self._coordinator.entry.data.get(CONF_ADDRESS), str):
            raise ValueError("Select the physical sleep receiver before changing its settings")
        if self._owner is None or self.client is not self._owner or not self._owner.is_connected:
            raise ConnectionError("The selected sleep receiver is disconnected")
        await super().set_sleep_option(setting, option)

    async def async_discover_capabilities(self) -> None:
        await super().async_discover_capabilities()
        if self._char is None or "notify" not in self._char.properties:
            raise ValueError("The separate sleep receiver requires notifications")
        self._generation += 1
        self._owner = self.client

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        owner, characteristic = self._owner, self._char
        if characteristic is None or owner is None or self.client is not owner:
            raise ConnectionError("The sleep receiver's BLE session changed")
        generation = self._generation
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            gap = max(0, self._next_write - asyncio.get_running_loop().time())
            try:
                await asyncio.wait_for(cancel.wait(), gap)
            except TimeoutError:
                pass
            if cancel.is_set():
                return

            def validate() -> None:
                if self.client is not self._owner or generation != self._generation:
                    raise ConnectionError("A queued sleep write lost its physical receiver")
                self._next_write = asyncio.get_running_loop().time() + 0.3

            async def send() -> None:
                for offset in range(0, len(command), 20):
                    await self._write_gatt_with_retry(
                        characteristic.uuid, command[offset:offset + 20],
                        cancel_event=cancel_event, response=True,
                        characteristic=characteristic, expected_client=owner,
                        before_write=validate,
                    )

            task = asyncio.create_task(send())
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
                    cancel.set()
            task.result()
            if self.client is not self._owner or generation != self._generation:
                raise ConnectionError("A completed sleep write belongs to the previous session")
            if cancelled:
                raise asyncio.CancelledError
            if index + 1 < repeat_count:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._char is None or self._owner is None:
            raise ConnectionError("The sleep notification characteristic is unresolved")
        self._generation += 1
        owner, generation = self._owner, self._generation
        previous = self._background_tasks()
        for task in previous:
            task.cancel()
        if previous:
            await asyncio.gather(*previous, return_exceptions=True)

        def receive(sender: object, data: bytearray) -> None:
            if self.client is owner and generation == self._generation:
                self._notify(sender, data)

        self._buffer.clear()
        self._attributes = None
        for attempt in range(APPS[self.app].sleep_notify_attempts):
            await asyncio.sleep(1)
            async with self._ble_lock:
                if self.client is not owner or generation != self._generation:
                    raise ConnectionError("Sleep notification setup lost its physical receiver")
                try:
                    await owner.start_notify(self._char, receive)
                except BleakError:
                    if attempt + 1 == APPS[self.app].sleep_notify_attempts:
                        raise
                else:
                    break
        if self.client is not owner or generation != self._generation:
            raise ConnectionError("Sleep notification setup completed on an abandoned session")
        self._heartbeat = asyncio.create_task(self._heartbeat_loop())

    def _background_tasks(self) -> tuple[asyncio.Task[None], ...]:
        return (*((self._heartbeat,) if self._heartbeat else ()), *tuple(self._replies))

    async def _serialized_write(self, frame: bytes) -> None:
        owner, generation = self._owner, self._generation

        async def send(_controller: object) -> None:
            if owner is None or self.client is not owner or generation != self._generation:
                raise ConnectionError("The queued sleep reply belongs to a previous session")
            await self.write_command(frame)

        await self._coordinator.async_execute_controller_command(send, cancel_running=False)

    async def stop_notify(self) -> None:
        owner, characteristic = self._owner, self._char
        pending = self._background_tasks()
        self._notify_callback = None
        self.on_disconnect()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if owner is not None and characteristic is not None:
            async with self._ble_lock:
                if self.client is owner and owner.is_connected:
                    await owner.stop_notify(characteristic)

    def _notify(self, _sender: object, data: bytearray) -> None:
        self.forward_raw_notification(CHARACTERISTIC, bytes(data))
        if data and data[0] == 0xFA:
            self._buffer.clear()
            if len(data) < 4:
                return  # Explicit HA malformed-header fence.
        self._buffer.extend(data)
        if len(self._buffer) < 4:
            return
        length = self._buffer[1]
        if length >= 128 or len(self._buffer) > 1024:
            self._buffer.clear()  # HA fence for the Android signed-length limitation.
            return
        if length > 18 and len(self._buffer) < length + 2:
            return
        frame = bytes(self._buffer)
        self._buffer.clear()
        # CRC covers the accumulated remainder. No invented coalesced splitter
        # or universal declared-length validation is attributed to the apps.
        if crc8(frame[3:]) == frame[2]:
            self._apply_frame(frame)

    def _apply_frame(self, frame: bytes) -> None:
        if frame[3] in (0x11, 0x12):
            try:
                obj = json.loads(frame[4:].decode("utf-8"))
            except ValueError, UnicodeError:
                return
            if not isinstance(obj, dict):
                return
            if frame[3] == 0x12:
                # The shared consumer handles the ACK and local bed fields only.
                obj = {key: obj[key] for key in ("SDMode", "SDModeSet", "LI", "RI") if key in obj}
            else:
                saved = self._coordinator.entry.data.get(CONF_ADDRESS)
                if self.app == "mlily_supreme" and not isinstance(saved, str):
                    return  # HA's saved physical receiver maps DEVICE_MAC's guard.
                for side, source in (("left", "Left"), ("right", "Right")):
                    row = obj.get(source)
                    if isinstance(row, dict):
                        value = row.get("Std", 1 if self.app == "mlily_supreme" else None)
                        if type(value) is int:
                            self.forward_controller_state_update(_STD_KEYS[side], value)
            frame = sleep_frame(frame[3], json.dumps(obj, separators=(",", ":")).encode())
        super()._apply_frame(frame)

    def on_disconnect(self) -> None:
        self._generation += 1
        self._owner = None
        self._next_write = 0.0
        super().on_disconnect()
