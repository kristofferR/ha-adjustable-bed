"""M Line's accepted direct BLE BED surface and session-safe HA adaptation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonValueType

from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import mline as codec
from ...command_scheduler import current_command_context
from ...const import CONF_BLE_DEVICE_NAME, CONF_HAS_MASSAGE, CONF_PRODUCT_TYPE
from ...controller_state import AnyStateKey
from ...profiles import mline as app
from ..base import BedController, ProfileExecution
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from . import history, state

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

STARTUP_DELAY_S = 0.1
HISTORY_LIMIT: Final = 8192
HISTORY_DEADLINE: Final = 30.0
HISTORY_IDLE: Final = 1.0
HISTORY_ACK_WINDOW: Final = 30.0


@dataclass(frozen=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    firmware: BleakGATTCharacteristic | None
    protocol: BleakGATTCharacteristic | None


async def settled[T](operation: Coroutine[object, object, T]) -> T:
    """Drain an in-flight write/release before giving its wire lane to STOP."""
    task = asyncio.create_task(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


class MLineController(ProfileExecution[app.MLineProfile], BedController):
    def __init__(
        self, coordinator: AdjustableBedCoordinator, protocol: codec.Protocol = "sleep"
    ) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILES[protocol]
        self.layout = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, "two"))
        if self.layout not in app.LAYOUTS:
            raise ValueError("Choose an M Line motor layout")
        self._link: Link | None = None
        self._notifying = False
        self._assembler = codec.Assembler()
        self._last_live: float | None = None
        self._firmware: str | None = None
        self._protocol_string: str | None = None
        self._history: list[history.Record] | None = None
        self._history_event = asyncio.Event()
        self._history_error: str | None = None
        self._history_token: str | None = None
        self._history_ack_until = 0.0
        self._history_idle_at = 0.0
        self._motion_window: tuple[bool, ...] = ()

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.NORDIC_WRITE

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or link is not None
            and current is not link
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("M Line BLE session changed or disconnected")
        return current

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("M Line is disconnected")
        write = notify = firmware = protocol = None
        # Iterate actual GATT order, preserving independent later-role overwrite.
        for service in client.services:
            for char in service.characteristics:
                role = (service.uuid.lower(), char.uuid.lower())
                if role in (
                    (codec.NORDIC_SERVICE, codec.NORDIC_WRITE),
                    (codec.FFE_SERVICE, codec.FFE_WRITE),
                ):
                    write = char
                if role in (
                    (codec.NORDIC_SERVICE, codec.NORDIC_NOTIFY),
                    (codec.FFE_NOTIFY_SERVICE, codec.FFE_NOTIFY),
                ):
                    notify = char
                if role == (codec.INFO_SERVICE, codec.FIRMWARE):
                    firmware = char
                if role == (codec.INFO_SERVICE, codec.PROTOCOL_STRING):
                    protocol = char
        if (
            write is None
            or notify is None
            or "write-without-response" not in write.properties
            or not {"notify", "indicate"}.intersection(notify.properties)
        ):
            raise ValueError("M Line requires its writable no-response and notification GATT roles")
        self._link = Link(client, write, notify, firmware, protocol)

    async def _write(
        self, link: Link, data: bytes, cancel: asyncio.Event, deadline: float | None = None
    ) -> None:
        async with self._ble_lock:
            self._live(link)
            if (
                cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline - 1e-9
            ):
                return
            self._record_command_trace(
                link.write.uuid, data, response=False, characteristic=link.write
            )
            await settled(link.client.write_gatt_char(link.write, data, response=False))
            self._live(link)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 200,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command if cancel_event is None else cancel_event
        for index in range(repeat_count):
            if index and await self._pause(repeat_delay_ms / 1000, cancel):
                return
            await self._write(link, bytes(command), cancel)

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        try:
            async with asyncio.timeout(seconds):
                await cancel.wait()
            return True
        except TimeoutError:
            return False

    def validate_action(self, action: str) -> None:
        if (
            action in (*codec.WORDS, "alarm")
            and action != "stopCommand"
            and self._coordinator.entry.data.get(app.CHILD_MODE, False)
        ):
            raise ValueError("M Line local child mode is enabled")
        if action in app.MASSAGE.values() and not self._coordinator.entry.data.get(
            CONF_HAS_MASSAGE, False
        ):
            raise ValueError("Enable the conditional M Line massage route in Configure")
        if action in ("anti_snore", "privacy", "history", "live") and self.profile.key != "sleep":
            raise ValueError("This M Line feature is available only on the Sleep protocol")

    async def _release(self, link: Link) -> None:
        async def release() -> None:
            await asyncio.sleep(self.profile.release_ms / 1000)
            if self._link is link and self.client is link.client and link.client.is_connected:
                await self._write(
                    link, codec.control("stopCommand", self.profile.key), asyncio.Event()
                )
                context = current_command_context()
                if context is not None:
                    context.cleanup_stop_sent = True

        await settled(release())

    def _held(self) -> dict[str, str]:
        return {
            **{
                f"{axis}_{direction}": actions[index]
                for axis, actions in app.MOTORS.items()
                if axis in app.LAYOUTS[self.layout]
                for index, direction in enumerate(("up", "down"))
            },
            **app.PRESETS,
        }

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._held())

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self._held() or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose an available M Line control and a hold up to 60 seconds")
        self.validate_action(self._held()[control])

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        command = codec.control(self._held()[control], self.profile.key)
        cancel = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
        try:
            while not cancel.is_set() and loop.time() < deadline - 1e-9:
                started = loop.time()
                await self._write(link, command, cancel, deadline)
                # No latency backfill and no write beginning beyond the finite ceiling.
                remaining = deadline - loop.time()
                interval = self.profile.refresh_ms / 1000
                next_tick = started + (int((loop.time() - started) / interval) + 1) * interval
                if remaining <= 0 or await self._pause(
                    min(max(0, next_tick - loop.time()), remaining), cancel
                ):
                    break
        finally:
            await self._release(link)

    async def move_axis(self, axis: str, up: bool) -> None:
        await self.hold_control(
            f"{axis}_{'up' if up else 'down'}",
            max(1, self._coordinator.motor_pulse_count) * self.profile.refresh_ms,
        )

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_lumbar_up(self) -> None:
        await self.move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self.move_axis("lumbar", False)

    async def stop_all(self) -> None:
        context = current_command_context()
        if context is not None:
            if context.cleanup_stop_sent:
                return
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._release(self._live())

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all
    move_lumbar_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                "neck" if axis == "head" else axis,
                lambda c, axis=axis: require(c).move_axis(axis, True),
                lambda c, axis=axis: require(c).move_axis(axis, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_is_native=True
                ),
            )
            for axis in app.LAYOUTS[self.layout]
        )

    async def preset_flat(self) -> None:
        await self.hold_control("flat", 1000)

    async def preset_zero_g(self) -> None:
        await self.hold_control("zero_g", 1000)

    async def preset_anti_snore(self) -> None:
        await self.hold_control("anti_snore", 1000)

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        self.validate_action(app.PRESETS[f"memory_{memory_num}"])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.hold_control(f"memory_{memory_num}", 1000)

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        await self.hold_control(f"memory_{slot}", hold_ms)

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError(
            "The M Line long callback only displays a toast; no save frame is proven"
        )

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        mapping = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_anti_snore": "anti_snore",
            "preset_memory_1": "memory_1",
            "preset_memory_2": "memory_2",
        }
        return ControllerHoldSpec(mapping[key]) if key in mapping else None

    async def one_shot(self, action: str) -> None:
        if action not in ("light", *app.MASSAGE.values()):
            raise ValueError("Unavailable M Line one-shot action")
        self.validate_action(action)
        await self.write_command(codec.control(action, self.profile.key))
        if action != "light":
            await self.check_state()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "mline_light",
                "Light action",
                lambda c: require(c).one_shot("light"),
                card=CARD_UTILITY,
            ),
            ControllerButtonSpec(
                "mline_settings_refresh",
                "Refresh settings",
                lambda c: require(c).settings_refresh(),
            ),
            ControllerButtonSpec(
                "mline_alarm_refresh", "Refresh alarm", lambda c: require(c).alarm_refresh()
            ),
        ]
        if self._coordinator.entry.data.get(CONF_HAS_MASSAGE, False):
            specs.extend(
                ControllerButtonSpec(
                    f"mline_massage_{key}",
                    f"Massage {key}",
                    lambda c, action=action: require(c).one_shot(action),
                    card=CARD_MASSAGE,
                )
                for key, action in app.MASSAGE.items()
            )
        if self.profile.key == "sleep":
            specs.append(
                ControllerButtonSpec(
                    "mline_live_query", "Query live sensor", lambda c: require(c).query_live()
                )
            )
        return tuple(specs)

    async def check_state(self) -> None:
        if (retry := self.profile.status_retry_ms) is not None:
            await self.write_command(codec.AUXILIARY["checkState"], 2, retry)

    async def settings_refresh(self) -> None:
        # SettingPage owns this unconditional write, distinct from checkState.
        await self.write_command(codec.AUXILIARY["checkState"])
        await self.check_state()

    async def query_live(self) -> None:
        self.validate_action("live")
        await self.write_command(codec.AUXILIARY["checkOpenBlemanage"])

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return codec.MODES

    async def sync_clock(self) -> None:
        await self.write_command(
            codec.clock(self.profile.key, dt_util.now()), 2 if self.profile.key == "okin" else 1, 0
        )

    async def alarm_refresh(self) -> None:
        link = self._live()
        await self.sync_clock()
        if not await self._pause(1.0, self._coordinator.cancel_command):
            self._live(link)
            await self._query_alarm()

    async def _query_alarm(self) -> None:
        await self.write_command(
            codec.AUXILIARY[f"checkAlarm.{'P2' if self.profile.key == 'okin' else 'P1'}"]
        )

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        self.validate_action("alarm")
        link = self._live()
        data = (
            codec.alarm(
                self.profile.key,
                hour,
                minute,
                codec.wake_mask(tuple(weekdays), hour, minute, dt_util.now()),
                preset,
            )
            if enabled
            else codec.AUXILIARY[f"closeAlarm.{'P2' if self.profile.key == 'okin' else 'P1'}"]
        )
        await self._write(link, data, self._coordinator.cancel_command)
        if not await self._pause(0.3, self._coordinator.cancel_command):
            self._live(link)
            await self._query_alarm()

    async def configure_privacy(self, enabled: bool) -> None:
        self.validate_action("privacy")
        await self.write_command(
            codec.AUXILIARY["openPrivacyMode" if enabled else "closePrivacyMode"]
        )
        await self.check_state()

    async def configure_anti_snore(
        self, enabled: bool, angle: int, position: int, *, demo: bool = False
    ) -> None:
        self.validate_action("anti_snore")
        link = self._live()
        await self.write_command(codec.anti_snore(enabled, angle, position, demo=demo), 2, 300)
        if not await self._pause(0.3, self._coordinator.cancel_command):
            self._live(link)
            await self.check_state()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return
        for attempt in range(2):
            self._live(link)
            try:
                async with self._ble_lock:
                    self._live(link)
                    # Bleak installs the callback before enabling the CCCD. Its
                    # supported API owns already-subscribed handling and MTU.
                    await link.client.start_notify(
                        link.notify, lambda sender, data: self._receive(link, sender, bytes(data))
                    )
                self._live(link)
                self._notifying = True
                return
            except BleakError, ValueError:
                if attempt:
                    raise
                await asyncio.sleep(1)
        raise ConnectionError("M Line notification setup failed")

    def _receive(self, link: Link, sender: BleakGATTCharacteristic, raw: bytes) -> None:
        if (
            self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
            or sender.handle != link.notify.handle
        ):
            return
        self.forward_raw_notification(sender.uuid, raw)
        data = self._assembler.feed(raw)
        if data is None:
            return
        if (live := codec.live(data)) is not None:
            now = asyncio.get_running_loop().time()
            if self._last_live is None or now - self._last_live > 0.5:
                self._last_live = now
                self._motion_window = (*self._motion_window[-23:], live.moving)
                self.forward_controller_state_updates(state.MOTION_WINDOW(self._motion_window))
                self.forward_controller_state_updates(
                    state.HEART(live.heart),
                    state.BREATH(live.breath),
                    state.MOTION(live.moving),
                    state.PROJECTION(live.projection),
                )
        elif data[:2] == b"\xa5\x0b" and self.profile.key == "sleep":
            if len(data) >= 17:
                self.forward_controller_state_updates(
                    state.ANTI_ENABLED(data[15] == 1), state.ANTI_ANGLE(data[16])
                )
            new = codec.new_sensor_protocol(self._protocol_string, self._firmware)
            if new is not None and len(data) >= (20 if new else 19):
                self.forward_controller_state_updates(
                    state.PRIVACY(bool(data[19] & 2) if new else data[18] == 1)
                )
        elif (alarm := codec.alarm_state(data)) is not None:
            self.forward_controller_state_updates(
                state.ALARM_MODE(codec.alarm_mode(self.profile.key, alarm.mode)),
                state.ALARM(
                    f"{alarm.hour:02}:{alarm.minute:02};{alarm.wake};{alarm.mode};{int(alarm.enabled)}"
                ),
            )
        elif data[:2] in (b"\xa6\x30", b"\xa6\x31") and self._history is not None:
            # Reader receives the complete payload, including its original prefix.
            self._history_idle_at = asyncio.get_running_loop().time() + HISTORY_IDLE
            rows = history.records(data, dt_util.now())
            if len(self._history) + len(rows) > HISTORY_LIMIT:
                self._history_error = "M Line raw history exceeded its bounded record limit"
            else:
                self._history.extend(rows)
            self._history_event.set()
        # A61106 and forwarded ED alarm replies intentionally publish no state.

    async def async_on_connect(self, session: ControllerSession) -> None:
        await self.start_notify()
        await self.async_read_device_info(session)

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        link = self._live()
        for char, field in ((link.firmware, "firmware"), (link.protocol, "protocol")):
            if char is not None and "read" in char.properties:
                async with self._ble_lock:
                    self._live(link)
                    raw = await link.client.read_gatt_char(char)
                self._live(link)
                try:
                    value = bytes(raw).decode("utf-8").rstrip("\0")
                except UnicodeDecodeError:
                    continue
                if field == "firmware":
                    self._firmware = value
                else:
                    self._protocol_string = value
        return True

    async def async_after_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await asyncio.sleep(STARTUP_DELAY_S)
        self._live(link)
        await self.sync_clock()
        await self.check_state()
        # Phone analytics' automatic history transfer is deliberately excluded.

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._assembler = codec.Assembler()
        self._last_live = None
        self._motion_window = ()
        self._firmware = self._protocol_string = None
        self._history_token = None
        if self._history is not None:
            self._history_error = "M Line disconnected during raw history transfer"
            self._history_event.set()
        self.forward_controller_state_updates(
            state.HEART(None),
            state.BREATH(None),
            state.MOTION(None),
            state.PROJECTION(None),
            state.PRIVACY(None),
            state.ANTI_ENABLED(None),
            state.ANTI_ANGLE(None),
            state.ALARM(None),
            state.ALARM_MODE(None),
            state.MOTION_WINDOW(None),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields: list[tuple[AnyStateKey, str]] = [
            (state.ALARM, "mdi:alarm"),
            (state.ALARM_MODE, "mdi:alarm-check"),
        ]
        if self.profile.key == "sleep":
            fields.extend(
                (
                    (state.HEART, "mdi:heart-pulse"),
                    (state.BREATH, "mdi:lungs"),
                    (state.ANTI_ANGLE, "mdi:angle-acute"),
                )
            )
        return tuple(
            ControllerStateSensorSpec(str(key), str(key), key, icon) for key, icon in fields
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        if self.profile.key != "sleep":
            return ()
        return tuple(
            ControllerStateBinarySensorSpec(
                str(key),
                str(key),
                key,
                icon,
                attribute_keys=(state.MOTION_WINDOW,) if key == state.MOTION else (),
            )
            for key, icon in (
                (state.MOTION, "mdi:motion-sensor"),
                (state.PROJECTION, "mdi:checkbox-blank-circle-outline"),
                (state.PRIVACY, "mdi:eye-off"),
                (state.ANTI_ENABLED, "mdi:sleep"),
            )
        )

    async def read_history(self, *, all_records: bool = False) -> dict[str, JsonValueType]:
        self.validate_action("history")
        if self._history is not None:
            raise ValueError("An M Line history transfer is already active")
        link = self._live()
        self._history_token = None
        self._history = []
        self._history_error = None
        self._history_event.clear()
        self._history_idle_at = asyncio.get_running_loop().time() + HISTORY_IDLE
        try:
            async with asyncio.timeout(HISTORY_DEADLINE):
                await self.write_command(
                    codec.AUXILIARY[
                        "gainAllHistoricalData" if all_records else "gainNewHistoricalData"
                    ],
                    2,
                    300,
                )
                while True:
                    self._live(link)
                    if self._history_error:
                        raise ValueError(self._history_error)
                    self._history_event.clear()
                    try:
                        async with asyncio.timeout(
                            max(0, self._history_idle_at - asyncio.get_running_loop().time())
                        ):
                            await self._history_event.wait()
                    except TimeoutError:
                        break
            self._live(link)
            if self._history_error:
                raise ValueError(self._history_error)
            groups = history.grouped(self._history)
            token = uuid4().hex
            self._history_token = token
            self._history_ack_until = asyncio.get_running_loop().time() + HISTORY_ACK_WINDOW
            return {
                "transfer": token,
                "groups": [[r.as_dict() for r in group] for group in groups],
                "acknowledged": False,
            }
        finally:
            self._history = None
            self._history_event.clear()

    def validate_history_ack(self, token: str) -> None:
        self.validate_action("history")
        if asyncio.get_running_loop().time() > self._history_ack_until:
            self._history_token = None
        if not token or token != self._history_token:
            raise ValueError("Acknowledge only a completed raw transfer on this same live session")
        self._live()

    async def acknowledge_history(self, token: str) -> None:
        self.validate_history_ack(token)
        self._history_token = None
        await self.write_command(codec.AUXILIARY["confirmGainHistoryData"], 2, 300)


def require(controller: BedController) -> MLineController:
    if not isinstance(controller, MLineController):
        raise ValueError("Select an M Line bed")
    return controller


async def build_controller(ctx: BuildContext) -> MLineController:
    selected = ctx.variant or "auto"
    if selected == "auto":
        name = (
            ctx.live_device_name
            or ctx.advertisement_name
            or str(ctx.data.get(CONF_BLE_DEVICE_NAME, ""))
        )
        protocol = app.resolve_protocol(name, ctx.manufacturer_data or {})
    elif selected in codec.PROTOCOLS:
        protocol = codec.PROTOCOLS[codec.PROTOCOLS.index(selected)]
    else:
        raise ValueError("Choose an M Line protocol")
    return MLineController(ctx.coordinator, protocol)
