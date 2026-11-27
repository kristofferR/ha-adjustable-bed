"""ErgoSportive's explicitly selected direct BLE subset over the AA codec."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_PRESETS
from ...codec import sleep_assistant as codec
from ...command_scheduler import current_command_context
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...profiles import ergosportive as app
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    sleep_flag_binary_sensor_spec,
    sleep_rate_sensor_spec,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

HEART: Final = StateKey[int | None]("ergosportive_heart_rate")
BREATHING: Final = StateKey[int | None]("ergosportive_breathing_rate")
PRESENCE: Final = StateKey[bool | None]("ergosportive_presence")
TWITCH: Final = StateKey[int | None]("ergosportive_twitch")
BRIGHTNESS: Final = StateKey[int | None]("ergosportive_brightness")


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool


def select_link(client: BleakClient) -> Link:
    """Validate exactly the audited UART tuple in setup and runtime."""
    for service in client.services:
        if service.uuid.lower() != codec.SERVICE:
            continue
        write, notify = (
            service.get_characteristic(codec.WRITE),
            service.get_characteristic(codec.NOTIFY),
        )
        if (
            write is not None
            and notify is not None
            and "notify" in notify.properties
            and {"write", "write-without-response"}.intersection(write.properties)
        ):
            return Link(client, write, notify, "write" in write.properties)
    raise BedNotConnectedError("ergosportive_gatt")


def _action(name: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await require_controller(controller, ErgoSportiveController).run_action(name)

    return run


class ErgoSportiveController(ProfileExecution[app.Profile], BedController):
    """No companion-app session, implicit model selection or cross-app gates."""

    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.Profile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._address = coordinator.address.upper()
        self._link: Link | None = None
        self._subscription: object | None = None
        self._sensor = codec.ErgoSportiveNormalSensor()

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
        return True

    def _live(self, expected: Link | None = None, *, cleanup: bool = False) -> Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or link.client is not self.client
            or not link.client.is_connected
            or self._coordinator.controller is not self
            or self._coordinator.address.upper() != self._address
        ):
            raise BedNotConnectedError("ergosportive_session")
        if cleanup:
            return link
        try:
            selected = app.selected(self._coordinator.entry.data)
        except ValueError as err:
            raise BedNotConnectedError("ergosportive_session") from err
        if selected != self.profile:
            raise BedNotConnectedError("ergosportive_session")
        return link

    def _owns_link(self, link: Link, token: object | None) -> bool:
        try:
            self._live(link, cleanup=True)
        except ConnectionError:
            return False
        return token is not None and self._subscription is token

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError("ergosportive_session")
        self._link = select_link(client)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        if self._subscription is not None:
            return
        token = object()

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._subscription is not token or sender.handle != link.notify.handle:
                return
            try:
                self._live(link)
            except ConnectionError:
                return
            packet = bytes(data)
            self.forward_raw_notification(link.notify.uuid, packet)
            if self.profile.old_dsp_normal:
                for frame in codec.split_notifications(packet):
                    if self._sensor.feed(frame):
                        s = self._sensor
                        self.forward_controller_state_updates(
                            HEART(s.heart),
                            BREATHING(s.respiration),
                            PRESENCE(s.presence),
                            TWITCH(s.twitch),
                        )

        try:
            await link.client.start_notify(link.notify, receive)
            self._live(link)
            self._subscription = token
        except BaseException:
            if self._subscription is token:
                self._subscription = None
            raise

    async def stop_notify(self) -> None:
        link, subscribed = self._link, self._subscription is not None
        self._subscription = None
        self.invalidate_diagnostics()
        if (
            link is not None
            and subscribed
            and link.client is self.client
            and link.client.is_connected
        ):
            await link.client.stop_notify(link.notify)

    def invalidate_diagnostics(self) -> None:
        self._sensor = codec.ErgoSportiveNormalSensor()
        self.forward_controller_state_updates(
            HEART(None), BREATHING(None), PRESENCE(None), TWITCH(None), BRIGHTNESS(None)
        )

    def on_disconnect(self) -> None:
        self._link, self._subscription = None, None
        self.invalidate_diagnostics()

    async def _send(
        self,
        link: Link,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        subscription: object | None,
        cleanup: bool = False,
        on_start: Callable[[], None] | None = None,
        deadline: float | None = None,
    ) -> None:
        token = subscription
        context = current_command_context()
        caller = asyncio.current_task()
        written = False

        def delivered() -> None:
            nonlocal written
            written = True

        def admit() -> None:
            self._live(link, cleanup=cleanup)
            if token is None or self._subscription is not token:
                raise BedNotConnectedError("ergosportive_subscription")
            if not cleanup and (
                cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() >= deadline
                or caller is not None
                and caller.cancelling()
                or context is not None
                and (
                    not context.active
                    or context.caller_is_cancelling is not None
                    and context.caller_is_cancelling()
                    or context.hold_deadline is not None
                    and asyncio.get_running_loop().time() >= context.hold_deadline
                )
            ):
                raise asyncio.CancelledError
            if on_start is not None:
                on_start()

        async def send() -> None:
            await self._write_gatt_with_retry(
                link.write.uuid,
                frame,
                cancel_event=cancel,
                characteristic=link.write,
                expected_client=link.client,
                response=link.response,
                before_write=admit,
                on_write=delivered,
                track_command_write=not cleanup,
            )

        await settled(send())
        if not written:
            raise asyncio.CancelledError

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        # The caller owns protocol cleanup; arbitrary public raw frames are not exposed.
        link = self._live()
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        token = self._subscription
        for index in range(repeat_count):
            await self._send(link, command, cancel, subscription=token)
            if index + 1 < repeat_count:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)

    async def _release(
        self, link: Link, subscription: object | None, *, brightness: bool = False
    ) -> None:
        token = subscription

        async def cleanup() -> None:
            try:
                self._live(link, cleanup=True)
                if token is None or self._subscription is not token:
                    return
            except ConnectionError:
                return
            origin = asyncio.get_running_loop().time()
            await asyncio.sleep(
                (app.BRIGHTNESS_RELEASE_MS if brightness else app.RELEASE_MS) / 1000
            )
            if self._subscription is not token:
                return
            try:
                await self._send(
                    link, codec.instruction(0), asyncio.Event(), subscription=token, cleanup=True
                )
            finally:
                # The app schedules this independently at800ms. A slow/failed
                # neutral write must neither overlap it nor shift its deadline.
                if (
                    not brightness
                    and self.profile.secondary_release
                    and self._subscription is token
                ):
                    await asyncio.sleep(
                        max(0, origin + app.SECONDARY_MS / 1000 - asyncio.get_running_loop().time())
                    )
                    if self._subscription is token:
                        await self._send(
                            link,
                            codec.ergosportive_secondary_release(),
                            asyncio.Event(),
                            subscription=token,
                            cleanup=True,
                        )
            if (
                self._subscription is token
                and self._link is link
                and (context := current_command_context()) is not None
            ):
                context.cleanup_stop_sent = True

        await settled(cleanup())

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{d}"
            for axis in ("head", "feet", "tilt")
            if axis in self.profile.controls
            for d in ("up", "down")
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 100 <= duration_ms <= 30000
        ):
            raise invalid("ergosportive_control")

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._live()
        if self._subscription is None:
            raise BedNotConnectedError("ergosportive_subscription")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.run_action(control, duration_ms=duration_ms)

    async def run_action(self, action: str, *, duration_ms: int | None = None) -> None:
        motion = action in self.held_control_options
        if action not in app.WORDS or not (motion or action in self.profile.controls):
            raise invalid("ergosportive_control")
        link = self._live()
        cancel = self._coordinator.cancel_command
        token = self._subscription
        attempted = False

        def dispatched() -> None:
            nonlocal attempted
            attempted = True

        count = 1
        refreshes = self.leased_hold_refreshes(app.REFRESH_MS) if motion else None
        if motion:
            count = refreshes or (
                -(-duration_ms // app.REFRESH_MS)
                if duration_ms is not None
                else self._coordinator.motor_pulse_count
            )
        next_tick = asyncio.get_running_loop().time()
        end = (
            next_tick + duration_ms / 1000
            if motion and duration_ms is not None and not refreshes
            else None
        )
        try:
            for _ in range(count):
                if end is not None and asyncio.get_running_loop().time() >= end:
                    break
                await self._send(
                    link,
                    codec.instruction(app.WORDS[action]),
                    cancel,
                    subscription=token,
                    on_start=dispatched,
                    deadline=end,
                )
                if motion:
                    next_tick += app.REFRESH_MS / 1000
                    await cancellable(
                        asyncio.sleep(
                            max(0, min(next_tick, end) - asyncio.get_running_loop().time())
                            if end is not None
                            else max(0, next_tick - asyncio.get_running_loop().time())
                        ),
                        cancel,
                    )
        finally:
            if attempted:
                await self._release(link, token)

    async def stop_all(self) -> None:
        if (context := current_command_context()) is not None:
            for previous in context.preempted_contexts:
                if previous.cleanup_stop_sent:
                    previous.cleanup_stop_sent = False
                    return
        await self._release(self._live(), self._subscription)

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all
    move_tilt_stop = stop_all

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

    async def preset_flat(self) -> None:
        await self.run_action("flat")

    async def preset_zero_g(self) -> None:
        await self.run_action("zero_g")

    async def preset_memory(self, memory_num: int) -> None:
        raise invalid("ergosportive_memory_gesture_unresolved")

    async def program_memory(self, memory_num: int) -> None:
        raise invalid("ergosportive_memory_gesture_unresolved")

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in self.profile.controls

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self.profile.controls

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.held_control_options)

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                label,
                _action(f"{wire}_up"),
                _action(f"{wire}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{wire}_up",
                    f"{wire}_down",
                    stop_scope="side",
                    press_is_native=True,
                    release_delay_ms=app.SECONDARY_MS
                    if self.profile.secondary_release
                    else app.RELEASE_MS,
                ),
            )
            for axis, wire, label in (
                ("back", "head", "back"),
                ("legs", "feet", "legs"),
                ("tilt", "tilt", "head"),
            )
            if wire in self.profile.controls
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                f"ergosportive_{name}",
                label,
                _action(name),
                translation_key=f"ergosportive_{name}",
                scheduler_resource="*",
                card=CARD_LIGHTING
                if name == "lamp"
                else CARD_PRESETS
                if name.startswith("position_")
                else CARD_MASSAGE,
            )
            for name, label in app.ACTIONS.items()
            if name in self.profile.controls
        )

    async def set_brightness(self, value: float) -> None:
        if (
            "brightness" not in self.profile.controls
            or not float(value).is_integer()
            or not 1 <= value <= app.BRIGHTNESS_MAX
        ):
            raise invalid("ergosportive_brightness")
        link = self._live()
        token = self._subscription
        attempted = False

        def dispatched() -> None:
            nonlocal attempted
            attempted = True

        try:
            with self.sent_state(
                BRIGHTNESS(int(value)), is_current=lambda: self._owns_link(link, token)
            ):
                await self._send(
                    link,
                    codec.light(int(value), False),
                    self._coordinator.cancel_command,
                    subscription=token,
                    on_start=dispatched,
                )
        finally:
            if attempted:
                await self._release(link, token, brightness=True)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            (
                ControllerNumberSpec(
                    "ergosportive_brightness",
                    "ergosportive_brightness",
                    BRIGHTNESS,
                    1,
                    app.BRIGHTNESS_MAX,
                    1,
                    lambda c, v: require_controller(c, ErgoSportiveController).set_brightness(v),
                    assumed_state=True,
                    card=CARD_LIGHTING,
                ),
            )
            if "brightness" in self.profile.controls
            else ()
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            (
                sleep_rate_sensor_spec("heart_rate", "ergosportive_heart_rate", HEART),
                sleep_rate_sensor_spec("breathing_rate", "ergosportive_breathing_rate", BREATHING),
                ControllerStateSensorSpec(
                    "ergosportive_twitch",
                    "ergosportive_twitch",
                    TWITCH,
                    "mdi:motion-sensor",
                    entity_registry_enabled_default=True,
                    entity_category=None,
                ),
            )
            if self.profile.old_dsp_normal
            else ()
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            (
                sleep_flag_binary_sensor_spec("bed_presence", "ergosportive_presence", PRESENCE),
            )
            if self.profile.old_dsp_normal
            else ()
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "ErgoSportive 2.5.5",
            "source": "PARTIAL",
            "hardware": "UNVERIFIED",
            "selected_release": self.profile.key,
            "old_dsp_normal": self.profile.old_dsp_normal,
            "controls": sorted(self.profile.controls),
            "automatic_firmware_model_selection": False,
        }


async def build_controller(ctx: BuildContext) -> ErgoSportiveController:
    return ErgoSportiveController(
        ctx.coordinator, app.selected({**ctx.data, "protocol_variant": ctx.variant})
    )
