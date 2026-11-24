"""Sinca Comfort Bed controls on the shared two-carrier BLE transport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE
from ...codec import mline as wire
from ...codec import sinca_comfort as codec
from ...command_scheduler import current_command_context, note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME, CONF_PRODUCT_TYPE
from ...controller_state import StateKey, StateUpdate
from ...errors import BedNotConnectedError, failed, invalid
from ...profiles import sinca_comfort as app
from ...state_keys import MASSAGE_ACTIVE, massage_intensity
from ..base import ProfileExecution
from ..builder import BuildContext
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..mline.transport import Link, MLineTransportController

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

PRIVACY: Final = StateKey[bool | None]("sinca_privacy")
ANTI_SNORE: Final = StateKey[bool | None]("sinca_anti_snore")
ANTI_SNORE_LEVEL: Final = StateKey[str | None]("sinca_anti_snore_level")
ALARM_ENABLED: Final = StateKey[bool | None]("sinca_alarm_enabled")
ALARM_TIME: Final = StateKey[str | None]("sinca_alarm_time")
MASSAGE_WAVE: Final = StateKey[int | None]("sinca_massage_wave")
MASSAGE_TIMER: Final = StateKey[int | None]("sinca_massage_timer")


@dataclass(slots=True)
class HistoryTransfer:
    """The receiver buffers only admitted timestamps, never physiological values."""

    idle_at: float
    local_zone: tzinfo
    activity: asyncio.Event = field(default_factory=asyncio.Event)
    timestamps: set[datetime] = field(default_factory=set)
    received: bool = False
    overflow: bool = False
    accepting: bool = True

    def feed(self, notification: bytes) -> None:
        if not self.accepting or self.overflow:
            return
        if (batch := codec.history_timestamps(notification, self.local_zone)) is None:
            return
        self.received = True
        self.timestamps.update(batch)
        self.overflow = len(self.timestamps) > app.HISTORY_RECORD_LIMIT
        self.idle_at = asyncio.get_running_loop().time() + app.HISTORY_IDLE_SECONDS
        self.activity.set()


class SincaComfortController(ProfileExecution[app.SincaProfile], MLineTransportController):
    """A single press followed by release, with independent settings replies."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: app.SincaProfile, layout: str
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self.layout = layout
        self._subscription: object | None = None
        self._replies = wire.Assembler()
        self._firmware: str | None = None
        self._protocol_string: str | None = None
        self._newer_privacy: bool | None = None
        self._pending_privacy: dict[bool, bool] | None = {}
        self._alarm: codec.AlarmState | None = None
        self._history: HistoryTransfer | None = None

    def _link_error(self, reason: Literal["disconnected", "roles"]) -> Exception:
        return (
            BedNotConnectedError("sinca_gatt_roles")
            if reason == "roles"
            else BedNotConnectedError()
        )

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {
            "receiver": self.profile.key,
            "layout": self.layout,
            "firmware": self._firmware,
            "protocol": self._protocol_string,
            "alarm_action": self._alarm.action(self.profile.key) if self._alarm else None,
            "alarm_repeat": self._alarm.repeat if self._alarm else None,
        }

    async def _metadata(self, link: Link, char: BleakGATTCharacteristic | None) -> str | None:
        if char is None or "read" not in char.properties:
            return None
        async with self._ble_lock:
            self._live(link)
            try:
                value = await link.client.read_gatt_char(char)
            except BleakError, TimeoutError:
                return None
            self._live(link)
            try:
                return bytes(value).decode("utf-8")
            except UnicodeDecodeError:
                return None

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await session.async_start_notify()
        firmware = await self._metadata(link, link.firmware)
        protocol_string = await self._metadata(link, link.protocol)
        self._live(link)
        self._firmware, self._protocol_string = firmware, protocol_string
        newer = self._newer_privacy = codec.newer_sensor(protocol_string, firmware)
        pending, self._pending_privacy = self._pending_privacy, None
        if newer is not None and pending is not None and newer in pending:
            self.forward_controller_state_updates(PRIVACY(pending[newer]))
        await asyncio.sleep(app.STARTUP_DELAY_MS / 1000)
        self._live(link)
        await self._sequence(
            link,
            wire.clock(self.profile.key, dt_util.now()),
            count=self.profile.clock_count,
            cancel=asyncio.Event(),
            track=False,
        )
        await self._status(link, asyncio.Event(), track=False)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        async with self._ble_lock:
            self._live(link)
            if self._subscription is not None:
                return
            token = self._subscription = object()
            try:
                await link.client.start_notify(
                    link.notify,
                    lambda sender, data: self._receive(link, token, sender, bytes(data)),
                )
                self._live(link)
            except BaseException:
                if self._subscription is token:
                    self._retire_subscription()
                raise

    async def stop_notify(self) -> None:
        link = self._link
        async with self._ble_lock:
            if link is None or self._link is not link or self._subscription is None:
                return
            self._retire_subscription()
            if self.client is link.client and link.client.is_connected:
                # Pairing setup can cancel this await to restore the retained link.
                await link.client.stop_notify(link.notify)

    def _retire_subscription(self) -> None:
        # The coordinator may restore notifications on the same physical link
        # after a failed disconnect. Retire the callback and fragment only.
        self._subscription = None
        self._replies = wire.Assembler()
        if self._pending_privacy is not None:
            self._pending_privacy.clear()

    def on_disconnect(self) -> None:
        had_link = self._link is not None
        self._link = None
        self._retire_subscription()
        self._firmware = self._protocol_string = None
        self._newer_privacy = None
        self._pending_privacy = {}
        self._alarm = None
        if self._history is not None:
            # Wake the transfer so it fails the link check before any ACK.
            self._history.activity.set()
        if had_link:
            self.forward_controller_state_updates(
                ALARM_ENABLED(None),
                ALARM_TIME(None),
                PRIVACY(None),
                ANTI_SNORE(None),
                ANTI_SNORE_LEVEL(None),
                MASSAGE_WAVE(None),
                MASSAGE_TIMER(None),
                StateUpdate(MASSAGE_ACTIVE, None),
                *(massage_intensity(zone)(None) for zone in ("head", "foot", "all")),
            )

    def _receive(
        self, link: Link, token: object, sender: BleakGATTCharacteristic, raw: bytes
    ) -> None:
        if (
            self._link is not link
            or self._subscription is not token
            or self.client is not link.client
            or not link.client.is_connected
            or sender.handle != link.notify.handle
        ):
            return
        if raw[0:1] != b"\xa6" and self._replies.pending is None:
            self.forward_raw_notification(sender.uuid, raw)
        if (data := self._replies.feed(raw)) is None:
            return
        if data[:2] in codec.HISTORY_HEADERS and self._history is not None:
            self._history.feed(data)
            return
        if (massage := codec.massage(data, self.profile.key)) is not None:
            self.forward_controller_state_updates(
                MASSAGE_ACTIVE(massage.intensity > 0),
                massage_intensity("head")(massage.head),
                massage_intensity("foot")(massage.foot),
                massage_intensity("all")(massage.intensity),
                MASSAGE_WAVE(massage.wave),
                MASSAGE_TIMER(massage.timer),
            )
        if (alarm := codec.alarm(data)) is not None:
            self._alarm = alarm
            time = (
                f"{alarm.hour:02}:{alarm.minute:02}"
                if alarm.enabled and alarm.hour < 24 and alarm.minute < 60
                else None
            )
            self.forward_controller_state_updates(
                ALARM_ENABLED(bool(alarm.enabled)), ALARM_TIME(time)
            )
        if self.profile.key == "sleep":
            if (anti := codec.anti_snore_state(data)) is not None:
                self.forward_controller_state_updates(
                    ANTI_SNORE(anti[0]), ANTI_SNORE_LEVEL(anti[1])
                )
            pending = self._pending_privacy
            if pending is not None:
                # A short status may be complete for legacy but not newer firmware.
                for newer in (False, True):
                    if (privacy := codec.privacy_state(data, newer)) is not None:
                        pending[newer] = privacy
            elif (privacy := codec.privacy_state(data, self._newer_privacy)) is not None:
                self.forward_controller_state_updates(PRIVACY(privacy))

    async def _sequence(
        self,
        link: Link,
        data: bytes,
        *,
        count: int = 1,
        interval_ms: int = 0,
        cancel: asyncio.Event | None = None,
        track: bool = True,
    ) -> None:
        cancel = self._coordinator.cancel_command if cancel is None else cancel
        loop = asyncio.get_running_loop()
        start = loop.time()
        for index in range(count):
            remaining = start + index * interval_ms / 1000 - loop.time()
            if remaining > 0 and await self._pause(remaining, cancel):
                if track:
                    note_frame_skipped()
                return
            await self._write(link, data, cancel, track=track)

    async def _release(self, link: Link, *, delay_ms: int) -> None:
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            return
        await self._write(link, self.profile.control(0), asyncio.Event())
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    async def _press(self, word: int, duration_ms: int = 0, *, massage: bool = False) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            note_frame_skipped()
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000 if duration_ms else None
        released_at = loop.time()

        async def release() -> None:
            nonlocal released_at
            released_at = loop.time()
            await self._release(link, delay_ms=self.profile.release_ms)

        async with self.releasing(release):
            await self._write(link, self.profile.control(word), cancel, deadline)
            if deadline is not None and (remaining := deadline - loop.time()) > 0:
                await self._pause(remaining, cancel)

        if massage and not cancel.is_set():
            remaining = released_at + app.QUERY_MS / 1000 - loop.time()
            if remaining <= 0 or not await self._pause(remaining, cancel):
                await self._status(link, cancel)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}"
            for axis in app.LAYOUTS[self.layout]
            for direction in ("up", "down")
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 60000:
            raise invalid("sinca_hold_invalid")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        axis, direction = control.rsplit("_", 1)
        await self._press(app.MOTORS[axis][direction == "down"], self.leased_hold_ms(duration_ms))

    async def move_axis(self, axis: str, up: bool) -> None:
        await self.hold_control(f"{axis}_{'up' if up else 'down'}", app.MOTION_PRESS_MS)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_legs_up(self) -> None:
        await self.move_axis("legs", True)

    async def move_legs_down(self) -> None:
        await self.move_axis("legs", False)

    async def move_neck_up(self) -> None:
        await self.move_axis("neck", True)

    async def move_neck_down(self) -> None:
        await self.move_axis("neck", False)

    async def move_lumbar_up(self) -> None:
        await self.move_axis("lumbar", True)

    async def move_lumbar_down(self) -> None:
        await self.move_axis("lumbar", False)

    move_head_up = move_back_up
    move_head_down = move_back_down
    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def stop_all(self) -> None:
        if (context := current_command_context()) is not None:
            for preempted in (context, *context.preempted_contexts):
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._release(self._live(), delay_ms=0)

    move_back_stop = move_head_stop = move_legs_stop = move_feet_stop = stop_all
    move_neck_stop = move_lumbar_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                lambda c, a=axis: cast(SincaComfortController, c).move_axis(a, True),
                lambda c, a=axis: cast(SincaComfortController, c).move_axis(a, False),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_is_native=True
                ),
            )
            for axis in app.LAYOUTS[self.layout]
        )

    async def preset_flat(self) -> None:
        await self._press(app.PRESETS["flat"])

    async def preset_reading(self) -> None:
        await self._press(app.PRESETS["reading"])

    async def preset_anti_snore(self) -> None:
        await self._press(app.PRESETS["anti_snore"])

    async def preset_tv(self) -> None:
        await self._press(app.PRESETS["tv"])

    async def preset_zero_g(self) -> None:
        await self._press(app.PRESETS["zero_g"])

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press(app.PRESETS[f"memory_{memory_num}"])

    async def program_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._press(app.PRESETS[f"memory_{memory_num}"], app.MEMORY_SAVE_PRESS_MS)

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
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
    def supports_lights(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self.write_command(self.profile.control(app.LIGHT))

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def reports_massage_state(self) -> bool:
        return True

    async def massage_toggle(self) -> None:
        await self._press(app.MASSAGE["toggle"], app.MASSAGE_TOGGLE_PRESS_MS, massage=True)

    async def massage_mode_step(self) -> None:
        await self._press(app.MASSAGE["wave"], massage=True)

    async def cycle_massage(self, key: str) -> None:
        await self._press(app.MASSAGE[key], massage=True)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        massage = (
            ("head", "Cycle head massage strength"),
            ("foot", "Cycle foot massage strength"),
            ("timer", "Cycle massage timer"),
        )
        buttons = (
            catalog_button(
                f"sinca_massage_{key}",
                label,
                lambda c, k=key: cast(SincaComfortController, c).cycle_massage(k),
                kind=Kind.MASSAGE,
            )
            for key, label in massage
        )
        return (
            *(spec for spec in buttons if spec is not None),
            ControllerButtonSpec(
                "sinca_refresh_settings",
                "Refresh settings",
                lambda c: cast(SincaComfortController, c).settings_refresh(),
                translation_key="sinca_refresh_settings",
                diagnostic=True,
            ),
            ControllerButtonSpec(
                "sinca_refresh_alarm",
                "Refresh alarm",
                lambda c: cast(SincaComfortController, c).alarm_refresh(),
                translation_key="sinca_refresh_alarm",
                diagnostic=True,
            ),
            ControllerButtonSpec(
                "sinca_disable_alarm",
                "Disable alarm",
                lambda c: cast(SincaComfortController, c).disable_alarm(),
                translation_key="sinca_disable_alarm",
                icon="mdi:alarm-off",
                entity_registry_enabled_default=False,
            ),
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if self.profile.key != "sleep":
            return ()
        return (
            ControllerSwitchSpec(
                "sinca_privacy",
                "sinca_privacy",
                lambda c, enabled: cast(SincaComfortController, c).set_privacy(enabled),
                state_key=PRIVACY,
                icon="mdi:eye-off",
                entity_registry_enabled_default=False,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        sensors = (
            ControllerStateSensorSpec(str(ALARM_TIME), str(ALARM_TIME), ALARM_TIME, "mdi:alarm"),
            ControllerStateSensorSpec(
                str(MASSAGE_WAVE),
                str(MASSAGE_WAVE),
                MASSAGE_WAVE,
                "mdi:waves",
                card=CARD_MASSAGE,
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
            ControllerStateSensorSpec(
                str(MASSAGE_TIMER),
                str(MASSAGE_TIMER),
                MASSAGE_TIMER,
                "mdi:timer",
                card=CARD_MASSAGE,
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
        )
        if self.profile.key == "sleep":
            return (
                *sensors,
                ControllerStateSensorSpec(
                    str(ANTI_SNORE_LEVEL), str(ANTI_SNORE_LEVEL), ANTI_SNORE_LEVEL, "mdi:sleep"
                ),
            )
        return sensors

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        alarm = ControllerStateBinarySensorSpec(
            str(ALARM_ENABLED), str(ALARM_ENABLED), ALARM_ENABLED, "mdi:alarm"
        )
        if self.profile.key == "sleep":
            return (
                alarm,
                ControllerStateBinarySensorSpec(
                    str(ANTI_SNORE), str(ANTI_SNORE), ANTI_SNORE, "mdi:sleep"
                ),
            )
        return (alarm,)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self._sequence(
            self._live(),
            wire.clock(self.profile.key, dt_util.now()),
            count=self.profile.clock_count,
        )

    async def _status(self, link: Link, cancel: asyncio.Event, *, track: bool = True) -> None:
        await self._sequence(
            link,
            self.profile.status,
            count=2,
            interval_ms=self.profile.status_repeat_ms,
            cancel=cancel,
            track=track,
        )

    async def settings_refresh(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        await self._write(link, wire.AUXILIARY["checkState"], cancel)
        await self._status(link, cancel)

    async def alarm_refresh(self) -> None:
        await self._query_alarm(self._live(), self._coordinator.cancel_command)

    async def _query_alarm(self, link: Link, cancel: asyncio.Event) -> None:
        await self._sequence(
            link, self.profile.alarm_frame(), count=3, interval_ms=app.QUERY_MS, cancel=cancel
        )

    async def disable_alarm(self) -> None:
        link, cancel = self._live(), self._coordinator.cancel_command
        loop = asyncio.get_running_loop()
        refresh_at = loop.time() + app.QUERY_MS / 1000
        await self._write(link, self.profile.alarm_frame(disable=True), cancel)
        remaining = refresh_at - loop.time()
        if remaining <= 0 or not await self._pause(remaining, cancel):
            await self._query_alarm(link, cancel)

    def require_sleep(self) -> None:
        if self.profile.key != "sleep":
            raise invalid("sinca_sleep_required")

    async def set_privacy(self, enabled: bool) -> None:
        self.require_sleep()
        link, cancel = self._live(), self._coordinator.cancel_command
        command = wire.AUXILIARY["openPrivacyMode" if enabled else "closePrivacyMode"]
        await self._write(link, command, cancel)
        await self._status(link, cancel)

    async def set_anti_snore(self, enabled: bool, position: int, angle: int, *, demo: bool) -> None:
        self.require_sleep()
        link, cancel = self._live(), self._coordinator.cancel_command
        data = (
            wire.anti_snore(enabled, angle, position, demo=demo)
            if demo or not enabled
            else codec.anti_snore(position, angle)
        )
        await self._sequence(link, data, count=2, interval_ms=app.QUERY_MS, cancel=cancel)
        # The refresh is a separate timer starting at the original press.
        if not demo:
            await self._status(link, cancel)

    async def consume_history(self, *, all_records: bool, confirmed: bool) -> tuple[bool, int]:
        """Receive a history transfer and acknowledge only data handled on this link."""
        link, cancel = self._live(), self._coordinator.cancel_command
        if self._history is not None:
            raise invalid("sinca_history_busy")
        loop = asyncio.get_running_loop()
        transfer = HistoryTransfer(
            loop.time() + app.HISTORY_IDLE_SECONDS, dt_util.get_default_time_zone()
        )
        self._history = transfer
        command = wire.AUXILIARY[
            "gainAllHistoricalData" if all_records else "gainNewHistoricalData"
        ]
        cancelled = asyncio.create_task(cancel.wait())
        activity = asyncio.create_task(transfer.activity.wait())
        try:
            async with asyncio.timeout(app.HISTORY_TRANSFER_SECONDS):
                await self._sequence(link, command, count=2, interval_ms=app.HISTORY_REPEAT_MS)
                while True:
                    self._live(link)
                    if cancel.is_set():
                        note_frame_skipped()
                        return False, 0
                    if transfer.overflow:
                        raise failed("sinca_history_limit")
                    remaining = transfer.idle_at - loop.time()
                    if remaining <= 0:
                        break
                    await asyncio.wait(
                        (activity, cancelled),
                        timeout=remaining,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if activity.done():
                        transfer.activity.clear()
                        activity = asyncio.create_task(transfer.activity.wait())
            transfer.accepting = False
            if not transfer.received:
                return False, 0
            # The phone ACKs report-length groups only after an external consumer
            # succeeds. HA only discards them when explicitly asked to do so.
            if not confirmed and codec.history_has_long_group(
                transfer.timestamps, transfer.local_zone
            ):
                raise invalid("sinca_history_confirm")
            await self._sequence(
                link,
                wire.AUXILIARY["confirmGainHistoryData"],
                count=2,
                interval_ms=app.HISTORY_REPEAT_MS,
                cancel=cancel,
            )
            return not cancel.is_set(), len(transfer.timestamps)
        except TimeoutError as err:
            raise failed("sinca_history_timeout") from err
        finally:
            self._history = None
            activity.cancel()
            cancelled.cancel()
            await asyncio.gather(activity, cancelled, return_exceptions=True)


async def build_controller(ctx: BuildContext) -> SincaComfortController:
    name = (
        ctx.live_device_name
        or ctx.advertisement_name
        or str(ctx.data.get(CONF_BLE_DEVICE_NAME, ""))
    )
    if ctx.variant in (None, "auto"):
        profile = app.PROFILES[app.protocol_from_scan(name, ctx.manufacturer_data or {})]
    else:
        profile = next((item for item in app.PROFILES.values() if item.key == ctx.variant), None)
    if profile is None:
        raise invalid("sinca_receiver_invalid")
    layout = str(ctx.data.get(CONF_PRODUCT_TYPE, "two"))
    return SincaComfortController(
        ctx.coordinator, profile, layout if layout in app.LAYOUTS else "unknown"
    )
