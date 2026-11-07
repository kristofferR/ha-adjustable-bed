"""The separate direct BLE sleep/intervention receiver in four Richmat apps."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from ..ruf_richmat_protocol import crc8, sleep_frame
from .base import BedController, ControllerSelectSpec, ControllerStateSensorSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
SERVICE = "2320567c-05cf-6eb4-c341-772851827e1b"
CHARACTERISTIC = "26f66991-68ee-c2be-444d-b95c3f2dc38a"
APPS = {
    "wsilver2": "W.Silver Products",
    "americanstar": "AMERICANSTAR",
    "bailey2": "Bailey's Bed Control",
    "tx": "TX",
}


async def _select(controller: BedController, setting: str, option: str) -> None:
    from .base import SideBoundController

    if isinstance(controller, SideBoundController):
        controller = controller._controller
    if not isinstance(controller, RufRichmatSleepController):
        raise ValueError("This action requires the separate Richmat sleep receiver")
    await controller.set_sleep_option(setting, option)


class RufRichmatSleepController(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, app: str) -> None:
        super().__init__(coordinator)
        if app not in APPS:
            raise ValueError("Select the app that owns this sleep receiver")
        self.app = app
        self._char: BleakGATTCharacteristic | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._replies: set[asyncio.Task[None]] = set()
        self._buffer = bytearray()
        self._attributes: dict[str, object] | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return CHARACTERISTIC

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple:
        return ()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return tuple(
            ControllerSelectSpec(
                f"ruf_richmat_sleep_{setting}",
                f"ruf_richmat_sleep_{setting}",
                f"ruf_richmat_sleep_{setting}",
                ("single", "double") if setting == "mode" else ("off", "on"),
                lambda ctrl, option, s=setting: _select(ctrl, s, option),
            )
            for setting in ("mode", "left_intervention", "right_intervention")
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        rows = []
        for side in ("left", "right"):
            for kind, unit, icon in (
                ("heart_rate", "bpm", "mdi:heart-pulse"),
                ("breathing_rate", "breaths/min", "mdi:lungs"),
                ("occupancy", None, "mdi:bed"),
                ("movement", None, "mdi:motion-sensor"),
            ):
                key = f"ruf_richmat_sleep_{side}_{kind}"
                rows.append(
                    ControllerStateSensorSpec(key, key, key, icon, native_unit_of_measurement=unit)
                )
        return tuple(rows) + (
            ControllerStateSensorSpec(
                "ruf_richmat_sleep_attributes",
                "ruf_richmat_sleep_attributes",
                "ruf_richmat_sleep_firmware",
                "mdi:information-outline",
                attribute_keys=("ruf_richmat_sleep_attributes",),
            ),
        )

    async def async_discover_capabilities(self) -> None:
        if self.client is None:
            raise ConnectionError("Sleep receiver is disconnected")
        service = self.client.services.get_service(SERVICE)
        char = service.get_characteristic(CHARACTERISTIC) if service else None
        if (
            char is None
            or not ({"write", "write-without-response"} & set(char.properties))
            or not ({"notify", "indicate"} & set(char.properties))
        ):
            raise ValueError(
                "The separate sleep receiver needs its fixed write/notify characteristic"
            )
        self._char = char

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if self._char is None:
            raise ConnectionError("Sleep receiver write role is unresolved")
        for offset in range(0, len(command), 20):
            await self._write_gatt_with_retry(
                self._char.uuid,
                command[offset : offset + 20],
                repeat_count=1,
                cancel_event=cancel_event,
                response="write-without-response" not in self._char.properties,
                characteristic=self._char,
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self.client is None or self._char is None:
            return
        self._attributes = None
        self._buffer.clear()
        await asyncio.sleep(1)
        async with self._ble_lock:
            await self.client.start_notify(self._char, self._notify)
        self._heartbeat = asyncio.create_task(self._heartbeat_loop())

    async def _serialized_write(self, frame: bytes) -> None:
        await self._coordinator.async_execute_controller_command(
            lambda _ctrl: self.write_command(frame),
            cancel_running=False,
        )

    async def _heartbeat_loop(self) -> None:
        try:
            while self.client is not None and self.client.is_connected:
                await self._serialized_write(sleep_frame(1))
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.debug("Sleep receiver heartbeat stopped", exc_info=True)

    def _queue_reply(self, frame: bytes) -> None:
        async def send() -> None:
            try:
                await self._serialized_write(frame)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("Sleep receiver reply failed", exc_info=True)

        task = asyncio.create_task(send())
        self._replies.add(task)
        task.add_done_callback(self._replies.discard)

    def _notify(self, _sender: object, data: bytearray) -> None:
        self.forward_raw_notification(CHARACTERISTIC, bytes(data))
        if data and data[0] == 0xFA:
            self._buffer.clear()
        self._buffer.extend(data)
        if len(self._buffer) < 4:
            return
        size = self._buffer[1] + 2
        if len(self._buffer) < size:
            return
        frame = bytes(self._buffer)
        self._buffer.clear()
        if len(frame) != size or crc8(frame[3:]) != frame[2]:
            return
        self._apply_frame(frame)

    def _apply_frame(self, frame: bytes) -> None:
        kind, payload = frame[3], frame[4:]
        if kind == 5:
            text = f"{int(datetime.now().timestamp()):x}"
            if len(text) % 2 == 0:
                self._queue_reply(sleep_frame(5, bytes.fromhex(text)[::-1]))
        elif kind in (0x11, 0x12):
            if kind == 0x12:
                self._queue_reply(sleep_frame(0xA5, b"\x12"))
            try:
                obj = json.loads(payload.decode("utf-8").strip())
            except ValueError, UnicodeError:
                return
            if not isinstance(obj, dict):
                return
            if kind == 0x12:
                self._attributes = {
                    key: obj[key]
                    for key in ("MAC", "CV", "NV", "SDMode", "SDModeSet", "LI", "RI")
                    if key in obj
                }
                self.forward_controller_state_updates(
                    {
                        "ruf_richmat_sleep_attributes": self._attributes,
                        "ruf_richmat_sleep_firmware": obj.get("CV"),
                        "ruf_richmat_sleep_mode": "double"
                        if obj.get("SDModeSet", -1) == 2
                        else "single",
                        "ruf_richmat_sleep_left_intervention": "on" if obj.get("LI", -1) == 1 else "off",
                        "ruf_richmat_sleep_right_intervention": "on"
                        if obj.get("RI", -1) == 1
                        else "off",
                    }
                )
            else:
                values: dict[str, object] = {}
                for side, source in (("left", "Left"), ("right", "Right")):
                    row = obj.get(source, {})
                    if not isinstance(row, dict):
                        continue
                    for name, raw in (
                        ("heart_rate", "HD"),
                        ("breathing_rate", "BD"),
                        ("occupancy", "IsOnBed"),
                        ("movement", "IsMove"),
                    ):
                        value = row.get(raw, 0)
                        if type(value) is not int or not -(2**31) <= value < 2**31:
                            continue
                        values[f"ruf_richmat_sleep_{side}_{name}"] = (
                            value if name.endswith("rate") else value == 1
                        )
                self.forward_controller_state_updates(values)
        elif kind == 0xA5 and len(frame) == 7 and payload[0] == 0x14:
            op, result = payload[1:]
            names = {1: "left_intervention", 2: "right_intervention", 3: "mode"}
            if name := names.get(op):
                option = (
                    ("double" if result == 2 else "single")
                    if op == 3
                    else ("on" if result == 1 else "off")
                )
                self.forward_controller_state_update(f"ruf_richmat_sleep_{name}", option)
        # Wi-Fi/provisioning and firmware administration responses have no product action.

    async def set_sleep_option(self, setting: str, option: str) -> None:
        if self._attributes is None:
            raise ValueError("Wait for this receiver's device attributes")
        if setting == "mode":
            if option not in ("single", "double"):
                raise ValueError("Choose single or double mode")
            if (
                self._attributes.get("SDMode", -1) == 1
                and self._coordinator.controller_state.get("ruf_richmat_sleep_mode") != "double"
            ):
                raise ValueError("This receiver declares a fixed single-user mode")
            op, value = 3, 1 if option == "single" else 2
        elif setting in ("left_intervention", "right_intervention") and option in ("off", "on"):
            op, value = (1 if setting == "left_intervention" else 2), int(option == "on")
        else:
            raise ValueError("Unknown sleep receiver option")
        await self.write_command(sleep_frame(0x14, bytes([1, op, value])))
        await asyncio.sleep(0.3)

    def on_disconnect(self) -> None:
        if self._heartbeat:
            self._heartbeat.cancel()
            self._heartbeat = None
        for task in self._replies:
            task.cancel()
        self._buffer.clear()
        self._attributes = None

    async def stop_notify(self) -> None:
        self.on_disconnect()
        if self.client and self.client.is_connected and self._char:
            async with self._ble_lock:
                await self.client.stop_notify(self._char)

    async def _unsupported(self, *_args: object) -> None:
        raise NotImplementedError("This separate sleep receiver has no motor or preset commands")

    move_head_up = move_head_down = move_head_stop = _unsupported
    move_back_up = move_back_down = move_back_stop = _unsupported
    move_legs_up = move_legs_down = move_legs_stop = _unsupported
    move_feet_up = move_feet_down = move_feet_stop = _unsupported
    stop_all = preset_flat = _unsupported

    async def preset_memory(self, memory_num: int) -> None:
        await self._unsupported()

    async def program_memory(self, memory_num: int) -> None:
        await self._unsupported()
