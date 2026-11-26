"""The Sleep Assist Pro remote over a single Home Assistant BLE session."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.util import dt as dt_util

from ...card import CARD_LIGHT_TOGGLE, CARD_LIGHTING, CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS
from ...codec import keeson, sleep_assistant
from ...codec import sleep_assist_pro as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import sleep_assist_pro as app
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
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    massage_timer_sensor_spec,
)

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


COUNTDOWN: Final = StateKey[int | None]("sleep_assist_pro_massage_countdown")
RGB_LEVEL: Final = StateKey[str | None]("sleep_assist_pro_rgb_intensity")
_RGB_LEVELS: Final = {"20": 0.2, "60": 0.6, "100": 1.0}


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    receive: BleakGATTCharacteristic
    response: bool


def _action(name: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await require_controller(controller, SleepAssistProController).run_action(name)

    return run


class SleepAssistProController(ProfileExecution[app.Profile], BedController):
    """Use one discovered GATT tuple without inheriting other Keeson app state."""

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.Profile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._link: _Link | None = None
        self._subscription: object | None = None
        self._lamp: bool | None = None
        self._lamp_reported = asyncio.Event()
        self._hardware_218 = False
        self._rgb_color: tuple[int, int, int] | None = None
        self._rgb_level = "100"

    @property
    def control_characteristic_uuid(self) -> str:
        if self._link is not None:
            return self._link.write.uuid
        return app.TRANSPORTS[self.profile.route][0].write_uuid

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return self.profile.route in ("p2", "p5")

    def _live(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or (expected is not None and link is not expected)
            or link.client is not self.client
            or not link.client.is_connected
        ):
            raise BedNotConnectedError
        return link

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        candidates = {item.service_uuid: item for item in app.TRANSPORTS[self.profile.route]}
        subscription = "indicate" if self.profile.indication else "notify"
        for service in client.services:
            transport = candidates.get(service.uuid)
            if transport is None:
                if self.profile.route in ("p1", "p2") and service.uuid.startswith("6e4000"):
                    break
                continue
            write = service.get_characteristic(transport.write_uuid)
            receive = service.get_characteristic(transport.notify_uuid)
            if (
                write is not None
                and {"write", "write-without-response"}.intersection(write.properties)
                and receive is not None
                and subscription in receive.properties
            ):
                self._link = _Link(client, write, receive, "write" in write.properties)
                return
            break
        raise BleakError("Sleep Assist Pro GATT roles are missing for the selected device ID")

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscription is not None:
            return
        token = self._subscription = object()

        def receive(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._subscription is not token
                or self._link is not link
                or self.client is not link.client
            ):
                return
            if link.client.is_connected:
                frame = bytes(data)
                self.forward_raw_notification(link.receive.uuid, frame)
                self._receive(frame)

        try:
            if self.profile.indication:
                await link.client.start_notify(link.receive, receive, force_indicate=True)
            else:
                await link.client.start_notify(link.receive, receive)
            self._live(link)
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise

    async def stop_notify(self) -> None:
        link = self._link
        subscribed = self._subscription is not None
        self._subscription = None
        if (
            subscribed
            and link is not None
            and link.client is self.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.receive)

    def on_disconnect(self) -> None:
        self._link = None
        self._subscription = None
        self._lamp = None
        self._lamp_reported.clear()
        self._hardware_218 = False
        self._rgb_color = None
        self._rgb_level = "100"
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(None),
            UNDER_BED_LIGHTS_RGB(None),
            LIGHT_LEVEL(None),
            MASSAGE_TIMER_MINUTES(None),
            RGB_LEVEL(None),
            COUNTDOWN(None),
        )

    async def async_resume_session(self) -> None:
        await self.start_notify()

    async def async_after_connect(self, session: ControllerSession) -> None:
        if session.is_current() and (self.supports_light_state_feedback or self.supports_massage):
            await self.async_refresh_diagnostics()

    def _receive(self, data: bytes) -> None:
        route = self.profile.route
        if route in ("p1", "p2"):
            if (feedback := codec.base_feedback(data)) is not None:
                self._publish_feedback(feedback)
        elif route == "p3":
            for frame in sleep_assistant.split_notifications(data):
                if 11 <= len(frame) < 25 and frame[0] == 0x8B:
                    bt = sleep_assistant.version_fields(frame.hex(), 1)
                    mcu = sleep_assistant.version_fields(frame.hex(), 2)
                    self._hardware_218 = (
                        bt is not None
                        and mcu is not None
                        and float(bt) >= 2.18
                        and float(mcu) >= 2.05
                    )
                self._publish_feedback(codec.smart_feedback(frame, hardware_218=self._hardware_218))
                if (
                    self.supports_massage
                    and (
                        seconds := codec.smart_massage_timer(frame, hardware_218=self._hardware_218)
                    )
                    is not None
                ):
                    self.forward_controller_state_updates(COUNTDOWN(seconds))

    def _publish_feedback(self, feedback: codec.Feedback) -> None:
        if feedback.lamp is not None and self.profile.light:
            self._lamp = feedback.lamp
            self._lamp_reported.set()
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(feedback.lamp))
        if feedback.timer_minutes is not None and self.supports_massage:
            self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(feedback.timer_minutes))
        if feedback.brightness is not None and self.supports_light_level_control:
            self.forward_controller_state_updates(LIGHT_LEVEL(feedback.brightness))

    def _format_command_trace_payload(self, command: bytes) -> dict[str, object] | None:
        if self.profile.indication:
            # A device ID can cross a split-buffer boundary.
            return {"hex": "**REDACTED**", "length": len(command)}
        return super()._format_command_trace_payload(command)

    async def _send(
        self,
        link: _Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        track: bool = True,
        on_start: Callable[[], None] | None = None,
    ) -> bool:
        async def chunks() -> bool:
            # Bound the original packet, including its continuation chunks, inside
            # the shield so a backend retry cannot hold the command lane forever.
            async with asyncio.timeout(app.GATT_OPERATION_TIMEOUT_SECONDS):
                # Once dispatch starts, finish this buffer before a cancellation can
                # hand the command lane to the next write (including release).
                continuation = asyncio.Event()
                for offset in range(0, len(frame), codec.WRITE_CHUNK_SIZE):
                    written = False

                    def acknowledge() -> None:
                        nonlocal written
                        written = True

                    def admit(offset: int = offset) -> None:
                        self._live(link)
                        if offset == 0 and on_start is not None:
                            on_start()

                    await self._write_gatt_with_retry(
                        link.write.uuid,
                        frame[offset : offset + codec.WRITE_CHUNK_SIZE],
                        cancel_event=cancel if offset == 0 else continuation,
                        characteristic=link.write,
                        expected_client=link.client,
                        response=link.response,
                        before_write=admit,
                        track_command_write=track,
                        on_write=acknowledge,
                    )
                    if not written:
                        return False
                return True

        return await settled(chunks())

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        event = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for index in range(repeat_count):
            if event.is_set():
                return
            await self._send(link, command, event)
            if index + 1 < repeat_count:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), event)

    async def async_refresh_diagnostics(self) -> None:
        link = self._live()
        cancel = self._coordinator.cancel_command
        route = self.profile.route
        if route not in ("p4", "p5"):
            status = codec.release(route)
            assert status is not None
            await self._send(link, status, cancel, track=False)
        if self.supports_light_level_control:
            await self._send(link, sleep_assistant.light(), cancel, track=False)

    async def _release(self, link: _Link, delays_ms: tuple[int, ...]) -> None:
        frame = codec.release(self.profile.route, self.profile.device_id)
        if frame is None:
            return

        async def cleanup() -> None:
            for delay in delays_ms:
                if delay:
                    await asyncio.sleep(delay / 1000)
                if (
                    self._link is not link
                    or link.client is not self.client
                    or not link.client.is_connected
                ):
                    return
                await self._send(link, frame, asyncio.Event(), track=False)
            context = current_command_context()
            if context is not None and self.profile.route != "p2":
                context.cleanup_stop_sent = True

        await settled(cleanup())

    @property
    def _axes(self) -> tuple[tuple[str, str, str], ...]:
        controls = self.profile.controls
        axes = (
            ("head", "back", "back"),
            ("feet", "legs", "legs"),
            ("tilt", "head", "head"),
            ("side_b", "head", "sleep_assist_pro_side_b"),
            ("lumbar", "lumbar", "lumbar"),
        )
        return tuple((axis, key, label) for axis, key, label in axes if axis in controls)

    @property
    def supports_motor_control(self) -> bool:
        return bool(self._axes)

    @property
    def has_lumbar_support(self) -> bool:
        return "lumbar" in self.profile.controls

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in self.profile.controls

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.profile.controls

    @property
    def supports_massage(self) -> bool:
        return not app.MASSAGE.keys().isdisjoint(self.profile.controls)

    @property
    def supports_lights(self) -> bool:
        return self.profile.light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.profile.light

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.profile.light and not self.profile.indication

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return self.supports_light_state_feedback

    @property
    def supports_light_color_control(self) -> bool:
        return "rgb" in self.profile.controls

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.supports_light_color_control else None

    @property
    def publishes_rgb_light_state(self) -> bool:
        return self.supports_light_color_control

    @property
    def supports_light_level_control(self) -> bool:
        return "dimmer" in self.profile.controls

    @property
    def light_level_min(self) -> int:
        return 13

    @property
    def light_level_max(self) -> int:
        return 255

    @property
    def _allowed(self) -> frozenset[str]:
        allowed = set(self.profile.controls.intersection(app.WORDS))
        allowed.update(self.held_control_options)
        if self.profile.light:
            allowed.add("light_toggle")
        if "dawnhouse" in self.profile.controls:
            allowed.update(("bed_in", "bed_out"))
        return frozenset(allowed)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        motors = tuple(
            f"{'tilt' if axis == 'side_b' else axis}_{direction}"
            for axis, _, _ in self._axes
            for direction in ("up", "down")
        )
        dawn = (
            ("bed_up", "bed_down")
            if self.profile.route == "p4" and "dawnhouse" in self.profile.controls
            else ()
        )
        return (
            *motors,
            *dawn,
            *(action for action in app.PRESETS if action in self.profile.controls),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            self._motor_spec("tilt" if axis == "side_b" else axis, key, label)
            for axis, key, label in self._axes
        )

    @staticmethod
    def _motor_spec(axis: str, key: str, label: str) -> MotorControlSpec:
        up, down = f"{axis}_up", f"{axis}_down"
        return MotorControlSpec(
            key,
            label,
            _action(up),
            _action(down),
            lambda ctrl: ctrl.stop_all(),
            scheduler_resource="motor:*",
            hold=ControllerMotorHoldSpec(up, down, press_hold_ms=None, stop_scope="side"),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        if self.supports_light_state_feedback:
            specs.append(
                ControllerButtonSpec(
                    "sleep_assist_pro_light_toggle",
                    "Toggle under-bed light",
                    _action("light_toggle"),
                    translation_key="sleep_assist_pro_light_toggle",
                    card=CARD_LIGHT_TOGGLE,
                    cancel_movement=False,
                )
            )
        for action, label in app.MASSAGE.items():
            if action in self.profile.controls:
                specs.append(
                    ControllerButtonSpec(
                        f"sleep_assist_pro_{action}",
                        label,
                        _action(action),
                        translation_key=(
                            "sleep_assist_pro_massage_timer"
                            if action == "massage_timer"
                            else MASSAGE_KEY
                        ),
                        translation_placeholders=None
                        if action == "massage_timer"
                        else {"action": label},
                        card=CARD_MASSAGE_TIMER if action == "massage_timer" else CARD_MASSAGE,
                        cancel_movement=False,
                    )
                )
        presets = {
            **app.PRESETS,
            "demonstration": "Demonstration",
            "bed_in": "Bed in",
            "bed_out": "Bed out",
            "bed_up": "Bed up",
            "bed_down": "Bed down",
        }
        for action, label in presets.items():
            if action in self._allowed:
                hold = ControllerHoldSpec(action) if action in self.held_control_options else None
                specs.append(
                    ControllerButtonSpec(
                        f"sleep_assist_pro_{action}",
                        label,
                        _action(action),
                        translation_key=PRESET_KEY,
                        translation_placeholders={"action": label},
                        card=CARD_PRESETS,
                        hold=hold,
                        invalidates_position=True,
                        scheduler_resource="motor:*",
                    )
                )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self.supports_massage or self.profile.indication:
            return ()
        timer = massage_timer_sensor_spec(
            "sleep_assist_pro_massage_timer",
            "sleep_assist_pro_massage_timer",
            MASSAGE_TIMER_MINUTES,
            card=CARD_MASSAGE_TIMER,
        )
        if self.profile.route != "p3":
            return (timer,)
        return (
            timer,
            ControllerStateSensorSpec(
                "sleep_assist_pro_massage_countdown",
                "sleep_assist_pro_massage_countdown",
                COUNTDOWN,
                "mdi:timer-sand",
                native_unit_of_measurement="s",
                device_class=SensorDeviceClass.DURATION,
            ),
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.supports_light_color_control:
            return ()
        return (
            ControllerSelectSpec(
                "sleep_assist_pro_rgb_intensity",
                "sleep_assist_pro_rgb_intensity",
                RGB_LEVEL,
                tuple(_RGB_LEVELS),
                lambda ctrl, value: require_controller(
                    ctrl, SleepAssistProController
                ).set_rgb_intensity(value),
                card=CARD_LIGHTING,
            ),
        )

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.route == "p3"

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise invalid("sleep_assist_pro_control_unavailable")
        await self._send(
            self._live(),
            sleep_assistant.local_clock(dt_util.now()),
            self._coordinator.cancel_command,
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("sleep_assist_pro_control_unavailable")
        await self.run_action(control, duration_ms=duration_ms)

    async def run_action(self, action: str, *, duration_ms: int | None = None) -> None:
        if action not in self._allowed:
            raise invalid("sleep_assist_pro_control_unavailable")
        link = self._live()
        event = self._coordinator.cancel_command
        route = self.profile.route
        named_preset = action in app.PRESETS
        motion = action in self.held_control_options and not named_preset
        held = motion or (duration_ms is not None and duration_ms > 200)
        start_delay = 0 if motion or action == "flat" else 200 if named_preset else 400
        if held:
            delays = (800, 500) if named_preset and route in ("p1", "p2", "p3") else (800,)
            if named_preset and self.profile.indication:
                delays = ()
        elif action == "flat" or named_preset:
            delays = (800,) if route == "p3" else ()
        else:
            # Treat an HA button as a completed tap. Follow-ups are relative to
            # its start, while the write itself waited for the tap decision.
            delays = (900, 200) if route == "p3" else (900,)
        if start_delay:
            await cancellable(asyncio.sleep(start_delay / 1000), event)

        attempted = False

        def started() -> None:
            nonlocal attempted
            attempted = True
            if action == "light_toggle":
                self._lamp = None
                self._lamp_reported.clear()
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))

        interval = app.MOTION_INTERVAL_MS
        count = 1
        if held:
            count = self.leased_hold_refreshes(interval) or (
                (duration_ms - start_delay + interval - 1) // interval
                if duration_ms is not None
                else self._coordinator.motor_pulse_count
            )
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        try:
            for _ in range(count):
                if event.is_set():
                    break
                frame = codec.key(
                    route, app.WORDS[action], self.profile.device_id, epoch_seconds=int(time.time())
                )
                await self._send(link, frame, event, on_start=started)
                if held:
                    deadline += interval / 1000
                    await cancellable(asyncio.sleep(max(0, deadline - loop.time())), event)
        finally:
            if attempted and delays:
                await self._release(link, delays)

    async def stop_all(self) -> None:
        if (context := current_command_context()) is not None:
            for preempted in context.preempted_contexts:
                if preempted.cleanup_stop_sent:
                    preempted.cleanup_stop_sent = False
                    return
        await self._release(self._live(), (0,))

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all
    move_tilt_stop = move_lumbar_stop = stop_all

    async def move_head_up(self) -> None:
        await self.run_action("head_up")

    async def move_head_down(self) -> None:
        await self.run_action("head_down")

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_feet_up(self) -> None:
        await self.run_action("feet_up")

    async def move_feet_down(self) -> None:
        await self.run_action("feet_down")

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

    async def preset_flat(self) -> None:
        await self.run_action("flat")

    async def preset_zero_g(self) -> None:
        await self.run_action("zero_g")

    async def preset_memory(self, memory_num: int) -> None:
        raise invalid("sleep_assist_pro_control_unavailable")

    async def program_memory(self, memory_num: int) -> None:
        raise invalid("sleep_assist_pro_control_unavailable")

    async def lights_toggle(self) -> None:
        await self.run_action("light_toggle")

    async def _reported_lamp(self, link: _Link) -> bool:
        if self._lamp is None:
            await self.async_refresh_diagnostics()
            try:
                async with asyncio.timeout(2):
                    await cancellable(self._lamp_reported.wait(), self._coordinator.cancel_command)
            except TimeoutError as err:
                raise invalid("light_state_unknown") from err
            self._live(link)
        if self._lamp is None:
            raise invalid("light_state_unknown")
        return self._lamp

    async def _toggle_light_to(self, on: bool) -> None:
        if not self.supports_light_state_feedback:
            raise invalid("sleep_assist_pro_control_unavailable")
        link = self._live()
        if await self._reported_lamp(link) is not on:
            await self.lights_toggle()

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self.supports_light_color_control or any(
            not 0 <= channel <= 255 for channel in rgb_color
        ):
            raise invalid("sleep_assist_pro_control_unavailable")
        await self._send_rgb(rgb_color, self._rgb_level)

    async def set_rgb_intensity(self, value: str) -> None:
        if not self.supports_light_color_control or value not in _RGB_LEVELS:
            raise invalid("sleep_assist_pro_control_unavailable")
        if self._rgb_color is None:
            raise invalid("sleep_assist_pro_color_unknown")
        await self._send_rgb(self._rgb_color, value)

    async def _send_rgb(self, color: tuple[int, int, int], level: str) -> None:
        link = self._live()
        if not await self._reported_lamp(link):
            raise invalid("sleep_assist_pro_light_off")
        frame = (
            sleep_assistant.rgb_channels(*color, _RGB_LEVELS[level])
            if self.profile.route == "p3"
            else keeson.rgb(sleep_assistant.scaled_rgb(color, _RGB_LEVELS[level]))
        )
        with self.sent_state(UNDER_BED_LIGHTS_RGB(color), RGB_LEVEL(level)):
            if await self._send(link, frame, self._coordinator.cancel_command):
                self._live(link)
                self._rgb_color = color
                self._rgb_level = level

    def _validate_light_level(self, level: int) -> None:
        if (
            not self.supports_light_level_control
            or not self.light_level_min <= level <= self.light_level_max
        ):
            raise invalid("sleep_assist_pro_control_unavailable")

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        self._validate_light_level(level)
        await super().set_light_color_with_level(rgb_color, level)

    async def set_light_level(self, level: int) -> None:
        self._validate_light_level(level)
        link = self._live()
        if not await self._reported_lamp(link):
            raise invalid("sleep_assist_pro_light_off")
        with self.sent_state(LIGHT_LEVEL(level)):
            sent = await self._send(
                link, sleep_assistant.light(level, query=False), self._coordinator.cancel_command
            )
        if sent:
            await self._release(link, (200,))


async def build_controller(ctx: BuildContext) -> SleepAssistProController:
    return SleepAssistProController(ctx.coordinator, app.selected(ctx.data))
