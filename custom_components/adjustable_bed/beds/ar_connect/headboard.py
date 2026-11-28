"""Independent headboard light/mood/routine state machine for AR Connect."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_LIGHTING, CARD_UTILITY
from ...codec import ar_connect as codec
from ...controller_state import StateKey, StateUpdate
from ...errors import BedNotConnectedError, invalid
from ...profiles import ar_headboard as app
from ...state_keys import LIGHT_INTENSITY, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGBW
from ..base import require_controller
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from .session import ArSessionController, Link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MOOD_ON = StateKey[bool | None]("ar_headboard_mood_on")
MOOD_DELAY = StateKey[str | None]("ar_headboard_mood_delay")
MOOD_REPEAT = StateKey[bool | None]("ar_headboard_mood_repeat")
STATUS = StateKey[str | None]("ar_headboard_status")
ROUTINE_COUNT = StateKey[int | None]("ar_headboard_routine_count")
ROUTINE_LIST = StateKey[dict[str, object] | None]("ar_headboard_routines")
LAST_CREATED_ROUTINE_ID = StateKey[str | None]("ar_headboard_last_created_routine_id")


class HeadboardController(ArSessionController):
    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.config: int | None = None
        self.version: str | None = None
        self.timeouts: dict[str, int] = {}
        self.colors: tuple[codec.RGBW, ...] | None = None
        self.delay: int | None = None
        self.repeat: bool | None = None
        self.routines: dict[str, codec.Routine] = {}
        self.framer = codec.RoutineFramer()
        self._routine_list_received = asyncio.Event()
        self._rgbw: codec.RGBW | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return app.TRANSPORTS["live_state"][1]

    @property
    def supports_motor_control(self) -> bool:
        return False

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return self.config is not None

    @property
    def supports_light_color_control(self) -> bool:
        return self.config is not None and self.config != 2

    @property
    def supports_lights(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_light_color_control

    @property
    def supported_color_mode(self) -> str | None:
        return "rgbw" if self.supports_light_color_control else None

    @property
    def publishes_rgb_light_state(self) -> bool:
        return True

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return True

    @property
    def reads_light_state_on_connect(self) -> bool:
        return True

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def async_discover_capabilities(self) -> None:
        link = self.bind()
        for key, (service, char) in app.TRANSPORTS.items():
            self.role(link, key, service, char)
        for key in (
            "clock",
            "routine",
            "remove",
            "mood_state",
            "mood_values",
            "live_state",
            "live_values",
        ):
            if "write" not in link.roles[key].properties:
                raise BedNotConnectedError()
        for key in ("version", "config", "advertising", "pairing", *app.INITIAL_READS):
            if "read" not in link.roles[key].properties:
                raise BedNotConnectedError()
        for key in app.NOTIFY_ORDER:
            if not {"notify", "indicate"}.intersection(link.roles[key].properties):
                raise BedNotConnectedError()

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self.link
        if link is None:
            raise BedNotConnectedError()
        link.generation = self._coordinator.connection_generation
        # BLE version is session context only. No excluded firmware/network lookup.
        row = codec.object_record(await self.read(link, "version"))
        if row is None or not isinstance(row.get("version"), str):
            raise invalid("ar_connect_invalid_state")
        self.version = str(row["version"])
        row = codec.object_record(await self.read(link, "config"))
        if row is None:
            raise invalid("ar_connect_invalid_state")
        self.config = codec.integer(row, "config")
        await self.frame(
            link,
            "clock",
            codec.clock(dt_util.now()),
            startup=True,
            response=True,
            cancel=asyncio.Event(),
        )
        for key in ("advertising", "pairing"):
            row = codec.object_record(await self.read(link, key))
            if row is None:
                raise invalid("ar_connect_invalid_state")
            self.timeouts[key] = codec.integer(row, "timeout")
        await session.async_start_notify()
        link.ready = True
        session.persist_capability_snapshot()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self.live(ready=False)
        for key in app.NOTIFY_ORDER:
            await self.subscribe(link, key, lambda data, key=key: self.receive(key, data))
        # FE02 has a parser and initial read, but no enable-notification call.
        for key in app.INITIAL_READS:
            self.receive(key, await self.read(link, key))

    def receive(self, key: str, data: bytes) -> None:
        try:
            self._receive(key, data)
        except ValueError, KeyError, TypeError, UnicodeDecodeError:
            # Reject malformed input without fabricating state or letting a
            # backend callback escape. A future valid record can recover.
            if key == "routine":
                self.framer.clear()
                self._routine_list_received.clear()
                self.forward_controller_state_updates(ROUTINE_COUNT(None), ROUTINE_LIST(None))
            elif key == "mood_state":
                self.forward_controller_state_updates(MOOD_ON(None))
            elif key == "mood_values":
                self.colors = self.delay = self.repeat = None
                self.forward_controller_state_updates(MOOD_DELAY(None), MOOD_REPEAT(None))
            elif key == "status":
                self.forward_controller_state_updates(STATUS(None))
            elif key == "live_state":
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
            elif key == "live_values":
                self._rgbw = None
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_RGBW(None), LIGHT_INTENSITY(None)
                )

    def _receive(self, key: str, data: bytes) -> None:
        if key == "live_values":
            channels = codec.parse_live(data)
            if channels is not None:
                self._rgbw = channels
                # Preserve unbounded wire values in diagnostics, but never send
                # an out-of-range HA color to the frontend.
                if all(0 <= value <= 255 for value in channels):
                    self.forward_controller_state_updates(
                        UNDER_BED_LIGHTS_RGBW(channels), LIGHT_INTENSITY(min(255, sum(channels)))
                    )
            return
        if key == "routine":
            event = self.framer.feed(data)
            if event is not None:
                kind, value = event
                if kind == "list" and isinstance(value, dict):
                    self.routines = {
                        str(k): v for k, v in value.items() if isinstance(v, codec.Routine)
                    }
                    self._routine_list_received.set()
                elif kind == "deleted":
                    self.routines.pop(str(value), None)
                elif kind == "created":
                    # An identity alone provides neither the record's content
                    # nor a complete list. Require fresh list evidence for edits.
                    self._routine_list_received.clear()
                    self.forward_controller_state_updates(
                        LAST_CREATED_ROUTINE_ID(str(value)), ROUTINE_COUNT(None), ROUTINE_LIST(None)
                    )
                    return
                if self._routine_list_received.is_set():
                    self._publish_routines()
            return
        row = codec.object_record(data)
        if row is None:
            return
        if key in ("live_state", "mood_state"):
            field = "livestat" if key == "live_state" else "scenstat"
            value = row[field]
            if type(value) is not bool:
                raise ValueError("Expected Boolean light state")
            self.forward_controller_state_updates(
                (UNDER_BED_LIGHTS_ON if key == "live_state" else MOOD_ON)(value)
            )
        elif key == "status":
            value = row["sysstat"]
            if value not in ("live", "scen", "wake", "sleep", "path", "idle"):
                raise ValueError("Unknown headboard status")
            self._system_status = str(value)
            self.forward_controller_state_updates(STATUS(None if value == "path" else str(value)))
        elif key == "mood_values":
            repeat, delay, colors = row["repeat"], codec.integer(row, "delay"), row["colors"]
            if (
                type(repeat) not in (bool, int)
                or delay not in codec.DURATIONS
                or not isinstance(colors, dict)
            ):
                raise ValueError("Invalid mood state")
            steps: list[codec.RGBW] = []
            for i in range(1, 6):
                color = colors[str(i)]
                if not isinstance(color, dict):
                    raise ValueError("Invalid mood color")
                channels = tuple(
                    codec.integer(dict(color), name) for name in ("red", "green", "blue", "white")
                )
                if len(channels) != 4:
                    raise ValueError("Invalid mood color")
                steps.append((channels[0], channels[1], channels[2], channels[3]))
            self.colors, self.delay, self.repeat = (
                tuple(steps),
                delay,
                repeat is True or type(repeat) is int and repeat == 1,
            )
            self.forward_controller_state_updates(MOOD_DELAY(str(delay)), MOOD_REPEAT(self.repeat))

    def _publish_routines(self) -> None:
        self.forward_controller_state_updates(
            ROUTINE_COUNT(len(self.routines)),
            ROUTINE_LIST(
                {
                    key: {
                        name: value
                        for name, value in row.payload().items()
                        if name not in ("track", "volume")
                    }
                    for key, row in self.routines.items()
                }
            ),
        )

    def _require_lights(self) -> Link:
        link = self.live()
        if not self.supports_light_color_control:
            raise self.not_supported("headboard lights")
        return link

    async def _set_light(self, enabled: bool) -> None:
        link = self._require_lights()
        with self.sent_state(UNDER_BED_LIGHTS_ON(enabled), is_current=lambda: self.current(link)):
            await self.frame(link, "live_state", codec.state(enabled), response=True)

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def set_light_color_rgbw(
        self, rgbw_color: codec.RGBW, intensity: int | None = None
    ) -> None:
        if any(type(v) is not int or not 0 <= v <= 255 for v in rgbw_color):
            raise invalid("ar_connect_color")
        r, g, b, w = rgbw_color
        total = r + g + b + w
        brightness = (intensity / 255) if intensity is not None else min(1, total / 255)
        tint = 0.5 + 0.5 * w / total if total else 1
        rgb = (float(r), float(g), float(b)) if r + g + b else (1.0, 0.0, 0.0)
        channels = codec.rgbw(rgb, tint, brightness)
        await self.live_color(channels)

    async def live_color(self, channels: codec.RGBW) -> None:
        link = self._require_lights()
        with self.sent_state(
            UNDER_BED_LIGHTS_RGBW(channels),
            LIGHT_INTENSITY(min(255, sum(channels))),
            is_current=lambda: self.current(link),
        ):
            await self.frame(link, "live_values", codec.live(channels), response=True)

    async def set_mood(self, repeat: bool, delay: int, colors: tuple[codec.RGBW, ...]) -> None:
        frame = codec.mood(repeat, delay, colors)
        link = self._require_lights()

        def remember() -> None:
            self.colors, self.repeat, self.delay = colors, repeat, delay

        with self.sent_state(
            MOOD_DELAY(str(delay)), MOOD_REPEAT(repeat), is_current=lambda: self.current(link)
        ):
            await self.frame(link, "mood_values", frame, response=True, on_write=remember)

    async def mood_on(self, enabled: bool) -> None:
        link = self._require_lights()
        with self.sent_state(MOOD_ON(enabled), is_current=lambda: self.current(link)):
            await self.frame(link, "mood_state", codec.state(enabled), response=True)

    async def _mood_parameter(
        self, *, repeat: bool | None = None, delay: int | None = None
    ) -> None:
        if self.colors is None or self.repeat is None or self.delay is None:
            raise invalid("ar_connect_mood_unknown")
        await self.set_mood(
            self.repeat if repeat is None else repeat,
            self.delay if delay is None else delay,
            self.colors,
        )

    async def sync_clock(self) -> None:
        await self.frame(self.live(), "clock", codec.clock(dt_util.now()), response=True)

    async def put_routine(self, routine: codec.Routine, identity: str | None = None) -> None:
        routine.validate()
        link = self.live()
        if identity is not None:
            if not await self._require_routine(link, identity):
                return
            prior = self.routines[identity]
            routine = replace(routine, track=prior.track, volume=prior.volume)

            # Removal then creation is deliberately non-atomic. Never retry the
            # whole sequence or publish a guessed replacement identity.
            def removed() -> None:
                self.routines.pop(identity, None)
                self._routine_list_received.clear()
                # Readback determines the stored list; command completion alone
                # does not acknowledge a replacement or its new identity.
                self.forward_controller_state_updates(ROUTINE_COUNT(None), ROUTINE_LIST(None))

            await self.frame(
                link, "remove", codec.remove(int(identity)), response=True, on_write=removed
            )
            self.live(link)
            if self._coordinator.cancel_command.is_set():
                return
        await self.frame(link, "routine", codec.routine(routine), response=True)

    async def refresh_routines(self) -> None:
        """Read a complete list on this link; identity events are not list data."""
        link = self.live()
        self.framer.clear()
        self._routine_list_received.clear()
        self.forward_controller_state_updates(ROUTINE_COUNT(None), ROUTINE_LIST(None))
        self.receive("routine", await self.read(link, "routine"))
        ready = asyncio.create_task(self._routine_list_received.wait())
        cancelled = asyncio.create_task(self._coordinator.cancel_command.wait())
        try:
            done, _ = await asyncio.wait(
                (ready, cancelled), timeout=15, return_when=asyncio.FIRST_COMPLETED
            )
            self.live(link)
            if not done:
                raise TimeoutError("Headboard routine list did not complete")
        finally:
            ready.cancel()
            cancelled.cancel()
            await asyncio.gather(ready, cancelled, return_exceptions=True)

    async def _require_routine(self, link: Link, identity: str) -> bool:
        if not self._routine_list_received.is_set():
            await self.refresh_routines()
            self.live(link)
            if self._coordinator.cancel_command.is_set():
                return False
        if identity not in self.routines:
            raise invalid("ar_connect_routine_unknown")
        try:
            int(identity)
        except ValueError:
            raise invalid("ar_connect_routine_unknown") from None
        return True

    async def delete_routine(self, identity: str) -> None:
        link = self.live()
        if not await self._require_routine(link, identity):
            return
        await self.frame(link, "remove", codec.remove(int(identity)), response=True)

    @property
    def alarm_capability(self) -> AlarmCapability:
        # Shared set_alarm creates a wake routine; editing/removal needs a real
        # returned id, handled by the routine action. No invented slot bank.
        return AlarmCapability(weekdays=True, durations=codec.DURATIONS)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if not alarm.enabled:
            raise invalid("ar_connect_alarm_record_required")
        if alarm.duration not in codec.DURATIONS:
            raise invalid("field_required", field="duration (routine duration in minutes)")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        assert alarm.duration is not None
        await self.put_routine(
            codec.Routine(
                alarm.enabled,
                "wake",
                alarm.hour,
                alarm.minute,
                alarm.duration,
                weekdays=tuple(codec.DAYS[i] for i in alarm.weekdays),
            )
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if not self.supports_light_color_control:
            return ()
        return (
            ControllerSwitchSpec(
                "ar_headboard_mood",
                "ar_headboard_mood",
                lambda c, v: require_controller(c, HeadboardController).mood_on(v),
                MOOD_ON,
                card=CARD_LIGHTING,
            ),
            ControllerSwitchSpec(
                "ar_headboard_repeat",
                "ar_headboard_repeat",
                lambda c, v: require_controller(c, HeadboardController)._mood_parameter(repeat=v),
                MOOD_REPEAT,
                card=CARD_LIGHTING,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.supports_light_color_control:
            return ()
        return (
            ControllerSelectSpec(
                "ar_headboard_mood_delay",
                "ar_headboard_mood_delay",
                MOOD_DELAY,
                tuple(map(str, codec.DURATIONS)),
                lambda c, v: require_controller(c, HeadboardController)._mood_parameter(
                    delay=int(v)
                ),
                card=CARD_LIGHTING,
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "ar_headboard_status",
                "ar_headboard_status",
                STATUS,
                "mdi:lightbulb",
                entity_registry_enabled_default=True,
                entity_category=None,
                card=CARD_LIGHTING,
            ),
            ControllerStateSensorSpec(
                "ar_headboard_routines",
                "ar_headboard_routines",
                ROUTINE_COUNT,
                "mdi:alarm",
                attribute_keys=(ROUTINE_LIST, LAST_CREATED_ROUTINE_ID),
                card=CARD_UTILITY,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "ar_headboard_refresh_routines",
                "Refresh routines",
                lambda c: require_controller(c, HeadboardController).refresh_routines(),
                icon="mdi:refresh",
                diagnostic=True,
                entity_registry_enabled_default=False,
                cancel_movement=False,
                scheduler_resource="configuration",
            ),
        )

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True, reconcile_on_persistent_link=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {"config": self.config}

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "route": "headboard",
            "config": self.config,
            "version": self.version,
            "timeouts": dict(self.timeouts),
            "live_channels": self._rgbw,
            "hardware": "UNVERIFIED",
        }

    async def read_light_state(self) -> tuple[StateUpdate, ...]:
        link = self._require_lights()
        for key in ("live_state", "live_values"):
            self.receive(key, await self.read(link, key))
        return ()

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self.config = None
        self.colors = self.delay = self.repeat = None
        self._rgbw = None
        if hasattr(self, "framer"):
            self.framer.clear()
            self.routines.clear()
            self._routine_list_received.clear()
        if self._coordinator.controller is not self:
            return
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGBW(None),
            LIGHT_INTENSITY(None),
            MOOD_ON(None),
            MOOD_DELAY(None),
            MOOD_REPEAT(None),
            STATUS(None),
            ROUTINE_COUNT(None),
            ROUTINE_LIST(None),
            LAST_CREATED_ROUTINE_ID(None),
        )

    async def stop_all(self) -> None:
        # This route has no physical motor STOP. Cancelling a queued local light
        # or routine action is owned by the shared command scheduler.
        return None
