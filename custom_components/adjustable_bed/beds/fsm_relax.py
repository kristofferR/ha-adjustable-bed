"""FSM Relax 1.9 app profile. Static artifact verified; hardware unverified."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from bleak.exc import BleakError

from ..fsm_relax_state import FsmRelaxState, validate_positions
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from .limoss import LimossController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_SERVICE = "0000ffe0-0000-1000-8000-00805f9b34fb"
_CHAR = "0000ffe1-0000-1000-8000-00805f9b34fb"
_TICK = 0.06
# Exact source order, including the asymmetric light-only six-key table.
_TABLES = {
    2: (
        (0x12, 0x13),
        (0x12, 0x13, 0x70),
        (0x12, 0x13, 0x60, 0x61, 0x62, 0x63),
        (0x12, 0x13, 0x64, 0x65, 0x70),
    ),
    4: (
        (0x12, 0x13, 0x22, 0x23, 0x50, 0x51),
        (0x12, 0x13, 0x22, 0x23, 0x70, 0x51),
        (0x12, 0x13, 0x22, 0x23, 0x60, 0x61, 0x62, 0x63),
        (0x12, 0x13, 0x22, 0x23, 0x70, 0x51, 0x64, 0x65),
    ),
    6: (
        (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x54, 0x55),
        (0x12, 0x13, 0x22, 0x23, 0x32, 0x33, 0x70, 0x54),
        (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x32, 0x33, 0x62, 0x54, 0x55, 0x63),
        (0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x32, 0x33, 0x70, 0x54, 0x55),
    ),
    8: (
        (0x12, 0x13, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
        (0x12, 0x13, 0x70, 0x22, 0x23, 0x50, 0x51, 0x52, 0x53),
        (0x12, 0x13, 0x60, 0x22, 0x23, 0x61, 0x50, 0x51, 0x62, 0x52, 0x53, 0x63),
        (0x12, 0x13, 0x64, 0x22, 0x23, 0x65, 0x50, 0x51, 0x70, 0x52, 0x53),
    ),
}
_LABELS = {
    0x12: "Back up",
    0x13: "Back down",
    0x22: "Legs up",
    0x23: "Legs down",
    0x32: "Tilt up",
    0x33: "Tilt down",
    0x50: "Combined up",
    0x51: "Combined down",
    0x52: "Elevation up",
    0x53: "Elevation down",
    0x54: "All regions up",
    0x55: "All regions down",
    0x60: "Back massage plus",
    0x61: "Back massage minus",
    0x62: "Legs massage plus",
    0x63: "Legs massage minus",
    0x64: "Both massage plus",
    0x65: "Both massage minus",
    0x70: "Underbed light control",
}


@dataclass(frozen=True, slots=True)
class FsmRelaxProfile:
    """Explicit immutable app layout, independent of shared advertisements."""

    layout: Literal["chair", "bed"] = "chair"
    light_enabled: bool = False
    massage_enabled: bool = False
    reversals: tuple[bool, bool, bool, bool] = (False, False, False, False)

    def __post_init__(self) -> None:
        if (
            self.layout not in ("chair", "bed")
            or type(self.light_enabled) is not bool
            or type(self.massage_enabled) is not bool
        ):
            raise ValueError("Invalid explicit FSM Relax profile")
        if (
            not isinstance(self.reversals, tuple)
            or len(self.reversals) != 4
            or any(type(v) is not bool for v in self.reversals)
        ):
            raise ValueError("Exactly four boolean reversals are required")


def build_packet(body: bytes, counter: int) -> bytes:
    """Pure source framing; the shared cipher has exact 43-vector proof."""
    if len(body) != 5:
        raise ValueError("FSM Relax command body must be five bytes")
    inner = b"\xaa" + body + bytes((counter & 255,))
    inner += bytes((sum(inner) & 255,))
    outer = b"\xdd" + LimossController._tea_encrypt(inner)
    return outer + bytes((sum(outer) & 255,))


def decode_packet(packet: bytes) -> bytes | None:
    """Reject malformed input before publishing raw or capability state."""
    if len(packet) != 10 or packet[0] != 0xDD or sum(packet[:9]) & 255 != packet[9]:
        return None
    inner = LimossController._tea_decrypt(packet[1:9])
    if inner[0] != 0xAA or sum(inner[:7]) & 255 != inner[7]:
        return None
    return inner[1:6]


def signed_version(data: bytes) -> str:
    """Preserve signed Java byte concatenation, including negative fields."""
    values = [v if v < 128 else v - 256 for v in data]
    return (
        (str(values[0]) if values[0] >= 0 else "")
        + str(values[1])
        + "."
        + (str(values[2]) if values[2] >= 0 else "")
        + (str(values[3]) if values[3] >= 0 else "")
    )


def _action(opcode: int) -> Callable[[BedController], Coroutine[Any, Any, None]]:
    async def invoke(controller: BedController) -> None:
        if not isinstance(controller, FsmRelaxController):
            raise ValueError("FSM Relax controller required")
        await controller.hold_control(f"command_{opcode:02x}", controller._default_hold_ms())

    return invoke


class FsmRelaxController(BedController):
    """Separate app semantics, with opaque signed memories and bounded sessions."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: FsmRelaxProfile | None = None,
        state: FsmRelaxState,
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile or FsmRelaxProfile()
        self.local = state
        self._write_lock = asyncio.Lock()
        self._memory_lock = state.session.memory_lock
        self._buffer = bytearray()
        self._generation = 0
        self._subscribed = False
        self._quarantined = False
        self._pending: dict[int, asyncio.Future[bytes]] = {}
        self._optional_task: asyncio.Task[None] | None = None
        self._metadata_tasks: set[asyncio.Task[None]] = set()
        self._capabilities: bytes | None = state.capability_body
        self._live_capabilities = False
        self._state: dict[str, object] = {}
        if state.serial is not None:
            self._publish({"serial": state.serial})
        if self._capabilities is not None:
            self._accept_body(self._capabilities)

    @property
    def _counter(self) -> int:
        return self.local.session.counter

    @_counter.setter
    def _counter(self, value: int) -> None:
        self.local.session.counter = value & 255

    @property
    def _quarantine_client(self) -> object | None:
        return self.local.session.quarantine_client

    @_quarantine_client.setter
    def _quarantine_client(self, client: object | None) -> None:
        self.local.session.quarantine_client = client

    @property
    def control_characteristic_uuid(self) -> str:
        return _CHAR

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # App-labelled buttons/services do not assert physical actuator axes.
        return ()

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def supports_held_control(self) -> bool:
        return bool(self.held_control_options)

    @property
    def memory_slot_count(self) -> int:
        return min(int.from_bytes(self._capabilities[3:5], "big"), 8) if self._capabilities else 0

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_confirmed_calibration(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return self.local.names

    @property
    def key_count(self) -> int:
        key = self._capabilities[1] if self._capabilities else 8
        return key if key in (2, 4, 6, 8) else 8

    @property
    def action_opcodes(self) -> tuple[int, ...]:
        if self._capabilities is None:
            return ()
        if self.profile.layout == "chair":
            return (0x50, 0x51) if self.key_count == 2 else (0x22, 0x23, 0x12, 0x13, 0x50, 0x51)
        flags = int(self.profile.light_enabled) + 2 * int(self.profile.massage_enabled)
        return _TABLES[self.key_count][flags]

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"command_{op:02x}" for op in self.action_opcodes)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def label(op: int) -> str:
            if self.profile.layout == "chair" and op in (0x12, 0x13):
                return "Footrest up" if op == 0x12 else "Footrest down"
            if self.profile.layout == "chair" and op in (0x22, 0x23):
                return "Chair back up" if op == 0x22 else "Chair back down"
            return _LABELS[op]

        return tuple(
            ControllerButtonSpec(f"fsm_relax_{op:02x}", label(op), _action(op))
            for op in self.action_opcodes
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = (
            "key_count",
            "vibration_count",
            "reported_memory_count",
            "hardware_version",
            "software_version",
            "serial",
            "acknowledgement",
            "calibration_observed",
            "memory_quarantined",
            "optional_information",
        ) + tuple(f"motor_{i}_raw" for i in range(1, 5))
        return tuple(
            ControllerStateSensorSpec(
                f"fsm_relax_{key}",
                f"fsm_relax_{key}",
                f"fsm_relax_{key}",
                "mdi:information-outline",
            )
            for key in fields
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **super().protocol_diagnostics,
            **self._state,
            "layout": self.profile.layout,
            "reversals": list(self.profile.reversals),
            "memory_quarantined": self._quarantined,
            "reply_freshness": "No echoed request ID; delayed same-opcode replies may be indistinguishable",
            "hardware_verified": False,
            "held_controls": list(self.held_control_options),
        }

    def _publish(self, updates: dict[str, object]) -> None:
        values = {f"fsm_relax_{key}": value for key, value in updates.items()}
        self._state.update(values)
        self.forward_controller_state_updates(values)

    def _role(self) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("FSM Relax is not connected")
        roles = [
            char
            for service in client.services or ()
            if service.uuid.lower() == _SERVICE
            for char in service.characteristics
            if char.uuid.lower() == _CHAR
        ]
        if len(roles) != 1:
            raise ValueError("FSM Relax requires exactly one FFE0/FFE1 role")
        return roles[0]

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 60,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if len(command) != 5:
            raise ValueError("Command body must be five bytes")
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        for index in range(repeat_count):
            if event.is_set():
                return
            await asyncio.sleep(max(0, start + index * repeat_delay_ms / 1000 - loop.time()))
            if event.is_set():
                return
            async with self._write_lock:
                role = self._role()
                packet = build_packet(command, self._counter)
                self._counter = (self._counter + 1) & 255
                client = self.client
                if client is None:
                    raise ConnectionError("FSM Relax disconnected")
                # Source forces no-response; properties are not a protocol gate.
                await client.write_gatt_char(role, packet, response=False)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._subscribed:
            return
        role = self._role()
        self._generation += 1
        generation = self._generation
        self._buffer.clear()
        client = self.client
        if client is None:
            raise ConnectionError("FSM Relax disconnected")

        def receive(_sender: object, data: bytearray) -> None:
            if (
                generation == self._generation
                and self._subscribed
                and client.is_connected
                and self.client is client
            ):
                self._receive(bytes(data))

        self._subscribed = True
        try:
            await client.start_notify(role, receive)
        except BaseException:
            self._subscribed = False
            self._generation += 1
            raise
        if self._quarantine_client is not client:
            self._quarantine_client = None
        self._quarantined = self._quarantine_client is client
        self._publish({"memory_quarantined": self._quarantined})

    def on_disconnect(self) -> None:
        self._generation += 1
        self._subscribed = False
        self._live_capabilities = False
        self._buffer.clear()
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()
        if self._optional_task is not None:
            self._optional_task.cancel()
        for task in tuple(self._metadata_tasks):
            task.cancel()

    async def stop_notify(self) -> None:
        self.on_disconnect()
        if self._optional_task is not None:
            self._optional_task.cancel()
            try:
                await self._optional_task
            except asyncio.CancelledError:
                pass
            self._optional_task = None
        for task in tuple(self._metadata_tasks):
            task.cancel()
        if self._metadata_tasks:
            await asyncio.gather(*self._metadata_tasks, return_exceptions=True)
        self._metadata_tasks.clear()
        client = self.client
        if client is not None and client.is_connected:
            await client.stop_notify(_CHAR)

    def _receive(self, data: bytes) -> None:
        # Bound memory before appending arbitrary remote data.
        if len(data) > 1024:
            self._buffer.clear()
            return
        self.forward_raw_notification(_CHAR, data)
        self._buffer.extend(data)
        while self._buffer:
            if self._buffer[0] != 0xDD:
                del self._buffer[0]
                continue
            if len(self._buffer) < 10:
                return
            body = decode_packet(bytes(self._buffer[:10]))
            if body is None:
                del self._buffer[0]
                continue
            del self._buffer[:10]
            self._accept_body(body)
            future = self._pending.get(body[0])
            if future is not None and not future.done():
                future.set_result(body)

    def _accept_body(self, body: bytes) -> None:
        opcode, data = body[0], body[1:]
        if opcode == 2:
            self._capabilities = body
            self._live_capabilities = self._subscribed
            self._publish(
                {
                    "key_count": self.key_count,
                    "vibration_count": data[1],
                    "reported_memory_count": int.from_bytes(data[2:], "big"),
                }
            )
        elif opcode in (0, 1):
            self._publish(
                {"hardware_version" if opcode == 0 else "software_version": signed_version(data)}
            )
        elif opcode in (0x10, 0x20, 0x30, 0x40):
            self._publish({f"motor_{opcode // 16}_raw": int.from_bytes(data, "big", signed=True)})
        elif opcode == 4:
            self._publish({"acknowledgement": "Observed, not correlated to physical arrival"})
        elif opcode == 5:
            self._publish({"calibration_observed": True})
        elif opcode == 6:
            serial = int.from_bytes(data, "big", signed=True)
            self._publish({"serial": serial})
            task = self._coordinator.entry.async_create_background_task(
                self._coordinator.hass, self.local.async_save_serial(serial), "fsm_relax_serial"
            )
            self._metadata_tasks.add(task)
            task.add_done_callback(self._metadata_tasks.discard)

    async def _query(self, opcode: int, *, retries: int = 4, optional: bool = False) -> bytes:
        if opcode in self._pending:
            raise RuntimeError("Response stage already active")
        future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._pending[opcode] = future
        event = self._coordinator.cancel_command
        cancelled = asyncio.create_task(event.wait())
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            for index in range(retries):
                if optional:
                    async with self._coordinator._command_lock:
                        if not self._subscribed or self._coordinator.controller is not self:
                            raise ConnectionError("Optional query session ended")
                        await self.write_command(
                            bytes((opcode, 0, 0, 0, 3 if opcode in (0, 1, 2) else 0))
                        )
                else:
                    await self.write_command(
                        bytes((opcode, 0, 0, 0, 3 if opcode in (0, 1, 2) else 0))
                    )
                done, _pending = await asyncio.wait(
                    (future, cancelled),
                    timeout=max(0, started + index + 1 - loop.time()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancelled in done:
                    raise asyncio.CancelledError
                if future in done:
                    return future.result()
            raise TimeoutError("FSM Relax response timed out; no reply correlation is available")
        finally:
            self._pending.pop(opcode, None)
            cancelled.cancel()
            if not future.done():
                future.cancel()

    async def async_discover_capabilities(self) -> None:
        await self.local.async_load()
        await self.start_notify()
        previous = self.local.capability_body
        async with asyncio.timeout(4):
            body = await self._query(2)
        await self.local.async_save_capabilities(body)
        if previous is not None and previous != body:
            self._coordinator._pending_capability_reload = True
        if self._optional_task is None or self._optional_task.done():
            self._optional_task = self._coordinator.entry.async_create_background_task(
                self._coordinator.hass,
                self._optional_information(),
                "fsm_relax_optional_information",
            )

    async def _optional_information(self) -> None:
        try:
            for opcode in (0, 1):
                await asyncio.sleep(0.12)
                await self._query(opcode, optional=True)
            self._publish({"optional_information": "Observed"})
        except TimeoutError, ConnectionError, ValueError, OSError, BleakError:
            self._publish({"optional_information": "Unavailable; capabilities remain usable"})

    def _default_hold_ms(self) -> int:
        return max(1, self._coordinator.motor_pulse_count) * 60

    async def _cleanup(self, opcode: int, params: bytes) -> None:
        async def release() -> None:
            loop = asyncio.get_running_loop()
            started = loop.time()
            event = asyncio.Event()
            failure: Exception | None = None
            for index in range(5):
                await asyncio.sleep(max(0, started + (index + 1) * _TICK - loop.time()))
                try:
                    await self.write_command(bytes((opcode,)) + params, cancel_event=event)
                except Exception as error:
                    failure = failure or error
            if failure is not None:
                raise failure

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
        if not self._live_capabilities:
            raise ConnectionError("Fresh capability response required before app control")
        if control not in self.held_control_options:
            raise ValueError("Action is not present in the selected FSM Relax table")
        if type(duration_ms) is not int or not 1 <= duration_ms <= 120000:
            raise ValueError("Hold must be 1..120000 ms")
        opcode = int(control.removeprefix("command_"), 16)
        event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        index = 1
        try:
            while index * 60 <= duration_ms:
                await asyncio.sleep(max(0, start + index * _TICK - loop.time()))
                if event.is_set():
                    break
                await self.write_command(bytes((opcode,)) + bytes(self.profile.reversals))
                index += 1
        finally:
            await self._cleanup(0xFF, bytes(self.profile.reversals))

    async def stop_all(self) -> None:
        await self._cleanup(0xFF, bytes(self.profile.reversals))

    def _validate_memory(self, slot: int) -> None:
        if type(slot) is not int or not 1 <= slot <= self.memory_slot_count:
            raise ValueError("Selected memory slot is unavailable")
        if not self._subscribed or not self._live_capabilities:
            raise ConnectionError("Fresh capability subscription required")
        if self._quarantined:
            raise RuntimeError(
                "Memory operations quarantined until disconnect and fresh subscription"
            )

    def _quarantine(self) -> None:
        self._quarantined = True
        self._quarantine_client = self.client
        self._buffer.clear()
        self._publish({"memory_quarantined": True})

    def validate_memory_recall(self, memory_num: int) -> None:
        """Check local targets before fan-out, without connecting an offline bed."""
        if type(memory_num) is not int:
            raise ValueError("Selected memory slot is unavailable")
        super().validate_memory_recall(memory_num)
        positions = self.local.slots.get(memory_num)
        if positions is None or 0 not in positions:
            raise ValueError("Memory has no motor-zero target")
        validate_positions(positions)
        if self._quarantined or self._quarantine_client is not None:
            raise ValueError("Memory operations quarantined until disconnect and fresh subscription")
        client = self.client
        if client is not None and client.is_connected and (
            not self._subscribed or not self._live_capabilities
        ):
            raise ValueError("Fresh capability subscription required")

    async def program_memory(self, memory_num: int) -> None:
        async with self._memory_lock:
            self._validate_memory(memory_num)
            try:
                positions = {}
                for index in range(self.key_count // 2):
                    body = await self._query((index + 1) * 16, retries=1)
                    positions[index] = int.from_bytes(body[1:], "big", signed=True)
                await self.local.async_save_slot(memory_num, positions)
            except BaseException:
                self._quarantine()
                raise

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        if type(hold_ms) is not int or not 1 <= hold_ms <= 120000:
            raise ValueError("Explicit hold must be 1..120000 ms")
        async with self._memory_lock:
            self._validate_memory(slot)
            self.validate_memory_recall(slot)
            positions = self.local.slots.get(slot)
            assert positions is not None
            loop = asyncio.get_running_loop()
            start = loop.time()
            event = self._coordinator.cancel_command
            try:
                tick = 1
                for index in range(self.key_count // 2):
                    if index not in positions:
                        continue
                    await asyncio.sleep(max(0, start + tick * _TICK - loop.time()))
                    if event.is_set():
                        self._quarantine()
                        break
                    await self.write_command(
                        bytes(((index + 1) * 16 + 1,))
                        + positions[index].to_bytes(4, "big", signed=True)
                    )
                    tick += 1
                if not event.is_set():
                    try:
                        await asyncio.wait_for(
                            event.wait(), max(0, start + hold_ms / 1000 - loop.time())
                        )
                        self._quarantine()
                    except TimeoutError:
                        pass
            except BaseException:
                self._quarantine()
                raise
            finally:
                try:
                    await self._cleanup(3, bytes(4))
                except BaseException:
                    self._quarantine()
                    raise

    async def preset_memory(self, memory_num: int) -> None:
        await self.recall_memory(memory_num, hold_ms=self._default_hold_ms())

    async def calibrate(self, *, confirmed: bool) -> None:
        if confirmed is not True:
            raise ValueError("Calibration requires explicit confirmation")
        if not self._live_capabilities:
            raise ConnectionError("Fresh capability subscription required")
        # One attempt only. A write failure does not prove hardware did nothing.
        await self.write_command(b"\x05" + bytes(self.profile.reversals))

    async def move_head_up(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_head_down(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        raise NotImplementedError("FSM Relax has no firmware flat preset")

    async def move_back_up(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_back_down(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_legs_down(self) -> None:
        raise NotImplementedError("Use explicit app controls")

    async def move_legs_stop(self) -> None:
        await self.stop_all()
