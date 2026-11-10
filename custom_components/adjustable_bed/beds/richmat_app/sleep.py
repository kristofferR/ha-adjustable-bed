"""Independent old/new MM and HJ control sessions from Richmat 4.2.0.

Physiology and report interpretation are outside scope. Envelope, fsize followup,
version metadata and polling cancellation remain part of the control session.
"""

from __future__ import annotations

import asyncio
import json
import math
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Final, cast

from homeassistant.util import dt as dt_util

from ...codec import richmat as richmat_codec
from ...codec import sleep_envelope
from ...controller_state import StateKey
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import ControllerStateSensorSpec
from .receive import Value
from .requests import Request

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

from .sleep_profiles import CHOICES

SERVICES = ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "2320567c-05cf-6eb4-c341-772851827e1b")
TX = "00000002-3c17-d293-8e48-14fe2e4da212"
RX = "00000003-3c17-d293-8e48-14fe2e4da212"
STATUS: Final = StateKey[str | None]("richmat_app_sleep_status")
STATE: Final = StateKey[dict[str, Value]]("richmat_app_sleep_state")
ORDER = (
    "s_time",
    "q_time",
    "q_part",
    "s_part",
    "q_realtime",
    "q_report",
    "s_init",
    "q_ota",
    "q_ota_ttl",
    "s_ota",
    "s_ota_crc",
    "q_sens",
    "s_sens",
    "q_antiSnore",
    "s_antiSnore",
)


def packet(sequence: int, command: str, value: object) -> bytes:
    if not 1 <= sequence <= 254:
        raise ValueError("Sleep sequence must be 1 through 254")
    payload = json.dumps(
        {"id": sequence, "cmd": command, "val": value},
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return sleep_envelope.frame(payload, sequence)


def _number(value: object, *, nullable: bool = False, integer: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError("Invalid sleep response number")
    return math.trunc(cast(int | float, value))


def _string(value: object, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid sleep response string")
    return value


def parse_response(obj: dict[str, Value], command: str, variant: str) -> dict[str, Value]:
    """Required/nullable fields follow the accepted beans, never guessed success defaults."""
    nullable = command != "s_time" or variant == "hj"
    integer = command in ("s_init", "q_sens", "q_antiSnore", "s_antiSnore")
    result: dict[str, Value] = {
        "id": _number(obj.get("id"), nullable=nullable, integer=integer),
        "cmd": _string(obj.get("cmd"), nullable),
    }
    val = obj.get("val")
    if (
        val is None
        and nullable
        and not (variant == "mm" and command == "q_report")
        and command != "s_init"
    ):
        result["val"] = None
        return result
    if command in ("q_part", "s_part"):
        result["val"] = val
        return result
    if not isinstance(val, dict):
        raise ValueError("Sleep response val must be an object")
    if command in ("s_time", "s_init"):
        optional = variant == "hj" or command == "s_init"
        result["val"] = {
            "error": _number(val.get("error"), nullable=optional, integer=command == "s_init"),
            "ver": _string(val.get("ver"), optional),
        }
        if variant.endswith("hj") or command == "s_init":
            cast(dict[str, Value], result["val"])["type"] = _string(val.get("type"), optional)
    elif command == "q_time":
        ts = val.get("ts")
        if ts is not None and type(ts) not in (int, float):
            raise ValueError("Invalid sleep timestamp")
        result["val"] = {"ts": ts, "utc": _string(val.get("utc"), True)}
    elif command == "q_report":
        result["val"] = {"fsize": _number(val.get("fsize"), nullable=True)}
    elif (
        command in ("q_sens", "q_antiSnore", "s_antiSnore")
        or command == "q_realtime"
        and variant.endswith("hj")
    ):
        sides: dict[str, Value] = {}
        for side in ("L", "R"):
            values = val.get(side) or []
            if not isinstance(values, list) or any(type(v) not in (int, float) for v in values):
                raise ValueError("Sleep side must be a numeric list")
            sides[side] = values
        result["val"] = sides
    elif command == "q_realtime":
        result["val"] = {"L": _string(val.get("L")), "R": _string(val.get("R"))}
    return result


@dataclass
class Receiver:
    variant: str
    current: str | None = None
    buffer: bytearray = field(default_factory=bytearray)
    expected: int = 0
    report_size: int = 0
    report_chunks: int = 0
    report_type: int = 1

    def clear(self) -> None:
        self.current = None
        self.buffer.clear()
        self.expected = self.report_size = self.report_chunks = 0

    def feed(self, chunk: bytes) -> tuple[str, dict[str, Value]] | None:
        if not self.current or not chunk:
            self.buffer.clear()
            return None
        if self.current == "q_report_allow":
            data = chunk[14:] if self.variant.endswith("hj") else chunk
            self.buffer.extend(data)
            self.report_chunks += len(data)
            if len(self.buffer) > 2**20:
                self.clear()
                raise ValueError("Oversized sleep report")
            if self.report_chunks >= self.report_size:
                decoder = zlib.decompressobj(31)
                raw = decoder.decompress(bytes(self.buffer), 2**20)
                self.buffer.clear()
                if not decoder.eof or decoder.unconsumed_tail:
                    raise ValueError("Incomplete or oversized compressed report")
                document = json.loads(raw.decode("latin1"))
                version = document.get("algorithmVersion") if isinstance(document, dict) else None
                newer = False
                if self.report_type == 2 and not isinstance(document, list):
                    raise ValueError("Month report requires a list")
                if self.report_type == 1 and not isinstance(document, dict):
                    raise ValueError("Day report requires an object")
                if (
                    self.report_type == 1
                    and self.variant.endswith("hj")
                    and not isinstance(version, str)
                ):
                    raise ValueError("HJ day report requires its algorithm version")
                if (
                    self.report_type == 1
                    and self.variant.endswith("hj")
                    and isinstance(version, str)
                ):
                    parts = [int(part) for part in version.split(".")]
                    newer = (
                        bool(parts)
                        and parts[0] != 1
                        and parts + [0] * max(0, 4 - len(parts)) >= [0, 0, 3, 0]
                    )
                self.current = None
                return "report_transfer", {
                    "compressed_bytes": self.report_chunks,
                    "interpretation": "excluded",
                    "format": "month"
                    if self.report_type == 2
                    else "mm_day"
                    if self.variant.endswith("mm")
                    else "hj_new_day"
                    if newer
                    else "hj_old_day",
                }
            return None
        if not self.buffer:
            size = sleep_envelope.response_size(chunk)
            if size is None:
                raise ValueError("Short first sleep chunk")
            self.expected = size
        self.buffer.extend(chunk)
        if len(self.buffer) > 2**20:
            self.clear()
            raise ValueError("Oversized sleep response")
        if len(self.buffer) < self.expected:
            return None
        raw = bytes(self.buffer)
        self.buffer.clear()
        text = raw[14:].decode("latin1")
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("Sleep response must be a JSON object")
        command = (
            next((name for name in ORDER if name in text), "")
            if self.variant.endswith("hj")
            else self.current
        )
        if command not in (
            "s_time",
            "q_time",
            "q_part",
            "s_part",
            "q_realtime",
            "q_report",
            "s_init",
            "q_sens",
            "q_antiSnore",
            "s_antiSnore",
        ):
            return None
        return command, parse_response(obj, command, self.variant)


class SleepController(BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, variant: str) -> None:
        super().__init__(coordinator)
        if variant not in CHOICES:
            raise ValueError("Choose MM or HJ and the current or restored sleep session")
        self.variant = variant
        self.mm = variant.endswith("mm")
        self.receiver = Receiver(variant)
        self.sequence = 1
        self._tx: BleakGATTCharacteristic | None = None
        self._rx: BleakGATTCharacteristic | None = None
        self._owner: BleakClient | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._poll: asyncio.Task[None] | None = None
        self._last_write: float | None = None
        self._report_context: dict[str, Value] | None = None
        self._status: str | None = None
        self.state: dict[str, Value] = {}

    @property
    def control_characteristic_uuid(self) -> str:
        return self._tx.uuid if self._tx else TX

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return self._poll is not None or super().requires_persistent_connection

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

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

    def _publish(self) -> None:
        self.forward_controller_state_updates(STATUS(self._status), STATE(self.state.copy()))

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "richmat_app_sleep_status",
                "richmat_app_sleep_status",
                STATUS,
                "mdi:sleep",
                attribute_keys=(STATE,),
            ),
        )

    def _task(self, command: str, value: object) -> None:
        owner = self._owner

        async def run() -> None:
            async def execute(controller: BedController) -> None:
                if controller is self and self._owner is owner:
                    await self.send(command, value)

            try:
                await self._coordinator.async_execute_controller_command(
                    execute, cancel_running=False
                )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self.state["rejection"] = str(err)
                self._publish()

        task = self._coordinator.entry.async_create_background_task(
            self._coordinator.hass, run(), name="richmat_app_sleep_followup"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _notification(
        self, owner: BleakClient, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if self._owner is not owner or self.client is not owner or not owner.is_connected:
            return
        try:
            result = self.receiver.feed(bytes(data))
            if result is None:
                return
            command, obj = result
            self._status = command
            val = obj.get("val")
            # Keep controls and metadata, exclude physiological values themselves.
            if command != "q_realtime":
                self.state[command] = obj
            if command == "s_time" and isinstance(val, dict):
                self.state["version"] = val.get("ver")
                self.state["type"] = val.get("type")
                if self.mm and self.variant.startswith("old_"):
                    self._task("s_part", None)
                elif self.variant == "old_hj":
                    self._task("q_time", None)
            if command == "q_time" and self.variant == "old_hj":
                self._task("q_part", None)
            if command in ("q_part", "s_part"):
                self.state["part"] = val
            if command in ("q_antiSnore", "s_antiSnore") and isinstance(val, dict):
                sides = [val.get(side) for side in ("L", "R")]
                self.state["anti_snore"] = all(
                    isinstance(a, list)
                    and bool(a)
                    and type(a[0]) in (int, float)
                    and math.trunc(cast(int | float, a[0])) == 1
                    for a in sides
                )
            if command == "q_report" and isinstance(val, dict):
                size = val.get("fsize")
                if type(size) is int and size > 0 and self._report_context is not None:
                    if size > 2**20:
                        raise ValueError("Oversized sleep report")
                    self.receiver.report_size = size
                    value = {**self._report_context, "allow": 1} if self.mm else {"allow": 1}
                    self._task("q_report_allow", value)
                elif type(size) is int:
                    self.state["report_size"] = size
        except (ValueError, TypeError, IndexError, UnicodeError) as err:
            self.state["rejection"] = str(err)
        self._publish()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Sleep device disconnected")
        self.on_disconnect()
        services: set[str] = set(SERVICES)
        if self.variant.startswith("old_"):
            services.update(
                richmat_codec.TRANSPORTS[k].service_uuid for k in ("n1", "w1", "w2", "w3", "w4")
            )
        for service in client.services:
            if service.uuid.lower() not in services:
                continue
            for char in service.characteristics:
                if self._tx is None and (
                    "write-without-response" in char.properties
                    if self.mm
                    else char.uuid.lower() == TX and "write" in char.properties
                ):
                    self._tx = char
                if (
                    self._rx is None
                    and "notify" in char.properties
                    and (self.mm or char.uuid.lower() == RX)
                ):
                    self._rx = char
        if self._tx is None or self._rx is None:
            raise ValueError(
                "Sleep session lacks its selected write and notification characteristics"
            )
        self._owner = client
        try:
            await client.start_notify(self._rx, partial(self._notification, client))
            await asyncio.sleep(0.00015)
            await self.execute_request(Request("sync"))
            if self.variant == "hj":
                await self.send("s_part", 12)
        except BaseException:
            self.on_disconnect()
            raise

    async def send(self, command: str, value: object) -> None:
        client, tx = self._owner, self._tx
        if client is None or tx is None or self.client is not client or not client.is_connected:
            raise ConnectionError("Sleep BLE session changed")
        sequence = self.sequence
        self.sequence = sequence % 254 + 1
        wire_cmd = "q_report" if command == "q_report_allow" else command
        data = packet(sequence, wire_cmd, value)
        self.receiver.buffer.clear()
        self.receiver.current = command
        async with self._ble_lock:
            if self._last_write is not None:
                await asyncio.sleep(
                    max(0, self._last_write + 0.1 - asyncio.get_running_loop().time())
                )
            stride = max(1, client.mtu_size - 3)
            for offset in range(0, len(data), stride):
                if self._owner is not client or self._coordinator.cancel_command.is_set():
                    self.receiver.clear()
                    return
                await client.write_gatt_char(
                    tx, data[offset : offset + stride], response=not self.mm
                )
            self._last_write = asyncio.get_running_loop().time()

    def validate_request(self, r: Request) -> None:
        if r.operation not in (
            "sync",
            "sleep_sync",
            "sleep_time",
            "sleep_part",
            "sleep_realtime",
            "sleep_report",
            "sleep_snore",
            "sleep_sensitivity",
            "sleep_init",
            "sleep_cancel",
            "sleep_poll",
        ):
            raise ValueError("Choose a sleep control operation")
        if self.mm and r.operation in (
            "sleep_time",
            "sleep_snore",
            "sleep_sensitivity",
            "sleep_init",
        ):
            raise ValueError("This MM session does not implement that HJ command")
        if self.variant == "old_hj" and r.operation == "sleep_snore" and r.value:
            raise ValueError("Old HJ setter is a removed-code branch; query using value zero")
        if r.operation == "sleep_part" and r.value not in (0, 11, 12, 13):
            raise ValueError("Choose query (0), off (11), automatic (12), or on (13)")
        if r.operation == "sleep_report" and (
            r.when is None or r.part not in (11, 12, 13) or r.report_type not in (1, 2)
        ):
            raise ValueError("Report session requires a date, part and day/month type")

    async def execute_request(self, r: Request) -> None:
        self.validate_request(r)
        op = r.operation
        if op not in ("sync", "sleep_sync", "sleep_realtime", "sleep_poll"):
            self._cancel_work()
            self.receiver.clear()
        if op == "sleep_cancel":
            self._cancel_work()
            self.receiver.clear()
            return
        if op == "sleep_poll":
            self._cancel_work()
            if not r.enabled:
                return

            async def poll() -> None:
                while self._owner:
                    await asyncio.sleep(2)
                    self._task("q_realtime", {"type": 0, "time": 1})

            self._poll = self._coordinator.entry.async_create_background_task(
                self._coordinator.hass, poll(), name="richmat_app_sleep_poll"
            )
            return
        if op in ("sync", "sleep_sync"):
            now = dt_util.now()
            offset = now.utcoffset()
            value = (
                {"ts": int(now.timestamp()), "tz": self._coordinator.hass.config.time_zone}
                if self.mm
                else {
                    "ts": int(now.timestamp()),
                    "utc": math.trunc(offset.total_seconds() / 3600) if offset else 0,
                }
            )
            await self.send("s_time", value)
        elif op == "sleep_part":
            if r.value == self.state.get("part") and r.value:
                return
            await self.send("s_part" if r.value or self.mm else "q_part", r.value or None)
        elif op == "sleep_time":
            await self.send("q_time", None)
        elif op == "sleep_realtime":
            await self.send("q_realtime", {"type": 0, "time": 1})
        elif op == "sleep_snore":
            await self.send(
                "s_antiSnore" if r.value else "q_antiSnore",
                {"L": [int(r.enabled), 8, 4], "R": [int(r.enabled), 8, 4]} if r.value else None,
            )
        elif op == "sleep_sensitivity":
            await self.send("q_sens", None)
        elif op == "sleep_init":
            await self.send("s_init", 0)
        elif op == "sleep_report":
            assert r.when is not None
            self._cancel_work()
            self.receiver.clear()
            value: dict[str, Value] = {
                "part": r.part,
                "type": r.report_type,
                "y": r.when.year,
                "m": r.when.month,
                "d": r.when.day,
            }
            self._report_context = value
            self.receiver.report_type = r.report_type
            await self.send("q_report", value)

    def _cancel_work(self) -> None:
        if self._poll:
            self._poll.cancel()
            self._poll = None
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()

    def on_disconnect(self) -> None:
        self._cancel_work()
        self.receiver.clear()
        self._tx = self._rx = self._owner = None
        self._last_write = None
        self._report_context = None

    async def stop_notify(self) -> None:
        client, rx = self._owner, self._rx
        self.on_disconnect()
        if client and rx and client.is_connected:
            await client.stop_notify(rx)

    async def stop_all(self) -> None:
        self._cancel_work()
        self.receiver.clear()

    async def _unsupported(self, *args: object) -> None:
        raise NotImplementedError("Sleep sessions have no bed motor commands")

    move_head_up = move_head_down = move_head_stop = _unsupported
    move_back_up = move_back_down = move_back_stop = _unsupported
    move_legs_up = move_legs_down = move_legs_stop = _unsupported
    move_feet_up = move_feet_down = move_feet_stop = _unsupported
    preset_flat = _unsupported

    async def preset_memory(self, memory_num: int) -> None:
        await self._unsupported()

    async def program_memory(self, memory_num: int) -> None:
        await self._unsupported()


async def build_controller(ctx: BuildContext) -> SleepController:
    return SleepController(ctx.coordinator, variant=ctx.variant or "")
