"""Sleep Assistant's session, serialized control stream and native HA entities."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...app_session import app_session
from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS, CARD_UTILITY
from ...codec import sleep_assistant as codec
from ...command_scheduler import current_command_context
from ...const import CONF_BED_TYPE, CONF_PROFILE_ID, CONF_PROTOCOL_VARIANT
from ...controller_state import StateUpdate
from ...errors import invalid
from ...profiles import sleep_assistant as app
from ...state_keys import (
    LIGHT_LEVEL,
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
)
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import MASSAGE_KEY, PRESET_KEY
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
    sleep_flag_binary_sensor_spec,
    sleep_rate_sensor_spec,
)
from ..lifecycle import ControllerSession
from . import state_keys as keys

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    address: str
    generation: int


def _action(name: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await require_controller(controller, SleepAssistantController).run_action(name)

    return run


@dataclass(slots=True)
class Intent:
    anti_snore_level: int | None = None
    proven_presets: tuple[str, ...] | None = None


class SleepAssistantController(ProfileExecution[app.SleepAssistantProfile], BedController):
    """One physical receiver. Physiological sides are never motor selectors."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: app.SleepAssistantProfile | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile or app.SleepAssistantProfile()
        self._link: Link | None = None
        self._notifying = False
        self._subscription_token: object | None = None
        self._generation = 0
        self._versions: dict[str, str] = {}
        self._diagnostics: dict[str, object] = {}
        self._light_on: bool | None = None
        self._color: tuple[int, int, int] | None = None
        self._level: int | None = 3
        self._clock_pending = 0
        self._firmware_ready = asyncio.Event()
        self._flat_expected: tuple[int, int, int, int, int] | None = None
        self._version_at: float | None = None
        self._anti_initialized = self._hours_initialized = False
        self._configuration = self._configuration_signature()
        self._intent = app_session(
            coordinator.hass, coordinator.address, ("sleep_assistant", self.profile), Intent
        )
        self._alarm_row = 0
        self._massage_until = self._one_until = 0.0

    @property
    def control_characteristic_uuid(self) -> str:
        return codec.WRITE

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **self._diagnostics,
            "versions": dict(self._versions),
            "hardware_verified": False,
            "model_assignments": "user supplied",
            "memory_programming": "unproven",
        }

    @property
    def _hw218(self) -> bool:
        return (
            float(self._versions.get("mcu", "0")) >= 2.05
            and float(self._versions.get("bt", "0")) >= 2.18
        )

    @property
    def _visible(self) -> tuple[str, ...]:
        return app.visible_presets(self.profile.presets, self._hw218)

    @property
    def _entity_visible(self) -> tuple[str, ...]:
        # Prior proof keeps offline controls callable; it never admits a frame.
        if (
            not self.controller_entity_discovery_complete
            and self._intent.proven_presets is not None
        ):
            return self._intent.proven_presets
        return self._visible

    def _configuration_signature(self) -> str:
        data = self._coordinator.entry.data
        return json.dumps(
            {
                key: data.get(key)
                for key in (
                    app.CONF_SLEEP_ASSISTANT_PRESETS,
                    app.CONF_SLEEP_ASSISTANT_CONTROLS,
                    app.CONF_SLEEP_ASSISTANT_LIGHTING,
                    app.CONF_SLEEP_ASSISTANT_IDENTITY,
                    app.CONF_SLEEP_ASSISTANT_PARAMETERS,
                    "has_light",
                    CONF_BED_TYPE,
                    CONF_PROTOCOL_VARIANT,
                    CONF_PROFILE_ID,
                )
            },
            sort_keys=True,
        )

    def _live(self, expected: Link | None = None) -> Link:
        link = self._link
        owner = self._coordinator.controller
        if (
            link is None
            or self._configuration_signature() != self._configuration
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
            or self._generation != link.generation
            or self._coordinator.address.upper() != link.address
            or owner is not self
            or self.command_side not in (None, "both")
        ):
            raise invalid("sleep_assistant_session_changed")
        return link

    def sent_state(
        self, *updates: StateUpdate, is_current: Callable[[], bool] | None = None
    ) -> AbstractContextManager[None]:
        expected = self._live()

        def current() -> bool:
            try:
                self._live(expected)
            except ServiceValidationError:
                return False
            return is_current is None or is_current()

        return super().sent_state(*updates, is_current=current)

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def controller_entity_discovery_complete(self) -> bool:
        return {"bt", "mcu"} <= self._versions.keys()

    @property
    def retained_entity_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            ("button", f"sleep_assistant_{app.PRESET_ACTIONS[token]}")
            for token in self.profile.presets
        )

    def controller_button_available(self, key: str) -> bool:
        return key in {spec.key for spec in self.controller_button_specs}

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise invalid("sleep_assistant_session_changed")
        service = client.services.get_service(codec.SERVICE)
        write = service.get_characteristic(codec.WRITE) if service else None
        notify = service.get_characteristic(codec.NOTIFY) if service else None
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
            or "notify" not in notify.properties
        ):
            raise invalid("sleep_assistant_gatt_missing")
        self._link = Link(
            client,
            write,
            notify,
            "write" in write.properties,
            self._coordinator.address.upper(),
            self._generation,
        )

    async def _async_send(
        self,
        frame: bytes,
        *,
        link: Link | None = None,
        cancel: asyncio.Event | None = None,
        track: bool = True,
        on_write: Callable[[], None] | None = None,
    ) -> bool:
        expected = self._live(link)
        written = False

        def after_write() -> None:
            nonlocal written
            self._live(expected)
            written = True
            if on_write is not None:
                on_write()

        def before_write() -> None:
            self._live(expected)
            context = current_command_context()
            if track and context is not None and not context.active:
                raise invalid("sleep_assistant_session_changed")

        await settled(
            self._write_gatt_with_retry(
                codec.WRITE,
                frame,
                cancel_event=cancel,
                response=expected.response,
                characteristic=expected.write,
                expected_client=expected.client,
                before_write=before_write,
                track_command_write=track,
                on_write=after_write,
            )
        )
        self._live(expected)
        return written

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        loop = asyncio.get_running_loop()
        for index in range(repeat_count):
            started = loop.time()
            await self._async_send(command, link=link, cancel=cancel_event)
            if index + 1 < repeat_count:
                await cancellable(
                    asyncio.sleep(max(0, started + repeat_delay_ms / 1000 - loop.time())),
                    cancel_event or self._coordinator.cancel_command,
                )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        link = self._live()
        if self._notifying:
            return

        token = self._subscription_token = object()

        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._subscription_token is not token:
                return
            try:
                self._live(link)
            except ServiceValidationError:
                return
            self.forward_raw_notification(codec.NOTIFY, bytes(data))
            for frame in codec.split_notifications(bytes(data)):
                self._receive(frame)

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
        except BaseException:
            if self._subscription_token is token:
                self._subscription_token = None
            raise
        self._notifying = True

    async def stop_notify(self) -> None:
        link = self._link
        self._subscription_token = None
        self._notifying = False
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.notify)

    async def async_resume_session(self) -> None:
        await self.start_notify()

    def on_disconnect(self) -> None:
        self._generation += 1
        self._link = None
        self._notifying = False
        self._subscription_token = None
        self._versions.clear()
        self._firmware_ready.set()
        self._firmware_ready = asyncio.Event()
        self._flat_expected = None
        self._diagnostics.clear()
        self._clock_pending = self._alarm_row = 0
        self._light_on = None
        self._color, self._level = None, 3
        self._version_at = None
        self._anti_initialized = self._hours_initialized = False
        self._massage_until = self._one_until = 0
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            LIGHT_LEVEL(None),
            MASSAGE_TIMER_MINUTES(None),
            keys.STORAGE(None),
            keys.PALETTE(None),
            keys.ANTI_SNORE(None),
            keys.MASSAGE(None),
            keys.FLAT_MINUTES(None),
            keys.ONE_BUTTON(None),
            *(key(None) for key in keys.ALARMS),
            *(
                key(None)
                for group in (keys.OCCUPIED, keys.HEART, keys.BREATH, keys.MOVEMENT)
                for key in group.values()
            ),
        )

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        link = self._live()
        await cancellable(asyncio.sleep(0.1), self._coordinator.cancel_command)
        self._live(link)
        if self.profile.identity is not None:
            await self._async_send(
                codec.serial_identity(self.profile.identity), link=link, track=False
            )
        if self.profile.calibration is not None:
            await self._async_send(
                codec.bed_calibration(*self.profile.calibration), link=link, track=False
            )
        if self.profile.gain is not None:
            await self._async_send(
                codec.gain("0", f"{self.profile.gain:02X}"), link=link, track=False
            )
        if self.profile.out_of_bed is not None:
            await self._async_send(
                codec.out_of_bed(*self.profile.out_of_bed), link=link, track=False
            )
        await self._async_send(codec.storage_query(), link=link, track=False)
        await self._async_send(codec.ANTI_SNORE_QUERY, link=link, track=False)
        await self._async_send(codec.ALARM_QUERY, link=link, track=False)
        deadline = asyncio.get_running_loop().time()
        for gap in (0.5, 0.3, 0.2, 0.3):
            deadline += gap
            await cancellable(
                asyncio.sleep(max(0, deadline - asyncio.get_running_loop().time())),
                self._coordinator.cancel_command,
            )
            await self._async_send(codec.instruction(0), link=link, track=False)
        if self.supports_lights:
            await self._async_send(codec.light(), link=link, track=False)
            await cancellable(asyncio.sleep(0.8), self._coordinator.cancel_command)
            await self._async_send(codec.light(), link=link, track=False)

    @property
    def diagnostic_poll_interval(self) -> float:
        return 1.0

    async def async_refresh_diagnostics(self) -> None:
        link = self._live()
        for index in range(self._clock_pending):
            if index:
                await cancellable(asyncio.sleep(0.1), self._coordinator.cancel_command)

            def consumed() -> None:
                self._clock_pending = max(0, self._clock_pending - 1)

            if not await self._async_send(
                codec.local_clock(dt_util.now()), link=link, track=False, on_write=consumed
            ):
                break
        now = asyncio.get_running_loop().time()
        if self._version_at is not None and (
            self.profile.anti_snore is not None or self._intent.anti_snore_level is not None
        ):
            elapsed = now - self._version_at
            if not self._anti_initialized and elapsed >= 2:
                await self._async_send(
                    codec.anti_snore(
                        self._desired_anti_level,
                        *self._anti_parameters[self._desired_anti_level][1:],
                    ),
                    link=link,
                    track=False,
                    on_write=lambda: setattr(self, "_anti_initialized", True),
                )
            if not self._hours_initialized and elapsed >= 3:
                await self._async_send(
                    codec.anti_hours(),
                    link=link,
                    track=False,
                    on_write=lambda: setattr(self, "_hours_initialized", True),
                )
        if self._massage_until and now >= self._massage_until:
            self._massage_until = 0
            self.forward_controller_state_updates(keys.MASSAGE(False))
        if self._one_until and now >= self._one_until:
            self._one_until = 0
            self.forward_controller_state_updates(keys.ONE_BUTTON(False))

    def _receive(self, frame: bytes) -> None:
        if not frame:
            return
        if frame[0] == 0x8E:
            self._clock_pending = 2
        elif frame[0] == 0x88:
            self._clock_pending = max(1, self._clock_pending)
        elif frame[0] == 0x8B and len(frame) < 25:
            before = (self._visible, self.controller_entity_discovery_complete)
            self._version_at = asyncio.get_running_loop().time()
            for kind, name in ((1, "bt"), (2, "mcu"), (3, "dsp")):
                version = codec.version_fields(frame.hex(), kind)
                if version is not None:
                    self._versions[name] = version
            if len(frame) > 2:
                self._diagnostics["bed_mode"] = frame[2]
            if self.controller_entity_discovery_complete:
                self._intent.proven_presets = self._visible
                self._firmware_ready.set()
            if before != (self._visible, self.controller_entity_discovery_complete):
                self.forward_controller_state_updates(keys.CAPABILITY_REVISION(self._generation))
        elif frame[:2] == b"\x95\x11":
            version = codec.dsp_fields(frame.hex())
            if version is not None:
                self._versions["dsp"] = version
        raw = codec.raw_fields(frame.hex(), float(self._versions.get("bt", "0")))
        if "storage" in raw:
            self.forward_controller_state_updates(keys.STORAGE(raw["storage"] is True))
        elif "side" in raw:
            side = str(raw["side"])
            absent = raw["absent"] is True
            heart, breath = raw.get("heart"), raw.get("breathing")
            self.forward_controller_state_updates(
                keys.OCCUPIED[side](not absent),
                keys.HEART[side](heart if type(heart) is int and heart >= 0 else None),
                keys.BREATH[side](
                    breath
                    if "bt" in self._versions and type(breath) is int and breath >= 0
                    else None
                ),
                keys.MOVEMENT[side](
                    None if absent or "bt" not in self._versions else raw.get("movement") != 0
                ),
            )
        elif raw:
            self._diagnostics.update(raw)
        scalar = codec.scalar_fields(frame.hex())
        if "level" in scalar:
            self.forward_controller_state_updates(keys.ANTI_SNORE(str(scalar["level"]).lower()))
            self._diagnostics["anti_snore_trigger"] = scalar["trigger"]
        elif "time" in scalar:
            # The source accumulates six sequential rows; no slot byte is invented.
            slot = self._alarm_row % 6
            key = keys.ALARMS[slot]
            self._alarm_row += 1
            if slot == 5:
                scalar["position"] = "Flat" if scalar["position"] else ""
                fields = (frame[3], frame[4], frame[6], frame[7], frame[8])
                if frame[6] == 0:
                    self._flat_expected = None
                    self.forward_controller_state_updates(keys.FLAT_MINUTES(0))
                elif self._flat_expected != fields:
                    self._flat_expected = None
                    self.forward_controller_state_updates(keys.FLAT_MINUTES(None))
            text = " ".join(str(scalar[k]) for k in ("time", "position", "state", "week"))
            self.forward_controller_state_updates(key(text.strip() or None))
        remote = codec.remote_fields(frame.hex(), self._hw218)
        if "light" in remote:
            self._light_on = remote["light"] is True
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(self._light_on))
        if "timer" in remote:
            # The app's UI categories -1/0/1/2 mean off/10/20/30 minutes.
            timer = remote["timer"]
            if type(timer) is int:
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES((timer + 1) * 10))
        if "palette" in remote and type(remote["palette"]) is int:
            index = remote["palette"]
            if 0 <= index < 7:
                self.forward_controller_state_updates(
                    keys.PALETTE(
                        ("off", "red", "orange", "yellow", "green", "blue", "purple")[index]
                    )
                )
        now = asyncio.get_running_loop().time()
        if "massage" in remote:
            self._massage_until = now + (
                2.5 if float(self._versions.get("mcu", "0")) > 2.09 else 5.5
            )
            self.forward_controller_state_updates(keys.MASSAGE(True))
        if "one_key" in remote:
            self._one_until = now + 3.5
            self.forward_controller_state_updates(keys.ONE_BUTTON(True))
        if "brightness_logged" in remote:
            self._diagnostics["brightness"] = remote["brightness_logged"]

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 200

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = [("back", "head"), ("legs", "feet")]
        axes += [
            (axis, axis)
            for axis, token in (("tilt", "m7"), ("lumbar", "m8"))
            if token in self.profile.controls
        ]
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                _action(f"{control}_up"),
                _action(f"{control}_down"),
                lambda c: c.stop_all(),
                hold=ControllerMotorHoldSpec(f"{control}_up", f"{control}_down", stop_scope="side"),
                scheduler_resource="motor:*",
            )
            for axis, control in axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        axes = (
            ["head", "feet"]
            + (["tilt"] if "m7" in self.profile.controls else [])
            + (["lumbar"] if "m8" in self.profile.controls else [])
        )
        return tuple(
            f"{axis}_{direction}" for axis in axes for direction in ("up", "down")
        ) + tuple(app.PRESET_ACTIONS[k] for k in self._entity_visible if k != "o5")

    async def _cleanup(self, link: Link, delays: tuple[int, ...]) -> None:
        async def release() -> None:
            loop = asyncio.get_running_loop()
            deadline = loop.time()
            for delay in delays:
                deadline += delay / 1000
                if deadline > loop.time():
                    await asyncio.sleep(deadline - loop.time())
                # Retired sessions never release on a replacement link.
                if (
                    self._link is not link
                    or self.client is not link.client
                    or not link.client.is_connected
                ):
                    return
                await self._async_send(
                    codec.instruction(0), link=link, cancel=asyncio.Event(), track=False
                )
            context = current_command_context()
            if context is not None:
                context.cleanup_stop_sent = True

        await settled(release())

    async def run_action(
        self, action: str, *, held: bool = False, duration_ms: int | None = None
    ) -> None:
        link = self._live()
        possible = set(app.visible_presets(self.profile.presets, True)) ^ set(
            app.visible_presets(self.profile.presets, False)
        )
        if (
            action in {app.PRESET_ACTIONS[token] for token in possible}
            and not self.controller_entity_discovery_complete
        ):
            try:
                async with asyncio.timeout(5):  # Native admission bound, not a protocol delay.
                    await cancellable(self._firmware_ready.wait(), self._coordinator.cancel_command)
            except TimeoutError as err:
                raise invalid("sleep_assistant_control_unavailable") from err
            self._live(link)
        if action not in self.available_actions:
            raise invalid("sleep_assistant_control_unavailable")
        if held and action not in self.held_control_options:
            raise invalid("sleep_assistant_control_unavailable")
        moving = action.endswith(("_up", "_down")) and action.split("_")[0] in (
            "head",
            "feet",
            "tilt",
            "lumbar",
        )
        refreshed = moving or held
        named_preset = action in ("anti_snore_preset", "memory", "relax", "tv")
        delays = (
            (800, 500)
            if held and not moving
            else (800,)
            if moving
            else (1500 if named_preset else 1300, 200, 200)
        )
        started = asyncio.get_running_loop().time()
        try:
            if held and named_preset:
                await cancellable(asyncio.sleep(0.2), self._coordinator.cancel_command)
            if not refreshed:
                await cancellable(
                    asyncio.sleep(
                        0
                        if action == "flat"
                        else 0.6
                        if action in ("anti_snore_preset", "memory", "relax", "tv")
                        else 0.4
                    ),
                    self._coordinator.cancel_command,
                )
            self._live(link)
            count = self.leased_hold_refreshes(200) if refreshed else None
            if duration_ms is not None:
                count = max(1, (duration_ms + 199) // 200)
            count = count or (self._coordinator.motor_pulse_count if refreshed else 1)
            hold_started = asyncio.get_running_loop().time()
            await self.write_command(codec.instruction(app.WORDS[action]), count, 200)
            if refreshed:
                await cancellable(
                    asyncio.sleep(
                        max(0, hold_started + count * 0.2 - asyncio.get_running_loop().time())
                    ),
                    self._coordinator.cancel_command,
                )
        finally:
            # HA cancels pending taps/refresh and always completes proven neutral cleanup.
            # It deliberately does not reproduce the app's unsafe ACTION_CANCEL timers.
            if not refreshed:
                elapsed_ms = int((asyncio.get_running_loop().time() - started) * 1000)
                delays = (max(0, delays[0] - elapsed_ms), *delays[1:])
            await self._cleanup(link, delays)

    @property
    def available_actions(self) -> frozenset[str]:
        actions = {"head_up", "head_down", "feet_up", "feet_down", "flat", "zero_gravity"}
        actions.update(app.PRESET_ACTIONS[k] for k in self._visible)
        for token, axis in (("m7", "tilt"), ("m8", "lumbar")):
            if token in self.profile.controls:
                actions.update((f"{axis}_up", f"{axis}_down"))
        controls = self.profile.controls
        if "m1" in controls:
            actions.add("massage_timer_cycle")
        if {"m1", "m2"} <= controls:
            actions.add("massage_all")
        for zone, cycle in (("head", "m5"), ("feet", "m6")):
            paired = {"m3", "m4"} <= controls
            if paired or cycle in controls:
                actions.add(f"massage_{zone}_up")
            if paired:
                actions.add(f"massage_{zone}_down")
        if self.supports_lights:
            actions.add("light_toggle")
        return frozenset(actions)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        await self.run_action(control, held=True, duration_ms=duration_ms)

    async def move_head_up(self) -> None:
        await self.run_action("head_up")

    async def move_head_down(self) -> None:
        await self.run_action("head_down")

    async def move_feet_up(self) -> None:
        await self.run_action("feet_up")

    async def move_feet_down(self) -> None:
        await self.run_action("feet_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down

    async def move_tilt_up(self) -> None:
        await self.run_action("tilt_up")

    async def move_tilt_down(self) -> None:
        await self.run_action("tilt_down")

    async def move_lumbar_up(self) -> None:
        await self.run_action("lumbar_up")

    async def move_lumbar_down(self) -> None:
        await self.run_action("lumbar_down")

    async def stop_all(self) -> None:
        await self._cleanup(self._live(), (0,))

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_feet_stop = stop_all
    move_legs_stop = stop_all
    move_tilt_stop = stop_all
    move_lumbar_stop = stop_all

    async def preset_flat(self) -> None:
        await self.run_action("flat")

    async def preset_zero_g(self) -> None:
        await self.run_action("zero_gravity")

    async def preset_memory(self, memory_num: int) -> None:
        raise invalid("sleep_assistant_control_unavailable")

    async def program_memory(self, memory_num: int) -> None:
        raise invalid("sleep_assistant_control_unavailable")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        result = []
        for token in self._entity_visible:
            action = app.PRESET_ACTIONS[token]
            result.append(
                ControllerButtonSpec(
                    f"sleep_assistant_{action}",
                    app.MODEL_KEYS[token],
                    _action(action),
                    translation_key=PRESET_KEY,
                    translation_placeholders={"action": app.MODEL_KEYS[token]},
                    card=CARD_PRESETS,
                    hold=ControllerHoldSpec(action) if token != "o5" else None,
                )
            )
        for action in sorted(self.available_actions):
            if action.startswith("massage_"):
                label = {
                    "massage_all": "Cycle massage",
                    "massage_timer_cycle": "Cycle massage timer",
                    "massage_head_up": "Cycle head massage"
                    if "m5" in self.profile.controls and not {"m3", "m4"} <= self.profile.controls
                    else "Increase head massage",
                    "massage_head_down": "Decrease head massage",
                    "massage_feet_up": "Cycle feet massage"
                    if "m6" in self.profile.controls and not {"m3", "m4"} <= self.profile.controls
                    else "Increase feet massage",
                    "massage_feet_down": "Decrease feet massage",
                }[action]
                result.append(
                    ControllerButtonSpec(
                        f"sleep_assistant_{action}",
                        label,
                        _action(action),
                        translation_key=MASSAGE_KEY,
                        translation_placeholders={"action": label},
                        card=CARD_MASSAGE_TIMER
                        if action == "massage_timer_cycle"
                        else CARD_MASSAGE,
                    )
                )
        return tuple(result)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            ControllerNumberSpec(
                "sleep_assistant_flat_minutes",
                "sleep_assistant_flat_minutes",
                keys.FLAT_MINUTES,
                0,
                120,
                20,
                lambda c, value: require_controller(c, SleepAssistantController).set_flat_minutes(
                    value
                ),
                native_unit_of_measurement="min",
            ),
        )

    async def set_flat_minutes(self, minutes: float) -> None:
        if minutes not in (0, 20, 40, 60, 80, 100, 120):
            raise invalid("sleep_assistant_invalid_settings")
        now = dt_util.now() + timedelta(minutes=int(minutes))
        frame = (
            codec.alarm(6, now.hour, now.minute, "2", 0, True) if minutes else codec.clear_alarm(6)
        )
        await self._write_alarm_slot(6, frame, int(minutes))

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "sleep_assistant_storage",
                "sleep_assistant_storage",
                lambda c, value: require_controller(c, SleepAssistantController).set_storage(value),
                keys.STORAGE,
                # A privacy setting, not a dashboard control.
                entity_category=EntityCategory.CONFIG,
            ),
        )

    async def set_storage(self, enabled: bool) -> None:
        with self.sent_state(keys.STORAGE(enabled)):
            await self._async_send(codec.storage(int(enabled)))

    @property
    def supports_lights(self) -> bool:
        return self.profile.light or self.profile.lighting != "none"

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return False

    @property
    def supports_light_color_control(self) -> bool:
        return self.profile.lighting == "4193"

    @property
    def supports_light_level_control(self) -> bool:
        return self.profile.lighting == "4193"

    @property
    def light_level_min(self) -> int:
        return 1

    @property
    def light_level_max(self) -> int:
        return 3

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise invalid("sleep_assistant_control_unavailable")
        link = self._live()
        target = not self._light_on if self._light_on is not None else None
        try:
            with self.sent_state(UNDER_BED_LIGHTS_ON(target)):
                await self._async_send(
                    codec.instruction(app.WORDS["light_toggle"]),
                    link=link,
                    on_write=lambda: setattr(self, "_light_on", target),
                )
        finally:
            await self._cleanup(link, (400, 200, 200, 200))

    async def lights_on(self) -> None:
        if self._light_on is None:
            raise invalid("sleep_assistant_light_unknown")
        if not self._light_on:
            await self.lights_toggle()

    async def lights_off(self) -> None:
        if self._light_on is None:
            raise invalid("sleep_assistant_light_unknown")
        if self._light_on:
            await self.lights_toggle()

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if self.profile.lighting != "4193" or self._level is None:
            raise invalid("sleep_assistant_light_unknown")
        if any(type(v) is not int or not 0 <= v <= 255 for v in rgb_color):
            raise invalid("sleep_assistant_invalid_settings")
        await self.lights_on()
        with self.sent_state(UNDER_BED_LIGHTS_RGB(rgb_color)):
            await self._async_send(
                codec.rgb_channels(*rgb_color, (0.2, 0.6, 1.0)[self._level - 1]),
                on_write=lambda: setattr(self, "_color", rgb_color),
            )

    async def set_light_level(self, level: int) -> None:
        if self.profile.lighting != "4193" or level not in (1, 2, 3) or self._color is None:
            raise invalid("sleep_assistant_light_unknown")
        await self.lights_on()
        with self.sent_state(LIGHT_LEVEL(level)):
            await self._async_send(
                codec.rgb_channels(*self._color, (0.2, 0.6, 1.0)[level - 1]),
                on_write=lambda: setattr(self, "_level", level),
            )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        result = []
        if self.profile.lighting == "sleep8":
            result.append(
                ControllerSelectSpec(
                    "sleep_assistant_palette",
                    "sleep_assistant_palette",
                    keys.PALETTE,
                    ("off", "red", "orange", "yellow", "green", "blue", "purple"),
                    lambda c, value: require_controller(c, SleepAssistantController).set_palette(
                        value
                    ),
                    card=CARD_LIGHTING,
                )
            )
        if self.profile.anti_snore is not None or self.profile.anti_snore_levels:
            result.append(
                ControllerSelectSpec(
                    "sleep_assistant_anti_snore",
                    "sleep_assistant_anti_snore",
                    keys.ANTI_SNORE,
                    self._anti_options,
                    lambda c, value: require_controller(c, SleepAssistantController).set_anti_snore(
                        value
                    ),
                )
            )
        return tuple(result)

    async def set_palette(self, color: str) -> None:
        options = ("off", "red", "orange", "yellow", "green", "blue", "purple")
        if self.profile.lighting != "sleep8" or color not in options:
            raise invalid("sleep_assistant_control_unavailable")
        with self.sent_state(keys.PALETTE(color), UNDER_BED_LIGHTS_ON(color != "off")):
            await self._async_send(
                codec.rgb(0, options.index(color)),
                on_write=lambda: setattr(self, "_light_on", color != "off"),
            )

    @property
    def _desired_anti_level(self) -> int:
        if self._intent.anti_snore_level is not None:
            return self._intent.anti_snore_level
        return self.profile.anti_snore[0] if self.profile.anti_snore is not None else 0

    @property
    def _anti_parameters(self) -> dict[int, tuple[int, int, int, int, int]]:
        parameters = {level[0]: level for level in self.profile.anti_snore_levels}
        if self.profile.anti_snore is not None:
            parameters[self.profile.anti_snore[0]] = self.profile.anti_snore
        parameters[0] = (0, 0, 0, 0, 0)  # The proven Off builder ignores numeric inputs.
        return parameters

    @property
    def _anti_options(self) -> tuple[str, ...]:
        return tuple(
            ("off", "high", "mid", "low")[level] for level in sorted(self._anti_parameters)
        )

    async def set_anti_snore(self, level: str) -> None:
        if (
            self.profile.anti_snore is None and not self.profile.anti_snore_levels
        ) or level not in self._anti_options:
            raise invalid("sleep_assistant_control_unavailable")
        selected = ("off", "high", "mid", "low").index(level)
        with self.sent_state(keys.ANTI_SNORE(level)):
            await self._async_send(
                codec.anti_snore(*self._anti_parameters[selected]),
                on_write=lambda: setattr(self._intent, "anti_snore_level", selected),
            )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        timer = (
            (
                massage_timer_sensor_spec(
                    "sleep_assistant_massage_timer",
                    "sleep_assistant_massage_timer",
                    MASSAGE_TIMER_MINUTES,
                    card=CARD_MASSAGE_TIMER,
                ),
            )
            if "m1" in self.profile.controls
            else ()
        )
        return (
            timer
            + tuple(
                ControllerStateSensorSpec(
                    str(key),
                    str(key),
                    key,
                    "mdi:alarm",
                    entity_registry_enabled_default=True,
                    entity_category=None,
                    card=CARD_UTILITY,
                )
                for key in keys.ALARMS
            )
            + tuple(
                spec
                for side in ("left", "right")
                for spec in (
                    sleep_rate_sensor_spec(
                        "heart_rate", str(keys.HEART[side]), keys.HEART[side], side
                    ),
                    sleep_rate_sensor_spec(
                        "breathing_rate", str(keys.BREATH[side]), keys.BREATH[side], side
                    ),
                )
            )
        )

    @property
    def controller_state_binary_sensor_specs(self):
        return tuple(
            spec
            for side in ("left", "right")
            for spec in (
                sleep_flag_binary_sensor_spec(
                    "bed_presence", str(keys.OCCUPIED[side]), keys.OCCUPIED[side], side
                ),
                sleep_flag_binary_sensor_spec(
                    "body_movement", str(keys.MOVEMENT[side]), keys.MOVEMENT[side], side
                ),
            )
        )

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(slots=6, weekdays=True, wake_actions=("zero_g", "massage", "flat"))

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.enabled and (
            ((alarm.wake_action == "flat") != (alarm.slot == 6))
            or alarm.slot == 6
            and alarm.weekdays
        ):
            raise invalid("sleep_assistant_alarm_slot")

    async def _write_alarm_slot(
        self, slot: int, frame: bytes, flat_minutes: int | None = None
    ) -> None:
        updates = (keys.ALARMS[slot - 1](None),)
        if slot == 6:
            updates += (keys.FLAT_MINUTES(flat_minutes),)
        link = self._live()

        def remember_flat() -> None:
            if slot != 6:
                return
            if flat_minutes is None:
                self._flat_expected = None
            else:
                body = bytes.fromhex(frame.decode("ascii"))
                self._flat_expected = (body[3], body[4], body[6], body[7], body[8])

        with self.sent_state(*updates):
            await self._async_send(frame, link=link, on_write=remember_flat)
        self._live(link)
        self._alarm_row = 0
        await cancellable(asyncio.sleep(0.2), self._coordinator.cancel_command)
        await self._async_send(codec.ALARM_QUERY, link=link, track=False)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        frame = (
            codec.clear_alarm(alarm.slot)
            if not alarm.enabled
            else codec.alarm(
                alarm.slot,
                alarm.hour,
                alarm.minute,
                {"zero_g": "0", "flat": "2", "massage": "1"}[alarm.wake_action],
                sum(1 << ((day + 1) % 7) for day in alarm.weekdays),
                True,
            )
        )
        await self._write_alarm_slot(alarm.slot, frame)

    async def sync_clock(self) -> None:
        await self._async_send(codec.local_clock(dt_util.now()))


async def build_controller(ctx: BuildContext) -> BedController:
    return SleepAssistantController(ctx.coordinator, app.selected(ctx.data))
