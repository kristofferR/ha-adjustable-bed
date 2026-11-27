"""MLILY 3.1.1's accepted direct BED subset over the shared product runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...codec import richmat as codec
from ...errors import invalid
from ...profiles.mlily0 import ACTIONS, PROFILES
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..casper_base.protocol import Request
from ..catalog_buttons import catalog_button
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec
from ..goodvibe.controller import Link
from ..mlily_remote.controller import LABELS, MlilyRemoteController
from .receive import Receiver

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

WAKE_ACTIONS = {
    "flat": "MotorReset", "zero_g": "ZeroGravity", "anti_snore": "AntiSnoring",
    "reading": "ReadingPosition", "tv": "TVPosition", "yoga": "YogaPosition",
    "get_up": "HelpGetUp", "lounge": "LoungePosition", "deep_sleep": "SleepPosition",
    "memory_1": "MemoryPosition1", "memory_2": "MemoryPosition2",
}


class MlilyController(MlilyRemoteController):
    """Keep product opcodes, alarm targets and session ownership app-specific."""

    profiles = PROFILES
    action_catalog = ACTIONS
    action_prefix = "mlily0_"
    button_labels = {
        **LABELS, "ReadingPosition": "Reading", "YogaPosition": "Yoga",
        "HelpGetUp": "Get Up", "SleepPosition": "Sleep",
    }

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        super().__init__(coordinator, product=product)
        self._receiver = Receiver(self._event)

    @property
    def cooling(self) -> bool:
        return False  # No timer/strength semantics borrowed from other PowerCool apps.

    @property
    def actions(self) -> dict[str, tuple[int, int | None]]:
        # Custom/alarm entries are short-only; they cannot erase the mode menu's
        # verified save opcode or introduce a dormant long opcode as a control.
        actions: dict[str, tuple[int, int | None]] = {}
        for group in self.product[1:6]:
            for i in group:
                name, short, save = self.action_catalog[i]
                previous = actions.get(name)
                if previous is not None and previous[0] != short:
                    raise ValueError("Conflicting product action opcodes")
                actions[name] = (short, save if save is not None else previous[1] if previous else None)
        return actions

    @property
    def supports_single_address_pairing(self) -> bool:
        return False  # The accepted builder has no side operand.

    def _side(self, link: Link) -> int:
        if self.command_side is not None:
            raise invalid("side_not_supported")
        return 0

    @property
    def persisted_app_state_key(self) -> str:
        return "mlily0:" + self.model

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        return {}  # Local alarm persistence/DB restoration remains unresolved.

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        return

    async def _write_packet(
        self, link: Link, packet: bytes, *, response: bool,
        cleanup: bool, cancel_event: asyncio.Event,
    ) -> None:
        # A submitted write settles before cancellation releases the command lane.
        await settled(super()._write_packet(
            link, packet, response=response, cleanup=cleanup, cancel_event=cancel_event,
        ), eager_start=True)

    def _can_release_link(self, link: Link) -> bool:
        # The original client still owns any movement that reached it. Never
        # substitute the controller's replacement link for its release.
        return link.client.is_connected

    async def _release_link(self, link: Link, side: int) -> None:
        await settled(super()._release_link(link, side))

    async def _initialize_link(self, link: Link) -> None:
        # ExitLimit is conditional in the app. Expose that proven operation as
        # an explicit button, rather than unconditionally unlocking on connect.
        return

    async def exit_limit(self) -> None:
        link = self._current()
        await self._write(codec.function(0, action="deviceFunctionItemExitLimit", single=link.legacy), link)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        async def initialize(controller: BedController) -> None:
            await require_controller(controller, MlilyController).exit_limit()

        spec = catalog_button("mlily0_exit_limit", "Exit Limit", initialize)
        assert spec is not None
        return (*super().controller_button_specs, spec)

    @property
    def alarm_modes(self) -> tuple[str, ...]:
        return tuple(self.action_catalog[i][0] for i in self.product[4])

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        modes = tuple(key for key, name in WAKE_ACTIONS.items() if name in self.alarm_modes)
        if not modes:
            return None
        return AlarmCapability(wake_actions=modes, weekdays=self.product[10], requires_wake_action=True)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if not self.alarm_modes:
            raise invalid("alarm_not_supported", device_name=self._coordinator.name)
        if alarm.enabled and WAKE_ACTIONS.get(alarm.wake_action) not in self.alarm_modes:
            raise invalid("alarm_wake_action_not_supported", device_name=self._coordinator.name,
                          wake_action=alarm.wake_action,
                          wake_actions=", ".join(key for key, name in WAKE_ACTIONS.items() if name in self.alarm_modes))
        if alarm.weekdays and (not self.product[10] or alarm.weekdays != tuple(range(7))):
            raise invalid("mlily0_alarm_repeat")

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._current()
        minutes = 0
        code = 0
        if alarm.enabled:
            minutes = alarm.minutes_until(dt_util.now())
            name = WAKE_ACTIONS[alarm.wake_action]
            code = next(self.action_catalog[i][1] for i in self.product[4] if self.action_catalog[i][0] == name)
        self._pending_alarm = None
        for packet in codec.countdown(minutes, code):
            if not await self._write(packet, link):
                return
        if alarm.enabled and self.product[10] and await self._wait(0.1):
            await self._write(codec.frame(codec.BED, 0x14, int(bool(alarm.weekdays)), 0xFE), link)

    async def stop_all(self) -> None:
        await settled(super().stop_all())

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_legs_stop = stop_all
    move_feet_stop = stop_all

    async def sync_clock(self) -> None:
        link = self._current()
        now = dt_util.now()
        for packet in (
            codec.frame(codec.BED, 0x13, now.hour, now.minute),
            codec.frame(codec.BED, 0x14, now.second, 0xFF),
        ):
            if not await self._write(packet, link):
                return

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return ()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "product": self.model,
            "events": deepcopy(self.events),
            "product_flags_3c_40_44": list(PROFILES[self.model].raw_flags),
            "notification_rejection": self._error,
        }

    def _publish(self) -> None:
        # The shared lifecycle calls this hook; protocol fields are diagnostics only.
        return

    def validate_casper_base_request(self, request: Request) -> None:
        raise invalid("mlily0_native_actions")

    def _event(self, name: str, value: object) -> None:
        # Parsed values never select a product, infer a motor axis or enable a command.
        self.events[name] = value


async def build_controller(ctx: BuildContext) -> MlilyController:
    return MlilyController(ctx.coordinator, product=ctx.variant or "")
