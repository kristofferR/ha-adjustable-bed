"""Ultramatic's live P1/P2 extension of the shared ORE comfort-bed controller."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, TypedDict, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmError, AlarmRequest
from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import keeson as codec
from ...command_scheduler import current_command_context
from ...const import KEESON_VARIANT_ORE_ULTRAMATIC
from ...profiles import keeson as profiles
from ...profiles import ore_ultramatic as app
from ..base import BedController
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from ..ore_comfort_bed import OreComfortBedController
from .state_keys import ACTION, ALL, INTENSITY, REPEAT, TIME, TIMER


class AlarmFields(TypedDict):
    enabled: bool
    hour: int
    minute: int
    repeat: int
    kind: int


if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    route: app.Route


class OreUltramaticController(OreComfortBedController):
    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, snapshot: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(coordinator, app=KEESON_VARIANT_ORE_ULTRAMATIC)
        saved = (
            snapshot.get("ultramatic_route")
            if snapshot is not None and set(snapshot) == {"ultramatic_route"}
            else None
        )
        self._route: app.Route | None = "P1" if saved == "P1" else "P2" if saved == "P2" else None
        self._link: Link | None = None
        self._notifying = False
        self._parser = codec.UltramaticParser()
        self._last_preset: str | None = None
        if self._route is not None:
            self._select_route(self._route)

    def _select_route(self, route: app.Route) -> None:
        self._route = route
        self.profile = app.profile(route)
        if self._motor_count == 2:
            self._axes["both"] = (0x10, 0x20) if route == "P1" else (0x05, 0x0A)

    def _capture_link(self) -> Link:
        if self._link is not None:
            self._check_link(self._link)
            return self._link
        client = self.client
        if client is None or not client.is_connected or client.services is None:
            raise ConnectionError("Ultramatic is not connected")
        write = notify = None
        route: app.Route = "P2"
        for service in client.services:
            if str(service.uuid).lower() == app.SELECTOR:
                route = "P1"
            for characteristic in service.characteristics:
                if str(characteristic.uuid).lower() == app.WRITE:
                    write = characteristic
                elif str(characteristic.uuid).lower() == app.NOTIFY:
                    notify = characteristic
        if write is None or notify is None:
            raise ValueError("ORE Ultramatic requires both FFE9 and FFE4")
        self._select_route(route)
        self._link = Link(
            client, write, notify, "write-without-response" not in write.properties, route
        )
        return self._link

    def _check_link(self, link: Link) -> None:
        if self._link is not link or self.client is not link.client or not link.client.is_connected:
            raise ConnectionError("Ultramatic operation belongs to a previous BLE session")

    async def _write_link(self, link: Link, frame: bytes, *, cleanup: bool = False) -> None:
        self._check_link(link)
        await self._write_gatt_with_retry(
            app.WRITE,
            frame,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            cancel_event=asyncio.Event() if cleanup else None,
            before_write=lambda: self._check_link(link),
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._capture_link()
        await self._write_gatt_with_retry(
            app.WRITE,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            before_write=lambda: self._check_link(link),
        )

    async def _single_on(self, link: Link, frame: bytes, delay_ms: int = app.SINGLE_MS) -> None:
        await asyncio.sleep(delay_ms / 1000)
        await self._write_link(link, frame)

    async def _send_single(self, word: int) -> None:
        link = self._capture_link()
        await self._single_on(link, profiles.encode(app.profile(link.route), word))

    async def _release_link(self, link: Link) -> None:
        async def release() -> None:
            await asyncio.sleep(app.SINGLE_MS / 1000)
            if self._link is link and self.client is link.client and link.client.is_connected:
                await self._write_link(
                    link, profiles.encode(app.profile(link.route), 0), cleanup=True
                )

        # A second cancellation cannot abandon the in-flight release or move it
        # to a replacement client. Drain it before the scheduler frees the lane.
        task = asyncio.create_task(release())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _send_release(self) -> None:
        await self._release_link(self._capture_link())

    async def _hold(self, word: int, duration_ms: int | None = None) -> None:
        link = self._capture_link()
        frame = profiles.encode(app.profile(link.route), word)
        count, interval = self.motor_pulse_settings()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (
            duration_ms / 1000 if duration_ms is not None else count * interval / 1000
        )
        context = current_command_context()
        try:
            while not self._coordinator.cancel_command.is_set():
                effective = (
                    context.hold_deadline
                    if context and context.hold_deadline is not None
                    else deadline
                )
                if loop.time() >= effective:
                    break
                await self._write_link(link, frame)
                await asyncio.sleep(min(interval / 1000, max(0, effective - loop.time())))
        finally:
            await self._release_link(link)

    async def _preset(self, name: str) -> None:
        if self._capture_link().route == "P2":
            await self._hold(app.P2_PRESETS[name])
        else:
            word = 0 if self._last_preset == name else app.P1_RECALL[name]
            self._last_preset = None if word == 0 else name
            await self._send_single(word)

    async def preset_flat(self) -> None:
        await self._preset("flat")

    async def preset_zero_g(self) -> None:
        await self._preset("zero_g")

    async def preset_tv(self) -> None:
        await self._preset("tv")

    async def preset_anti_snore(self) -> None:
        await self._preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        if self._capture_link().route != "P1" or memory_num not in (1, 2):
            raise ValueError("Ultramatic P2 has no memory recall")
        await self._preset(f"memory_{memory_num}")

    async def _save(self, name: str) -> None:
        if self._capture_link().route != "P1":
            raise ValueError("Ultramatic P2 has no programmable presets")
        await self._send_single(app.P1_SAVE[name])

    async def program_memory(self, memory_num: int) -> None:
        if memory_num not in (1, 2):
            raise ValueError("Choose memory1 or2")
        await self._save(f"memory_{memory_num}")

    async def program_flat(self) -> None:
        await self._save("flat")

    async def program_zero_g(self) -> None:
        await self._save("zero_g")

    @property
    def supports_preset_tv(self) -> bool:
        return self._route == "P2"

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._route == "P2"

    @property
    def supports_memory_presets(self) -> bool:
        return self._route == "P1"

    @property
    def memory_slot_count(self) -> int:
        return 2 if self._route == "P1" else 0

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return ("M1", "M2") if self._route == "P1" else ()

    @property
    def supports_memory_programming(self) -> bool:
        return self._route == "P1"

    @property
    def supports_discrete_light_control(self) -> bool:
        return self._route == "P1"

    @property
    def supports_light_toggle_control(self) -> bool:
        return self._route == "P2"

    @property
    def supports_massage_off_control(self) -> bool:
        return self._route == "P1"

    @property
    def supports_preset_hold(self) -> bool:
        return self._route == "P2"

    @property
    def held_preset_options(self) -> tuple[str, ...]:
        return tuple(app.P2_PRESETS) if self._route == "P2" else ()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            (*app.P2_MASSAGE, *(f"preset_{name}" for name in app.P2_PRESETS))
            if self._route == "P2"
            else ()
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        if self._route == "P2" and key.removeprefix("preset_") in app.P2_PRESETS:
            return ControllerHoldSpec(key, release_delay_ms=app.SINGLE_MS)
        return None

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 1 <= duration_ms <= 30000:
            raise ValueError("Choose a P2 massage control and hold of1..30000ms")

    async def lights_toggle(self) -> None:
        if self._capture_link().route != "P2":
            raise ValueError("P1 uses explicit light on/off")
        await self._send_single(app.LIGHT_TOGGLE)

    async def lights_on(self) -> None:
        if self._capture_link().route != "P1":
            raise ValueError("P2 light is toggle-only")
        await super().lights_on()

    async def lights_off(self) -> None:
        if self._capture_link().route != "P1":
            raise ValueError("P2 light is toggle-only")
        await super().lights_off()

    async def set_massage_level(self, zone: str, level: int) -> None:
        if self._capture_link().route != "P1":
            raise ValueError("P2 has no absolute massage levels")
        await super().set_massage_level(zone, level)

    async def set_massage_timer_option(self, option: str) -> None:
        if self._capture_link().route != "P1":
            raise ValueError("P2 has no absolute massage timer")
        await super().set_massage_timer_option(option)

    async def massage_start(self) -> None:
        link = self._capture_link()
        if link.route != "P1":
            raise ValueError("P2 has a held massage toggle")
        from ..ore_comfort_bed import MASSAGE_BASE

        for zone in ("wave", "head", "foot"):
            await self._single_on(
                link,
                profiles.encode(app.profile(link.route), MASSAGE_BASE[zone] + self._levels[zone]),
            )

    async def massage_off(self) -> None:
        link = self._capture_link()
        if link.route != "P1":
            raise ValueError("P2 has no discrete massage off")
        from ..ore_comfort_bed import MASSAGE_BASE, STATE_TIMER

        for zone in ("head", "foot"):
            await self._single_on(
                link, profiles.encode(app.profile(link.route), MASSAGE_BASE[zone])
            )
        self.forward_controller_state_updates(STATE_TIMER(None))

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self._capture_link()
        self.validate_hold_control(control, duration_ms)
        word = (
            app.P2_PRESETS[control.removeprefix("preset_")]
            if control.startswith("preset_")
            else app.P2_MASSAGE[control]
        )
        await self._hold(word, duration_ms)

    async def hold_preset(self, preset: str, duration_ms: int) -> None:
        if self._capture_link().route != "P2" or preset not in app.P2_PRESETS:
            raise ValueError("Only P2 presets support holds")
        if not 1 <= duration_ms <= 30000:
            raise ValueError("Choose a hold of1..30000ms")
        await self._hold(app.P2_PRESETS[preset], duration_ms)

    @property
    def supports_clock_sync(self) -> bool:
        return self._route == "P2"

    async def sync_clock(self) -> None:
        link = self._capture_link()
        if link.route != "P2":
            raise ValueError("P1 clock is part of alarm/query records")
        await self._single_on(link, codec.clock(dt_util.now()))

    async def query_alarm(self) -> None:
        link = self._capture_link()
        await self._single_on(link, app.query(link.route, dt_util.now()), app.QUERY_MS)

    @property
    def alarm_capability(self) -> AlarmCapability:
        # The route, and so the wake actions, is known once the bed has connected.
        # The live route is checked on every target before any write, and a wake
        # action is explicit so a changed route cannot pick a different default.
        # Before that, every route's choices pass so the route error is the one shown.
        known = self._route is not None
        return AlarmCapability(
            wake_actions=tuple(app.WAKE_KINDS[self._route])
            if self._route
            else tuple(dict.fromkeys(k for kinds in app.WAKE_KINDS.values() for k in kinds)),
            weekdays=True,
            requires_wake_action=known,
            live_check=known,
            resource="*",
        )

    def _alarm_fields(self, alarm: AlarmRequest) -> tuple[app.Route, AlarmFields]:
        if self._route is None:
            raise AlarmError(
                "alarm_route_unknown",
                "Connect the bed once so Home Assistant can discover its bed route",
            )
        kinds = app.WAKE_KINDS[self._route]
        if alarm.enabled and alarm.wake_action not in kinds:
            # The live route differs from the one the request was checked against.
            raise AlarmError(
                "alarm_route_changed",
                f"The bed's controls changed; choose one of: {', '.join(kinds)}",
                wake_actions=", ".join(kinds),
            )
        return self._route, {
            "enabled": alarm.enabled,
            "hour": alarm.hour,
            "minute": alarm.minute,
            "repeat": app.repeat_mask(alarm.weekdays),
            # A disabled alarm sends no alarm type.
            "kind": kinds.get(alarm.wake_action, 0),
        }

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        route, fields = self._alarm_fields(alarm)
        app.alarm(route, alarm.reference_time, **fields)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.set_alarm(**self._alarm_fields(alarm)[1])

    async def set_alarm(
        self, *, enabled: bool, hour: int, minute: int, repeat: int, kind: int
    ) -> None:
        link = self._capture_link()
        now = dt_util.now()
        frame = app.alarm(
            link.route, now, enabled=enabled, hour=hour, minute=minute, repeat=repeat, kind=kind
        )
        if link.route == "P2":
            await self._single_on(link, codec.clock(now))
        await self._single_on(link, frame)
        await self._single_on(link, app.query(link.route, dt_util.now()), app.QUERY_MS)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return super().controller_number_specs if self._route == "P1" else ()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return super().controller_select_specs if self._route == "P1" else ()

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = (
            tuple(
                replace(spec, requires_confirmation=spec.key.startswith("ore_comfort_program_"))
                for spec in super().controller_button_specs
            )
            if self._route == "P1"
            else ()
        )
        return (
            *buttons,
            # The bed reports its alarm only when asked.
            ControllerButtonSpec(
                "ore_ultramatic_alarm_refresh",
                "Refresh alarm",
                lambda c: cast(OreUltramaticController, c).query_alarm(),
                "mdi:alarm",
                translation_key="ore_ultramatic_alarm_refresh",
                diagnostic=True,
                card=CARD_UTILITY,
            ),
            *(
                ControllerButtonSpec(
                    f"ore_ultramatic_massage_{key}",
                    f"Massage {key}",
                    _massage_press(key),
                    translation_key=f"ore_ultramatic_massage_{key}",
                    hold=ControllerHoldSpec(key, release_delay_ms=app.SINGLE_MS),
                    card=CARD_MASSAGE,
                )
                for key in app.P2_MASSAGE
                if self._route == "P2"
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                str(TIME), str(TIME), TIME, "mdi:alarm", attribute_keys=(REPEAT, ACTION)
            ),
            ControllerStateSensorSpec(
                str(INTENSITY),
                str(INTENSITY),
                INTENSITY,
                "mdi:vibrate",
                attribute_keys=(TIMER,),
            ),
        )

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy()

    def capability_snapshot(self) -> dict[str, object] | None:
        return {"ultramatic_route": self._route} if self._route else None

    async def async_discover_capabilities(self) -> None:
        self._capture_link()

    async def async_on_connect(self, session: ControllerSession) -> None:
        # Notifications carry alarm/massage state even with angles disabled.
        await self.start_notify()
        session.persist_capability_snapshot()

    @property
    def requires_notification_channel(self) -> bool:
        """Alarm/massage reports remain subscribed when diagnostics finishes."""
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._capture_link()
        if self._notifying:
            return

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            self.forward_raw_notification(str(link.notify.uuid), bytes(data))
            callbacks = self._parser.feed(bytes(data))
            s = self._parser.state
            if "alarm" in callbacks:
                self.forward_controller_state_updates(
                    TIME(
                        f"{s.hour:02d}:{s.minute:02d}"
                        if 0 <= s.hour < 24 and 0 <= s.minute < 60
                        else None
                    ),
                    REPEAT(s.repeat),
                    ACTION(s.type),
                )
            if "massage" in callbacks:
                self.forward_controller_state_updates(TIMER(s.timer), INTENSITY(s.intensity))

        async with self._ble_lock:
            self._check_link(link)
            await link.client.start_notify(link.notify, received)
        self._check_link(link)
        self._notifying = True

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._notifying
        self.on_disconnect()
        if link is not None and subscribed and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._parser = codec.UltramaticParser()
        self._last_preset = None
        self.forward_controller_state_updates(*(key(None) for key in ALL))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {**super().protocol_diagnostics, "route": self._route, "hardware": "UNVERIFIED"}


def _massage_press(key: str) -> MotorCommandCallable:
    async def press(ctrl: BedController) -> None:
        await cast(OreUltramaticController, ctrl).hold_control(key, 1000)

    return press
