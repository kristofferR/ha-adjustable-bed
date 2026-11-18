"""Good Vibe Sleep exact product controls and independent sleep-sensor sessions."""

from __future__ import annotations

import asyncio
import logging
import zlib
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...app_session import app_session
from ...card import (
    CARD_CONTROLLED_SIDE,
    CARD_HIDDEN,
    CARD_UTILITY,
)
from ...codec import richmat as codec
from ...command_scheduler import CommandContext, current_command_context
from ...controller_state import StateKey
from ...execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities
from ...profiles.richmat import GOODVIBE, RichmatProfile
from ...profiles.richmat_catalog import Catalog
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..builder import BuildContext
from ..catalog_buttons import (
    EXTRA_KEY,
    Kind,
    catalog_button,
    classify,
    is_placeholder,
    unique_buttons,
)
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
)
from ..richmat.labels import function_label
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
# HA readiness budget after the startup queries, not a protocol pacing interval.
MENU_REPLY_TIMEOUT_S = 3
TICK_MS = 100
QUEUE_MS = 100
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
    assert GOODVIBE.stop is not None
    return codec.function(GOODVIBE.stop, side, single=link.legacy)


def label(action: Action) -> str:
    suffix = " (long press)" if action.force_long else ""
    return function_label(action.label) + suffix


def select_link(
    client: BleakClient, kind: int, profile: RichmatProfile = GOODVIBE, *,
    strict_sleep: bool = False, bind_framing: bool = False, coherent_service: bool = False,
) -> Link:
    tx = rx = None
    legacy = False
    candidate_legacy = False
    for service in client.services:
        uuid = service.uuid.lower()
        if kind == 1:
            pair = {codec.TRANSPORTS[k].service_uuid.lower(): (codec.TRANSPORTS[k].write_uuid.lower(), codec.TRANSPORTS[k].single) for k in profile.transports}.get(uuid)
            if pair is None:
                continue
            target, candidate_legacy = pair
            if coherent_service:
                tx = rx = None
            if not bind_framing:
                legacy = candidate_legacy
        else:
            if uuid not in SLEEP_SERVICES:
                continue
            target = "00000002-3c17-d293-8e48-14fe2e4da212"
            if strict_sleep:
                tx = rx = None
        for char in service.characteristics:
            if strict_sleep and kind == 2:
                if "write-without-response" in char.properties:
                    tx = char
                elif "notify" in char.properties:
                    rx = char
                continue
            if tx is None:
                if kind == 2:
                    matches = "write-without-response" in char.properties
                else:
                    matches = char.uuid.lower() == target and "write" in char.properties
                if matches:
                    tx = char
                    if bind_framing and kind == 1:
                        legacy = candidate_legacy
            if (
                rx is None
                and "notify" in char.properties
                and (kind != 3 or char.uuid.lower() == "00000003-3c17-d293-8e48-14fe2e4da212")
            ):
                rx = char
        if (coherent_service or strict_sleep and kind != 1) and tx is not None and rx is not None:
            break
    if tx is None or rx is None:
        raise ValueError("Good Vibe Sleep requires its selected write and notify characteristics")
    return Link(client, tx, rx, legacy)


GOODVIBE_CATALOG = Catalog("goodvibe", "Good Vibe Sleep", GOODVIBE, ACTIONS, PRODUCTS, ACTION_EXPANSIONS)


class GoodVibeController(BedController):
    """A normal product or a separate RM-/HJ- sleep device, chosen explicitly."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, profile: str,
        catalog: Catalog = GOODVIBE_CATALOG,
    ) -> None:
        super().__init__(coordinator)
        self.catalog = catalog
        self.actions = catalog.actions
        self.record = catalog.record
        self.queries = p.queries(self.record)
        if profile not in catalog.products and (
            catalog.key not in ("goodvibe", "mlily") or profile not in ("sleep_rm", "sleep_hj")
        ):
            raise ValueError("Choose the exact product in Good Vibe Sleep")
        self.profile = self.catalog.wire
        self.product_key = profile
        self.kind = 2 if profile == "sleep_rm" else 3 if profile == "sleep_hj" else 1
        self.product = self.catalog.products.get(profile)

        def initial() -> Choices:
            choices = Choices(
                release=(catalog.release_initially if self.product is None
                         else (self.product.label not in ("BRRM", "APRM", "YFRM", "YGRM"))
                         == catalog.release_initially)
            )
            if runtime := self.catalog.runtimes.get(profile):
                choices.release = runtime.initial_release
            if self.product is not None and self.product.light:
                model = self.product.label.split(" / ")[0]
                choices.events["light_duration"] = (
                    300 if catalog.reply_gated_menus else 900 if model == "FMRM" else 14400 if model == "RNRN" else 300
                )
            return choices

        self.choices = app_session(
            coordinator.hass, coordinator.address, (self.catalog.key, profile), initial
        )
        self._address = coordinator.address
        self._link: Link | None = None
        self._gesture: Gesture | None = None
        self._expiry: asyncio.TimerHandle | None = None
        self._poll: asyncio.Task[None] | None = None
        self._followups: set[asyncio.Task[None]] = set()
        self._normal = Notifications(
            self._event, mlily=catalog.key == "mlily", timer_pair=catalog.notification_menus,
            direct_bed=catalog.bed is not None,
        )
        self._sleep = Receiver(self.kind, ordinary_utf8=catalog.reply_gated_menus) if self.kind != 1 else None
        self._pending_single: dict[str, object] | None = None
        self._report_ready = asyncio.Event()
        self._report_done = asyncio.Event()
        self._report_error: str | None = None
        self._report_context: tuple[int, int, int, int, int] | None = None
        self._menus: set[str] = set()
        self._menus_changed = asyncio.Event()
        self._last_write = 0.0
        self._last_event: str | None = None
        self._rejection: str | None = None
        self._next_write_at = 0.0

    @property
    def snore_available(self) -> bool:
        if self.product is None or self.catalog.reply_gated_menus or self.catalog.bed is not None:
            return False
        if self.catalog.notification_menus:
            return self.catalog.runtimes[self.product_key].snore
        return (
            self.product.sleep != "deviceSleepMonitoringNone"
            and self.product.label.split(" / ")[0] not in p.SNORE_MENU_EXCLUDED_MODELS
        )

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link else "00000002-3c17-d293-8e48-14fe2e4da212"

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_persistent_connection(self) -> bool:
        return (
            super().requires_persistent_connection
            or self.choices.monitoring
            or (self._sleep is not None and self._sleep.last in ("q_report", "q_report_allow"))
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
        return self.catalog.key + ":" + self.product_key

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
        if self.catalog.bed is not None and duration is not None and duration not in (
            minute * 60 for minute in self.catalog.bed.light_minutes
        ):
            raise ValueError("Choose a Power Bob Base light duration from 0 to 15 minutes")
        for key in ("saved_single", "light_color", "light_duration"):
            if key in state:
                self.choices.events[key] = deepcopy(state[key])

    def _side(self) -> int:
        side = {"left": 0, "right": 1, "both": 2}.get(self.command_side or "", self.choices.side)
        if self.product is None or side not in self.product.sides:
            raise ValueError("This product does not offer the requested side")
        if self.catalog.bed is not None and self._link is not None and self._link.legacy and side != 0:
            raise ValueError("The Nordic command does not address a bed side")
        return side

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return self.catalog.bed is not None or super().has_dynamic_controller_entities

    @property
    def has_dynamic_buttons(self) -> bool:
        return self.catalog.bed is not None or super().has_dynamic_buttons

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        if self.catalog.bed is not None and self.product is not None and self.product.light:
            # A missing session reply withdraws permission, not the known
            # product's registry identity or the user's customizations.
            return frozenset({
                ("button", "goodvibe_light_off"),
                ("select", "controller_select_goodvibe_light_duration"),
            })
        return super().retained_entity_keys

    def menu_available(self, menu: str) -> bool:
        """A product getter permits a menu; the app may also require its reply."""
        if self.product is None:
            return False
        allowed = {
            "light": self.product.light,
            "alarm": bool(self.product.alarms),
            "sleep": self.product.sleep == "deviceSleepMonitoringBle" if self.catalog.reply_gated_menus else self.product.sleep != "deviceSleepMonitoringNone",
        }[menu]
        if self.catalog.bed is not None:
            return allowed and (menu != "light" or "deviceCharacteristicsSubscriptionLightEvent" in self.choices.events)
        if not self.catalog.reply_gated_menus:
            return allowed
        if menu == "alarm" and allowed and any(
            self.actions[key].label == "deviceFunctionItemClock"
            and not self.actions[key].hidden
            and self.actions[key].interactive
            for key in self.product.actions
        ):
            return True
        event = {
            "light": "deviceCharacteristicsSubscriptionLightEvent",
            "alarm": "deviceCharacteristicsSubscriptionClockEvent",
            "sleep": "deviceSleepAdvNameEvent",
        }[menu]
        return allowed and event in self.choices.events

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
            "app": self.catalog.key,
            "profile": self.product_key,
            "hardware_verified": False,
            "events": deepcopy(self.choices.events),
            "rejection": self._rejection,
            "monitoring": self.choices.monitoring,
        }

    def _event(self, name: str, value: object) -> None:
        if self.catalog.bed is not None:
            # Keep shared BED effects, without promoting companion/audio/accessory state.
            if name.startswith(("deviceMusic", "deviceBlacket", "deviceFan", "deviceAtomization", "deviceHeating", "deviceSleep")) or name in (
                "deviceCharacteristicsSubscriptionMusicEvent",
                "deviceCharacteristicsSubscriptionAromatherapyEvent",
                "deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent",
            ):
                return
        self._last_event = name
        self.choices.events[name] = deepcopy(value)
        if self.catalog.bed is not None and name == "deviceCharacteristicsSubscriptionLightEvent":
            self._menus_changed.set()
        if self.catalog.notification_menus and self.product is not None:
            if name == "deviceCharacteristicsSubscriptionClockEvent" and self.product.alarms:
                self._menus.add("alarm")
            elif name == "deviceCharacteristicsSubscriptionLightEvent" and self.product.light:
                self._menus.add("light")
            elif name == "deviceSleepAdvNameEvent":
                if self.product.sleep != "deviceSleepMonitoringBle" or "sleep" in self._menus:
                    self._publish()
                    return
                if not isinstance(value, list) or any(
                    type(v) is not int or not 0 <= v < 128 for v in value
                ):
                    self._rejection = "Invalid ASCII sleep advertisement name"
                    self._publish()
                    return
                self._menus.add("sleep")
                if self.snore_available:
                    self._menus.add("snore")
            self.choices.events["menus"] = sorted(self._menus)
            self._menus_changed.set()
        if name in (
            "deviceRepeatAlarmListStatusEvent",
            "deviceRepeatAlarmListEscalationStatusEvent",
        ) and isinstance(value, dict):
            fields = value.get("alarm_fields")
            if isinstance(fields, list) and len(fields) == 6:
                if self.catalog.reply_gated_menus:
                    records = self.choices.events.setdefault("repeat_alarm_records", [])
                    if isinstance(records, list):
                        if name == "deviceRepeatAlarmListStatusEvent":
                            if fields not in records:
                                records.append(deepcopy(fields))
                        else:
                            index = next((i for i, old in enumerate(records) if old[0] == fields[0]), None)
                            if index is not None:
                                records[index] = deepcopy(fields)
                else:
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
            or self.catalog.bed is not None and self._coordinator.controller is not self
        ):
            raise ConnectionError("Good Vibe Sleep session changed")
        return link

    async def _pace(self, cleanup: bool) -> bool:
        if self.catalog.notification_menus:
            delay = TICK_MS / 1000 - (asyncio.get_running_loop().time() - self._last_write)
            if delay > 0:
                if cleanup:
                    await asyncio.sleep(delay)
                else:
                    return await self._delay(max(1, int(delay * 1000)))
        return True

    async def _send(
        self,
        data: bytes,
        *,
        cleanup: bool = False,
        link: Link | None = None,
        release_gesture: Gesture | None = None,
        on_submit: Callable[[], None] | None = None,
        deadline: float | None = None,
        dispatch: Callable[[], None] | None = None,
    ) -> bool:
        link = link or self._current_link()
        cancel = asyncio.Event() if cleanup else self._coordinator.cancel_command
        if cancel.is_set():
            return False
        async with self._ble_lock:
            if release_gesture is not None and (
                self._gesture is not release_gesture or not release_gesture.release_is_current
            ):
                return False
            if self._current_link() is not link:
                raise ConnectionError("Good Vibe Sleep link was replaced")
            if cancel.is_set():
                return False
            if self.catalog.reply_gated_menus or self.catalog.bed is not None:
                loop = asyncio.get_running_loop()
                delay = self._next_write_at - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                if self._current_link() is not link:
                    raise ConnectionError("The BLE link changed while a write was queued")
                if cancel.is_set():
                    return False
                tick = self.catalog.bed.tick_ms if self.catalog.bed is not None else QUEUE_MS
                self._next_write_at = loop.time() + tick / 1000
            # Pacing holds the wire lock; cancellation/link ownership are checked again.
            if not await self._pace(cleanup):
                return False
            if self._current_link() is not link:
                raise ConnectionError("Catalog link was replaced during pacing")
            if cancel.is_set():
                return False
            if deadline is not None and monotonic() >= deadline:
                return False
            context = current_command_context()
            if (
                self.catalog.bed is not None
                and not cleanup
                and context is not None
                and context.lease is not None
                and (
                    context.hold_deadline is not None
                    and asyncio.get_running_loop().time() >= context.hold_deadline
                )
            ):
                return False
            if release_gesture is not None and (
                self._gesture is not release_gesture or not release_gesture.release_is_current
            ):
                return False
            if dispatch is not None:
                dispatch()
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
                command_origin=self.catalog.key,
                controller_class=type(self).__name__,
            )
            if on_submit is not None:
                on_submit()
            if self.catalog.bed is None:
                await link.client.write_gatt_char(link.tx, data, response=response)
            else:
                write = asyncio.create_task(link.client.write_gatt_char(link.tx, data, response=response))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    # A submitted GATT write must drain before cleanup releases
                    # the same physical link and wire lock.
                    while not write.done():
                        try:
                            await asyncio.shield(write)
                        except asyncio.CancelledError:
                            if write.cancelled():
                                raise
                    write.result()
                    raise
            self._last_write = asyncio.get_running_loop().time()
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
        if self.catalog.bed is not None and self._coordinator.controller is not self:
            return
        self.forward_raw_notification(link.rx.uuid, bytes(data))
        if self.kind == 1:
            self._normal.feed(bytes(data))
            if self._expiry is not None:
                self._expiry.cancel()
            self._expiry = (
                asyncio.get_running_loop().call_later(
                    self.catalog.bed.receive_expiry_s if self.catalog.bed else EXPIRY_S,
                    self._expire_notifications, link,
                )
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

    def _expire_notifications(self, link: Link) -> None:
        if self._link is link:
            self._normal.clear()

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
                        await self._send(self.queries["alarms"], link=link)
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
        link = select_link(
            client, self.kind, self.profile, strict_sleep=self.catalog.reply_gated_menus,
            bind_framing=self.catalog.notification_menus or self.catalog.bed is not None,
        )
        self._link = link
        try:
            await client.start_notify(link.rx, partial(self._notification, link))
            if self.kind == 1:
                if self.catalog.bed is not None:
                    self._next_write_at = asyncio.get_running_loop().time() + self.catalog.bed.tick_ms / 1000
                    for action, code in self.catalog.startup:
                        await self._send(codec.function(code, action=action, single=link.legacy), link=link)
                    if self.product is not None and self.product.alarms:
                        await self._send(codec.calendar(dt_util.now(), build=self.record), link=link)
                    self._publish()
                    return
                startup = self.catalog.startup
                time_sync = self.product is not None and bool(self.product.alarms)
                sleep_query = (
                    self.product is not None and (
                        self.product.sleep == "deviceSleepMonitoringBle" if self.catalog.reply_gated_menus
                        else self.product.sleep != "deviceSleepMonitoringNone"
                    )
                )
                if self.catalog.notification_menus:
                    runtime = self.catalog.runtimes[self.product_key]
                    names = {
                        "check_clock": ("deviceFunctionItemCheckClock", 1),
                        "check_light": ("deviceFunctionItemCheckLight", 1),
                    }
                    startup = tuple(names[name] for name in runtime.query_order)
                    time_sync, sleep_query = runtime.time_sync, runtime.sleep_query
                    self._menus = {"alarm"} if runtime.initial_alarm else set()
                menu_started = asyncio.get_running_loop().time()
                if self.catalog.notification_menus:
                    if time_sync:
                        for frame in p.sync_time(dt_util.now(), dt_util.now(), build=self.record):
                            await self._send(frame, link=link)
                    if sleep_query:
                        await self._send(self.queries["sleep_name"], link=link)
                for step, (action, code) in enumerate(startup):
                    if self.catalog.notification_menus:
                        due = menu_started + (step + 1) * MENU_PROBE_S
                        await asyncio.sleep(max(0, due - asyncio.get_running_loop().time()))
                    elif step == 1 and self.catalog.reply_gated_menus:
                        if time_sync:
                            for frame in p.sync_time(dt_util.now(), dt_util.now(), build=self.record):
                                await self._send(frame, link=link)
                        await asyncio.sleep(MENU_PROBE_S)
                    elif step:
                        await asyncio.sleep(MENU_PROBE_S)
                    await self._send(
                        codec.function(code, action=action, single=link.legacy), link=link
                    )
                if self.catalog.notification_menus:
                    expected = {
                        menu
                        for menu, required in (
                            ("alarm", bool(self.product and self.product.alarms)),
                            ("light", bool(self.product and self.product.light)),
                            (
                                "sleep",
                                bool(self.product and self.product.sleep == "deviceSleepMonitoringBle"),
                            ),
                        )
                        if required
                    }
                    try:
                        async with asyncio.timeout(MENU_REPLY_TIMEOUT_S):
                            while not expected <= self._menus:
                                self._menus_changed.clear()
                                if self._link is not link:
                                    raise ConnectionError("Catalog link was replaced during startup")
                                await self._menus_changed.wait()
                    except TimeoutError:
                        pass  # Request validation still rejects unadvertised capabilities.
                if not self.catalog.notification_menus:
                    if time_sync and not self.catalog.reply_gated_menus:
                        for frame in p.sync_time(dt_util.now(), dt_util.now(), build=self.record):
                            await self._send(frame, link=link)
                    if sleep_query:
                        await self._send(self.queries["sleep_name"], link=link)
            else:
                await asyncio.sleep(0.00015)
                if self.kind == 3 and not self.catalog.reply_gated_menus:
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
        self._menus.clear()
        self._menus_changed.set()
        if self.catalog.bed is not None:
            durable = {key: value for key, value in self.choices.events.items()
                       if key in ("light_color", "light_duration")}
            self.choices.events.clear()
            self.choices.events.update(durable)
            self._last_event = None
            self._last_write = 0.0
            self._normal.rejection = None
        if self.catalog.notification_menus:
            for key in ("repeat_alarms", "sleep_advertisement_name", "menus"):
                self.choices.events.pop(key, None)
        for task in self._followups:
            task.cancel()
        self._followups.clear()
        self._link = None
        self._next_write_at = 0.0
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
        """The product's controls once each, in app order, without empty slots."""
        if self.product is None:
            return ()
        details = (
            child
            for detail in self.product.actions
            for child in self.catalog.expansions.get(detail, (detail,))
        )
        unique: dict[tuple[object, ...], str] = {}
        for detail in details:
            action = self.actions[detail]
            # Some products list one control twice under different descriptors.
            same = (
                action.label, action.gesture, action.force_long,
                action.short, action.long, action.legacy_short,
            )
            if not is_placeholder(label(action)):
                unique.setdefault(same, detail)
        return tuple(unique.values())

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

            return tuple(
                ControllerButtonSpec(
                    key, name, press, translation_key=EXTRA_KEY,
                    translation_placeholders={"action": name},
                )
                for key, name, press in (
                    ("goodvibe_monitor", "Start live sleep data", start),
                    ("goodvibe_stop_monitor", "Stop live sleep data", stop),
                )
            )
        buttons: list[ControllerButtonSpec | None] = []
        labels = self.catalog.labels
        # The product's light-off request, unless a control already turns the light off.
        if (
            self.product.light
            and (self.catalog.bed is None or self.menu_available("light"))
            and not any(label(self.actions[d]) == "Light off" for d in self.control_actions)
        ):

            async def light_off(controller: BedController) -> None:
                from .services import Request

                await selected(controller).async_execute_goodvibe_request(Request("light_off"))

            buttons.append(
                catalog_button(
                    "goodvibe_light_off", labels.get("light_off", "Bed light off"), light_off,
                    kind=Kind.LIGHT,
                )
            )
        for detail in self.control_actions:
            action = self.actions[detail]
            if action.local or action.hidden or not action.interactive:
                continue
            key = "goodvibe_" + detail
            power_bob = self.catalog.bed is not None
            # A long press sends the action's own long operand. A preset's saves it;
            # another distinct operand is its own control; a zero operand sends nothing.
            distinct_long = action.long not in (0, action.short)
            saves = self._long_press_saves(action)
            # A long-press-only control's short press sends nothing.
            long_only = action.gesture == "longPress"
            if (power_bob or not long_only) and (
                power_bob or not action.force_long or distinct_long
            ):
                buttons.append(
                    catalog_button(
                        key,
                        "Save " + function_label(action.label)
                        if action.force_long and saves and not power_bob
                        else labels.get(detail, label(action)),
                        partial(_press, detail=detail),
                        kind=Kind.SAVE if action.force_long and saves and not power_bob else None,
                        enabled=power_bob or not action.force_long or saves,
                        # Holding a control whose long press saves would save unconfirmed.
                        hold=(ControllerHoldSpec(key, 0, 0, "goodvibe_release")
                              if (not power_bob or action.gesture != "shortPress")
                              and not saves else None),
                    )
                )
            # A forced long press already sends its long operand from the button itself.
            if action.gesture in ("longPress", "shortAndLongPress") and (
                long_only or not action.force_long
            ) and (power_bob or distinct_long or long_only and action.long != 0):
                buttons.append(
                    catalog_button(
                        key + "_long",
                        labels.get(detail + "_long", "Save " + function_label(action.label))
                        if power_bob or saves
                        else function_label(action.label)
                        + ("" if long_only else " (long press)"),
                        partial(_press, detail=detail, duration=3100),
                        kind=Kind.SAVE if power_bob or saves else None,
                        # Another long operand's effect is unnamed: there to enable.
                        enabled=power_bob or saves or long_only,
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
        return unique_buttons(buttons)

    @staticmethod
    def _long_press_saves(action: Action) -> bool:
        """Whether the action's long press sends its own operand for a preset or memory.

        In this app vocabulary a preset's long operand saves it (``0x66`` saves
        Zero gravity); a zero long operand sends nothing.
        """
        control = classify(function_label(action.label))
        return (
            action.long not in (0, action.short)
            and control is not None
            and control.kind in (Kind.PRESET, Kind.MEMORY)
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            "goodvibe_" + d
            for d in self.control_actions
            if not self.actions[d].local and not self.actions[d].hidden
            and self.actions[d].interactive
        )

    def _effective_gesture(self, action: Action) -> tuple[str, bool]:
        """The gesture a press runs, and whether local memory mode applies.

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

        Good Vibe Sleep: a sustained press first sends after 100 ms, repeats every 100 ms
        with no fixed count and, once a tick fired, releases with the generic
        STOP. Short, long and short-and-long gestures, and sustained controls
        local memory mode turns into one long operand, keep their gestures.
        """
        controls = frozenset(
            control
            for control in self.held_control_options
            if self._effective_gesture(self.actions[control.removeprefix("goodvibe_")])[0]
            == "sustainPress"
        )
        if not controls:
            return NO_EXECUTION_CAPABILITIES
        return ExecutionCapabilities(hold="stream", hold_controls=controls)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is unavailable for this product")
        await self.press(control.removeprefix("goodvibe_"), duration_ms)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        super().validate_hold_control(control, duration_ms)
        if self.catalog.bed is not None:
            self._side()

    def controller_button_available(self, key: str) -> bool:
        if self.catalog.bed is None:
            return super().controller_button_available(key)
        if key == "goodvibe_light_off" and not self.menu_available("light"):
            return False
        try:
            self._side()
        except ValueError:
            return False
        return super().controller_button_available(key)

    async def _delay(self, milliseconds: float) -> bool:
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
        action = self.actions[detail]
        if action.local or action.hidden or not action.interactive:
            raise ValueError("Use the configuration action for this local menu")
        gesture, memory = self._effective_gesture(action)
        context = current_command_context()
        if gesture != "sustainPress" and context is not None and context.lease is not None:
            # Admission checks the scope too; memory mode may change after it.
            raise ValueError("This control does not support renewable holds")
        side, link = self._side(), self._current_link()
        bed = self.catalog.bed
        finite_bed_hold = (
            bed is not None
            and gesture == "sustainPress"
            and duration >= bed.tick_ms
            and (context is None or context.lease is None)
        )
        deadline = monotonic() + duration / 1000 if bed is not None else None
        if finite_bed_hold:
            assert bed is not None and deadline is not None
            # HA's finite movement budget excludes the source's first tick.
            # Anchor it here, never after a delayed timer or submitted write.
            deadline += bed.tick_ms / 1000
        cancel = self._coordinator.cancel_command
        long = action.force_long or memory
        # The artifact replaces flagged items with the None descriptor while its local release mode is off.
        substituted = (
            self.product.label in ("BRRM", "YFRM", "YGRM")
            and self.choices.release == self.catalog.substitute_when_release
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

        async def send(*, released: bool = False) -> bool:
            return await self._send(
                frame,
                link=link,
                cleanup=released,
                release_gesture=gesture_state if released else None,
                on_submit=mark_submitted,
                deadline=deadline if gesture == "sustainPress" and not released else None,
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
                    if bed is not None:
                        assert deadline is not None
                        next_tick_ms = bed.tick_ms
                        while (
                            not finite_bed_hold or next_tick_ms < bed.tick_ms + duration
                        ) and monotonic() + bed.tick_ms / 1000 < deadline:
                            if not await self._delay(bed.tick_ms):
                                break
                            if not await send():
                                break
                            next_tick_ms += bed.tick_ms
                        remaining_ms = (deadline - monotonic()) * 1000
                        if finite_bed_hold and remaining_ms > 0 and not cancel.is_set():
                            await self._delay(remaining_ms)
                    else:
                        remaining = duration
                        while remaining >= TICK_MS and await self._delay(TICK_MS):
                            await send()
                            remaining -= TICK_MS
                elif gesture in ("longPress", "shortAndLongPress"):
                    program_ms = bed.program_ms if bed is not None else LONG_PRESS_MS
                    if duration >= program_ms:
                        if await self._delay(program_ms):
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
            if attempted and not long_callback and not substituted and action.memory_toggle:
                if action.label == "deviceFunctionItemMemory":
                    self.choices.memory = not self.choices.memory
                elif action.label == "deviceFunctionItemHeadUpAndFootDown":
                    self.choices.release, self.choices.hold = True, False
                elif action.label == "deviceFunctionItemFootUpAndHeadDown":
                    self.choices.release, self.choices.hold = False, True
            self._publish()
            if attempted and gesture == "shortPress" and bed is None:
                await self._delay(duration)
        finally:
            if self._gesture is gesture_state:
                self._gesture = None
            release_required = (attempted or bed is not None and not cancel.is_set()) and gesture == "sustainPress"
            if release_required or attempted and gesture == "shortPress" and bed is None:
                if bed is None:
                    await self._send(_stop(side, link), cleanup=True, link=link)
                else:
                    release = asyncio.create_task(self._send(_stop(side, link), cleanup=True, link=link))
                    cancelled = False
                    while not release.done():
                        try:
                            await asyncio.shield(release)
                        except asyncio.CancelledError:
                            cancelled = True
                            if release.cancelled():
                                raise
                    release.result()
                    if cancelled:
                        raise asyncio.CancelledError

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
            # Good Vibe has no single-address pairing, so the select is the
            # only way to reach the other side of a split bed.

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
                    card=CARD_CONTROLLED_SIDE,
                )
            )
        if self.product.light and (self.catalog.bed is None or self.menu_available("light")):

            async def duration(controller: BedController, value: str) -> None:
                from .services import Request

                await selected(controller).async_execute_goodvibe_request(
                    Request("light_duration", seconds=int(value))
                )

            eight = self.product.light_display == "deviceBedLightDisplayCircleEightColorValue"
            options = tuple(map(str, (minute * 60 for minute in self.catalog.bed.light_minutes))) if self.catalog.bed else tuple(map(str, p.light_durations(self.product.label.split(" / ")[0], eight)))
            specs.append(
                ControllerSelectSpec(
                    "goodvibe_light_duration",
                    "goodvibe_light_duration",
                    LIGHT_DURATION,
                    options,
                    duration,
                    is_available=(
                        lambda controller: isinstance(controller, GoodVibeController)
                        and controller.catalog.bed is not None and controller.menu_available("light")
                    ) if self.catalog.bed is not None else None,
                )
            )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        if not self.snore_available:
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
            await selected(controller).async_execute_goodvibe_request(
                Request("snore_time", value=int(value))
            )

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
        status_key = "bobpowerbase_status" if self.catalog.bed is not None else "galaxy_status" if self.catalog.key == "galaxy" else "goodvibe_status"
        specs = [
            ControllerStateSensorSpec(
                status_key,
                status_key,
                STATUS,
                "mdi:bed",
                attribute_keys=(
                    EVENTS,
                    REJECTION,
                    MONITORING,
                    MEMORY,
                ),
                entity_registry_enabled_default=False,
            )
        ]
        if self.product is None:
            for side in ("L", "R"):
                for name in ("heart", "respiration", "occupancy", "movement", "snore"):
                    key = f"goodvibe_{side}_{name}"
                    specs.append(
                        ControllerStateSensorSpec(
                            key,
                            key.lower(),
                            _live_key(side, name),
                            "mdi:bed",
                            entity_registry_enabled_default=True,
                            card=CARD_UTILITY,
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
                if (self.kind == 2 and not self.catalog.reply_gated_menus) or request is not None and request.part is not None
                else "q_part"
            )
            value = request.part if request else None
        elif operation == "anti_snore":
            supplied = request is not None and (request.left is not None or request.right is not None)
            command = (
                "s_antiSnore"
                if request is not None and (request.enabled is not None or supplied)
                else "q_antiSnore"
            )
            value = (
                {"L": int(request.enabled), "R": int(request.enabled)}
                if self.catalog.reply_gated_menus and request and request.enabled is not None
                else {"L": [int(request.enabled), 8, 4], "R": [int(request.enabled), 8, 4]}
                if request and request.enabled is not None
                else None
            )
            if self.catalog.reply_gated_menus and supplied and request is not None:
                value = {
                    side: list(operand) if isinstance(operand, tuple) else operand
                    for side, operand in (("L", request.left), ("R", request.right))
                    if operand is not None
                }
        elif operation == "init":
            command, value = "s_init", 0
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
        packet = sleep_packet(
            self.choices.sequence, command, value,
            omit_null=self.catalog.reply_gated_menus and command in ("q_sens", "q_antiSnore"),
        )
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

    async def async_prepare_goodvibe_request(
        self, request: Request, *, admitted: Callable[[], bool]
    ) -> None:
        """Await Bob's reported light permission within the existing HA readiness budget."""
        if self.catalog.bed is None or not request.operation.startswith("light_"):
            return
        request.validate(self, reported=False)
        link = self._current_link()
        generation = self._coordinator._position_connection_generation
        cancel = self._coordinator.cancel_command

        def current() -> None:
            admitted()
            if self._current_link() is not link or self._coordinator._position_connection_generation != generation:
                raise ConnectionError("Power Bob Base session changed while awaiting light capability")
            if cancel.is_set():
                raise asyncio.CancelledError

        self._menus_changed.clear()
        current()
        if self.menu_available("light"):
            return
        ready = asyncio.create_task(self._menus_changed.wait())
        stopped = asyncio.create_task(cancel.wait())
        try:
            done, _pending = await asyncio.wait(
                (ready, stopped), timeout=MENU_REPLY_TIMEOUT_S,
                return_when=asyncio.FIRST_COMPLETED,
            )
            current()
            if not done:
                raise ValueError("The connected bed has no light menu reply before readiness timed out")
            request.validate(self)
        finally:
            ready.cancel()
            stopped.cancel()
            await asyncio.gather(ready, stopped, return_exceptions=True)

    async def async_execute_goodvibe_request(
        self, request: Request, *, dispatch: Callable[[], None] | None = None
    ) -> None:
        self.validate_goodvibe_request(request)
        link = self._current_link()
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
        if self.catalog.bed is not None and request.operation == "light_duration":
            if not await self._delay(self.catalog.bed.light_delay_ms):
                return
        if request.operation == "alarms":
            self.choices.events["repeat_alarms"] = {}
            if self.catalog.reply_gated_menus:
                self.choices.events["repeat_alarm_records"] = []
        try:
            for frame in frames:
                if not await self._send(frame, link=link, dispatch=dispatch):
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
        if self.catalog.reply_gated_menus and request.operation in ("repeat", "delete"):
            await asyncio.sleep(0.2)
            self.choices.events["repeat_alarm_records"] = []
            await self._send(p.QUERIES["alarms"])
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
