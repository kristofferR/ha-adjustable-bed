"""ISleep com.kaidi_test4 1.6.3 (45), accepted standalone row064 evidence.

One press and a matching release, no held refresh and no position telemetry.
The independent app profile deliberately does not reuse sibling command tables.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..const import KAIDI_NOTIFY_CHAR_UUID, KAIDI_WRITE_CHAR_UUID, SIDE_LEFT, SIDE_RIGHT
from ..isleep_profile import validate_isleep_profile
from ..kaidi_protocol import format_kaidi_node_address
from .base import BedController, ControllerButtonSpec, MotorControlSpec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

# Values are the app's live UI, including Flat despite its misleading constant name.
# tuple order: single/left, right, both (only role1 uses columns 2 and 3).
COMMANDS: dict[str, tuple[int, int, int]] = {
    "head_up": (1, 10, 19),
    "head_down": (2, 11, 20),
    "head_stop": (3, 12, 21),
    "legs_up": (4, 13, 22),
    "legs_down": (5, 14, 23),
    "legs_stop": (6, 15, 24),
    "all_up": (7, 16, 25),
    "all_down": (8, 17, 26),
    "all_stop": (9, 18, 27),
    "flat": (28, 29, 30),
    "save_1": (37, 45, 53),
    "save_2": (38, 46, 54),
    "save_3": (39, 47, 55),
    "memory_1": (41, 49, 57),
    "memory_2": (42, 50, 58),
    "memory_3": (43, 51, 59),
    "massage_on": (71, 73, 75),
    "massage_off": (72, 74, 76),
    "head_strength": (77, 78, 81),
    "foot_strength": (79, 80, 82),
    "timer_1": (83, 86, 89),
    "timer_2": (84, 87, 90),
    "timer_3": (85, 88, 91),
    "light_on": (92, 94, 96),
    "light_off": (93, 95, 97),
    "zero_g": (98, 99, 100),
    "anti_snore": (101, 102, 103),
    "pattern_1": (107, 108, 109),
    "pattern_2": (110, 111, 112),
    "pattern_3": (113, 114, 115),
    "pattern_cancel": (116, 117, 118),
    "timer_cancel": (119, 120, 121),
    "back_up": (122, 122, 122),
    "back_down": (123, 123, 123),
    "back_stop": (124, 124, 124),
    "lumbar_up": (131, 131, 131),
    "lumbar_down": (132, 132, 132),
    "lumbar_stop": (133, 133, 133),
    "new_all_up": (149, 149, 149),
    "new_all_down": (150, 150, 150),
    "new_all_stop": (151, 151, 151),
}


def room_frame(room: int, *, enroll: bool = False) -> bytes:
    """Exact selected-room auth/enrollment encodings, signed Java LE32."""
    return (
        (b"\x01\x03" if enroll else b"\x01\x16\x01")
        + (room & 0xFFFFFFFF).to_bytes(4, "little")
        + b"1122"
        + (b"\0" * 4 if enroll else b"")
    )


def control_frame(own: int, target: int, opcode: int, parameter: int) -> bytes:
    """The retained parameter belongs to the physical connection, across sides."""
    return (
        b"\x03"
        + (target & 0xFFFFFFFF).to_bytes(4, "little")
        + b"\x20"
        + (own & 0xFFFFFFFF).to_bytes(4, "little")
        + bytes((1, opcode & 255, parameter & 255, 0))
    )


class IsleepController(BedController):
    """Explicit app profile; live session addresses are never restored from disk."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = validate_isleep_profile(coordinator.entry.data)
        self._notify_started = False
        self._ready = False
        self._generation = 0
        self._own: int | None = None
        self._target: int | None = None
        self._auth = asyncio.Event()
        self._own_event = asyncio.Event()
        self._roster = asyncio.Event()
        self._enrollment = asyncio.Event()
        self._auth_status: int | None = None
        self._enroll_status: int | None = None
        self._session_lock = asyncio.Lock()
        self._parameter = 0
        self._pending_ack = False
        self._pending_room: int | None = None
        self._massage = [False, False, False]
        self._patterns = [0, 0, 0]
        self._timers = [0, 0, 0]
        self._strengths = [{"head": 0, "foot": 0} for _ in range(3)]

    @property
    def control_characteristic_uuid(self) -> str:
        return KAIDI_WRITE_CHAR_UUID

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.profile.split

    @property
    def _lane(self) -> int:
        if not self.profile.split:
            return 0
        return {SIDE_LEFT: 0, SIDE_RIGHT: 1}.get(self.command_side or "both", 2)

    def _opcode(self, action: str, lane: int | None = None) -> int:
        return COMMANDS[action][self._lane if lane is None else lane]

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Construct from the app's rendered axes, not a numeric bedUI or motor count.
        commands = {
            "back": (
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
            ),
            "legs": (
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
            ),
            "head": (
                lambda c: c.move_head_up(),
                lambda c: c.move_head_down(),
                lambda c: c.move_head_stop(),
            ),
            "lumbar": (
                lambda c: c.move_lumbar_up(),
                lambda c: c.move_lumbar_down(),
                lambda c: c.move_lumbar_stop(),
            ),
        }
        return tuple(MotorControlSpec(axis, axis, *commands[axis]) for axis in self.profile.axes)

    @property
    def position_number_specs(self) -> tuple:
        return ()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "isleep_all_up",
                "All up",
                lambda c: cast(IsleepController, c)._move("all", True),
                translation_key="isleep_all_up",
            ),
            ControllerButtonSpec(
                "isleep_all_down",
                "All down",
                lambda c: cast(IsleepController, c)._move("all", False),
                translation_key="isleep_all_down",
            ),
            *(
                ControllerButtonSpec(
                    f"isleep_pattern_{i}",
                    f"Massage pattern {i}" if i else "Cancel massage pattern",
                    lambda c, i=i: cast(IsleepController, c).set_pattern(i),
                    translation_key="isleep_pattern",
                    translation_placeholders={"pattern": str(i)},
                )
                for i in range(4)
            ),
            ControllerButtonSpec(
                "isleep_enroll",
                "Enroll unprovisioned bed in selected room",
                lambda c: cast(IsleepController, c).enroll_room(),
                translation_key="isleep_enroll",
            ),
        )

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self.profile.axes

    @property
    def supports_preset_flat(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 3

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["head"] if self.profile.product == 143 else ["head", "foot"]

    @property
    def massage_intensity_max(self) -> int:
        return 100

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30] if self.profile.product == 143 else [15, 30, 45]

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        # Requested UI state is optimistic; live routing/authentication never goes on disk.
        return {
            "pending_ack": self._pending_ack,
            "room": self._pending_room,
            "profile_room": self.profile.room,
            "product": self.profile.product,
            "parameter": self._parameter,
            "massage": list(self._massage),
            "patterns": list(self._patterns),
            "timers": list(self._timers),
            "strengths": [dict(values) for values in self._strengths],
        }

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        self._parameter = 0
        self._massage = [False, False, False]
        self._patterns = [0, 0, 0]
        self._timers = [0, 0, 0]
        self._strengths = [{"head": 0, "foot": 0} for _ in range(3)]
        self._pending_ack = (
            state.get("pending_ack") is True and state.get("room") == self.profile.room
        )
        self._pending_room = self.profile.room if self._pending_ack else None
        if (
            state.get("profile_room") != self.profile.room
            or state.get("product") != self.profile.product
        ):
            self._publish_intent()
            return
        parameter = state.get("parameter", 0)
        if type(parameter) is not int or not 0 <= parameter <= 100:
            raise ValueError("Invalid saved ISleep strength parameter")
        for key, target, allowed in (
            ("massage", self._massage, (False, True)),
            ("patterns", self._patterns, (0, 1, 2, 3)),
            ("timers", self._timers, (0, *self.massage_timer_options)),
        ):
            values = state.get(key)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(type(v) is not type(allowed[0]) or v not in allowed for v in values)
            ):
                raise ValueError(f"Invalid saved ISleep {key}")
            target[:] = values
        strengths = state.get("strengths")
        if not isinstance(strengths, list) or len(strengths) != 3:
            raise ValueError("Invalid saved ISleep strengths")
        for index, values in enumerate(strengths):
            if not isinstance(values, dict) or any(
                type(values.get(z)) is not int or not 0 <= values[z] <= 100
                for z in ("head", "foot")
            ):
                raise ValueError("Invalid saved ISleep zone strength")
            self._strengths[index] = {z: values[z] for z in ("head", "foot")}
        self._parameter = parameter
        self._publish_intent()

    def _publish_intent(self) -> None:
        self.forward_controller_state_updates(
            {
                f"isleep_massage_{side}": self._massage_state(lane if self.profile.split else 0)
                for side, lane in (("left", 0), ("right", 1), ("both", 2))
            }
        )

    def _save_intent(self) -> None:
        if self.profile.split:
            self._massage[2] = all(self._massage[:2])
            self._patterns[2] = self._patterns[0] if self._patterns[0] == self._patterns[1] else 0
            self._timers[2] = self._timers[0] if self._timers[0] == self._timers[1] else 0
            for zone in ("head", "foot"):
                self._strengths[2][zone] = (
                    self._strengths[0][zone]
                    if self._strengths[0][zone] == self._strengths[1][zone]
                    else 0
                )
        self._publish_intent()
        self._coordinator.save_app_state(self)

    @property
    def _affected_lanes(self) -> tuple[int, ...]:
        return (0, 1, 2) if self.profile.split and self._lane == 2 else (self._lane,)

    def on_disconnect(self) -> None:
        self._generation += 1
        self._notify_started = self._ready = False
        self._own = self._target = None
        self._auth_status = self._enroll_status = None
        for event in (self._auth, self._own_event, self._roster, self._enrollment):
            event.set()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._notify_started:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("ISleep is disconnected")
        generation = self._generation

        def notification(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if generation == self._generation:
                self._notification(sender, data)

        async with self._ble_lock:
            await client.start_notify(KAIDI_NOTIFY_CHAR_UUID, notification)
        if generation != self._generation:
            raise ConnectionError("ISleep disconnected while subscribing")
        self._notify_started = True

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if self._notify_started and client and client.is_connected:
                async with self._ble_lock:
                    await client.stop_notify(KAIDI_NOTIFY_CHAR_UUID)
        finally:
            self.on_disconnect()

    async def read_positions(self, motor_count: int = 2) -> None:
        return

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        frame = bytes(data)
        self.forward_raw_notification(KAIDI_NOTIFY_CHAR_UUID, frame)
        if len(frame) >= 3 and frame[:2] == b"\x02\x16":
            self._auth_status = frame[2]
            self._auth.set()
        elif len(frame) >= 3 and frame[:2] == b"\x02\x03":
            self._enroll_status = frame[2]
            self._enrollment.set()
        elif len(frame) >= 6 and frame[:2] == b"\x01\x0a":
            self._own = int.from_bytes(frame[2:6], "little") or 0xFFFFFFFF
            self._own_event.set()
        elif len(frame) >= 10 and frame[:2] == b"\x01\x02":
            self._target = None
            self._roster.clear()
        elif len(frame) >= 16 and frame[0] == 3 and frame[5] == 255:
            if format_kaidi_node_address(frame[6:12]) != self._coordinator.address.upper():
                return
            target = int.from_bytes(frame[12:16], "little")
            self._target = 0 if target in (0, 0xFFFFFFFE) else target
            self._roster.set()
        # 20 has no telemetry; 2F is a phone alarm; library metadata has no control consumer.

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """One GATT write, no retry or hold refresh in the artifact."""
        await self._write_gatt_with_retry(
            KAIDI_WRITE_CHAR_UUID, command, response=True, cancel_event=cancel_event
        )

    async def _wait(self, event: asyncio.Event, timeout: float, generation: int) -> None:
        await asyncio.wait_for(event.wait(), timeout)
        if generation != self._generation or self.client is None or not self.client.is_connected:
            raise ConnectionError("ISleep session ended while waiting for a response")

    async def _ensure_session(self) -> None:
        async with self._session_lock:
            if self._ready and self._target is not None:
                return
            await self.start_notify()
            generation = self._generation
            if not self._ready:
                self._auth.clear()
                self._auth_status = None
                await self.write_command(room_frame(self.profile.room))
                await self._wait(self._auth, 5, generation)
                if self._auth_status != 0:
                    raise ConnectionError(
                        f"ISleep room authentication rejected ({self._auth_status})"
                    )
                if self._own is None:
                    self._own_event.clear()
                    await self._wait(self._own_event, 5, generation)
                self._ready = True
            self._roster.clear()
            await self.write_command(
                b"\x03\xff\xff\xff\xff\xfe" + cast(int, self._own).to_bytes(4, "little")
            )
            await self._wait(self._roster, 5, generation)
            if self._pending_ack:
                await self._send_opcode(69, cancel=asyncio.Event())
                self._pending_ack = False
                self._pending_room = None
                await self._coordinator.async_write_app_state(self, self.persisted_app_state)

    async def _send_opcode(self, opcode: int, *, cancel: asyncio.Event | None = None) -> None:
        if self._own is None or self._target is None:
            raise ConnectionError("ISleep has no live current-MAC roster mapping")
        await self.write_command(
            control_frame(self._own, self._target, opcode, self._parameter), cancel_event=cancel
        )

    async def _action(self, action: str, *, parameter: int | None = None) -> None:
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        opcode = self._opcode(action)
        await self._ensure_session()
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        if parameter is not None:
            self._parameter = parameter
        await self._send_opcode(opcode)
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError

    def _axis(self, axis: str) -> str:
        if axis == "all":
            return "new_all" if self.profile.product == 142 else "all"
        if axis not in self.profile.axes:
            raise ValueError(f"ISleep product {self.profile.product} has no {axis} control")
        if axis == "back" and self.profile.product in (129, 130, 143):
            return "head"
        return axis

    async def _move(self, axis: str, up: bool) -> None:
        axis = self._axis(axis)
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        lane = self._lane
        await self._ensure_session()
        client, generation, target, own = self.client, self._generation, self._target, self._own
        if self._coordinator.cancel_command.is_set():
            raise asyncio.CancelledError
        try:
            await self._send_opcode(self._opcode(axis + ("_up" if up else "_down"), lane))
            # HA gesture duration, not a hardware refresh interval. No repeated writes.
            duration = (
                self._coordinator.motor_pulse_count * self._coordinator.motor_pulse_delay_ms / 1000
            )
            try:
                await asyncio.wait_for(self._coordinator.cancel_command.wait(), duration)
            except TimeoutError:
                pass
        finally:
            if (
                client is self.client
                and generation == self._generation
                and client
                and client.is_connected
            ):
                assert own is not None and target is not None
                await self.write_command(
                    control_frame(own, target, self._opcode(axis + "_stop", lane), self._parameter),
                    cancel_event=asyncio.Event(),
                )

    async def _stop(self, axis: str) -> None:
        axis = self._axis(axis)
        # STOP never reconnects or authenticates into a new session.
        if self._ready and self._own is not None and self._target is not None:
            await self._send_opcode(self._opcode(axis + "_stop"), cancel=asyncio.Event())

    async def stop_all(self) -> None:
        # Flat 28/29/30 is never used as an emergency stop.
        for axis in (*self.profile.axes, "all"):
            await self._stop(axis)

    async def move_head_up(self) -> None:
        await self._move("head", True)

    async def move_head_down(self) -> None:
        await self._move("head", False)

    async def move_head_stop(self) -> None:
        await self._stop("head")

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_back_stop(self) -> None:
        await self._stop("back")

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    async def move_legs_stop(self) -> None:
        await self._stop("legs")

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", False)

    async def move_lumbar_stop(self) -> None:
        await self._stop("lumbar")

    async def preset_flat(self) -> None:
        await self._action("flat")

    async def preset_zero_g(self) -> None:
        await self._action("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._action("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2, 3):
            raise ValueError("ISleep memory slots are 1-3")
        await self._action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2, 3):
            raise ValueError("ISleep memory slots are 1-3")
        await self._action(f"save_{memory_num}")

    async def lights_on(self) -> None:
        await self._action("light_on")

    async def lights_off(self) -> None:
        await self._action("light_off")

    async def massage_toggle(self) -> None:
        lane = self._lane
        await self._action("massage_off" if self._massage[lane] else "massage_on")
        active = not self._massage[lane]
        for affected in self._affected_lanes:
            self._massage[affected] = active
        self._save_intent()

    async def massage_off(self) -> None:
        await self._action("massage_off")
        for affected in self._affected_lanes:
            self._massage[affected] = False
        self._save_intent()

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if (
            zone not in self.massage_intensity_zones
            or type(level) is not int
            or not 0 <= level <= 100
        ):
            raise ValueError("Invalid ISleep massage zone or strength (0-100)")
        await self._action(f"{zone}_strength", parameter=level)
        for affected in self._affected_lanes:
            self._strengths[affected][zone] = level
        self._save_intent()

    async def set_pattern(self, pattern: int) -> None:
        if type(pattern) is not int or pattern not in (0, 1, 2, 3):
            raise ValueError("ISleep pattern is 0-3")
        lane = self._lane
        selected = 0 if self._patterns[lane] == pattern else pattern
        await self._action(f"pattern_{selected}" if selected else "pattern_cancel")
        for affected in self._affected_lanes:
            self._patterns[affected] = selected
        self._save_intent()

    async def massage_mode_step(self) -> None:
        await self.set_pattern((self._patterns[self._lane] + 1) % 4)

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in (0, *self.massage_timer_options):
            raise ValueError("Invalid ISleep massage timer")
        lane = self._lane
        selected = 0 if minutes == self._timers[lane] else minutes
        action = (
            f"timer_{self.massage_timer_options.index(selected) + 1}"
            if selected
            else "timer_cancel"
        )
        await self._action(action)
        for affected in self._affected_lanes:
            self._timers[affected] = selected
        self._save_intent()

    def get_massage_state(self) -> dict[str, Any]:
        return self._massage_state(self._lane)

    def _massage_state(self, lane: int) -> dict[str, Any]:
        return {
            "head_active": self._massage[lane],
            "foot_active": self._massage[lane] and self.profile.product != 143,
            "head_intensity": self._strengths[lane]["head"],
            "foot_intensity": self._strengths[lane]["foot"],
            "mode": self._patterns[lane],
            "timer_mode": str(self._timers[lane]) if self._timers[lane] else None,
        }

    async def enroll_room(self) -> None:
        """Explicit fresh-device enrollment; never reset or steal another room."""
        from homeassistant.components import bluetooth

        from ..isleep_profile import isleep_advertisement

        info = bluetooth.async_last_service_info(
            self._coordinator.hass, self._coordinator.address, connectable=True
        )
        ad = isleep_advertisement(info.manufacturer_data) if info is not None else None
        if ad is None or ad.adv_type != 9 or ad.product_id != self.profile.product:
            raise ValueError(
                "Enrollment requires this bed's live unprovisioned mode09 advertisement"
            )
        await self.start_notify()
        generation = self._generation
        self._enrollment.clear()
        self._enroll_status = None
        try:
            await self.write_command(room_frame(self.profile.room, enroll=True))
            await self._wait(self._enrollment, 8, generation)
            if self._enroll_status != 0:
                raise ConnectionError(f"ISleep enrollment rejected ({self._enroll_status})")
            self._pending_ack = True
            self._pending_room = self.profile.room
            await self._coordinator.async_write_app_state(self, self.persisted_app_state)
        finally:
            # The app terminates enrollment on either status. The next control rejoins.
            await self._coordinator.async_disconnect()

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "product": self.profile.product,
            "room": self.profile.room,
            "split": self.profile.split,
            "authenticated": self._ready,
            "live_roster": self._target is not None,
            "pending_enrollment_ack": self._pending_ack,
            "hardware": "UNVERIFIED",
        }
