"""VivaSleep's app-local controls on the shared, session-fenced HHC runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from ...app_session import app_session
from ...codec import motomotion as codec
from ...command_scheduler import Delivery, delivered, note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid, setup_stopped
from ...profiles import vivasleep as app
from ...state_keys import LIGHT_LEVEL, LIGHT_TIMER_OPTION, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import require_controller
from ..catalog_buttons import catalog_button, save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
)
from .controller import ALARM, STRENGTH, BedgearController, Link, Request, select_transport
from .protocol import color_parameters, reported_color, token_fields

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...alarm import AlarmRequest
    from ...coordinator import AdjustableBedCoordinator
    from ..base import BedController
    from ..builder import BuildContext

SYNC_ENABLED = StateKey[bool | None]("vivasleep_sync_enabled")
SYNC_MODE = StateKey[str | None]("vivasleep_sync_mode")
SYNC_MODES = ("wireless", "wired")


async def sync_mode(controller: BedController, *, mode: str, confirmed: bool = False) -> None:
    await require_controller(controller, VivaSleepController).set_sync_mode(
        mode, confirmed=confirmed
    )


@dataclass(slots=True)
class LightSelection:
    rgb: tuple[int, int, int] | None = None
    level: int | None = None


class VivaSleepController(BedgearController):
    profile: app.VivaSleepProfile

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, profile: app.VivaSleepProfile
    ) -> None:
        super().__init__(coordinator, name=profile.name, profile=profile)
        self._last_tokens: tuple[str, ...] = ()
        self._light_selection = app_session(
            coordinator.hass, coordinator.address, ("vivasleep-light", profile.name), LightSelection
        )

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else ""

    def _select_transport(self, client: BleakClient) -> Link:
        try:
            return select_transport(client)
        except ValueError as err:
            raise BedNotConnectedError("vivasleep_receiver_missing") from err

    def _letter(self, letter: str) -> bytes | None:
        return self.profile.writer_bytes("$" + letter)

    def on_disconnect(self) -> None:
        self._link = None
        self._reset_session_state()

    def _reset_session_state(self) -> None:
        self._last_tokens = ()
        self._color_busy = None
        self._color_cancel = None
        super()._reset_session_state()

    def _parse_status_number(self, value: object) -> int | None:
        if isinstance(value, str):
            try:
                return app.decimal(value)
            except ValueError:
                pass
        return None

    @property
    def _observed_strength(self) -> int | None:
        value = self._parse_status_number(self._alarm[2]) if self._alarm else None
        return value if value in (0, 1, 2) else None

    def _on_rgb_report(self) -> None:
        if (
            self.profile.rgb
            and self._color_busy is None
            and self._rgb is not None
            and any(self._rgb)
        ):
            selected = self._light_selection
            expected = (
                reported_color(*color_parameters(selected.rgb, selected.level / 255))
                if selected.rgb is not None and selected.level is not None
                else None
            )
            if self._rgb != expected:
                selected.rgb, selected.level = self._rgb, 255

    def _status_fields(self, text: str) -> dict[str, object]:
        self._last_tokens = tuple(text.split(" "))
        fields = token_fields(
            text, alarm_indices=app.ALARM_FIELD_INDICES, parse_sync=self._parse_status_number
        )
        if "bind" in fields:
            value = fields.get("sync_type")
            if isinstance(value, int):
                self.forward_controller_state_updates(
                    SYNC_MODE(SYNC_MODES[value] if value in (0, 1) and self.profile.sync else None)
                )
            else:
                # The app mutates RGB/bind caches before int.parse throws. Retain
                # those updates, but neither acknowledge nor consume its suffix.
                self._receiver.buffer.clear()
        return fields

    @property
    def _reported_alarm_time(self) -> tuple[str, str] | None:
        if self._alarm is None or not self.profile.alarm:
            return None
        hour, minute = map(self._parse_status_number, self._alarm[:2])
        if hour is None or minute is None or hour > 23 or minute > 59:
            return None
        return self._alarm[0], self._alarm[1]

    def _publish(self) -> None:
        if self._coordinator.controller is not self:
            return
        time = self._reported_alarm_time
        rgb = self._rgb if self.profile.rgb else None
        timer = self._timer if self.profile.timer else None
        self.forward_controller_state_updates(
            ALARM(f"{app.decimal(time[0]):02d}:{app.decimal(time[1]):02d}" if time else None),
            STRENGTH(self._observed_strength if self.profile.alarm else None),
            UNDER_BED_LIGHTS_RGB(self._light_selection.rgb),
            UNDER_BED_LIGHTS_ON(any(rgb) if rgb is not None else None),
            LIGHT_LEVEL(self._light_selection.level if self.profile.brightness else None),
            LIGHT_TIMER_OPTION(
                "Off"
                if timer == 0
                else f"{timer} min"
                if timer is not None and timer <= app.TIMER_MAX_MINUTES
                else None
            ),
            SYNC_ENABLED(self._bind[1] if self._bind and self._bind[0] else None),
        )
        if self._link is None:
            self.forward_controller_state_updates(SYNC_MODE(None))

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            **super().protocol_diagnostics,
            "alarm_fields": self._alarm,
            "tokens": self._last_tokens,
        }

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return ()

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return ()  # Changing the coupling mode requires the confirmed buttons.

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        specs = []
        if self.profile.alarm:
            specs.extend(
                (
                    ControllerStateSensorSpec(
                        "vivasleep_alarm",
                        "bedgear_alarm",
                        ALARM,
                        "mdi:alarm",
                        entity_registry_enabled_default=True,
                    ),
                    ControllerStateSensorSpec(
                        "vivasleep_alarm_strength",
                        "vivasleep_alarm_strength",
                        STRENGTH,
                        "mdi:alarm",
                    ),
                )
            )
        if self.profile.sync:
            specs.append(
                ControllerStateSensorSpec(
                    "vivasleep_sync_mode", "vivasleep_sync_mode", SYNC_MODE, "mdi:sync"
                )
            )
        return tuple(specs)

    @property
    def sync_available(self) -> bool:
        return bool(
            self._link and self._link_is_current(self._link) and self._bind and self._bind[0]
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "vivasleep_sync_enabled",
                "vivasleep_sync_enabled",
                lambda ctrl, on: require_controller(ctrl, VivaSleepController).set_sync(on),
                state_key=SYNC_ENABLED,
                available_fn=lambda ctrl: (
                    isinstance(ctrl, VivaSleepController) and ctrl.sync_available
                ),
            ),
        )

    async def set_sync(self, enabled: bool) -> None:
        link = self._current()
        self._validate_sync()
        await self._send(
            codec.ascii_command(12 if enabled else 15),
            link,
            self._coordinator.cancel_command,
            before_dispatch=self._validate_sync,
        )

    def _validate_sync(self) -> None:
        if not self.sync_available:
            raise invalid("vivasleep_sync_unavailable")

    async def set_sync_mode(self, mode: str, *, confirmed: bool = False) -> None:
        if not self.profile.sync or mode not in SYNC_MODES or not confirmed:
            raise invalid("vivasleep_sync_confirmation")
        await self._send(
            codec.ascii_command(33049, SYNC_MODES.index(mode)),
            self._current(),
            self._coordinator.cancel_command,
        )

    @property
    def _extra_buttons(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        if self.profile.panel == "PanelE":
            specs.append(
                save_button(
                    "vivasleep_save_snore",
                    "Save anti-snore position",
                    lambda ctrl: require_controller(ctrl, VivaSleepController).save_snore(),
                )
            )
        if self.profile.sync:
            for mode in SYNC_MODES:
                spec = catalog_button(
                    "vivasleep_sync_" + mode,
                    f"Use {mode} synchronization",
                    partial(sync_mode, mode=mode),
                    requires_confirmation=True,
                    confirmed_press_fn=partial(sync_mode, mode=mode, confirmed=True),
                    enabled=True,
                )
                assert spec is not None
                specs.append(spec)
        return tuple(specs)

    async def save_snore(self) -> None:
        if self.profile.panel != "PanelE":
            raise invalid("hhc_control_unavailable")
        await self._send(self._letter("W"), self._current(), self._coordinator.cancel_command)

    async def press(self, key: str) -> None:
        if not any(c.key == key for c in self.profile.controls):
            raise invalid("hhc_control_unavailable")
        await super().press(key)

    async def program_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.profile.memory_slots:
            raise invalid("hhc_control_unavailable")
        await super().program_memory(memory_num)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("hhc_hold_unavailable")

    @property
    def supports_light_timer(self) -> bool:
        return self.profile.timer

    @property
    def light_timer_options(self) -> list[str]:
        return (
            ["Off", *(f"{n} min" for n in range(1, app.TIMER_MAX_MINUTES + 1))]
            if self.profile.timer
            else []
        )

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in self.light_timer_options:
            raise invalid("hhc_control_unavailable")
        minutes = 0 if timer_option == "Off" else int(timer_option.removesuffix(" min"))
        link, cancel = self._current(), self._coordinator.cancel_command
        with self.sent_state(
            LIGHT_TIMER_OPTION(timer_option), is_current=lambda: self._link_is_current(link)
        ):
            await self._settings_frame(
                codec.ascii_command(app.TIMER_COMMAND, minutes), link, cancel
            )

    async def _settings_frame(self, frame: bytes, link: Link, cancel: asyncio.Event) -> None:
        await self._send(self._letter("z"), link, cancel)
        if await self._wait(app.SETTINGS_DELAY_MS / 1000, cancel):
            await self._send(frame, link, cancel)
        else:
            note_frame_skipped()

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        super().validate_alarm(alarm)
        if not alarm.enabled and not alarm.time_provided and self._reported_alarm_time is None:
            raise invalid("alarm_time_required_to_turn_off", device_name=self._coordinator.name)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link, cancel = self._current(), self._coordinator.cancel_command
        time = self._reported_alarm_time if not alarm.enabled and not alarm.time_provided else None
        hour, minute = time if time else (f"{alarm.hour:02d}", f"{alarm.minute:02d}")
        strength = alarm.massage_intensity if alarm.enabled else 0
        with self.sent_state(
            ALARM(f"{app.decimal(hour):02d}:{app.decimal(minute):02d}"),
            STRENGTH(strength),
            is_current=lambda: self._link_is_current(link),
        ):
            await self._settings_frame(
                app.alarm_frame(hour, minute, strength),
                link,
                cancel,
            )

    @property
    def supports_lights(self) -> bool:
        return self.profile.rgb

    @property
    def supports_light_color_control(self) -> bool:
        return self.profile.rgb

    @property
    def supports_light_level_control(self) -> bool:
        return self.profile.brightness

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
    def light_level_max(self) -> int:
        return 255

    @property
    def default_light_rgb_color(self) -> tuple[int, int, int]:
        return (255, 255, 255)

    @property
    def current_light_rgb_color(self) -> tuple[int, int, int] | None:
        return self._light_selection.rgb

    async def lights_on(self) -> None:
        await self.set_light_color(self._light_selection.rgb or self.default_light_rgb_color)

    async def lights_off(self) -> None:
        await self.set_light_color_with_level((0, 0, 0), 255)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.set_light_color_with_level(
            rgb_color,
            self._light_selection.level if self._light_selection.level is not None else 255,
        )

    async def set_light_level(self, level: int) -> None:
        if not self.profile.brightness:
            raise invalid("hhc_control_unavailable")
        await self.set_light_color_with_level(
            self._light_selection.rgb or self.default_light_rgb_color, level
        )

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        if (
            not self.profile.rgb
            or type(level) is not int
            or not 0 <= level <= 255
            or not self.profile.brightness
            and level != 255
        ):
            raise invalid("hhc_control_unavailable")
        if len(rgb_color) != 3 or any(
            type(channel) is not int or not 0 <= channel <= 255 for channel in rgb_color
        ):
            raise invalid("hhc_control_unavailable")
        request = Request(operation="rgb", rgb=rgb_color, brightness=level / 255)
        link, cancel = self._current(), self._coordinator.cancel_command
        effective = reported_color(*color_parameters(rgb_color, request.brightness))

        selected_rgb = rgb_color if any(rgb_color) else self._light_selection.rgb
        selected_level = level if any(rgb_color) else self._light_selection.level

        def shown(delivery: Delivery) -> None:
            if not self._link_is_current(link):
                return
            if delivery is Delivery.SENT and any(rgb_color):
                self._light_selection.rgb, self._light_selection.level = rgb_color, level
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_RGB(None), UNDER_BED_LIGHTS_ON(None), LIGHT_LEVEL(None)
                )

        with (
            delivered(shown),
            self.sent_state(
                UNDER_BED_LIGHTS_RGB(selected_rgb),
                UNDER_BED_LIGHTS_ON(any(effective)),
                LIGHT_LEVEL(selected_level if self.profile.brightness else None),
                is_current=lambda: self._link_is_current(link),
            ),
        ):
            complete = False
            try:
                await self._change_color(request, link, cancel)
                complete = not cancel.is_set() and self._link_is_current(link)
            finally:
                if not complete:
                    note_frame_skipped()


async def build_controller(ctx: BuildContext) -> VivaSleepController:
    stored = ctx.data.get(CONF_BLE_DEVICE_NAME)
    observed = ctx.advertisement_local_name
    name = stored if isinstance(stored, str) else observed
    if name is None or not app.accepts_name(name) or observed is not None and observed != name:
        raise setup_stopped("vivasleep_name_mismatch")
    return VivaSleepController(ctx.coordinator, profile=app.VivaSleepProfile(name))
