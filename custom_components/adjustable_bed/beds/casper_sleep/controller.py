"""Separate MM/SXB direct BLE sensors shipped by Casper Base 1.0.8."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ..casper_base_protocol import CasperBaseActions, Request, SensorKind
from ..casper_sleep_protocol import (
    NOTIFY,
    SERVICES,
    WRITE,
    Json,
    Live,
    Receive,
    command,
    decode_bean,
    mapping,
    wire_command,
)
from ..controller_state import StateKey, StateUpdate
from .base import BedController, ControllerStateSensorSpec

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


STATUS: Final = StateKey[str]("casper_sleep_status")
INFO: Final = StateKey[dict[str, Json]]("casper_sleep_info")
REPORT: Final = StateKey[Json]("casper_sleep_report")
PART: Final = StateKey[Json]("casper_sleep_part")
ERROR: Final = StateKey[str]("casper_sleep_error")
REMOTE_STATUS: Final = StateKey[str]("casper_remote_status")


def live_key(side: str, field: str) -> StateKey[object]:
    """One side's live sensor field."""
    return StateKey[object](f"casper_sleep_{side}_{field}")


class CasperSleepController(BedController, CasperBaseActions):
    """Own parser, command and timer state for one physical sensor."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, kind: SensorKind) -> None:
        super().__init__(coordinator)
        self.kind: SensorKind = kind
        self._write_char: BleakGATTCharacteristic | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._receive = Receive(kind)
        self._live = Live(kind)
        self._sequence = 1
        self._pending: asyncio.Future[Json] | None = None
        self._report_request: Request | None = None
        self._info: dict[str, Json] = {}
        self._poll: asyncio.Task[None] | None = None
        self._generation = 0

    @property
    def control_characteristic_uuid(self) -> str:
        return self._write_char.uuid if self._write_char else WRITE

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return False

    @property
    def supports_casper_base_controls(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return super().requires_persistent_connection or self._poll is not None

    @property
    def motor_control_specs(self) -> tuple:
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                "casper_sleep",
                "casper_sleep",
                STATUS,
                "mdi:sleep",
                attribute_keys=(
                    INFO,
                    REPORT,
                    PART,
                    ERROR,
                ),
            )
        ]
        for side in ("L", "R"):
            for field in ("on_bed", "heart", "breath", "body_move", "snoring"):
                specs.append(
                    ControllerStateSensorSpec(
                        f"casper_sleep_{side}_{field}",
                        f"casper_sleep_{side.lower()}_{field}",
                        live_key(side, field),
                        "mdi:sleep",
                        attribute_keys=(live_key(side, "valid"),),
                    )
                )
        return tuple(specs)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self.client is None:
            raise ConnectionError("Not connected")
        for service in self.client.services:
            if service.uuid.lower() not in SERVICES:
                continue
            write = notify = None
            for char in service.characteristics:
                if self.kind == "sxb":
                    if char.uuid.lower() == WRITE and "write" in char.properties:
                        write = char
                    elif char.uuid.lower() == NOTIFY and "notify" in char.properties:
                        notify = char
                else:
                    if "write-without-response" in char.properties:
                        write = char
                    elif "notify" in char.properties:
                        notify = char
            if write is not None and notify is not None:
                self._write_char, self._notify_char = write, notify
                break
        if self._write_char is None or self._notify_char is None:
            raise ValueError("Sensor requires a supported service with write and notify")
        await self.client.start_notify(self._notify_char, self._on_notification)
        await self._send("s_time", Request("sensor_time"))
        self.forward_controller_state_update(STATUS, "connected")

    async def stop_notify(self) -> None:
        if self.client and self.client.is_connected and self._notify_char:
            await self.client.stop_notify(self._notify_char)
        self.on_disconnect()

    def on_disconnect(self) -> None:
        self._generation += 1
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._receive.reset(None)
        self._write_char = self._notify_char = None

    async def _send(self, action: str, request: Request) -> None:
        if self.client is None or self._write_char is None:
            raise ConnectionError("Sensor disconnected")
        if self._sequence >= 255:
            self._sequence = 1
        now = dt_util.now()
        offset = now.utcoffset()
        zone = (
            str(now.tzinfo)
            if self.kind == "mm"
            else int((offset.total_seconds() if offset else 0) / 3600)
        )
        packet = command(
            self.kind, action, self._sequence, request, ts=int(now.timestamp()), zone=zone
        )
        self._sequence += 1
        self._receive.reset(action)
        await asyncio.sleep(0.1)
        mtu = self.client.mtu_size - 3
        if mtu < 1:
            raise ValueError("Invalid negotiated MTU")
        for index in range(0, len(packet), mtu):
            await self._write_gatt_with_retry(
                self.control_characteristic_uuid,
                packet[index : index + mtu],
                characteristic=self._write_char,
                response=self.kind == "sxb",
            )

    async def _query(self, action: str, request: Request) -> Json:
        self._pending = asyncio.get_running_loop().create_future()
        try:
            await self._send(action, request)
            # HA request bound, not an invented firmware protocol interval.
            async with asyncio.timeout(5):
                return await self._pending
        finally:
            self._pending = None

    def _on_notification(self, _sender: BleakGATTCharacteristic, raw: bytearray) -> None:
        self.forward_raw_notification(
            self._notify_char.uuid if self._notify_char else "", bytes(raw)
        )
        try:
            data = self._receive.feed(bytes(raw))
            if data is None:
                return
            action = self._receive.action
            reply_cmd = data.get("cmd") if isinstance(data, dict) else None
            if (
                action is not None
                and action != "q_report_allow"
                and isinstance(reply_cmd, str)
                and reply_cmd != wire_command(self.kind, action)
            ):
                # A late reply to an earlier request, such as the connect-time
                # s_time, must not be decoded as or complete the current query.
                _LOGGER.debug("Ignoring %s reply while awaiting %s", reply_cmd, action)
                return
            self._consume(data)
            if self._pending is not None and not self._pending.done():
                self._pending.set_result(data)
        except (ValueError, IndexError, OverflowError) as err:
            self.forward_controller_state_update(ERROR, str(err))
            self._publish_live()
            if self._pending is not None and not self._pending.done():
                self._pending.set_exception(err)

    def _consume(self, data: Json) -> None:
        action = self._receive.action
        if action == "q_report_allow":
            r = self._report_request
            if r is None:
                return
            if r.report_type == 2:
                if not isinstance(data, list):
                    raise ValueError("Expected monthly report list")
                report: Json = [decode_bean(self.kind + "_month", item) for item in data]
            else:
                report = decode_bean(self.kind + "_day", data)
            key = (
                f"{r.year:04}-{r.month:02}"
                + (f"-{r.day:02}" if r.report_type == 1 else "")
                + f"-{r.part}"
            )
            self.forward_controller_state_update(
                REPORT, {"key": key, "data": report}
            )
            return
        names = {
            "s_time": "time",
            "s_init": "init",
            "q_part": "part",
            "s_part": "part",
            "q_realtime": "live",
            "q_report": "report",
        }
        if action not in names:
            return
        bean = decode_bean(self.kind + "_" + names[action], data)
        val = bean.get("val")
        if action in ("s_time", "s_init"):
            info = mapping(val)
            # Error is retained; the app's information merge has no error gate.
            self._info["error"] = info.get("error")
            for key in ("type", "ver"):
                if info.get(key) is not None:
                    self._info[key] = info[key]
            self.forward_controller_state_update(INFO, dict(self._info))
        elif action in ("q_part", "s_part"):
            self.forward_controller_state_update(PART, val)
        elif action == "q_realtime" and val is not None:
            self._live.feed(val)
            self._publish_live()
        elif action == "q_report":
            size = mapping(val).get("fsize")
            if size is not None and type(size) is not int:
                raise ValueError("Invalid report size")
            self._receive.report_size = size if isinstance(size, int) else 0

    def _publish_live(self) -> None:
        updates: list[StateUpdate] = []
        for side, state in self._live.state.items():
            updates += [live_key(side, key)(value) for key, value in state.items()]
            updates.append(live_key(side, "valid")(self._live.valid[side]))
        self.forward_controller_state_updates(*updates)

    def validate_casper_base_request(self, request: Request) -> None:
        r = request
        if r.operation not in (
            "sensor_time",
            "sensor_info",
            "sensor_part",
            "sensor_query_part",
            "sensor_live",
            "sensor_report",
            "sensor_stop",
        ):
            raise ValueError("Choose a sensor operation")
        if r.operation == "sensor_info" and self.kind != "sxb":
            raise ValueError("s_init requires SXB")
        if r.operation in ("sensor_part", "sensor_report") and r.part not in (
            (1, 2) if self.kind == "mm" else (11, 12, 13)
        ):
            raise ValueError("Unsupported sensor partition")

    async def async_execute_casper_base_request(self, request: Request) -> None:
        r = request
        self.validate_casper_base_request(r)
        if r.operation == "sensor_stop":
            self._generation += 1
            if self._poll:
                self._poll.cancel()
                self._poll = None
            self._receive.reset(None)
        elif r.operation == "sensor_live":
            if r.enabled:
                if self._poll:
                    self._poll.cancel()
                self._poll = self._coordinator.hass.async_create_background_task(
                    self._poll_live(), "Casper sleep live"
                )
            else:
                await self.async_execute_casper_base_request(Request("sensor_stop"))
        elif r.operation == "sensor_report":
            self._report_request = r
            await self._query("q_report", r)
            if self._receive.report_size > 0:
                generation = self._generation
                await asyncio.sleep(1)
                if generation == self._generation:
                    await self._query("q_report_allow", r)
            else:
                self.forward_controller_state_update(REPORT, {})
        elif r.operation == "sensor_info":
            await self._query("s_time", r)
            await asyncio.sleep(0.1)
            await self._query("s_init", r)
        else:
            await self._query(
                {"sensor_time": "s_time", "sensor_part": "s_part", "sensor_query_part": "q_part"}[
                    r.operation
                ],
                r,
            )

    async def _poll_live(self) -> None:
        try:
            while True:
                await asyncio.sleep(2)
                await self._coordinator.async_execute_controller_command(
                    lambda _: self._query_live(), cancel_running=False, resource="configuration"
                )
        except asyncio.CancelledError:
            raise
        except ConnectionError, ValueError, TimeoutError:
            _LOGGER.debug("Casper sensor live polling stopped", exc_info=True)
        finally:
            if self._poll is asyncio.current_task():
                self._poll = None
                self._coordinator.resume_disconnect_timer()

    async def _query_live(self) -> None:
        await self._query("q_realtime", Request("sensor_live"))

    async def _no_movement(self, *_args: object) -> None:
        raise NotImplementedError("Sleep sensors have no motor control")

    move_head_up = _no_movement
    move_head_down = _no_movement
    move_head_stop = _no_movement
    move_back_up = _no_movement
    move_back_down = _no_movement
    move_back_stop = _no_movement
    move_legs_up = _no_movement
    move_legs_down = _no_movement
    move_legs_stop = _no_movement
    move_feet_up = _no_movement
    move_feet_down = _no_movement
    move_feet_stop = _no_movement
    preset_flat = _no_movement

    async def preset_memory(self, memory_num: int) -> None:
        await self._no_movement()

    async def program_memory(self, memory_num: int) -> None:
        await self._no_movement()

    async def stop_all(self) -> None:
        await self.async_execute_casper_base_request(Request("sensor_stop"))


class CasperRemoteController(CasperSleepController):
    """The app's RCRM locator only connects; no locator command is defined."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, kind="mm")

    @property
    def requires_notification_channel(self) -> bool:
        return False

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "casper_remote", "casper_remote", REMOTE_STATUS, "mdi:remote"
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.forward_controller_state_update(REMOTE_STATUS, "connected")

    def validate_casper_base_request(self, request: Request) -> None:
        if request.operation != "remote_find":
            raise ValueError("This entry is a remote, not a bed or sensor")

    async def async_execute_casper_base_request(self, request: Request) -> None:
        self.validate_casper_base_request(request)
        self.forward_controller_state_update(REMOTE_STATUS, "connected")
