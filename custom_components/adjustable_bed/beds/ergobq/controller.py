"""ErgoBQ BED controls, authentication and replies owned by one GATT session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...codec import ergobq as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...profiles import ergobq as app
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import BedController, ProfileExecution
from ..cancellation import cancellable, settled
from ..entity_specs import MotorControlSpec

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession

POSITIONS: Final = {dp: StateKey[int | None](f"ergobq_position_{dp}") for dp in app.AXES}
CHILD_LOCK: Final = StateKey[bool | None]("ergobq_child_lock")
MASSAGE_SYNC: Final = StateKey[bool | None]("ergobq_massage_sync")
SIDE: Final = StateKey[str | None]("ergobq_side")
IDENTITY: Final = StateKey[str | None]("ergobq_identity")
FAULTS: Final = StateKey[int | None]("ergobq_faults")
FAULT_NAMES: Final = (
    "head_motor",
    "foot_motor",
    "headrest_motor",
    "waist_motor",
    "control_box_overheat",
    "massage",
    "anti_pinch",
    "light",
)
FAULT_FLAGS: Final = {name: StateKey[bool | None](f"ergobq_fault_{name}") for name in FAULT_NAMES}
PARTNER_CONNECTED: Final = StateKey[bool | None]("ergobq_partner_connected")
PARTNER_BROADCAST: Final = StateKey[bool | None]("ergobq_partner_broadcast")
LIGHT_MINUTES: Final = StateKey[int | None]("ergobq_light_minutes")
LIGHT_REMAINING: Final = StateKey[int | None]("ergobq_light_remaining")
DIY_REMAINING: Final = StateKey[int | None]("ergobq_diy_remaining")
MASSAGE_FIELDS: Final = {
    (zone, field): StateKey[int | None](f"ergobq_{zone}_{field}")
    for zone in ("head", "legs")
    for field in ("intensity", "minutes", "remaining")
}
MASSAGE_MODE: Final = {
    zone: StateKey[str | None](f"ergobq_{zone}_mode") for zone in ("head", "legs")
}
MASSAGE_ON: Final = {zone: StateKey[bool | None](f"ergobq_{zone}_on") for zone in ("head", "legs")}


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic


class ErgoBQController(ProfileExecution[app.ErgoBQProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILE
        self.axes = tuple(app.AXES)[: app.motor_count(coordinator.entry.data.get(app.SERIAL, ""))]
        self._link: Link | None = None
        self._authorized = False
        self._receiver = codec.Receiver()
        self._waiters: list[tuple[int | None, asyncio.Future[codec.Frame]]] = []
        self._massages: dict[str, codec.Massage] = {}
        self._massage_sync: bool | None = None
        self._sync_revision = 0
        self._private_write = ContextVar("ergobq_private_write", default=False)
        self._metadata: dict[int, bytes] = {}
        self._partner: bytes | None = None
        self._diy: tuple[int, tuple[codec.Segment, ...]] | None = None

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
    def commands_share_timer(self) -> bool:
        # A route change during a hold would send its release to another side.
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def position_number_specs(self):
        # The app values have no proven degrees/percentage mapping. The custom
        # numbers carry their own native targets and never use angle seeking.
        return ()

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    @property
    def supports_light_color_control(self) -> bool:
        return True

    @property
    def supported_color_mode(self) -> str:
        return "rgb"

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def supports_light_level_control(self) -> bool:
        return True

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        from .entities import motor_specs

        return motor_specs(self)

    @property
    def controller_button_specs(self):
        from .entities import buttons

        return buttons(self)

    @property
    def controller_number_specs(self):
        from .entities import numbers

        return numbers(self)

    @property
    def controller_switch_specs(self):
        from .entities import switches

        return switches(self)

    @property
    def controller_select_specs(self):
        from .entities import selects

        return selects(self)

    @property
    def controller_state_sensor_specs(self):
        from .entities import sensors

        return sensors(self)

    @property
    def controller_state_binary_sensor_specs(self):
        from .entities import binary_sensors

        return binary_sensors(self)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{dp}_{direction}" for dp in self.axes for direction in ("up", "down"))

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and getattr(self._coordinator, "controller", self) is self
        )

    def _live(self, *, authorized: bool = True) -> Link:
        link = self._link
        if link is None or not self._current(link) or authorized and not self._authorized:
            raise ConnectionError("ErgoBQ BED session is unavailable or unauthenticated")
        return link

    async def _send(
        self,
        link: Link,
        packet: bytes,
        cancel: asyncio.Event,
        *,
        setup: bool = False,
        on_submit: Callable[[], None] | None = None,
        reply_command: int | None = None,
    ) -> None:
        chunk_size = max(1, link.client.mtu_size - 3)
        if "write-without-response" in link.write.properties:
            chunk_size = min(chunk_size, link.write.max_write_without_response_size)
        for pos in range(0, len(packet), chunk_size):
            chunk = packet[pos : pos + chunk_size]
            for attempt in range(self.profile.attempts):
                if cancel.is_set():
                    raise asyncio.CancelledError
                if not self._current(link):
                    raise ConnectionError("ErgoBQ session changed before write")
                reply = None
                if reply_command is not None and pos + chunk_size >= len(packet):
                    reply = asyncio.get_running_loop().create_future()
                    self._waiters.append((reply_command, reply))
                private = self._private_write.set(packet[:4] == b"\x55\xaa\x00\x03")
                try:
                    await self._write_gatt_with_retry(
                        codec.WRITE,
                        chunk,
                        cancel_event=cancel,
                        response="write-without-response" not in link.write.properties,
                        characteristic=link.write,
                        expected_client=link.client,
                        before_write=lambda: self._before_write(link, on_submit),
                        settle_write=True,
                        write_timeout=self.profile.write_timeout,
                        track_command_write=not setup,
                    )
                    if cancel.is_set():
                        raise asyncio.CancelledError
                    self._check_link(link)
                    if reply is not None:
                        await self._wait(reply, self.profile.response_timeout, cancel)
                    break
                except BleakError, TimeoutError:
                    if attempt == self.profile.attempts - 1:
                        raise
                    await cancellable(asyncio.sleep(self.profile.retry_delay), cancel)
                finally:
                    self._private_write.reset(private)
                    if reply is not None:
                        self._waiters = [(cmd, f) for cmd, f in self._waiters if f is not reply]
                        reply.cancel()

    def _check_link(self, link: Link) -> None:
        if not self._current(link):
            raise ConnectionError("ErgoBQ operation belongs to a previous connection")

    def _before_write(self, link: Link, on_submit: Callable[[], None] | None) -> None:
        self._check_link(link)
        if on_submit is not None:
            on_submit()

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        # App actions are single-shot. HA pulse settings never repeat a DP map.
        await self._send(self._live(), command, cancel_event or self._coordinator.cancel_command)

    async def publish(self, entries: tuple[codec.DP, ...]) -> None:
        await self.write_command(codec.publish(entries))

    async def _wait(
        self, future: asyncio.Future[codec.Frame], seconds: float, cancel: asyncio.Event
    ) -> codec.Frame:
        async with asyncio.timeout(seconds):
            return await cancellable(self._await_future(future), cancel)

    async def _await_future(self, future: asyncio.Future[codec.Frame]) -> codec.Frame:
        return await future

    async def request(
        self,
        command: int,
        payload: bytes,
        *,
        timeout: float,
        response_wait: bool = False,
        cancel: asyncio.Event | None = None,
        setup: bool = False,
    ) -> codec.Frame:
        link = self._live(authorized=not setup)
        event = cancel or self._coordinator.cancel_command
        future = asyncio.get_running_loop().create_future()
        self._waiters.append((command, future))
        try:
            # The sync/controller deadline starts before enqueue. Metadata and
            # unlink additionally wait up to 1 s for their nonempty response at
            # the last fragment; no undocumented ACK payload is invented.
            async with asyncio.timeout(timeout):
                await self._send(
                    link,
                    codec.frame(command, payload),
                    event,
                    setup=setup,
                    reply_command=command if response_wait else None,
                )
                result = await cancellable(self._await_future(future), event)
            self._check_link(link)
            return result
        finally:
            self._waiters = [
                (cmd, pending) for cmd, pending in self._waiters if pending is not future
            ]
            future.cancel()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        # Only CMD01 metadata is proven here. No generic DIS reads.
        return True

    async def async_on_connect(self, session: ControllerSession) -> None:
        if self._coordinator.entry.data.get("product_type") not in app.PRODUCTS:
            raise ValueError("Select an explicit ErgoBQ BED product identity first")
        await session.async_start_notify()

    async def async_after_connect(self, session: ControllerSession) -> None:
        context = current_command_context()
        # Manual startup has no running caller, and must not reuse an old STOP
        # event. A command-owned connection keeps that caller's cancellation.
        cancel = context.cancel_event if context is not None else asyncio.Event()
        link = self._live(authorized=False)
        try:
            await cancellable(asyncio.sleep(self.profile.notify_settle), cancel)
            response = await self.request(
                3,
                b"\x01\x01" + self._coordinator.entry.data.get(app.STAMP, "").strip().encode(),
                timeout=self.profile.auth_timeout,
                cancel=cancel,
                setup=True,
            )
            if response.payload[0] != 1:
                raise ConnectionError("ErgoBQ channel authentication rejected")
            if not session.is_current():
                raise ConnectionError("ErgoBQ setup session changed")
            self._check_link(link)
            self._authorized = True
            await self._clock(link, cancel, setup=True)
            # Sending these queries proves no device ACK or feature-bit meaning.
            await self._send(link, codec.frame(0), cancel, setup=True)
            await self._send(link, codec.frame(2), cancel, setup=True)
        except BaseException:
            self._authorized = False
            raise

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self._link is not None:
            self._check_link(self._link)
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("No ErgoBQ BLE client")
        service = client.services.get_service(codec.SERVICE)
        if service is None:
            raise ConnectionError("ErgoBQ BED service is missing")
        write = next((char for char in service.characteristics if char.uuid == codec.WRITE), None)
        notify = next((char for char in service.characteristics if char.uuid == codec.NOTIFY), None)
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
        ):
            raise ConnectionError("ErgoBQ BED GATT roles are missing")
        link = self._link = Link(client, write, notify)
        self._receiver = codec.Receiver()

        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(link):
                return
            # Channel-auth payloads can contain private association data.
            for packet in self._receiver.feed(bytes(data)):
                for command, waiter in tuple(self._waiters):
                    if not waiter.done() and (
                        command is None or command == packet.command and packet.payload
                    ):
                        waiter.set_result(packet)
                if packet.command == 5:
                    self.forward_raw_notification(codec.NOTIFY, packet.wire)
                    try:
                        self._status(codec.parse_dps(packet.payload))
                    except ValueError:
                        continue
                elif packet.command == 1:
                    self._metadata = codec.parse_info(packet.payload)

        try:
            await client.start_notify(notify, receive)
            self._check_link(link)
        except BaseException:
            self.on_disconnect()
            raise

    def on_disconnect(self) -> None:
        self._link = None
        self._authorized = False
        self._receiver = codec.Receiver()
        self._massages.clear()
        self._massage_sync = None
        self._metadata.clear()
        self._partner = None
        self._diy = None
        for _, waiter in self._waiters:
            waiter.cancel()
        self._waiters.clear()
        keys = (
            *POSITIONS.values(),
            CHILD_LOCK,
            MASSAGE_SYNC,
            SIDE,
            IDENTITY,
            FAULTS,
            LIGHT_MINUTES,
            LIGHT_REMAINING,
            DIY_REMAINING,
            *MASSAGE_FIELDS.values(),
            *MASSAGE_ON.values(),
            *MASSAGE_MODE.values(),
            *FAULT_FLAGS.values(),
            PARTNER_CONNECTED,
            PARTNER_BROADCAST,
            UNDER_BED_LIGHTS_ON,
            LIGHT_LEVEL,
            UNDER_BED_LIGHTS_RGB,
        )
        if getattr(self._coordinator, "controller", self) in (self, None):
            self.forward_controller_state_updates(*(key(None) for key in keys))

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        self._notify_callback = None
        if link is not None and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def _status(self, values: dict[int, codec.Value]) -> None:
        for dp, key in POSITIONS.items():
            value = values.get(dp)
            if type(value) is int:
                self.forward_controller_state_update(key, value)
        for dp, key in ((18, MASSAGE_SYNC), (30, CHILD_LOCK), (50, UNDER_BED_LIGHTS_ON)):
            value = values.get(dp)
            if type(value) is bool:
                self.forward_controller_state_update(key, value)
                if dp == 18:
                    self._massage_sync = value
                    self._sync_revision += 1
        for dp, key in (
            (51, LIGHT_LEVEL),
            (53, LIGHT_MINUTES),
            (55, LIGHT_REMAINING),
            (16, MASSAGE_FIELDS["head", "remaining"]),
            (17, MASSAGE_FIELDS["legs", "remaining"]),
        ):
            value = values.get(dp)
            if type(value) is int:
                self.forward_controller_state_update(key, value)
        for dp, key, options in ((9, SIDE, ("a", "b", "ab")), (32, IDENTITY, ("unset", "a", "b"))):
            value = values.get(dp)
            if type(value) is int:
                self.forward_controller_state_update(
                    key, options[value] if 0 <= value < len(options) else options[0]
                )
        for dp, zone in ((12, "head"), (14, "legs")):
            value = values.get(dp)
            if isinstance(value, bytes) and len(value) >= 4:
                massage = codec.Massage(value[0] == 1, value[1], value[2], value[3])
                try:
                    massage.encode()
                except ValueError:
                    continue
                self._massages[zone] = massage
                self.forward_controller_state_update(MASSAGE_ON[zone], massage.on)
                self.forward_controller_state_update(MASSAGE_MODE[zone], app.MODES[massage.mode])
                for field in ("intensity", "minutes"):
                    self.forward_controller_state_update(
                        MASSAGE_FIELDS[zone, field], getattr(massage, field)
                    )
        rgb = values.get(52)
        if isinstance(rgb, bytes) and len(rgb) >= 3:
            self.forward_controller_state_update(UNDER_BED_LIGHTS_RGB, (rgb[0], rgb[1], rgb[2]))
        packed = values.get(54)
        if isinstance(packed, bytes) and len(packed) >= 6:
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_ON(packed[0] == 1),
                LIGHT_LEVEL(packed[1]),
                UNDER_BED_LIGHTS_RGB((packed[2], packed[3], packed[4])),
                LIGHT_MINUTES(packed[5]),
            )
        faults = values.get(31)
        if isinstance(faults, bytes):
            bitmap = int.from_bytes(faults[:4], "big") if len(faults) >= 4 else 0
            self.forward_controller_state_update(FAULTS, bitmap)
            self.forward_controller_state_updates(
                *(
                    FAULT_FLAGS[name](bool(bitmap & 1 << bit))
                    for bit, name in enumerate(FAULT_NAMES)
                )
            )
        partner = values.get(33)
        if isinstance(partner, bytes):
            self._partner = partner[:6].ljust(6, b"\x00")
            self.forward_controller_state_updates(
                PARTNER_CONNECTED(any(self._partner)),
                PARTNER_BROADCAST(self._partner == bytes([255] * 6)),
            )
        program = values.get(60)
        if isinstance(program, bytes):
            self._diy = codec.parse_diy(program)
        diy = values.get(61)
        if isinstance(diy, bytes) and len(diy) >= 4:
            self.forward_controller_state_update(DIY_REMAINING, int.from_bytes(diy[2:4], "big"))
        # DP41 is intentionally not interpreted, including deletion/clearAll.

    async def target(self, motor: int, value: int) -> None:
        if motor not in self.axes:
            raise ValueError("Motor is not present in this serial's layout")
        await self.publish((codec.number(motor, codec.integer(value, 0, app.AXES[motor][1])),))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Unknown ErgoBQ motor control")
        codec.integer(duration_ms, 1, 60000)
        motor, direction = control.split("_")
        link = self._live()
        event = self._coordinator.cancel_command
        started = False

        def sent() -> None:
            nonlocal started
            started = True

        async def release() -> None:
            if started and self._current(link):
                await self._send(link, codec.publish((codec.boolean(5, True),)), asyncio.Event())

        async with self.releasing(release):
            value = app.AXES[int(motor)][1] if direction == "up" else 0
            await self._send(
                link, codec.publish((codec.number(int(motor), value),)), event, on_submit=sent
            )
            await cancellable(asyncio.sleep(duration_ms / 1000), event)

    async def _move(self, motor: int, up: bool) -> None:
        await self.hold_control(f"{motor}_{'up' if up else 'down'}", 1000)

    async def move_head_up(self) -> None:
        await self._move(1, True)

    async def move_head_down(self) -> None:
        await self._move(1, False)

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_legs_up(self) -> None:
        await self._move(2, True)

    async def move_legs_down(self) -> None:
        await self._move(2, False)

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        await self._send(self._live(), codec.publish((codec.boolean(5, True),)), asyncio.Event())

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def scene(self, name: str, operation: int = 6) -> None:
        codec.integer(operation, 6, 8)
        await self.publish((codec.enumeration(operation, app.SCENES[name]),))

    async def preset_flat(self) -> None:
        await self.scene("flat")

    async def preset_memory(self, memory_num: int) -> None:
        codec.integer(memory_num, 1, 2)
        await self.scene(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        codec.integer(memory_num, 1, 2)
        await self.scene(f"memory_{memory_num}", 7)

    async def set_massage(self, zone: str, massage: codec.Massage) -> None:
        if zone not in MASSAGE_ON:
            raise ValueError("Unknown massage zone")
        targets = (zone,)
        if (
            self._massage_sync is True
            and len(self._massages) == 2
            and self._massages["head"] == self._massages["legs"]
        ):
            targets = ("head", "legs")
        link = self._live()
        previous = {target: self._massages.get(target) for target in targets}
        try:
            await self.publish(
                tuple(
                    codec.raw(12 if target == "head" else 14, massage.encode())
                    for target in targets
                )
            )
        except BaseException:
            for target in targets:
                if self._massages.get(target) is previous[target]:
                    self._massages.pop(target, None)
            raise
        if self._current(link):
            # Preserve successful intent for the next partial edit, without
            # overwriting a report received during the write. Entities still
            # show only values reported by the bed.
            for target in targets:
                if self._massages.get(target) is previous[target]:
                    self._massages[target] = massage

    async def set_massage_sync(self, enabled: bool) -> None:
        revision = self._sync_revision
        try:
            await self.publish((codec.boolean(18, enabled),))
        except BaseException:
            if revision == self._sync_revision:
                self._massage_sync = None
            raise
        if revision == self._sync_revision:
            self._massage_sync = enabled

    async def change_massage(self, zone: str, field: str, value: bool | int) -> None:
        current = self._massages.get(zone)
        if current is None:
            raise ValueError("Wait for current massage parameters before editing one field")
        await self.set_massage(zone, replace(current, **{field: value}))

    async def lights_on(self) -> None:
        await self.publish((codec.boolean(50, True),))

    async def lights_off(self) -> None:
        await self.publish((codec.boolean(50, False),))

    async def set_light_level(self, level: int) -> None:
        await self.publish((codec.number(51, codec.integer(level, 0, 100)),))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.publish((codec.raw(52, bytes(codec.integer(v, 0, 255) for v in rgb_color)),))

    async def _clock(self, link: Link, cancel: asyncio.Event, *, setup: bool = False) -> None:
        now = dt_util.now()
        offset = now.utcoffset()
        await self._send(
            link,
            codec.clock(int(now.timestamp()), int(offset.total_seconds()) if offset else 0),
            cancel,
            setup=setup,
        )

    async def sync_clock(self) -> None:
        await self._clock(self._live(), self._coordinator.cancel_command)

    async def metadata(self) -> None:
        await self.request(1, b"\x00", timeout=self.profile.metadata_timeout, response_wait=True)

    async def unlink(self, phase: int = 2) -> None:
        codec.integer(phase, 2, 3)
        packet = codec.auth(self._coordinator.entry.data.get(app.STAMP, ""), phase=phase)
        link = self._live()
        try:
            await self.request(
                3, packet[6:-2], timeout=self.profile.unlink_timeout, response_wait=True
            )
        finally:
            # A waiter match is not a decoded unlink success code. Even a timed
            # out/cancelled write may have changed the association. HA releases
            # its original link and requires fresh authentication afterward.
            self.on_disconnect()
            if self.client is link.client and link.client.is_connected:
                await settled(link.client.disconnect())

    def _format_command_trace_payload(self, command: bytes):
        if self._private_write.get() or command[:4] == b"\x55\xaa\x00\x03":
            return {"hex": "**REDACTED**", "length": len(command), "ascii_preview": None}
        return super()._format_command_trace_payload(command)
