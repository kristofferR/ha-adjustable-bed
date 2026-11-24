"""MoodBase controls on the shared HHC letter session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...card import CardPlacement, CardRole, CardSection
from ...codec import motomotion as codec
from ...command_scheduler import Delivery, delivered, note_frame_skipped
from ...const import CONF_BLE_DEVICE_NAME
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid, setup_stopped
from ...profiles.bedgear import eligible
from ...profiles.moodbase import (
    CHARACTERISTIC_MARKER,
    CHARACTERISTIC_UUID,
    COLOR_COMMANDS,
    COLOR_INTERVAL_MS,
    SAVE_SNORE,
    SERVICE_MARKER,
    SETTINGS_DELAY_MS,
    SYNC_DISABLE,
    SYNC_ENABLE,
    SYNC_MODE_COMMAND,
    TIMER_COMMAND,
    TIMER_DEFAULT_MINUTES,
    TIMER_MAX_MINUTES,
    VIBRATION_MAX,
    MoodBaseProfile,
    lighting_frame,
)
from ...state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from ..base import require_controller
from ..builder import BuildContext
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerSwitchSpec,
)
from ..motomotion.protocol import decimal
from .controller import TIMER, BedgearController, Link
from .protocol import color_parameters, reported_color, token_fields

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

TIMER_ENABLED = StateKey[bool | None]("moodbase_light_timer_enabled")
VIBRATION_LEVEL = StateKey[int | None]("moodbase_vibration")
SYNC_ENABLED = StateKey[bool | None]("moodbase_sync_enabled")
SYNC_MODE = StateKey[str | None]("moodbase_sync_mode")
SYNC_MODES = ("wireless", "wired")


class MoodBaseController(BedgearController):
    profile: MoodBaseProfile

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: MoodBaseProfile) -> None:
        super().__init__(coordinator, name=profile.name, profile=profile)
        self._color_level: int | None = None
        self._selected_rgb: tuple[int, int, int] | None = None
        self._writing_rgb = False

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.write.uuid if self._link else CHARACTERISTIC_UUID

    def _select_transport(self, client: BleakClient) -> Link:
        services = [s for s in client.services if SERVICE_MARKER in s.uuid.lower()]
        if not services:
            raise BedNotConnectedError("moodbase_receiver_missing")
        matches = [
            char
            for service in services
            for char in service.characteristics
            if CHARACTERISTIC_MARKER in char.uuid.lower()
        ]
        writes = [
            char
            for char in services[-1].characteristics
            if CHARACTERISTIC_MARKER in char.uuid.lower()
        ]
        notify = tuple(char for char in matches if "notify" in char.properties)
        if not writes or "write-without-response" not in writes[-1].properties or not notify:
            raise BedNotConnectedError("moodbase_receiver_missing")
        return Link(client, writes[-1], notify)

    def _parse_status_number(self, value: object) -> int | None:
        if isinstance(value, str):
            try:
                return decimal(value)
            except ValueError:
                return None
        return None

    def _status_fields(self, text: str) -> dict[str, object]:
        fields = token_fields(
            text, alarm_indices=self.profile.alarm_indices, parse_sync=self._parse_status_number
        )
        if "bind" in fields:
            mode = fields.get("sync_type")
            if not isinstance(mode, int):
                # Bind flags precede sync parsing. A malformed sync type
                # prevents completion and discards any same-notification suffix.
                self._receiver.buffer.clear()
            elif self.profile.sync:
                self.forward_controller_state_updates(
                    SYNC_MODE(SYNC_MODES[mode] if mode in (0, 1) else None)
                )
        return fields

    @property
    def _reported_alarm_time(self) -> tuple[str, str] | None:
        if self._alarm is None:
            return None
        hour, minute, _ = map(self._parse_status_number, self._alarm)
        if hour is None or minute is None or hour >= 24 or minute >= 60:
            return None
        return f"{hour:02d}", f"{minute:02d}"

    def on_disconnect(self) -> None:
        self._link = None
        self._reset_session_state()

    def _publish(self) -> None:
        if self._coordinator.controller is not self:
            return
        super()._publish()
        self.forward_controller_state_updates(
            TIMER_ENABLED(None if self._timer is None else self._timer != 0),
            SYNC_ENABLED(self._bind[1] if self._bind and self._bind[0] else None),
        )
        if self._link is None:
            self._selected_rgb, self._color_level = None, None
            self.forward_controller_state_updates(
                SYNC_MODE(None),
                VIBRATION_LEVEL(None),
                LIGHT_LEVEL(None),
                UNDER_BED_LIGHTS_ON(None),
                UNDER_BED_LIGHTS_RGB(None),
            )

    def _on_rgb_report(self) -> None:
        if self.profile.rgb and self._rgb is not None and not self._writing_rgb:
            self._project_rgb(self._rgb)

    def _project_rgb(self, rgb: tuple[int, int, int]) -> None:
        on = any(rgb)
        if on and (
            self._selected_rgb is None
            or self._color_level is None
            or rgb
            != reported_color(
                *color_parameters(self._selected_rgb, self._color_level / self.light_level_max)
            )
        ):
            # The receiver reports effective channels with no separate brightness.
            self._selected_rgb, self._color_level = rgb, None
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_ON(on),
            UNDER_BED_LIGHTS_RGB(self._selected_rgb),
            LIGHT_LEVEL(self._color_level),
        )

    @property
    def _extra_buttons(self) -> tuple[ControllerButtonSpec, ...]:
        if self.profile.panel != "PanelE":
            return ()
        return (
            save_button(
                "moodbase_save_snore",
                "Save anti-snore position",
                lambda ctrl: require_controller(ctrl, MoodBaseController).save_snore(),
            ),
        )

    async def save_snore(self) -> None:
        if self.profile.panel != "PanelE":
            raise invalid("hhc_control_unavailable")
        await self._send(
            self._letter(SAVE_SNORE), self._current(), self._coordinator.cancel_command
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs = []
        if self.profile.timer:
            specs.append(
                ControllerNumberSpec(
                    "moodbase_light_timer",
                    "moodbase_light_timer",
                    TIMER,
                    0,
                    TIMER_MAX_MINUTES,
                    1,
                    lambda ctrl, value: require_controller(ctrl, MoodBaseController).set_timer(
                        value
                    ),
                    "min",
                    card=CardPlacement(CardSection.LIGHTING, CardRole.TIMER_MINUTES),
                )
            )
        if self.profile.vibration:
            specs.append(
                ControllerNumberSpec(
                    "moodbase_vibration",
                    "moodbase_vibration",
                    VIBRATION_LEVEL,
                    0,
                    VIBRATION_MAX,
                    1,
                    lambda ctrl, value: require_controller(ctrl, MoodBaseController).set_vibration(
                        value
                    ),
                    card=CardPlacement(CardSection.MASSAGE),
                )
            )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.profile.sync:
            return ()
        return (
            ControllerSelectSpec(
                "moodbase_sync_mode",
                "moodbase_sync_mode",
                SYNC_MODE,
                SYNC_MODES,
                lambda ctrl, value: require_controller(ctrl, MoodBaseController).set_sync_mode(
                    value
                ),
            ),
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        sync = ControllerSwitchSpec(
            "moodbase_sync_enabled",
            "moodbase_sync_enabled",
            lambda ctrl, value: require_controller(ctrl, MoodBaseController).set_sync(value),
            state_key=SYNC_ENABLED,
            available_fn=lambda ctrl: isinstance(ctrl, MoodBaseController) and ctrl.sync_available,
        )
        if not self.profile.timer:
            return (sync,)
        return (
            sync,
            ControllerSwitchSpec(
                "moodbase_light_timer_enabled",
                "moodbase_light_timer_enabled",
                lambda ctrl, on: require_controller(ctrl, MoodBaseController).set_timer(
                    TIMER_DEFAULT_MINUTES if on else 0
                ),
                state_key=TIMER_ENABLED,
                card=CardPlacement(CardSection.LIGHTING, CardRole.TIMER_TOGGLE),
            ),
        )

    @property
    def sync_available(self) -> bool:
        if not self._bind or not self._bind[0]:
            return False
        try:
            self._current()
        except ConnectionError:
            return False
        return True

    async def set_sync(self, enabled: bool) -> None:
        link = self._current()
        if not self._bind or not self._bind[0]:
            raise invalid("moodbase_sync_unavailable")
        if self._bind[1] != enabled:
            await self._send(
                codec.ascii_command(SYNC_ENABLE if enabled else SYNC_DISABLE),
                link,
                self._coordinator.cancel_command,
            )

    async def set_sync_mode(self, mode: str) -> None:
        if not self.profile.sync or mode not in SYNC_MODES:
            raise invalid("hhc_control_unavailable")
        link, cancel = self._current(), self._coordinator.cancel_command
        self._validate_sync_mode()
        with self.sent_state(SYNC_MODE(mode), is_current=lambda: self._link_is_current(link)):
            await self._send(
                codec.ascii_command(SYNC_MODE_COMMAND, SYNC_MODES.index(mode)),
                link,
                cancel,
                before_dispatch=self._validate_sync_mode,
            )

    def _validate_sync_mode(self) -> None:
        if self._bind is None:
            raise invalid("moodbase_sync_state_unknown")
        if self._bind[0]:
            raise invalid("moodbase_sync_bound")

    async def set_timer(self, value: float) -> None:
        if not self.profile.timer:
            raise invalid("hhc_control_unavailable")
        if not 0 <= value <= TIMER_MAX_MINUTES or value != int(value):
            raise invalid("value_out_of_range", min=0, max=TIMER_MAX_MINUTES, step=1)
        link, cancel = self._current(), self._coordinator.cancel_command
        minutes = int(value)
        with self.sent_state(
            TIMER(minutes),
            TIMER_ENABLED(minutes != 0),
            is_current=lambda: self._link_is_current(link),
        ):
            # The app schedules this from its query attempt. The M carrier suppresses the query.
            if await self._wait(SETTINGS_DELAY_MS / 1000, cancel):
                await self._send(lighting_frame(TIMER_COMMAND, minutes), link, cancel)
            else:
                note_frame_skipped()

    async def set_vibration(self, value: float) -> None:
        if not self.profile.vibration:
            raise invalid("hhc_control_unavailable")
        if not 0 <= value <= VIBRATION_MAX:
            raise invalid("value_out_of_range", min=0, max=VIBRATION_MAX, step=1)
        link, cancel = self._current(), self._coordinator.cancel_command
        frame = codec.short_transport(
            codec.music_command("V", value).decode("ascii"), wrapped=self.profile.wrapped
        )
        with self.sent_state(
            VIBRATION_LEVEL(int(value)), is_current=lambda: self._link_is_current(link)
        ):
            await self._send(frame, link, cancel)

    @property
    def supports_lights(self) -> bool:
        return self.profile.light or self.profile.rgb

    @property
    def supports_light_color_control(self) -> bool:
        return self.profile.rgb

    @property
    def supports_light_level_control(self) -> bool:
        return self.profile.rgb

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.rgb

    @property
    def publishes_rgb_light_state(self) -> bool:
        return self.profile.rgb

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return False  # Setting a color is the on operation.

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
        return self._selected_rgb

    async def lights_on(self) -> None:
        await self.set_light_color(self._base_color)

    async def lights_off(self) -> None:
        await self._write_color((0, 0, 0), 0, remember=False)

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        await self.set_light_color_with_level(rgb_color, self._color_level or self.light_level_max)

    @property
    def _base_color(self) -> tuple[int, int, int]:
        return self.current_light_rgb_color or self.default_light_rgb_color

    async def set_light_level(self, level: int) -> None:
        await self.set_light_color_with_level(self._base_color, level)

    async def set_light_color_with_level(self, rgb_color: tuple[int, int, int], level: int) -> None:
        await self._write_color(rgb_color, level)

    async def _write_color(
        self, rgb: tuple[int, int, int], level: int, *, remember: bool = True
    ) -> None:
        if not self.profile.rgb or not 0 <= level <= self.light_level_max:
            raise invalid("hhc_control_unavailable")
        link, cancel = self._current(), self._coordinator.cancel_command
        values = color_parameters(rgb, level / self.light_level_max)
        effective = reported_color(*values)

        def show(delivery: Delivery) -> None:
            if not self._link_is_current(link):
                return
            if delivery is Delivery.SENT:
                if remember:
                    self._selected_rgb, self._color_level = rgb, level
                # Feedback can describe intermediate channels. The effective
                # value of all three sent frames is the coherent result; a
                # matching report projects the same color and brightness.
                self._project_rgb(effective)
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(
                    UNDER_BED_LIGHTS_ON(None), UNDER_BED_LIGHTS_RGB(None), LIGHT_LEVEL(None)
                )

        def start_writing() -> None:
            self._writing_rgb = True

        interval = COLOR_INTERVAL_MS / 1000
        next_index = 0
        with delivered(show):
            try:
                for index, (command, value) in enumerate(zip(COLOR_COMMANDS, values, strict=True)):
                    if index and not await self._wait(interval, cancel):
                        return
                    await self._send(
                        lighting_frame(command, value),
                        link,
                        cancel,
                        before_dispatch=start_writing if index == 0 else None,
                    )
                    next_index = index + 1
            finally:
                self._writing_rgb = False
                if next_index < len(COLOR_COMMANDS):
                    note_frame_skipped()
        # Keep the app's final pacing interval while accepting new RGB reports.
        await self._wait(interval, cancel)


async def build_controller(ctx: BuildContext) -> MoodBaseController:
    stored = ctx.data.get(CONF_BLE_DEVICE_NAME)
    observed = ctx.advertisement_name or ctx.live_device_name
    name = stored if isinstance(stored, str) else observed
    if name is None or not eligible(name) or (eligible(observed) and observed != name):
        raise setup_stopped("moodbase_name_mismatch")
    return MoodBaseController(ctx.coordinator, profile=MoodBaseProfile(name))
