"""OKIN SleepEase bed and mattress-sensor controller."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .. import doublesleep_protocol as p
from ..app_session import app_session
from ..doublesleep_state import Notifications, Report, report_records
from ..profiles.okin_nframe import DOUBLESLEEP
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator
    from ..doublesleep_services import Request

_LOGGER = logging.getLogger(__name__)


@dataclass
class Session:
    cache: p.Cache = field(default_factory=p.Cache)
    writer: p.JsonWriter = field(default_factory=p.JsonWriter)
    child_lock: bool = False
    privacy: bool = False


def selected(controller: BedController | SideBoundController) -> DoubleSleepController:
    if isinstance(controller, SideBoundController):
        controller = controller._controller
    if not isinstance(controller, DoubleSleepController):
        raise TypeError("This action requires OKIN SleepEase")
    return controller


def action(index: int) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        await selected(controller).press(index)

    return execute


def motor(index: int) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        await selected(controller)._move(index)

    return execute


# Binary-driver motors and held controls refresh on the app's 300 ms timer.
_REFRESH_S = (DOUBLESLEEP.hold.repeat_ms or 0) / 1000


class DoubleSleepController(BedController):
    profile = DOUBLESLEEP

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        protocol: p.Protocol,
        model: int,
        session: Session | None = None,
        advertised_identity: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        if protocol not in ("p1", "p2", "p3") or model not in p.MODELS:
            raise ValueError("Select a valid SleepEase driver and saved app model")
        self.protocol: p.Protocol = protocol
        self.model = model
        self.advertised_identity = advertised_identity
        self.session = session or app_session(
            coordinator.hass, coordinator.address, ("doublesleep", protocol, model), Session
        )
        # HA rebuilds the BLE controller on reconnect. Its coordinator lives for
        # the logical UI lifetime; a reload creates a cold view while numeric
        # per-device statics remain in app_session.
        self.ui = p.UIState()
        view = coordinator.controller_state.get("doublesleep_ui")
        if isinstance(view, dict) and view.get("profile") == f"{protocol}:{model}":
            if type(view.get("sonic_ui")) is bool:
                self.ui.sonic_ui = view["sonic_ui"]
            if type(view.get("slow")) is bool:
                self.ui.slow = view["slow"]
            if type(view.get("pwm")) is int and 0 <= view["pwm"] <= 255:
                self.ui.pwm = view["pwm"]
            if type(view.get("timer")) is int and 0 <= view["timer"] <= 255:
                self.ui.timer = view["timer"]
        self.parser = Notifications(protocol, model, self.session.cache, ui=self.ui)
        for side in ("left", "right"):
            history = coordinator.controller_state.get(f"doublesleep_{side}_history")
            if (
                isinstance(history, list)
                and len(history) == 8
                and all(type(value) is int for value in history)
            ):
                self.parser.state[side + "_history"] = list(history)
        self.parser.privacy = self.session.privacy
        self._client: BleakClient | None = None
        self._tx: BleakGATTCharacteristic | None = None
        self._rx: BleakGATTCharacteristic | None = None
        self._generation = 0
        self._ready = False
        self._report_timer: asyncio.TimerHandle | None = None
        self._legacy_timer: asyncio.TimerHandle | None = None
        self._followups: set[asyncio.Task[None]] = set()
        self._legacy_active = False
        self._legacy_finishing = False
        self._legacy_generation = 0
        self._report_future: asyncio.Future[Report] | None = None
        self._report_allow = asyncio.Event()
        self._report_wake = asyncio.Event()
        self._report_context: tuple[int, ...] | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return p.TX_UUID

    @property
    def supports_doublesleep_controls(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return True  # Realtime sensor reports and report continuation use the live RX stream.

    @property
    def supports_single_address_pairing(self) -> bool:
        return False  # Sides are sensor/report fields, not independently routed motor writes.

    @property
    def supports_motor_control(self) -> bool:
        return self.protocol != "p3" and self.model not in p.P3_MODELS

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def supports_stop_all(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_memory_presets(self) -> bool:
        return self.supports_motor_control

    @property
    def memory_slot_count(self) -> int:
        return 2 if self.supports_motor_control else 0

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_motor_control and self.protocol == "p2"

    @property
    def supports_preset_flat(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_zero_g(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_tv(self) -> bool:
        return self.supports_motor_control

    @property
    def supports_preset_lounge(self) -> bool:
        return self.supports_motor_control

    @property
    def persisted_app_state_key(self) -> str:
        return f"{self.protocol}:{self.model}"

    @property
    def persisted_app_state(self) -> dict[str, bool]:
        return {"child_lock": self.session.child_lock}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        value = state.get("child_lock", False)
        if set(state) - {"child_lock"} or type(value) is not bool:
            raise ValueError("Invalid SleepEase child-lock preference")
        self.session.child_lock = value
        self.forward_controller_state_updates({"doublesleep_child_lock": "on" if value else "off"})

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "driver": self.protocol,
            "app_model": self.model,
            "model_name": p.MODELS[self.model],
            "advertised_identity": self.advertised_identity,
            "is_double": self.model in p.DOUBLE_MODELS,
            "ready": self._ready,
            "child_lock": self.session.child_lock,
            "sonic_ui": self.ui.sonic_ui,
            "slow_anti_snore": self.ui.slow,
            "state": self.parser.state,
        }

    def _publish(self) -> None:
        self.parser.state["child_lock"] = "on" if self.session.child_lock else "off"
        self.parser.state["privacy"] = "on" if self.parser.privacy else "off"
        self.parser.state["model"] = p.MODELS[self.model]
        self.parser.state["ui"] = {
            "profile": f"{self.protocol}:{self.model}",
            "sonic_ui": self.ui.sonic_ui,
            "slow": self.ui.slow,
            "pwm": self.ui.pwm,
            "timer": self.ui.timer,
        }
        self.parser.state["configuration"] = {
            key: value
            for key, value in self.parser.state.items()
            if key
            in (
                "privacy",
                "anti_state",
                "anti_mode",
                "left_sensitivity",
                "right_sensitivity",
                "use_side",
                "functions",
                "sensor_version",
                "firmware_version",
                "sensitivity_raw",
            )
        }
        self.parser.state["configuration"].update(
            {
                "slow_anti_snore": self.ui.slow,
                "pwm": self.ui.pwm,
                "timer": self.ui.timer,
                "sonic_ui": self.ui.sonic_ui,
            }
        )
        self.parser.state["light_on"] = self.session.cache.light[1]
        self.parser.state["light_raw"] = list(self.session.cache.light)
        alarm = self.parser.state.get("alarm")
        if isinstance(alarm, dict):
            self.parser.state["alarm_enabled"] = alarm.get("enabled", 0)
        self.forward_controller_state_updates(
            {"doublesleep_" + k: v for k, v in self.parser.state.items()}
        )

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("SleepEase is disconnected")
        if self._client is client:
            return
        service = client.services.get_service(p.SERVICE_UUID)
        if service is None:
            raise ConnectionError("SleepEase UART service is absent")
        self._tx = next((c for c in service.characteristics if c.uuid.lower() == p.TX_UUID), None)
        self._rx = next((c for c in service.characteristics if c.uuid.lower() == p.RX_UUID), None)
        if self._tx is None or self._rx is None:
            raise ConnectionError("SleepEase requires both TX and RX characteristics")
        required = "write" if self.protocol == "p3" else "write-without-response"
        if required not in self._tx.properties or not {"notify", "indicate"}.intersection(
            self._rx.properties
        ):
            raise ConnectionError("SleepEase GATT properties do not support the selected driver")
        self._client = client

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._ready and self.client is self._client:
            return
        await self.async_discover_capabilities()
        client, rx = self._client, self._rx
        assert client is not None and rx is not None
        self._generation += 1
        generation = self._generation
        self._notify_callback = callback

        def receive(sender: BleakGATTCharacteristic, value: bytearray) -> None:
            if (
                generation != self._generation
                or self.client is not client
                or not client.is_connected
            ):
                return
            self._receive(bytes(value))

        try:
            await client.start_notify(rx, receive)
            # No PIN, bonding, authentication, or guessed family initialization.
            if self.protocol in ("p1", "p2"):
                if self.protocol == "p2":
                    await self.execute(57, (0,))
                await asyncio.sleep(0.2)
                if not self.session.child_lock:
                    await self.execute(47)
                await asyncio.sleep(0.2)
                if not self.session.child_lock:
                    await self.execute(47)
            else:
                if not self.session.child_lock:
                    await self.execute(47)
                await asyncio.sleep(0.5)
                await self.execute(77)
            await asyncio.sleep(0.3)
            # Report retrieval is exposed as an explicit serialized HA action.
            await asyncio.sleep(0.2)
            await self.execute(53)
            if self.protocol == "p3":
                for index in (69, 71, 73):
                    await self.execute(index)
            device_info = client.services.get_service(p.FIRMWARE_SERVICE_UUID)
            firmware = (
                next(
                    (
                        char
                        for char in device_info.characteristics
                        if char.uuid.lower() == p.FIRMWARE_UUID
                    ),
                    None,
                )
                if device_info
                else None
            )
            if firmware is not None:
                with suppress(Exception):
                    async with self._ble_lock:
                        self.parser.state["firmware_version"] = bytes(
                            await client.read_gatt_char(firmware)
                        ).decode("utf-8")[:128]
            self._ready = True
            self._publish()
        except BaseException:
            await self.stop_notify()
            raise

    def _report(self, report: Report) -> None:
        side = "right" if report.side else "left"
        attributes = {**report.attributes(), "records": report_records(report)}
        context = self._report_context
        matching = (
            context is not None
            and context[0] == report.side
            and (
                report.status != 0
                or report.channel == ("history_month" if context[1] else "history")
            )
        )
        if matching and context is not None:
            attributes.update(
                requested_date=f"{context[2]:04}-{context[3]:02}-{context[4]:02}",
                period="month" if context[1] else "day",
                physical_address=self._coordinator.address,
            )
        self.parser.state[side + "_report_status"] = report.status
        self.parser.state[side + "_report"] = attributes
        self._publish()
        if (
            matching
            and self._report_future is not None
            and not self._report_future.done()
            and report.status in (0, 1)
        ):
            self._report_future.set_result(report)

    def _receive(self, data: bytes) -> None:
        self.forward_raw_notification(p.RX_UUID, data)
        generation = self.parser.binary.timer_generation
        previous_binary = (generation, self.parser.binary.index, len(self.parser.binary.buffer))
        previous_json = (self.parser.json_reader.index, len(self.parser.json_reader.buffer))
        parsed = False
        try:
            if self._legacy_active and self.parser.legacy_feed(data):
                self._schedule_legacy()
            result, allow = self.parser.feed(data, dt_util.now())
            parsed = True
            if result is not None:
                self._report(result)
            if allow and self._report_future is not None:
                self._report_allow.set()
                self._report_wake.set()
            self.session.privacy = self.parser.privacy
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as err:
            # Keep mutations that happened before the malformed field, but never
            # let a corrupt notification escape into HA's Bluetooth dispatcher.
            self.parser.state["parser_error"] = str(err)
            _LOGGER.debug("Rejected SleepEase notification: %s", err)
        finally:
            history = self.parser.binary
            if generation != history.timer_generation:
                if self._report_timer is not None:
                    self._report_timer.cancel()
                self._report_timer = (
                    asyncio.get_running_loop().call_later(
                        5, self._report_timeout, self._generation, history.timer_generation
                    )
                    if history.timer_pending
                    else None
                )
            elif not history.timer_pending and self._report_timer is not None:
                self._report_timer.cancel()
                self._report_timer = None
            if parsed and self._report_future is not None and not self._report_future.done():
                context = self._report_context
                binary_progress = (
                    history.timer_generation != previous_binary[0]
                    or len(history.buffer) > previous_binary[2]
                )
                json_progress = len(self.parser.json_reader.buffer) > previous_json[1]
                if (self.protocol == "p3" and json_progress) or (
                    binary_progress
                    and context is not None
                    and history.side == context[0]
                    and history.monthly == bool(context[1])
                ):
                    self._report_wake.set()
            self._publish()

    def _report_timeout(
        self, generation: int | None = None, timer_generation: int | None = None
    ) -> None:
        if (
            self._client is None
            or generation is not None
            and generation != self._generation
            or timer_generation is not None
            and timer_generation != self.parser.binary.timer_generation
        ):
            return
        self._report_timer = None
        if (result := self.parser.binary.timeout()) is not None:
            self._report(result)

    def _followup(self, index: int) -> None:
        generation = self._generation

        async def run() -> None:
            if generation != self._generation:
                return

            async def execute(controller: BedController) -> None:
                if controller is self and generation == self._generation:
                    await self.execute(index)

            try:
                await self._coordinator.async_execute_controller_command(
                    execute, cancel_running=False, resource="doublesleep_report"
                )
            except Exception:
                _LOGGER.debug("SleepEase report continuation failed", exc_info=True)
            finally:
                if index == 64 and generation == self._generation:
                    self._legacy_finishing = False

        task = self._coordinator.hass.async_create_task(run())
        self._followups.add(task)
        task.add_done_callback(self._followups.discard)

    def _schedule_legacy(self) -> None:
        if self._legacy_timer is not None:
            self._legacy_timer.cancel()
        self._legacy_generation += 1
        self._legacy_timer = asyncio.get_running_loop().call_later(
            0.5, self._finish_legacy, self._generation, self._legacy_generation
        )

    def _finish_legacy(
        self, generation: int | None = None, timer_generation: int | None = None
    ) -> None:
        if (
            not self._legacy_active
            or self._client is None
            or generation is not None
            and generation != self._generation
            or timer_generation is not None
            and timer_generation != self._legacy_generation
        ):
            return
        self._legacy_generation += 1
        self._legacy_timer = None
        self._legacy_active = False
        self._legacy_finishing = True
        self.parser.state["legacy_report"] = {
            **self.parser.legacy_report(dt_util.now().tzinfo),
            "physical_address": self._coordinator.address,
        }
        self._publish()
        self._followup(64)

    def _invalidate_connection(self) -> tuple[asyncio.Task[None], ...]:
        """Retire callbacks synchronously, including an unexpected link loss."""
        self._generation += 1
        self._ready = False
        self._notify_callback = None
        if self._report_future is not None and not self._report_future.done():
            self._report_future.set_exception(ConnectionError("SleepEase report session ended"))
        for timer in (self._report_timer, self._legacy_timer):
            if timer is not None:
                timer.cancel()
        self._report_timer = self._legacy_timer = None
        self._legacy_active = self._legacy_finishing = False
        self._legacy_generation += 1
        followups = tuple(task for task in self._followups if task is not asyncio.current_task())
        for task in followups:
            task.cancel()
        self._client = None
        self._tx = self._rx = None
        self._report_context = None
        # Parser buffers and timers belong to a connection; notification caches
        # and sequence remain in this physical target's process-local session.
        self.parser = Notifications(self.protocol, self.model, self.session.cache, ui=self.ui)
        self.parser.privacy = self.session.privacy
        return followups

    def on_disconnect(self) -> None:
        self._invalidate_connection()

    async def stop_notify(self) -> None:
        client, rx = self._client, self._rx
        followups = self._invalidate_connection()
        if followups:
            await asyncio.gather(*followups, return_exceptions=True)
        if client is not None and rx is not None and client.is_connected:
            with suppress(Exception):
                await client.stop_notify(rx)

    def validate_request(self, request: Request) -> None:
        index = {
            "alarm": 49,
            "anti_snore": 62,
            "anti_snore_demo": 62,
            "sensitivities": 68 if self.model in p.P3_MODELS else 67,
            "report": 72,
            "save_preset": request.values[0] if request.values else 0,
            "capabilities": 57,
        }[request.action]
        self.validate(index)
        if (
            request.action == "sensitivities"
            and self.model in p.P3_MODELS
            and request.values[0] != -1
        ):
            raise ValueError("P3 reports its sensor sides but has no reachable side-setting action")
        if request.action == "save_preset" and not self.supports_memory_programming:
            raise ValueError("This SleepEase profile cannot program presets")
        if request.action in ("alarm", "save_preset") and not self.supports_motor_control:
            raise ValueError("This SleepEase app profile has no bed control page")
        if (
            request.action in ("anti_snore", "anti_snore_demo")
            and not self.ui.slow
            and any(v >= 0 for v in request.values[2:])
        ):
            raise ValueError("Slow anti-snore settings require the MFP capability")
        if request.action == "report" and self.model not in p.P2_MODELS | p.P3_MODELS:
            raise ValueError("Use Download legacy history for this saved app model")
        if (
            request.action == "report"
            and self.protocol == "p2"
            and not 2000 <= request.values[2] <= 2255
        ):
            raise ValueError("The binary report year must fit its 2000-based byte")
        if request.action == "report" and self._report_future is not None:
            raise ValueError("A SleepEase report request is already active")

    async def request(self, request: Request) -> None:
        self.validate_request(request)
        if request.action == "alarm":
            await self.execute(47)
            await self.execute(49, request.values)
            await asyncio.sleep(0.3)
            await self.execute(52)
        elif request.action in ("anti_snore", "anti_snore_demo"):
            operation, strength, pwm, timer = request.values
            cache = self.ui
            if not cache.slow and (pwm >= 0 or timer >= 0):
                raise ValueError("Slow anti-snore settings require the MFP capability")
            values = (
                (
                    operation,
                    strength,
                    cache.pwm if pwm < 0 else pwm,
                    cache.timer if timer < 0 else timer,
                )
                if self.protocol == "p2"
                else (operation, strength)
            )
            try:
                await self.execute(62, values)
            finally:
                # Separate shipped apply/demo roots use closeAntiSnore/allStop.
                await self.execute(
                    63 if request.action == "anti_snore" else 27, cancel=asyncio.Event()
                )
        elif request.action == "sensitivities":
            values = []
            for key, requested, default in zip(
                ("use_side", "left_sensitivity", "right_sensitivity"),
                request.values,
                (3, 1, 1),
                strict=True,
            ):
                reported = self.parser.state.get(key, default)
                if type(reported) is not int:
                    raise ValueError("SleepEase reported an invalid sensitivity configuration")
                values.append(reported if requested == -1 else requested)
            await self.execute(
                68 if self.model in p.P3_MODELS else 67,
                tuple(values[1:]) if self.model in p.P3_MODELS else tuple(values),
            )
            await asyncio.sleep(0.2)
            await self.execute(69 if self.model in p.P3_MODELS else 53)
        elif request.action == "save_preset":
            await self._save(request.values[0])
        elif request.action == "capabilities":
            await self.execute(57, request.values)
        else:
            # Request-side correlation is connection-local. Keep the coordinator
            # lock until completion so a second request cannot steal its side.
            self._report_context = request.values
            future = self._report_future = asyncio.get_running_loop().create_future()
            self._report_allow.clear()
            self._report_wake.clear()
            continuation: asyncio.Task[bool] | None = None
            cancelled = asyncio.create_task(self._coordinator.cancel_command.wait())
            try:
                await self.execute(72, request.values)
                # The source has a 5s timeout indication. In HA it bounds silence,
                # not an otherwise progressing transfer, while the request owns
                # its physical connection/side until completion.
                while not future.done():
                    continuation = asyncio.create_task(self._report_wake.wait())
                    done, _ = await asyncio.wait(
                        (future, continuation, cancelled),
                        timeout=5,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        raise TimeoutError("SleepEase report made no progress for 5 seconds")
                    if cancelled in done:
                        raise asyncio.CancelledError
                    if continuation in done and not future.done():
                        self._report_wake.clear()
                        if self._report_allow.is_set():
                            self._report_allow.clear()
                            await self.execute(78)
                    else:
                        continuation.cancel()
                        with suppress(asyncio.CancelledError):
                            await continuation
                    continuation = None
                future.result()
            except BaseException:
                # There is no report request ID in responses. A cancelled exchange
                # must end the session before another request can use this device.
                client = self._client
                await self.stop_notify()
                if client is not None and client.is_connected:
                    await client.disconnect()
                raise
            finally:
                for task in (cancelled, continuation):
                    if task is not None:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()
                self._report_future = None

    @property
    def held_control_options(self) -> tuple[str, ...]:
        if not self.supports_motor_control:
            return ()
        indices = (2, 3, 4, 5, 8, 9, 10, 11, 12, 13)
        if self.protocol == "p1":
            indices += (14, 15, 16, 17, 18, 19, 26)
        return tuple(f"doublesleep_{index}" for index in indices)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 100 <= duration_ms <= 60000
        ):
            raise ValueError("Choose a SleepEase held control and duration from 100 to 60000 ms")
        self.validate(int(control.removeprefix("doublesleep_")))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        index = int(control.removeprefix("doublesleep_"))
        end = asyncio.get_running_loop().time() + duration_ms / 1000
        cancel = self._coordinator.cancel_command
        try:
            while not cancel.is_set() and asyncio.get_running_loop().time() < end:
                started = asyncio.get_running_loop().time()
                await self.execute(index)
                delay = min(
                    end - asyncio.get_running_loop().time(),
                    _REFRESH_S - (asyncio.get_running_loop().time() - started),
                )
                if delay > 0:
                    with suppress(TimeoutError):
                        await asyncio.wait_for(cancel.wait(), delay)
        finally:
            await self.execute(1, cancel=asyncio.Event())

    async def read_positions(self, motor_count: int = 2) -> None:
        return  # This app reports sensor data, never measured motor positions.

    def validate(self, index: int) -> None:
        supported = {"p1": p.P1_SUPPORTED, "p2": p.P2_SUPPORTED, "p3": p.P3_SUPPORTED}[
            self.protocol
        ]
        if index not in supported:
            raise ValueError("SleepEase action is unavailable for this driver")
        if self.session.child_lock and index in p.CHILD_BLOCKED:
            raise ValueError("SleepEase child lock blocks this action")
        if index == 66 and self.model in p.P2_MODELS | p.P3_MODELS:
            raise ValueError("Legacy history requires a saved legacy app model")
        if index == 66 and (self._legacy_active or self._legacy_finishing):
            raise ValueError("A SleepEase legacy download is already active")

    async def press(self, index: int) -> None:
        await self.execute(index)
        if index == 48:
            await asyncio.sleep(0.3)
            await self.execute(52)
        elif index in (28, 29, 31, 32, 35, 36, 37, 38, 40, 41):
            await asyncio.sleep(0.2)
            await self.execute(50)
        elif index in (*range(79, 87), 89, 90):
            await asyncio.sleep(0.2)
            await self.execute(51)

    async def execute(
        self, index: int, values: tuple[int, ...] = (), *, cancel: asyncio.Event | None = None
    ) -> None:
        self.validate(index)
        client, tx = self._client, self._tx
        if client is None or tx is None or client is not self.client or not client.is_connected:
            raise ConnectionError("SleepEase session ended")
        effective_cancel = cancel if cancel is not None else self._coordinator.cancel_command
        if effective_cancel.is_set():
            raise asyncio.CancelledError
        now = dt_util.now()
        packets = (
            self.session.writer.command(index, values, now, client.mtu_size)
            if self.protocol == "p3"
            else [p.binary_command(self.protocol, index, values, self.session.cache, now)]
        )
        if index == 72 and self.protocol == "p3":
            self.parser.json_reader.side = values[0]
        if index == 66:
            self._legacy_generation += 1
            self.parser.legacy.clear()
            self.parser.legacy_count = self.parser.legacy_expected = 0
            self._legacy_active = True
        try:
            await self._send_packets(packets, effective_cancel)
        except BaseException:
            if index == 66:
                self._legacy_active = False
                if self._legacy_timer is not None:
                    self._legacy_timer.cancel()
                    self._legacy_timer = None
            if self.protocol == "p3":
                client = self._client
                await self.stop_notify()
                if client is not None and client.is_connected:
                    await client.disconnect()
            raise
        if index in (59, 60):
            self.session.privacy = self.parser.privacy = index == 59
        if index == 66 and self._legacy_active and self._legacy_timer is None:
            self._schedule_legacy()
        self._publish()

    async def _send_packets(self, packets: list[bytes], effective_cancel: asyncio.Event) -> None:
        client, tx = self._client, self._tx
        assert client is not None and tx is not None
        for packet in packets:
            if self._client is not client or self.client is not client or not client.is_connected:
                raise ConnectionError("SleepEase packet belongs to an ended session")
            if effective_cancel.is_set():
                raise asyncio.CancelledError
            if not packet:
                continue
            if len(packet) > min(client.mtu_size - 3, 512):
                raise ValueError("SleepEase packet exceeds negotiated ATT write capacity")
            if self.protocol != "p3" and len(packet) > tx.max_write_without_response_size:
                raise ValueError("SleepEase packet exceeds characteristic write capacity")
            wrote = False

            def mark_written() -> None:
                nonlocal wrote
                wrote = True

            # FlutterBluePlus367f88 also bounds its write callback at15s.
            async with asyncio.timeout(15):
                await self._write_gatt_with_retry(
                    p.TX_UUID,
                    packet,
                    response=self.protocol == "p3",
                    characteristic=tx,
                    cancel_event=effective_cancel,
                    on_write=mark_written,
                )
            if not wrote:
                raise asyncio.CancelledError

    async def _move(self, index: int) -> None:
        if not self.supports_motor_control:
            raise ValueError("The selected SleepEase profile has no bed controls")
        self.validate(index)
        try:
            count, _delay = self.motor_pulse_settings()
            for tick in range(count):
                if self._coordinator.cancel_command.is_set():
                    break
                await self.execute(index)
                if tick + 1 < count:
                    try:
                        await asyncio.wait_for(self._coordinator.cancel_command.wait(), _REFRESH_S)
                    except TimeoutError:
                        pass
        finally:
            await self.execute(1, cancel=asyncio.Event())

    async def _preset(self, index: int) -> None:
        if self.protocol == "p1":
            await self._move(index)
            return
        if not self.supports_motor_control:
            raise ValueError("The selected SleepEase profile has no bed controls")
        try:
            await self.execute(index)
        finally:
            await self.execute(1, cancel=asyncio.Event())

    async def move_head_up(self) -> None:
        await self._move(2)

    async def move_head_down(self) -> None:
        await self._move(3)

    async def move_head_stop(self) -> None:
        await self.execute(1, cancel=asyncio.Event())

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move(4)

    async def move_legs_down(self) -> None:
        await self._move(5)

    async def move_legs_stop(self) -> None:
        await self.move_head_stop()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_head_stop()

    async def stop_all(self) -> None:
        if self.protocol != "p3":
            await self.execute(1, cancel=asyncio.Event())

    async def preset_flat(self) -> None:
        await self._preset(26)

    async def preset_zero_g(self) -> None:
        await self._preset(19)

    async def preset_anti_snore(self) -> None:
        await self._preset(16)

    async def preset_tv(self) -> None:
        await self._preset(18)

    async def preset_lounge(self) -> None:
        await self._preset(17)

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("SleepEase has two numbered recall buttons")
        await self._preset(13 + memory_num)

    async def program_memory(self, memory_num: int) -> None:
        if not self.supports_memory_programming or memory_num not in (1, 2):
            raise ValueError("SleepEase memory programming is unavailable")
        await self._save(19 + memory_num)

    async def _save(self, index: int) -> None:
        self.validate(index)
        try:
            await self.execute(index)
        finally:
            await self.execute(1, cancel=asyncio.Event())

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self.supports_motor_control:
            return ()
        return tuple(
            MotorControlSpec(
                key,
                key,
                motor(up),
                motor(down),
                action(1),
                # Any motor release replaces the app's one shared hold stream.
                hold=ControllerMotorHoldSpec(
                    f"doublesleep_{up}", f"doublesleep_{down}", 0, 0, stop_scope="side"
                ),
            )
            for key, up, down in (
                ("head", 2, 3),
                ("feet", 4, 5),
                ("lumbar", 8, 9),
                ("pillow", 10, 11),
                ("hip", 12, 13),
            )
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if self.protocol != "p1" or not self.supports_motor_control:
            return None
        mapping = {"preset_" + name: index for name, index in p.PRESETS.items()}
        index = mapping.get(key)
        return ControllerHoldSpec(f"doublesleep_{index}", 0, 0) if index is not None else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        items = {47: "Synchronize clock", 53: "Refresh state"}
        if self.protocol != "p3":
            items.update(
                {
                    27: "App all stop",
                    28: "Massage on / toggle",
                    29: "Massage off / toggle",
                    31: "Massage time up",
                    32: "Massage time down",
                    35: "Head massage up",
                    36: "Head massage down",
                    37: "Foot massage up",
                    38: "Foot massage down",
                    40: "Massage mode up",
                    41: "Massage mode down",
                    48: "Disable alarm",
                    50: "Refresh massage",
                    52: "Refresh alarm",
                    58: "Toggle light",
                    59: "Privacy on",
                    60: "Privacy off",
                    63: "Disable anti-snore",
                }
            )
            if self.model not in p.P2_MODELS | p.P3_MODELS:
                items[66] = "Download legacy history"
        if self.protocol == "p2":
            items.update(
                {
                    51: "Refresh sonic massage",
                    54: "Refresh light",
                    73: "Read sensor version",
                    79: "Sonic head up",
                    80: "Sonic head down",
                    81: "Sonic foot up",
                    82: "Sonic foot down",
                    83: "Sonic mode up",
                    84: "Sonic mode down",
                    85: "Sonic time up",
                    86: "Sonic time down",
                    87: "Sonic normal source",
                    88: "Sonic music source",
                    89: "Sonic on",
                    90: "Sonic off",
                }
            )
        if self.protocol == "p3":
            items.update(
                {
                    55: "Query clock",
                    59: "Privacy on",
                    60: "Privacy off",
                    69: "Read sensitivities",
                    71: "Read sensor sides",
                    73: "Initialize sensor",
                    77: "Refresh realtime data",
                }
            )
        if not self.supports_motor_control:
            items = {
                index: label
                for index, label in items.items()
                if index
                not in (
                    27,
                    28,
                    29,
                    31,
                    32,
                    35,
                    36,
                    37,
                    38,
                    40,
                    41,
                    48,
                    50,
                    51,
                    52,
                    54,
                    58,
                    *range(79, 91),
                )
            }
        return tuple(
            ControllerButtonSpec(
                f"doublesleep_{i}",
                name,
                action(i),
                translation_key=(
                    "doublesleep_massage_action"
                    if i in (28, 29, 31, 32, 35, 36, 37, 38, 40, 41, 50, 51, *range(79, 91))
                    else "doublesleep_light_action"
                    if i in (54, 58)
                    else "doublesleep_action"
                ),
                translation_placeholders={"action": name},
            )
            for i, name in items.items()
        )

    def controller_button_available(self, key: str) -> bool:
        index = int(key.removeprefix("doublesleep_"))
        if self.session.child_lock and index in p.CHILD_BLOCKED:
            return False
        if index in range(79, 91) and not self.ui.sonic_ui:
            return False
        return not (index in (28, 29, 31, 32, 35, 36, 37, 38, 40, 41) and self.ui.sonic_ui)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        async def choose(controller: BedController, option: str) -> None:
            current = selected(controller)
            current.session.child_lock = option == "on"
            current._publish()

        def local(option: str) -> None:
            current = self._coordinator.capability_controller
            if current is None or selected(current).session is not self.session:
                raise ValueError("The SleepEase app profile changed")
            self.session.child_lock = option == "on"
            self.forward_controller_state_updates({"doublesleep_child_lock": option})

        return (
            ControllerSelectSpec(
                "doublesleep_child_lock",
                "doublesleep_child_lock",
                "doublesleep_child_lock",
                ("off", "on"),
                choose,
                local_select_fn=local,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        rows: list[tuple[str, str | None]] = [
            ("model", None),
            ("sensor_version", None),
            ("firmware_version", None),
            ("privacy", None),
            ("use_side", None),
            ("parser_error", None),
            ("left_sensitivity", None),
            ("right_sensitivity", None),
        ]
        rows.extend(
            (f"{side}_{key}", unit)
            for side in ("left", "right")
            for key, unit in (("heart_rate", "bpm"), ("breath_rate", "brpm"), ("status", None))
        )
        specs = [
            ControllerStateSensorSpec(
                "doublesleep_" + key, "doublesleep_" + key, "doublesleep_" + key, "mdi:bed", unit
            )
            for key, unit in rows
        ]
        for side in ("left", "right"):
            specs.append(
                ControllerStateSensorSpec(
                    f"doublesleep_{side}_report",
                    "doublesleep_report",
                    f"doublesleep_{side}_report_status",
                    "mdi:chart-line",
                    attribute_keys=(
                        f"doublesleep_{side}_report",
                        f"doublesleep_{side}_history",
                        f"doublesleep_{side}_raw",
                    ),
                )
            )
        specs.append(
            ControllerStateSensorSpec(
                "doublesleep_legacy_report",
                "doublesleep_legacy_report",
                "doublesleep_model",
                "mdi:chart-line",
                attribute_keys=("doublesleep_legacy_report",),
            )
        )
        specs.extend(
            (
                ControllerStateSensorSpec(
                    "doublesleep_configuration",
                    "doublesleep_configuration",
                    "doublesleep_model",
                    "mdi:cog",
                    attribute_keys=("doublesleep_configuration",),
                ),
                ControllerStateSensorSpec(
                    "doublesleep_alarm",
                    "doublesleep_alarm",
                    "doublesleep_alarm_enabled",
                    "mdi:alarm",
                    attribute_keys=("doublesleep_alarm",),
                ),
                ControllerStateSensorSpec(
                    "doublesleep_light",
                    "doublesleep_light",
                    "doublesleep_light_on",
                    "mdi:lightbulb",
                    attribute_keys=("doublesleep_light_raw",),
                ),
            )
        )
        for domain in (
            ()
            if self.protocol == "p3"
            else ("massage", "sonic")
            if self.protocol == "p2"
            else ("massage",)
        ):
            for key in ("mode", "strength", "head", "foot", "time", "running", "source"):
                if domain == "massage" and key == "source":
                    continue
                name = f"doublesleep_{domain}_{key}"
                specs.append(ControllerStateSensorSpec(name, name, name, "mdi:vibrate"))
        return tuple(specs)

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                f"doublesleep_{side}_{flag}",
                f"doublesleep_{side}_{flag}",
                f"doublesleep_{side}_{flag}",
                "mdi:bed",
            )
            for side in ("left", "right")
            for flag in ("flag1", "flag2")
        )
