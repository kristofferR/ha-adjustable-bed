"""FSM Relax 1.9 app profile over the Limoss DD codec. Static artifact verified; hardware unverified."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState

from ...codec import limoss as codec
from ...const import (
    CONF_FSM_RELAX_MEMORY_NAMES,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_PRODUCT_TYPE,
    CONF_REVERSE_MOTORS,
    LIMOSS_CHAR_UUID,
    LIMOSS_SERVICE_UUID,
)
from ...controller_state import StateKey
from ...profiles.limoss import FSM_LABELS, FSM_RELAX, Burst, LimossProfile, fsm_relax_layout
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from .state import (
    FsmRelaxSession,
    validate_capability_body,
    validate_names,
    validate_positions,
)

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator


def _state_key(field: str) -> StateKey[object]:
    """Diagnostic fields carry mixed value types."""
    return StateKey[object](f"fsm_relax_{field}")


@dataclass(frozen=True, slots=True)
class FsmRelaxSetup:
    """The entry's explicit app layout, independent of shared advertisements."""

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


def _action(opcode: int) -> Callable[[BedController], Coroutine[Any, Any, None]]:
    async def invoke(controller: BedController) -> None:
        if not isinstance(controller, FsmRelaxController):
            raise ValueError("FSM Relax controller required")
        await controller.hold_control(f"command_{opcode:02x}", controller._default_hold_ms())

    return invoke


class FsmRelaxController(ProfileExecution[LimossProfile], BedController):
    """Separate app semantics, with opaque signed memories and bounded sessions."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        setup: FsmRelaxSetup | None = None,
        session: FsmRelaxSession,
        names: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.profile = FSM_RELAX
        self.setup = setup or FsmRelaxSetup()
        self.session = session
        self.names = names or validate_names([""] * 8)
        self._write_lock = asyncio.Lock()
        self._memory_lock = session.memory_lock
        self._parser = codec.StreamParser(verify=True)
        self._generation = 0
        self._subscribed = False
        self._quarantined = False
        self._pending: dict[int, asyncio.Future[bytes]] = {}
        self._optional_task: asyncio.Task[None] | None = None
        self._capabilities: bytes | None = self._stored_capabilities
        self._live_capabilities = False
        self._state: dict[str, object] = {}
        if session.serial is not None:
            self._publish({"serial": session.serial})
        if self._capabilities is not None:
            self._accept_body(self._capabilities)

    @property
    def _counter(self) -> int:
        return self.session.counter

    @_counter.setter
    def _counter(self, value: int) -> None:
        self.session.counter = value & 255

    @property
    def _quarantine_client(self) -> object | None:
        return self.session.quarantine_client

    @_quarantine_client.setter
    def _quarantine_client(self, client: object | None) -> None:
        self.session.quarantine_client = client

    @property
    def persisted_app_state(self) -> dict[str, object]:
        return self.session.persisted()

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        self.session.restore(state)
        if self.session.serial is not None:
            self._publish({"serial": self.session.serial})

    @property
    def _stored_capabilities(self) -> bytes | None:
        """The last capability reply, kept in the entry because it decides the entities."""
        capabilities = self._coordinator.entry.data.get("capabilities")
        if not isinstance(capabilities, Mapping):
            return None
        return validate_capability_body(capabilities.get("fsm_relax"))

    @property
    def control_characteristic_uuid(self) -> str:
        return LIMOSS_CHAR_UUID

    @property
    def _tick_ms(self) -> int:
        assert self.profile.tick_ms is not None
        return self.profile.tick_ms

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self._known_capabilities is not None

    @property
    def _known_capabilities(self) -> bytes | None:
        # A cached offline controller observes successful saves by its live replacement.
        if not self._subscribed and (stored := self._stored_capabilities) is not None:
            return stored
        return self._capabilities

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
        body = self._known_capabilities
        return min(int.from_bytes(body[3:5], "big"), 8) if body else 0

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_memory_programming(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return self.names

    @property
    def key_count(self) -> int:
        body = self._known_capabilities
        key = body[1] if body else 8
        return key if key in (2, 4, 6, 8) else 8

    @property
    def action_opcodes(self) -> tuple[int, ...]:
        if self._known_capabilities is None:
            return ()
        layout = fsm_relax_layout(
            self.setup.layout == "chair",
            self.key_count,
            self.setup.light_enabled,
            self.setup.massage_enabled,
        )
        return tuple(op for op in self.profile.layouts[layout] if op is not None)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"command_{op:02x}" for op in self.action_opcodes)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def label(op: int) -> str:
            if self.setup.layout == "chair" and op in (0x12, 0x13):
                return "Footrest up" if op == 0x12 else "Footrest down"
            if self.setup.layout == "chair" and op in (0x22, 0x23):
                return "Chair back up" if op == 0x22 else "Chair back down"
            return FSM_LABELS[op]

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
                _state_key(key),
                "mdi:information-outline",
            )
            for key in fields
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        persisted: dict[str, object] = {}
        if not self._subscribed:
            body = self._known_capabilities
            if body is not None:
                persisted.update(
                    fsm_relax_key_count=self.key_count,
                    fsm_relax_vibration_count=body[2],
                    fsm_relax_reported_memory_count=int.from_bytes(body[3:5], "big"),
                )
            if self.session.serial is not None:
                persisted["fsm_relax_serial"] = self.session.serial
        return {
            **super().protocol_diagnostics,
            **self._state,
            **persisted,
            "layout": self.setup.layout,
            "reversals": list(self.setup.reversals),
            "memory_quarantined": self._quarantined,
            "reply_freshness": "No echoed request ID; delayed same-opcode replies may be indistinguishable",
            "hardware_verified": False,
            "held_controls": list(self.held_control_options),
        }

    def _publish(self, updates: dict[str, object]) -> None:
        values = [_state_key(key)(value) for key, value in updates.items()]
        self._state.update((update.key, update.value) for update in values)
        self.forward_controller_state_updates(*values)

    def _role(self) -> BleakGATTCharacteristic:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("FSM Relax is not connected")
        roles = [
            char
            for service in client.services or ()
            if service.uuid.lower() == LIMOSS_SERVICE_UUID
            for char in service.characteristics
            if char.uuid.lower() == LIMOSS_CHAR_UUID
        ]
        if len(roles) != 1:
            raise ValueError("FSM Relax requires exactly one FFE0/FFE1 role")
        return roles[0]

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if repeat_delay_ms is None:
            repeat_delay_ms = self._tick_ms
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
                packet = codec.frame(command, self._counter)
                self._counter = (self._counter + 1) & 255
                client = self.client
                if client is None:
                    raise ConnectionError("FSM Relax disconnected")
                self._record_command_trace(
                    LIMOSS_CHAR_UUID, packet, response=False, characteristic=role
                )
                # Source forces no-response; properties are not a protocol gate.
                await client.write_gatt_char(role, packet, response=False)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._subscribed:
            return
        role = self._role()
        self._generation += 1
        generation = self._generation
        self._parser.clear()
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
        self._parser.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("FSM Relax disconnected"))
        self._pending.clear()
        if self._optional_task is not None:
            self._optional_task.cancel()

    async def stop_notify(self) -> None:
        self.on_disconnect()
        if self._optional_task is not None:
            self._optional_task.cancel()
            try:
                await self._optional_task
            except asyncio.CancelledError:
                pass
            self._optional_task = None
        client = self.client
        if client is not None and client.is_connected:
            await client.stop_notify(LIMOSS_CHAR_UUID)

    def _receive(self, data: bytes) -> None:
        # Bound memory before appending arbitrary remote data.
        if len(data) > 1024:
            self._parser.clear()
            return
        self.forward_raw_notification(LIMOSS_CHAR_UUID, data)
        for body in self._parser.feed(data):
            self._accept_body(body)
            future = self._pending.get(body[0])
            if future is not None and not future.done():
                future.set_result(body)

    def _accept_body(self, body: bytes) -> None:
        opcode, data = body[0], body[1:]
        if opcode == codec.QUERY_CAPABILITIES:
            self._capabilities = body
            self._live_capabilities = self._subscribed
            self._publish(
                {
                    "key_count": self.key_count,
                    "vibration_count": data[1],
                    "reported_memory_count": int.from_bytes(data[2:], "big"),
                }
            )
        elif opcode in (codec.QUERY_HARDWARE, codec.QUERY_SOFTWARE):
            field = "hardware_version" if opcode == codec.QUERY_HARDWARE else "software_version"
            self._publish({field: codec.version(data)})
        elif opcode in codec.POSITION_OPCODES:
            self._publish({f"motor_{opcode // 16}_raw": int.from_bytes(data, "big", signed=True)})
        elif opcode == codec.ACKNOWLEDGE:
            self._publish({"acknowledgement": "Observed, not correlated to physical arrival"})
        elif opcode == codec.CALIBRATE:
            self._publish({"calibration_observed": True})
        elif opcode == codec.SERIAL:
            self.session.serial = int.from_bytes(data, "big", signed=True)
            self._coordinator.save_app_state(self)
            self._publish({"serial": self.session.serial})

    async def _query(self, request: bytes, *, retries: int = 4, optional: bool = False) -> bytes:
        opcode = request[0]
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
                        await self.write_command(request)
                else:
                    await self.write_command(request)
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
            elif not future.cancelled():
                # Disconnect also cancels optional tasks before they can consume the error.
                future.exception()

    async def async_discover_capabilities(self) -> None:
        await self.start_notify()
        previous = self._stored_capabilities
        async with asyncio.timeout(4):
            body = await self._query(codec.query(codec.QUERY_CAPABILITIES))
        if len(body) != 5 or body[0] != 2:
            raise ValueError("Invalid capability record")
        self._coordinator.remember_fsm_relax_capabilities(body)
        loaded = self._coordinator.hass.config_entries.async_get_entry(
            self._coordinator.entry.entry_id
        )
        # Initial setup builds its platforms from this discovery; loaded entries need reload.
        if previous != body and (
            previous is not None
            or (loaded is not None and loaded.state is ConfigEntryState.LOADED)
        ):
            self._coordinator._pending_capability_reload = True
        if self._optional_task is None or self._optional_task.done():
            self._optional_task = self._coordinator.entry.async_create_background_task(
                self._coordinator.hass,
                self._optional_information(),
                "fsm_relax_optional_information",
            )

    async def _optional_information(self) -> None:
        try:
            for opcode in (codec.QUERY_HARDWARE, codec.QUERY_SOFTWARE):
                await asyncio.sleep(0.12)
                await self._query(codec.query(opcode), optional=True)
            self._publish({"optional_information": "Observed"})
        except TimeoutError, ConnectionError, ValueError, OSError, BleakError:
            self._publish({"optional_information": "Unavailable; capabilities remain usable"})

    def _default_hold_ms(self) -> int:
        return max(1, self._coordinator.motor_pulse_count) * self._tick_ms

    async def _cleanup(self, burst: Burst) -> None:
        body = codec.release(burst.opcode, self.setup.reversals)

        async def release() -> None:
            loop = asyncio.get_running_loop()
            started = loop.time()
            event = asyncio.Event()
            failure: Exception | None = None
            for index in range(burst.frames):
                await asyncio.sleep(
                    max(0, started + (index + 1) * self._tick_ms / 1000 - loop.time())
                )
                try:
                    await self.write_command(body, cancel_event=event)
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
        tick = self._tick_ms
        try:
            while index * tick <= duration_ms:
                await asyncio.sleep(max(0, start + index * tick / 1000 - loop.time()))
                if event.is_set():
                    break
                await self.write_command(codec.flagged(opcode, self.setup.reversals))
                index += 1
        finally:
            await self._cleanup(self.profile.stop)

    async def stop_all(self) -> None:
        await self._cleanup(self.profile.stop)

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
        self._parser.clear()
        self._publish({"memory_quarantined": True})

    def validate_memory_recall(self, memory_num: int) -> None:
        """Check local targets before fan-out, without connecting an offline bed."""
        if type(memory_num) is not int:
            raise ValueError("Selected memory slot is unavailable")
        super().validate_memory_recall(memory_num)
        positions = self.session.slots.get(memory_num)
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
                    body = await self._query(codec.ask_position(index + 1), retries=1)
                    positions[index] = int.from_bytes(body[1:], "big", signed=True)
                await self._save_slot(memory_num, positions)
            except BaseException:
                self._quarantine()
                raise

    async def _save_slot(self, slot: int, positions: dict[int, int]) -> None:
        """Report a saved memory only once it is durable; a failed write changes nothing."""
        validated = validate_positions(positions)
        async with self.session.persist_lock:
            candidate = {**self.session.slots, slot: validated}
            await self._coordinator.async_write_app_state(
                self, self.session.persisted(slots=candidate)
            )
            self.session.slots = candidate
        # Pick up a serial received while the write was in flight.
        self._coordinator.save_app_state(self)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        if type(hold_ms) is not int or not 1 <= hold_ms <= 120000:
            raise ValueError("Explicit hold must be 1..120000 ms")
        async with self._memory_lock:
            self._validate_memory(slot)
            self.validate_memory_recall(slot)
            positions = self.session.slots.get(slot)
            assert positions is not None
            loop = asyncio.get_running_loop()
            start = loop.time()
            event = self._coordinator.cancel_command
            try:
                tick = 1
                for index in range(self.key_count // 2):
                    if index not in positions:
                        continue
                    await asyncio.sleep(
                        max(0, start + tick * self.profile.recall_ms / 1000 - loop.time())
                    )
                    if event.is_set():
                        self._quarantine()
                        break
                    await self.write_command(codec.set_position(index + 1, positions[index]))
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
                assert self.profile.recall_release is not None
                try:
                    await self._cleanup(self.profile.recall_release)
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
        await self.write_command(codec.flagged(codec.CALIBRATE, self.setup.reversals))

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


async def build_controller(ctx: BuildContext) -> FsmRelaxController:
    """Build the controller from the stored setup, options taking precedence."""
    from ...app_session import app_session
    from .state import FsmRelaxSession, validate_names

    coordinator = ctx.coordinator
    data = {**ctx.data, **coordinator.entry.options}
    reversals = tuple(data.get(key, False) for key in CONF_REVERSE_MOTORS)
    setup = FsmRelaxSetup(
        data.get(CONF_PRODUCT_TYPE, "chair"),
        data.get(CONF_HAS_LIGHT, False),
        data.get(CONF_HAS_MASSAGE, False),
        (reversals[0], reversals[1], reversals[2], reversals[3]),
    )
    return FsmRelaxController(
        coordinator,
        setup=setup,
        session=app_session(coordinator.hass, coordinator.address, ("fsm_relax",), FsmRelaxSession),
        names=validate_names(data.get(CONF_FSM_RELAX_MEMORY_NAMES, [""] * 8)),
    )
