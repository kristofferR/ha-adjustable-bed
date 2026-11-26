"""Direct BLE controls for the Langjue Comfort Smart Bed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Final, cast

from homeassistant.util import dt as dt_util

from ..alarm import AlarmCapability, AlarmRequest
from ..card import CARD_PRESETS
from ..codec import langjue as codec
from ..codec.langjue import Op
from ..command_scheduler import (
    CommandContext,
    capture_caller_cancellation,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
)
from ..const import CONF_HAS_LIGHT, CONF_HAS_MASSAGE, CONF_PRODUCT_TYPE
from ..controller_state import StateKey
from ..errors import invalid, rejected
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities
from ..profiles import langjue as app
from ..runtime_data import DomainKey, domain_registry
from ..state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, massage_intensity
from .base import BedController
from .cancellation import cancellable, settled
from .catalog_buttons import PRESET_KEY, massage_button
from .entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from homeassistant.core import HomeAssistant

    from ..coordinator import AdjustableBedCoordinator

_REPLY_TIMEOUT: Final = 2.0
ALARM_ENABLED: Final = StateKey[bool | None]("langjue_alarm_enabled")
_READ_ALARM: Final = codec.frame(Op.READ_ALARM, 1, b"\x00")
_ALARM_RECEIVERS = DomainKey[set[str]]("langjue_alarm_receivers")


@contextmanager
def reserve_alarm_receivers(hass: HomeAssistant, addresses: Collection[str]) -> Iterator[None]:
    """Claim every Langjue receiver before any check can read its alarm record."""
    receivers = {address.upper() for address in addresses}
    active = domain_registry(hass, _ALARM_RECEIVERS, set)
    if not active.isdisjoint(receivers):
        raise invalid("langjue_alarm_busy")
    active.update(receivers)
    try:
        yield
    finally:
        active.difference_update(receivers)


class _ReplyMissing(TimeoutError):
    """A P1 request was sent without a matching notification."""


@dataclass(slots=True)
class _Link:
    client: BleakClient
    writer: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    motor_count: int = 0
    reply: tuple[Op, asyncio.Future[codec.Notification]] | None = None
    cleanup_context: CommandContext | None = None
    alarm_payload: bytes | None = None
    checked_alarm: AlarmRequest | None = None
    massage_status_code: int | None = None


def resolve_gatt(client: BleakClient) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
    """Find the app's property roles inside the exact P1 service."""
    services = [service for service in client.services if service.uuid.lower() == app.SERVICE]
    if len(services) != 1:
        raise ConnectionError("Expected one Langjue bed service")
    chars = services[0].characteristics
    writers = [char for char in chars if "write" in char.properties]
    notifiers = [
        char for char in chars if "write" not in char.properties and "notify" in char.properties
    ]
    if len(writers) != 1 or "write-without-response" not in writers[0].properties:
        raise ConnectionError("Expected one Langjue characteristic with both write modes")
    if len(notifiers) != 1:
        raise ConnectionError("Expected one Langjue notification characteristic")
    return writers[0], notifiers[0]


class LangjueController(BedController):
    """Bind every write, reply and release to the session that owns it."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._link: _Link | None = None
        data = coordinator.entry.data
        self._head_foot = data.get(CONF_PRODUCT_TYPE) == app.HEAD_FOOT
        self._has_light = data.get(CONF_HAS_LIGHT) is True
        self._has_massage = data.get(CONF_HAS_MASSAGE) is True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        link = self._live(motion=True)
        if self._head_foot and link.motor_count != 2:
            raise ValueError("Linked control requires a matching live two-motor layout")

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.writer.uuid if self._link is not None else ""

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        """Report the raw massage status for the current connection."""
        link = self._link
        if link is None or not self._is_current(link) or link.massage_status_code is None:
            return {}
        return {"massage_status_code": link.massage_status_code}

    def _is_current(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _live(self, *, motion: bool = False) -> _Link:
        link = self._link
        if link is None or not self._is_current(link):
            raise ConnectionError("Langjue bed is disconnected")
        if motion and (
            not link.motor_count
            or link.motor_count + 6 > link.writer.max_write_without_response_size
        ):
            raise ConnectionError("The bed has not reported a usable motor count for STOP")
        return link

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Langjue bed is disconnected")
        if self._link is not None and self._is_current(self._link):
            return
        writer, notify = resolve_gatt(client)
        link = self._link = _Link(client, writer, notify)
        try:
            await client.start_notify(notify, partial(self._notification, link))
        except BaseException:
            if self._link is link:
                self.on_disconnect()
            raise
        await asyncio.sleep(app.HANDSHAKE_DELAY_MS / 1000)
        startup = asyncio.Event()
        try:
            handshake = await self._query(
                link, Op.HANDSHAKE, codec.handshake(), startup, setup=True
            )
            count = handshake.decimal_value
            if count and count + 6 <= link.writer.max_write_without_response_size:
                link.motor_count = count
            for op in (Op.VERSION, Op.RELEASE_DATE):
                await self._query(link, op, codec.frame(op), startup, setup=True)
            await self._send(
                link, codec.frame(Op.READ_LIGHT, 8), startup, response=True, setup=True
            )
        except _ReplyMissing:
            # A missing reply ends this sequence. Axis and preset moves still
            # require a usable 81 reply on this link so STOP can be encoded.
            pass

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and self.client is link.client and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            massage_intensity("head")(None),
            massage_intensity("foot")(None),
            MASSAGE_TIMER_MINUTES(None),
            ALARM_ENABLED(None),
        )

    def _notification(self, link: _Link, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        if not self._is_current(link) or sender.handle != link.notify.handle:
            return
        raw = bytes(data)
        self.forward_raw_notification(sender.uuid, raw)
        msg = codec.notification(raw)
        if msg is None:
            return
        if (
            (reply := link.reply) is not None
            and reply[0] is msg.op
            and not reply[1].done()
            and (msg.op is not Op.HANDSHAKE or msg.payload)
        ):
            reply[1].set_result(msg)
        if msg.op in (Op.LIGHT, Op.READ_LIGHT) and self._has_light and msg.payload:
            light = {1: True, 2: False}.get(msg.payload[0])
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(light))
        elif msg.op is Op.READ_ALARM:
            if len(msg.payload) == 8 and msg.payload[1] in (0, 1):
                link.alarm_payload = msg.payload
                self.forward_controller_state_updates(ALARM_ENABLED(bool(msg.payload[1])))
            else:
                link.alarm_payload = None
                self.forward_controller_state_updates(ALARM_ENABLED(None))
        elif self._has_massage:
            if (level := msg.massage_level) is not None and level[1] in range(4):
                self.forward_controller_state_updates(massage_intensity(level[0])(level[1]))
            elif msg.op is Op.READ_MASSAGE_TIME:
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(msg.decimal_value))
            elif msg.op is Op.READ_MASSAGE_STATE and msg.payload:
                link.massage_status_code = msg.payload[0]

    async def _query(
        self,
        link: _Link,
        op: Op,
        command: bytes,
        event: asyncio.Event,
        *,
        setup: bool = False,
    ) -> codec.Notification:
        if link.reply is not None:
            raise RuntimeError("A Langjue reply is already pending")
        reply = asyncio.get_running_loop().create_future()
        link.reply = (op, reply)
        try:
            await self._send(link, command, event, response=True, setup=setup)
            try:
                async with asyncio.timeout(_REPLY_TIMEOUT):
                    return await reply
            except TimeoutError as exc:
                raise _ReplyMissing(f"No Langjue reply for opcode {op:02x}") from exc
        finally:
            link.reply = None
            reply.cancel()

    async def _send(
        self,
        link: _Link,
        command: bytes,
        event: asyncio.Event,
        *,
        response: bool = False,
        setup: bool = False,
        repeat_count: int = 1,
        repeat_delay_ms: int = 0,
        command_factory: Callable[[], bytes] | None = None,
    ) -> None:
        def require_current() -> None:
            if not self._is_current(link):
                raise ConnectionError("Langjue command belongs to a previous connection")
            if not response and len(command) > link.writer.max_write_without_response_size:
                raise ValueError("Langjue quick command exceeds the negotiated write size")

        await self._write_gatt_with_retry(
            link.writer.uuid,
            command,
            characteristic=link.writer,
            expected_client=link.client,
            response=response,
            cancel_event=event,
            before_write=require_current,
            track_command_write=not setup,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            command_factory=command_factory,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._send(
            self._live(),
            command,
            cancel_event or self._coordinator.cancel_command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
        )

    @property
    def supports_motor_control(self) -> bool:
        return self._head_foot

    @property
    def execution(self) -> ExecutionCapabilities:
        return STREAM_HOLD if self._head_foot else NO_EXECUTION_CAPABILITIES

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self._head_foot:
            return ()
        return tuple(
            replace(
                spec,
                hold=ControllerMotorHoldSpec(
                    f"{spec.key}_up",
                    f"{spec.key}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            )
            for spec in super().motor_control_specs[:2]
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(app.DIRECTIONS) if self._head_foot else ()

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 30_000:
            raise ValueError(
                "Choose a confirmed Langjue direction and hold it for up to 30 seconds"
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, up = app.DIRECTIONS[control]
        await self._move(axis, up=up, duration_ms=self.leased_hold_ms(duration_ms))

    async def _send_motion_frame(
        self,
        link: _Link,
        frame: bytes,
        event: asyncio.Event,
        on_submit: Callable[[], None],
        *,
        caller_is_cancelling: Callable[[], bool],
        deadline: float | None = None,
    ) -> bool:
        """Wait cancellably for admission and settle only the submitted write."""
        admitted = False

        async def write() -> None:
            self._record_command_trace(
                link.writer.uuid, frame, response=False, characteristic=link.writer
            )
            await link.client.write_gatt_char(link.writer, frame, response=False)
            note_frame_written(event)

        try:
            async with self._ble_lock:
                now = asyncio.get_running_loop().time()
                context = current_command_context()
                lease_deadline = context.hold_deadline if context is not None else None
                scheduler_caller = context.caller_is_cancelling if context is not None else None
                if (
                    event.is_set()
                    or caller_is_cancelling()
                    or (scheduler_caller is not None and scheduler_caller())
                    or (deadline is not None and now >= deadline)
                    or (lease_deadline is not None and now >= lease_deadline)
                ):
                    note_frame_skipped()
                    return False
                if not self._is_current(link):
                    raise ConnectionError("Langjue command belongs to a previous connection")
                if (
                    max(len(frame), link.motor_count + 6)
                    > link.writer.max_write_without_response_size
                ):
                    raise ValueError(
                        "Langjue quick command or STOP exceeds the negotiated write size"
                    )
                admitted = True
                on_submit()
                await settled(write(), eager_start=True)
        except asyncio.CancelledError:
            if not admitted:
                note_frame_skipped()
            raise
        return True

    async def _move(self, axis: int, *, up: bool, duration_ms: int | None = None) -> None:
        link = self._live(motion=True)
        if not self._head_foot or link.motor_count != 2:
            raise ValueError("Directional control requires the confirmed two-motor layout")
        event = self._coordinator.cancel_command
        if event.is_set():
            note_frame_skipped()
            return
        frame = codec.motion(link.motor_count, axis, up=up)
        interval_ms = app.MOTOR_REFRESH_MS
        loop = asyncio.get_running_loop()
        if duration_ms is None:
            duration_ms = self.motor_pulse_settings()[0] * interval_ms
        deadline = loop.time() + duration_ms / 1000
        caller_is_cancelling = capture_caller_cancellation()
        submitted = False

        def on_submit() -> None:
            nonlocal submitted
            if not submitted:
                self._bind_paired_abort_stop(link)
            submitted = True

        async def release() -> None:
            if submitted:
                await self._release(link)

        async with self.releasing(release):
            timeout = asyncio.timeout_at(deadline)
            try:
                async with timeout:
                    while not event.is_set():
                        until = min(deadline, loop.time() + interval_ms / 1000)
                        if not await cancellable(
                            self._send_motion_frame(
                                link,
                                frame,
                                event,
                                on_submit,
                                deadline=deadline,
                                caller_is_cancelling=caller_is_cancelling,
                            ),
                            event,
                        ):
                            break
                        if (remaining := until - loop.time()) > 0:
                            with suppress(TimeoutError):
                                async with asyncio.timeout(remaining):
                                    await event.wait()
            except TimeoutError:
                if not timeout.expired():
                    raise

    async def _release(self, link: _Link) -> None:
        if not self._is_current(link):
            raise ConnectionError("Langjue disconnected before STOP could be sent")
        await self._send(link, codec.motion(link.motor_count), asyncio.Event())
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            link.cleanup_context = context

    def _bind_paired_abort_stop(self, link: _Link) -> None:
        context = current_command_context()
        if context is None or context.group_id is None:
            return

        async def stop_on_original(operation: CommandContext) -> None:
            if not operation.cleanup_stop_sent and self._is_current(link):
                await self._release(link)

        context.paired_abort_stop = stop_on_original

    async def stop_all(self) -> None:
        link = self._live(motion=True)
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted is link.cleanup_context and preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await settled(self._release(link))

    async def move_head_up(self) -> None:
        await self._move(0, up=True)

    async def move_head_down(self) -> None:
        await self._move(0, up=False)

    async def move_feet_up(self) -> None:
        await self._move(1, up=True)

    async def move_feet_down(self) -> None:
        await self._move(1, up=False)

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def _preset(self, mode: int) -> None:
        link = self._live(motion=True)
        event = self._coordinator.cancel_command
        if event.is_set():
            note_frame_skipped()
            return
        submitted = False

        def on_submit() -> None:
            nonlocal submitted
            self._bind_paired_abort_stop(link)
            submitted = True

        completed = False

        async def release() -> None:
            if submitted and not completed:
                await self._release(link)

        # A successful tap is one shot. An interrupted or failed submitted
        # write may already have started the bed.
        async with self.releasing(release):
            await cancellable(
                self._send_motion_frame(
                    link,
                    codec.preset(mode),
                    event,
                    on_submit,
                    caller_is_cancelling=capture_caller_cancellation(),
                ),
                event,
            )
            completed = True

    async def preset_flat(self) -> None:
        await self._preset(app.PRESETS["flat"])

    async def preset_zero_g(self) -> None:
        await self._preset(app.PRESETS["zero_g"])

    async def preset_reading(self) -> None:
        await self._preset(app.PRESETS["reading"])

    async def preset_anti_snore(self) -> None:
        await self._preset(app.PRESETS["anti_snore"])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._preset(app.MEMORY_MODES[memory_num - 1])

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.write_command(codec.preset(app.MEMORY_MODES[memory_num - 1], save=True))

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
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
        return len(app.MEMORY_MODES)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        presets = tuple(
            ControllerButtonSpec(
                f"langjue_{key}",
                name,
                lambda ctrl, mode=app.PRESETS[key]: cast(LangjueController, ctrl)._preset(mode),
                translation_key=PRESET_KEY,
                translation_placeholders={"preset": name},
                card=CARD_PRESETS,
                invalidates_position=True,
            )
            for key, name in app.EXTRA_PRESETS.items()
        )
        if not self._has_massage:
            return presets
        return (
            *presets,
            massage_button(
                "langjue_massage_start",
                "Start massage",
                lambda ctrl: cast(LangjueController, ctrl)._massage_sequence(app.MASSAGE_START),
            ),
            *(
                massage_button(
                    f"langjue_massage_pattern_{pattern}",
                    f"Massage Type {pattern}",
                    lambda ctrl, value=pattern: cast(LangjueController, ctrl)._set_massage(
                        "pattern", value
                    ),
                )
                for pattern in app.MASSAGE_PATTERNS
            ),
            massage_button(
                "langjue_massage_refresh",
                "Refresh massage state",
                lambda ctrl: cast(LangjueController, ctrl)._read_massage(),
                diagnostic=True,
            ),
        )

    @property
    def supports_lights(self) -> bool:
        return self._has_light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._has_light

    @property
    def supports_light_state_feedback(self) -> bool:
        return self._has_light

    @property
    def reads_light_state_on_connect(self) -> bool:
        return self._has_light

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def _light(self, enabled: bool) -> None:
        if not self._has_light:
            raise ValueError("Enable light controls for this bed in Configure")
        await self.write_command(codec.light(enabled))

    @property
    def supports_massage(self) -> bool:
        return self._has_massage

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self._has_massage

    @property
    def supports_massage_timer(self) -> bool:
        return self._has_massage

    @property
    def reports_massage_state(self) -> bool:
        return self._has_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self._has_massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        return list(app.MASSAGE_ZONES) if self._has_massage else []

    @property
    def massage_intensity_max(self) -> int:
        return 3

    @property
    def massage_timer_options(self) -> list[int]:
        return list(app.MASSAGE_TIMERS)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def _standard(self, frame: bytes) -> None:
        await self._send(self._live(), frame, self._coordinator.cancel_command, response=True)

    def _massage_frame(self, setting: str, value: int) -> bytes:
        if not self._has_massage:
            raise ValueError("Enable massage controls for this bed in Configure")
        if setting in app.MASSAGE_ZONES:
            return codec.massage_level(app.MASSAGE_ZONES[setting], value)
        if setting == "timer" and value in app.MASSAGE_TIMERS:
            return codec.frame(Op.MASSAGE_TIMER, 2, bytes((0, app.MASSAGE_TIMERS[value])))
        if setting == "pattern" and value in app.MASSAGE_PATTERNS:
            return codec.frame(Op.MASSAGE_PATTERN, 2, bytes((0, value)))
        raise ValueError("Unknown Langjue massage setting or value")

    async def _set_massage(self, setting: str, value: int) -> None:
        await self._standard(self._massage_frame(setting, value))

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in app.MASSAGE_ZONES:
            raise ValueError("Choose the head or foot massage zone")
        await self._set_massage(zone, level)

    async def set_massage_timer(self, minutes: int) -> None:
        await self._set_massage("timer", minutes)

    async def _massage_sequence(
        self, steps: tuple[tuple[int, app.MassageSetting, int], ...]
    ) -> None:
        link = self._live()
        event = self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        start = loop.time()
        for offset_ms, setting, value in steps:
            if (delay := start + offset_ms / 1000 - loop.time()) > 0:
                await asyncio.sleep(delay)
            if event.is_set():
                break
            await self._send(link, self._massage_frame(setting, value), event, response=True)

    async def massage_off(self) -> None:
        await self._massage_sequence(app.MASSAGE_STOP)

    async def _read_massage(self) -> None:
        if not self._has_massage:
            raise ValueError("Enable massage controls for this bed in Configure")
        link = self._live()
        event = self._coordinator.cancel_command
        for op in (Op.READ_MASSAGE_TIME, Op.READ_MASSAGE_STATE):
            await self._send(link, codec.frame(op), event, response=True)
        for zone in app.MASSAGE_ZONES.values():
            frame = codec.frame(Op.READ_MASSAGE_LEVEL, 1, bytes((zone,)))
            await self._send(link, frame, event, response=True)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=tuple(app.ALARM_ACTIONS),
            weekdays=True,
            requires_wake_action=True,
            live_check=True,
        )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        link = self._live(motion=alarm.enabled)
        link.checked_alarm = None
        if not alarm.enabled:
            reply = await self._query(
                link, Op.READ_ALARM, _READ_ALARM, self._coordinator.cancel_command, setup=True
            )
            try:
                codec.alarm_enabled(reply.payload, False)
            except ValueError as err:
                raise rejected(err) from err
        if not self._is_current(link):
            raise invalid("bed_changed")
        link.checked_alarm = alarm

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.enabled:
            self._alarm_frame(alarm)

    @staticmethod
    def _alarm_frame(alarm: AlarmRequest) -> bytes:
        action = app.ALARM_ACTIONS.get(alarm.wake_action, 0)
        return codec.alarm(action, alarm.weekdays, alarm.hour, alarm.minute)

    async def sync_clock(self) -> None:
        await self._standard(codec.clock(dt_util.now()))

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        link = self._live(motion=alarm.enabled)

        def encode() -> bytes:
            if link.checked_alarm != alarm:
                raise invalid("bed_changed")
            # Use the latest valid record at dispatch on the checked link.
            # A second read here could fail after another target has changed.
            if alarm.enabled:
                self._live(motion=True)
                return self._alarm_frame(alarm)
            try:
                return codec.alarm_enabled(link.alarm_payload or b"", False)
            except ValueError as err:
                raise rejected(err) from err

        await self._write_alarm(link, encode, self._coordinator.cancel_command)

    async def _set_alarm_enabled(self, enabled: bool) -> None:
        link = self._live(motion=enabled)
        event = self._coordinator.cancel_command

        def encode() -> bytes:
            payload = link.alarm_payload or b""
            try:
                frame = codec.alarm_enabled(payload, enabled)
                if enabled:
                    self._live(motion=True)
                    _, _, mode, action, mask, hour, minute, _ = payload
                    if (
                        mode not in (1, 2)
                        or action not in app.ALARM_ACTIONS.values()
                        or hour not in range(24)
                        or minute not in range(60)
                        or (mask != 0 if mode == 1 else not 1 <= mask <= 0x7F)
                    ):
                        raise ValueError("The bed did not report a programmable alarm")
            except ValueError as err:
                raise rejected(err) from err
            return frame

        await self._query(link, Op.READ_ALARM, _READ_ALARM, event)
        await self._write_alarm(link, encode, event)

    async def _write_alarm(
        self, link: _Link, encode: Callable[[], bytes], event: asyncio.Event
    ) -> None:
        def prepare() -> bytes:
            frame = encode()
            link.checked_alarm = None
            link.alarm_payload = None
            self.forward_controller_state_updates(ALARM_ENABLED(None))
            return frame

        await self._send(link, b"", event, response=True, command_factory=prepare)
        if self._is_current(link) and not event.is_set():
            await self._send(link, _READ_ALARM, event, response=True)

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "langjue_alarm_enabled",
                "langjue_alarm_enabled",
                lambda ctrl, enabled: cast(LangjueController, ctrl)._set_alarm_enabled(enabled),
                state_key=ALARM_ENABLED,
                command_admission=partial(
                    reserve_alarm_receivers, self._coordinator.hass, (self._coordinator.address,)
                ),
            ),
        )
