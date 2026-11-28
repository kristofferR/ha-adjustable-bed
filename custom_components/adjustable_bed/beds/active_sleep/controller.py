"""Active Sleep local controls, admitted by live replies on one authenticated link."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory

from ...card import CARD_HIDDEN, CARD_UTILITY
from ...codec import active_sleep as codec
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid, keyed
from ...execution import HOLD_CEILING_MS
from ...profiles.active_sleep import ACTIVE_SLEEP, AUTH_ID, BED_TEMPLATES, MATTRESS_TEMPLATES
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
    sleep_rate_sensor_spec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MONITOR: Final = StateKey[bool | None]("active_sleep_monitor")
MODEL: Final = StateKey[str | None]("active_sleep_model")
SERIAL: Final = StateKey[str | None]("active_sleep_serial")
HEIGHT: Final = StateKey[int | None]("active_sleep_height")
TILT: Final = StateKey[int | None]("active_sleep_tilt")
HEART: Final = StateKey[int | None]("active_sleep_heart")
RESPIRATION: Final = StateKey[int | None]("active_sleep_respiration")
RAW: Final = StateKey[str | None]("active_sleep_respiration_raw_feed")
FAIL: Final = StateKey[int | None]("active_sleep_failure")
WARNING: Final = StateKey[bool | None]("active_sleep_height_warning")
FAST: Final = StateKey[str | None]("active_sleep_speed")
MODE: Final = StateKey[str | None]("active_sleep_mattress_mode")
VENTILATION: Final = StateKey[bool | None]("active_sleep_ventilation")
FUKATTO: Final = StateKey[bool | None]("active_sleep_fukatto")
REMAINING: Final = StateKey[int | None]("active_sleep_ventilation_remaining")
BUSY: Final = StateKey[int | None]("active_sleep_mattress_busy")
LOCK_KEYS: Final = {
    axis: StateKey[bool | None](f"active_sleep_lock_{axis}") for axis in codec.LOCKS
}
ZONE_KEYS: Final = {
    zone: StateKey[int | None](f"active_sleep_pressure_{zone}") for zone in codec.ZONES
}


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    characteristic: BleakGATTCharacteristic
    epoch: object
    token: str


async def action(controller: BedController, name: str) -> None:
    await require_controller(controller, ActiveSleepController).press(name)


class ActiveSleepController(ProfileExecution, BedController):
    """No command, reply, warning acknowledgement or cleanup survives its link."""

    profile = ACTIVE_SLEEP

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        token: str = "",
        snapshot: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._bed_templates = list(BED_TEMPLATES)
        self._mattress_templates: list[tuple[tuple[int, ...], int]] = list(MATTRESS_TEMPLATES)
        self._token = token
        self._link: Link | None = None
        self._epoch = object()
        self._authenticated = False
        self._receiver = codec.Receiver()
        self._pending: tuple[int, asyncio.Future[codec.Reply]] | None = None
        self._poisoned = False
        self._spec: codec.Spec | None = None
        self._bed_spec: codec.BedSpec | None = None
        self._position: codec.Position | None = None
        self._mattress: codec.Mattress | None = None
        self._monitor = False
        self._last_poll = 0.0
        self._last_sequence = -1
        self._last_change = monotonic()
        self._acknowledged = False
        self._warned = False
        self._wire_lock = asyncio.Lock()
        if snapshot:
            spec, limits = snapshot.get("spec"), snapshot.get("limits")
            if isinstance(spec, str) and isinstance(limits, str):
                try:
                    raw_spec, raw_limits = bytes.fromhex(spec), bytes.fromhex(limits)
                    if len(raw_spec) == 9 and len(raw_limits) == 9:
                        self._spec = codec.Spec.parse(raw_spec)
                        self._bed_spec = codec.BedSpec.parse(raw_limits)
                except ValueError:
                    pass
        self._spec_bytes = b""
        self._limit_bytes = b""

    @property
    def persisted_app_state(self) -> dict[str, object]:
        return {
            "bed_templates": [list(p) for p in self._bed_templates],
            "mattress_templates": [list(zones) for zones, _ in self._mattress_templates],
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        beds, mattresses = state.get("bed_templates"), state.get("mattress_templates")
        if isinstance(beds, list) and len(beds) == 10:
            for i, row in enumerate(beds):
                if (
                    isinstance(row, list)
                    and len(row) == 4
                    and all(type(v) is int and -128 <= v <= 255 for v in row)
                ):
                    self._bed_templates[i] = (row[0], row[1], row[2], row[3])
        if isinstance(mattresses, list) and len(mattresses) == 5:
            for i, row in enumerate(mattresses):
                if (
                    isinstance(row, list)
                    and len(row) == 6
                    and all(type(v) is int and 0 <= v <= 15 for v in row)
                ):
                    self._mattress_templates[i] = (tuple(row), MATTRESS_TEMPLATES[i][1])

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._live(auth=True)
        if self._spec is None or self._spec.mode != 0:
            raise invalid("active_sleep_normal_mode_required")

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {"spec": self._spec_bytes.hex(), "limits": self._limit_bytes.hex()}

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
    def supports_motor_control(self) -> bool:
        return bool(self._axes())

    @property
    def supports_position_feedback(self) -> bool:
        return bool(self._axes())

    def _axes(self) -> tuple[str, ...]:
        spec, limits = self._spec, self._bed_spec
        if spec is None or not spec.bed or limits is None or spec.model not in range(1, 6):
            return ()
        return tuple(
            axis
            for i, axis in enumerate(codec.AXES)
            if limits.bounds[i][0] < limits.bounds[i][1]
            and (axis != "height" or limits.locks & 4)
            and (axis != "tilt" or spec.model in (3, 5))
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        controls = [f"{axis}_{direction}" for axis in self._axes() for direction in ("up", "down")]
        if "head" in self._axes() and "legs" in self._axes():
            controls.extend(("combination_up", "combination_down"))
        if self._axes():
            controls.append("multi_button")
            controls.extend(
                f"template_{i}"
                for i in range(1, 11)
                if i != 10 or (self._spec and self._spec.model == 5)
            )
        return tuple(controls)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid(
                "held_control_not_supported",
                device_name=self._coordinator.name,
                control=control,
                valid_controls=", ".join(self.held_control_options),
            )
        self._live(auth=True)
        if not 1 <= duration_ms <= HOLD_CEILING_MS:
            raise invalid("hold_lease_duration", min=1, max=HOLD_CEILING_MS)
        if self._position is None or self._position.fail:
            raise invalid("active_sleep_position_required")
        if control.startswith("template_"):
            self._target(
                control
            )  # Reject any unsupported target before another paired target moves.
        else:
            axes = (
                ("head", "legs", "combination")
                if control.startswith("combination")
                else (control.rsplit("_", 1)[0],)
            )
            if any(self._position.locks & codec.LOCKS.get(axis, 0) for axis in axes):
                raise invalid("active_sleep_motor_locked")
        if control == "height_down" or control.startswith("template_"):
            self._height_gate(control, first=True, start_high=False)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                {"height": "bed_height"}.get(axis, axis),
                partial(action, name=f"{axis}_up"),
                partial(action, name=f"{axis}_down"),
                partial(action, name="stop"),
                position_key=axis if axis in ("head", "legs") else None,
                max_angle=self._bed_spec.bounds[codec.AXES.index(axis)][1] if self._bed_spec else 0,
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down", press_hold_ms=1000),
            )
            for axis in self._axes()
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs: list[ControllerButtonSpec | None] = [
            ControllerButtonSpec(
                "active_sleep_refresh",
                "Refresh state",
                partial(action, name="refresh"),
                translation_key="active_sleep_refresh",
                diagnostic=True,
                cancel_movement=False,
            )
        ]
        if self._axes():
            specs.append(
                ControllerButtonSpec(
                    "active_sleep_height_ack",
                    "Acknowledge bed height warning",
                    partial(action, name="acknowledge"),
                    translation_key="active_sleep_height_ack",
                    requires_confirmation=True,
                )
            )
        for name in self.held_control_options:
            if name.startswith("template_"):
                specs.append(
                    catalog_button(
                        f"active_sleep_{name}",
                        f"Bed position {name.split('_')[1]}",
                        partial(action, name=name),
                        kind=Kind.PRESET,
                        hold=ControllerHoldSpec(name),
                    )
                )
            elif name.startswith("combination_"):
                direction = name.rsplit("_", 1)[1]
                specs.append(
                    catalog_button(
                        f"active_sleep_{name}",
                        f"Head and feet {direction}",
                        partial(action, name=name),
                        kind=Kind.MOTOR,
                        hold=ControllerHoldSpec(name),
                    )
                )
        if self._spec and self._spec.mattress:
            specs.extend(
                catalog_button(
                    f"active_sleep_mattress_template_{i}",
                    f"Mattress firmness {i}",
                    partial(action, name=f"mattress_template_{i}"),
                    kind=Kind.PRESET,
                )
                for i in range(1, 6)
            )
        for kind, count in (("bed", 10), ("mattress", 5)):
            present = (
                bool(self._axes()) if kind == "bed" else bool(self._spec and self._spec.mattress)
            )
            if present:
                for slot in range(1, count + 1):
                    if kind == "bed" and slot == 10 and self._spec and self._spec.model != 5:
                        continue
                    label = f"Bed position {slot}" if kind == "bed" else f"Mattress firmness {slot}"
                    for operation in ("save", "reset"):
                        name = f"{operation}_{kind}_{slot}"
                        specs.append(
                            catalog_button(
                                f"active_sleep_{name}",
                                f"{operation.capitalize()} {label.lower()}",
                                partial(action, name=name),
                                kind=Kind.SAVE if operation == "save" else Kind.EXTRA,
                                requires_confirmation=True,
                                enabled=False,
                            )
                        )
        return unique_buttons(specs)

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if not self._bed_spec:
            return ()
        return tuple(
            build_position_number_spec(axis, max_value=float(self._bed_spec.bounds[i][1]), unit="°")
            for i, axis in enumerate(codec.AXES[:2])
            if axis in self._axes()
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs: list[ControllerSelectSpec] = []
        if self._axes():
            specs.append(
                ControllerSelectSpec(
                    "active_sleep_speed",
                    "active_sleep_speed",
                    FAST,
                    ("normal", "fast"),
                    self._select_speed,
                )
            )
        return tuple(specs)

    async def _select_speed(self, _controller: BedController, value: str) -> None:
        await self.change_setting(fast=value == "fast")

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        specs: list[ControllerSwitchSpec] = []
        if self._spec and self._spec.analyzer:
            specs.append(
                ControllerSwitchSpec(
                    "active_sleep_monitor",
                    "active_sleep_monitor",
                    self._set_monitor,
                    MONITOR,
                    local_set_fn=self.set_monitor,
                )
            )
        if self._bed_spec:
            for axis, bit in codec.LOCKS.items():
                if self._bed_spec.locks & bit:
                    specs.append(
                        ControllerSwitchSpec(
                            f"active_sleep_lock_{axis}",
                            "active_sleep_motor_lock",
                            partial(self._set_lock, axis=axis),
                            LOCK_KEYS[axis],
                            translation_placeholders={"motor": axis},
                        )
                    )
        if self._spec and self._spec.mattress:
            specs.extend(
                (
                    ControllerSwitchSpec(
                        "active_sleep_ventilation",
                        "active_sleep_ventilation",
                        partial(self._set_mattress_flag, flag="ventilation"),
                        VENTILATION,
                    ),
                    ControllerSwitchSpec(
                        "active_sleep_fukatto",
                        "active_sleep_fukatto",
                        partial(self._set_mattress_flag, flag="fukatto"),
                        FUKATTO,
                    ),
                )
            )
        return tuple(specs)

    def set_monitor(self, enabled: bool) -> None:
        self._monitor = enabled
        self.forward_controller_state_updates(MONITOR(enabled))

    async def _set_monitor(self, _controller: BedController, enabled: bool) -> None:
        self.set_monitor(enabled)

    async def _set_lock(self, _controller: BedController, value: bool, *, axis: str) -> None:
        await self.change_setting(axis=axis, enabled=value)

    async def _set_mattress_flag(
        self, _controller: BedController, value: bool, *, flag: str
    ) -> None:
        if flag == "ventilation":
            await self.change_mattress(ventilation=value)
        else:
            await self.change_mattress(fukatto=value)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = tuple(
            ControllerStateSensorSpec(
                str(key),
                str(key),
                key,
                icon,
                native_unit_of_measurement=unit,
                entity_registry_enabled_default=user,
                entity_category=None if user else EntityCategory.DIAGNOSTIC,
                card=CARD_UTILITY if user else CARD_HIDDEN,
            )
            for key, icon, unit, user in (
                (MODEL, "mdi:bed", None, False),
                (SERIAL, "mdi:identifier", None, False),
                (HEIGHT, "mdi:arrow-expand-vertical", "cm", True),
                (TILT, "mdi:angle-acute", "°", True),
                (WARNING, "mdi:alert", None, True),
                (REMAINING, "mdi:timer", None, True),
            )
            if (key != REMAINING or bool(self._spec and self._spec.mattress))
            and (key not in (HEIGHT, WARNING) or "height" in self._axes())
            and (key != TILT or "tilt" in self._axes())
        )
        if self._spec and self._spec.analyzer:
            specs += (
                sleep_rate_sensor_spec("heart_rate", str(HEART), HEART),
                sleep_rate_sensor_spec("breathing_rate", str(RESPIRATION), RESPIRATION),
            )
        return specs

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            str(key): self._coordinator.controller_state.get(key)
            for key in (RAW, MODE, BUSY, FAIL, *ZONE_KEYS.values())
        }

    def _live(self, link: Link | None = None, *, auth: bool = False) -> Link:
        current = self._link
        configured_token = self._coordinator.entry.options.get(
            AUTH_ID, self._coordinator.entry.data.get(AUTH_ID, "")
        )
        if (
            current is None
            or (link is not None and current is not link)
            or current.client is not self.client
            or not current.client.is_connected
            or "write" not in current.characteristic.properties
            or "notify" not in current.characteristic.properties
            or current.epoch is not self._epoch
            or current.token != self._token
            or current.token != configured_token
            or self._coordinator.controller is not self
            or current.client.services.get_characteristic(current.characteristic.handle)
            is not current.characteristic
        ):
            raise BedNotConnectedError("active_sleep_link_changed")
        if auth and (not self._authenticated or self._poisoned):
            raise invalid("active_sleep_reconnect_required")
        return current

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object] | None:
        if command and command[0] == 0x84:
            return {"redacted": True, "length": len(command)}
        return super()._format_command_trace_payload(command)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._link is not None:
            try:
                self._live()
            except ConnectionError:
                pass
            else:
                return
        self.on_disconnect()
        client = self.client
        service = client.services.get_service(codec.SERVICE_UUID) if client else None
        char = service.get_characteristic(codec.CHAR_UUID) if service else None
        if (
            client is None
            or char is None
            or "write" not in char.properties
            or "notify" not in char.properties
        ):
            raise BedNotConnectedError("bed_missing_service")
        link = self._link = Link(client, char, self._epoch, self._token)

        def receive(_char: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self._live(link)
            except ConnectionError:
                return
            self._notification(bytes(data))

        await client.start_notify(char, receive)
        self._live(link)

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link and link.client.is_connected:
            await link.client.stop_notify(link.characteristic)

    def on_disconnect(self) -> None:
        self._epoch = object()
        self._link = None
        self._authenticated = False
        self._poisoned = False
        self._receiver = codec.Receiver()
        self._position = None
        self._mattress = None
        self._monitor = False
        self._last_poll = 0.0
        self._last_sequence = -1
        self._acknowledged = False
        self._warned = False
        if self._pending:
            self._pending[1].cancel()
            self._pending = None
        self.forward_controller_state_updates(
            MONITOR(False),
            *(
                key(None)
                for key in (
                    HEIGHT,
                    TILT,
                    HEART,
                    RESPIRATION,
                    RAW,
                    FAIL,
                    WARNING,
                    FAST,
                    MODE,
                    VENTILATION,
                    FUKATTO,
                    REMAINING,
                    BUSY,
                )
            ),
            *(key(None) for key in LOCK_KEYS.values()),
            *(key(None) for key in ZONE_KEYS.values()),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        if len(self._token) != 16 or not self._token.isascii():
            raise invalid("active_sleep_auth_id_required")
        await session.async_start_notify()
        link = self._live()
        await self._exchange(link, codec.frame(0x81), event=asyncio.Event())
        await self._exchange(link, codec.frame(0x82), event=asyncio.Event())
        if self._spec is None or self._spec.mode != 0:
            raise invalid("active_sleep_normal_mode_required")
        reply = await self._exchange(link, codec.authentication(self._token), event=asyncio.Event())
        if reply.payload[0] not in (0, 2):
            raise invalid("active_sleep_auth_rejected")
        self._authenticated = True
        if self._spec.bed:
            await self._exchange(link, codec.frame(0xB1), event=asyncio.Event())
            await self._exchange(link, codec.frame(0xB2), event=asyncio.Event())
        if self._spec.mattress:
            await self._exchange(link, codec.frame(0xC1), event=asyncio.Event())
        session.persist_capability_snapshot()

    async def _send(
        self,
        link: Link,
        command: bytes,
        event: asyncio.Event,
        *,
        guard: Callable[[], None] | None = None,
        sent: Callable[[], None] | None = None,
    ) -> None:
        def admit() -> None:
            self._live(link)
            if guard:
                guard()
            # An acknowledgement failure cannot prove the submitted motion
            # missed the bed. Cleanup belongs to this original session.
            if sent:
                sent()

        async with self._wire_lock:
            await self._write_gatt_with_retry(
                codec.CHAR_UUID,
                command,
                cancel_event=event,
                response=True,
                characteristic=link.characteristic,
                expected_client=link.client,
                before_write=admit,
                settle_write=True,
                write_timeout=5,
            )
        self._live(link)
        if event.is_set():
            raise asyncio.CancelledError

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        raise invalid("active_sleep_request_unavailable")

    async def _exchange(
        self,
        link: Link,
        command: bytes,
        *,
        event: asyncio.Event | None = None,
        guard: Callable[[], None] | None = None,
        sent: Callable[[], None] | None = None,
    ) -> codec.Reply:
        event = event if event is not None else self._coordinator.cancel_command
        self._live(link)
        if event.is_set():
            raise asyncio.CancelledError
        if self._poisoned or self._pending is not None:
            raise invalid("active_sleep_reconnect_required")
        future: asyncio.Future[codec.Reply] = asyncio.get_running_loop().create_future()
        self._pending = (command[0] & 127, future)
        if command[0] == 0xB4:
            self._expected_button = command[2]
        timeout = (
            self.profile.response_timeout_ms / 1000
            if command[0] == 0xB4
            else self.profile.query_timeout_s
        )
        try:
            await self._send(link, command, event, guard=guard, sent=sent)

            async def wait() -> codec.Reply:
                async with asyncio.timeout(timeout):
                    return await future

            reply = await cancellable(wait(), event)
            self._live(link)
            return reply
        except BaseException:
            # Cancellation can arrive after the matched reply, while a settled
            # write unwinds. Only an unconfirmed exchange makes the link ambiguous.
            if not future.done() or future.cancelled() or future.exception() is not None:
                self._poisoned = True
            raise
        finally:
            future.cancel()
            if self._pending and self._pending[1] is future:
                self._pending = None

    def _notification(self, data: bytes) -> None:
        reply = self._receiver.feed(data)
        if reply is None:
            return
        pending = self._pending
        if pending is None or pending[0] != reply.opcode or pending[1].done():
            return
        p = reply.payload
        if reply.opcode == 1:
            serial = p.decode("ascii", errors="replace")
            self.forward_controller_state_updates(SERIAL("AMS0NG" if p == bytes(8) else serial))
        elif reply.opcode == 2:
            self._spec_bytes = p
            self._spec = codec.Spec.parse(p)
            self.forward_controller_state_updates(
                MODEL(codec.MODELS.get(self._spec.model, "Unknown"))
            )
        elif reply.opcode == 0x31:
            self._limit_bytes = p
            self._bed_spec = codec.BedSpec.parse(p)
        elif reply.opcode == 0x32:
            self._update_position(codec.Position.parse(p))
        elif reply.opcode == 0x34:
            # The current B4 selector must match, including STOP/multitouch.
            if p[0] != self._expected_button:
                return
            if self._position and self._authenticated:
                self._update_position(
                    replace(
                        self._position,
                        posture=(
                            codec.signed(p[1]),
                            codec.signed(p[2]),
                            codec.signed(p[3]),
                            codec.signed(p[4]),
                        ),
                        fail=codec.signed(p[5]),
                    )
                )
        elif reply.opcode == 0x41:
            self._mattress = m = codec.Mattress.parse(p)
            self.forward_controller_state_updates(
                *(ZONE_KEYS[zone](v) for zone, v in zip(codec.ZONES, m.zones, strict=True)),
                MODE(str(m.mode)),
                VENTILATION(bool(m.ventilation)),
                FUKATTO(m.fukatto),
                REMAINING(m.remaining),
                BUSY(m.busy),
                FAIL(m.fail),
            )
        elif reply.opcode == 0x22 and self._authenticated and self._spec and self._spec.analyzer:
            if p[0] != self._last_sequence:
                self._last_sequence = p[0]
                self.forward_controller_state_updates(
                    HEART(codec.sensor_value(p[11])),
                    RESPIRATION(codec.sensor_value(p[10], respiration=True)),
                    RAW(p.hex()),
                )
        pending[1].set_result(reply)

    _expected_button = 0

    def _update_position(self, position: codec.Position) -> None:
        if self._position is None or self._position.posture != position.posture:
            self._last_change = monotonic()
        self._position = position
        if self._notify_callback:
            self._notify_callback("head", position.posture[0])
            self._notify_callback("legs", abs(position.posture[1]))
        self.forward_controller_state_updates(
            HEIGHT(position.posture[2]),
            TILT(position.posture[3]),
            FAIL(position.fail),
            FAST("fast" if position.fast else "normal"),
            *(LOCK_KEYS[axis](bool(position.locks & bit)) for axis, bit in codec.LOCKS.items()),
        )
        if self._bed_spec and self._spec and self._effective(position.posture) > self._upper():
            self._acknowledged = False
            self._warned = False
            self.forward_controller_state_updates(WARNING(False))

    def _effective(self, posture: codec.Posture) -> int:
        return (
            posture[2]
            if self._position is None or self._position.posture[3] < 2
            else int(posture[2] - math.sin(math.radians(posture[3])) * 70.80000305175781)
        )

    def _threshold(self) -> int:
        return {3: 28, 4: 36}.get(self._spec.model if self._spec else 0, 31)

    def _upper(self) -> int:
        return self._threshold() + (4 if self._position and self._position.posture[3] >= 2 else 0)

    def _height_gate(
        self, control: str, *, first: bool, start_high: bool, target: codec.Posture | None = None
    ) -> None:
        if not self._spec or not self._bed_spec or not self._position or self._acknowledged:
            return
        if target is None and control.startswith("template_"):
            target = self._target(control)
        if target is not None:
            head, legs, height, tilt = (
                current if desired == 255 else desired
                for desired, current in zip(target, self._position.posture, strict=True)
            )
            target = head, legs, height, tilt
        model = self._spec.model
        if model not in (1, 3, 4) and not self._bed_spec.locks & 4:
            return
        current = self._effective(self._position.posture)
        upper = self._upper()
        if first:
            warn = model != 1 and current <= upper
            if target is not None:
                reached = all(
                    t == 255 or t == c for t, c in zip(target, self._position.posture, strict=True)
                )
                warn = warn and not reached and model != 4 and current > self._effective(target)
        else:
            warn = start_high and self._threshold() - 3 <= current <= upper
            if target is not None:
                warn = (
                    warn
                    and model != 1
                    and (
                        self._position.posture[2] != target[2]
                        or (
                            self._position.posture[3] != target[3] and self._position.posture[3] < 2
                        )
                    )
                )
        if warn:
            self._warned = True
            self.forward_controller_state_updates(WARNING(True))
            raise invalid("active_sleep_height_clearance")

    def _target(self, control: str) -> codec.Posture:
        target = self._bed_templates[int(control.split("_")[1]) - 1]
        self._validate_target(target)
        return target

    def _validate_target(self, target: codec.Posture) -> None:
        if not self._bed_spec or not self._position:
            raise invalid("active_sleep_limits_required")
        for i, (axis, value) in enumerate(zip(codec.AXES, target, strict=True)):
            if value == 255:
                continue
            low, high = self._bed_spec.bounds[i]
            if (
                (axis not in self._axes() and value != self._position.posture[i])
                or not low <= value <= high
                or self._position.locks & codec.LOCKS[axis]
            ):
                raise invalid("active_sleep_target_unavailable")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        target = self._target(control) if control.startswith("template_") else None
        await self._hold_movement(control, duration_ms, target)

    async def _hold_movement(
        self, control: str, duration_ms: int, target: codec.Posture | None
    ) -> None:
        link = self._live(auth=True)
        start_high = bool(
            self._position and self._effective(self._position.posture) > self._upper()
        )
        written = False

        def sent() -> None:
            nonlocal written
            written = True

        def guard() -> None:
            self._live(link, auth=True)
            if self._position is None or self._position.fail:
                raise invalid("active_sleep_position_required")
            if target is not None:
                self._validate_target(target)
            elif control != "multi_button":
                axes = (
                    ("head", "legs", "combination")
                    if control.startswith("combination")
                    else (control.rsplit("_", 1)[0],)
                )
                if any(
                    (axis != "combination" and axis not in self._axes())
                    or self._position.locks & codec.LOCKS[axis]
                    for axis in axes
                ):
                    raise invalid("active_sleep_motor_locked")
            if not written or monotonic() - self._last_change >= self.profile.no_change_ms / 1000:
                if control == "height_down" or target is not None:
                    self._height_gate(
                        control, first=not written, start_high=start_high, target=target
                    )

        command = codec.preset(*target) if target else codec.arrow(codec.OPERATIONS[control])
        self._expected_button = command[2]
        deadline = monotonic() + duration_ms / 1000
        try:
            await cancellable(
                asyncio.sleep(
                    (
                        self.profile.preset_delay_ms
                        if target and self._spec and self._spec.model in (1, 3, 4)
                        else self.profile.manual_delay_ms
                    )
                    / 1000
                ),
                self._coordinator.cancel_command,
            )
            while monotonic() < deadline:
                guard()
                await self._exchange(link, command, guard=guard, sent=sent)
                if self._position and self._position.fail:
                    raise invalid("active_sleep_movement_failed")
                if monotonic() - self._last_change >= self.profile.no_change_ms / 1000:
                    if (
                        target
                        and self._position
                        and all(
                            t == 255 or t == c
                            for t, c in zip(target, self._position.posture, strict=True)
                        )
                    ):
                        await cancellable(
                            asyncio.sleep(self.profile.reached_stop_ms / 1000),
                            self._coordinator.cancel_command,
                        )
                        break
                    if control == "height_down" or target:
                        self._height_gate(
                            control, first=False, start_high=start_high, target=target
                        )
                await cancellable(
                    asyncio.sleep(self.profile.interval_ms / 1000), self._coordinator.cancel_command
                )
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if not self._coordinator.cancel_command.is_set() or task is None or task.cancelling():
                raise
        finally:
            if written:
                await settled(self._release(link))

    @property
    def supports_direct_position_control(self) -> bool:
        return bool(self._axes())

    @property
    def position_validation_requires_connection(self) -> bool:
        return True

    @property
    def requires_connection_reset(self) -> bool:
        return self._poisoned or not self._authenticated

    def _single_target(self, motor: str, position: int) -> codec.Posture:
        axis = {"back": "head", "feet": "legs"}.get(motor, motor)
        if axis not in self._axes():
            raise invalid("active_sleep_motor_unavailable")
        if self._position is None:
            raise invalid("active_sleep_position_required")
        values = [255] * 4
        values[codec.AXES.index(axis)] = position
        return values[0], values[1], values[2], values[3]

    def validate_position_request(self, motor: str, position: float) -> None:
        if not math.isfinite(position) or position != int(position):
            raise invalid("whole_number_required", value=position)
        target = self._single_target(motor, int(position))
        self._live(auth=True)
        if self._position is None or self._position.fail:
            raise invalid("active_sleep_position_required")
        self._validate_target(target)
        self._height_gate("target", first=True, start_high=False, target=target)

    async def set_motor_position(self, motor: str, position: int) -> None:
        self.validate_position_request(motor, position)
        await self._hold_movement("target", HOLD_CEILING_MS, self._single_target(motor, position))

    async def _release(self, link: Link) -> None:
        self._live(link)
        await asyncio.sleep(self.profile.interval_ms / 1000)
        self._live(link)
        if self._poisoned:
            # An ambiguous request must never consume a later movement reply.
            await self._send(link, codec.arrow(0), asyncio.Event())
        else:
            await self._exchange(link, codec.arrow(0), event=asyncio.Event())

    async def stop_all(self) -> None:
        link = self._live()
        if not self._authenticated:
            raise invalid("active_sleep_reconnect_required")
        await self._release(link)

    async def press(self, name: str) -> None:
        if name == "stop":
            await self.stop_all()
        elif name == "refresh":
            await self.read_positions()
        elif name == "acknowledge":
            self._live(auth=True)
            if not self._warned:
                raise invalid("active_sleep_no_height_warning")
            self._acknowledged = True
            self.forward_controller_state_updates(WARNING(False))
        elif name.startswith(("save_", "reset_")):
            operation, kind, raw_slot = name.split("_")
            slot = int(raw_slot) - 1
            link = self._live(auth=True)
            if kind == "bed":
                if not self._spec or not self._spec.bed or not 0 <= slot < 10:
                    raise invalid("active_sleep_template_unavailable")
                if operation == "save":
                    await self._exchange(link, codec.frame(0xB2))
                    if self._position is None or self._position.fail:
                        raise invalid("active_sleep_position_required")
                    self._bed_templates[slot] = self._position.posture
                else:
                    self._bed_templates[slot] = BED_TEMPLATES[slot]
            else:
                if not self._spec or not self._spec.mattress or not 0 <= slot < 5:
                    raise invalid("active_sleep_template_unavailable")
                if operation == "save":
                    await self._exchange(link, codec.frame(0xC1))
                    if self._mattress is None or self._mattress.fail:
                        raise invalid("active_sleep_mattress_state_required")
                    self._mattress_templates[slot] = (
                        self._mattress.zones,
                        MATTRESS_TEMPLATES[slot][1],
                    )
                else:
                    self._mattress_templates[slot] = MATTRESS_TEMPLATES[slot]
            self._coordinator.save_app_state()
        elif name.startswith("mattress_template_"):
            zones, mode = self._mattress_templates[int(name.rsplit("_", 1)[1]) - 1]
            await self.change_mattress(zones=zones, mode=mode, ventilation=False)
        else:
            await self.hold_control(name, 1000)

    async def change_setting(
        self, *, axis: str | None = None, enabled: bool = False, fast: bool | None = None
    ) -> None:
        link = self._live(auth=True)
        await self._exchange(link, codec.frame(0xB2))
        current = self._position
        if not current or current.fail or not self._bed_spec:
            raise invalid("active_sleep_settings_required")
        mask = current.locks
        if axis is not None:
            bit = codec.LOCKS[axis]
            if not self._bed_spec.locks & bit:
                raise invalid("active_sleep_motor_lock_unavailable")
            mask = mask | bit if enabled else mask & ~bit
        command = codec.settings(
            *(bool(mask & bit) for bit in (1, 2, 4, 8, 16)),
            fast=current.fast if fast is None else fast,
        )
        await self._exchange(link, command)
        await self._exchange(link, codec.frame(0xB2))
        if (
            self._position is None
            or self._position.locks != mask
            or (fast is not None and self._position.fast != fast)
        ):
            raise invalid("active_sleep_settings_unconfirmed")

    async def change_mattress(
        self,
        *,
        zone: str | None = None,
        value: int = 0,
        zones: tuple[int, ...] | None = None,
        mode: int | None = None,
        ventilation: bool | None = None,
        fukatto: bool | None = None,
    ) -> None:
        link = self._live(auth=True)
        if not self._spec or not self._spec.mattress:
            raise invalid("active_sleep_mattress_unavailable")
        await self._exchange(link, codec.frame(0xC1))
        current = self._mattress
        if current is None or current.fail or current.busy:
            raise invalid("active_sleep_mattress_busy")
        values = list(zones if zones is not None else current.zones)
        if zone is not None:
            if not 0 <= value <= 15:
                raise invalid("value_out_of_range", min=0, max=15, step=1)
            values[codec.ZONES.index(zone)] = value
            mode = 15
            ventilation = False
        desired = replace(
            current,
            zones=tuple(values),
            mode=current.mode if mode is None else mode,
            ventilation=current.ventilation if ventilation is None else int(ventilation),
            fukatto=current.fukatto if fukatto is None else fukatto,
        )
        await self._exchange(link, desired.encode())
        await self._exchange(link, codec.frame(0xC1))
        if self._mattress is None or self._mattress.encode() != desired.encode():
            raise invalid("active_sleep_mattress_unconfirmed")

    async def async_refresh_diagnostics(self) -> None:
        if not self._authenticated or self._poisoned:
            return
        if monotonic() - self._last_poll >= 1:
            self._last_poll = monotonic()
            await self.read_positions()
        elif self._monitor and self._spec and self._spec.analyzer:
            await self._exchange(self._live(auth=True), codec.frame(0xA2))

    @property
    def diagnostic_poll_interval(self) -> float:
        return self.profile.realtime_ms / 1000

    async def read_positions(self, motor_count: int = 2) -> None:
        link = self._live(auth=True)
        if self._spec and self._spec.bed:
            await self._exchange(link, codec.frame(0xB2))
        if self._spec and self._spec.mattress:
            await self._exchange(link, codec.frame(0xC1))
        if self._spec and self._spec.analyzer:
            await self._exchange(link, codec.frame(0xA2))

    async def move_head_up(self) -> None:
        await self.press("head_up")

    async def move_head_down(self) -> None:
        await self.press("head_down")

    async def move_legs_up(self) -> None:
        await self.press("legs_up")

    async def move_legs_down(self) -> None:
        await self.press("legs_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def preset_flat(self) -> None:
        raise NotImplementedError(keyed("active_sleep_flat_unavailable")[0])

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError(
            keyed("memory_presets_not_supported", device_name=self._coordinator.name)[0]
        )

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError(
            keyed("memory_programming_not_supported", device_name=self._coordinator.name)[0]
        )


async def build_controller(ctx: BuildContext) -> ActiveSleepController:
    return ActiveSleepController(
        ctx.coordinator, str(ctx.data.get(AUTH_ID, "")), ctx.stored_capabilities("active_sleep")
    )
