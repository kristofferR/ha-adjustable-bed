"""ErgoBed Control on the shared HHC letter session."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ...card import CARD_LIGHTING
from ...codec.motomotion import TIMER_PREFIX
from ...command_scheduler import note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid, setup_stopped
from ...profiles.ergobed import (
    CHARACTERISTIC_MARKER,
    COLOR_COMMANDS,
    SERVICE_MARKER,
    SETTINGS_INTERVAL_MS,
    STARTUP_DELAY_MS,
    TIMER_MAX_SECONDS,
    ErgoBedProfile,
    alarm_frame,
    clock_frame,
    color_frame,
    eligible,
    timer_frame,
)
from ...state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import require_controller
from ..entity_specs import ControllerNumberSpec
from ..motomotion.protocol import decimal
from .controller import ALARM, STRENGTH, BedgearController, Link
from .protocol import ErgoBedReceiver

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...alarm import AlarmRequest
    from ...coordinator import AdjustableBedCoordinator
    from ..base import BedController
    from ..builder import BuildContext
    from ..lifecycle import ControllerSession

_LOGGER = logging.getLogger(__name__)
LIGHT_TIMER = StateKey[int | None]("ergobed_light_timer")


class ErgoBedController(BedgearController):
    profile: ErgoBedProfile
    _receiver_type = ErgoBedReceiver
    _timer_max = TIMER_MAX_SECONDS

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: ErgoBedProfile) -> None:
        super().__init__(coordinator, name=profile.name, profile=profile)
        self._startup_task: asyncio.Task[None] | None = None

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    def _select_transport(self, client: BleakClient) -> Link:
        chars = [
            char
            for service in client.services
            if SERVICE_MARKER in service.uuid.lower()
            for char in service.characteristics
            if CHARACTERISTIC_MARKER in char.uuid.lower()
        ]
        if not chars or not {"notify", "write-without-response"}.issubset(chars[-1].properties):
            raise BedNotConnectedError("ergobed_receiver_missing")
        return Link(client, chars[-1], (chars[-1],))

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.alarm

    async def sync_clock(self) -> None:
        await self._sync_clock(self._current())

    async def _sync_clock(self, link: Link) -> None:
        cancel = self._coordinator.cancel_command
        await self._send(TIMER_PREFIX, link, cancel)
        await self._send(clock_frame(dt_util.now()), link, cancel)

    async def async_after_connect(self, session: ControllerSession) -> None:
        if self.profile.alarm:
            self._startup_task = self._coordinator.entry.async_create_background_task(
                session.hass, self._startup(session, self._current()), "ErgoBed clock and status"
            )

    async def _startup(self, session: ControllerSession, link: Link) -> None:
        def current() -> bool:
            return session.is_current() and self._link_is_current(link)

        async def initialize(controller: BedController) -> None:
            if controller is self and current():
                await self._sync_clock(link)

        try:
            await asyncio.sleep(STARTUP_DELAY_MS / 1000)
            if current():
                await self._coordinator.async_execute_controller_query(
                    initialize, skip_disconnect=True, run_if=current, preserve_idle_deadline=True
                )
        except (BleakError, ConnectionError, RuntimeError, TimeoutError) as error:
            _LOGGER.debug("ErgoBed startup ended: %s", error)
        finally:
            if self._startup_task is asyncio.current_task():
                self._startup_task = None

    def _reset_session_state(self) -> None:
        if self._startup_task is not None:
            self._startup_task.cancel()
            self._startup_task = None
        super()._reset_session_state()

    def on_disconnect(self) -> None:
        self._link = None
        self._reset_session_state()

    async def stop_all(self) -> None:
        # The coordinator ends the held refresh. Massage stop is a separate button.
        return

    def _parse_status_number(self, value: object) -> int | None:
        if isinstance(value, str):
            try:
                return decimal(value)
            except ValueError:
                pass
        return None

    @property
    def _reported_alarm_time(self) -> tuple[str, str] | None:
        if not self.profile.alarm or self._alarm is None:
            return None
        hour, minute = map(self._parse_status_number, self._alarm[:2])
        if hour is not None and minute is not None and hour < 24 and minute < 60:
            return self._alarm[0], self._alarm[1]
        return None

    def _publish(self) -> None:
        alarm_time = self._reported_alarm_time
        rgb = self._rgb if self.profile.rgb else None
        self.forward_controller_state_updates(
            ALARM(":".join(alarm_time) if alarm_time is not None else None),
            STRENGTH(self._observed_strength if self.profile.alarm else None),
            LIGHT_TIMER(self._timer),
            UNDER_BED_LIGHTS_RGB(rgb if rgb is not None and any(rgb) else None),
            UNDER_BED_LIGHTS_ON(any(rgb) if rgb is not None else None),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {"layout": self.profile.panel, "rgb": self._rgb, "light_seconds": self._timer}

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return (
            ControllerNumberSpec(
                "ergobed_light_timer",
                "ergobed_light_timer",
                LIGHT_TIMER,
                0,
                TIMER_MAX_SECONDS,
                1,
                lambda ctrl, value: require_controller(ctrl, ErgoBedController).set_timer(value),
                "s",
                card=CARD_LIGHTING,
            ),
        )

    async def _write_settings(self, frames: tuple[bytes, ...]) -> None:
        link, cancel = self._current(), self._coordinator.cancel_command
        for index, frame in enumerate(frames):
            if index and not await self._wait(SETTINGS_INTERVAL_MS / 1000, cancel):
                note_frame_skipped()
                return
            await self._send(frame, link, cancel)

    async def set_timer(self, seconds: float) -> None:
        if not 0 <= seconds <= TIMER_MAX_SECONDS:
            raise invalid("value_out_of_range", min=0, max=TIMER_MAX_SECONDS, step=1)
        await self._write_settings((TIMER_PREFIX, timer_frame(seconds)))

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        super().validate_alarm(alarm)
        if not alarm.enabled and not alarm.time_provided and self._reported_alarm_time is None:
            raise invalid("alarm_time_required_to_turn_off", device_name=self._coordinator.name)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        hour, minute = alarm.hour, alarm.minute
        if not alarm.enabled and not alarm.time_provided:
            observed = self._reported_alarm_time
            assert observed is not None
            hour, minute = decimal(observed[0]), decimal(observed[1])
        strength = alarm.massage_intensity if alarm.enabled else 0
        await self._write_settings((TIMER_PREFIX, alarm_frame(hour, minute, strength)))

    @property
    def supports_lights(self) -> bool:
        return self.profile.light or self.profile.rgb

    @property
    def supports_light_color_control(self) -> bool:
        return self.profile.rgb

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.rgb

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return False

    @property
    def publishes_rgb_light_state(self) -> bool:
        return self.profile.rgb

    @property
    def preserves_unknown_rgb_power(self) -> bool:
        return self.profile.rgb

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.profile.rgb else None

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int]:
        return (255, 255, 255)

    async def lights_on(self) -> None:
        await self.set_light_color(self._rgb if self._rgb and any(self._rgb) else (255, 255, 255))

    async def lights_off(self) -> None:
        await self.set_light_color((0, 0, 0))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        if not self.profile.rgb:
            raise invalid("hhc_control_unavailable")
        frames = tuple(
            frame
            for command, value in zip(COLOR_COMMANDS, rgb_color, strict=True)
            for frame in (TIMER_PREFIX, color_frame(command, value))
        )
        await self._write_settings(frames)


async def build_controller(ctx: BuildContext) -> ErgoBedController:
    saved = ctx.data.get(CONF_BLE_DEVICE_NAME)
    observed = ctx.advertisement_local_name
    name = saved if isinstance(saved, str) else observed
    if name is None or not eligible(name) or (observed is not None and observed != name):
        raise setup_stopped("ergobed_name_mismatch")
    return ErgoBedController(ctx.coordinator, profile=ErgoBedProfile(name))
