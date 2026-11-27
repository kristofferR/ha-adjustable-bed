"""King Koil controls using the shared SUTA wire and fenced execution machinery."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles import suta_king_koil as app
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, require_controller
from ..cancellation import cancellable, settled
from ..entity_specs import ControllerButtonSpec, ControllerNumberSpec, ControllerSelectSpec
from ..truemotion.controller import ZONES, Burst, TrueMotionController
from .receive import Receiver

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext

STEPS: Final = {zone: StateKey[int | None](f"suta_king_koil_{zone.lower()}_step") for zone in ZONES}
MODE: Final = StateKey[str | None]("suta_king_koil_massage_mode")
MODES: Final = tuple(f"Mode {i}" for i in range(1, 5))


class KingKoilController(TrueMotionController):
    session_namespace = "suta_king_koil"
    receiver_type = Receiver

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app.PROFILE)
        self._committed_alarms: dict[str, str] | None = None

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        receiver = self._receiver()
        return {
            "date_raw": self._state.observations.gd,
            "alarms_raw": self._committed_alarms,
            "response_raw": receiver.raw if receiver else None,
            "version_raw": self._state.observations.version,
        }

    def _receiver(self) -> Receiver | None:
        receiver = self._link.receiver if self._link else None
        return receiver if isinstance(receiver, Receiver) else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            *super().controller_button_specs,
            ControllerButtonSpec(
                "suta_king_koil_alarms",
                "Read alarms",
                _refresh,
                diagnostic=True,
                translation_key="suta_king_koil_alarms",
            ),
            ControllerButtonSpec(
                "suta_king_koil_clock",
                "Read bed clock",
                _clock,
                diagnostic=True,
                translation_key="suta_king_koil_clock",
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        return tuple(
            ControllerNumberSpec(
                f"suta_king_koil_{zone.lower()}_step",
                f"suta_king_koil_{zone.lower()}_step",
                STEPS[zone],
                0,
                3,
                1,
                partial(_step, zone=zone),
                card=CARD_MASSAGE,
            )
            for zone in ZONES
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        return (
            ControllerSelectSpec(
                "suta_king_koil_massage_mode",
                "suta_king_koil_massage_mode",
                MODE,
                MODES,
                _mode,
                card=CARD_MASSAGE,
            ),
        )

    def on_disconnect(self) -> None:
        super().on_disconnect()
        # No notification proves current massage state on a replacement link.
        self._state.timers = dict.fromkeys(ZONES, "00")
        self._state.level = None
        self.forward_controller_state_updates(MODE(None), *(key(None) for key in STEPS.values()))

    async def _preset(self, mode: str, *, save: bool = False) -> None:
        if mode not in (self.profile.saves if save else self.profile.presets):
            raise invalid("truemotion_control", control=mode)
        await self._run(
            Burst(
                f"AT+{'SETMODE' if save else 'MODE'}=BOTH {mode}",
                app.SAVE_COUNT if save else app.RECALL_COUNT,
                app.SAVE_DELAY_MS + app.REPEAT_MS if save else app.REPEAT_MS,
            )
        )

    async def set_step(self, zone: app.Zone, step: int) -> None:
        if not 0 <= step < len(app.MASSAGE_STEPS):
            raise ValueError("Choose massage step 0 to 3")
        code = app.MASSAGE_STEPS[step]
        link = self._current_link()
        # An interrupted setting cannot keep admitting modes from an older step.
        self._state.timers[zone] = "00"
        with self.sent_state(STEPS[zone](step), is_current=lambda: self._link_is_current(link)):
            await self._run(Burst(f"AT+MASS=BOTH {zone} DT{code}", 3, 100))
        if not self._link_is_current(link):
            return
        self._state.timers[zone] = code
        if not any(value != "00" for value in self._state.timers.values()):
            self._state.level = None
            self.forward_controller_state_updates(MODE(None))

    async def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError("Choose massage mode 1 to 4")
        head, foot = (self._state.timers[zone] != "00" for zone in ZONES)
        if not (head or foot):
            raise invalid("truemotion_massage_off")
        code = app.MASSAGE_MODES[MODES.index(mode)]
        link = self._current_link()
        with self.sent_state(MODE(mode), is_current=lambda: self._link_is_current(link)):
            await self._run(
                *(
                    Burst(
                        f"AT+MASS=BOTH {zone} LV{code}", 3, 150 if zone == "FOOT" and head else 100
                    )
                    for zone, active in zip(ZONES, (head, foot), strict=True)
                    if active
                )
            )
        if self._link_is_current(link):
            self._state.level = code

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        link = self._current_link()
        self._state.timers = dict.fromkeys(ZONES, "00")
        self._state.level = None
        with self.sent_state(
            *(key(0) for key in STEPS.values()),
            MODE(None),
            is_current=lambda: self._link_is_current(link),
        ):
            await settled(
                self._sequence(
                    link,
                    (
                        Burst("AT+CTRL=BOTH STOP", 2, 100),
                        Burst("AT+MASS=BOTH HEAD DT00", 2, 250),
                        Burst("AT+MASS=BOTH FOOT DT00", 2, 400),
                    ),
                    asyncio.Event(),
                    complete_release=True,
                )
            )
        self._state.timers = dict.fromkeys(ZONES, "00")
        self._state.level = None

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(weekdays=True, time_to_turn_off=True, live_check=True)

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.enabled and not self._state.observations.gd:
            raise invalid("suta_king_koil_calibrate")

    async def _alarm_sequence(self, bursts: tuple[Burst, ...], finish_ms: int) -> None:
        link = self._current_link()
        receiver = self._receiver()
        assert receiver is not None
        receiver.alarms.clear()
        receiver.collecting = True
        cancel = self._coordinator.cancel_command
        end = asyncio.get_running_loop().time() + finish_ms / 1000
        try:
            await self._sequence(link, bursts, cancel)
            await cancellable(
                asyncio.sleep(max(0, end - asyncio.get_running_loop().time())), cancel
            )
            if self._link_is_current(link):
                self._committed_alarms = dict(receiver.alarms)
        finally:
            receiver.collecting = False
            receiver.alarms.clear()

    async def sync_clock(self) -> None:
        now = dt_util.now()
        await self._alarm_sequence(
            (
                Burst(app.clock(now.year, now.month, now.day, now.hour, now.minute), 3, 1100),
                Burst("AT+GD", 3, 2100),
                Burst("AT+GA", 3, 3100),
            ),
            4500,
        )

    async def refresh_alarms(self) -> None:
        if not self._state.observations.gd:
            raise invalid("suta_king_koil_calibrate")
        await self._alarm_sequence((Burst("AT+GA", 3, 100),), 1500)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        days = (
            sorted((day + 1) % 7 for day in alarm.weekdays)
            if alarm.weekdays
            else [(alarm.occurrence().weekday() + 1) % 7]
        )
        assert alarm.hour is not None and alarm.minute is not None
        operation = "SA" if alarm.enabled else "CA"
        await self.alarm_operation(
            operation, days, alarm.hour, alarm.minute, "01" if alarm.weekdays else "00"
        )

    async def alarm_operation(
        self,
        operation: app.AlarmOperation,
        days: list[int],
        hour: int,
        minute: int,
        loop: str = "01",
    ) -> None:
        bursts = tuple(
            Burst(app.alarm(operation, day, hour, minute, loop), 3, 100 + i * 1000)
            for i, day in enumerate(days)
        )
        await self._alarm_sequence(
            (*bursts, Burst("AT+GA", 3, 100 + len(days) * 1000)), len(days) * 1000 + 1500
        )


async def _step(controller: BedController, value: float, *, zone: app.Zone) -> None:
    if not value.is_integer():
        raise ValueError("Choose an integral massage step")
    await require_controller(controller, KingKoilController).set_step(zone, int(value))


async def _mode(controller: BedController, option: str) -> None:
    await require_controller(controller, KingKoilController).set_mode(option)


async def _refresh(controller: BedController) -> None:
    await require_controller(controller, KingKoilController).refresh_alarms()


async def _clock(controller: BedController) -> None:
    await require_controller(controller, KingKoilController)._run(Burst("AT+GD", 3, 100))


async def build_controller(ctx: BuildContext) -> KingKoilController:
    return KingKoilController(ctx.coordinator)
