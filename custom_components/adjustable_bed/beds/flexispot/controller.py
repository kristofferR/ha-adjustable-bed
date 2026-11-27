"""Flexispot direct BLE controls, with connection-bound movement and state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...alarm import AlarmCapability, AlarmRequest
from ...app_session import app_session
from ...card import CARD_MASSAGE
from ...codec import flexispot as codec
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...errors import BedNotConnectedError
from ...errors import invalid as command_error
from ...profiles import flexispot as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..base import BedController, ProfileExecution
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

GLOBAL_SNORE: Final = StateKey[bool | None]("flexispot_snore_enabled")
POWER: Final = StateKey[bool | None]("flexispot_massage_power")
MODE: Final = StateKey[str | None]("flexispot_massage_mode")
LEVELS: Final = {
    zone: StateKey[int | None](f"flexispot_{zone}_massage") for zone in ("upper", "feet", "right")
}
SNORE: Final = {
    side: StateKey[bool | None](f"flexispot_{side}_snore") for side in ("left", "right")
}
SENSITIVITY: Final = {side: StateKey[str | None](f"flexispot_{side}_sensitivity") for side in SNORE}
ANGLE: Final = {side: StateKey[str | None](f"flexispot_{side}_angle") for side in SNORE}


@dataclass(slots=True)
class _Owner:
    publisher: object | None = None


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    owner: object


class _AdmissionExpired(Exception):
    """A hold/cancellation expired before final wire submission."""


class FlexispotController(ProfileExecution[app.FlexispotProfile], BedController):
    """Explicit product selection; no inferred positions, authentication or pairing."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        model = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, ""))
        if model not in app.PROFILES:
            raise command_error("flexispot_model_required")
        self.profile = app.PROFILES[model]
        self._owner = app_session(coordinator.hass, coordinator.address, "flexispot", _Owner)
        self._link: _Link | None = None
        self._notifying = False
        self._status: codec.Status | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return self.profile.light

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_off_control(self) -> bool:
        return False  # The power switch exposes both actions.

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        # The older circle excludes its upper endpoint; V3 includes it.
        return list(range(61 if self.profile.split else 60))

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    @property
    def mode_options(self) -> tuple[str, ...]:
        return (
            app.MODES
            if self.profile.split
            else ("pattern_1", "pattern_2", "pattern_3", "pattern_4")
        )

    def _role(self, uuid: str) -> BleakGATTCharacteristic:
        client = self.client
        if client is not None and client.is_connected:
            for service in client.services:
                if service.uuid.lower() == codec.SERVICE:
                    char = service.get_characteristic(uuid)
                    if char is not None:
                        return char
        raise BedNotConnectedError("flexispot_gatt_roles")

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        write, notify = self._role(codec.WRITE), self._role(codec.NOTIFY)
        if (
            not {"write", "write-without-response"}.intersection(write.properties)
            or "notify" not in notify.properties
        ):
            raise BedNotConnectedError("flexispot_gatt_roles")
        client = self.client
        assert client is not None
        owner = object()
        self._owner.publisher = owner
        self._link = _Link(client, write, notify, owner)

    def _live(self, link: _Link | None = None) -> _Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self._owner.publisher is not current.owner
            or self.client is not current.client
            or not current.client.is_connected
            or self._role(codec.WRITE) is not current.write
            or self._role(codec.NOTIFY) is not current.notify
        ):
            raise BedNotConnectedError
        return current

    def _current(self, link: _Link) -> bool:
        try:
            self._live(link)
        except ConnectionError:
            return False
        return True

    @staticmethod
    async def _settle(task: asyncio.Task[None]) -> None:
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    @staticmethod
    async def _wait(event: asyncio.Event, seconds: float) -> None:
        if event.is_set() or seconds <= 0:
            return
        try:
            await asyncio.wait_for(event.wait(), seconds)
        except TimeoutError:
            pass

    def _admitted(self, event: asyncio.Event) -> bool:
        context = current_command_context()
        return not (
            event.is_set()
            or context is not None
            and (
                context.cancel_event.is_set()
                or context.caller_is_cancelling is not None
                and context.caller_is_cancelling()
                or context.hold_deadline is not None
                and asyncio.get_running_loop().time() >= context.hold_deadline
            )
        )

    async def _send(
        self,
        link: _Link,
        frame: bytes,
        event: asyncio.Event,
        *,
        cleanup: bool = False,
        submitted: Callable[[], None] | None = None,
        on_write: Callable[[], None] | None = None,
        deadline: float | None = None,
    ) -> None:
        caller = asyncio.current_task()

        def admit() -> None:
            self._live(link)
            if not cleanup and (
                not self._admitted(event)
                or caller is not None
                and caller.cancelling()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
            ):
                note_frame_skipped()
                raise _AdmissionExpired
            if not {"write", "write-without-response"}.intersection(link.write.properties):
                raise BedNotConnectedError("flexispot_gatt_roles")
            if submitted is not None:
                submitted()

        def written() -> None:
            # Settle cache changes with the successful write, even when the
            # caller was cancelled while it was in flight. A new link owns its
            # own snapshot and must never be invalidated by an old completion.
            if on_write is not None and self._current(link):
                on_write()

        async def send() -> None:
            await self._write_gatt_with_retry(
                codec.WRITE,
                frame,
                cancel_event=event,
                characteristic=link.write,
                expected_client=link.client,
                response="write" in link.write.properties,
                before_write=admit,
                on_write=written,
            )

        # There is no await between the final admission in the writer and
        # submission. A fresh event is reserved for proven cleanup only.
        try:
            await self._settle(asyncio.create_task(send()))
        except _AdmissionExpired:
            return

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            await self._send(link, command, event)
            if index + 1 < repeat_count:
                await self._wait(event, repeat_delay_ms / 1000)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if not self._notifying:
            await link.client.start_notify(
                link.notify, lambda sender, data: self._notification(link, data)
            )
            self._live(link)
            self._notifying = True

    async def stop_notify(self) -> None:
        link, notifying = self._link, self._notifying
        self.on_disconnect()
        if (
            link is not None
            and notifying
            and self.client is link.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        link, self._link = self._link, None
        self._notifying = False
        self._status = None
        if link is None or self._owner.publisher is not link.owner:
            return
        self._owner.publisher = None
        self.forward_controller_state_updates(
            GLOBAL_SNORE(None),
            POWER(None),
            MODE(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
            *(key(None) for keys in (LEVELS, SNORE, SENSITIVITY, ANGLE) for key in keys.values()),
        )

    def _notification(self, link: _Link, data: bytearray) -> None:
        if not self._current(link):
            return
        self.forward_raw_notification(codec.NOTIFY, bytes(data))
        status = codec.parse(bytes(data))
        if status is None:
            return
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(status.light == 1 if status.light in (1, 2) else None)
        )
        if status.alarms is None:
            return
        self._status = status
        self.forward_controller_state_updates(
            MODE(
                self.mode_options[status.mode]
                if status.mode is not None and status.mode in range(4)
                else None
            ),
            # The source displays time+1; do not turn this into actuator feedback.
            MASSAGE_TIMER_MINUTES(
                status.minutes + 1 if status.minutes is not None and status.minutes < 60 else None
            ),
            *(
                LEVELS[zone](value if value is not None and value in range(7) else None)
                for zone, value in (
                    ("upper", status.upper),
                    ("feet", status.feet),
                    ("right", status.right),
                )
            ),
        )
        if self.profile.split:
            self.forward_controller_state_updates(
                GLOBAL_SNORE(status.snore_mask != 0 if status.snore_mask in range(4) else None)
            )
            angles = codec.unpair(status.angles or 0)
            sensitivities = codec.unpair(status.sensitivities or 0)
            for index, side in enumerate(SNORE):
                self.forward_controller_state_updates(
                    SNORE[side](
                        bool(status.snore_mask & (1 << index))
                        if status.snore_mask is not None and status.snore_mask in range(4)
                        else None
                    ),
                    SENSITIVITY[side](
                        ("low", "medium", "high")[sensitivities[index]] if sensitivities else None
                    ),
                    ANGLE[side](("8", "12", "15")[angles[index]] if angles else None),
                )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        from dataclasses import asdict

        return {
            "product": self.profile.key,
            "status": asdict(self._status) if self._status else None,
        }

    async def _release(self, link: _Link, motor: int) -> None:
        async def release() -> None:
            await asyncio.sleep(app.RELEASE_MS / 1000)
            if self._current(link):
                await self._send(link, codec.frame(3, motor), asyncio.Event(), cleanup=True)
                if (context := current_command_context()) is not None:
                    context.cleanup_stop_sent = True

        await self._settle(asyncio.create_task(release()))

    async def move_axis(self, axis: str, up: bool, duration_ms: int | None = None) -> None:
        motors = dict(self.profile.motors)
        if axis not in motors:
            raise command_error("flexispot_control_unavailable")
        link, motor = self._live(), motors[axis]
        event = self._coordinator.cancel_command
        duration = self.leased_hold_ms(
            duration_ms or self._coordinator.motor_pulse_count * app.REFRESH_MS
        )
        deadline = asyncio.get_running_loop().time() + duration / 1000
        started = False
        submitted_at = 0.0

        def submitted() -> None:
            nonlocal started, submitted_at
            started = True
            submitted_at = asyncio.get_running_loop().time()

        try:
            while self._admitted(event) and asyncio.get_running_loop().time() < deadline:
                await self._send(
                    link,
                    codec.frame(1 if up else 2, motor),
                    event,
                    submitted=submitted,
                    deadline=deadline,
                )
                await self._wait(
                    event,
                    max(
                        0,
                        min(
                            submitted_at + app.REFRESH_MS / 1000,
                            deadline,
                        )
                        - asyncio.get_running_loop().time(),
                    ),
                )
        finally:
            if started:
                await self._release(link, motor)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}" for axis, _ in self.profile.motors for direction in ("up", "down")
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 30000
        ):
            raise command_error("flexispot_control_unavailable")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        await self.move_axis(axis, direction == "up", duration_ms)

    async def stop_axis(self, axis: str) -> None:
        motor = dict(self.profile.motors).get(axis)
        if motor is None:
            raise command_error("flexispot_control_unavailable")
        await self._send(self._live(), codec.frame(3, motor), asyncio.Event(), cleanup=True)

    async def stop_all(self) -> None:
        # Fan out the proven per-motor stops, never invent a global stop key.
        link = self._live()
        for _, motor in self.profile.motors:
            await self._send(link, codec.frame(3, motor), asyncio.Event(), cleanup=True)

    async def move_head_up(self) -> None:
        await self.move_axis(
            "head"
            if self.profile.key == "eb704"
            else "left_back"
            if self.profile.split
            else "back",
            True,
        )

    async def move_head_down(self) -> None:
        await self.move_axis(
            "head"
            if self.profile.key == "eb704"
            else "left_back"
            if self.profile.split
            else "back",
            False,
        )

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.move_axis("left_back" if self.profile.split else "back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("left_back" if self.profile.split else "back", False)

    async def move_feet_up(self) -> None:
        await self.move_axis("feet", True)

    async def move_feet_down(self) -> None:
        await self.move_axis("feet", False)

    move_back_stop = move_head_stop
    move_feet_stop = move_head_stop
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_legs_stop = move_head_stop

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                "back" if axis == "left_back" else axis,
                "neck"
                if axis == "head"
                else "flexispot_left_back"
                if axis == "left_back"
                else axis,
                lambda c, axis=axis: cast(FlexispotController, c).move_axis(axis, True),
                lambda c, axis=axis: cast(FlexispotController, c).move_axis(axis, False),
                lambda c, axis=axis: cast(FlexispotController, c).stop_axis(axis),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(f"{axis}_up", f"{axis}_down"),
            )
            for axis, _ in self.profile.motors
        )

    @property
    def supports_preset_flat(self) -> bool:
        return not self.profile.split

    @property
    def supports_memory_presets(self) -> bool:
        return self.profile.key == "eb632"

    @property
    def supports_memory_programming(self) -> bool:
        return self.supports_memory_presets

    @property
    def memory_slot_count(self) -> int:
        return 3 if self.supports_memory_presets else 0

    async def preset_memory(self, memory_num: int) -> None:
        if not self.supports_memory_presets or not 1 <= memory_num <= 3:
            raise command_error("flexispot_control_unavailable")
        await self.preset(self.profile.memories[memory_num - 1][1])

    async def program_memory(self, memory_num: int) -> None:
        if not self.supports_memory_presets or not 1 <= memory_num <= 3:
            raise command_error("flexispot_control_unavailable")
        await self.preset(self.profile.memories[memory_num - 1][1], save=True)

    async def preset_flat(self) -> None:
        await self.write_command(codec.frame(5, 2))

    async def preset(self, key: int, *, flat: bool = False, save: bool = False) -> None:
        await self.write_command(codec.frame(5 if flat else 6 if save else 7, key))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons: list[ControllerButtonSpec | None] = []
        for side, mask in (("left", 0), ("right", 128)) if self.profile.split else (("", 0),):
            for name, key in (("flat", 2), ("zero_g", 5), *self.profile.memories):
                if self.supports_memory_presets and name.startswith("memory_"):
                    continue
                if name == "flat" and not side:
                    continue  # Shared Flat button calls preset_flat.
                label = (side + " " if side else "") + name.replace("_", " ")
                buttons.append(
                    catalog_button(
                        f"{side}_{name}",
                        label,
                        lambda c, key=key | mask, flat=name == "flat": cast(
                            FlexispotController, c
                        ).preset(key, flat=flat),
                        kind=Kind.PRESET if self.profile.split and name == "memory" else None,
                        invalidates_position=True,
                    )
                )
                if (name, key) in self.profile.memories:
                    buttons.append(
                        catalog_button(
                            f"save_{side}_{name}",
                            "Save " + label,
                            lambda c, key=key | mask: cast(FlexispotController, c).preset(
                                key, save=True
                            ),
                            requires_confirmation=True,
                        )
                    )
        if not self.profile.split:
            for zone in ("upper", "feet"):
                for up in (True, False):
                    buttons.append(
                        catalog_button(
                            f"{zone}_massage_{'up' if up else 'down'}",
                            f"{zone.capitalize()} massage {'increase' if up else 'decrease'}",
                            lambda c, zone=zone, up=up: cast(FlexispotController, c).massage_step(
                                zone, up
                            ),
                        )
                    )
        buttons.append(
            catalog_button(
                "restore",
                "Restore original settings",
                lambda c: cast(FlexispotController, c).restore(),
                requires_confirmation=True,
            )
        )
        return unique_buttons(buttons)

    async def restore(self) -> None:
        link = self._live()
        with self.sent_state(
            GLOBAL_SNORE(None),
            POWER(None),
            MODE(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
            *(key(None) for keys in (LEVELS, SNORE, SENSITIVITY, ANGLE) for key in keys.values()),
            is_current=lambda: self._current(link),
        ):
            await self._send(
                link,
                codec.frame(5, 10),
                self._coordinator.cancel_command,
                on_write=self._forget_status,
            )

    def _forget_status(self) -> None:
        self._status = None

    def _forget_level(self, zone: str) -> None:
        if self._status is not None:
            self._status = replace(self._status, **{zone: None})

    def _forget_snore(self) -> None:
        if self._status is not None:
            self._status = replace(self._status, snore_mask=None, angles=None, sensitivities=None)
        self.forward_controller_state_updates(
            GLOBAL_SNORE(None),
            *(key(None) for keys in (SNORE, SENSITIVITY, ANGLE) for key in keys.values()),
        )

    def _forget_alarms(self) -> None:
        if self._status is not None:
            self._status = replace(self._status, alarms=None)

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def _light(self, on: bool) -> None:
        if not self.profile.light:
            raise command_error("flexispot_control_unavailable")
        link = self._live()
        with self.sent_state(UNDER_BED_LIGHTS_ON(on), is_current=lambda: self._current(link)):
            await self._send(link, codec.frame(4, 1 if on else 2), self._coordinator.cancel_command)

    async def massage_power(self, on: bool) -> None:
        link = self._live()
        with self.sent_state(POWER(on), is_current=lambda: self._current(link)):
            await self._send(link, codec.frame(14, int(on)), self._coordinator.cancel_command)

    async def massage_off(self) -> None:
        await self.massage_power(False)

    async def massage_step(self, zone: str, up: bool) -> None:
        opcode = (17 if up else 13) if zone == "feet" else (12 if up else 18)
        if zone not in LEVELS or zone == "right" and not self.profile.split:
            raise command_error("flexispot_control_unavailable")
        link = self._live()
        with self.sent_state(LEVELS[zone](None), is_current=lambda: self._current(link)):
            await self._send(
                link,
                codec.frame(opcode, 128 if zone == "right" else 0),
                self._coordinator.cancel_command,
                on_write=lambda: self._forget_level(zone),
            )

    async def set_level(self, zone: str, value: float) -> None:
        if (
            not self.profile.split
            or zone not in LEVELS
            or not float(value).is_integer()
            or not 0 <= value <= 6
        ):
            raise command_error("flexispot_control_unavailable")
        status = self._status
        current = getattr(status, zone, None)
        if current is None or current not in range(7):
            raise command_error("flexispot_status_required")
        link, event = self._live(), self._coordinator.cancel_command
        started_at = asyncio.get_running_loop().time()
        for index in range(1, abs(int(value) - current) + 1):
            await self._wait(
                event,
                max(
                    0,
                    started_at
                    + index * app.MASSAGE_STEP_MS / 1000
                    - asyncio.get_running_loop().time(),
                ),
            )
            self._live(link)
            if not self._admitted(event):
                note_frame_skipped()
                return
            await self.massage_step(zone, value > current)

    async def set_mode(self, value: str) -> None:
        if value not in self.mode_options:
            raise command_error("flexispot_control_unavailable")
        link = self._live()
        with self.sent_state(MODE(value), is_current=lambda: self._current(link)):
            await self._send(
                link,
                codec.frame(16, self.mode_options.index(value)),
                self._coordinator.cancel_command,
            )

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes != 0 and minutes not in self.massage_timer_options:
            raise command_error("flexispot_control_unavailable")
        link = self._live()
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._current(link)
        ):
            await self._send(link, codec.frame(15, minutes), self._coordinator.cancel_command)

    def _snore_status(self) -> codec.Status:
        s = self._status
        if (
            not self.profile.split
            or s is None
            or s.snore_mask not in range(4)
            or codec.unpair(s.angles or 0) is None
            or codec.unpair(s.sensitivities or 0) is None
        ):
            raise command_error("flexispot_status_required")
        return s

    async def set_snore(self, side: str, kind: str, value: str | bool) -> None:
        s = self._snore_status()
        assert s.snore_mask is not None and s.angles is not None and s.sensitivities is not None
        sensitivities = codec.unpair(s.sensitivities)
        assert sensitivities is not None
        index = 0 if side == "left" else 1
        mask, angles, sensitivity = s.snore_mask, s.angles, s.sensitivities
        if kind == "enabled":
            mask = (mask | 1 << index) if value else (mask & ~(1 << index))
        else:
            values = ("low", "medium", "high") if kind == "sensitivity" else ("8", "12", "15")
            selected = values.index(str(value))
            pair = (
                codec.pair(selected, sensitivities[1])
                if index == 0
                else codec.pair(sensitivities[0], selected)
            )
            if kind == "sensitivity":
                sensitivity = pair
            else:
                angles = pair  # Shipped angle setter uses the OTHER side's sensitivity.
        link = self._live()
        await self._send(
            link,
            codec.snore(mask, angles, sensitivity),
            self._coordinator.cancel_command,
            on_write=self._forget_snore,
        )

    async def snore_global(self, enabled: bool) -> None:
        if not self.profile.split:
            raise command_error("flexispot_control_unavailable")
        link = self._live()
        with self.sent_state(GLOBAL_SNORE(enabled), is_current=lambda: self._current(link)):
            await self._send(
                link,
                codec.snore(3 if enabled else 0, 0, 0),
                self._coordinator.cancel_command,
                on_write=self._forget_snore,
            )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        result = [
            ControllerSwitchSpec(
                "massage",
                "flexispot_massage",
                lambda c, on: cast(FlexispotController, c).massage_power(on),
                POWER,
                assumed_state=True,
                card=CARD_MASSAGE,
            )
        ]
        if self.profile.split:
            result.append(
                ControllerSwitchSpec(
                    "snore",
                    "flexispot_snore",
                    lambda c, on: cast(FlexispotController, c).snore_global(on),
                    GLOBAL_SNORE,
                    assumed_state=True,
                )
            )
            result.extend(
                ControllerSwitchSpec(
                    f"{side}_snore",
                    f"flexispot_{side}_snore",
                    lambda c, on, side=side: cast(FlexispotController, c).set_snore(
                        side, "enabled", on
                    ),
                    SNORE[side],
                )
                for side in SNORE
            )
        return tuple(result)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        result = [
            ControllerSelectSpec(
                "massage_mode",
                "flexispot_massage_mode",
                MODE,
                self.mode_options,
                lambda c, value: cast(FlexispotController, c).set_mode(value),
                card=CARD_MASSAGE,
            )
        ]
        if self.profile.split:
            for side in SNORE:
                for kind, keys, options in (
                    ("sensitivity", SENSITIVITY, ("low", "medium", "high")),
                    ("angle", ANGLE, ("8", "12", "15")),
                ):
                    result.append(
                        ControllerSelectSpec(
                            f"{side}_{kind}",
                            f"flexispot_{side}_{kind}",
                            keys[side],
                            options,
                            lambda c, value, side=side, kind=kind: cast(
                                FlexispotController, c
                            ).set_snore(side, kind, value),
                        )
                    )
        return tuple(result)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.profile.split:
            return ()
        return tuple(
            ControllerNumberSpec(
                f"{zone}_massage",
                f"flexispot_{zone}_massage",
                LEVELS[zone],
                0,
                6,
                1,
                lambda c, value, zone=zone: cast(FlexispotController, c).set_level(zone, value),
                card=CARD_MASSAGE,
            )
            for zone in LEVELS
        )

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        return (
            AlarmCapability(
                slots=2, weekdays=True, wake_actions=("wake_mode_1", "wake_mode_2"), live_check=True
            )
            if self.profile.split
            else None
        )

    def _alarm_slots(self) -> tuple[codec.Alarm, codec.Alarm]:
        if self._status is None or self._status.alarms is None:
            raise command_error("flexispot_status_required")
        slots = self._status.alarms
        # Preserve even an unused slot with no weekdays, as the app does.
        # Reject malformed time/pattern values rather than constructing a partial record.
        if any(
            not 0 <= slot.hour <= 23 or not 0 <= slot.minute <= 59 or slot.pattern not in (0, 1, 2)
            for slot in slots
        ):
            raise command_error("flexispot_status_required")
        return slots

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if (
            not self.profile.split
            or alarm.slot not in (1, 2)
            or not 0 <= alarm.hour <= 23
            or not 0 <= alarm.minute <= 59
            or alarm.wake_action not in ("none", "wake_mode_1", "wake_mode_2")
        ):
            raise command_error("flexispot_control_unavailable")
        slots = self._alarm_slots()
        if alarm.enabled:
            if not alarm.weekdays:
                raise command_error("alarm_weekdays_required")
            other = slots[2 - alarm.slot]
            if (
                codec.flags(False, alarm.weekdays) & other.flags & 0x7F
                and abs(alarm.hour * 60 + alarm.minute - other.hour * 60 - other.minute) <= 20
            ):
                raise command_error("flexispot_alarm_overlap")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        slots = list(self._alarm_slots())
        index = alarm.slot - 1
        if alarm.enabled:
            slots[index] = codec.Alarm(
                alarm.hour,
                alarm.minute,
                codec.flags(True, alarm.weekdays),
                2 if alarm.wake_action == "wake_mode_2" else 1,
            )
        else:
            slots[index] = replace(slots[index], flags=slots[index].flags & 0x7F)
        link = self._live()
        await self._send(
            link,
            codec.alarm(
                (slots[0], slots[1]), alarm.slot, 1 if any(s.enabled for s in slots) else 2
            ),
            self._coordinator.cancel_command,
            on_write=self._forget_alarms,
        )
