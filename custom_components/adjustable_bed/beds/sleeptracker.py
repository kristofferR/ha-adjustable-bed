"""Authenticated Sleeptracker processor control, separate from UART bases."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
from typing import TYPE_CHECKING

from .. import sleeptracker_protocol as p
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

REPLY_TIMEOUT = 60.0


def _controller(controller: BedController) -> SleeptrackerController:
    if not isinstance(controller, SleeptrackerController):
        raise TypeError("Sleeptracker control requires the Sleeptracker processor")
    return controller


def _request_button(key: str, name: str, request: p.Request) -> ControllerButtonSpec:
    async def press(controller: BedController) -> None:
        await controller.async_execute_sleeptracker_request(request)

    return ControllerButtonSpec(key, name, press, translation_key=key)


def _axis_command(axis: p.Axis, action: str) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        selected = _controller(controller)
        if action == "stop":
            await selected._release(axis)
        else:
            await selected._move(axis, action)

    return execute


class SleeptrackerController(BedController):
    """One physical processor, one serialized request/reply session."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        model: str,
        unit_number: int = 0,
        snapshot_side: int = 0,
        restricted: bool = False,
        processor_type: int = 0,
        manufacturer_data: Mapping[int, bytes] | None = None,
        foundation: str = "Unspecified",
    ) -> None:
        super().__init__(coordinator)
        if (
            model not in p.MODELS
            or type(unit_number) is not int
            or not -(2**31) <= unit_number < 2**31
            or (restricted and unit_number != 0)
            or foundation not in p.FOUNDATIONS
            or type(snapshot_side) is not int
            or snapshot_side not in range(4)
            or type(processor_type) is not int
            or not -(2**31) <= processor_type < 2**31
            or type(restricted) is not bool
        ):
            raise ValueError("Select a Sleeptracker app layout and processor unit/snapshot side")
        self._model = p.MODELS[model]
        self._unit = unit_number
        self._snapshot_side = snapshot_side
        self._restricted = restricted
        self._processor_type = processor_type
        self._foundation = foundation
        self._characteristics: dict[str, BleakGATTCharacteristic] = {}
        self._subscribed: list[BleakGATTCharacteristic] = []
        self._session_client: BleakClient | None = None
        self._generation = 0
        self._token: str | None = None
        self._ready = False
        self._tainted = False
        self._transaction_lock = asyncio.Lock()
        self._pending: dict[str, asyncio.Future[bytes]] = {}
        self._buffers: dict[str, p.Reassembler] = {}
        self._reads: dict[str, asyncio.Task[None]] = {}
        self._state: dict[str, p.Json] = {"wave_frequency": 52, "wave_minutes": 30}
        self._advertisement_metadata = p.manufacturer_metadata(
            manufacturer_data or {}, coordinator.address
        )
        self._metadata: dict[str, p.Json] = dict(self._advertisement_metadata)

    @property
    def control_characteristic_uuid(self) -> str:
        return p.CONTROL_UUID

    @property
    def supports_single_address_pairing(self) -> bool:
        # The artifact does not prove how unitNumber maps to physical halves.
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_sleeptracker_controls(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "transport": "sleeptracker_framed_json",
            "layout_id": self._model.id,
            "unit_number": self._unit,
            "snapshot_side": self._snapshot_side,
            "foundation": self._foundation,
            "restricted": self._restricted,
            "session_ready": self._ready,
            "authenticated": self._token is not None,
            **self._metadata,
        }

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object]:
        return {"hex": "**REDACTED**", "length": len(command)}

    def _publish(self) -> None:
        for side in ("left", "right"):
            level = self._state.get(side + "_level")
            heating = self._state.get(side + "_heating")
            self._state[side + "_mode"] = (
                ("off" if level == 0 else "heat" if heating else "cool")
                if level is not None and heating is not None
                else None
            )
            constant = self._state.get(side + "_commanded_constant")
            self._state[side + "_curve"] = (
                ("constant" if constant else "curve") if constant is not None else None
            )
        updates: dict[str, p.Json] = {
            "sleeptracker_" + key: value for key, value in self._state.items()
        }
        # HA select options are strings; retain the numeric builder setting locally.
        updates["sleeptracker_wave_frequency"] = str(self._state["wave_frequency"])
        self.forward_controller_state_updates(updates)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Sleeptracker processor is disconnected")
        if client is self._session_client:
            return
        service = next(
            (
                found
                for uuid in p.SERVICES
                if (found := client.services.get_service(uuid)) is not None
            ),
            None,
        )
        if service is None:
            raise ConnectionError(
                "Sleeptracker processor service is absent; select its processor, not a UART base"
            )
        characteristics = {char.uuid.lower(): char for char in service.characteristics}
        required = (
            (p.HELLO_UUID, p.CONTROL_UUID)
            if self._restricted
            else (p.HELLO_UUID, p.AUTH_UUID, p.CONTROL_UUID)
        )
        if any(uuid not in characteristics for uuid in required):
            raise ConnectionError("Selected service lacks the Sleeptracker hello/auth/control path")
        self._session_client = client
        self._characteristics = characteristics
        self._generation += 1

    def _current(self) -> BleakClient:
        client = self.client
        if client is None or client is not self._session_client or not client.is_connected:
            raise ConnectionError("Sleeptracker session ended")
        return client

    def _accept(self, uuid: str, data: bytes) -> None:
        # Raw chunks can carry authentication challenges or tokens. Forward only
        # byte counts to capture callbacks, with no raw logging.
        if self._raw_notify_callback is not None:
            self._raw_notify_callback(uuid, bytes(len(data)))
        if uuid not in self._pending and (uuid != p.CONTROL_UUID or not self._ready):
            return
        buffer = self._buffers.setdefault(uuid, p.Reassembler())
        try:
            result = buffer.feed(data)
        except ValueError as err:
            if (future := self._pending.get(uuid)) is not None and not future.done():
                future.set_exception(err)
            return
        if result is not None:
            if (future := self._pending.get(uuid)) is not None and not future.done():
                future.set_result(result)
            elif uuid == p.CONTROL_UUID and self._ready:
                with suppress(ValueError):
                    self._update_status(p.json_object(result))
        elif uuid not in self._reads:
            generation = self._generation
            self._reads[uuid] = self._coordinator.hass.async_create_task(
                self._continue_read(uuid, generation), eager_start=False
            )

    async def _read(self, uuid: str) -> None:
        generation = self._generation
        async with self._ble_lock:
            if generation != self._generation:
                return
            client = self._current()
            data = await client.read_gatt_char(self._characteristics[uuid])
        if generation == self._generation and self.client is client and client.is_connected:
            self._accept(uuid, bytes(data))

    async def _continue_read(self, uuid: str, generation: int) -> None:
        try:
            async with asyncio.timeout(REPLY_TIMEOUT):
                while generation == self._generation and self._buffers[uuid].buffer is not None:
                    await self._read(uuid)
        except (Exception, asyncio.CancelledError) as err:
            future = self._pending.get(uuid) if generation == self._generation else None
            if future is not None and not future.done():
                future.set_exception(
                    ConnectionError("Sleeptracker continuation ended")
                    if isinstance(err, asyncio.CancelledError)
                    else err
                )
        finally:
            if generation == self._generation:
                self._reads.pop(uuid, None)

    async def _write(self, uuid: str, payload: bytes, *, fast: bool, cancel: asyncio.Event) -> None:
        char = self._characteristics[uuid]
        response = not (fast and "write-without-response" in char.properties)
        # ATT write payload is MTU - 3, with another two bytes for this header.
        limit = min(500, max(1, self._current().mtu_size - 5))
        if not response:
            limit = min(limit, max(1, char.max_write_without_response_size - 2))
        for frame in p.frames(payload, limit):
            if cancel.is_set():
                raise asyncio.CancelledError
            await self._write_gatt_with_retry(
                uuid, frame, cancel_event=cancel, response=response, characteristic=char
            )
            if cancel.is_set():
                raise asyncio.CancelledError

    async def _exchange(
        self,
        uuid: str,
        payload: bytes | None = None,
        *,
        fast: bool = False,
        cancel: asyncio.Event | None = None,
    ) -> dict[str, p.Json]:
        effective_cancel = cancel if cancel is not None else self._coordinator.cancel_command
        async with self._transaction_lock:
            self._current()
            if effective_cancel.is_set():
                raise asyncio.CancelledError
            future: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
            self._pending[uuid] = future
            self._buffers[uuid] = p.Reassembler()
            cancelled = asyncio.create_task(effective_cancel.wait())
            try:
                async with asyncio.timeout(REPLY_TIMEOUT):
                    if payload is None:
                        await self._read(uuid)
                    else:
                        await self._write(uuid, payload, fast=fast, cancel=effective_cancel)
                    done, _ = await asyncio.wait(
                        (future, cancelled), return_when=asyncio.FIRST_COMPLETED
                    )
                    if cancelled in done:
                        raise asyncio.CancelledError
                    return p.json_object(future.result())
            except BaseException:
                # A late reply has no request ID. Never reuse that session for
                # another command after cancellation, malformed data or timeout.
                self._tainted = True
                raise
            finally:
                cancelled.cancel()
                with suppress(asyncio.CancelledError):
                    await cancelled
                self._pending.pop(uuid, None)
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._ready and not self._tainted and self.client is self._session_client:
            self._notify_callback = callback
            return
        await self.async_discover_capabilities()
        client = self._current()
        generation = self._generation
        self._notify_callback = callback
        try:
            for uuid in (p.HELLO_UUID, p.AUTH_UUID, p.CONTROL_UUID):
                if (char := self._characteristics.get(uuid)) is None:
                    continue

                def receive(
                    sender: BleakGATTCharacteristic, data: bytearray, channel: str = uuid
                ) -> None:
                    if (
                        generation == self._generation
                        and self.client is client
                        and client.is_connected
                    ):
                        self._accept(channel, bytes(data))

                if "notify" in char.properties or "indicate" in char.properties:
                    await client.start_notify(char, receive)
                    self._subscribed.append(char)
            hello = await self._exchange(p.HELLO_UUID)
            self._parse_hello(hello)
            if not self._restricted:
                challenge = hello.get("authCode", "")
                if not isinstance(challenge, str):
                    raise ValueError("Sleeptracker auth challenge must be text")
                payload = await self._coordinator.hass.async_add_executor_job(
                    p.authentication, self._coordinator.address, challenge
                )
                auth = await self._exchange(p.AUTH_UUID, payload)
                details = p.child(auth, "details")
                token = details.get("token")
                if not isinstance(token, str) or not token or len(token.encode()) > 4096:
                    raise ConnectionError(
                        "Sleeptracker authentication did not return a usable token"
                    )
                self._token = token
            self._update_status(
                await self._exchange(
                    p.CONTROL_UUID, p.envelope(None, self._token, operation="motor-status")
                )
            )
            if p.FIRMWARE_UUID in self._characteristics:
                with suppress(Exception):
                    async with asyncio.timeout(REPLY_TIMEOUT), self._ble_lock:
                        firmware = bytes(
                            await client.read_gatt_char(self._characteristics[p.FIRMWARE_UUID])
                        ).decode(errors="replace")
                    self._metadata["firmware_revision"] = firmware[:128]
            self._current()
            self._ready = True
            self._publish()
        except BaseException:
            await self.stop_notify()
            if client.is_connected:
                await client.disconnect()
            raise

    def _parse_hello(self, hello: dict[str, p.Json]) -> None:
        # A whitelist prevents new firmware fields from leaking credentials.
        for key in (
            "FSPVersion",
            "Hardware",
            "SensorBoardFirmware",
            "product",
            "productModel",
            "productFeatures",
            "SystemType",
        ):
            if key in hello:
                self._metadata[key] = hello[key]
        capabilities = p.child(hello, "motorMeta").get("capabilities", [])
        if (
            isinstance(capabilities, list)
            and capabilities
            and isinstance(first := capabilities[0], dict)
        ):
            model = first.get("controllerModel")
            if isinstance(model, str):
                self._metadata["hello_controller_model"] = model
                self._metadata["hello_layout_alias"] = p.HELLO_MODELS.get(model)
        for side in ("left", "right"):
            sensor = p.child(hello, side + "Sensor")
            for key in ("motors_bitfield", "massagers_bitfield", "sample_range", "status"):
                if key in sensor:
                    self._metadata[side + "_sensor_" + key] = sensor[key]
        left = p.child(hello, "leftSensor")
        right = p.child(hello, "rightSensor")
        if left and right:
            left_connected = str(left.get("status", "")).lower() == "connected"
            right_connected = str(right.get("status", "")).lower() == "connected"
            special = str(hello.get("product", "")).lower() == "sleeptracker" or p.boolean(
                hello.get("FailsafeMode")
            )
            self._metadata["connected_sensor_count"] = int(left_connected) + int(right_connected)
            self._metadata["setup_connected_sensor_count"] = int(left_connected) + (
                int(right_connected) if not (special and not left_connected) else 0
            )
        self._state["layout"] = self._model.label
        self._state["metadata"] = dict(self._metadata)

    def _update_status(self, value: dict[str, p.Json]) -> None:
        # A result envelope may carry the motor status under details.
        details = p.child(value, "details")
        body = details if details else value
        running = p.wind_down_running(details)
        try:
            self._state = p.status(body, self._snapshot_side, self._state)
        except p.RemoteSnapshotError:
            if not self._model.premium or running is None:
                raise
            # Wind Down ignores later scalar entries. Preserve the last remote
            # and climate state when that independent consumer cannot parse them.
        if running is not None:
            self._state["wind_down_running"] = running
        invariants = p.child(body, "body").get("invariants", [])
        if isinstance(invariants, list):
            for item in invariants:
                if isinstance(item, dict) and item.get("type") == "controller":
                    self._metadata["reported_controller_model"] = item.get("model", "NONE")
                    self._metadata["reported_controller_version"] = item.get("version")
                    thresholds = {18: 66, 19: 83, 20: 97, 21: 113}
                    version = p.integer(item.get("version"))
                    required = thresholds.get(self._model.id, 0)
                    self._metadata["app_firmware_threshold"] = required
                    self._metadata["app_firmware_below_threshold"] = 0 < version < required
                    self._metadata["layout_matches_report"] = (
                        item.get("model", "NONE") == self._model.controller_model
                    )
                    break
        self._state["metadata"] = dict(self._metadata)
        self._publish()

    def on_disconnect(self) -> None:
        self._generation += 1
        self._ready = False
        self._tainted = False
        self._token = None
        self._session_client = None
        self._subscribed.clear()
        self._characteristics.clear()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Sleeptracker disconnected"))
        for task in self._reads.values():
            task.cancel()
        self._reads.clear()
        self._buffers.clear()
        self._state = {
            **dict.fromkeys(self._state),
            "wave_frequency": self._state.get("wave_frequency", 52),
            "wave_minutes": self._state.get("wave_minutes", 30),
        }
        self._metadata = dict(self._advertisement_metadata)
        self._publish()

    async def stop_notify(self) -> None:
        client = self._session_client
        subscribed = tuple(self._subscribed)
        self.on_disconnect()
        if client is not None and client.is_connected:
            for char in subscribed:
                with suppress(Exception):
                    await client.stop_notify(char)

    async def _release(self, axis: p.Axis | None = None, *, massage_only: bool = False) -> None:
        if self._session_client is None or self.client is None or not self.client.is_connected:
            return
        payload = (
            p.movement(axis, "stop", self._unit, self._token)
            if axis is not None
            else p.stop(self._unit, self._token, all_features=not massage_only)
        )
        try:
            if self._tainted:
                # A cancelled request may still reply. Deliver cleanup without
                # accepting its reply, then end the ambiguous session.
                async with self._transaction_lock:
                    await self._write(p.CONTROL_UUID, payload, fast=True, cancel=asyncio.Event())
            else:
                reply = await self._exchange(
                    p.CONTROL_UUID, payload, fast=True, cancel=asyncio.Event()
                )
                self._update_status(reply)
        except BaseException:
            self._tainted = True
            raise
        finally:
            if self._tainted and self.client is not None:
                await self.client.disconnect()

    async def _control(
        self, payload: bytes, *, fast: bool = False, cancel: asyncio.Event | None = None
    ) -> None:
        if not self._ready or self._tainted:
            raise ConnectionError("Sleeptracker session is not ready")
        try:
            result = await self._exchange(p.CONTROL_UUID, payload, fast=fast, cancel=cancel)
            self._update_status(result)
        except BaseException:
            self._tainted = True
            await self._release()
            raise

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        # Public BedController entry point; each request is one transaction.
        if cancel_event is not None and cancel_event.is_set():
            return
        await self._control(command, cancel=cancel_event)

    async def read_positions(self, motor_count: int = 2) -> None:
        await self._control(p.envelope(None, self._token, operation="motor-status"))

    async def async_refresh_diagnostics(self) -> None:
        await self.read_positions()

    async def _move(self, axis: p.Axis, action: str) -> None:
        if axis == "lumbar" and not self._model.lumbar:
            raise ValueError("Generic Sleeptracker layout has no lumbar control")
        if not self._ready:
            raise ConnectionError("Sleeptracker session is not ready")
        count, planning_delay = self.motor_pulse_settings()
        # HA bounds a button/timed hold; this is not a BLE refresh interval.
        deadline = asyncio.get_running_loop().time() + count * planning_delay / 1000
        hold = asyncio.timeout_at(deadline)
        try:
            async with hold:
                while not self._coordinator.cancel_command.is_set():
                    self._update_status(
                        await self._exchange(
                            p.CONTROL_UUID,
                            p.movement(axis, action, self._unit, self._token),
                            fast=True,
                        )
                    )
                    if asyncio.get_running_loop().time() >= deadline:
                        break
        except TimeoutError:
            if not hold.expired():
                self._tainted = True
                raise
        except BaseException:
            self._tainted = True
            raise
        finally:
            await self._release(axis)

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def has_lumbar_support(self) -> bool:
        return self._model.lumbar

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes: tuple[p.Axis, ...] = (
            ("head", "foot", "lumbar") if self._model.lumbar else ("head", "foot")
        )
        return tuple(
            MotorControlSpec(
                "back" if axis == "head" else "legs" if axis == "foot" else axis,
                "back" if axis == "head" else "legs" if axis == "foot" else axis,
                _axis_command(axis, "up"),
                _axis_command(axis, "down"),
                _axis_command(axis, "stop"),
            )
            for axis in axes
        )

    async def move_head_up(self) -> None:
        await self._move("head", "up")

    async def move_head_down(self) -> None:
        await self._move("head", "down")

    async def move_head_stop(self) -> None:
        await self._release("head")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_back_stop = move_head_stop

    async def move_legs_up(self) -> None:
        await self._move("foot", "up")

    async def move_legs_down(self) -> None:
        await self._move("foot", "down")

    async def move_legs_stop(self) -> None:
        await self._release("foot")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_feet_stop = move_legs_stop

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", "up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", "down")

    async def move_lumbar_stop(self) -> None:
        await self._release("lumbar")

    async def stop_all(self) -> None:
        await self._release()

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return self._model.extra_presets

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2 if self._model.extra_presets and self._model.id != 0 else 1

    @property
    def supports_memory_programming(self) -> bool:
        return self._processor_type not in (5, 6, 7)

    async def preset_flat(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("preset"))

    async def preset_zero_g(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("preset", preset="zero_g"))

    async def preset_anti_snore(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("preset", preset="anti_snore"))

    async def preset_tv(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("preset", preset="tv_pc"))

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.async_execute_sleeptracker_request(
            p.Request("preset", preset="user_favorite" if memory_num == 1 else "favorite_2")
        )

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.async_execute_sleeptracker_request(
            p.Request(
                "preset", preset="user_favorite" if memory_num == 1 else "favorite_2", save=True
            )
        )

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return self._model.zones

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return self._model.zones

    async def massage_head_toggle(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("massage", massage_action="head"))

    async def massage_foot_toggle(self) -> None:
        await self.async_execute_sleeptracker_request(p.Request("massage", massage_action="foot"))

    async def massage_mode_step(self) -> None:
        await self.async_execute_sleeptracker_request(
            p.Request("massage", massage_action="pattern")
        )

    async def massage_off(self) -> None:
        await self._release(massage_only=True)

    async def lights_toggle(self) -> None:
        await self._control(
            p.light(self._unit, self._token, restricted=self._restricted), fast=True
        )

    def validate_sleeptracker_request(self, request: p.Request) -> None:
        p.validate_request(request, self._model)
        if request.kind == "identify" and request.mode == 2 and not self._restricted:
            raise ValueError("App local identification requires the restricted session")
        if request.save and not self.supports_memory_programming:
            raise ValueError("Processor types 5, 6 and 7 have no app preset-save route")

    async def async_execute_sleeptracker_request(self, request: p.Request) -> None:
        self.validate_sleeptracker_request(request)
        if request.kind == "preset":
            await self._control(
                p.preset(request.preset, self._unit, self._token, save=request.save),
                fast=not request.save,
            )
        elif request.kind == "climate":
            await self._control(p.fan(request, None if self._restricted else self._token))
            for side in ("left", "right") if request.fan_side == "both" else (request.fan_side,):
                self._state[side + "_commanded_constant"] = request.constant
                self._state[side + "_commanded_timer_seconds"] = 3600 if request.heating else 36000
            self._publish()
        elif request.kind == "wave":
            await self._control(
                p.wave(request, self._unit, None if self._restricted else self._token)
            )
        elif request.kind == "wind_down":
            await self._control(
                p.envelope(
                    {"windDown": {"position": {"side": self._unit}, "mode": request.mode}},
                    self._token,
                )
            )
        elif request.kind == "local_animation":
            await self._control(
                p.local_animation(self._unit, None if self._restricted else self._token)
            )
        elif request.kind == "massage":
            if request.massage_action == "off":
                await self.massage_off()
            else:
                zone = (
                    request.massage_action if request.massage_action in ("head", "foot") else None
                )
                await self._control(
                    p.massage(
                        "step" if zone else request.massage_action,
                        self._unit,
                        self._token,
                        location=zone,
                    )
                )
        else:
            split = request.mode == 1
            try:
                # Split-setup identification is a literal side1 request, not a
                # physical-side mapping or regular authenticated light command.
                for index in range(4):
                    reply = await self._exchange(
                        p.CONTROL_UUID,
                        p.light(
                            1,
                            None,
                            restricted=True,
                            identify=split,
                            off=not split and index % 2 == 1,
                        ),
                    )
                    self._update_status(reply)
                    if not split:
                        continue
                    try:
                        await asyncio.wait_for(self._coordinator.cancel_command.wait(), timeout=1.5)
                    except TimeoutError:
                        continue
                    raise asyncio.CancelledError
            except BaseException:
                self._tainted = True
                raise
            finally:
                if (
                    self._session_client is not None
                    and self.client is not None
                    and self.client.is_connected
                ):
                    try:
                        payload = p.light(1, None, restricted=True, identify=split, off=True)
                        if self._tainted:
                            await self._write(
                                p.CONTROL_UUID, payload, fast=False, cancel=asyncio.Event()
                            )
                        else:
                            await self._exchange(p.CONTROL_UUID, payload, cancel=asyncio.Event())
                    finally:
                        if self._tainted and self.client is not None:
                            await self.client.disconnect()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = [
            ControllerButtonSpec(
                "sleeptracker_light_toggle",
                "Toggle safety light",
                lambda ctrl: ctrl.lights_toggle(),
                translation_key="sleeptracker_light_toggle",
            ),
            ControllerButtonSpec(
                "sleeptracker_refresh",
                "Refresh bed state",
                lambda ctrl: ctrl.read_positions(),
                translation_key="sleeptracker_refresh",
                cancel_movement=False,
            ),
            _request_button(
                "sleeptracker_identify", "Identify split light (unit 1)", p.Request("identify")
            ),
        ]
        if self.supports_memory_programming:
            for name in ("zero_g", "anti_snore", "tv_pc"):
                if name != "tv_pc" or self.supports_preset_tv:
                    buttons.append(
                        _request_button(
                            "sleeptracker_save_" + name,
                            "Save " + name,
                            p.Request("preset", preset=name, save=True),
                        )
                    )
        if self._restricted:
            buttons.append(
                _request_button(
                    "sleeptracker_identify_local",
                    "Identify local light",
                    p.Request("identify", mode=2),
                )
            )

            async def off(ctrl: BedController) -> None:
                selected = _controller(ctrl)
                await selected._control(
                    p.light(selected._unit, selected._token, restricted=True, off=True), fast=True
                )

            buttons.append(
                ControllerButtonSpec(
                    "sleeptracker_light_off",
                    "Safety light off",
                    off,
                    translation_key="sleeptracker_light_off",
                )
            )
        if self._model.premium:
            buttons.append(
                _request_button(
                    "sleeptracker_massage_28hz",
                    "28 Hz massage",
                    p.Request("massage", massage_action="28Hz"),
                )
            )
            buttons.append(
                _request_button(
                    "sleeptracker_massage_40hz",
                    "40 Hz massage",
                    p.Request("massage", massage_action="40Hz"),
                )
            )
            for mode in (1, 2):
                buttons.append(
                    _request_button(
                        f"sleeptracker_wind_down_{mode}",
                        f"Wind down {mode}",
                        p.Request("wind_down", mode=mode),
                    )
                )
            buttons.append(
                _request_button(
                    "sleeptracker_local_animation",
                    "Local bed animation",
                    p.Request("local_animation"),
                )
            )

            async def wave_start(ctrl: BedController) -> None:
                selected = _controller(ctrl)
                await selected.async_execute_sleeptracker_request(
                    p.Request(
                        "wave",
                        frequency=p.integer(selected._state.get("wave_frequency"), 52),
                        minutes=p.integer(selected._state.get("wave_minutes"), 30),
                    )
                )

            buttons.append(
                ControllerButtonSpec(
                    "sleeptracker_wave_start",
                    "Start relaxation wave",
                    wave_start,
                    translation_key="sleeptracker_wave_start",
                )
            )
        return tuple(buttons)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs: list[ControllerSelectSpec] = []
        if self._model.premium:

            def choose(option: str) -> None:
                self._state["wave_frequency"] = int(option)
                self._publish()

            async def choose_connected(ctrl: BedController, option: str) -> None:
                _controller(ctrl)._state["wave_frequency"] = int(option)
                _controller(ctrl)._publish()

            specs.append(
                ControllerSelectSpec(
                    "sleeptracker_wave_frequency",
                    "sleeptracker_wave_frequency",
                    "sleeptracker_wave_frequency",
                    tuple(str(hz) for hz in p.FREQUENCIES),
                    choose_connected,
                    local_select_fn=choose,
                )
            )
        if self._model.breeze:
            fan_sides: tuple[p.FanSide, ...] = ("left", "right")
            for side in fan_sides:

                async def select_mode(
                    ctrl: BedController, option: str, zone: p.FanSide = side
                ) -> None:
                    selected = _controller(ctrl)
                    level = p.integer(selected._state.get(zone + "_level"), 1)
                    await selected.async_execute_sleeptracker_request(
                        p.Request(
                            "climate",
                            fan_side=zone,
                            heating=option == "heat",
                            level=0 if option == "off" else max(1, level),
                            constant=selected._state.get(zone + "_commanded_constant", True)
                            is True,
                        )
                    )

                specs.append(
                    ControllerSelectSpec(
                        "sleeptracker_" + side + "_mode",
                        "sleeptracker_" + side + "_mode",
                        "sleeptracker_" + side + "_mode",
                        ("off", "cool", "heat"),
                        select_mode,
                    )
                )

                async def select_curve(
                    ctrl: BedController, option: str, zone: p.FanSide = side
                ) -> None:
                    selected = _controller(ctrl)
                    await selected.async_execute_sleeptracker_request(
                        p.Request(
                            "climate",
                            fan_side=zone,
                            heating=selected._state.get(zone + "_heating") is True,
                            level=p.integer(selected._state.get(zone + "_level")),
                            constant=option == "constant",
                        )
                    )

                specs.append(
                    ControllerSelectSpec(
                        "sleeptracker_" + side + "_curve",
                        "sleeptracker_" + side + "_curve",
                        "sleeptracker_" + side + "_curve",
                        ("constant", "curve"),
                        select_curve,
                    )
                )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self._model.premium:

            async def minutes(ctrl: BedController, value: float) -> None:
                selected = _controller(ctrl)
                if value not in range(5, 106, 5):
                    raise ValueError("Wave duration must be 5–105 minutes in steps of 5")
                selected._state["wave_minutes"] = int(value)
                selected._publish()

            specs.append(
                ControllerNumberSpec(
                    "sleeptracker_wave_minutes",
                    "sleeptracker_wave_minutes",
                    "sleeptracker_wave_minutes",
                    5,
                    105,
                    5,
                    minutes,
                    "min",
                )
            )
        if self._model.breeze:
            fan_sides: tuple[p.FanSide, ...] = ("left", "right")
            for side in fan_sides:

                async def level(ctrl: BedController, value: float, zone: p.FanSide = side) -> None:
                    selected = _controller(ctrl)
                    if value not in range(4):
                        raise ValueError("ActiveBreeze level must be 0 through 3")
                    await selected.async_execute_sleeptracker_request(
                        p.Request(
                            "climate",
                            fan_side=zone,
                            level=int(value),
                            heating=selected._state.get(zone + "_heating") is True,
                            constant=selected._state.get(zone + "_commanded_constant", True)
                            is True,
                        )
                    )

                specs.append(
                    ControllerNumberSpec(
                        "sleeptracker_" + side + "_level",
                        "sleeptracker_" + side + "_level",
                        "sleeptracker_" + side + "_level",
                        0,
                        3,
                        1,
                        level,
                    )
                )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        keys = ["layout", "massage_pattern", "massage_head_strength", "massage_foot_strength"]
        if self._model.breeze:
            keys.extend(side + "_commanded_timer_seconds" for side in ("left", "right"))
        return tuple(
            ControllerStateSensorSpec(
                "sleeptracker_" + key,
                "sleeptracker_" + key,
                "sleeptracker_" + key,
                "mdi:bed-outline",
                attribute_keys=("sleeptracker_metadata",) if key == "layout" else (),
            )
            for key in keys
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "sleeptracker_light_on",
                "sleeptracker_light_on",
                "sleeptracker_light_on",
                "mdi:lightbulb",
            ),
        ) + (
            (
                ControllerStateBinarySensorSpec(
                    "sleeptracker_wind_down_running",
                    "sleeptracker_wind_down_running",
                    "sleeptracker_wind_down_running",
                    "mdi:bed-clock",
                ),
            )
            if self._model.premium
            else ()
        )
