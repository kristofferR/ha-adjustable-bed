"""Majestic Home's layouts over the shared Richmat catalog session.

HA serializes radio callbacks, fences the physical owner, drains an in-flight
write before STOP and bounds elapsed holds. It never reproduces the app's
overlapping async FIFO ticks or replays its pending motion after disconnect.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...card import CARD_PRESET_SAVE, CardPlacement, CardSection, memory_card
from ...codec import richmat as codec
from ...command_scheduler import CommandOutcome, current_command_context
from ...controller_state import StateKey
from ...execution import ExecutionCapabilities
from ...profiles.majestichome import LAYOUTS, STOP, TICK_MS, catalog, resolve_layout
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..goodvibe.controller import Gesture, GoodVibeController, Link
from .protocol import LIST_ALARMS, Alarm, Receiver, decode
from .requests import Request

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

MODEL: Final = StateKey[str]("majestichome_product")
OBSERVATIONS: Final = StateKey[dict[str, object]]("majestichome_observations")
ALARMS: Final = StateKey[list[dict[str, object]]]("majestichome_alarms")
WRITE_TIMEOUT_S: Final = 5.0  # HA transport bound, not a firmware motion timeout.
FIRST_WRITE_MS: Final = 100
ALARM_OBSERVATION_S: Final = 5.0  # HA observation window; no list-completeness proof.
READ_GUARD_S: Final = 0.1  # Recheck local ownership while waiting, without polling the bed.
MIN_FINITE_HOLD_MS: Final = 200


@dataclass(frozen=True, slots=True)
class Plan:
    request: Request
    link: Link
    packets: tuple[bytes, ...]
    records: tuple[Alarm, ...]
    stale: frozenset[int]


@dataclass(frozen=True, slots=True)
class Intent:
    """Validated input across an intentional sequential disconnect, never wire bytes."""

    owner: AdjustableBedCoordinator
    product: str
    request: Request
    alarm: Alarm | None


class MajesticHomeController(GoodVibeController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        self._physical_owner = coordinator
        self.layout = LAYOUTS[resolve_layout(product)]
        super().__init__(coordinator, profile=self.layout.key, catalog=catalog(self.layout.key))
        self._receiver = Receiver()
        self.observations: dict[str, object] = {}
        self.alarms: dict[int, Alarm] = {}
        self._stale: set[int] = set()
        self._movement_deadline: float | None = None
        self._reply_event = asyncio.Event()
        self._alarm_observer: Callable[[Alarm], None] | None = None

    @property
    def auto_stops_on_idle(self) -> bool:
        # Hold cleanup owns the real STOP. Avoid the generic extra release.
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.held_control_options)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, TICK_MS

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {}  # Product and local display name belong to the HA entry.

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        return

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "Majestic Home 1.0.4",
            "product": self.layout.key,
            "hardware_verified": False,
            "frozen_acquisition": "2026-07-14",
            "observations": dict(self.observations),
            "alarms": [asdict(a) for a in self.alarms.values()],
        }

    def _current_link(self) -> Link:
        link = super()._current_link()
        if (
            self._coordinator is not self._physical_owner
            or self._physical_owner.controller is not self
        ):
            raise ConnectionError("Majestic Home physical controller was replaced")
        if self.command_side is not None:
            raise ValueError("Majestic Home has no single-address side selector")
        return link

    async def _pace(self, cleanup: bool) -> bool:
        return cleanup or self._movement_allowed()

    def _movement_allowed(self) -> bool:
        if self._movement_deadline is None:
            return True
        context = current_command_context()
        if context is not None and context.lease is not None:
            if not context.active or context.cancel_event is not self._coordinator.cancel_command:
                return False
            if (
                context.hold_deadline is None
                or asyncio.get_running_loop().time() >= context.hold_deadline
            ):
                context.request_cancel(CommandOutcome.EXPIRED)
                return False
        return monotonic() < self._movement_deadline

    async def _send(
        self,
        data: bytes,
        *,
        cleanup: bool = False,
        link: Link | None = None,
        release_gesture: Gesture | None = None,
        on_submit: Callable[[], None] | None = None,
    ) -> bool:
        if self._next_write_at == 0:
            self._next_write_at = asyncio.get_running_loop().time() + FIRST_WRITE_MS / 1000

        async def write() -> bool:
            async with asyncio.timeout(WRITE_TIMEOUT_S):
                return await super(MajesticHomeController, self)._send(
                    data,
                    cleanup=cleanup,
                    link=link,
                    release_gesture=release_gesture,
                    on_submit=on_submit,
                )

        task = asyncio.create_task(write())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - propagate the settled result below.
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        return task.result()

    def _notification(self, link: Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        try:
            if self._current_link() is not link:
                return
        except ConnectionError, ValueError:
            return
        self.forward_raw_notification(sender.uuid, bytes(data))
        for packet in self._receiver.feed(bytes(data)):
            state = decode(packet)
            self.observations.update(state)
            if "alarm_number" in state:
                alarm = Alarm(*packet[6:12])
                if state["event"] == "list" or alarm.number in self.alarms:
                    self.alarms[alarm.number] = alarm
                    self._stale.discard(alarm.number)
                    if self._alarm_observer is not None:
                        self._alarm_observer(alarm)
        self._publish()
        self._reply_event.set()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._receiver = Receiver()
        self.observations.clear()
        self.alarms.clear()
        self._stale.clear()
        self._movement_deadline = None
        self._publish()
        self._reply_event.set()

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            MODEL(self.layout.key),
            OBSERVATIONS(dict(self.observations)),
            ALARMS([asdict(a) for a in self.alarms.values()]),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "majestichome",
                "majestichome",
                MODEL,
                "mdi:bed",
                # The product layout, carrying received bed replies and alarms as attributes.
                attribute_keys=(OBSERVATIONS, ALARMS),
                entity_registry_enabled_default=False,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[()]:
        return ()

    @property
    def controller_number_specs(self) -> tuple[()]:
        return ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.layout.controls if c.held)

    @property
    def execution(self) -> ExecutionCapabilities:
        return (
            ExecutionCapabilities(hold="stream")
            if self.held_control_options
            else ExecutionCapabilities()
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not MIN_FINITE_HOLD_MS <= duration_ms <= 60000
        ):
            raise ValueError(
                "Choose an available Majestic Home movement and a duration from 200 to 60000 ms"
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        submitted = await self._run_hold_window(control, duration_ms)
        if not submitted and not self._coordinator.cancel_command.is_set():
            raise TimeoutError("No Majestic Home movement was sent within the elapsed budget")

    async def _run_hold_window(self, control: str, duration_ms: int) -> bool:
        """App cadence, independent of the public finite-input minimum."""
        link = self._current_link()
        packet = codec.function(self.layout.control(control).code, single=link.legacy)
        started = monotonic()
        deadline = started + self.leased_hold_ms(duration_ms) / 1000
        self._movement_deadline = deadline
        submitted = False

        def mark_submitted() -> None:
            nonlocal submitted
            if not self._movement_allowed():
                if self._coordinator.cancel_command.is_set():
                    raise asyncio.CancelledError
                raise TimeoutError("The Majestic Home movement expired before submission")
            submitted = True

        try:
            # The first tick is delayed. Slow writes consume the elapsed budget,
            # rather than extending it or backfilling missed refreshes.
            due = started + TICK_MS / 1000
            while due <= deadline and not self._coordinator.cancel_command.is_set():
                if not await self._delay(max(0, round((due - monotonic()) * 1000))):
                    break
                if not self._movement_allowed():
                    break
                await self._send(packet, link=link, on_submit=mark_submitted)
                due = max(due + TICK_MS / 1000, monotonic() + TICK_MS / 1000)
            if (
                remaining := deadline - monotonic()
            ) > 0 and not self._coordinator.cancel_command.is_set():
                await self._delay(round(remaining * 1000))
        finally:
            self._movement_deadline = None
            if (
                submitted
                and self._link is link
                and self.client is link.client
                and link.client.is_connected
            ):
                await self._send(codec.function(STOP, single=link.legacy), cleanup=True, link=link)
        return submitted

    async def action(self, key: str, *, save: bool = False) -> None:
        control = self.layout.control(key)
        if control.held and not save:
            await self.hold_control(
                key, max(MIN_FINITE_HOLD_MS, self._coordinator.motor_pulse_count * TICK_MS)
            )
            return
        if save and control.save is None:
            raise ValueError("This Majestic Home control cannot be saved")
        link = self._current_link()
        await self._send(
            codec.function(
                control.save if save and control.save is not None else control.code,
                single=link.legacy,
            ),
            link=link,
        )

    async def stop_all(self) -> None:
        if not CONTROLLER_GESTURE_RELEASE.get():
            link = self._current_link()
            await self._send(codec.function(STOP, single=link.legacy), cleanup=True, link=link)

    async def move_head_up(self) -> None:
        await self.action("head_up")

    async def move_head_down(self) -> None:
        await self.action("head_down")

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_legs_up(self) -> None:
        await self.action("foot_up")

    async def move_legs_down(self) -> None:
        await self.action("foot_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                label,
                partial(_action, key=axis + "_up"),
                partial(_action, key=axis + "_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    axis + "_up", axis + "_down", stop_scope="side", press_is_native=True
                ),
            )
            for key, label, axis in (
                ("back", "head", "head"),
                ("legs", "feet", "foot"),
                ("lumbar", "lumbar", "lumbar"),
                ("both", "head_feet", "both"),
            )
            if axis + "_up" in self.held_control_options
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = []
        for control in self.layout.controls:
            if control.held:
                continue  # Native motor entities own these held controls.
            for save in (False, True) if control.save is not None else (False,):
                label = control.label
                if save:
                    # Match the shared "Save to Memory N" buttons.
                    label = ("Save to " if control.key.startswith("memory_") else "Save ") + label
                section = (
                    CardSection.MASSAGE
                    if control.group == "massage"
                    else CardSection.LIGHTING
                    if control.group == "light"
                    else CardSection.PRESETS
                )
                placement = (
                    memory_card(int(control.key[-1]), save=save)
                    if control.key.startswith("memory_")
                    else CARD_PRESET_SAVE
                    if save
                    else CardPlacement(section)
                )
                translation = "majestichome_" + (
                    control.key + ("_save" if save else "")
                    if control.key.startswith("memory_")
                    else "save_action"
                    if save
                    else control.group + "_action"
                )
                buttons.append(
                    ControllerButtonSpec(
                        "majestichome_" + control.key + ("_save" if save else ""),
                        label,
                        partial(_action, key=control.key, save=save),
                        translation_key=translation,
                        translation_placeholders={"action": label},
                        requires_confirmation=save,
                        card=placement,
                    )
                )
        return tuple(buttons)

    def validate_request(self, request: Request) -> None:
        if request.operation not in ("list", "set", "new", "toggle", "delete", "sync_clock"):
            raise ValueError("Unknown Majestic Home action")
        if request.number is not None and (
            type(request.number) is not int or not 0 <= request.number <= 255
        ):
            raise ValueError("Alarm ID must be a byte")
        if request.operation in ("new", "set", "toggle", "delete") and request.number is None:
            raise ValueError(
                "Choose an explicit alarm ID; received records do not prove a complete list"
            )
        if request.operation in ("new", "set"):
            if (
                request.preset not in self.layout.alarms
                or type(request.hour) is not int
                or not 0 <= request.hour <= 23
                or type(request.minute) is not int
                or not 0 <= request.minute <= 59
                or any(type(day) is not int or day not in range(7) for day in request.weekdays)
            ):
                raise ValueError("Choose a product alarm preset, valid time and weekdays")
            if (
                request.operation == "new"
                and request.number is not None
                and request.number not in range(1, 8)
            ):
                raise ValueError("New alarms use the app's IDs 1 through 7")
        if request.operation == "sync_clock" and not self.layout.alarms:
            raise ValueError("This product has no clock synchronization schedule")

    def prepare(self, request: Request) -> Plan:
        self.validate_request(request)
        link = self._current_link()
        if request.operation == "sync_clock":
            packets = codec.time_sync(dt_util.now(), build=self.record, first_hex=True)
        else:
            if not self.observations.get("clock_available"):
                raise ValueError("The current connection has not reported an alarm menu")
            if request.operation == "list":
                packets = (LIST_ALARMS,)
            elif request.operation in ("new", "set"):
                number = request.number
                assert number is not None
                repeat = sum(1 << (7 - d) for d in set(request.weekdays)) | int(request.enabled)
                packets = (
                    Alarm(
                        number,
                        0,
                        request.hour,
                        request.minute,
                        self.layout.control(request.preset).code,
                        repeat,
                    ).packet(),
                )
            else:
                assert request.number is not None
                if request.operation == "delete":
                    packets = (codec.record(5, 2, 1, (request.number,)),)
                else:
                    alarm = self.alarms.get(request.number)
                    if alarm is None or request.number in self._stale:
                        raise ValueError(
                            "Query current alarm fields before changing their enabled state"
                        )
                    packets = (alarm.toggle(request.enabled).packet(),)
        return Plan(request, link, packets, tuple(self.alarms.values()), frozenset(self._stale))

    async def _wait_for_settings(
        self,
        link: Link,
        *,
        deadline: float,
        available: Callable[[], bool] | None = None,
        validate_admission: Callable[[], None] | None = None,
    ) -> None:
        """Bound one live read; a window ending never proves list completeness."""
        cancel = self._coordinator.cancel_command
        cancelled = asyncio.create_task(cancel.wait())
        reply: asyncio.Task[bool] | None = None
        try:
            while True:
                self._reply_event.clear()
                if self._current_link() is not link:
                    raise ConnectionError("Majestic Home session changed while reading settings")
                if validate_admission is not None:
                    validate_admission()
                if cancel.is_set():
                    raise asyncio.CancelledError
                if available is not None and available():
                    return
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    if available is not None:
                        raise TimeoutError("The requested Majestic Home settings were not received")
                    return
                reply = asyncio.create_task(self._reply_event.wait())
                await asyncio.wait(
                    (reply, cancelled),
                    timeout=min(READ_GUARD_S, remaining),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                reply.cancel()
                await asyncio.gather(reply, return_exceptions=True)
                reply = None
        finally:
            cancelled.cancel()
            if reply is not None:
                reply.cancel()
            await asyncio.gather(
                cancelled, *(() if reply is None else (reply,)), return_exceptions=True
            )

    async def prepare_live(
        self, request: Request, *, validate_admission: Callable[[], None] | None = None
    ) -> Plan:
        """Read required fields on the current link before building bytes."""
        self.validate_request(request)
        link = self._current_link()
        if request.operation != "sync_clock" and not self.observations.get("clock_available"):
            await self._send(
                codec.function(1, action="deviceFunctionItemCheckClock", single=link.legacy),
                link=link,
                on_submit=validate_admission,
            )
            await self._wait_for_settings(
                link,
                deadline=asyncio.get_running_loop().time() + WRITE_TIMEOUT_S,
                available=lambda: bool(self.observations.get("clock_available")),
                validate_admission=validate_admission,
            )
        if request.operation == "toggle":
            number = request.number
            assert number is not None

            def invalidate() -> None:
                if validate_admission is not None:
                    validate_admission()
                self.alarms.pop(number, None)
                self._stale.add(number)
                self._publish()

            await self._send(LIST_ALARMS, link=link, on_submit=invalidate)
            await self._wait_for_settings(
                link,
                deadline=asyncio.get_running_loop().time() + WRITE_TIMEOUT_S,
                available=lambda: number in self.alarms and number not in self._stale,
                validate_admission=validate_admission,
            )
        return self.prepare(request)

    def capture_intent(self, plan: Plan) -> Intent:
        self.validate_plan(plan)
        number = plan.request.number
        return Intent(
            self._physical_owner,
            self.layout.key,
            plan.request,
            self.alarms.get(number)
            if number is not None and plan.request.operation == "toggle"
            else None,
        )

    async def prepare_intent(
        self, intent: Intent, *, validate_admission: Callable[[], None] | None = None
    ) -> Plan:
        if self._physical_owner is not intent.owner or self.layout.key != intent.product:
            raise ValueError("Majestic Home physical owner or product changed after preflight")
        plan = await self.prepare_live(intent.request, validate_admission=validate_admission)
        if intent.request.operation == "toggle":
            assert intent.request.number is not None
            if self.alarms.get(intent.request.number) != intent.alarm:
                raise ValueError("Majestic Home alarm fields changed after preflight")
        return plan

    def validate_plan(self, plan: Plan) -> None:
        if (
            self._current_link() is not plan.link
            or tuple(self.alarms.values()) != plan.records
            or frozenset(self._stale) != plan.stale
        ):
            raise ValueError("The Majestic Home session or alarm list changed during admission")

    async def execute_prepared(
        self,
        plan: Plan,
        *,
        validate_admission: Callable[[], None] | None = None,
        on_submit: Callable[[], None] | None = None,
    ) -> tuple[Alarm, ...] | None:
        self.validate_plan(plan)
        if plan.request.operation == "list":
            observed: dict[int, Alarm] = {}
            deadline = 0.0

            def observe(alarm: Alarm) -> None:
                if asyncio.get_running_loop().time() < deadline:
                    observed[alarm.number] = alarm

            def begin() -> None:
                nonlocal deadline
                self.validate_plan(plan)
                if validate_admission is not None:
                    validate_admission()
                if on_submit is not None:
                    on_submit()
                deadline = asyncio.get_running_loop().time() + ALARM_OBSERVATION_S
                self.alarms.clear()
                self._stale.clear()
                self._publish()
                self._alarm_observer = observe

            try:
                if not await self._send(LIST_ALARMS, link=plan.link, on_submit=begin):
                    raise asyncio.CancelledError
                await self._wait_for_settings(
                    plan.link, deadline=deadline, validate_admission=validate_admission
                )
                return tuple(observed.values())
            finally:
                self._alarm_observer = None
        for packet in plan.packets:
            self.validate_plan(plan)

            # Fence again after pacing/lock waits, at actual submission.
            def submitted(packet: bytes = packet) -> None:
                self.validate_plan(plan)
                if validate_admission is not None:
                    validate_admission()
                if on_submit is not None:
                    on_submit()
                if plan.request.operation in ("new", "set", "toggle", "delete"):
                    self._stale.add(packet[6])

            await self._send(packet, link=plan.link, on_submit=submitted)
        return None


async def _action(controller: BedController, key: str, *, save: bool = False) -> None:
    if not isinstance(controller, MajesticHomeController):
        raise TypeError("Majestic Home controller required")
    await controller.action(key, save=save)


async def build_controller(ctx: BuildContext) -> MajesticHomeController:
    return MajesticHomeController(ctx.coordinator, product=ctx.variant or "")
