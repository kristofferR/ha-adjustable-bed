"""JobsAI 1.0.6 app data and its two direct-bed alarm channels."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

from bleak import BleakClient
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmError, AlarmRequest
from ...card import CARD_MASSAGE, CARD_UTILITY
from ...codec import okin_nframe as codec
from ...controller_state import StateKey
from ...profiles.okin_nframe import JOBS_ACTIONS, JOBS_PROFILES, JOBS_SAVE_CODES
from ..builder import BuildContext
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
)
from .controller import OkinBeddingApp, SessionBeddingAppController, _callback, clock_frame

AlarmKind = Literal["sleep", "wake"]
STATUS: Final = StateKey[int]("jobs_status")
SAVE_EVENT: Final = StateKey[int]("jobs_save_event")


@dataclass(frozen=True)
class AlarmKeys:
    type: StateKey[int]
    repeat: StateKey[int]
    hour: StateKey[int]
    minute: StateKey[int]
    enabled: StateKey[bool]


ALARM_KEYS: Final = {
    kind: AlarmKeys(
        StateKey[int](f"jobs_{kind}_type"),
        StateKey[int](f"jobs_{kind}_repeat"),
        StateKey[int](f"jobs_{kind}_hour"),
        StateKey[int](f"jobs_{kind}_minute"),
        StateKey[bool](f"jobs_{kind}_enabled"),
    )
    for kind in ("sleep", "wake")
}
# These are the app's selectable choices, not inferred physical effects.
SLEEP_ACTIONS: Final = {"none": 0, "flat": 9, "custom": 2}
WAKE_ACTIONS: Final = {"none": 0, "memory_2": 8}
_RETAINABLE: Final = {
    "sleep": frozenset({0, 1, 2, 9, 11}),
    "wake": frozenset({0, 1, 2, 7, 8, 11, 12}),
}
_MODEL_UUID: Final = "00002a24-0000-1000-8000-00805f9b34fb"
_NOTIFY: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"


def alarm_frame(kind: AlarmKind, repeat: int, action: int, hour: int, minute: int) -> bytes:
    """Encode the live manager's seven-field record, with enable derived from repeat."""
    return codec.record(
        5 if kind == "sleep" else 7, (repeat, action, hour, minute, 0, int(repeat != 0), 0)
    )


def repeat_mask(now: datetime, weekdays: Sequence[int]) -> int:
    """Selected Sunday-zero days recur; no selection uses today's one-shot bit."""
    return (
        0x80 | sum(1 << day for day in set(weekdays))
        if weekdays
        else 1 << ((now.weekday() + 1) % 7)
    )


class JobsController(SessionBeddingAppController):
    """Shared Bedding execution with Jobs-specific controls, parser and settings."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, mode: str = "mode1") -> None:
        super().__init__(
            coordinator,
            app=OkinBeddingApp(
                prefix="jobs",
                label="JobsAI",
                actions=JOBS_ACTIONS,
                save_codes=JOBS_SAVE_CODES,
                buttons=(),
                profile=JOBS_PROFILES[mode],
                information_uuid=_MODEL_UUID,
                information_log_only=True,
                exact_duration=True,
                settle_writes=True,
            ),
        )
        self._mode = mode
        self._alarm_types: dict[str, int] = {}

    def _hold_ms(self, action: str) -> int:
        # Use this app's bounded voice deadlines for native presses. Saves use
        # its help gesture; this is not a proven device-side programming gate.
        if action in JOBS_SAVE_CODES:
            return 5000
        return 1500 if action == "flat" else 500

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, 200

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._startup_cancel_counter = self._coordinator.cancel_counter
        await super().start_notify(callback)

    async def _after_information_read(self, generation: int, client: BleakClient) -> None:
        await asyncio.sleep(0.2)
        if (
            generation == self._connection_generation
            and client is self.client
            and self._startup_cancel_counter == self._coordinator.cancel_counter
        ):
            await self.sync_clock()

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._app.actions)

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            slots=2,
            requires_slot=True,
            weekdays=True,
            wake_actions=(
                "none",
                "flat",
                "memory_1",
                "wake_up",
                "memory_2",
                "massage",
                "wave_massage",
            ),
            cancel_running=True,
            resource=None,
        )

    def _alarm_action(self, alarm: AlarmRequest) -> str:
        kind = "sleep" if alarm.slot == 1 else "wake"
        action = alarm.wake_action
        if action in ("massage", "wave_massage") or (kind == "wake" and action == "memory_1"):
            code = {"massage": 1, "wave_massage": 11, "memory_1": 2}[action]
            if self._alarm_types.get(kind) != code:
                raise AlarmError(
                    "jobs_alarm_not_received",
                    "Read this alarm type from the bed before preserving it",
                )
            return "keep"
        return {"memory_1": "custom", "wake_up": "automatic"}.get(action, action)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.enabled:
            try:
                self.validate_alarm_action(
                    "sleep" if alarm.slot == 1 else "wake", self._alarm_action(alarm)
                )
            except ValueError as error:
                if isinstance(error, AlarmError):
                    raise
                raise AlarmError(
                    str(error), "Choose an action supported by this Jobs alarm kind"
                ) from error

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        await self.configure_jobs_alarm(
            kind="sleep" if alarm.slot == 1 else "wake",
            enabled=alarm.enabled,
            action=self._alarm_action(alarm) if alarm.enabled else "none",
            hour=alarm.hour,
            minute=alarm.minute,
            weekdays=tuple((day + 1) % 7 for day in alarm.weekdays),
            reference_time=alarm.reference_time,
        )

    def _handle_notification(self, _: object, data: bytearray) -> None:
        self.forward_raw_notification(_NOTIFY, bytes(data))
        if len(data) <= 10:
            return

        def signed(value: int) -> int:
            return value if value < 128 else value - 256

        if data[1] in (12, 13):
            kind = "sleep" if data[1] == 12 else "wake"
            keys = ALARM_KEYS[kind]
            self._alarm_types[kind] = signed(data[5])
            self.forward_controller_state_updates(
                keys.type(signed(data[5])),
                keys.repeat(signed(data[4])),
                keys.hour(signed(data[6])),
                keys.minute(signed(data[7])),
                keys.enabled(data[9] == 1),
            )
        status = signed(data[10])
        if status != self._status_code:
            self._status_code = status
            self.forward_controller_state_update(STATUS, status)
            if self._save_code:
                self.forward_controller_state_update(SAVE_EVENT, self._save_code)
                self._save_code = 0

    def on_disconnect(self) -> None:
        self._alarm_types.clear()
        self._status_code = 0
        super().on_disconnect()

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        keys = (STATUS, SAVE_EVENT, *(key for alarm in ALARM_KEYS.values() for key in (
            alarm.type, alarm.repeat, alarm.hour, alarm.minute, alarm.enabled,
        )))
        return {
            **super().protocol_diagnostics,
            "received": {str(key): self._coordinator.controller_state.get(key) for key in keys},
        }

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return ()

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            ControllerStateBinarySensorSpec(
                f"jobs_{kind}_enabled",
                f"jobs_{kind}_enabled",
                keys.enabled,
                "mdi:alarm-check",
                entity_registry_enabled_default=True,
                entity_category=None,
            )
            for kind, keys in ALARM_KEYS.items()
        )

    @property
    def replaced_standard_button_keys(self) -> frozenset[str]:
        return frozenset({"program_memory_1", "program_memory_2"})

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        saves = (
            ("save_lounge", "Save Lounge"),
            ("save_zero_g", "Save zero gravity"),
            ("save_incline", "Save Incline"),
        )
        actions = (
            "massage_on",
            "wave_1",
            "wave_2",
            "wave_3",
            "wave_4",
            "smb_on",
            "smb_off",
            "query_sleep",
            "query_wake",
        )
        return (
            *(save_button(f"jobs_{action}", label, _callback(action)) for action, label in saves),
            save_button("program_memory_1", "Save M1", lambda ctrl: ctrl.program_memory(1)),
            save_button("program_memory_2", "Save M2", lambda ctrl: ctrl.program_memory(2)),
            *(
                ControllerButtonSpec(
                    f"jobs_{action}",
                    action.replace("_", " "),
                    _callback(action),
                    translation_key=f"jobs_{action}",
                    card=CARD_MASSAGE
                    if action.startswith(("massage", "wave", "smb"))
                    else CARD_UTILITY,
                )
                for action in actions
            ),
        )

    async def execute_app_control(self, action: str) -> None:
        if action in ("query_sleep", "query_wake"):
            await self.query_alarm("sleep" if action == "query_sleep" else "wake")
            return
        await super().execute_app_control(action)

    async def massage_toggle(self) -> None:
        # There is an explicit on command, no proven toggle or state feedback.
        await self.hold_control("massage_on", self._hold_ms("massage_on"))

    async def massage_off(self) -> None:
        await self.hold_control("massage_off", self._hold_ms("massage_off"))

    async def massage_intensity_up(self) -> None:
        await self.hold_control("massage_intensity_up", self._hold_ms("massage_intensity_up"))

    async def massage_intensity_down(self) -> None:
        await self.hold_control("massage_intensity_down", self._hold_ms("massage_intensity_down"))

    async def massage_mode_step(self) -> None:
        await self._send_next_wave(1)

    async def _send_next_wave(self, direction: int) -> None:
        self._massage_wave_index = (
            (0 if direction > 0 else 3)
            if self._massage_wave_index is None
            else (self._massage_wave_index + direction) % 4
        )
        action = f"wave_{self._massage_wave_index + 1}"
        await self.hold_control(action, self._hold_ms(action))

    async def sync_clock(self) -> None:
        await self._press_writer()(clock_frame(dt_util.now()))

    async def query_alarm(self, kind: AlarmKind) -> None:
        await self._press_writer()(codec.request(0xC0 if kind == "sleep" else 0xD0))

    def validate_alarm_action(self, kind: AlarmKind, action: str) -> int:
        if action == "keep":
            code = self._alarm_types.get(kind)
            if code not in _RETAINABLE[kind]:
                raise ValueError("jobs_alarm_not_received")
            return code
        if kind == "wake" and action == "automatic":
            return 12 if self._mode == "mode1" else 7
        choices = SLEEP_ACTIONS if kind == "sleep" else WAKE_ACTIONS
        if action not in choices:
            raise ValueError("jobs_alarm_action_invalid")
        return choices[action]

    async def configure_jobs_alarm(
        self,
        *,
        kind: AlarmKind,
        enabled: bool,
        action: str,
        hour: int,
        minute: int,
        weekdays: Sequence[int],
        reference_time: datetime | None = None,
    ) -> None:
        code = self.validate_alarm_action(kind, action) if enabled else 0
        write = self._press_writer()
        repeat = repeat_mask(reference_time or dt_util.now(), weekdays) if enabled else 0
        await write(
            alarm_frame(kind, repeat, code, hour if enabled else 0, minute if enabled else 0)
        )
        await asyncio.sleep(0.5)
        await write(codec.request(0xC0 if kind == "sleep" else 0xD0))


async def build_jobs(ctx: BuildContext) -> JobsController:
    mode = ctx.variant if ctx.variant not in (None, "auto") else "mode1"
    if mode not in JOBS_PROFILES:
        raise ValueError("Choose JobsAI mode 1 or mode 2")
    return JobsController(ctx.coordinator, mode=mode)
