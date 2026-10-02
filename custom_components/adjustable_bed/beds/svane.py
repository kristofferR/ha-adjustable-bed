"""Svane Remote Version1.8: exact BLE paths with opaque host memory."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..command_scheduler import current_command_context
from ..svane_state import SvaneProfile, SvaneSession, integer
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


def uuid(short: str) -> str:
    return f"0000{short}-0000-1000-8000-00805f9b34fb"


HEAD, FEET, LIGHT, OLD, DIS, SOFTWARE = (
    uuid(x) for x in ("abcb", "c258", "d07b", "1234", "180a", "f92a")
)
POSITION, OLD_CHAR, UP, DOWN = (uuid(x) for x in ("143d", "1111", "01ac", "bae9"))
MOTIONS: dict[str, tuple[bool | None, bool | None]] = {
    "head_up": (True, None),
    "head_down": (False, None),
    "feet_up": (None, True),
    "feet_down": (None, False),
    "head_up_feet_up": (True, True),
    "head_up_feet_down": (True, False),
    "head_down_feet_up": (False, True),
    "head_down_feet_down": (False, False),
}


class SvaneCommands:
    """Reachable normal-control literals, without dormant firmware commands."""

    MOTOR_MOVE = bytes.fromhex("0100")
    MOTOR_STOP = bytes.fromhex("0000")
    SVANE_POSITION = bytes.fromhex("0300")
    LIGHT_OFF = bytes.fromhex("130200000000")
    SOFTWARE_QUERY = bytes.fromhex("040000000000")

    @staticmethod
    def light_brightness(level: int) -> bytes:
        integer(level, -(2**31), 2**31 - 1)
        return bytes((0x13, 2, level & 0xFF, 1, 0, 100))

    @staticmethod
    def motion(head: bool | None, feet: bool | None) -> bytes:
        if (head is not None and type(head) is not bool) or (
            feet is not None and type(feet) is not bool
        ):
            raise ValueError("Axis intent must be boolean or absent")
        mask = (0 if head is None else 1 if head else 2) | (
            0 if feet is None else 16 if feet else 32
        )
        return bytes((0x10, mask, 0, 0, 0, 0))

    @staticmethod
    def recall(position: bytes) -> bytes:
        if not isinstance(position, bytes) or len(position) != 4:
            raise ValueError("JMC recall requires four opaque bytes")
        return b"\x10\x04" + position


def _action(name: str) -> MotorCommandCallable:
    async def press(controller: BedController) -> None:
        if not isinstance(controller, SvaneController):
            raise ValueError("Svane action requires its app profile")
        await controller.execute_app_control(name)

    return press


async def _intensity(controller: BedController, value: float) -> None:
    if not isinstance(controller, SvaneController) or not float(value).is_integer():
        raise ValueError("Svane intensity requires a whole source step")
    await controller.set_light_level(int(value))


@dataclass(frozen=True, slots=True)
class SvaneHoldAdmission:
    """A physical session's release boundary before public preflight/admission."""

    session: SvaneSession
    release_epochs: tuple[int, int]

    @contextmanager
    def activate(self, controller: BedController) -> Iterator[None]:
        if not isinstance(controller, SvaneController) or controller.session is not self.session:
            raise ValueError("Svane physical session changed before held command admission")
        token = _hold_admission.set(self)
        try:
            yield
        finally:
            _hold_admission.reset(token)


_hold_admission: ContextVar[SvaneHoldAdmission | None] = ContextVar(
    "svane_hold_admission", default=None
)


class SvaneController(BedController):
    """An explicit app profile; local intent and raw observations are not angles."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: SvaneProfile = "multi",
        session: SvaneSession | None = None,
    ) -> None:
        super().__init__(coordinator)
        if profile not in ("multi", "jmc"):
            raise ValueError("Unknown Svane profile")
        self.profile = profile
        self.session = session or SvaneSession()
        self._started: set[tuple[str, str]] = set()
        self._subscriptions: list[BleakGATTCharacteristic] = []
        self._notification_tokens: dict[BleakGATTCharacteristic, object] = {}
        self._descriptor_state = 0
        self._initialized = False
        self._active_head: bool | None = None
        self._active_feet: bool | None = None
        self._pending_release: set[str] = set()
        self._wake = asyncio.Event()
        self._publish_intent()
        self.forward_controller_state_updates(dict(self.session.observations))

    @property
    def control_characteristic_uuid(self) -> str:
        return OLD_CHAR if self.profile == "jmc" else UP

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec(
                "back",
                "head",
                lambda c: c.move_head_up(),
                lambda c: c.move_head_down(),
                lambda c: c.move_head_stop(),
            ),
            MotorControlSpec(
                "legs",
                "feet",
                lambda c: c.move_feet_up(),
                lambda c: c.move_feet_down(),
                lambda c: c.move_feet_stop(),
            ),
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "svane_profile": self.profile,
            "light_local_intent": self.session.light_on,
            "light_step": self.session.light_step,
            "opaque_observations": dict(self.session.observations),
            "native_position_units": None,
            "memory_scope": "process_session" if self.profile == "multi" else "target_preferences",
            "descriptor_state": self._descriptor_state,
            "initialized": self._initialized,
        }

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        """Literal app labels, not names observed from the bed."""
        return ("Read", "TV")

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_held_control(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (*MOTIONS, "light_adjust")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(f"svane_{key}", label, _action(key))
            for key, label in (
                ("position", "Svane position"),
                ("read", "Read position"),
                ("tv", "TV position"),
                ("light_toggle", "Toggle light"),
                ("refresh", "Refresh device information"),
            )
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            ControllerNumberSpec(
                "svane_intensity", "svane_intensity", "svane_intensity", 5, 100, 5, _intensity
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"svane_{key}",
                f"svane_{key}",
                f"svane_{key}",
                "mdi:bluetooth",
                attribute_keys=(
                    f"svane_{key}_observed_at",
                    f"svane_{key}_service",
                    f"svane_{key}_characteristic",
                    f"svane_{key}_target_address",
                    "svane_profile",
                    "svane_initialization",
                ),
            )
            for key in (
                "head_raw",
                "feet_raw",
                "position_raw",
                "firmware",
                "hardware",
                "manufacturer",
            )
        )

    def _publish_intent(self) -> None:
        self.forward_controller_state_updates(
            {
                "svane_intensity": self.session.intensity,
                "svane_light_intent": self.session.light_on,
                "under_bed_lights_on": self.session.light_on,
                "svane_profile": self.profile,
            }
        )

    def _remember(self) -> None:
        self._coordinator.remember_svane_preferences(self.session.preferences())
        self._publish_intent()

    def _role(self, service: str, char: str) -> BleakGATTCharacteristic | None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Svane link is not connected")
        matches = [
            c
            for s in client.services
            if s.uuid.lower() == service
            for c in s.characteristics
            if c.uuid.lower() == char
        ]
        if len(matches) > 1:
            raise ValueError("Ambiguous Svane GATT role")
        return matches[0] if matches else None

    async def _write(self, service: str, char: str, data: bytes) -> None:
        role = self._role(service, char)
        if role is None:
            raise ValueError(f"Missing Svane role {service}/{char}")
        properties = set(role.properties)
        if not properties & {"write", "write-without-response"}:
            raise ValueError("Svane role is not writable")
        client = self.client
        if client is None:
            raise ConnectionError("Svane link is not connected")
        # The app inherits runtime mode. Host policy prefers advertised
        # no-response; a write-only role uses its advertised response mode.
        async with self._ble_lock:
            await client.write_gatt_char(
                role, data, response="write-without-response" not in properties
            )

    async def _wait(self, seconds: float) -> bool:
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return False
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
            return False
        except TimeoutError:
            return True

    def _observe(self, key: str, value: str, service: str, char: str) -> None:
        """Completed target-local record; no command acknowledgement is inferred."""
        updates = {
            key: value,
            f"{key}_observed_at": datetime.now(UTC).isoformat(),
            f"{key}_service": service,
            f"{key}_characteristic": char,
            f"{key}_target_address": self._coordinator.address,
        }
        self.session.observations.update(updates)
        self.forward_controller_state_updates(updates)

    def accept_response(self, service: str, char: str, data: bytes) -> bool:
        """Guard origin/length around the source's opaque projections."""
        service, char = service.lower(), char.lower()
        if not data or service == DIS:
            return False
        updates: dict[str, str] = {}
        if char == POSITION and service in (HEAD, FEET):
            key = "head" if service == HEAD else "feet"
            if key == "head":
                self.session.head = bytes(data)
            else:
                self.session.feet = bytes(data)
            updates[f"svane_{key}_raw"] = data.hex()
        elif service == OLD and char == OLD_CHAR and len(data) >= 6 and data[0] == 0x10:
            self.session.position = bytes(data[2:6])
            updates["svane_position_raw"] = self.session.position.hex()
        else:
            return False
        key, value = next(iter(updates.items()))
        self._observe(key, value, service, char)
        return True

    async def _subscribe(self, service: str, char: str) -> bool:
        role = self._role(service, char)
        client = self.client
        if role is None or client is None or not set(role.properties) & {"notify", "indicate"}:
            return False
        if role in self._subscriptions:
            return True

        token = object()
        self._notification_tokens[role] = token

        def receive(sender: BleakGATTCharacteristic, raw: bytearray) -> None:
            if (
                self.client is not client
                or not client.is_connected
                or self._notification_tokens.get(role) is not token
                or sender is not role
                or self._role(service, char) is not role
            ):
                return
            self.forward_raw_notification(char, bytes(raw))
            self.accept_response(service, char, bytes(raw))

        try:
            await client.start_notify(role, receive)
        except BaseException:
            if self._notification_tokens.get(role) is token:
                del self._notification_tokens[role]
            raise
        self._subscriptions.append(role)
        return True

    async def _read(
        self, service: str, char: str, *, fresh: dict[str, bytes] | None = None
    ) -> bytes | None:
        role = self._role(service, char)
        client = self.client
        if role is None or client is None:
            return None
        async with self._ble_lock:
            raw = bytes(await client.read_gatt_char(role))
        accepted = self.accept_response(service, char, raw)
        if fresh is not None and accepted:
            if service in (HEAD, FEET) and char == POSITION:
                fresh["head" if service == HEAD else "feet"] = raw
            elif service == OLD and char == OLD_CHAR:
                fresh["position"] = raw[2:6]
        if service != DIS:
            # Map source CCCD writes to the backend's supported subscription
            # API; a read-only role still remains readable and cacheable.
            await self._subscribe(service, char)
        return raw

    async def refresh_device_information(self) -> None:
        for key, char in (("firmware", "2a26"), ("hardware", "2a27"), ("manufacturer", "2a29")):
            raw = await self._read(DIS, uuid(char))
            if raw is not None:
                self._observe(
                    f"svane_{key}", raw.decode("utf-8", errors="replace"), DIS, uuid(char)
                )
            if not await self._wait(1):
                return

    async def _read_state(self, state: int, *, fresh: dict[str, bytes] | None = None) -> None:
        if state in (0, 1):
            for service, char in ((HEAD if state == 0 else FEET, POSITION), (OLD, OLD_CHAR)):
                try:
                    await self._read(service, char, fresh=fresh)
                except BleakError as error:
                    self.forward_controller_state_update("svane_last_read_error", str(error))

    async def read_positions(self, motor_count: int = 2) -> None:
        del motor_count
        await self._read_positions()

    async def _read_positions(self, *, fresh: dict[str, bytes] | None = None) -> None:
        self._descriptor_state = 0
        await self._read_state(0, fresh=fresh)
        self._descriptor_state = 1
        await self._read_state(1, fresh=fresh)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        del callback  # No numeric position decoder exists in the artifact.
        if self._initialized:
            return
        try:
            if not await self._wait(0.1):
                return
            await self.refresh_device_information()
            if self._coordinator.cancel_command.is_set():
                return
            if await self._subscribe(OLD, OLD_CHAR):
                if self._role(SOFTWARE, uuid("a592")) is not None:
                    await self._write(SOFTWARE, uuid("a592"), SvaneCommands.SOFTWARE_QUERY)
                self._descriptor_state = 1
                await self._read_state(1)
                self.forward_controller_state_update("svane_initialization", "old_notify_ready")
            else:
                self.forward_controller_state_update(
                    "svane_initialization", "old_notify_unavailable"
                )
            self._initialized = True
        except BaseException:
            await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        client = self.client
        self._notification_tokens.clear()
        try:
            if client is not None and client.is_connected:
                if self._started:
                    await self.stop_all()
            else:
                self._started.clear()
        finally:
            subscriptions, self._subscriptions = self._subscriptions, []
            self._initialized = False
            if client is not None and client.is_connected:
                for role in subscriptions:
                    try:
                        await client.stop_notify(role)
                    except BleakError:
                        pass

    def _motion_roles(self, head: bool | None, feet: bool | None) -> tuple[tuple[str, str], ...]:
        return tuple(
            (service, UP if direction else DOWN)
            for service, direction in ((HEAD, head), (FEET, feet))
            if direction is not None
        )

    def validate_svane_hold_constraints(self, control: str, duration_ms: int) -> None:
        """Validate profile/local intent/duration without requiring a BLE client."""
        integer(duration_ms, 1, 60000)
        if control not in self.held_control_options:
            raise ValueError("Unknown Svane held control")
        if control == "light_adjust":
            intensity = integer(self.session.intensity, 5, 100)
            if intensity % 5:
                raise ValueError("Svane lamp intensity uses steps of five")
        if control != "light_adjust":
            head, feet = MOTIONS[control]
            delayed_feet = feet is not None and not (self.profile == "jmc" and head is not None)
            if delayed_feet and duration_ms <= 100:
                raise ValueError("Feet controls require a hold longer than 100 ms (0.1 seconds)")
    def validate_svane_hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_svane_hold_constraints(control, duration_ms)
        roles = (
            ((LIGHT, uuid("b5e9")), (LIGHT, uuid("3fb2")))
            if control == "light_adjust"
            else self._motion_roles(*MOTIONS[control])
        )
        if self.profile == "jmc":
            roles = ((OLD, OLD_CHAR),)
        for service, char in roles:
            role = self._role(service, char)
            if role is None or not set(role.properties) & {"write", "write-without-response"}:
                raise ValueError("Svane held control role is unavailable")

    def prepare_svane_hold_admission(self) -> SvaneHoldAdmission:
        return SvaneHoldAdmission(
            self.session, (self.session.head_release_epoch, self.session.feet_release_epoch)
        )

    def request_svane_axis_release(self, axis: str) -> None:
        """Signal the active command writer; this synchronous method does no I/O."""
        if axis not in ("head", "feet"):
            raise ValueError("Unknown Svane axis")
        if axis == "head":
            self.session.head_release_epoch += 1
        else:
            self.session.feet_release_epoch += 1
        self._pending_release.add(axis)
        self._wake.set()

    async def _consume_release(self) -> None:
        pending, self._pending_release = self._pending_release, set()
        self._wake.clear()
        for axis in pending:
            service = HEAD if axis == "head" else FEET
            if axis == "head":
                self._active_head = None
            else:
                self._active_feet = None
            if self.profile == "multi":
                await self._release(tuple(role for role in self._started if role[0] == service))

    async def _motor_wait(self, seconds: float) -> None:
        waiters = [
            asyncio.create_task(self._coordinator.cancel_command.wait()),
            asyncio.create_task(self._wake.wait()),
        ]
        try:
            await asyncio.wait(waiters, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waiters:
                task.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_svane_hold_control(control, duration_ms)
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        if control == "light_adjust":
            if not self.session.light_on or duration_ms <= 200 or not await self._wait(0.2):
                return
            previous_preferences = self.session.preferences()
            try:
                while not cancel.is_set() and asyncio.get_running_loop().time() < deadline:
                    if (self.session.intensity >= 100 and self.session.light_step > 0) or (
                        self.session.intensity <= 5 and self.session.light_step < 0
                    ):
                        self.session.light_step *= -1
                    old = self.session.intensity
                    self.session.intensity += self.session.light_step
                    self._publish_intent()
                    await self._light(
                        self.session.intensity, "b5e9" if self.session.intensity > old else "3fb2"
                    )
                    if not await self._wait(
                        min(0.1, max(0, deadline - asyncio.get_running_loop().time()))
                    ):
                        return
            finally:
                preferences = self.session.preferences()
                if preferences != previous_preferences:
                    self._coordinator.remember_svane_preferences(preferences)
            return
        self._active_head, self._active_feet = MOTIONS[control]
        admission = _hold_admission.get() or self.prepare_svane_hold_admission()
        self._pending_release = {
            axis
            for axis, current, baseline in (
                ("head", self.session.head_release_epoch, admission.release_epochs[0]),
                ("feet", self.session.feet_release_epoch, admission.release_epochs[1]),
            )
            if current > baseline
        }
        self._wake.clear()
        feet_started = False
        try:
            while not cancel.is_set() and asyncio.get_running_loop().time() < deadline:
                await self._consume_release()
                head, feet = self._active_head, self._active_feet
                if head is None and feet is None:
                    break
                if self.profile == "jmc" and head is not None:
                    self._started.add((OLD, OLD_CHAR))
                    await self._write(OLD, OLD_CHAR, SvaneCommands.motion(head, feet))
                else:
                    if head is not None:
                        self._started.add((HEAD, UP if head else DOWN))
                        await self._write(HEAD, UP if head else DOWN, SvaneCommands.MOTOR_MOVE)
                    if feet is not None:
                        await self._motor_wait(
                            min(0.1, max(0, deadline - asyncio.get_running_loop().time()))
                        )
                        await self._consume_release()
                        feet = self._active_feet
                        if cancel.is_set() or feet is None:
                            continue
                        if asyncio.get_running_loop().time() >= deadline:
                            if not feet_started:
                                raise ValueError("Hold ended before the selected feet axis could start")
                            continue
                        role = (
                            (OLD, OLD_CHAR)
                            if self.profile == "jmc"
                            else (FEET, UP if feet else DOWN)
                        )
                        self._started.add(role)
                        await self._write(
                            *role,
                            SvaneCommands.motion(None, feet)
                            if self.profile == "jmc"
                            else SvaneCommands.MOTOR_MOVE,
                        )
                        feet_started = True
                await self._motor_wait(
                    min(0.1, max(0, deadline - asyncio.get_running_loop().time()))
                )
        finally:
            self._active_head = self._active_feet = None
            await self._release(tuple(self._started))

    async def _release(self, roles: tuple[tuple[str, str], ...]) -> None:
        if self.profile == "jmc":
            roles = ((OLD, OLD_CHAR),) if (OLD, OLD_CHAR) in self._started else ()
        errors: list[Exception] = []
        for service, char in roles:
            if (service, char) not in self._started:
                continue
            try:
                await self._write(
                    service,
                    char,
                    SvaneCommands.motion(None, None)
                    if self.profile == "jmc"
                    else SvaneCommands.MOTOR_STOP,
                )
            except Exception as error:
                errors.append(error)
            else:
                self._started.discard((service, char))
        if errors:
            raise errors[0]

    async def stop_all(self) -> None:
        self._active_head = self._active_feet = None
        if self.profile == "jmc":
            self._started.add((OLD, OLD_CHAR))
        await self._release(tuple(self._started))

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        axis = "head" if motor == "back" else "feet"
        self.validate_svane_hold_constraints(f"{axis}_{direction}", duration_ms)

    def _motor_hold_duration_ms(self) -> int:
        context = current_command_context()
        if (
            context is not None
            and context.active
            and context.scheduler_token is self._coordinator._command_scheduler.token
            and context.pulse_count is not None
            and context.pulse_delay_ms is not None
        ):
            # The service keeps the exact elapsed ceiling; its repeat plan
            # supplies enough hold time without changing the native cadence.
            return max(1, (context.pulse_count - 1) * context.pulse_delay_ms)
        return 1000

    async def move_head_up(self) -> None:
        await self.hold_control("head_up", self._motor_hold_duration_ms())

    async def move_head_down(self) -> None:
        await self.hold_control("head_down", self._motor_hold_duration_ms())

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self.hold_control("feet_up", self._motor_hold_duration_ms())

    async def move_legs_down(self) -> None:
        await self.hold_control("feet_down", self._motor_hold_duration_ms())

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        del command, repeat_count, repeat_delay_ms, cancel_event
        raise ValueError("Svane writes require a typed source action and exact role")

    async def preset_flat(self) -> None:
        raise NotImplementedError("Svane Remote has no reachable Flat preset")

    def validate_memory_recall(self, memory_num: int) -> None:
        """Reject unavailable local memory before any selected target moves."""
        super().validate_memory_recall(memory_num)
        integer(memory_num, 1, 2)
        if self.profile == "jmc":
            SvaneCommands.recall(self.session.jmc_slots[memory_num - 1])
        else:
            saved = self.session.multi_slots.get(memory_num)
            if saved is None:
                raise ValueError("Read both raw axes and save this local slot before recall")
            if len(saved) != 2 or any(not isinstance(raw, bytes) or not raw for raw in saved):
                raise ValueError("Saved Svane memory requires both nonempty raw axes")

    async def preset_memory(self, memory_num: int) -> None:
        integer(memory_num, 1, 2)
        if self._coordinator.cancel_command.is_set():
            return
        if self.profile == "jmc":
            await self._write(
                OLD, OLD_CHAR, SvaneCommands.recall(self.session.jmc_slots[memory_num - 1])
            )
            await self._wait(1)
        else:
            saved = self.session.multi_slots.get(memory_num)
            if saved is None:
                raise ValueError("Read both raw axes and save this local slot before recall")
            await self._write(HEAD, POSITION, saved[0])
            if await self._wait(1):
                await self._write(FEET, POSITION, saved[1])

    async def program_memory(self, memory_num: int) -> None:
        integer(memory_num, 1, 2)
        fresh: dict[str, bytes] = {}
        await self._read_positions(fresh=fresh)
        if self.profile == "jmc":
            if "position" not in fresh:
                raise ValueError("No fresh valid four-byte position was read for this target")
            slots = list(self.session.jmc_slots)
            slots[memory_num - 1] = fresh["position"]
            self.session.jmc_slots = (slots[0], slots[1])
            self._remember()
        else:
            if "head" not in fresh or "feet" not in fresh:
                raise ValueError("Both fresh valid raw axes must be read for this target")
            self.session.multi_slots[memory_num] = (fresh["head"], fresh["feet"])

    async def _light(self, intensity: int, char: str = "a8e0") -> None:
        await self._write(
            OLD if self.profile == "jmc" else LIGHT,
            OLD_CHAR if self.profile == "jmc" else uuid(char),
            SvaneCommands.light_brightness(intensity),
        )

    async def lights_on(self) -> None:
        self.session.light_on = True
        self._publish_intent()
        await self._light(self.session.intensity)

    async def lights_off(self) -> None:
        self.session.light_on = False
        self._publish_intent()
        await self._write(
            OLD if self.profile == "jmc" else LIGHT,
            OLD_CHAR if self.profile == "jmc" else uuid("a8e0"),
            SvaneCommands.LIGHT_OFF,
        )

    async def lights_toggle(self) -> None:
        if self.session.light_on:
            await self.lights_off()
        else:
            await self.lights_on()

    async def set_light_level(self, level: int) -> None:
        integer(level, 5, 100)
        if level % 5:
            raise ValueError("Svane lamp intensity uses steps of five")
        self.session.intensity = level
        self.session.light_on = True
        self._remember()
        await self._light(level)

    async def execute_app_control(self, action: str) -> None:
        if action == "position":
            await self._write(
                OLD if self.profile == "jmc" else HEAD,
                OLD_CHAR if self.profile == "jmc" else uuid("fb6e"),
                bytes.fromhex("108100000000")
                if self.profile == "jmc"
                else SvaneCommands.SVANE_POSITION,
            )
        elif action in ("read", "tv"):
            await self.preset_memory(1 if action == "read" else 2)
        elif action == "light_toggle":
            await self.lights_toggle()
        elif action == "refresh":
            await self.refresh_device_information()
            await self.read_positions()
        else:
            raise ValueError("Unknown Svane app control")
