"""Accepted KomfyD / ComfyDS bed controls over the proven Kaidi codec.

Android UI callbacks are represented by the admitted HA operation. Recall
repeats end on ACK, cancellation or session loss, and never resume on another
link. There is no memory/global emergency STOP in either accepted inventory.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final, cast

from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_PRESETS, CARD_UTILITY
from ...codec import kaidi as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey, sided
from ...execution import ExecutionCapabilities
from ...profiles.comfy import (
    COMFY_ACTIONS,
    ComfyProfile,
    signed32,
    validate_comfy_profile,
    wire_target,
)
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .app import KaidiAppController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

SELECTED_SIDE: Final = StateKey[str | None]("comfy_selected_side")
TIMER_SELECTION: Final = StateKey[str | None]("comfy_timer_selection")
TIMER_REMAINING: Final = StateKey[int | None]("comfy_timer_remaining")
LOCK_STATUS: Final = StateKey[str | None]("comfy_lock_status")
LOCK_OWNER: Final = StateKey[int | None]("comfy_lock_owner")


class ComfyController(KaidiAppController):
    """App-specific data and session effects; shared subscription and held motors."""

    profile: ComfyProfile

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, validate_comfy_profile(coordinator.entry.data))
        # ComfyDS explicitly starts with zero and retains the installed source
        # across reconnect. KomfyD's initial source is unestablished: await it.
        self._own = 0 if self.profile.retain_source_on_reconnect else None
        self._selected_side: int | None = 0
        self._lock_owner = 0
        self._lock_status = "unlocked"
        self._memory_ack = asyncio.Event()
        self._led = [False, False, False]
        self._timer_minutes = [10, 10, 10]
        self._timer_started = [0.0, 0.0, 0.0]
        self._countdown: asyncio.TimerHandle | None = None
        self._write_lane = asyncio.Lock()
        self._next_write_at = 0.0
        self._ping_task: asyncio.Task[None] | None = None
        self._sdk_nodes: dict[str, dict[str, int]] = {}
        coordinator.entry.async_on_unload(self._stop_countdown)
        self._publish()

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def commands_share_timer(self) -> bool:
        # One app-global recall callback/ACK owner. HA serializes operations
        # across logical sides instead of resurrecting overlapping callbacks.
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        # The app labels this Zero; its physical posture is not established.
        return False

    @property
    def supports_preset_anti_snore(self) -> bool:
        return False

    @property
    def supports_massage(self) -> bool:
        return False

    @property
    def supports_massage_intensity_control(self) -> bool:
        return False

    @property
    def supports_massage_timer(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        return self.profile.can_store

    @property
    def _lane(self) -> int:
        return self._feature_lane("motion")

    def _feature_lane(self, feature: str) -> int:
        if feature != "lock" and not self.profile.split:
            return 0
        if self.command_side is not None:
            return {"left": 0, "right": 1, "both": 2}[self.command_side]
        if self._selected_side is None:
            # V04: default per feature, not a universal side value.
            return {"motion": 1, "light": 2, "timer": 0, "lock": 2}.get(feature, 1)
        return {0: 0, 1: 2}.get(self._selected_side, 1)

    def _opcode(self, action: str, lane: int | None = None) -> int:
        if (
            action.startswith(("h_", "f_"))
            and self.profile.key == "comfyds"
            and self.profile.split
            and self._selected_side is None
            and self.command_side is None
            and lane is None
        ):
            # G2b establishes no ComfyDS H/F missing-record fallback.
            raise ValueError("Select a bed side before using H/F steps")
        feature = (
            "lock"
            if action in ("lock", "unlock")
            else "light"
            if action.startswith("light_")
            else "timer"
            if action.startswith("timer_")
            else "motion"
        )
        return self.profile.commands[action][self._feature_lane(feature) if lane is None else lane]

    def _axis(self, axis: str) -> str:
        if axis == "head":
            return "head"
        if axis not in self.profile.axes:
            raise ValueError(f"Unknown app control {axis}")
        return "head" if axis == "back" else axis

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        labels = {"back": "comfy_head", "legs": "comfy_foot", "lumbar": "comfy_waist"}
        return tuple(
            replace(spec, translation_key=labels[spec.key]) for spec in super().motor_control_specs
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"comfy_{action}",
                action.replace("_", " "),
                lambda c, action=action: cast(ComfyController, c).control(action),
                translation_key=f"comfy_{action}",
                card=CARD_PRESETS if action == "zero" else CARD_UTILITY,
            )
            for action in COMFY_ACTIONS
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        side = (
            (
                ControllerSelectSpec(
                    "comfy_selected_side",
                    "comfy_selected_side",
                    SELECTED_SIDE,
                    ("left", "both", "right"),
                    lambda c, value: cast(ComfyController, c).select_side(value),
                    local_select_fn=self._select_side,
                ),
            )
            if self.profile.split and self.command_side is None
            else ()
        )
        return (
            *side,
            ControllerSelectSpec(
                "comfy_timer_selection",
                "comfy_timer_selection",
                TIMER_SELECTION,
                ("10", "20", "30", "40", "50"),
                lambda c, value: cast(ComfyController, c).select_timer(int(value)),
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "comfy_lock_status",
                "comfy_lock_status",
                LOCK_STATUS,
                "mdi:lock",
                attribute_keys=(LOCK_OWNER,),
            ),
            ControllerStateSensorSpec(
                "comfy_timer_remaining",
                "comfy_timer_remaining",
                TIMER_REMAINING,
                "mdi:timer-outline",
                "s",
            ),
        )

    def _publish(self) -> None:
        side = (
            None
            if self._selected_side is None
            else {0: "left", 1: "both", 2: "right"}[self._selected_side]
        )
        self.forward_controller_state_updates(
            SELECTED_SIDE(side),
            LOCK_STATUS(self._lock_status),
            LOCK_OWNER(self._lock_owner),
        )
        for name, lane in (
            (None, self._feature_lane("timer")),
            ("left", 0),
            ("right", 1),
            ("both", 2),
        ):
            start = self._timer_started[lane]
            remaining = (
                max(0, int(self._timer_minutes[lane] * 60 - (time.time() - start))) if start else 0
            )
            self.forward_controller_state_updates(
                sided(TIMER_SELECTION, name)(str(self._timer_minutes[lane])),
                sided(TIMER_REMAINING, name)(remaining),
                sided(UNDER_BED_LIGHTS_ON, name)(
                    self._led[
                        (self._feature_lane("light") if name is None else lane)
                        if self.profile.split
                        else 0
                    ]
                ),
            )

    def _stop_countdown(self) -> None:
        if self._countdown is not None:
            self._countdown.cancel()
            self._countdown = None

    def _tick(self) -> None:
        self._stop_countdown()
        self._publish()
        if any(
            start and time.time() < start + minutes * 60
            for start, minutes in zip(self._timer_started, self._timer_minutes, strict=True)
        ):
            self._countdown = asyncio.get_running_loop().call_later(1, self._tick)

    def _save_local(self) -> None:
        self._tick()
        self._coordinator.save_app_state(self)

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        return {
            "profile": self.profile.key,
            "room": self.profile.room,
            "raw_type": self.profile.raw_type,
            "side": self._selected_side,
            "owner": self._lock_owner,
            "led": list(self._led),
            "timer_minutes": list(self._timer_minutes),
            "timer_started": list(self._timer_started),
        }

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        # Live target, source, auth and a pending recall never restore from disk.
        if (state.get("profile"), state.get("room"), state.get("raw_type")) != (
            self.profile.key,
            self.profile.room,
            self.profile.raw_type,
        ):
            self._publish()
            return
        side = state.get("side")
        if side is not None and (type(side) is not int or side not in (0, 1, 2)):
            raise ValueError("Invalid saved app side")
        owner = state.get("owner", 0)
        if type(owner) is not int or not 0 <= owner <= 255:
            raise ValueError("Invalid saved lock owner")
        led, minutes, started = (
            state.get(key) for key in ("led", "timer_minutes", "timer_started")
        )
        if not isinstance(led, list) or len(led) != 3 or any(type(v) is not bool for v in led):
            raise ValueError("Invalid saved light intent")
        if (
            not isinstance(minutes, list)
            or len(minutes) != 3
            or any(type(v) is not int or v not in (10, 20, 30, 40, 50) for v in minutes)
        ):
            raise ValueError("Invalid saved timer selection")
        if (
            not isinstance(started, list)
            or len(started) != 3
            or any(type(v) not in (int, float) or not 0 <= v <= time.time() for v in started)
        ):
            raise ValueError("Invalid saved local timer start")
        self._selected_side, self._lock_owner = side, owner
        self._led, self._timer_minutes, self._timer_started = (
            list(led),
            list(minutes),
            list(started),
        )
        self._tick()

    def _select_side(self, value: str) -> None:
        if not self.profile.split or value not in ("left", "both", "right"):
            raise ValueError("This product has no selectable bed side")
        self._selected_side = {"left": 0, "both": 1, "right": 2}[value]
        self._save_local()

    async def select_side(self, value: str) -> None:
        self._select_side(value)

    def on_disconnect(self) -> None:
        own = self._own
        if self._ping_task is not None:
            self._ping_task.cancel()
            self._ping_task = None
        super().on_disconnect()
        self._own = own if self.profile.retain_source_on_reconnect else None
        self._memory_ack.set()
        self._next_write_at = 0.0
        # The local lock/LED/timer record survives; it is not physical telemetry.

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Capture bytes/link before pacing; never retry or replay on a new session."""
        client, generation = self.client, self._generation
        cancel = cancel_event or self._coordinator.cancel_command
        async with self._write_lane:
            delay = max(0, self._next_write_at - time.monotonic())
            if not self._next_write_at:
                delay = self.profile.first_write_s
            if delay:
                try:
                    await asyncio.wait_for(cancel.wait(), delay)
                except TimeoutError:
                    pass
            async with self._ble_lock:
                if cancel.is_set():
                    raise asyncio.CancelledError
                if (
                    generation != self._generation
                    or client is not self.client
                    or not client
                    or not client.is_connected
                ):
                    raise ConnectionError("App frame belongs to a disconnected session")
                self._record_command_trace(codec.WRITE_CHAR_UUID, command, response=True)
                await client.write_gatt_char(codec.WRITE_CHAR_UUID, command, response=True)
                self._next_write_at = time.monotonic() + self.profile.write_spacing_s

    async def _ensure_session(self) -> None:
        async with self._session_lock:
            if self._ready and self._target is not None:
                return
            await self.start_notify()
            generation = self._generation
            if not self._ready:
                if self._own is None:
                    self._own_event.clear()
                self._auth.clear()
                self._auth_status = None
                await self.write_command(codec.join(self.profile.room))
                await self._wait(self._auth, self.profile.join_timeout_s, generation)
                if self._auth_status != 0:
                    raise ConnectionError("Existing-room authentication failed")
                if self._own is None:
                    await self._wait(self._own_event, self.profile.join_timeout_s, generation)
                self._ready = True
            self._roster.clear()
            assert self._own is not None
            await self.write_command(codec.ping(self._own))
            if self._target is None:
                await self._wait(self._roster, self.profile.join_timeout_s, generation)
            if self._target is None or self._target == 0:
                raise ConnectionError("No live nonzero bed destination")

    async def async_after_connect(self, session: ControllerSession) -> None:
        await self._ensure_session()
        await self._send_opcode(self._opcode("query"))

    def _notification(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        frame = bytes(data)
        self.forward_raw_notification(codec.NOTIFY_CHAR_UUID, frame)
        match codec.parse_notification(frame):
            case codec.JoinReply(status) if status is not None:
                self._auth_status = status
                self._auth.set()
            case codec.OwnAddress(own):
                self._own = own or codec.BROADCAST
                self._own_event.set()
                self._schedule_ping()
            case codec.RosterChange():
                self._target = None
                self._roster.clear()
                self._sdk_nodes.clear()
                self._schedule_ping()
            case codec.PingReply(node, target) if node == self._coordinator.address.upper():
                signed = signed32(target)
                self._target = -2 if signed == 0 else signed
                self._roster.set()
            case codec.ControlReply(command, value) if len(frame) == 14:
                # Registered channel20 consumes exact8-byte payloads without a
                # selected-node/source filter. The full37..60 ACK range survives.
                if 37 <= command <= 60:
                    self._memory_ack.set()
                elif command in (61, 62, 63):
                    self._lock_owner = value
                    self._lock_status = "local"
                    self._save_local()
                elif command == 70:
                    self._lock_status = (
                        "unlocked"
                        if value == 0
                        else "local"
                        if self._lock_owner != 0 and value == self._lock_owner
                        else "other"
                    )
                    self._publish()
        if self.profile.key == "comfyds":
            self._parse_sdk_metadata(frame)

    def _schedule_ping(self) -> None:
        if not self._ready or self._own is None:
            return
        generation, own = self._generation, self._own

        async def send() -> None:
            if generation != self._generation:
                return
            try:
                await self.write_command(codec.ping(own))
            except ConnectionError:
                # Roster hydration is retried by the next admitted operation.
                return

        self._ping_task = self._coordinator.entry.async_create_background_task(
            self._coordinator.hass, send(), "KomfyD/ComfyDS roster ping"
        )

    def _parse_sdk_metadata(self, frame: bytes) -> None:
        # P03: conditional SDK state has no app capability/catalog consumer.
        if len(frame) != 20 or frame[0] != 3 or frame[5] not in (0x23, 0x24, 0x25, 0x28):
            return
        if frame[10] == 0x80:
            mac = codec.node_address(frame[11:17])
            target = signed32(
                int.from_bytes(frame[12:16] if mac in self._sdk_nodes else frame[6:10], "little")
            )
            self._sdk_nodes[mac] = {
                "virtual": target,
                "product": int.from_bytes(frame[17:18], signed=True),
            }
        elif frame[10] == 0xD7 and frame[12:18] == bytes(6):
            target = signed32(int.from_bytes(frame[6:10], "little"))
            for node in self._sdk_nodes.values():
                if node["virtual"] == target:
                    node["group"] = int.from_bytes(frame[18:19], signed=True)

    def _ordinary_guard(self, *, release: bool = False) -> None:
        if self._target is not None and not (self._target > 0 or self._target == -2):
            raise ValueError("Ordinary app controls require a positive destination or -2")
        if not release and self._lock_status != "unlocked":
            raise ValueError("The app control panel is locked")

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        self._axis(motor)
        self._ordinary_guard()

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        if self._lock_status != "unlocked":
            raise ValueError("The app control panel is locked")

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        # Readiness also serves direct unlock/query, whose admission differs.
        await self._ensure_session()

    async def _send_opcode(self, opcode: int, *, cancel: asyncio.Event | None = None) -> None:
        if self._own is None or self._target is None:
            raise ConnectionError("No live app source/destination")
        await self.write_command(
            codec.control(wire_target(self._target), self._own, opcode), cancel_event=cancel
        )

    async def _move(self, axis: str, up: bool) -> None:
        self._ordinary_guard()
        await self._ensure_session()
        self._ordinary_guard()
        # The shared gesture captures side, destination, source and generation
        # for its release. Its wire target needs the app's -2 normalization.
        await self._gesture(
            self._opcode(self._axis(axis) + ("_up" if up else "_down")),
            self._opcode(self._axis(axis) + "_stop"),
        )

    async def _gesture(self, opcode: int, release: int) -> None:
        client, generation, target, own = self.client, self._generation, self._target, self._own
        assert target is not None and own is not None
        context = current_command_context()
        if context is not None:
            context.cleanup_stop_sent = False
        try:
            await self._send_opcode(opcode)
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
                await self.write_command(
                    codec.control(wire_target(target), own, release), cancel_event=asyncio.Event()
                )
                if context is not None:
                    context.cleanup_stop_sent = True

    def _consume_preempted_release(self) -> bool:
        context = current_command_context()
        if context is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return True
        return False

    async def _stop(self, axis: str) -> None:
        if self._consume_preempted_release():
            return
        if self._ready and self._target is not None and self._own is not None:
            self._ordinary_guard(release=True)
            await self._send_opcode(
                self._opcode(self._axis(axis) + "_stop"), cancel=asyncio.Event()
            )

    async def stop_all(self) -> None:
        if self._consume_preempted_release():
            return
        # Protocol-specific fan-out only; no fabricated global/memory STOP.
        for axis in self.profile.axes:
            await self._stop(axis)

    def validate_control(self, action: str) -> None:
        if action not in COMFY_ACTIONS:
            raise ValueError("Unknown KomfyD/ComfyDS action")
        self._opcode(action)
        if self._target is not None:
            wire_target(self._target)
        if action not in ("lock", "unlock", "query"):
            self._ordinary_guard()

    async def control(self, action: str) -> None:
        self.validate_control(action)
        timer_lane = self._feature_lane("timer") if action.startswith("timer_") else None
        await self._ensure_session()
        self.validate_control(action)
        if action == "zero":
            await self._gesture(self._opcode("zero"), self._opcode("preset_stop"))
            return
        await self._send_opcode(self._opcode(action, timer_lane))
        if action in ("lock", "unlock"):
            self._lock_status = "local" if action == "lock" else "unlocked"
            self._save_local()
        elif timer_lane is not None:
            self._timer_started[timer_lane] = time.time() if action == "timer_start" else 0
            self._save_local()

    async def _action(self, action: str, *, parameter: int | None = None) -> None:
        # Legacy sibling-app preset/massage methods never select this app's bytes.
        raise NotImplementedError("Use this app's named controls")

    async def enroll_room(self) -> None:
        raise NotImplementedError("Room administration is outside direct bed control")

    async def preset_flat(self) -> None:
        await self._ensure_session()
        self._ordinary_guard()
        await self._gesture(self._opcode("flat"), self._opcode("preset_stop"))

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._ensure_session()
        self.validate_memory_recall(memory_num)
        self._memory_ack.clear()
        generation = self._generation
        # The admitted HA operation owns the callback. Source and destination
        # are read for each new frame, but paced bytes are already captured.
        while generation == self._generation and not self._memory_ack.is_set():
            if self._coordinator.cancel_command.is_set():
                break
            await self._send_opcode(self._opcode(f"memory_{memory_num}"))
            try:
                await asyncio.wait_for(self._memory_ack.wait(), self.profile.memory_repeat_s)
            except TimeoutError:
                pass
        # Cancellation ends only the callback; neither app defines a memory STOP.

    async def program_memory(self, memory_num: int) -> None:
        if not self.supports_memory_programming or memory_num not in (1, 2, 3, 4):
            raise ValueError("Memory save requires a store-capable bed and slot 1-4")
        await self._ensure_session()
        await self._send_opcode(self._opcode(f"save_{memory_num}"))

    async def select_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in (10, 20, 30, 40, 50):
            raise ValueError("The app timer selections are 10, 20, 30, 40 or 50 minutes")
        lane = self._feature_lane("timer")
        await self._ensure_session()
        self._ordinary_guard()
        await self._send_opcode(self._opcode(f"timer_{minutes}", lane))
        self._timer_minutes[lane] = minutes
        self._save_local()

    async def _light(self, enabled: bool) -> None:
        lane = self._feature_lane("light")
        await self._ensure_session()
        self._ordinary_guard()
        await self._send_opcode(self._opcode("light_on" if enabled else "light_off", lane))
        for index in (0, 1, 2) if lane == 2 else (lane,):
            self._led[index] = enabled
        self._save_local()

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "app": self.profile.key,
            "raw_type": self.profile.raw_type,
            "product": self.profile.product,
            "capability_word": self.profile.actuators,
            "authenticated": self._ready,
            "live_target": self._target,
            "local_side": self._selected_side,
            "lock_status": self._lock_status,
            "sdk_nodes": len(self._sdk_nodes),
            "hardware": "UNVERIFIED",
        }
