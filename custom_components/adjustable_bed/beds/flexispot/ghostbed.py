"""GhostBed's current direct-BLE route on the shared 9B/9D carrier."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Final, cast

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import flexispot as codec
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import ghostbed as app
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON
from ..catalog_buttons import catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    PositionNumberSpec,
)
from .controller import LEVELS, MODE, POWER, FlexispotController, _Link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

HOME: Final = StateKey[bool | None]("ghostbed_snore_home")
LEFT: Final = StateKey[bool | None]("ghostbed_snore_left")
SENSITIVITY: Final = StateKey[str | None]("ghostbed_sensitivity")
ANGLE: Final = StateKey[str | None]("ghostbed_angle")
ALARMS: Final = StateKey[str | None]("ghostbed_alarms")
EMPTY: Final = codec.Alarm(0, 0, 0, 0)


class GhostBedController(FlexispotController):
    """Fixed two-axis layout; no physical angles or split-side motor claims."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=app.PROFILE)
        self._raw_status: str | None = None
        self._suspended_link: _Link | None = None
        self._alarms: list[codec.Alarm | None] = [None] * 4
        self._left_open: bool | None = False
        self._left_sensitivity: int | None = 0
        self._left_angle: int | None = 0

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    async def async_discover_capabilities(self) -> None:
        await super().async_discover_capabilities()
        self._clear_published_state()

    def _clear_published_state(self) -> None:
        self._raw_status = None
        self.forward_controller_state_updates(
            HOME(None),
            LEFT(None),
            SENSITIVITY(None),
            ANGLE(None),
            ALARMS(None),
            POWER(None),
            MODE(None),
            MASSAGE_TIMER_MINUTES(None),
            UNDER_BED_LIGHTS_ON(None),
            *(LEVELS[zone](None) for zone in ("upper", "feet")),
        )

    @property
    def refresh_ms(self) -> int:
        return app.REFRESH_MS

    @property
    def release_ms(self) -> int:
        return app.RELEASE_MS

    @property
    def massage_step_ms(self) -> int:
        return app.MASSAGE_STEP_MS

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def mode_options(self) -> tuple[str, ...]:
        return app.MODES

    @property
    def massage_timer_options(self) -> list[int]:
        return list(app.TIMER_OPTIONS)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def restore_notifications_after_cancel(self) -> bool:
        # Retained teardown suspends the exact link. Resume it before subscribing.
        return False

    def _retains(self, link: _Link) -> bool:
        return (
            self._suspended_link is link
            and self._owner.publisher is link.owner
            and self.client is link.client
            and link.client.is_connected
            and self._role(codec.WRITE) is link.write
            and self._role(codec.NOTIFY) is link.notify
        )

    async def async_resume_session(self) -> None:
        link = self._suspended_link
        if link is not None:
            if not self._retains(link):
                raise BedNotConnectedError
            # Ownership is reserved during suspension, never reclaimed here.
            self._link, self._suspended_link = link, None
        await self._settle(asyncio.create_task(self.start_notify()))

    async def _stop_suspended_subscription(self, link: _Link) -> None:
        async with self._owner.subscription_lock:
            if self._retains(link):
                await link.client.stop_notify(link.notify)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._notifying:
            return
        # Subscription can complete after cancellation. Settle it before cleanup;
        # old completions cannot publish into or unsubscribe a replacement link.
        try:
            await self._settle(asyncio.create_task(self._start_subscription(link)))
            self._live(link)
            await self.sync_clock()
        except BaseException:
            if self._current(link):
                with suppress(Exception):
                    await self.stop_notify()
            raise

    async def stop_notify(self) -> None:
        link = self._link
        if link is None:
            return
        if not self._current(link):
            self.on_disconnect()
            return
        notifying = self._notifying
        # Keep the owner token reserved until real disconnect or replacement.
        # An inactive link rejects old callbacks and queued writes via _live().
        self._suspended_link, self._link = link, None
        self._notifying = False
        self._status = None
        self._alarms = [None] * 4
        self._left_open, self._left_sensitivity, self._left_angle = False, 0, 0
        self._clear_published_state()
        if notifying:
            await self._settle(asyncio.create_task(self._stop_suspended_subscription(link)))

    async def preset(self, key: int, *, flat: bool = False, save: bool = False) -> None:
        if (
            type(key) is not int
            or key not in ((2,) if flat else (1, 2, 3, 4) if save else (1, 2, 3, 4, 5))
            or flat
            and save
        ):
            raise invalid("ghostbed_control_unavailable")
        await super().preset(key, flat=flat, save=save)

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in app.TIMER_OPTIONS:
            raise invalid("ghostbed_control_unavailable")
        await super().set_massage_timer(minutes)

    def on_disconnect(self) -> None:
        link = self._link
        suspended, self._suspended_link = self._suspended_link, None
        owns_suspended = suspended is not None and self._owner.publisher is suspended.owner
        owns_state = owns_suspended or link is not None and self._owner.publisher is link.owner
        super().on_disconnect()
        if owns_suspended:
            self._owner.publisher = None
        self._alarms = [None] * 4
        self._raw_status = None
        self._left_open, self._left_sensitivity, self._left_angle = False, 0, 0
        if owns_state:
            self.forward_controller_state_updates(
                HOME(None),
                LEFT(None),
                SENSITIVITY(None),
                ANGLE(None),
                ALARMS(None),
            )

    def _notification(self, link: _Link, data: bytearray) -> None:
        if not self._current(link):
            return
        self.forward_raw_notification(codec.NOTIFY, bytes(data))
        status = codec.parse(bytes(data))
        if status is None:
            return
        # The opcode04 listener has no current-screen consumer. Keep it raw.
        self._raw_status = bytes(data).hex()
        if status.alarms is None:
            return
        self._status = status
        light, bank = data[3] & 15, data[3] >> 4
        if bank in (0, 8):
            start = 0 if bank == 0 else 2
            self._alarms[start : start + 2] = status.alarms
            self._publish_alarms()
        # App UI grace applies only to its settings widgets. HA receives all
        # state immediately; the active peer caches stay at their defaults.
        if status.snore_mask in range(4):
            self._left_open = status.snore_mask in (1, 3)
        if (levels := codec.unpair(status.sensitivities or 0)) is not None:
            self._left_sensitivity = levels[0]
        if (levels := codec.unpair(status.angles or 0)) is not None:
            self._left_angle = levels[0]
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(light == 1 if light in (1, 2) else None),
            MODE(
                app.MODES[status.mode]
                if status.mode is not None and status.mode in range(4)
                else None
            ),
            MASSAGE_TIMER_MINUTES(status.minutes if status.minutes in app.TIMER_OPTIONS else None),
            *(
                LEVELS[zone](value if value in range(7) else None)
                for zone, value in (("upper", status.upper), ("feet", status.feet))
            ),
            HOME(status.snore_mask != 0),
            LEFT(self._left_open),
            SENSITIVITY(
                app.SENSITIVITIES[self._left_sensitivity]
                if self._left_sensitivity is not None
                else None
            ),
            ANGLE(app.ANGLES[self._left_angle] if self._left_angle is not None else None),
        )

    @staticmethod
    def _alarm_label(slot: int, alarm: codec.Alarm | None) -> str:
        if alarm is None:
            return f"{slot}: Unknown"
        if alarm.pattern == 0:
            return f"{slot}: Not set"
        if not 0 <= alarm.hour <= 23 or not 0 <= alarm.minute <= 59:
            return f"{slot}: Unknown"
        days = (
            ", ".join(
                day
                for bit, day in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
                if alarm.flags & (1 << bit)
            )
            or "No repeat days"
        )
        mode = {1: "Basic", 2: "Pro"}.get(alarm.pattern, "Unknown")
        return f"{slot}: {alarm.hour:02}:{alarm.minute:02} · {'On' if alarm.enabled else 'Off'} · {days} · {mode}"

    def _publish_alarms(self) -> None:
        self.forward_controller_state_updates(
            ALARMS("; ".join(self._alarm_label(i, a) for i, a in enumerate(self._alarms, 1)))
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": "ghostbed",
            "raw_status": self._raw_status,
            "status": asdict(self._status) if self._status else None,
            "alarms": [asdict(a) if a else None for a in self._alarms],
            "selected_side": "left",
            "peer_defaults": {"open": False, "sensitivity": 0, "angle": 0},
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "ghostbed_alarms",
                "ghostbed_alarms",
                ALARMS,
                "mdi:alarm",
                card=CARD_UTILITY,
                entity_registry_enabled_default=True,
                entity_category=None,
            ),
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            *super().controller_switch_specs,
            ControllerSwitchSpec(
                "snore_home",
                "ghostbed_snore_home",
                lambda c, on: cast(GhostBedController, c).snore_home(on),
                HOME,
            ),
            ControllerSwitchSpec(
                "snore_left",
                "ghostbed_snore_left",
                lambda c, on: cast(GhostBedController, c).snore_setting("enabled", on),
                LEFT,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            *(
                replace(spec, translation_key="ghostbed_massage_mode")
                for spec in super().controller_select_specs
            ),
            ControllerSelectSpec(
                "snore_sensitivity",
                "ghostbed_sensitivity",
                SENSITIVITY,
                app.SENSITIVITIES,
                lambda c, value: cast(GhostBedController, c).snore_setting("sensitivity", value),
            ),
            ControllerSelectSpec(
                "snore_angle",
                "ghostbed_angle",
                ANGLE,
                app.ANGLES,
                lambda c, value: cast(GhostBedController, c).snore_setting("angle", value),
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(
            ControllerNumberSpec(
                f"{zone}_massage",
                f"ghostbed_{zone}_massage",
                LEVELS[zone],
                0,
                6,
                1,
                lambda c, value, zone=zone: cast(GhostBedController, c).set_level(zone, value),
                card=CARD_MASSAGE,
            )
            for zone in ("upper", "feet")
        )

    async def set_level(self, zone: str, value: float) -> None:
        if (
            isinstance(value, bool)
            or zone not in ("upper", "feet")
            or not float(value).is_integer()
            or not 0 <= value <= 6
        ):
            raise invalid("ghostbed_control_unavailable")
        snapshot = self._status
        current = getattr(snapshot, zone, None)
        if current is None or current not in range(7):
            raise invalid("ghostbed_status_required")
        link, event = self._live(), self._coordinator.cancel_command
        started = asyncio.get_running_loop().time()
        opcode = (
            (17 if value > current else 13) if zone == "feet" else (12 if value > current else 18)
        )
        for index in range(1, abs(int(value) - current) + 1):
            await self._wait(
                event,
                max(
                    0,
                    started
                    + index * self.massage_step_ms / 1000
                    - asyncio.get_running_loop().time(),
                ),
            )

            def consume(index: int = index) -> None:
                if index == 1 and self._status is not snapshot:
                    raise invalid("ghostbed_status_required")
                self._forget_level(zone)
                self.forward_controller_state_updates(LEVELS[zone](None))

            await self._send(link, codec.frame(opcode), event, submitted=consume)

    def _snore_values(self) -> tuple[int, int]:
        status = self._status
        if status is None or status.angles is None or status.sensitivities is None:
            raise invalid("ghostbed_status_required")
        # Raw invalid pair codes are preserved by the app's home toggle.
        return status.angles, status.sensitivities

    def _invalidate_snore(self) -> None:
        if self._status is not None:
            self._status = replace(self._status, angles=None, sensitivities=None)
        self.forward_controller_state_updates(
            HOME(None), LEFT(None), SENSITIVITY(None), ANGLE(None)
        )

    def _consume_snore(self, snapshot: codec.Status | None) -> None:
        if snapshot is not self._status:
            raise invalid("ghostbed_status_required")
        self._invalidate_snore()

    async def snore_home(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise invalid("ghostbed_control_unavailable")
        angle, sensitivity = self._snore_values()
        snapshot = self._status
        await self._send(
            self._live(),
            codec.snore(int(enabled), angle, sensitivity),
            self._coordinator.cancel_command,
            submitted=lambda: self._consume_snore(snapshot),
        )

    async def snore_setting(self, kind: str, value: str | bool) -> None:
        angle, sensitivity = self._snore_values()
        snapshot = self._status
        if kind == "enabled" and type(value) is bool:
            enabled = value
        elif kind in ("sensitivity", "angle"):
            choices = app.SENSITIVITIES if kind == "sensitivity" else app.ANGLES
            if not isinstance(value, str) or value not in choices or self._left_open is None:
                raise invalid("ghostbed_control_unavailable")
            enabled = self._left_open
            pair = codec.pair(choices.index(value), 0)  # Active peer cache stays default0.
            if kind == "sensitivity":
                sensitivity = pair
            else:
                angle = pair
        else:
            raise invalid("ghostbed_control_unavailable")
        await self._send(
            self._live(),
            codec.snore(int(enabled), angle, sensitivity),
            self._coordinator.cancel_command,
            submitted=lambda: self._consume_snore(snapshot),
        )

    async def sync_clock(self) -> None:
        now = dt_util.now()
        await self.write_command(
            codec.frame(0x34, 3, {4: now.hour, 5: now.minute, 6: now.second, 7: now.isoweekday()})
        )

    def _all_alarms(self) -> tuple[codec.Alarm, ...]:
        if any(
            a is None
            or not 0 <= a.hour <= 23
            or not 0 <= a.minute <= 59
            or a.pattern not in (0, 1, 2)
            for a in self._alarms
        ):
            raise invalid("ghostbed_status_required")
        return tuple(cast(codec.Alarm, a) for a in self._alarms)

    def _invalidate_alarms(self) -> None:
        self._alarms = [None] * 4
        self._publish_alarms()

    def _consume_alarms(self, snapshot: tuple[codec.Alarm, ...]) -> None:
        if tuple(self._alarms) != snapshot:
            raise invalid("ghostbed_status_required")
        self._invalidate_alarms()

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            slots=4,
            weekdays=True,
            wake_actions=("wake_mode_1", "wake_mode_2"),
            live_check=True,
            requires_slot=True,
        )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if (
            type(alarm.enabled) is not bool
            or type(alarm.slot) is not int
            or alarm.slot not in range(1, 5)
        ):
            raise invalid("ghostbed_control_unavailable")
        slots = self._all_alarms()
        if not alarm.enabled and not alarm.time_provided:
            return
        if (
            type(alarm.hour) is not int
            or type(alarm.minute) is not int
            or not 0 <= alarm.hour <= 23
            or not 0 <= alarm.minute <= 59
            or alarm.wake_action not in ("wake_mode_1", "wake_mode_2")
            or not alarm.weekdays
        ):
            raise invalid("ghostbed_control_unavailable")
        flags = codec.flags(alarm.enabled, alarm.weekdays)
        for i, other in enumerate(slots, 1):
            if (
                i != alarm.slot
                and other.pattern != 0
                and flags & other.flags & 0x7F
                and abs(alarm.hour * 60 + alarm.minute - other.hour * 60 - other.minute) <= 30
            ):
                raise invalid("ghostbed_alarm_overlap")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        snapshot = self._all_alarms()
        slots = list(snapshot)
        index = alarm.slot - 1
        slots[index] = (
            codec.Alarm(
                alarm.hour,
                alarm.minute,
                codec.flags(alarm.enabled, alarm.weekdays),
                2 if alarm.wake_action == "wake_mode_2" else 1,
            )
            if alarm.enabled or alarm.time_provided
            else replace(slots[index], flags=slots[index].flags & 0x7F)
        )
        start = 0 if index < 2 else 2
        packet = codec.alarm(
            (slots[start], slots[start + 1]),
            alarm.slot if start == 0 else 4,
            1 if start == 0 else 0x34,
        )
        await self._send(
            self._live(),
            packet,
            self._coordinator.cancel_command,
            submitted=lambda: self._consume_alarms(snapshot),
        )

    async def delete_alarm(self, slot: int) -> None:
        if type(slot) is not int or slot not in range(1, 5):
            raise invalid("ghostbed_control_unavailable")
        slots = self._all_alarms()
        survivors = [a for i, a in enumerate(slots, 1) if i != slot and a.pattern != 0]
        survivors += [EMPTY] * (4 - len(survivors))
        # Prebuild both full records before the first write. A partial batch
        # stays unknown until new bank reports arrive; no optimistic rollback.
        first = codec.alarm((survivors[0], survivors[1]), 1, 1)
        second = codec.alarm((survivors[2], survivors[3]), 4, 0x34)
        link, event = self._live(), self._coordinator.cancel_command
        await self._send(link, first, event, submitted=lambda: self._consume_alarms(slots))
        await self._wait(event, app.ALARM_DELETE_GAP_MS / 1000)
        await self._send(link, second, event, submitted=self._invalidate_alarms)

    async def restore(self) -> None:
        link = self._live()

        def forget() -> None:
            self._forget_status()
            self._raw_status = None
            self._invalidate_alarms()
            self._left_open = self._left_sensitivity = self._left_angle = None
            self.forward_controller_state_updates(
                HOME(None),
                LEFT(None),
                SENSITIVITY(None),
                ANGLE(None),
                POWER(None),
                MODE(None),
                MASSAGE_TIMER_MINUTES(None),
                UNDER_BED_LIGHTS_ON(None),
                *(LEVELS[zone](None) for zone in ("upper", "feet")),
            )

        await self._send(
            link, codec.frame(5, 10), self._coordinator.cancel_command, submitted=forget
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return unique_buttons(
            (
                *super().controller_button_specs,
                *(
                    catalog_button(
                        f"delete_alarm_{slot}",
                        f"Delete alarm {slot}",
                        lambda c, slot=slot: cast(GhostBedController, c).delete_alarm(slot),
                        requires_confirmation=True,
                    )
                    for slot in range(1, 5)
                ),
            )
        )
