"""Shared authenticated Kaidi app session and cancellable gestures.

One press and a matching release, no held refresh and no position telemetry.
Frames come from the Kaidi mesh codec; the command table is this app's own
profile (``profiles/kaidi.py``), never a sibling app's.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, cast

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_HIDDEN, CARD_MASSAGE
from ...codec import kaidi as codec
from ...const import SIDE_LEFT, SIDE_RIGHT
from ...controller_state import StateUpdate, sided
from ...execution import ExecutionCapabilities
from ...profiles.kaidi import IsleepProfile, isleep_advertisement
from ...state_keys import MASSAGE_TIMER_MINUTES, massage_intensity
from ..base import BedController
from ..entity_specs import ControllerButtonSpec, MotorControlSpec

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class KaidiAppController(BedController):
    """Explicit app profile; live session addresses are never restored from disk."""

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: IsleepProfile) -> None:
        super().__init__(coordinator)
        self.profile = profile
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
    def pattern_count(self) -> int:
        return 3

    @property
    def execution(self) -> ExecutionCapabilities:
        """One start per press, then a per-axis release (#483)."""
        return ExecutionCapabilities(hold="latched")

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE_CHAR_UUID

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
        return self.profile.commands[action][self._lane if lane is None else lane]

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
            "neck": (
                lambda c: c.move_neck_up(),
                lambda c: c.move_neck_down(),
                lambda c: c.move_neck_stop(),
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
                f"{self.profile.key}_all_up",
                "All up",
                lambda c: cast(KaidiAppController, c)._move("all", True),
                translation_key=f"{self.profile.key}_all_up",
            ),
            ControllerButtonSpec(
                f"{self.profile.key}_all_down",
                "All down",
                lambda c: cast(KaidiAppController, c)._move("all", False),
                translation_key=f"{self.profile.key}_all_down",
            ),
            *(
                ControllerButtonSpec(
                    f"{self.profile.key}_pattern_{i}",
                    f"Massage pattern {i}" if i else "Cancel massage pattern",
                    lambda c, i=i: cast(KaidiAppController, c).set_pattern(i),
                    translation_key=f"{self.profile.key}_pattern",
                    translation_placeholders={"pattern": str(i)},
                    card=CARD_MASSAGE,
                )
                for i in range(self.pattern_count + 1)
            ),
            ControllerButtonSpec(
                f"{self.profile.key}_enroll",
                "Enroll unprovisioned bed in selected room",
                lambda c: cast(KaidiAppController, c).enroll_room(),
                translation_key=f"{self.profile.key}_enroll",
                card=CARD_HIDDEN,
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
            raise ValueError("Invalid saved Kaidi app strength parameter")
        for key, target, allowed in (
            ("massage", self._massage, (False, True)),
            ("patterns", self._patterns, tuple(range(self.pattern_count + 1))),
            ("timers", self._timers, (0, *self.massage_timer_options)),
        ):
            values = state.get(key)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(type(v) is not type(allowed[0]) or v not in allowed for v in values)
            ):
                raise ValueError(f"Invalid saved Kaidi app {key}")
            target[:] = values
        strengths = state.get("strengths")
        if not isinstance(strengths, list) or len(strengths) != 3:
            raise ValueError("Invalid saved Kaidi app strengths")
        for index, values in enumerate(strengths):
            if not isinstance(values, dict) or any(
                type(values.get(z)) is not int or not 0 <= values[z] <= 100
                for z in ("head", "foot")
            ):
                raise ValueError("Invalid saved Kaidi app zone strength")
            self._strengths[index] = {z: values[z] for z in ("head", "foot")}
        self._parameter = parameter
        self._publish_intent()

    def _publish_intent(self) -> None:
        """Publish each side's intent for display between connections."""
        updates: list[StateUpdate] = []
        for side, lane in (("left", 0), ("right", 1), ("both", 2)):
            index = lane if self.profile.split else 0
            updates.append(sided(MASSAGE_TIMER_MINUTES, side)(self._timers[index]))
            updates += [
                sided(massage_intensity(zone), side)(self._strengths[index][zone])
                for zone in ("head", "foot")
            ]
        self.forward_controller_state_updates(*updates)

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
            raise ConnectionError("Kaidi app is disconnected")
        generation = self._generation

        def notification(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if generation == self._generation:
                self._notification(sender, data)

        async with self._ble_lock:
            await client.start_notify(codec.NOTIFY_CHAR_UUID, notification)
        if generation != self._generation:
            raise ConnectionError("Kaidi app disconnected while subscribing")
        self._notify_started = True

    async def stop_notify(self) -> None:
        client = self.client
        try:
            if self._notify_started and client and client.is_connected:
                async with self._ble_lock:
                    await client.stop_notify(codec.NOTIFY_CHAR_UUID)
        finally:
            self.on_disconnect()

    async def read_positions(self, motor_count: int = 2) -> None:
        return

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        frame = bytes(data)
        self.forward_raw_notification(codec.NOTIFY_CHAR_UUID, frame)
        match codec.parse_notification(frame):
            case codec.JoinReply(status) if status is not None:
                self._auth_status = status
                self._auth.set()
            case codec.EnrollReply(status):
                self._enroll_status = status
                self._enrollment.set()
            case codec.OwnAddress(own):
                self._own = own or codec.BROADCAST
                self._own_event.set()
            case codec.RosterChange():
                self._target = None
                self._roster.clear()
            case codec.PingReply(node, target) if node == self._coordinator.address.upper():
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
            codec.WRITE_CHAR_UUID, command, response=True, cancel_event=cancel_event
        )

    async def _wait(self, event: asyncio.Event, timeout: float, generation: int) -> None:
        await asyncio.wait_for(event.wait(), timeout)
        if generation != self._generation or self.client is None or not self.client.is_connected:
            raise ConnectionError("Kaidi app session ended while waiting for a response")

    async def _ensure_session(self) -> None:
        async with self._session_lock:
            if self._ready and self._target is not None:
                # A failed acknowledgment stays pending on a live session too.
                await self._flush_pending_ack()
                return
            await self.start_notify()
            generation = self._generation
            if not self._ready:
                self._auth.clear()
                self._auth_status = None
                await self.write_command(codec.join(self.profile.room))
                await self._wait(self._auth, 5, generation)
                if self._auth_status != 0:
                    raise ConnectionError(
                        f"Kaidi app room authentication rejected ({self._auth_status})"
                    )
                if self._own is None:
                    self._own_event.clear()
                    await self._wait(self._own_event, 5, generation)
                self._ready = True
            self._roster.clear()
            await self.write_command(codec.ping(cast(int, self._own)))
            await self._wait(self._roster, 5, generation)
            await self._flush_pending_ack()

    async def _flush_pending_ack(self) -> None:
        """Send a pending enrollment acknowledgment, clearing it only on success."""
        if not self._pending_ack:
            return
        await self._send_opcode(self.profile.enroll_ack, cancel=asyncio.Event())
        self._pending_ack = False
        self._pending_room = None
        await self._coordinator.async_write_app_state(self, self.persisted_app_state)

    async def _send_opcode(self, opcode: int, *, cancel: asyncio.Event | None = None) -> None:
        if self._own is None or self._target is None:
            raise ConnectionError("Kaidi app has no live current-MAC roster mapping")
        await self.write_command(
            codec.control(self._target, self._own, opcode, self._parameter), cancel_event=cancel
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
            raise ValueError(f"Kaidi app product {self.profile.product} has no {axis} control")
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
            # A renewable hold (#483) waits for its lease, within its ceiling.
            duration = (
                self.leased_hold_ms(
                    self._coordinator.motor_pulse_count * self._coordinator.motor_pulse_delay_ms
                )
                / 1000
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
                    codec.control(target, own, self._opcode(axis + "_stop", lane), self._parameter),
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
            raise ValueError("Kaidi app memory slots are 1-3")
        await self._action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2, 3):
            raise ValueError("Kaidi app memory slots are 1-3")
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
            raise ValueError("Invalid Kaidi app massage zone or strength (0-100)")
        await self._action(f"{zone}_strength", parameter=level)
        for affected in self._affected_lanes:
            self._strengths[affected][zone] = level
        self._save_intent()

    async def set_pattern(self, pattern: int) -> None:
        if type(pattern) is not int or pattern not in (0, 1, 2, 3):
            raise ValueError("Kaidi app pattern is 0-3")
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
            raise ValueError("Invalid Kaidi app massage timer")
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

    def _enrollment_advertisement(self, manufacturer_data: Mapping[int, bytes]):
        return isleep_advertisement(manufacturer_data)

    async def enroll_room(self) -> None:
        """Explicit fresh-device enrollment; never reset or steal another room."""
        from homeassistant.components import bluetooth

        info = bluetooth.async_last_service_info(
            self._coordinator.hass, self._coordinator.address, connectable=True
        )
        ad = self._enrollment_advertisement(info.manufacturer_data) if info is not None else None
        if ad is None or ad.adv_type != 9 or ad.product_id != self.profile.product:
            raise ValueError(
                "Enrollment requires this bed's live unprovisioned mode09 advertisement"
            )
        await self.start_notify()
        generation = self._generation
        self._enrollment.clear()
        self._enroll_status = None
        try:
            await self.write_command(codec.enroll(self.profile.room))
            await self._wait(self._enrollment, self.profile.enroll_wait_s, generation)
            if self._enroll_status != 0:
                raise ConnectionError(f"Kaidi app enrollment rejected ({self._enroll_status})")
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
