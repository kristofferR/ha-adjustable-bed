"""SonicSleep's one physical BED session, with fenced refresh and alarm state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...card import CARD_PRESETS
from ...codec import richmat as codec
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...profiles.sonicsleep import (
    DIRECTIONS,
    EXIT_LIMIT,
    FLAT,
    PRESETS,
    PROFILE,
    QUERY_CLOCK,
    ROUTES,
    TICK_S,
    SonicSleepProfile,
)
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .protocol import (
    LINK_NAME,
    LIST_ALARMS,
    Alarm,
    Receiver,
    decode,
    delete_alarm,
    form_alarm,
    parse_alarm,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

MODEL: Final = StateKey[str]("sonicsleep_model")
OBSERVATIONS: Final = StateKey[dict[str, object]]("sonicsleep_observations")
ALARMS: Final = StateKey[list[dict[str, object]]]("sonicsleep_alarms")
LINK_NAME_STATE: Final = StateKey[str | None]("sonicsleep_link_name")
STATE_WAIT_S: Final = 2.0
"""HA's bounded live read admission budget, not a source protocol timeout."""
WRITE_TIMEOUT_S: Final = 5.0


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    single: bool
    owner: AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    id: int | None = None
    hour: int = 0
    minute: int = 0
    mode: str = "zero_gravity"
    days: tuple[int, ...] = ()
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    request: Request
    link: Link
    packets: tuple[bytes, ...]
    cache: tuple[Alarm, ...]


class SonicSleepController(ProfileExecution[SonicSleepProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        if coordinator.entry.data.get(CONF_PRODUCT_TYPE, "one") != "one":
            raise ValueError("SonicSleep requires its fixed one/IQRM product")
        self.profile = PROFILE
        self._link: Link | None = None
        self._receiver = Receiver()
        self.observations: dict[str, object] = {}
        self.alarms: list[Alarm] = []
        # The source list can retain multiple records for one ID. Mutations
        # must use that ID's latest received fields, not an older list entry.
        self._alarm_records: dict[int, Alarm] = {}
        self._stale_alarm_ids: set[int] = set()
        self._changed = asyncio.Event()

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        """This app performs no BED GATT reads, including Device Information."""
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        """Skip invented release writes. Firmware motion termination is unverified."""
        return True

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
    def position_number_specs(self) -> tuple[()]:
        """No selected BED caller sets positions or proves a calibration."""
        return ()

    def validate_memory_recall(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("SonicSleep exposes memory slots 1 and 2")

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return memory_num in (1, 2)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(DIRECTIONS)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key, "head_feet" if key == "both" else key, partial(_action, action=axis + "_up"), partial(_action, action=axis + "_down"),
                lambda c: c.stop_all(), scheduler_resource="*",
                hold=ControllerMotorHoldSpec(axis + "_up", axis + "_down", press_is_native=True, stop_scope="side"),
            )
            for key, axis in (("back", "head"), ("legs", "foot"), ("both", "both"))
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                "sonicsleep_" + action + ("_save" if save else ""),
                ("Save " if save else "") + action.replace("_", " ").title(),
                partial(_action, action=action, save=save),
                icon="mdi:content-save" if save else "mdi:bed",
                translation_key="sonicsleep_action",
                translation_placeholders={"action": ("Save " if save else "") + action.replace("_", " ").title()},
                card=CARD_PRESETS,
                requires_confirmation=save,
            )
            for action in PRESETS if not action.startswith("memory_") for save in (False, True)
        )

    def standard_button_requires_confirmation(self, key: str) -> bool:
        return key in ("program_memory_1", "program_memory_2")

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (ControllerStateSensorSpec("sonicsleep", "sonicsleep", MODEL, "mdi:bed", attribute_keys=(OBSERVATIONS, ALARMS, LINK_NAME_STATE)),)

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if current is None or (link is not None and current is not link) or self._coordinator is not current.owner or self._coordinator.controller is not self or self.client is not current.client or not current.client.is_connected:
            raise ConnectionError("SonicSleep physical session changed")
        if self.command_side is not None:
            raise ValueError("SonicSleep has no single-address side selector")
        return current

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("SonicSleep is disconnected")
        write = notify = None
        single = False
        routes = {codec.TRANSPORTS[key].service_uuid: codec.TRANSPORTS[key] for key in ROUTES.values()}
        for service in client.services:
            route = routes.get(service.uuid.lower())
            if route is None:
                continue
            single = route.single  # The app overwrites the route independently of the first roles.
            if write is None:
                write = next((c for c in service.characteristics if c.uuid.lower() == route.write_uuid and "write" in c.properties), None)
            if notify is None:
                notify = next((c for c in service.characteristics if "notify" in c.properties), None)
        if write is None or notify is None:
            raise ValueError("SonicSleep requires a supported writable route and notify property")
        link = self._link = Link(client, write, notify, single, self._coordinator)

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            try:
                self._live(link)
            except (ConnectionError, ValueError):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for frame in self._receiver.feed(bytes(data)):
                state = decode(frame)
                self.observations.update(state)
                alarm = parse_alarm(frame)
                if alarm is not None:
                    if frame[5] == 2:
                        if alarm not in self.alarms:
                            self.alarms.insert(0, alarm)
                        self._alarm_records[alarm.id] = alarm
                        self._stale_alarm_ids.discard(alarm.id)
                    else:
                        for i, old in enumerate(self.alarms):
                            if old.id == alarm.id:
                                self.alarms[i] = alarm
                                self._alarm_records[alarm.id] = alarm
                                self._stale_alarm_ids.discard(alarm.id)
                                break
                self._changed.set()
            self._publish()

        await client.start_notify(notify, receive)
        for enum, code in (EXIT_LIMIT, QUERY_CLOCK):
            await self._send(link, codec.function(code, action=enum, single=single))
        for packet in (LINK_NAME, *codec.time_sync(dt_util.now())):
            await self._send(link, packet)
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._receiver = Receiver()
        self.observations.clear()
        self.alarms.clear()
        self._alarm_records.clear()
        self._stale_alarm_ids.clear()
        self._changed.set()
        self._publish()

    def _publish(self) -> None:
        name = self.observations.get("link_name")
        self.forward_controller_state_updates(MODEL(self.profile.label), OBSERVATIONS(dict(self.observations)), ALARMS([asdict(a) for a in self.alarms]), LINK_NAME_STATE(name if isinstance(name, str) else None))

    async def _send(self, link: Link, packet: bytes, *, deadline: float | None = None, plan: PreparedRequest | None = None) -> None:
        cancel = self._coordinator.cancel_command
        delay = TICK_S if deadline is None else min(TICK_S, max(0, deadline - monotonic()))
        if await _pause(delay, cancel):
            return
        self._live(link)
        if deadline is not None and monotonic() >= deadline:
            return

        async def write() -> None:
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set() or deadline is not None and monotonic() >= deadline:
                    return
                if plan is not None:
                    # Notifications may change the cache while the tick or BLE
                    # lock waits. Validate at the actual write boundary.
                    self.validate_plan(plan)
                    if plan.request.operation in ("new", "edit", "toggle", "delete"):
                        # ACKs do not contain the new record. Keep the last
                        # observation visible, but require fresh fields to reuse it.
                        self._stale_alarm_ids.add(packet[6])
                response = "write-without-response" not in link.write.properties
                self._record_command_trace(link.write.uuid, packet, response=response, characteristic=link.write)
                async with asyncio.timeout(WRITE_TIMEOUT_S):
                    await link.client.write_gatt_char(link.write, packet, response=response)

        # A cancelled owner must settle the write already handed to BLE. There
        # is no pending FIFO and no retry/backfill after a slow radio write.
        task = asyncio.create_task(write())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except Exception:  # noqa: BLE001 - propagated by result below.
                break
        if cancelled:
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        task.result()

    async def action(self, action: str, *, save: bool = False) -> None:
        if action in DIRECTIONS and not save:
            duration = self.leased_hold_ms(self._coordinator.motor_pulse_count * 100)
            await self.hold_control(action, duration)
            return
        if action == "flat" and not save:
            code = FLAT
        elif action in PRESETS:
            code = PRESETS[action][int(save)]
        else:
            raise ValueError("Unknown SonicSleep control")
        link = self._live()
        await self._send(link, codec.function(code, single=link.single))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in DIRECTIONS or isinstance(duration_ms, bool) or not 0 < duration_ms <= 60000:
            raise ValueError("Choose a SonicSleep direction and a duration from 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        packet = codec.function(DIRECTIONS[control], single=link.single)
        # The first queue tick precedes the requested movement window.
        deadline = monotonic() + TICK_S + self.leased_hold_ms(duration_ms) / 1000
        while not self._coordinator.cancel_command.is_set() and monotonic() < deadline:
            await self._send(link, packet, deadline=deadline)

    async def stop_all(self) -> None:
        """Scheduler cancellation already ended and drained the held refresh."""

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def move_back_up(self) -> None:
        await self.action("head_up")

    async def move_back_down(self) -> None:
        await self.action("head_down")

    move_head_up = move_back_up
    move_head_down = move_back_down

    async def move_legs_up(self) -> None:
        await self.action("foot_up")

    async def move_legs_down(self) -> None:
        await self.action("foot_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def preset_flat(self) -> None:
        await self.action("flat")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_{memory_num}", save=True)

    def validate_request(self, request: Request) -> None:
        if request.operation not in ("list", "new", "edit", "toggle", "delete", "link_name", "sync_clock"):
            raise ValueError("Unknown SonicSleep operation")
        if request.operation in ("edit", "toggle", "delete") and (request.id is None or not 0 <= request.id <= 255):
            raise ValueError("Choose the received alarm ID")
        if request.operation in ("new", "edit"):
            form_alarm(request.id or 1, request.hour, request.minute, request.mode, request.days, request.enabled)

    async def prepare_request(self, request: Request) -> tuple[bytes, ...]:
        self.validate_request(request)
        link = self._live()
        if request.operation == "link_name":
            return (LINK_NAME,)
        if request.operation == "sync_clock":
            return codec.time_sync(dt_util.now())
        try:
            async with asyncio.timeout(STATE_WAIT_S):
                while not self.observations.get("clock_capability"):
                    self._changed.clear()
                    await self._changed.wait()
                    self._live(link)
                if request.operation == "list":
                    return (LIST_ALARMS,)
                if request.operation == "new":
                    self.alarms.clear()
                    self._alarm_records.clear()
                    await self._send(link, LIST_ALARMS)
                    # There is no source-proven list terminator or empty-list
                    # reply. Silence cannot prove an empty cache. Require a
                    # current response, then collect its burst for a bounded
                    # HA observation window before allocating a new ID.
                    while not self.alarms:
                        self._changed.clear()
                        await self._changed.wait()
                        self._live(link)
                    await _pause(0.2, self._coordinator.cancel_command)
                    self._live(link)
                if request.operation in ("edit", "toggle", "delete"):
                    if request.id in self._stale_alarm_ids or request.id not in self._alarm_records:
                        await self._send(link, LIST_ALARMS)
                    while request.id in self._stale_alarm_ids or request.id not in self._alarm_records:
                        self._changed.clear()
                        await self._changed.wait()
                        self._live(link)
        except TimeoutError:
            raise ValueError("No current-connection SonicSleep clock/alarm reply; no alarm was written") from None
        self._live(link)
        if request.operation == "new":
            # The source's allocator is UI policy, never a received-ID limit.
            if len(self.alarms) > 6:
                raise ValueError("SonicSleep's new-alarm list is full")
            number = next((i for i in range(1, 8) if i not in self._stale_alarm_ids and all(a.id != i for a in self.alarms)), None)
            if number is None:
                raise ValueError("No free SonicSleep new-alarm ID")
            return (form_alarm(number, request.hour, request.minute, request.mode, request.days, request.enabled).packet(),)
        assert request.id is not None
        alarm = self._alarm_records[request.id]
        if request.operation == "toggle":
            return (alarm.toggle(request.enabled).packet(),)
        if request.operation == "delete":
            return (delete_alarm(alarm.id),)
        return (form_alarm(alarm.id, request.hour, request.minute, request.mode, request.days, request.enabled).packet(),)

    async def execute_request(self, request: Request) -> None:
        await self.execute_prepared(await self.prepare_plan(request))

    async def prepare_plan(self, request: Request) -> PreparedRequest:
        link = self._live()
        packets = await self.prepare_request(request)
        self._live(link)
        return PreparedRequest(request, link, packets, tuple(self._alarm_records.values()))

    def validate_plan(self, plan: PreparedRequest) -> None:
        self._live(plan.link)
        if plan.request.operation in ("new", "edit", "toggle", "delete"):
            if tuple(self._alarm_records.values()) != plan.cache or plan.packets[0][6] in self._stale_alarm_ids:
                raise ValueError("SonicSleep alarm list changed during admission; refresh and retry")

    async def execute_prepared(self, plan: PreparedRequest) -> None:
        self.validate_plan(plan)
        if plan.request.operation == "list":
            self.alarms.clear()
            self._alarm_records.clear()
            self._publish()
        for packet in plan.packets:
            await self._send(plan.link, packet, plan=plan)


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


async def _action(controller: BedController, action: str, *, save: bool = False) -> None:
    if not isinstance(controller, SonicSleepController):
        raise TypeError("SonicSleep controller required")
    await controller.action(action, save=save)
