"""MattressPoint controls on the shared single-record UART session."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...card import CARD_HIDDEN, CARD_MASSAGE, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles import mattresspoint as app
from ...profiles.okin_nframe import OkinNFrameProfile
from ..base import BedController, ProfileExecution, require_controller
from ..builder import BuildContext
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateBinarySensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..lifecycle import ControllerSession
from ..okin_uart import Link, OkinUartController, _wait

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

MASSAGE_ACTIVE: Final = StateKey[bool | None]("mattresspoint_massage_active")
ALARM_ENABLED: Final = StateKey[bool | None]("mattresspoint_alarm_enabled")
_RELEASE: Final = "mattresspoint_release"


def _move(control: str) -> MotorCommandCallable:
    async def move(ctrl: BedController) -> None:
        await require_controller(ctrl, MattressPointController).press_motor(control)

    return move


class MattressPointController(ProfileExecution[OkinNFrameProfile], OkinUartController):
    """Require an explicit app/box choice and exact live GATT properties."""

    settle_writes = True
    gatt_error_key = "mattresspoint_gatt"
    stop_frame = app.STOP

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str) -> None:
        super().__init__(coordinator)
        self.variant = variant
        self.profile = app.PROFILES[variant]
        self._massage_version = self._alarm_version = 0
        self._raw_report: codec.MassageReport | codec.ShortAlarmReport | None = None

    def on_disconnect(self) -> None:
        self._massage_version += 1
        self._alarm_version += 1
        self._raw_report = None
        self.forward_controller_state_updates(MASSAGE_ACTIVE(None), ALARM_ENABLED(None))
        super().on_disconnect()

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    def _live(self, expected: Link | None = None) -> Link:
        from ...errors import BedNotConnectedError
        from ..uart_roles import gatt_roles

        link = super()._live(expected)
        roles = gatt_roles(link.client.services)
        if roles is None or roles[0] is not link.write or roles[1] is not link.notify:
            raise BedNotConnectedError("mattresspoint_gatt")
        return link

    def _current(self, link: Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _receive(self, report: codec.MassageReport | codec.ShortAlarmReport | None) -> None:
        if report is None:
            return
        self._raw_report = report
        if isinstance(report, codec.MassageReport):
            self._massage_version += 1
            self.forward_controller_state_updates(MASSAGE_ACTIVE(bool(report.head or report.foot)))
        else:
            self._alarm_version += 1
            self.forward_controller_state_updates(
                ALARM_ENABLED(bool(report.enabled) if report.enabled in (0, 1) else None)
            )

    async def _sequence(
        self,
        link: Link,
        frame: bytes,
        offsets: tuple[int, ...],
        cancel: asyncio.Event,
        *,
        track: bool = True,
    ) -> None:
        start = asyncio.get_running_loop().time()
        remaining = len(offsets)

        def written() -> None:
            nonlocal remaining
            remaining -= 1

        try:
            for offset in offsets:
                if await _wait(cancel, start + offset / 1000 - asyncio.get_running_loop().time()):
                    note_frame_skipped()
                    return
                # Finish a submitted write before cancellation may settle sent state.
                await self._write(link, frame, cancel, track=track, on_write=written)
        except BaseException:
            if remaining:
                note_frame_skipped()
            raise

    async def async_on_connect(self, session: ControllerSession) -> None:
        await session.async_start_notify()
        await asyncio.sleep(0.2)
        await self._sequence(
            self._live(), app.clock(dt_util.now()), app.CLOCK_OFFSETS, asyncio.Event(), track=False
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"{axis}_{d}" for axis in self.profile.axes for d in ("up", "down"))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported(control)
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60_000:
            raise invalid("mattresspoint_hold")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._held(
            codec.frame40(self.profile.keys[control]), self.leased_hold_ms(duration_ms)
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, app.REFRESH_MS

    async def press_motor(self, control: str) -> None:
        await self.hold_control(
            control, min(60_000, self._coordinator.motor_pulse_count * app.REFRESH_MS)
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                "tilt" if axis == "head_tilt" else axis,
                axis,
                _move(f"{axis}_up"),
                _move(f"{axis}_down"),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    release_button_key=_RELEASE,
                    press_hold_ms=None,
                    stop_scope="side",
                ),
            )
            for axis in self.profile.axes
        )

    async def move_head_up(self) -> None:
        await self.press_motor("back_up")

    async def move_head_down(self) -> None:
        await self.press_motor("back_down")

    async def move_feet_up(self) -> None:
        await self.press_motor("legs_up")

    async def move_feet_down(self) -> None:
        await self.press_motor("legs_down")

    move_back_up = move_head_up
    move_back_down = move_head_down
    move_legs_up = move_feet_up
    move_legs_down = move_feet_down
    move_head_stop = move_back_stop = move_feet_stop = move_legs_stop = OkinUartController.stop_all

    async def preset_flat(self) -> None:
        raise self.not_supported("flat")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)

    async def program_memory(self, memory_num: int) -> None:
        raise self.not_supported("program_memory")

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    # Preset hold/save/reset/model gating remains S02. No memory entities are invented.
    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return True

    async def lights_toggle(self) -> None:
        await self.write_command(app.LIGHT)

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    async def massage(self, action: str) -> None:
        link = self._live()
        version = self._massage_version

        def current() -> bool:
            return self._current(link) and self._massage_version == version

        if action in ("on", "off"):
            with self.sent_state(MASSAGE_ACTIVE(action == "on"), is_current=current):
                await self._sequence(
                    link, codec.frame40(app.MASSAGE[action]), (0,), self._coordinator.cancel_command
                )
        else:
            await self.write_command(codec.frame40(app.MASSAGE[action]))

    async def massage_off(self) -> None:
        await self.massage("off")

    async def disable_alarm(self) -> None:
        link, version = self._live(), self._alarm_version
        with self.sent_state(
            ALARM_ENABLED(False),
            is_current=lambda: self._current(link) and self._alarm_version == version,
        ):
            await self._sequence(
                link, app.ALARM_DISABLE, app.ALARM_OFFSETS, self._coordinator.cancel_command
            )

    async def query_alarm(self) -> None:
        await self._sequence(
            self._live(), app.ALARM_QUERY, app.QUERY_OFFSETS, self._coordinator.cancel_command
        )

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        await self._sequence(
            self._live(),
            app.clock(dt_util.now()),
            app.CLOCK_OFFSETS,
            self._coordinator.cancel_command,
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *(
                ControllerButtonSpec(
                    f"mattresspoint_{action}",
                    label,
                    lambda c, a=action: require_controller(c, MattressPointController).massage(a),
                    translation_key=f"mattresspoint_{action}",
                    scheduler_resource="*",
                    card=CARD_MASSAGE,
                )
                for action, label in (
                    ("on", "Start massage"),
                    ("timer", "Cycle massage timer"),
                    ("head_up", "Increase head massage"),
                    ("head_down", "Decrease head massage"),
                    ("foot_up", "Increase foot massage"),
                    ("foot_down", "Decrease foot massage"),
                    ("wave_up", "Next massage wave"),
                    ("wave_down", "Previous massage wave"),
                )
            ),
            ControllerButtonSpec(
                "mattresspoint_disable_alarm",
                "Disable alarm",
                lambda c: require_controller(c, MattressPointController).disable_alarm(),
                translation_key="mattresspoint_disable_alarm",
                scheduler_resource="*",
            ),
            ControllerButtonSpec(
                "mattresspoint_query_alarm",
                "Refresh alarm",
                lambda c: require_controller(c, MattressPointController).query_alarm(),
                translation_key="mattresspoint_query_alarm",
                scheduler_resource="*",
                diagnostic=True,
            ),
            ControllerButtonSpec(
                "mattresspoint_query_massage",
                "Refresh massage",
                lambda c: c.write_command(app.MASSAGE_QUERY),
                translation_key="mattresspoint_query_massage",
                scheduler_resource="*",
                diagnostic=True,
            ),
            ControllerButtonSpec(
                _RELEASE,
                "Release held control",
                lambda c: c.stop_all(),
                translation_key=_RELEASE,
                release_only=True,
                card=CARD_HIDDEN,
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            ControllerStateBinarySensorSpec(
                "mattresspoint_massage",
                "mattresspoint_massage",
                MASSAGE_ACTIVE,
                "mdi:vibrate",
                entity_category=None,
                entity_registry_enabled_default=True,
                card=CARD_MASSAGE,
            ),
            ControllerStateBinarySensorSpec(
                "mattresspoint_alarm",
                "mattresspoint_alarm",
                ALARM_ENABLED,
                "mdi:alarm",
                entity_category=None,
                entity_registry_enabled_default=True,
                card=CARD_UTILITY,
            ),
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        from dataclasses import asdict

        return {
            "app": "com.okin.MattressPoint 1.0.3 (5)",
            "box": self.variant,
            "source_status": "PARTIAL",
            "hardware": "UNVERIFIED",
            "last_report": asdict(self._raw_report) if self._raw_report is not None else None,
        }


async def build_controller(ctx: BuildContext) -> MattressPointController:
    if ctx.variant is None or ctx.variant not in app.PROFILES:
        raise invalid("mattresspoint_variant")
    return MattressPointController(ctx.coordinator, ctx.variant)
