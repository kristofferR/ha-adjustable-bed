"""Explicit com.limoss.limossremote 7.1.8 app profile, independent of legacy."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..const import LIMOSS_CHAR_UUID, LIMOSS_SERVICE_UUID
from ..limoss_remote_state import LimossRemoteMemoryStore
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)
from .limoss_remote_protocol import (
    APP_SEQUENCE,
    HELD_COMMANDS,
    LAYOUTS,
    THEMES,
    LimossRemoteCapabilities,
    LimossRemoteParser,
    LimossRemoteSequence,
    Product,
    format_command,
    integer,
    version_string,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


def validate_limoss_remote_profile(
    product: Product | None,
    underbed_light: bool,
    massage: bool,
    reverse_motors: tuple[bool, bool, bool, bool],
    theme: str | None,
) -> None:
    """Validate selected local settings without any BLE or model inference."""
    if product not in (None, "bed", "chair"):
        raise ValueError("Select bed or chair")
    if type(underbed_light) is not bool or type(massage) is not bool:
        raise ValueError("Local feature selections must be booleans")
    if (
        not isinstance(reverse_motors, tuple)
        or len(reverse_motors) != 4
        or any(type(value) is not bool for value in reverse_motors)
    ):
        raise ValueError("Select exactly four reversal booleans")
    if theme is not None and theme not in THEMES:
        raise ValueError("Select a shipped app theme")


def _characteristic(client: BleakClient) -> BleakGATTCharacteristic:
    """The app's first exact service, then first exact member characteristic."""
    service = next(
        (item for item in client.services if item.uuid.lower() == LIMOSS_SERVICE_UUID), None
    )
    if service is None:
        raise ValueError("Limoss Remote service FFE0 is absent")
    char = next(
        (item for item in service.characteristics if item.uuid.lower() == LIMOSS_CHAR_UUID), None
    )
    if char is None:
        raise ValueError("Selected FFE0 service has no FFE1 characteristic")
    properties = set(char.properties)
    if "notify" not in properties or not properties.intersection(
        ("write", "write-without-response")
    ):
        raise ValueError("Selected FFE1 needs notify and a usable write property")
    return char


def _action(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        if (
            isinstance(controller, LimossRemoteController)
            or isinstance(controller, SideBoundController)
            and isinstance(controller._controller, LimossRemoteController)
        ):
            await controller.execute_app_action(action)
        else:
            raise TypeError("Requires the explicit Limoss Remote profile")

    return invoke


async def apply_limoss_remote_features(
    controller: BedController | SideBoundController,
    light: bool,
    massage: bool,
    *,
    persist: bool = True,
) -> None:
    """Use the live, possibly side-bound controller for an options transaction."""
    if isinstance(controller, LimossRemoteController) or (
        isinstance(controller, SideBoundController)
        and isinstance(controller._controller, LimossRemoteController)
    ):
        await controller.set_optional_features(light, massage, persist=persist)
        return
    raise ValueError("Requires the current Limoss Remote profile")


class LimossRemoteController(BedController):
    """Native rendered controls and local eight-slot position capture/recall."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        product: Product | None = None,
        underbed_light: bool = False,
        massage: bool = False,
        reverse_motors: tuple[bool, bool, bool, bool] = (False, False, False, False),
        theme: str | None = None,
        cached_capabilities: LimossRemoteCapabilities | None = None,
        memories: LimossRemoteMemoryStore,
        sequence: LimossRemoteSequence | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator)
        validate_limoss_remote_profile(product, underbed_light, massage, reverse_motors, theme)
        if not isinstance(memories, LimossRemoteMemoryStore):
            raise TypeError("A persistent per-target memory store is required")
        self.product_selection: Product | None = product
        self.underbed_light, self.massage = underbed_light, massage
        self.reverse_motors, self.theme = reverse_motors, theme
        self.capabilities = cached_capabilities
        self.memories = memories
        self.sequence = sequence if sequence is not None else APP_SEQUENCE
        self._metadata = dict(metadata or {})
        if any(
            key not in ("hardware_version", "software_version", "serial")
            or not isinstance(value, str)
            for key, value in self._metadata.items()
        ):
            raise ValueError("Cached metadata contains invalid diagnostic fields")
        self._parser = LimossRemoteParser()
        self._notify_client: BleakClient | None = None
        self._notify_char: BleakGATTCharacteristic | None = None
        self._notify_generation = 0
        self._request_reply: tuple[int, asyncio.Future[bytes]] | None = None
        self._request_active: asyncio.Future[bytes] | None = None
        self._progress: dict[str, object] | None = None
        self._last_write_started = float("-inf")
        self._publish_metadata()

    @property
    def control_characteristic_uuid(self) -> str:
        return LIMOSS_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple:
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return False  # The app exposes a held lamp action, no measured ON/OFF.

    @property
    def supports_massage(self) -> bool:
        return False  # Exact +/- actions are custom controls, not intensity state.

    @property
    def layout(self) -> str | None:
        if self.capabilities is None:
            return None
        return self.capabilities.layout(self.product_selection, self.underbed_light, self.massage)

    @property
    def visible_opcodes(self) -> tuple[int, ...]:
        layout = self.layout
        return tuple(opcode for opcode in LAYOUTS[layout] if opcode is not None) if layout else ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            action for action, opcode in HELD_COMMANDS.items() if opcode in self.visible_opcodes
        )

    @property
    def memory_slot_count(self) -> int:
        if self.capabilities is None or self.capabilities.memory_count > 8:
            return 0
        return self.capabilities.memory_count

    @property
    def supports_memory_programming(self) -> bool:
        if not self.memory_slot_count or self.capabilities is None:
            return False
        return 1 <= self.capabilities.effective_motor_count(self.product_selection) <= 4

    @property
    def supports_memory_presets(self) -> bool:
        return self.supports_memory_programming

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return tuple(
            self.memories.slots[slot].name if slot in self.memories.slots else None
            for slot in range(1, self.memory_slot_count + 1)
        )

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self.capabilities is not None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=f"motor_{index}",
                translation_key=f"limoss_remote_motor_{index}",
                open_fn=_action(f"motor_{index}_up"),
                close_fn=_action(f"motor_{index}_down"),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
            )
            for index in range(1, 5)
            if f"motor_{index}_up" in self.held_control_options
            and f"motor_{index}_down" in self.held_control_options
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = [
            (action, action.replace("_", " ").title()) for action in self.held_control_options
        ]
        actions += [("refresh_info", "Refresh App Information")]
        if self.underbed_light:
            actions += [("light_off", "Light Off")]
        if self.massage:
            actions += [("massage_off", "Massage Off")]
        return tuple(
            ControllerButtonSpec(f"limoss_remote_{action}", name, _action(action))
            for action, name in actions
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = (
            "hardware_version",
            "software_version",
            "serial",
            "key_count",
            "motor_count",
            "configuration",
            "memory_slots",
            "reported_entry",
            "calibration_result",
        )
        fields += tuple(f"motor_{index}_position_raw" for index in range(1, 5))
        return tuple(
            ControllerStateSensorSpec(
                f"limoss_remote_{field}",
                f"limoss_remote_{field}",
                f"limoss_remote_{field}",
                "mdi:information-outline",
            )
            for field in fields
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": "com.limoss.limossremote 7.1.8",
            "selected_product": self.product_selection,
            "capabilities": asdict(self.capabilities) if self.capabilities else None,
            "layout": self.layout,
            "visible_opcodes": self.visible_opcodes,
            "reversal": self.reverse_motors,
            "theme": self.theme,
            "local_features": {"light": self.underbed_light, "massage": self.massage},
            "metadata": dict(self._metadata),
            "memories": self.memories.serialize(),
            "sequence": self.sequence.value,
            "position_units": "opaque_signed_int32",
            "hardware_validation": "unverified",
        }

    async def async_discover_capabilities(self) -> None:
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected")
        _characteristic(self.client)

    def _construct(self, payload: bytes, event: asyncio.Event | None = None) -> bytes:
        event = event if event is not None else self._coordinator.cancel_command
        if event.is_set():
            raise asyncio.CancelledError
        if len(payload) != 5:
            raise ValueError("Logical command needs five bytes")
        return format_command(payload, self.sequence.take())

    async def _write(
        self, payload: bytes, event: asyncio.Event | None = None, *,
        reply: tuple[int, asyncio.Future[bytes]] | None = None,
    ) -> None:
        await self._send(self._construct(payload, event), event, reply=reply)

    async def _send(
        self, packet: bytes, event: asyncio.Event | None = None, *,
        reply: tuple[int, asyncio.Future[bytes]] | None = None,
    ) -> None:
        event = event if event is not None else self._coordinator.cancel_command
        async with self._ble_lock:
            wait = self._last_write_started + 0.08 - asyncio.get_running_loop().time()
            if wait > 0:
                await self._sleep(wait, event)
            if event.is_set():
                raise asyncio.CancelledError
            client = self.client
            if client is None or not client.is_connected:
                raise ConnectionError("Not connected")
            char = _characteristic(client)
            response = "write" in char.properties
            self._last_write_started = asyncio.get_running_loop().time()
            self._coordinator.record_command_trace(
                payload={"hex": packet.hex(), "length": len(packet)},
                characteristic_uuid=char.uuid,
                characteristic_handle=char.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=80,
                command_origin="limoss_remote",
                controller_class=type(self).__name__,
            )
            # Host deadline prevents a stalled ATT call retaining the command lane.
            async with asyncio.timeout(2):
                # Pre-query frames cannot satisfy a request waiting for the lane/pacing.
                # After emission, same-opcode replies have no native correlation ID.
                if reply is not None:
                    if reply[1].done():
                        reply[1].result()  # Teardown can fail a reserved, not-yet-emitted query.
                    self._request_reply = reply
                await client.write_gatt_char(char, packet, response=response)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 80,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        integer(repeat_count, 1, 1000, "Repeat count")
        integer(repeat_delay_ms, 0, 60000, "Repeat delay")
        for index in range(repeat_count):
            if index:
                await self._sleep(repeat_delay_ms / 1000, cancel_event)
            await self._write(command, cancel_event)

    async def _sleep(self, seconds: float, event: asyncio.Event | None = None) -> None:
        event = event if event is not None else self._coordinator.cancel_command
        if event.is_set():
            raise asyncio.CancelledError
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0, seconds))
        except TimeoutError:
            return
        raise asyncio.CancelledError

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if (
            self._notify_client is self.client
            and self._notify_client is not None
            and self._notify_client.is_connected
            and self._notify_char is not None
        ):
            return
        await self.stop_notify()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected")
        char = _characteristic(client)
        self._parser.clear()
        self._notify_client, self._notify_char = client, char
        generation = self._notify_generation

        def notification(sender: BleakGATTCharacteristic, raw: bytearray) -> None:
            if (
                self._notify_generation != generation
                or self.client is not client
                or not client.is_connected
                or self._notify_client is not client
                or self._notify_char is not char
                or sender.handle != char.handle
                or sender.uuid.lower() != LIMOSS_CHAR_UUID
            ):
                return
            try:
                if _characteristic(client) is not char:
                    return
            except ValueError:
                return
            self._notification(sender, raw)

        try:
            await client.start_notify(char, notification)
            await self.refresh_device_info()
        except BaseException:
            cleanup = asyncio.create_task(self.stop_notify())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            try:
                cleanup.result()
            except Exception:
                _LOGGER.debug("Notification cleanup failed after startup error", exc_info=True)
            raise

    def _invalidate_notification_channel(
        self,
    ) -> tuple[BleakClient | None, BleakGATTCharacteristic | None]:
        client, char = self._notify_client, self._notify_char
        self._notify_generation += 1
        self._notify_client, self._notify_char = None, None
        self._parser.clear()
        pending = self._request_active or (self._request_reply[1] if self._request_reply else None)
        if pending is not None and not pending.done():
            pending.set_exception(
                ConnectionError("App notification channel stopped")
            )
        return client, char

    def on_disconnect(self) -> None:
        self._invalidate_notification_channel()

    async def stop_notify(self) -> None:
        client, char = self._invalidate_notification_channel()
        if client is not None and char is not None and client.is_connected:
            async with asyncio.timeout(2):
                await client.stop_notify(char)

    def _notification(self, sender: BleakGATTCharacteristic, raw: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(raw))
        for payload in self._parser.feed(bytes(raw)):
            opcode, parameters = payload[0], payload[1:]
            delta: dict[str, object] = {}
            if opcode in (0, 1):
                field = "hardware_version" if opcode == 0 else "software_version"
                value = version_string(parameters)
                self._metadata[field] = value
                delta["metadata"] = dict(self._metadata)
                self.forward_controller_state_update(f"limoss_remote_{field}", value)
            elif opcode == 2:
                self.capabilities = LimossRemoteCapabilities.from_parameters(parameters)
                delta["capabilities"] = asdict(self.capabilities)
                self.forward_controller_state_updates(
                    {
                        "limoss_remote_key_count": self.capabilities.key_count,
                        "limoss_remote_motor_count": self.capabilities.system & 15,
                        "limoss_remote_configuration": self.capabilities.configuration,
                        "limoss_remote_memory_slots": self.capabilities.memory_count,
                        "limoss_remote_reported_entry": self.capabilities.reported_product
                        or "unknown",
                    }
                )
            elif opcode == 5:
                self.forward_controller_state_update(
                    "limoss_remote_calibration_result", "reply_received"
                )
            elif opcode == 6:
                value = str(int.from_bytes(parameters, "big", signed=True))
                self._metadata["serial"] = value
                delta["metadata"] = dict(self._metadata)
                self.forward_controller_state_update("limoss_remote_serial", value)
            elif opcode in (0x10, 0x20, 0x30, 0x40):
                self.forward_controller_state_update(
                    f"limoss_remote_motor_{opcode // 16}_position_raw",
                    int.from_bytes(parameters, "big", signed=True),
                )
            if delta:
                if self._progress is not None:
                    self._progress.update(delta)
                else:
                    self._coordinator.remember_limoss_remote_data(delta)
            if self._request_reply is not None:
                expected, future = self._request_reply
                if expected == opcode and not future.done():
                    future.set_result(parameters)

    def _publish_metadata(self) -> None:
        for field, value in self._metadata.items():
            self.forward_controller_state_update(f"limoss_remote_{field}", value)

    async def _reply(self, future: asyncio.Future[bytes], timeout: float) -> bytes:
        event_task = asyncio.create_task(self._coordinator.cancel_command.wait())
        try:
            done, _ = await asyncio.wait(
                (future, event_task), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if event_task in done:
                raise asyncio.CancelledError
            if future in done:
                return future.result()
            raise TimeoutError("No matching app reply")
        finally:
            event_task.cancel()
            await asyncio.gather(event_task, return_exceptions=True)

    async def _request(
        self, opcode: int, payload: bytes, *, retry_capabilities: bool = False
    ) -> bytes:
        if self._request_active or self._request_reply is not None:
            raise RuntimeError("Another app information transaction is active")
        future = asyncio.get_running_loop().create_future()
        self._request_active = future
        try:
            while True:
                self._request_reply = None
                await self._write(payload, reply=(opcode, future))
                try:
                    return await self._reply(future, 1 if retry_capabilities else 10)
                except TimeoutError:
                    if not retry_capabilities:
                        raise
        finally:
            self._request_reply = None
            self._request_active = None
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Consume a teardown error even if the preceding write failed.

    async def refresh_device_info(self) -> None:
        self._progress = {}
        try:
            async with asyncio.timeout(10):
                await self._request(2, b"\x02\0\0\0\x03", retry_capabilities=True)
                await self._request(0, b"\0\0\0\0\x03")
                await self._request(1, b"\x01\0\0\0\x03")
        finally:
            completed, self._progress = self._progress, None
            if completed:
                self._coordinator.remember_limoss_remote_data(completed)

    def _slot(self, slot: int) -> int:
        integer(slot, 1, 8, "Memory slot")
        if slot > self.memory_slot_count:
            raise ValueError("This memory slot is unavailable")
        return slot

    async def program_memory(self, memory_num: int) -> None:
        slot = self._slot(memory_num)
        if not self.supports_memory_programming:
            raise ValueError("Saving requires one to four reported motors")
        assert self.capabilities is not None
        count = self.capabilities.effective_motor_count(self.product_selection)
        positions: list[tuple[int, int]] = []
        async with asyncio.timeout(10):
            for motor in range(count):
                opcode = 0x10 * (motor + 1)
                raw = await self._request(opcode, bytes((opcode, 0, 0, 0, 0)))
                positions.append((motor, int.from_bytes(raw, "big", signed=True)))
        self.memories.save(slot, tuple(positions))

    async def rename_memory(self, memory_num: int, name: str) -> None:
        self._slot(memory_num)
        if not isinstance(name, str):
            raise ValueError("Memory name must be a string")
        self.memories.rename(memory_num, name)
        self.forward_controller_state_update("limoss_remote_memory_names", self.memory_slot_names)

    async def _release(self, *, calibration: bool = False) -> None:
        payload = bytes((3, 0, 0, 0, 0)) if calibration else bytes((0xFF, *self.reverse_motors))

        async def cleanup() -> None:
            error: Exception | None = None
            packets = tuple(self._construct(payload, asyncio.Event()) for _ in range(5))
            for packet in packets:
                try:
                    async with asyncio.timeout(2):
                        await self._send(packet, asyncio.Event())
                except Exception as failure:
                    error = error or failure
            if error is not None:
                raise error

        task = asyncio.create_task(cleanup())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _cleanup(self, *, calibration: bool = False) -> None:
        original = sys.exception()
        try:
            await self._release(calibration=calibration)
        except Exception:
            if original is None:
                raise
            _LOGGER.debug("Release failed after an earlier command error", exc_info=True)

    async def stop_all(self) -> None:
        await self._release()

    async def _held(
        self,
        payloads: tuple[bytes, ...],
        duration_ms: int,
        *,
        interval: float,
        initial_delay: float = 0,
        calibration: bool = False,
    ) -> None:
        integer(duration_ms, 1, 60000, "Hold duration")
        if self._coordinator.cancel_command.is_set():
            return
        timer = asyncio.timeout(duration_ms / 1000)
        attempted = False
        try:
            async with timer:
                if initial_delay:
                    await self._sleep(initial_delay)
                while True:
                    started = asyncio.get_running_loop().time()
                    packets = tuple(self._construct(payload) for payload in payloads)
                    attempted = True
                    for packet in packets:
                        await self._send(packet)
                    await self._sleep(
                        max(0, started + interval - asyncio.get_running_loop().time())
                    )
        except TimeoutError:
            if not timer.expired():
                raise
        finally:
            if attempted:
                await self._cleanup(calibration=calibration)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is not rendered by the current app layout")
        await self._held(
            (bytes((HELD_COMMANDS[control], *self.reverse_motors)),),
            duration_ms,
            interval=0.08,
            initial_delay=0.08,
        )

    async def preset_memory(self, memory_num: int) -> None:
        await self.hold_memory(memory_num, 1000)

    async def hold_memory(self, memory_num: int, duration_ms: int) -> None:
        self.validate_memory_recall(memory_num)
        memory = self.memories.slots[memory_num]
        assert self.capabilities is not None
        count = self.capabilities.effective_motor_count(self.product_selection)
        # The source recalls present rows; retained sparse memories are valid.
        payloads = tuple(
            bytes((0x11 + motor * 16,)) + value.to_bytes(4, "big", signed=True)
            for motor, value in memory.positions
            if motor < count
        )
        await self._held(payloads, duration_ms, interval=0.3)

    def validate_memory_recall(self, memory_num: int) -> None:
        slot = self._slot(memory_num)
        if not self.supports_memory_presets:
            raise ValueError("Recalling requires one to four reported motors")
        memory = self.memories.slots.get(slot)
        if memory is None or not any(motor == 0 for motor, _ in memory.positions):
            raise ValueError("Save this memory before recall")
        assert self.capabilities is not None
        count = self.capabilities.effective_motor_count(self.product_selection)
        if any(motor >= count for motor, _ in memory.positions):
            raise ValueError("Stored memory belongs to a different reported motor layout")

    async def hold_calibration(self, duration_ms: int, *, confirmed: bool) -> None:
        if confirmed is not True or self.memory_slot_count == 0:
            raise ValueError("Calibration needs explicit confirmation and a memory-capable profile")
        await self._held(
            (bytes((5, *self.reverse_motors)),), duration_ms, interval=0.1, calibration=True
        )

    async def _feature_off(self, opcode: int) -> None:
        packets = tuple(self._construct(bytes((opcode, 0, 0, 0, 0))) for _ in range(10))
        for packet in packets:
            await self._send(packet)

    async def set_optional_features(
        self, underbed_light: bool, massage: bool, *, persist: bool = True
    ) -> None:
        validate_limoss_remote_profile(
            self.product_selection, underbed_light, massage, self.reverse_motors, self.theme
        )
        if self.underbed_light and not underbed_light:
            await self._feature_off(0x71)
        if self.massage and not massage:
            await self._feature_off(0x66)
        self.underbed_light, self.massage = underbed_light, massage
        if persist:
            self._coordinator.remember_limoss_remote_features(underbed_light, massage)

    async def execute_app_action(self, action: str) -> None:
        if action in self.held_control_options:
            await self.hold_control(action, 1000)
        elif action == "refresh_info":
            await self.refresh_device_info()
        elif action == "light_off" and self.underbed_light:
            await self._feature_off(0x71)
        elif action == "massage_off" and self.massage:
            await self._feature_off(0x66)
        else:
            raise ValueError("Action is unavailable in this profile")

    async def read_positions(self, motor_count: int = 2) -> None:
        # Save gates matching replies at query emission; there is no idle telemetry poll.
        return

    async def preset_flat(self) -> None:
        raise ValueError("There is no flat preset in this app")

    async def move_head_up(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_head_down(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_back_up(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_back_down(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_legs_up(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_legs_down(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_feet_up(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_feet_down(self) -> None:
        raise ValueError("Use the literal app channel controls")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_stop(self) -> None:
        await self.stop_all()
