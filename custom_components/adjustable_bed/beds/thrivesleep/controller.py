"""Thrive Sleep's current product controls on one admitted physical BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_LIGHTING
from ...codec import richmat as codec
from ...command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
    note_frame_written,
    note_write_not_counted,
)
from ...const import CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...profiles.thrivesleep import (
    ACTIONS,
    DIRECTIONS,
    MASSAGE_TIMERS,
    PROFILES,
    ROUTES,
    STARTUP,
    STARTUP_DELAY_S,
    THERAPY,
    TICK_S,
    ThriveSleepProfile,
)
from ...state_keys import MASSAGE_TIMER_MINUTES
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from .receive import Receiver, decode

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator

PRODUCT: Final = StateKey[str]("thrivesleep_product")
ALARMS: Final = StateKey[list[dict[str, int]]]("thrivesleep_alarms")
LIGHT_SECONDS: Final = StateKey[int | None]("thrivesleep_light_seconds")
ANTI_SNORE: Final = StateKey[bool | None]("thrivesleep_anti_snore")
WAKE_ACTIONS: Final = {
    "anti_snore": "anti_snoring",
    "zero_g": "zero_gravity",
    "tv": "t_v_position",
    "lounge": "lounge_position",
    **{f"memory_{i}": f"memory_position{i}" for i in range(1, 4)},
}


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    raw: bool
    owner: AdjustableBedCoordinator
    product: ThriveSleepProfile


def select_link(
    client: BleakClient, owner: AdjustableBedCoordinator, product: ThriveSleepProfile
) -> Link:
    """Reject mixed services rather than replay order-dependent app encoding on unknown hardware."""
    routes = {codec.TRANSPORTS[key].service_uuid.lower(): codec.TRANSPORTS[key] for key in ROUTES}
    accepted = [s for s in client.services if s.uuid.lower() in routes]
    if len(accepted) != 1:
        raise ValueError("Thrive Sleep requires exactly one recognized bed service")
    service = accepted[0]
    route = routes[service.uuid.lower()]
    write = next(
        (
            c
            for c in service.characteristics
            if c.uuid.lower() == route.write_uuid.lower() and "write" in c.properties
        ),
        None,
    )
    notify = next((c for c in service.characteristics if "notify" in c.properties), None)
    if write is None or notify is None:
        raise ValueError(
            "Thrive Sleep requires the app's write property and a live notification channel"
        )
    return Link(client, write, notify, route.single, owner, product)


class ThriveSleepController(ProfileExecution[ThriveSleepProfile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator)
        if product not in PROFILES:
            raise ValueError("Choose Cool flow, Level 5 or Eco Comfort")
        self.profile = PROFILES[product]
        self._configured_variant = coordinator.entry.data.get(CONF_PROTOCOL_VARIANT)
        self._link: Link | None = None
        self._last_write: float | None = None
        self._receiver = Receiver()
        self.features: set[str] = set()
        self.observations: dict[str, object] = {}
        self.alarms: list[dict[str, int]] = []
        self.sleep_name = ""
        self._snore_requested = False
        self._cleanup_context: CommandContext | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else codec.TRANSPORTS["w1"].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return sum(key.startswith("memory_position") for key in self.profile.actions)

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return "t_v_position" in self.profile.actions

    @property
    def position_number_specs(self) -> tuple[()]:
        return ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in DIRECTIONS if key in self.profile.actions)

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 100

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                key,
                partial(_action, action=axis + "_up"),
                partial(_action, action=axis + "_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    axis + "_up", axis + "_down", press_is_native=True, stop_scope="side"
                ),
            )
            for key, axis in (
                ("back", "head"),
                ("legs", "foot"),
                ("lumbar", "lumber"),
                ("pillow", "pillow"),
                ("motor_3", "motor3"),
            )
            if axis + "_up" in self.profile.actions
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        for key in self.profile.actions:
            if (
                key in DIRECTIONS
                or key in MASSAGE_TIMERS.values()
                or key in ("motor_reset", "zero_gravity", "anti_snoring", "t_v_position")
                or key.startswith("memory_position")
            ):
                continue
            item = ACTIONS[key]
            kind = (
                Kind.MASSAGE
                if key.startswith("massage")
                else Kind.CLIMATE
                if key.startswith("fan")
                else Kind.LIGHT
                if key == "light_board"
                else Kind.PRESET
            )
            if spec := catalog_button(
                "thrivesleep_" + key, item.label, partial(_action, action=key), kind=kind
            ):
                specs.append(spec)
        for key in self.profile.actions:
            item = ACTIONS[key]
            if item.alternate is not None and not key.startswith("memory_position"):
                if spec := catalog_button(
                    "thrivesleep_save_" + key,
                    "Save " + item.label,
                    partial(_action, action=key, alternate=True),
                    kind=Kind.SAVE,
                ):
                    specs.append(spec)
        if self.profile.key == "eco_comfort":
            for option in ("close", *THERAPY):
                specs.append(
                    ControllerButtonSpec(
                        "thrivesleep_therapy_" + option,
                        "Light therapy " + option,
                        partial(_therapy, option=option),
                        card=CARD_LIGHTING,
                        translation_key="catalog_light",
                        translation_placeholders={"action": "Light therapy " + option},
                        scheduler_resource="configuration",
                        cancel_movement=False,
                    )
                )
        specs.append(
            ControllerButtonSpec(
                "thrivesleep_query_alarms",
                "Refresh bed alarms",
                _query_alarms,
                scheduler_resource="configuration",
                cancel_movement=False,
                diagnostic=True,
            )
        )
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            ControllerNumberSpec(
                "thrivesleep_light_seconds",
                "thrivesleep_light_seconds",
                LIGHT_SECONDS,
                0,
                900,
                1,
                _light_timer,
                "s",
                card=CARD_LIGHTING,
            ),
        )

    @property
    def unavailable_controller_entity_keys(self) -> tuple[str, ...]:
        return () if "light" in self.features else ("controller_number_thrivesleep_light_seconds",)

    @property
    def supports_massage_timer(self) -> bool:
        return bool(self.massage_timer_options)

    @property
    def massage_timer_options(self) -> list[int]:
        return [
            minutes for minutes, action in MASSAGE_TIMERS.items() if action in self.profile.actions
        ]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        # Massage all-off remains its own control; it is not a timer setting.
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in self.massage_timer_options:
            raise ValueError("Choose a massage timer this product offers")
        link = self._live()
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes), is_current=lambda: self._current(link)
        ):
            await self.action(MASSAGE_TIMERS[minutes])

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if self.profile.key != "level5":
            return ()
        return (
            ControllerSwitchSpec(
                "thrivesleep_anti_snore",
                "thrivesleep_anti_snore",
                _snore,
                ANTI_SNORE,
                available_fn=lambda c: isinstance(c, ThriveSleepController) and bool(c.sleep_name),
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "thrivesleep",
                "thrivesleep",
                PRODUCT,
                "mdi:bed",
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "observations": dict(self.observations),
            "alarms": [dict(row) for row in self.alarms],
        }

    def _current(self, link: Link) -> bool:
        return (
            self._link is link
            and self._coordinator is link.owner
            and self._coordinator.controller is self
            and self.client is link.client
            and link.client.is_connected
            and self.profile is link.product
            and self._coordinator.entry.data.get(CONF_PROTOCOL_VARIANT) == self._configured_variant
            and self.command_side is None
        )

    def _live(self, link: Link | None = None) -> Link:
        current = link or self._link
        if current is None or not self._current(current):
            raise ConnectionError(
                "Thrive Sleep physical session has ended or its product/side changed"
            )
        return current

    async def _send(
        self,
        link: Link,
        packet: bytes,
        cancel: asyncio.Event,
        *,
        count: bool = True,
        expires_at: float | None = None,
        before_write: Callable[[], None] | None = None,
    ) -> bool:
        submitted = False

        async def transmit() -> bool:
            nonlocal submitted
            response = "write-without-response" not in link.write.properties
            self._record_command_trace(
                link.write.uuid, packet, response=response, characteristic=link.write
            )
            if before_write is not None:
                before_write()
            submitted = True
            await link.client.write_gatt_char(link.write, packet, response=response)
            self._live(link)
            self._last_write = monotonic()
            if count:
                note_frame_written(cancel)
            else:
                note_write_not_counted()
            return True

        async def write() -> bool:
            try:
                async with self._ble_lock:
                    if self._last_write is not None:
                        await cancellable(
                            asyncio.sleep(max(0, self._last_write + TICK_S - monotonic())), cancel
                        )
                    self._live(link)
                    if cancel.is_set() or expires_at is not None and monotonic() > expires_at:
                        if count:
                            note_frame_skipped()
                        return False
                    # Settle only an admitted write; queued user work stays cancellable.
                    return await settled(transmit(), eager_start=True)
            except asyncio.CancelledError:
                if count and not submitted:
                    note_frame_skipped()
                raise

        # Cleanup still owns its complete admission, including a cancelled caller.
        return await write() if count else await settled(write())

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is not None:
            await self.stop_notify()
        else:
            self.on_disconnect()
        client = self.client
        if client is None:
            raise ConnectionError("No Thrive Sleep connection")
        link = self._link = select_link(client, self._coordinator, self.profile)

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if not self._current(link):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for frame in self._receiver.feed(bytes(data)):
                self._accept(frame)

        await client.start_notify(link.notify, receive)
        self._live(link)
        for name, code in STARTUP[:1]:
            await self._send(
                link,
                self.profile.frame(code, raw=link.raw, action=name),
                asyncio.Event(),
                count=False,
            )
        await asyncio.sleep(STARTUP_DELAY_S)
        self._live(link)
        for name, code in STARTUP[1:]:
            await self._send(
                link,
                self.profile.frame(code, raw=link.raw, action=name),
                asyncio.Event(),
                count=False,
            )
        await self._send(
            link,
            codec.calendar(dt_util.now(), build=codec.record_20_len),
            asyncio.Event(),
            count=False,
        )
        if self.profile.key == "level5":
            await self._send(link, codec.record_20_len(6, 3, 0, (0,)), asyncio.Event(), count=False)
        self._publish()

    def _publish(self) -> None:
        self.forward_controller_state_updates(
            PRODUCT(self.profile.label),
            ALARMS([dict(row) for row in self.alarms]),
        )

    def _accept(self, frame: bytes) -> None:
        values = decode(frame)
        self.observations.update(values)
        self.features.update(key for key in ("clock", "light") if values.get(key) is True)
        if "id" in values:
            row = {key: int(value) for key, value in values.items() if isinstance(value, int)}
            index = next((i for i, old in enumerate(self.alarms) if old["id"] == row["id"]), None)
            if frame[5] == 2 and index is None:
                self.alarms.append(row)
            elif index is not None:
                self.alarms[index] = row
        if "sleepAdvName" in values:
            self.sleep_name = str(values["sleepAdvName"])
            if not self.sleep_name:
                self._snore_requested = False
                self.forward_controller_state_updates(ANTI_SNORE(None))
        if "antiSnore" in values and self.profile.key == "level5" and self.sleep_name:
            self.forward_controller_state_updates(ANTI_SNORE(values["antiSnore"] is True))
        self._publish()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._last_write = None
        self._cleanup_context = None
        self._receiver.close()
        self.features.clear()
        self.observations.clear()
        self.alarms.clear()
        self.sleep_name = ""
        self._snore_requested = False
        if self._coordinator.controller is self:
            self.forward_controller_state_updates(
                ALARMS([]),
                LIGHT_SECONDS(None),
                ANTI_SNORE(None),
                MASSAGE_TIMER_MINUTES(None),
            )

    async def read_positions(self, motor_count: int = 2) -> None:
        # No current app angle UI/axis mapping is proven. Only the direct bed
        # setting is queried, once its returned name opens Level 5's gate.
        if self.profile.key == "level5" and self.sleep_name and not self._snore_requested:
            link = self._live()
            if await self._send(
                link, codec.record_20_len(6, 1, 0, (0,)), self._coordinator.cancel_command
            ):
                self._snore_requested = True

    async def action(self, action: str, *, alternate: bool = False) -> None:
        if action not in self.profile.actions or alternate and ACTIONS[action].alternate is None:
            raise ValueError("This Thrive Sleep product does not offer that action")
        if action.startswith("eco_sleep_") and "light" not in self.features:
            raise ValueError("The bed has not confirmed its light therapy capability")
        if action in DIRECTIONS:
            await self.hold_control(
                action, self.leased_hold_ms(self._coordinator.motor_pulse_count * 100)
            )
            return
        link = self._live()
        item = ACTIONS[action]
        code = item.alternate if alternate else item.code
        assert code is not None
        await self._send(
            link, self.profile.frame(code, raw=link.raw), self._coordinator.cancel_command
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Choose a supported Thrive Sleep motor and 1 to 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._live()
        cancel = self._coordinator.cancel_command
        started = monotonic()
        hold_ms = self.leased_hold_ms(duration_ms)
        deadline = started + hold_ms / 1000
        tick = 1
        next_tick = started + TICK_S
        context = current_command_context()
        attempted = False

        def mark_attempted() -> None:
            nonlocal attempted
            attempted = True

        try:
            while True:
                try:
                    await _pause(max(0, min(next_tick, deadline) - monotonic()), cancel)
                except asyncio.CancelledError:
                    if not attempted:
                        note_frame_skipped()  # The intended first motion frame was held back.
                    raise
                if tick * 100 > hold_ms:
                    break
                expires_at = deadline + (0.005 if tick * 100 == hold_ms else 0)
                if cancel.is_set() or monotonic() > expires_at:
                    note_frame_skipped()
                    break
                self._live(link)
                if not await self._send(
                    link,
                    self.profile.frame(ACTIONS[control].code, raw=link.raw),
                    cancel,
                    before_write=mark_attempted,
                    expires_at=expires_at,
                ):
                    break
                # Stay on the source's periodic cadence. A slow write never
                # builds a backlog of old ticks to replay on the radio.
                tick = max(tick + 1, int((monotonic() - started) / TICK_S) + 1)
                next_tick = started + tick * TICK_S
        finally:
            if attempted and self._current(link):
                await self._send(
                    link, self.profile.frame(codec.STOP, raw=link.raw), asyncio.Event(), count=False
                )
                if context is not None:
                    context.cleanup_stop_sent = True
                    self._cleanup_context = context

    async def stop_all(self) -> None:
        """A scheduler STOP cancels/drains its owner; local STOP never cancels a pair."""
        link = self._live()
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted is self._cleanup_context and preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    self._cleanup_context = None
                    return
        await self._send(
            link, self.profile.frame(codec.STOP, raw=link.raw), asyncio.Event(), count=False
        )

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = move_lumbar_stop = stop_all

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

    async def move_lumbar_up(self) -> None:
        await self.action("lumber_up")

    async def move_lumbar_down(self) -> None:
        await self.action("lumber_down")

    async def preset_flat(self) -> None:
        await self.action("motor_reset")

    async def preset_zero_g(self) -> None:
        await self.action("zero_gravity")

    async def preset_anti_snore(self) -> None:
        await self.action("anti_snoring")

    async def preset_tv(self) -> None:
        await self.action("t_v_position")

    def validate_memory_recall(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Choose a memory offered by this Thrive Sleep product")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_position{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.action(f"memory_position{memory_num}", alternate=True)

    def validate_light(self) -> None:
        self._live()
        if "light" not in self.features:
            raise ValueError("The bed has not confirmed its light capability")

    async def light_timer(self, seconds: int) -> None:
        self.validate_light()
        if type(seconds) is not int or not 0 <= seconds <= 900:
            raise ValueError("Choose 0 to 900 seconds; zero keeps the light on")
        link = self._live()
        value = seconds or 65535
        with self.sent_state(LIGHT_SECONDS(seconds), is_current=lambda: self._current(link)):
            await self._send(
                link, codec.light_timer(value >> 8, value & 255), self._coordinator.cancel_command
            )

    async def light_rgb(self, rgb: tuple[int, int, int]) -> None:
        self.validate_light()
        if len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb):
            raise ValueError("Supply three integer RGB channels, 0 to 255")
        await self._send(self._live(), codec.rgb(*rgb), self._coordinator.cancel_command)

    async def therapy(self, option: str) -> None:
        self.validate_light()
        if self.profile.key != "eco_comfort" or option not in ("close", *THERAPY):
            raise ValueError("Choose Eco Comfort light therapy: close, warm, neutral or cool")
        packet = (
            codec.record_20_len(4, 4, 1, (0, 0))
            if option == "close"
            else codec.record_20_len(4, 1, 1, (0, *THERAPY[option]))
        )
        await self._send(self._live(), packet, self._coordinator.cancel_command)

    async def snore(self, enabled: bool) -> None:
        if self.profile.key != "level5" or not self.sleep_name or type(enabled) is not bool:
            raise ValueError("Level 5 anti-snore requires a returned sleep device name")
        await self._send(
            self._live(),
            codec.record_20_len(6, 1, 1, (0, int(enabled))),
            self._coordinator.cancel_command,
        )
        # State changes only on a bed reply, never on enqueue.

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=tuple(k for k, v in WAKE_ACTIONS.items() if v in self.profile.alarms),
            weekdays=True,
            slots=7,
            requires_slot=True,
            requires_wake_action=True,
            live_check=True,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if (
            type(alarm.slot) is not int
            or not 1 <= alarm.slot <= 7
            or type(alarm.enabled) is not bool
            or type(alarm.hour) is not int
            or not 0 <= alarm.hour <= 23
            or type(alarm.minute) is not int
            or not 0 <= alarm.minute <= 59
            or any(type(d) is not int or not 0 <= d <= 6 for d in alarm.weekdays)
            or len(set(alarm.weekdays)) != len(alarm.weekdays)
            or WAKE_ACTIONS.get(alarm.wake_action) not in self.profile.alarms
        ):
            raise ValueError(
                "Choose an app alarm ID 1 to 7, time, weekdays and a mode this product offers"
            )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        self._live()
        if "clock" not in self.features:
            raise ValueError("The bed has not confirmed its alarm capability")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        mode = ACTIONS[WAKE_ACTIONS[alarm.wake_action]].code
        repeat = int(alarm.enabled) | sum(1 << (7 - d) for d in alarm.weekdays)
        await self._send(
            self._live(),
            codec.record_20_len(5, 1, 1, (alarm.slot, 0, alarm.hour, alarm.minute, mode, repeat)),
            self._coordinator.cancel_command,
        )

    async def query_alarms(self) -> None:
        if "clock" not in self.features:
            raise ValueError("The bed has not confirmed its alarm capability")
        link = self._live()
        records = tuple(self.alarms)
        with delivered(partial(self._retire_alarms, link, records)):
            await self._send(
                link, codec.record_20_len(5, 1, 0, (0,)), self._coordinator.cancel_command
            )

    async def delete_alarm(self, number: int) -> None:
        if type(number) is not int or not 1 <= number <= 7 or "clock" not in self.features:
            raise ValueError("Choose an app alarm ID 1 to 7 on an alarm-capable bed")
        link = self._live()
        record = next((row for row in self.alarms if row["id"] == number), None)
        records = () if record is None else (record,)
        with delivered(partial(self._retire_alarms, link, records)):
            await self._send(
                link, codec.record_20_len(5, 2, 1, (number,)), self._coordinator.cancel_command
            )

    def _retire_alarms(
        self, link: Link, records: tuple[dict[str, int], ...], delivery: Delivery
    ) -> None:
        if self._current(link) and delivery is not Delivery.NONE:
            # Newer notifications replace records and outrank this sent refresh/deletion.
            self.alarms = [row for row in self.alarms if all(row is not old for old in records)]
            self._publish()

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        now = dt_util.now()
        await self._send(
            self._live(),
            codec.calendar(now, build=codec.record_20_len),
            self._coordinator.cancel_command,
        )


async def _action(controller: BedController, action: str, *, alternate: bool = False) -> None:
    await require_controller(controller, ThriveSleepController).action(action, alternate=alternate)


async def _therapy(controller: BedController, *, option: str) -> None:
    await require_controller(controller, ThriveSleepController).therapy(option)


async def _query_alarms(controller: BedController) -> None:
    await require_controller(controller, ThriveSleepController).query_alarms()


async def _light_timer(controller: BedController, value: float) -> None:
    if not float(value).is_integer():
        raise ValueError("Choose whole seconds")
    await require_controller(controller, ThriveSleepController).light_timer(int(value))


async def _snore(controller: BedController, enabled: bool) -> None:
    await require_controller(controller, ThriveSleepController).snore(enabled)


async def _pause(seconds: float, cancel: asyncio.Event) -> None:
    await cancellable(asyncio.sleep(seconds), cancel)


async def build_controller(ctx: BuildContext) -> ThriveSleepController:
    return ThriveSleepController(ctx.coordinator, product=ctx.variant or "cool_flow")
