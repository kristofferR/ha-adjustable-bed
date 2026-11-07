"""Good Vibe Sleep exact product controls and independent sleep-sensor sessions."""

from __future__ import annotations

import asyncio
import logging
import re
import zlib
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...card import CARD_HIDDEN, CARD_UTILITY, CardPlacement, CardSection
from ...codec import richmat as codec
from ...command_scheduler import CommandContext, current_command_context
from ...controller_state import StateKey
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.richmat import GOODVIBE
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
)
from . import protocol as p
from .catalog import ACTION_EXPANSIONS, ACTIONS, PRODUCTS, Action
from .receive import Notifications
from .sleep import Realtime, Receiver, sleep_packet

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from .services import Request

_LOGGER = logging.getLogger(__name__)

# Normal-product service -> (write characteristic, single-byte commands).
GATT = {
    transport.service_uuid: (transport.write_uuid, transport.single)
    for transport in (codec.TRANSPORTS[key] for key in GOODVIBE.transports)
}
# Connection startup: exit limit, then the clock and light menu checks.
STARTUP = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
)
MENU_PROBE_S = 0.3
TICK_MS = 100
"""A sustained press first sends after one tick, then once per tick."""
LONG_PRESS_MS = 3000
POLL_S = 2
"""Live sleep-data polling interval."""
EXPIRY_S = 0.5
"""Incomplete notification bytes are dropped after this long."""
SLEEP_SERVICES = frozenset(
    ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "2320567c-05cf-6eb4-c341-772851827e1b")
)


STATUS: Final = StateKey[str | None]("goodvibe_status")
EVENTS: Final = StateKey[dict[str, object]]("goodvibe_events")
REJECTION: Final = StateKey[str | None]("goodvibe_rejection")
SIDE: Final = StateKey[str | None]("goodvibe_side")
MONITORING: Final = StateKey[bool]("goodvibe_monitoring")
MEMORY: Final = StateKey[bool]("goodvibe_memory")
LIGHT_DURATION: Final = StateKey[str | None]("goodvibe_light_duration")
SNORE_COUNT: Final = StateKey[int | None]("goodvibe_snore_count")
SNORE_TIME: Final = StateKey[int | None]("goodvibe_snore_time")
MASSAGE_TIMER: Final = StateKey[str | None]("goodvibe_massage_timer")


def _live_key(side: str, name: str) -> StateKey[object]:
    """One realtime sleep-monitoring reading."""
    return StateKey[object](f"goodvibe_{side}_{name}")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    tx: BleakGATTCharacteristic
    rx: BleakGATTCharacteristic
    legacy: bool


@dataclass(slots=True)
class Gesture:
    side: int
    cancel_event: asyncio.Event
    owner: asyncio.Task[object] | None
    context: CommandContext | None
    release_generation: int | None = None

    @property
    def release_is_current(self) -> bool:
        return (
            self.context is not None
            and self.context.active
            and self.release_generation is not None
            and self.context.cancel_generation == self.release_generation
        )


@dataclass
class Choices:
    side: int = 0
    release: bool = True
    hold: bool = False
    memory: bool = False
    monitoring: bool = False
    sequence: int = 0
    events: dict[str, object] = field(default_factory=dict)
    realtime: dict[str, Realtime] = field(
        default_factory=lambda: {"L": Realtime(), "R": Realtime()}
    )


def selected(controller: BedController) -> GoodVibeController:
    if not isinstance(controller, GoodVibeController):
        raise TypeError("This action requires Good Vibe Sleep")
    return controller


async def _press(controller: BedController, *, detail: str, duration: int = 1000) -> None:
    await controller.hold_control("goodvibe_" + detail, duration)


async def _release(controller: BedController) -> None:
    # STOP admission cancels the held task, whose finally owns its release frame.
    return


def _stop(side: int, link: Link) -> bytes:
    return codec.function(GOODVIBE.stop, side, single=link.legacy)


def label(action: Action) -> str:
    key = action.label.removeprefix("deviceFunctionItem").removeprefix("deviceFunctionSofa")
    return re.sub(r"(?<!^)(?=[A-Z])", " ", key)


def select_link(client: BleakClient, kind: int) -> Link:
    tx = rx = None
    legacy = False
    for service in client.services:
        uuid = service.uuid.lower()
        if kind == 1:
            pair = GATT.get(uuid)
            if pair is None:
                continue
            target, legacy = pair
        else:
            if uuid not in SLEEP_SERVICES:
                continue
            target = "00000002-3c17-d293-8e48-14fe2e4da212"
        for char in service.characteristics:
            if tx is None:
                if kind == 2:
                    matches = "write-without-response" in char.properties
                else:
                    matches = char.uuid.lower() == target and "write" in char.properties
                if matches:
                    tx = char
            if (
                rx is None
                and "notify" in char.properties
                and (kind != 3 or char.uuid.lower() == "00000003-3c17-d293-8e48-14fe2e4da212")
            ):
                rx = char
    if tx is None or rx is None:
        raise ValueError("Good Vibe Sleep requires its selected write and notify characteristics")
    return Link(client, tx, rx, legacy)


class GoodVibeController(BedController):
    """A normal product or a separate RM-/HJ- sleep device, chosen explicitly."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: str) -> None:
        super().__init__(coordinator)
        if profile not in PRODUCTS and profile not in ("sleep_rm", "sleep_hj"):
            raise ValueError("Choose the exact product in Good Vibe Sleep")
        self.profile = GOODVIBE
        self.product_key = profile
        self.kind = 2 if profile == "sleep_rm" else 3 if profile == "sleep_hj" else 1
        self.product = PRODUCTS.get(profile)

        def initial() -> Choices:
            choices = Choices(
                release=self.product is None
                or self.product.label not in ("BRRM", "APRM", "YFRM", "YGRM")
            )
            if self.product is not None and self.product.light:
                model = self.product.label.split(" / ")[0]
                choices.events["light_duration"] = (
                    900 if model == "FMRM" else 14400 if model == "RNRN" else 300
                )
            return choices

        self.choices = app_session(
            coordinator.hass, coordinator.address, ("goodvibe", profile), initial
        )
        self._address = coordinator.address
        self._link: Link | None = None
        self._gesture: Gesture | None = None
        self._expiry: asyncio.TimerHandle | None = None
        self._poll: asyncio.Task[None] | None = None
        self._followups: set[asyncio.Task[None]] = set()
        self._normal = Notifications(self._event)
        self._sleep = Receiver(self.kind) if self.kind != 1 else None
        self._pending_single: dict[str, object] | None = None
        self._report_ready = asyncio.Event()
        self._report_done = asyncio.Event()
        self._report_error: str | None = None
        self._report_context: tuple[int, int, int, int, int] | None = None
        self._last_event: str | None = None
        self._rejection: str | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else "00000002-3c17-d293-8e48-14fe2e4da212"

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return super().requires_persistent_connection or self.choices.monitoring or (
            self._sleep is not None and self._sleep.last in ("q_report", "q_report_allow")
        )

    @property
    def requests_connection_recovery(self) -> bool:
        return self.choices.monitoring

    @property
    def supports_motor_control(self) -> bool:
        return False  # App labels are retained without inferred physical axes.

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
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.product is not None and 0 in self.product.sides and 1 in self.product.sides

    @property
    def persisted_app_state_key(self) -> str:
        return "goodvibe:" + self.product_key

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # Only choices the app writes to local storage are durable across restarts.
        return {
            key: deepcopy(self.choices.events[key])
            for key in ("saved_single", "light_color", "light_duration")
            if key in self.choices.events
        }

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        saved = state.get("saved_single")
        if saved is not None:
            if (
                self.product is None
                or not isinstance(saved, dict)
                or set(saved) != {"time", "action"}
                or saved.get("action") not in self.product.alarms
                or not isinstance(saved.get("time"), str)
            ):
                raise ValueError("Invalid saved Good Vibe alarm")
            from datetime import datetime

            when = datetime.fromisoformat(saved["time"])
            if when.utcoffset() is None:
                raise ValueError("Saved alarm lacks a timezone")
        color = state.get("light_color")
        if color is not None and (
            not isinstance(color, (list, tuple))
            or len(color) != 3
            or any(type(v) is not int or not 0 <= v <= 255 for v in color)
        ):
            raise ValueError("Invalid saved Good Vibe color")
        duration = state.get("light_duration")
        if duration is not None and (type(duration) is not int or not 0 <= duration <= 65535):
            raise ValueError("Invalid saved Good Vibe duration")
        for key in ("saved_single", "light_color", "light_duration"):
            if key in state:
                self.choices.events[key] = deepcopy(state[key])

    def _side(self) -> int:
        side = {"left": 0, "right": 1, "both": 2}.get(self.command_side or "", self.choices.side)
        if self.product is None or side not in self.product.sides:
            raise ValueError("This product does not offer the requested side")
        return side

    def _publish(self) -> None:
        events = self.choices.events
        timer = events.get("massage_timer")
        count = events.get("deviceAntiSnoreConfigCountEvent")
        time = events.get("deviceAntiSnoreConfigTimeEvent")
        self.forward_controller_state_updates(
            STATUS(self._last_event),
            EVENTS(deepcopy(events)),
            REJECTION(self._rejection or self._normal.rejection),
            SIDE(str(self.choices.side)),
            MONITORING(self.choices.monitoring),
            MEMORY(self.choices.memory),
            LIGHT_DURATION(str(events["light_duration"]) if "light_duration" in events else None),
            # The entities only show numbers and option strings.
            SNORE_COUNT(count if isinstance(count, int) else None),
            SNORE_TIME(time if isinstance(time, int) else None),
            MASSAGE_TIMER(timer if isinstance(timer, str) else None),
            *(
                _live_key(side, name)(getattr(live, name))
                for side, live in self.choices.realtime.items()
                for name in ("heart", "respiration", "occupancy", "movement", "snore")
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": self.product_key,
            "hardware_verified": False,
            "events": deepcopy(self.choices.events),
            "rejection": self._rejection,
            "monitoring": self.choices.monitoring,
        }

    def _event(self, name: str, value: object) -> None:
        self._last_event = name
        self.choices.events[name] = deepcopy(value)
        if name in (
            "deviceRepeatAlarmListStatusEvent",
            "deviceRepeatAlarmListEscalationStatusEvent",
        ) and isinstance(value, dict):
            fields = value.get("alarm_fields")
            if isinstance(fields, list) and len(fields) == 6:
                records = self.choices.events.setdefault("repeat_alarms", {})
                if isinstance(records, dict):
                    records[str(fields[0])] = deepcopy(fields)
        if (
            name == "deviceSleepAdvNameEvent"
            and isinstance(value, list)
            and all(type(v) is int and 0 <= v <= 255 for v in value)
        ):
            self.choices.events["sleep_advertisement_name"] = "".join(map(chr, value))
        if name == "deviceAddAlarmSuccessEvent" and self._pending_single is not None:
            self.choices.events["saved_single"] = self._pending_single
            self._pending_single = None
        elif name == "deviceCancelAlarmSuccessEvent":
            self.choices.events.pop("saved_single", None)
        elif (
            name == "deviceRefreshRepeatAlarmListStatusEvent"
            and self._link is not None
            and self.product is not None
            and self.product.repeat_alarm
        ):
            self._follow_up(self._link, "alarms")
        self._publish()

    def _current_link(self) -> Link:
        link = self._link
        if (
            link is None
            or self.client is not link.client
            or not link.client.is_connected
            or self._coordinator.address != self._address
        ):
            raise ConnectionError("Good Vibe Sleep session changed")
        return link

    async def _send(
        self,
        data: bytes,
        *,
        cleanup: bool = False,
        link: Link | None = None,
        release_gesture: Gesture | None = None,
        on_submit: Callable[[], None] | None = None,
    ) -> bool:
        link = link or self._current_link()
        if not cleanup and self._coordinator.cancel_command.is_set():
            return False
        async with self._ble_lock:
            if release_gesture is not None and (
                self._gesture is not release_gesture or not release_gesture.release_is_current
            ):
                return False
            if self._current_link() is not link:
                raise ConnectionError("Good Vibe Sleep link was replaced")
            if not cleanup and self._coordinator.cancel_command.is_set():
                return False
            response = self.kind == 3 or (
                self.kind == 1 and "write-without-response" not in link.tx.properties
            )
            self._coordinator.record_command_trace(
                payload={"hex": data.hex()},
                characteristic_uuid=link.tx.uuid,
                characteristic_handle=link.tx.handle,
                response=response,
                repeat_count=1,
                repeat_delay_ms=0,
                command_origin="goodvibe",
                controller_class=type(self).__name__,
            )
            if on_submit is not None:
                on_submit()
            await link.client.write_gatt_char(link.tx, data, response=response)
        return True

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        cancel = cancel_event or self._coordinator.cancel_command
        for i in range(repeat_count):
            if cancel.is_set() or not await self._send(command):
                break
            if i + 1 < repeat_count:
                try:
                    await asyncio.wait_for(cancel.wait(), repeat_delay_ms / 1000)
                    break
                except TimeoutError:
                    pass

    def _notification(self, link: Link, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        if self.kind == 1:
            self._normal.feed(bytes(data))
            if self._expiry is not None:
                self._expiry.cancel()
            self._expiry = (
                asyncio.get_running_loop().call_later(EXPIRY_S, self._normal.clear)
                if self._normal.buffer
                else None
            )
        else:
            assert self._sleep is not None
            try:
                result = self._sleep.feed(bytes(data))
                if result is not None:
                    route, obj = result
                    val = obj.get("val")
                    if route == "q_realtime" and isinstance(val, dict):
                        # Parse both sides atomically before replacing visible values.
                        live = deepcopy(self.choices.realtime)
                        for side in ("L", "R"):
                            if val.get(side) is not None:
                                live[side].accept(self.kind, val[side])
                        self.choices.realtime = live
                    if route == "q_report" and isinstance(val, dict):
                        size = val.get("fsize")
                        if (
                            isinstance(size, (int, float))
                            and not isinstance(size, bool)
                            and 0 < size <= 2**20
                        ):
                            self._sleep.report_size = int(size)
                            self._report_ready.set()
                        elif self._report_context is not None:
                            self._report_error = (
                                "No sleep report is available for this date and part"
                            )
                            self._report_ready.set()
                    if route == "report":
                        if self._report_context is not None:
                            cache = self.choices.events.setdefault("report_cache", {})
                            if isinstance(cache, dict):
                                cache[":".join(map(str, self._report_context))] = deepcopy(obj)
                        self._report_done.set()
                    self._event(route, obj)
                    if self.kind == 3 and route in ("s_time", "q_time"):
                        self._follow_up(link, "time" if route == "s_time" else "part", route)
                self._rejection = None
            except (ValueError, TypeError, IndexError, zlib.error) as err:
                self._rejection = str(err)
                self._sleep.buffer.clear()
                self._sleep.target = 0
                if self._report_context is not None:
                    self._report_error = str(err)
                    self._report_ready.set()
                    self._report_done.set()
        self._publish()

    def _follow_up(self, link: Link, operation: str, expected: str | None = None) -> None:
        async def follow() -> None:
            async def execute(controller: BedController) -> None:
                target = selected(controller)
                if (
                    target is self
                    and self._link is link
                    and (
                        expected is None or self._sleep is not None and self._sleep.last == expected
                    )
                ):
                    if operation == "alarms":
                        self.choices.events["repeat_alarms"] = {}
                        await self._send(p.QUERIES["alarms"], link=link)
                    else:
                        await self.sleep_request(operation)

            try:
                await self._coordinator.async_execute_controller_command(
                    execute, cancel_running=False
                )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                self._rejection = str(err)
                self._publish()

        task = self._coordinator.hass.async_create_background_task(follow(), "goodvibe_follow_up")
        self._followups.add(task)
        task.add_done_callback(self._followups.discard)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Good Vibe Sleep is disconnected")
        if self._link is not None:
            await self.stop_notify()
        else:
            self.on_disconnect()
        link = select_link(client, self.kind)
        self._link = link
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            if self.kind == 1:
                for step, (action, code) in enumerate(STARTUP):
                    if step:
                        await asyncio.sleep(MENU_PROBE_S)
                    await self._send(
                        codec.function(code, action=action, single=link.legacy), link=link
                    )
                if self.product is not None and self.product.alarms:
                    for frame in p.sync_time(dt_util.now(), dt_util.now()):
                        await self._send(frame, link=link)
                if self.product is not None and self.product.sleep != "deviceSleepMonitoringNone":
                    await self._send(p.QUERIES["sleep_name"], link=link)
            else:
                await asyncio.sleep(0.00015)
                if self.kind == 3:
                    from .services import Request

                    await self.sleep_request("part", Request("part", part=12))
                await self.sleep_request("sync")
                if self.choices.monitoring:
                    self._start_polling()
        except BaseException:
            self.on_disconnect()
            raise
        self._publish()

    def on_disconnect(self) -> None:
        self._gesture = None
        for task in self._followups:
            task.cancel()
        self._followups.clear()
        self._link = None
        self._normal.clear()
        if self._sleep is not None:
            self._sleep.clear()
            self._sleep.report_size = 0
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None
        self._pending_single = None
        self._report_error = "Sleep device disconnected"
        self._report_ready.set()
        self._report_done.set()
        self._report_context = None

    def on_connection_release(self, reason: str) -> None:
        if reason not in ("idle_timeout", "command_complete", "disconnect_after_command"):
            self.choices.monitoring = False
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    def _start_polling(self) -> None:
        if self._poll is not None:
            self._poll.cancel()
        owner = self._link

        async def poll() -> None:
            while self.choices.monitoring and self._link is owner:
                await asyncio.sleep(POLL_S)

                async def query(controller: BedController) -> None:
                    target = selected(controller)
                    if target is self and self.choices.monitoring and self._link is owner:
                        await self.sleep_request("realtime")

                try:
                    await self._coordinator.async_execute_controller_command(
                        query, cancel_running=False
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    # A failed poll does not abandon the user's monitoring intent.
                    # Disconnection invalidates this owner; a fresh controller restarts it.
                    self._rejection = str(err)
                    self._publish()

        self._poll = self._coordinator.entry.async_create_background_task(
            self._coordinator.hass, poll(), name="goodvibe_realtime"
        )

    @property
    def control_actions(self) -> tuple[str, ...]:
        return (
            tuple(
                child
                for detail in self.product.actions
                for child in ACTION_EXPANSIONS.get(detail, (detail,))
            )
            if self.product is not None
            else ()
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.product is None:

            async def start(controller: BedController) -> None:
                target = selected(controller)
                target.choices.monitoring = True
                target._start_polling()
                await target.sleep_request("realtime")
                target._publish()

            async def stop(controller: BedController) -> None:
                await selected(controller).stop_all()

            return (
                ControllerButtonSpec(
                    "goodvibe_monitor",
                    "Start live sleep data",
                    start,
                    translation_key="goodvibe_action",
                    translation_placeholders={"action": "Start live sleep data"},
                ),
                ControllerButtonSpec(
                    "goodvibe_stop_monitor",
                    "Stop live sleep data",
                    stop,
                    translation_key="goodvibe_action",
                    translation_placeholders={"action": "Stop live sleep data"},
                ),
            )
        buttons = []
        if self.product.light:

            async def light_off(controller: BedController) -> None:
                from .services import Request

                await selected(controller).async_execute_goodvibe_request(Request("light_off"))

            buttons.append(
                ControllerButtonSpec(
                    "goodvibe_light_off",
                    "Close bed light",
                    light_off,
                    translation_key="goodvibe_action",
                    translation_placeholders={"action": "Close bed light"},
                )
            )
        for detail in self.control_actions:
            action = ACTIONS[detail]
            if action.local:
                continue
            key = "goodvibe_" + detail
            buttons.append(
                ControllerButtonSpec(
                    key,
                    label(action),
                    partial(_press, detail=detail),
                    translation_key="goodvibe_action",
                    translation_placeholders={"action": label(action)},
                    hold=ControllerHoldSpec(key, 0, 0, "goodvibe_release"),
                )
            )
            if action.gesture in ("longPress", "shortAndLongPress"):
                buttons.append(
                    ControllerButtonSpec(
                        key + "_long",
                        label(action) + " (long press)",
                        partial(_press, detail=detail, duration=3100),
                        translation_key="goodvibe_action",
                        translation_placeholders={"action": label(action) + " (long press)"},
                    )
                )
        buttons.append(
            ControllerButtonSpec(
                "goodvibe_release",
                "Release held control",
                _release,
                translation_key="goodvibe_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return tuple(buttons)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple("goodvibe_" + d for d in self.control_actions if not ACTIONS[d].local)
            if self.product
            else ()
        )

    def _effective_gesture(self, action: Action) -> tuple[str, bool]:
        """The gesture a press runs, and whether local memory mode applies (row116).

        Memory mode replaces an eligible sustained press with one long operand.
        """
        assert self.product is not None
        memory = self.choices.memory and p.memory_eligible(self.product.label, action.label)
        if memory and action.gesture == "sustainPress":
            return "shortPress", memory
        return action.gesture, memory

    @property
    def execution(self) -> ExecutionCapabilities:
        """Renewable holds on the held controls that run a sustained press (#483).

        Row116: a sustained press first sends after 100 ms, repeats every 100 ms
        with no fixed count and, once a tick fired, releases with the generic
        STOP. Short, long and short-and-long gestures, and sustained controls
        local memory mode turns into one long operand, keep their gestures.
        """
        controls = frozenset(
            control
            for control in self.held_control_options
            if self._effective_gesture(ACTIONS[control.removeprefix("goodvibe_")])[0]
            == "sustainPress"
        )
        if not controls:
            return NO_EXECUTION_CAPABILITIES
        return ExecutionCapabilities(hold="stream", hold_controls=controls)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is unavailable for this product")
        await self.press(control.removeprefix("goodvibe_"), duration_ms)

    async def _delay(self, milliseconds: int) -> bool:
        try:
            await asyncio.wait_for(self._coordinator.cancel_command.wait(), milliseconds / 1000)
            return False
        except TimeoutError:
            return True

    def on_gesture_release(self) -> None:
        gesture = self._gesture
        side = {"left": 0, "right": 1, "both": 2}.get(self.command_side or "")
        if (
            gesture is not None
            and gesture.context is not None
            and gesture.context.active
            and not gesture.cancel_event.is_set()
            and gesture.owner is not None
            and not gesture.owner.cancelling()
            and (side is None or side == 2 or side == gesture.side)
        ):
            gesture.release_generation = gesture.context.cancel_generation + 1

    async def press(self, detail: str, duration: int) -> None:
        if self.product is None or detail not in self.control_actions or not 0 <= duration <= 60000:
            raise ValueError("Action is unavailable for this product")
        action = ACTIONS[detail]
        if action.local:
            raise ValueError("Use the configuration action for this local menu")
        gesture, memory = self._effective_gesture(action)
        context = current_command_context()
        if gesture != "sustainPress" and context is not None and context.lease is not None:
            # Admission checks the scope too; memory mode may change after it.
            raise ValueError("This control does not support renewable holds")
        side, link = self._side(), self._current_link()
        cancel = self._coordinator.cancel_command
        long = action.force_long or memory
        # The artifact replaces flagged items with the None descriptor while its local release mode is off.
        substituted = (
            self.product.label in ("BRRM", "YFRM", "YGRM")
            and not self.choices.release
            and action.force_long
        )
        frame = (
            codec.function(0, side, single=link.legacy)
            if substituted
            else p.action_frame(action, side, link.legacy, long)
        )
        attempted = False
        long_callback = False
        gesture_state = self._gesture = Gesture(
            side, cancel, asyncio.current_task(), current_command_context()
        )

        def mark_submitted() -> None:
            nonlocal attempted
            attempted = True

        async def send(*, released: bool = False) -> None:
            await self._send(
                frame,
                link=link,
                cleanup=released,
                release_gesture=gesture_state if released else None,
                on_submit=mark_submitted,
            )

        def released_short() -> bool:
            return (
                gesture == "shortAndLongPress"
                and not long_callback
                and self._gesture is gesture_state
                and self._link is link
                and gesture_state.release_is_current
            )

        try:
            try:
                if gesture == "sustainPress":
                    remaining = duration
                    while remaining >= TICK_MS and await self._delay(TICK_MS):
                        await send()
                        remaining -= TICK_MS
                elif gesture in ("longPress", "shortAndLongPress"):
                    if duration >= LONG_PRESS_MS:
                        if await self._delay(LONG_PRESS_MS):
                            long_callback = True
                            frame = (
                                codec.function(0, side, single=link.legacy)
                                if substituted
                                else p.action_frame(action, side, link.legacy, True)
                            )
                            await send()
                    elif await self._delay(duration) and gesture == "shortAndLongPress":
                        await send()
                else:
                    if not cancel.is_set():
                        await send()
            except asyncio.CancelledError:
                if not released_short():
                    raise
            if not attempted and released_short():
                # The coordinator may deliver this release's cancellation while
                # the short callback is waiting for the wire. Drain the same
                # guarded write; never retry a frame already handed to BLE.
                short_task = asyncio.create_task(send(released=True))
                try:
                    while True:
                        try:
                            await asyncio.shield(short_task)
                            break
                        except asyncio.CancelledError:
                            if short_task.cancelled() or not released_short():
                                raise
                finally:
                    if not short_task.done():
                        short_task.cancel()
                        await asyncio.gather(short_task, return_exceptions=True)
            if attempted and not long_callback and memory and not action.force_long:
                self.choices.memory = False
            if attempted and not long_callback and action.memory_toggle:
                if action.label == "deviceFunctionItemMemory":
                    self.choices.memory = not self.choices.memory
                elif action.label == "deviceFunctionItemHeadUpAndFootDown":
                    self.choices.release, self.choices.hold = True, False
                elif action.label == "deviceFunctionItemFootUpAndHeadDown":
                    self.choices.release, self.choices.hold = False, True
            self._publish()
            if attempted and gesture == "shortPress":
                await self._delay(duration)
        finally:
            if self._gesture is gesture_state:
                self._gesture = None
            if attempted and gesture in ("shortPress", "sustainPress"):
                await self._send(_stop(side, link), cleanup=True, link=link)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if self.product is None:
            return ()
        specs = []
        if self.product.massage_timer:

            async def massage_timer(controller: BedController, value: str) -> None:
                from .services import Request

                await selected(controller).async_execute_goodvibe_request(
                    Request("massage_timer", value=int(value))
                )

            specs.append(
                ControllerSelectSpec(
                    "goodvibe_massage_timer",
                    "goodvibe_massage_timer",
                    MASSAGE_TIMER,
                    ("0", "10", "20", "30"),
                    massage_timer,
                )
            )
        if len(self.product.sides) > 1:

            async def set_side(_controller: BedController, value: str) -> None:
                self._select_side(value)

            specs.append(
                ControllerSelectSpec(
                    "goodvibe_side",
                    "goodvibe_side",
                    SIDE,
                    tuple(map(str, self.product.sides)),
                    set_side,
                    local_select_fn=self._select_side,
                    card=CardPlacement(CardSection.MOTORS),
                )
            )
        if self.product.light:

            async def duration(controller: BedController, value: str) -> None:
                from .services import Request

                await selected(controller).async_execute_goodvibe_request(
                    Request("light_duration", seconds=int(value))
                )

            eight = self.product.light_display == "deviceBedLightDisplayCircleEightColorValue"
            options = tuple(map(str, p.light_durations(self.product.label.split(" / ")[0], eight)))
            specs.append(
                ControllerSelectSpec(
                    "goodvibe_light_duration",
                    "goodvibe_light_duration",
                    LIGHT_DURATION,
                    options,
                    duration,
                )
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if (
            self.product is None
            or self.product.sleep == "deviceSleepMonitoringNone"
            or self.product.label.split(" / ")[0] in p.SNORE_MENU_EXCLUDED_MODELS
        ):
            return ()

        async def count(controller: BedController, value: float) -> None:
            from .services import Request

            if value != int(value):
                raise ValueError("Snore count must be an integer")
            await selected(controller).async_execute_goodvibe_request(
                Request("snore_count", value=int(value))
            )

        async def time(controller: BedController, value: float) -> None:
            from .services import Request

            if value != int(value):
                raise ValueError("Snore time must be an integer")
            await selected(controller).async_execute_goodvibe_request(Request("snore_time", value=int(value)))

        return (
            ControllerNumberSpec(
                "goodvibe_snore_count",
                "goodvibe_snore_count",
                SNORE_COUNT,
                1,
                30,
                1,
                count,
            ),
            ControllerNumberSpec(
                "goodvibe_snore_time", "goodvibe_snore_time", SNORE_TIME, 5, 30, 5, time
            ),
        )

    def _select_side(self, value: str) -> None:
        side = int(value)
        if self.product is None or side not in self.product.sides:
            raise ValueError("Unsupported side")
        self.choices.side = side
        self._publish()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = [
            ControllerStateSensorSpec(
                "goodvibe_status",
                "goodvibe_status",
                STATUS,
                "mdi:bed",
                attribute_keys=(
                    EVENTS,
                    REJECTION,
                    MONITORING,
                    MEMORY,
                ),
                card=CARD_UTILITY,
            )
        ]
        if self.product is None:
            for side in ("L", "R"):
                for name in ("heart", "respiration", "occupancy", "movement", "snore"):
                    key = f"goodvibe_{side}_{name}"
                    specs.append(
                        ControllerStateSensorSpec(
                            key, key.lower(), _live_key(side, name), "mdi:bed", card=CARD_UTILITY
                        )
                    )
        return tuple(specs)

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        for task in self._followups:
            task.cancel()
        self._followups.clear()
        if self.kind != 1:
            self.choices.monitoring = False
            if self._poll is not None:
                self._poll.cancel()
                self._poll = None
            assert self._sleep is not None
            self._sleep.clear()
            self._publish()
            return
        link = self._current_link()
        await self._send(_stop(self._side(), link), cleanup=True, link=link)

    async def sleep_request(self, operation: str, request: Request | None = None) -> None:
        if self._sleep is None:
            raise ValueError("Choose a separate sleep-sensor profile")
        if operation in ("report", "report_allow"):
            # Report pages replace the live page in the app. Their single shared
            # receive state must not be overwritten by the realtime poller.
            self.choices.monitoring = False
            if self._poll is not None:
                self._poll.cancel()
                self._poll = None
        now = dt_util.now()
        command, value = "q_" + operation, None
        if operation == "sync":
            offset = now.utcoffset()
            command = "s_time"
            value = (
                {"ts": int(now.timestamp()), "tz": self._coordinator.hass.config.time_zone}
                if self.kind == 2
                else {
                    "ts": int(now.timestamp()),
                    "utc": int(offset.total_seconds() / 3600) if offset else 0,
                }
            )
        elif operation == "realtime":
            command, value = "q_realtime", {"type": 0, "time": 1}
        elif operation == "part":
            command = (
                "s_part"
                if self.kind == 2 or request is not None and request.part is not None
                else "q_part"
            )
            value = request.part if request else None
        elif operation == "anti_snore":
            command = (
                "s_antiSnore"
                if request is not None and request.enabled is not None
                else "q_antiSnore"
            )
            value = (
                {"L": [int(request.enabled), 8, 4], "R": [int(request.enabled), 8, 4]}
                if request and request.enabled is not None
                else None
            )
        elif operation == "sensitivity":
            command = "q_sens"
        elif operation == "time":
            command = "q_time"
        elif operation == "report":
            if request is None or request.date is None or request.part is None:
                raise ValueError("Report requires date and part")
            command = "q_report"
            value = {
                "part": request.part,
                "type": request.report_type,
                "y": request.date.year,
                "m": request.date.month,
                "d": request.date.day,
            }
            self._sleep.report_type = request.report_type
            self._sleep.report_size = 0
            self._report_context = (
                request.part,
                request.report_type,
                request.date.year,
                request.date.month,
                request.date.day,
            )
        elif operation == "report_allow":
            command = "q_report"
            value = {"allow": 1}
            if self.kind == 2:
                if request is None or request.date is None or request.part is None:
                    raise ValueError("Type 1 report continuation requires date and part")
                value = {
                    "part": request.part,
                    "type": request.report_type,
                    "y": request.date.year,
                    "m": request.date.month,
                    "d": request.date.day,
                    "allow": 1,
                }
        else:
            raise ValueError("Unsupported sleep action")
        self.choices.sequence = self.choices.sequence % 254 + 1
        packet = sleep_packet(self.choices.sequence, command, value)
        receive_command = (
            "q_report_allow"
            if operation == "report_allow"
            else ("q_part" if self.kind == 2 and operation == "part" and value is None else command)
        )
        self._sleep.begin(receive_command)
        link = self._current_link()
        cap = max(1, min(link.client.mtu_size - 3, 512))
        for offset in range(0, len(packet), cap):
            if not await self._send(packet[offset : offset + cap], link=link):
                self._sleep.clear()
                break

    def validate_goodvibe_request(self, request: Request) -> None:
        request.validate(self)

    async def async_execute_goodvibe_request(self, request: Request) -> None:
        self.validate_goodvibe_request(request)
        if self.kind != 1:
            assert self._sleep is not None
            if request.operation != "report":
                await self.sleep_request(request.operation, request)
                return
            self._report_ready.clear()
            self._report_done.clear()
            self._report_error = None
            try:
                await self.sleep_request("report", request)
                await asyncio.wait_for(self._report_ready.wait(), 30)
                if self._report_error is not None:
                    raise ConnectionError(self._report_error)
                await self.sleep_request("report_allow", request)
                await asyncio.wait_for(self._report_done.wait(), 30)
                if self._report_error is not None:
                    raise ValueError(self._report_error)
            finally:
                self._sleep.clear()
                self._sleep.report_size = 0
                self._report_context = None
            return
        frames = request.frames(self)
        if request.operation == "alarms":
            self.choices.events["repeat_alarms"] = {}
        try:
            for frame in frames:
                if not await self._send(frame):
                    raise asyncio.CancelledError
        except BaseException:
            self._pending_single = None
            raise
        if request.operation in ("light_color", "light_duration"):
            self.choices.events[request.operation] = (
                request.rgb if request.operation == "light_color" else request.seconds
            )
        elif request.operation == "massage_timer":
            self.choices.events["massage_timer"] = str(request.value)
        self._publish()

    async def move_head_up(self) -> None:
        raise NotImplementedError("Use the exact app-labelled action")

    move_head_down = move_head_up
    move_back_up = move_head_up
    move_back_down = move_head_up
    move_legs_up = move_head_up
    move_legs_down = move_head_up
    move_feet_up = move_head_up
    move_feet_down = move_head_up
    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    preset_flat = move_head_up

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the exact app-labelled action")

    program_memory = preset_memory


async def build_controller(ctx: BuildContext) -> GoodVibeController:
    """Build the controller for the selected GoodVibe profile."""
    return GoodVibeController(ctx.coordinator, profile=ctx.variant or "")
