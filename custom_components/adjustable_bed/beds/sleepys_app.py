"""Explicit Sleepy's Elite app profile backed by the accepted route table.

This profile is selected by the user. NUS, a characteristic UUID, or a device
name never selects it implicitly.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from bleak.exc import BleakError

from ..command_scheduler import CommandContext, current_command_context
from ..const import (
    SLEEPYS_ELITE_NATIVE_ACTION_MS,
    SLEEPYS_ELITE_SELECTORS,
)
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .sleepys_app_routes import CANONICAL_ROUTE_SHA256, ROUTES, SleepysAppRoute

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.backends.service import BleakGATTService

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_AppFieldValue = int | bool | float
_ParsedValue = _AppFieldValue | dict[str, float]
_BOX25_SELECTORS = frozenset({"BOX25", "BOX25_STAR"})
_STAR_CODE_SELECTOR = "BOX25_STAR"
_POSITION_SLIDER_SELECTORS = frozenset(
    {"none", "BOX15", "BOX24", "BOX1220", "BOX1221", "BOX2422", "BOX2442"}
)
_POSITION_UI_SELECTORS = _POSITION_SLIDER_SELECTORS | _BOX25_SELECTORS
_APP_REFRESH_MS = 100
_APP_HOLD_MIN_MS = 100
_APP_HOLD_MAX_MS = 60_000
_MOTION_SENSOR_REFRESH_MS = 5_000
_DEADLINE_EPSILON_SECONDS = 1e-9
_BOX24_STATE_FIELDS = frozenset(
    {
        "field_0x0b",
        "field_0x13",
        "field_0x1b",
        "field_0x23",
        "field_0x67",
        "field_0x6b",
        "field_0x73",
        "field_0x7b",
        "field_0x83",
    }
)
_APP_STATE_FIELDS_BY_SELECTOR = {
    "none": _BOX24_STATE_FIELDS,
    "BOX15": frozenset(
        {
            "field_0x0b",
            "field_0x13",
            "field_0x1b",
            "field_0x23",
            "field_0x67",
            "field_0x6b",
            "field_0x73",
            "field_0x7b",
            "field_0x83",
        }
    ),
    "BOX24": _BOX24_STATE_FIELDS,
    "BOX1220": _BOX24_STATE_FIELDS,
    "BOX1221": _BOX24_STATE_FIELDS,
    "BOX2422": _BOX24_STATE_FIELDS,
    "BOX2442": _BOX24_STATE_FIELDS,
    "BOX3633": _BOX24_STATE_FIELDS,
    "BOX25": frozenset(
        {
            "field_0x0b",
            "field_0x13",
            "field_0x1b",
            "field_0x23",
            "field_0x43",
            "field_0x47",
            "field_0x4b",
            "field_0x53",
            "field_0x5f",
            "field_0x67",
            "field_0x6b",
            "field_0x73",
            "field_0x7b",
            "field_0x83",
        }
    ),
    "BOX25_STAR": frozenset(
        {
            "field_0x0b",
            "field_0x13",
            "field_0x1b",
            "field_0x23",
            "field_0x43",
            "field_0x47",
            "field_0x4b",
            "field_0x53",
            "field_0x5f",
            "field_0x67",
            "field_0x6b",
            "field_0x73",
            "field_0x7b",
            "field_0x83",
        }
    ),
}
_ALL_APP_STATE_FIELDS = frozenset().union(*_APP_STATE_FIELDS_BY_SELECTOR.values())
_REPEATABLE_BUTTONS = {
    "sleepys_app_program": "program",
    "sleepys_app_reset_memory": "resetMemory",
    "sleepys_app_memory_1": "m1",
    "sleepys_app_memory_2": "m2",
    "sleepys_app_light_on": "turnonUnderbedLighting",
    "sleepys_app_light_off": "turnoffUnderbedLighting",
    "sleepys_app_light_mode": "underbedLighting",
    "sleepys_app_light_brightness_down": "lightReduce",
    "sleepys_app_light_brightness_up": "lightAdd",
    "sleepys_app_rgb_action": "change2RGB",
    "sleepys_app_massage_mode_1": "massageMode1",
    "sleepys_app_massage_mode_2": "massageMode2",
    "sleepys_app_massage_mode_3": "massageMode3",
    "sleepys_app_massage_timer": "massageTimer",
    "sleepys_app_massage_wave_down": "waveReduce",
    "sleepys_app_massage_wave_up": "waveAdd",
    "sleepys_app_massage_foot_down": "footStrengthReduce",
    "sleepys_app_massage_foot_up": "footStrengthAdd",
    "sleepys_app_massage_head_down": "headStrengthReduce",
    "sleepys_app_massage_head_up": "headStrengthAdd",
    "sleepys_app_massage_lumbar_down": "meanwhileStrengthReduce",
    "sleepys_app_massage_lumbar_up": "meanwhileStrengthAdd",
    "sleepys_app_massage_toggle": "massageMode",
    "sleepys_app_massage_off": "massageOff",
    "sleepys_app_massage_on": "massageOn",
    "sleepys_app_save_zero_gravity": "saveZeroGravity",
    "sleepys_app_save_lounge": "saveLounge",
    "sleepys_app_save_tv": "saveTv",
    "sleepys_app_preset_flat": "flatPosition",
    "sleepys_app_preset_snore": "anti",
    "sleepys_app_preset_zero_g": "zeroGravity",
    "sleepys_app_preset_lounge": "lounge",
    "sleepys_app_preset_tv": "tv",
}


def _normalize_uuid(value: str) -> str:
    """Normalize full and short GATT UUID spellings for service lookup."""
    normalized = value.strip().lower()
    if len(normalized) == 4:
        return f"0000{normalized}-0000-1000-8000-00805f9b34fb"
    if len(normalized) == 8:
        return f"{normalized}-0000-1000-8000-00805f9b34fb"
    return normalized


def _same_uuid(left: str, right: str) -> bool:
    return _normalize_uuid(left) == _normalize_uuid(right)


class SleepysEliteAppController(BedController):
    """Controller for one explicitly selected Sleepy's Elite app selector."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        selector: str,
    ) -> None:
        super().__init__(coordinator)
        if selector not in SLEEPYS_ELITE_SELECTORS:
            raise ValueError(f"Unsupported Sleepy's Elite selector: {selector!r}")
        self.selector = selector
        self._notify_characteristic: BleakGATTCharacteristic | None = None
        self._write_characteristic: BleakGATTCharacteristic | None = None
        self._initialized = False
        self._position_data: dict[str, float] = {}
        self._app_fields: dict[str, _AppFieldValue] = {}
        self._massage_intensity = 0
        self._light_level = 0
        self._light_level_known = False
        self._light_color_code = 1
        self._targets: dict[int, int] = {}
        self._last_notify_error: str | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the selected route's write characteristic."""
        return self._route("keepConnect").write_characteristic

    @property
    def requires_notification_channel(self) -> bool:
        """Always subscribe because the app's response parsers use notifications."""
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, str]:
        return {
            "app_profile": "sleepys_elite_app",
            "selector": self.selector,
            "canonical_route_sha256": CANONICAL_ROUTE_SHA256,
        }

    def _route(self, builder: str) -> SleepysAppRoute:
        try:
            return ROUTES[(builder, self.selector)]
        except KeyError as err:
            raise ValueError(
                f"No accepted Sleepy's route for {builder!r}/{self.selector!r}"
            ) from err

    @staticmethod
    def _characteristic(
        client: object,
        service_uuid: str,
        characteristic_uuid: str,
    ) -> BleakGATTCharacteristic:
        """Resolve a characteristic only within its accepted service route."""
        services = getattr(client, "services", None)
        if services is None:
            raise ConnectionError("BLE services are unavailable")

        service = None
        get_service = getattr(services, "get_service", None)
        if callable(get_service):
            service = get_service(service_uuid)
        if service is None:
            for candidate in services:
                if _same_uuid(candidate.uuid, service_uuid):
                    service = candidate
                    break
        if service is None:
            raise ConnectionError(f"Sleepy's service {service_uuid} is unavailable")

        get_characteristic = getattr(service, "get_characteristic", None)
        characteristic = (
            get_characteristic(characteristic_uuid) if callable(get_characteristic) else None
        )
        if characteristic is None:
            characteristic = next(
                (
                    candidate
                    for candidate in cast("BleakGATTService", service).characteristics
                    if _same_uuid(candidate.uuid, characteristic_uuid)
                ),
                None,
            )
        if characteristic is None:
            raise ConnectionError(f"Sleepy's characteristic {characteristic_uuid} is unavailable")
        return cast("BleakGATTCharacteristic", characteristic)

    async def _ensure_initialized(self) -> None:
        """Send the selector's app setup frame and one same-frame error fallback."""
        if self._initialized:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")

        setup = self._route("keepConnect")
        characteristic = self._characteristic(
            client, setup.write_service, setup.write_characteristic
        )
        self._write_characteristic = characteristic
        try:
            await self._write_gatt_with_retry(
                setup.write_characteristic,
                setup.payload,
                response=setup.write_with_response,
                characteristic=characteristic,
                cancel_event=asyncio.Event(),
                log_errors=False,
            )
        except BleakError, OSError, TimeoutError:
            # The app's initial write error callback builds and sends the same
            # setup list once. Keep this separate from ordinary command retries.
            await self._write_gatt_with_retry(
                setup.write_characteristic,
                setup.payload,
                response=setup.write_with_response,
                characteristic=characteristic,
                cancel_event=asyncio.Event(),
            )
        self._initialized = True

    async def _write_route(
        self,
        route: SleepysAppRoute,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = _APP_REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
        wall_clock_pacing: bool = False,
    ) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        await self._ensure_initialized()
        characteristic = self._characteristic(
            client, route.write_service, route.write_characteristic
        )
        if route.builder != "stop":
            context = current_command_context()
            if context is not None:
                # A later value frame means an earlier STOP no longer releases
                # this operation's most recent movement attempt.
                context.cleanup_stop_sent = False
        await self._write_gatt_with_retry(
            route.write_characteristic,
            route.payload,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=route.write_with_response,
            characteristic=characteristic,
            wall_clock_pacing=wall_clock_pacing,
        )

    async def send(self, builder: str) -> None:
        """Send one accepted static route for this selector."""
        await self._write_route(self._route(builder))

    async def _send_dynamic(self, builder: str, values: tuple[int, ...]) -> None:
        """Serialize an accepted logical formula using the selector route's ABI."""
        route = self._route(builder)
        if any(not 0 <= value <= 0xFF for value in values):
            raise ValueError("Sleepy's logical command values must be bytes")
        payload = bytes(values)
        await self._write_route(
            SleepysAppRoute(
                builder=route.builder,
                selector=route.selector,
                logical_values=values,
                payload=payload,
                write_service=route.write_service,
                write_characteristic=route.write_characteristic,
                notify_target=route.notify_target,
                write_with_response=route.write_with_response,
                response_parser=route.response_parser,
            )
        )

    async def _send_with_cleanup(
        self,
        builder: str,
        *,
        acknowledge_context: CommandContext | None = None,
    ) -> bool:
        """Send and settle a release with a fresh event, even after cancellation."""
        client = self.client
        if client is None or not client.is_connected:
            return False

        release = asyncio.create_task(
            self._write_route(self._route(builder), cancel_event=asyncio.Event())
        )
        caller_cancelled = False
        while not release.done():
            try:
                await asyncio.shield(release)
            except asyncio.CancelledError:
                if release.cancelled():
                    break
                caller_cancelled = True
            except Exception:
                break

        # Surface a failed write before acknowledging it or propagating a
        # cancellation received while the write was being drained.
        release.result()
        if acknowledge_context is not None:
            acknowledge_context.cleanup_stop_sent = True
        if caller_cancelled:
            raise asyncio.CancelledError
        return True

    async def _wait_until_or_cancel(
        self,
        when: float,
        deadline: float,
        cancel_event: asyncio.Event,
    ) -> bool:
        """Wait for a refresh slot without sleeping past cancellation or deadline."""
        now = self._monotonic()
        if cancel_event.is_set() or now >= deadline - _DEADLINE_EPSILON_SECONDS:
            return False
        remaining = min(when, deadline) - now
        if remaining <= 0:
            return True

        timer = asyncio.create_task(self._sleep(remaining))
        cancelled = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait((timer, cancelled), return_when=asyncio.FIRST_COMPLETED)
            return (
                timer in done
                and not cancel_event.is_set()
                and self._monotonic() < deadline - _DEADLINE_EPSILON_SECONDS
            )
        finally:
            for task in (timer, cancelled):
                if not task.done():
                    task.cancel()
            await asyncio.gather(timer, cancelled, return_exceptions=True)

    def _monotonic(self) -> float:
        return asyncio.get_running_loop().time()

    async def _sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _write_route_before_deadline(
        self,
        route: SleepysAppRoute,
        deadline: float,
        cancel_event: asyncio.Event,
    ) -> bool:
        """Bound one pending acknowledged write and cancel it at the active deadline."""
        remaining = deadline - self._monotonic()
        if remaining <= _DEADLINE_EPSILON_SECONDS or cancel_event.is_set():
            return False

        async def write() -> None:
            await self._write_route(route, cancel_event=cancel_event)

        write_task = asyncio.create_task(write())
        deadline_task = asyncio.create_task(self._sleep(remaining))
        cancelled = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                (write_task, deadline_task, cancelled),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if write_task in done:
                await write_task
                return not cancel_event.is_set()
            return False
        finally:
            for task in (write_task, deadline_task, cancelled):
                if not task.done():
                    task.cancel()
            await asyncio.gather(write_task, deadline_task, cancelled, return_exceptions=True)

    async def _run_refresh_window(
        self,
        route: SleepysAppRoute,
        duration_ms: int,
        *,
        release: bool,
    ) -> None:
        """Refresh at the accepted cadence for an elapsed window, then release once."""
        now = self._monotonic()
        cancel_event = self._coordinator.cancel_command
        deadline = now + duration_ms / 1000
        next_refresh = now
        context = current_command_context()
        failed = False
        try:
            while await self._wait_until_or_cancel(next_refresh, deadline, cancel_event):
                started = self._monotonic()
                if started >= deadline - _DEADLINE_EPSILON_SECONDS:
                    break
                if not await self._write_route_before_deadline(route, deadline, cancel_event):
                    break
                now = self._monotonic()
                if cancel_event.is_set() or now >= deadline - _DEADLINE_EPSILON_SECONDS:
                    break
                next_refresh = now + _APP_REFRESH_MS / 1000
        except BaseException:
            failed = True
            raise
        finally:
            if release:
                try:
                    await self._send_with_cleanup("stop", acknowledge_context=context)
                except Exception:
                    if not failed:
                        raise
                    _LOGGER.debug("Sleepy's STOP cleanup failed", exc_info=True)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Refresh one held app action until its elapsed deadline, then send STOP."""
        self.validate_hold_control(control, duration_ms)
        await self._run_refresh_window(self._route(control), duration_ms, release=True)

    async def set_motion_sensor(self, *, enabled: bool) -> None:
        """Run the app's cancellable five-second sensor refresh without STOP."""
        builder = "motionSensorOn" if enabled else "motionSensorOff"
        await self._run_refresh_window(
            self._route(builder), _MOTION_SENSOR_REFRESH_MS, release=False
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Set up the chosen route, then subscribe to its response characteristic."""
        del callback  # Response axes remain raw until a physical mapping is proven.
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to bed")
        await self._ensure_initialized()

        route = self._route("keepConnect")
        service_uuid, characteristic_uuid = route.notify_target.split("/", 1)
        self._notify_characteristic = self._characteristic(
            client, service_uuid, characteristic_uuid
        )
        await client.start_notify(self._notify_characteristic, self._handle_notification)

    async def stop_notify(self) -> None:
        """Remove the selected response subscription on the current connection."""
        client = self.client
        if client is not None and client.is_connected and self._notify_characteristic is not None:
            try:
                await client.stop_notify(self._notify_characteristic)
            except BleakError:
                _LOGGER.debug("Could not stop Sleepy's notification subscription", exc_info=True)
        self._notify_characteristic = None

    def on_disconnect(self) -> None:
        """Invalidate callbacks and connection-local initialization immediately."""
        self._notify_characteristic = None
        self._write_characteristic = None
        self._initialized = False

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a single route frame with its accepted selector mode."""
        route = self._route("keepConnect")
        await self._write_gatt_with_retry(
            route.write_characteristic,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=route.write_with_response,
            characteristic=self._write_characteristic,
        )

    def _handle_notification(
        self,
        characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        """Parse only fully validated frames and apply updates atomically."""
        client = self.client
        if (
            client is None
            or not client.is_connected
            or self._notify_characteristic is not characteristic
        ):
            return
        raw = bytes(data)
        self.forward_raw_notification(characteristic.uuid, raw)
        updates = self._parse_notification(raw)
        if updates is None:
            return

        positions = cast(dict[str, float] | None, updates.pop("_positions", None))
        if positions is not None:
            for axis, value in positions.items():
                self._position_data[axis] = value
                updates[f"position_{axis}"] = value
        if updates:
            state_updates: dict[str, int | float | str] = {}
            for key, value in updates.items():
                if not isinstance(value, (int, bool, float)):
                    continue
                timer_code = value if type(value) is int else None
                self._app_fields[key] = value
                if isinstance(value, bool):
                    value = int(value)
                state_updates[f"sleepys_app_{key}"] = value
                if (
                    key == "field_0x0b"
                    and self.supports_massage
                    and timer_code is not None
                    and 1 <= timer_code <= 3
                ):
                    state_updates["sleepys_app_massage_timer_code"] = str(timer_code)
            self.forward_controller_state_updates(state_updates)

    def _parse_notification(self, raw: bytes) -> dict[str, _ParsedValue] | None:
        """Decode a complete accepted parser branch without partial state writes."""
        if self.selector == "BOX15":
            if len(raw) > 3 and raw[:2] == b"\xed\x80":
                if len(raw) < 7:
                    return None
                return {
                    "field_0x6b": raw[3],
                    "field_0x83": raw[5],
                    "field_0x73": raw[4],
                    "field_0x7b": raw[6],
                    "field_0x67": any((raw[3], raw[5], raw[4], raw[6])),
                }
            if len(raw) == 23:
                return {
                    "field_0x0b": raw[19] & 0x0F,
                    "field_0x13": _box15_norm(raw[11] & 0x07),
                    "field_0x1b": _box15_norm(raw[12]),
                    "field_0x23": raw[21],
                }
            if len(raw) == 16:
                return {
                    "field_0x0b": raw[14] & 0x0F,
                    "field_0x23": raw[14] >> 4,
                    "field_0x13": _box15_norm(raw[7]),
                    "field_0x1b": _box15_norm(raw[8]),
                }
            if len(raw) == 10:
                return {
                    "field_0x0b": raw[8] & 0x0F,
                    "field_0x23": 1,
                    "field_0x13": 0,
                    "field_0x1b": 0,
                }
            return None

        if self.selector in _BOX25_SELECTORS:
            if raw[:2] == b"\xa5\x0c":
                if len(raw) < 8:
                    return None
                values: dict[str, int | bool | float | dict[str, float]] = _status_fields(raw)
                return values
            if raw[:2] == b"\xa5\x0b":
                if len(raw) < 16:
                    return None
                seconds = (raw[4] << 8) | raw[5]
                code = 0 if seconds <= 0 or seconds > 1800 else min(3, (seconds + 599) // 600)
                return {
                    "field_0x0b": code,
                    "field_0x23": raw[6] & 0x0F,
                    "field_0x13": raw[7] & 0x0F,
                    "field_0x1b": raw[7] & 0x0F,
                    "field_0x53": raw[14] >> 4,
                    "field_0x4b": raw[14] & 0x0F,
                    "field_0x47": (raw[14] & 0x0F) > 0,
                    "field_0x43": (raw[15] >> 4) == 1,
                }
            if raw[:2] == b"\xa5\x0d":
                if len(raw) < 19:
                    return None
                return {
                    "_positions": {
                        "axis_0": float(min(100, raw[4])),
                        "axis_1": float(min(100, raw[6])),
                        "axis_2": float(min(100, raw[8])),
                    },
                    "field_0x5f": raw[17] == 0,
                }
            return None

        if raw[:2] == b"\xa5\x0c":
            if len(raw) < 8:
                return None
            return _status_fields(raw)
        if raw[:3] == b"\xa5\x0b\x0e":
            if len(raw) < 9:
                return None
            seconds = (raw[4] << 8) | raw[5]
            code = 0 if seconds <= 0 or seconds > 1800 else min(3, (seconds + 599) // 600)
            return {
                "field_0x0b": code * 10,
                "field_0x23": raw[6] - 1,
                "field_0x13": _conv3(raw[7] & 0x0F),
                "field_0x1b": raw[8],
            }
        return None

    @property
    def supports_position_feedback(self) -> bool:
        # The app reports three axes, but the accepted parser evidence does not
        # map them to this integration's named motor positions.
        return False

    @property
    def reports_percentage_position(self) -> bool:
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
    def supports_preset_lounge(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return self.selector in _BOX25_SELECTORS

    @property
    def supports_under_bed_lights(self) -> bool:
        return self.supports_lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def light_state_is_assumed(self) -> bool:
        return self.supports_lights

    @property
    def supports_massage(self) -> bool:
        return self.selector in _BOX25_SELECTORS

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.supports_massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["all"] if self.supports_massage else []

    @property
    def massage_intensity_max(self) -> int:
        return 7

    @property
    def supports_massage_timer(self) -> bool:
        # The app sends opaque codes 1/2/3, not minute durations.
        return False

    @property
    def massage_timer_options(self) -> list[int]:
        return []

    @property
    def supports_light_level_control(self) -> bool:
        return self.supports_lights

    @property
    def light_level_max(self) -> int:
        return 6

    @property
    def held_control_options(self) -> tuple[str, ...]:
        controls = [
            control
            for spec in self.motor_control_specs
            if spec.hold is not None
            for control in (spec.hold.up_control, spec.hold.down_control)
        ]
        controls.extend(
            spec.hold.control for spec in self.controller_button_specs if spec.hold is not None
        )
        return tuple(dict.fromkeys(controls))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported Sleepy's held control: {control!r}")
        if not _APP_HOLD_MIN_MS <= duration_ms <= _APP_HOLD_MAX_MS:
            raise ValueError("Sleepy's held control duration must be 100-60000 ms")

    def _value_route(self, control: str, value: float) -> SleepysAppRoute:
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("Sleepy's value controls accept whole numbers only")
        code = int(value)
        if control.startswith("position_axis_"):
            axis_text = control.removeprefix("position_axis_")
            if (
                axis_text not in {"0", "1", "2"}
                or self.selector not in _POSITION_UI_SELECTORS
                or not 0 <= code <= 200
            ):
                raise ValueError(f"Unsupported Sleepy's value control: {control!r}")
            axis = int(axis_text)
            if self.selector == _STAR_CODE_SELECTOR:
                logical = (90, 240, 3, axis, code, 0, 165)
            else:
                logical = (3, 240, axis, code, 0)
            builder = "changePosition"
        elif control == "light_level":
            if not self.supports_lights or not 0 <= code <= 6:
                raise ValueError("Sleepy's light level must be between 0 and 6")
            logical = (
                (90, 224, 4, 0, code, 0, 0, 165)
                if self.selector == _STAR_CODE_SELECTOR
                else (4, 224, 0, code, 0, 0)
            )
            builder = "changeLightBrightness"
        elif control == "light_color_code":
            if not self.supports_lights or not 1 <= code <= 7:
                raise ValueError("Sleepy's current color control accepts codes 1 to 7")
            logical = (
                (90, 224, 4, 1, code, 0, 0, 165)
                if self.selector == _STAR_CODE_SELECTOR
                else (4, 224, 1, code, 0, 0)
            )
            builder = "changeLightColorLevel"
        elif control == "massage_timer_code":
            if not self.supports_massage or code not in (1, 2, 3):
                raise ValueError("Sleepy's massage timer code must be 1, 2, or 3")
            logical = (
                (90, 224, 4, 7, code, 0, 0, 165)
                if self.selector == _STAR_CODE_SELECTOR
                else (4, 224, 7, code, 0, 0)
            )
            builder = "changeMassageTime"
        elif control == "massage_intensity_all":
            if not self.supports_massage or not 0 <= code <= 7:
                raise ValueError("Sleepy's combined massage intensity must be 0 to 7")
            intensity = 0 if code == 0 else code + 1
            logical = (
                (90, 224, 4, 6, intensity, intensity, 0, 165)
                if self.selector == _STAR_CODE_SELECTOR
                else (4, 224, 6, intensity, intensity, 0)
            )
            builder = "changeMassageIntensity"
        else:
            raise ValueError(f"Unsupported Sleepy's value control: {control!r}")

        route = self._route(builder)
        return replace(route, logical_values=logical, payload=bytes(logical))

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=lambda ctrl, builder=up: cast(SleepysEliteAppController, ctrl).send(
                    builder
                ),
                close_fn=lambda ctrl, builder=down: cast(SleepysEliteAppController, ctrl).send(
                    builder
                ),
                stop_fn=lambda ctrl: cast(SleepysEliteAppController, ctrl).stop_all(),
                max_angle=100,
                hold=ControllerMotorHoldSpec(
                    up_control=up,
                    down_control=down,
                    start_delay_ms=_APP_HOLD_MIN_MS,
                    release_delay_ms=_APP_REFRESH_MS,
                ),
            )
            for axis, up, down in (
                ("head", "headUp", "headDown"),
                ("feet", "footUp", "footDown"),
                ("lumbar", "lumbarUp", "lumbarDown"),
                ("neck", "neckTiltUp", "neckTiltDown"),
            )
            if (up, self.selector) in ROUTES and (down, self.selector) in ROUTES
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self.selector in _POSITION_UI_SELECTORS:
            for axis in range(3):
                key = f"sleepys_app_target_axis_{axis}"
                specs.append(
                    ControllerNumberSpec(
                        key=key,
                        translation_key=key,
                        state_key=key,
                        native_min_value=0,
                        native_max_value=100,
                        native_step=1,
                        set_fn=lambda ctrl, value, axis=axis: cast(
                            SleepysEliteAppController, ctrl
                        ).set_position_target(axis, int(value)),
                    )
                )
        if self.supports_lights:
            specs.append(
                ControllerNumberSpec(
                    key="light_level",
                    translation_key="light_level",
                    state_key="light_level",
                    native_min_value=0,
                    native_max_value=6,
                    native_step=1,
                    set_fn=lambda ctrl, value: cast(
                        SleepysEliteAppController, ctrl
                    ).set_light_slider_value(int(value)),
                )
            )
            specs.append(
                ControllerNumberSpec(
                    key="sleepys_app_color_code",
                    translation_key="sleepys_app_color_code",
                    state_key="sleepys_app_color_code",
                    native_min_value=1,
                    native_max_value=7,
                    native_step=1,
                    set_fn=lambda ctrl, value: cast(
                        SleepysEliteAppController, ctrl
                    ).set_light_color_code(int(value)),
                )
            )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.supports_massage:
            return ()
        options = ("1", "2", "3")
        return (
            ControllerSelectSpec(
                key="sleepys_app_massage_timer_code",
                translation_key="sleepys_app_massage_timer_code",
                state_key="sleepys_app_massage_timer_code",
                options=options,
                select_fn=lambda ctrl, value: cast(
                    SleepysEliteAppController, ctrl
                ).set_massage_timer_code(int(value)),
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec] = []
        app_actions = {
            "sleepys_app_program": ("program", "Program", "mdi:content-save-outline"),
            "sleepys_app_reset_memory": ("resetMemory", "Reset memory", "mdi:backup-restore"),
            "sleepys_app_voice_stop": ("voiceStop", "Voice stop", "mdi:stop-circle-outline"),
            "sleepys_app_query_position": (
                "queryPosition",
                "Refresh position state",
                "mdi:refresh",
            ),
            "sleepys_app_memory_1": ("m1", "Memory 1", "mdi:numeric-1-box"),
            "sleepys_app_memory_2": ("m2", "Memory 2", "mdi:numeric-2-box"),
            "sleepys_app_save_zero_gravity": (
                "saveZeroGravity",
                "Save zero gravity",
                "mdi:content-save",
            ),
            "sleepys_app_save_lounge": ("saveLounge", "Save lounge", "mdi:content-save"),
            "sleepys_app_save_tv": ("saveTv", "Save TV", "mdi:content-save"),
            "sleepys_app_preset_flat": ("flatPosition", "Flat", "mdi:bed"),
            "sleepys_app_preset_snore": ("anti", "Anti-snore", "mdi:sleep-off"),
            "sleepys_app_preset_zero_g": ("zeroGravity", "Zero gravity", "mdi:rocket-launch"),
            "sleepys_app_preset_lounge": ("lounge", "Lounge", "mdi:seat-recline-normal"),
            "sleepys_app_preset_tv": ("tv", "TV", "mdi:television"),
            "sleepys_app_motion_sensor_on": (
                "motionSensorOn",
                "Motion sensor on",
                "mdi:motion-sensor",
            ),
            "sleepys_app_motion_sensor_off": (
                "motionSensorOff",
                "Motion sensor off",
                "mdi:motion-sensor-off",
            ),
        }
        if self.selector in _BOX25_SELECTORS:
            app_actions.update(
                {
                    "sleepys_app_light_on": (
                        "turnonUnderbedLighting",
                        "Light on",
                        "mdi:lightbulb-on",
                    ),
                    "sleepys_app_light_off": (
                        "turnoffUnderbedLighting",
                        "Light off",
                        "mdi:lightbulb-off",
                    ),
                    "sleepys_app_light_mode": (
                        "underbedLighting",
                        "Light mode",
                        "mdi:lightbulb-multiple",
                    ),
                    "sleepys_app_light_brightness_down": (
                        "lightReduce",
                        "Reduce light",
                        "mdi:brightness-5",
                    ),
                    "sleepys_app_light_brightness_up": (
                        "lightAdd",
                        "Increase light",
                        "mdi:brightness-7",
                    ),
                    "sleepys_app_rgb_action": ("change2RGB", "RGB action", "mdi:palette"),
                    "sleepys_app_massage_mode_1": ("massageMode1", "Massage mode 1", "mdi:vibrate"),
                    "sleepys_app_massage_mode_2": ("massageMode2", "Massage mode 2", "mdi:vibrate"),
                    "sleepys_app_massage_mode_3": ("massageMode3", "Massage mode 3", "mdi:vibrate"),
                    "sleepys_app_massage_query": (
                        "queryMassage",
                        "Refresh massage state",
                        "mdi:refresh",
                    ),
                    "sleepys_app_massage_timer": (
                        "massageTimer",
                        "Massage timer",
                        "mdi:timer-outline",
                    ),
                    "sleepys_app_massage_wave_down": (
                        "waveReduce",
                        "Previous massage wave",
                        "mdi:chevron-left",
                    ),
                    "sleepys_app_massage_wave_up": (
                        "waveAdd",
                        "Next massage wave",
                        "mdi:chevron-right",
                    ),
                    "sleepys_app_massage_foot_down": (
                        "footStrengthReduce",
                        "Reduce foot massage",
                        "mdi:chevron-down",
                    ),
                    "sleepys_app_massage_foot_up": (
                        "footStrengthAdd",
                        "Increase foot massage",
                        "mdi:chevron-up",
                    ),
                    "sleepys_app_massage_head_down": (
                        "headStrengthReduce",
                        "Reduce head massage",
                        "mdi:chevron-down",
                    ),
                    "sleepys_app_massage_head_up": (
                        "headStrengthAdd",
                        "Increase head massage",
                        "mdi:chevron-up",
                    ),
                    "sleepys_app_massage_lumbar_down": (
                        "meanwhileStrengthReduce",
                        "Reduce lumbar massage",
                        "mdi:chevron-down",
                    ),
                    "sleepys_app_massage_lumbar_up": (
                        "meanwhileStrengthAdd",
                        "Increase lumbar massage",
                        "mdi:chevron-up",
                    ),
                    "sleepys_app_massage_toggle": ("massageMode", "Massage mode", "mdi:vibrate"),
                    "sleepys_app_massage_off": ("massageOff", "Massage off", "mdi:vibrate-off"),
                    "sleepys_app_massage_on": ("massageOn", "Massage on", "mdi:vibrate"),
                }
            )

        for key, (builder, name, icon) in app_actions.items():
            if (builder, self.selector) not in ROUTES:
                continue
            specs.append(
                ControllerButtonSpec(
                    key=key,
                    name=name,
                    translation_key=key,
                    icon=icon,
                    press_fn=lambda ctrl, key=key, builder=builder: cast(
                        SleepysEliteAppController, ctrl
                    )._press_app_action(key, builder),
                    hold=(
                        ControllerHoldSpec(
                            control=builder,
                            start_delay_ms=_APP_HOLD_MIN_MS,
                            release_delay_ms=_APP_REFRESH_MS,
                        )
                        if key in _REPEATABLE_BUTTONS
                        else None
                    ),
                )
            )

        if self.selector in _BOX25_SELECTORS:
            for delta, direction in ((-1, "down"), (1, "up")):
                key = f"sleepys_app_voice_brightness_{direction}"
                specs.append(
                    ControllerButtonSpec(
                        key=key,
                        name=f"Brightness {direction} by one",
                        translation_key=key,
                        icon="mdi:brightness-6",
                        press_fn=lambda ctrl, delta=delta: cast(
                            SleepysEliteAppController, ctrl
                        ).adjust_light_level(delta),
                    )
                )
            for axis in range(3):
                for target in (100, 0):
                    key = f"sleepys_app_voice_axis_{axis}_{target}"
                    specs.append(
                        ControllerButtonSpec(
                            key=key,
                            name=f"Position axis {axis} target {target}",
                            translation_key=key,
                            icon="mdi:bed-outline",
                            press_fn=lambda ctrl, axis=axis, target=target: cast(
                                SleepysEliteAppController, ctrl
                            ).set_position_target(axis, target),
                        )
                    )
        return tuple(specs)

    async def _press_app_action(self, key: str, builder: str) -> None:
        if key == "sleepys_app_motion_sensor_on":
            await self.set_motion_sensor(enabled=True)
        elif key == "sleepys_app_motion_sensor_off":
            await self.set_motion_sensor(enabled=False)
        elif key in _REPEATABLE_BUTTONS:
            await self._run_refresh_window(
                self._route(builder), SLEEPYS_ELITE_NATIVE_ACTION_MS, release=True
            )
        else:
            await self.send(builder)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                key=f"sleepys_app_{field}",
                translation_key=f"sleepys_app_{field}",
                state_key=f"sleepys_app_{field}",
                icon="mdi:code-braces",
            )
            for field in sorted(_APP_STATE_FIELDS_BY_SELECTOR.get(self.selector, ()))
        ]
        if self.selector in _BOX25_SELECTORS:
            specs.extend(
                ControllerStateSensorSpec(
                    key=f"sleepys_app_position_axis_{axis}",
                    translation_key=f"sleepys_app_position_axis_{axis}",
                    state_key=f"sleepys_app_position_axis_{axis}",
                    icon="mdi:bed-outline",
                    native_unit_of_measurement="%",
                    suggested_display_precision=0,
                )
                for axis in range(3)
            )
        return tuple(specs)

    @property
    def stale_controller_state_sensor_entity_keys(self) -> frozenset[str]:
        active = {spec.key for spec in self.controller_state_sensor_specs}
        return frozenset(
            {
                *(f"sleepys_app_position_axis_{axis}" for axis in range(3)),
                *(f"sleepys_app_{field}" for field in _ALL_APP_STATE_FIELDS),
            }
            - active
        )

    async def set_position_target(self, axis: int, target: int) -> None:
        if self.selector not in _POSITION_UI_SELECTORS:
            raise ValueError("Sleepy's position targets are unavailable for this selector")
        if axis not in range(3):
            raise ValueError("Unsupported Sleepy's position target")
        if not 0 <= target <= 100:
            raise ValueError("Sleepy's position target must be between 0 and 100")

        if self.selector not in _POSITION_SLIDER_SELECTORS:
            # BOX25 voice and UI value calls are one-shot.
            await self._send_position_value(axis, target)
            return

        context = current_command_context()
        release_sent = False
        failed = False
        try:
            await self._send_position_value(axis, target)
        except BaseException:
            failed = True
            raise
        finally:
            try:
                release_sent = await self._send_with_cleanup("stop", acknowledge_context=context)
            except Exception:
                if not failed:
                    raise
                _LOGGER.debug("Sleepy's position STOP cleanup failed", exc_info=True)
        # The seven position36 selectors end their finite HA commit with STOP,
        # then issue the source's separately guarded midpoint target as another
        # value write. HA has no separate drag-end callback, so the commit is
        # treated as a complete value interaction. The STOP does not imply that
        # midpoint50 is harmless or that it is a STOP frame.
        if release_sent:
            try:
                await self._send_position_value(axis, 50)
            except BaseException:
                # The preceding STOP cannot release this later movement attempt.
                # Settle a fresh release on the same serialized operation.
                try:
                    await self._send_with_cleanup("stop", acknowledge_context=context)
                except BaseException:
                    _LOGGER.debug("Sleepy's midpoint STOP cleanup failed", exc_info=True)
                raise

    async def _send_position_value(self, axis: int, target: int) -> None:
        route = self._value_route(f"position_axis_{axis}", float(target))
        await self._send_dynamic(route.builder, route.logical_values)
        self._targets[axis] = target
        self.forward_controller_state_updates({f"sleepys_app_target_axis_{axis}": target})

    async def set_light_level(self, level: int) -> None:
        """Send the controller-level brightness value, including voice value zero."""
        route = self._value_route("light_level", float(level))
        await self._send_dynamic(route.builder, route.logical_values)
        self._light_level = level
        self._light_level_known = True
        self.forward_controller_state_updates({"light_level": level})

    async def set_light_slider_value(self, level: int) -> None:
        """Adapt the HA slider's zero endpoint to the separate light-off route."""
        if not 0 <= level <= self.light_level_max:
            raise ValueError("Sleepy's light level must be between 0 and 6")
        if not self._light_ui_enabled():
            raise ValueError("Sleepy's light slider requires enabled under-bed lighting")
        if level == 0:
            await self.lights_off()
            return
        await self.set_light_level(level)

    async def adjust_light_level(self, delta: int) -> None:
        """Provide the source's one-step brightness caller as an HA button."""
        if delta not in (-1, 1):
            raise ValueError("Sleepy's brightness adjustment must be one step")
        if not self._light_level_known:
            return
        candidate = self._light_level + delta
        level = candidate if 0 <= candidate <= self.light_level_max else self._light_level
        await self.set_light_level(level)

    async def set_light_color_code(self, code: int) -> None:
        route = self._value_route("light_color_code", float(code))
        if not self._light_ui_enabled():
            raise ValueError("Sleepy's light palette requires enabled under-bed lighting")
        await self._send_dynamic(route.builder, route.logical_values)
        self._light_color_code = code
        self.forward_controller_state_updates({"sleepys_app_color_code": code})

    async def set_massage_timer_code(self, code: int) -> None:
        route = self._value_route("massage_timer_code", float(code))
        if not self._massage_is_active():
            raise ValueError("Sleepy's massage timer requires active massage")
        if self._app_fields.get("field_0x0b") == code:
            return
        # The app's interruptByOther event clears pending position events only.
        # HA value commits have no app gesture queue to retain or replay.
        await self._send_dynamic(route.builder, route.logical_values)
        self._app_fields["field_0x0b"] = code
        self.forward_controller_state_updates({"sleepys_app_massage_timer_code": str(code)})

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone != "all":
            raise ValueError("Sleepy's exposes one all-zone massage intensity")
        route = self._value_route("massage_intensity_all", float(level))
        if not self._massage_is_active():
            raise ValueError("Sleepy's massage intensity requires active massage")
        # Event4 clears queued position events. It does not reset a running
        # axis, transition state, or send a STOP frame.
        await self._send_dynamic(route.builder, route.logical_values)
        self._massage_intensity = level
        self.forward_controller_state_updates({"sleepys_massage_intensity": level})

    def _massage_is_active(self) -> bool:
        active = self._app_fields.get("field_0x4b")
        return active is True or (type(active) is int and active > 0)

    def _light_ui_enabled(self) -> bool:
        enabled = self._app_fields.get("field_0x53")
        return enabled is True or (type(enabled) is int and enabled > 0)

    def get_light_state(self) -> dict[str, int]:
        return (
            {"light_level": self._light_level}
            if self.supports_lights and self._light_level_known
            else {}
        )

    def get_massage_state(self) -> dict[str, int]:
        return {"intensity": self._massage_intensity} if self.supports_massage else {}

    async def lights_on(self) -> None:
        await self.send("turnonUnderbedLighting")

    async def lights_off(self) -> None:
        await self.send("turnoffUnderbedLighting")
        self._light_level = 0
        self._light_level_known = True
        self.forward_controller_state_updates({"light_level": 0})

    async def massage_on(self) -> None:
        if not self.supports_massage:
            await super().massage_toggle()
        await self.send("massageOn")

    async def massage_off(self) -> None:
        if not self.supports_massage:
            await super().massage_off()
        await self.send("massageOff")

    async def massage_toggle(self) -> None:
        if not self.supports_massage:
            await super().massage_toggle()
        await self.send("massageMode")

    async def move_head_up(self) -> None:
        await self.send("headUp")

    async def move_head_down(self) -> None:
        await self.send("headDown")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.send("footUp")

    async def move_legs_down(self) -> None:
        await self.send("footDown")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.send("lumbarUp")

    async def move_lumbar_down(self) -> None:
        await self.send("lumbarDown")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._send_with_cleanup("stop")

    async def preset_flat(self) -> None:
        await self.send("flatPosition")

    async def preset_memory(self, memory_num: int) -> None:
        builder = {1: "m1", 2: "m2"}.get(memory_num)
        if builder is None:
            raise ValueError("Sleepy's Elite has two app memory slots")
        await self.send(builder)

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Sleepy's Elite app routes do not save memory slots")

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        if ("queryPosition", self.selector) in ROUTES:
            await self.send("queryPosition")


def _box15_norm(value: int) -> int:
    if value == 3:
        return 2
    if value == 6:
        return 3
    return value


def _conv3(value: int) -> int:
    return value % 3 + value // 3 + (1 if value > 1 else 0)


def _status_fields(raw: bytes) -> dict[str, _ParsedValue]:
    field_7b = {10: 17, 12: 19}.get(raw[5], 9)
    field_83 = raw[4]
    return {
        "field_0x6b": raw[6],
        "field_0x83": field_83,
        "field_0x73": raw[7],
        "field_0x7b": field_7b,
        "field_0x67": field_83 != 0,
    }
