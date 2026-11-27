"""FlexiRest's K1 profile, using the shared Solace/Sophie controls."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_PRESETS
from ...codec import ff_frame as codec
from ...command_scheduler import (
    CommandKind,
    capture_caller_cancellation,
    command_frames_counted,
    current_command_context,
    note_frame_skipped,
    note_frame_written,
)
from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey, StateUpdate
from ...profiles import flexirest as app
from ...profiles.ff_frame import SolaceProfile
from ...state_keys import LIGHT_LEVEL, LIGHT_TIMER_OPTION, SYNCHRO_MODE, UNDER_BED_LIGHTS_ON
from ..base import require_controller
from ..cancellation import settled
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    PositionNumberSpec,
)
from .sophie import SophieController
from .sophie_state import (
    ALARM_ENABLED,
    ALARM_MASSAGE,
    ALARM_MODE,
    ALARM_RING,
    ALARM_SUPPORTED,
    ALARM_TIME,
    ALARM_WEEKDAYS,
    SYNC_SUPPORTED,
)

FAULT: Final = StateKey[str]("flexirest_fault")
ALARM_AUDIO: Final = StateKey[bool]("flexirest_alarm_audio")

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class FlexirestController(SophieController):
    """One unaddressed two-axis layout, with replies scoped to its BLE session."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self._identity: tuple[str, object, object, int] | None = None
        self._raw: dict[str, str] = {}
        self._audio: bool | None = coordinator.controller_state.get(ALARM_AUDIO)
        self._reported_alarm: tuple[int, bytes] | None = None

    @property
    def profile(self) -> SolaceProfile:
        return app.PROFILE

    @property
    def _query_family(self) -> str:
        return "q2"

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def auto_stops_on_idle(self) -> bool:
        return False

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return True

    def _startup_schedule(self) -> list[tuple[int, bytes | None]]:
        return app.startup_schedule()

    def _current_identity(self) -> tuple[str, object, object, int]:
        data = self._coordinator.entry.data
        return (
            self._coordinator.address.upper(),
            data.get(CONF_BED_TYPE),
            data.get(CONF_PROTOCOL_VARIANT),
            self._coordinator.connection_generation,
        )

    def _current(self) -> bool:
        return (
            self._identity is not None
            and self._identity == self._current_identity()
            and self._identity[1:3] == ("solace", "flexirest")
            and self._coordinator.controller is self
        )

    def sent_state(
        self,
        *updates: StateUpdate,
        is_current: Callable[[], bool] | None = None,
    ) -> AbstractContextManager[None]:
        client, generation = self.client, self._generation
        return super().sent_state(
            *updates,
            is_current=lambda: (
                self._current()
                and self.client is client
                and self._generation == generation
                and (is_current is None or is_current())
            ),
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._identity = self._current_identity()
        if not self._current():
            raise ConnectionError("FlexiRest profile changed")
        await super().start_notify(callback)

    def _handle_notification(self, _: object, data: bytearray) -> None:
        if self._current():
            super()._handle_notification(_, data)

    def _admit_write(
        self,
        client: BleakClient,
        generation: int,
        event: asyncio.Event | None,
        epoch: int,
        caller_cancelled: Callable[[], bool],
    ) -> None:
        if (
            not self._current()
            or generation != self._generation
            or client is not self.client
            or not client.is_connected
        ):
            raise ConnectionError("FlexiRest session changed")
        context = current_command_context()
        if (
            event is not None
            and event.is_set()
            or epoch != self._coordinator.cancel_counter
            or caller_cancelled()
            or context is not None
            and context.kind is not CommandKind.STOP
            and (
                context.cancel_event.is_set()
                or context.caller_is_cancelling is not None
                and context.caller_is_cancelling()
                or context.scheduler_token is self._coordinator.command_scheduler.token
                and context.admitted_stop_epoch != self._coordinator.command_scheduler.stop_epoch
            )
        ):
            note_frame_skipped()
            raise asyncio.CancelledError

    async def _write_link(
        self,
        client: BleakClient,
        char: BleakGATTCharacteristic,
        command: bytes,
        generation: int,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        epoch = self._coordinator.cancel_counter
        caller_cancelled = capture_caller_cancellation()
        async with self._ble_lock:
            await self._emit(
                client,
                char,
                command,
                cancel_event,
                before_write=lambda: self._admit_write(
                    client,
                    generation,
                    cancel_event,
                    epoch,
                    caller_cancelled,
                ),
            )
            if not self._current() or client is not self.client or generation != self._generation:
                raise ConnectionError("FlexiRest session changed during write")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        context = current_command_context()
        event = (
            cancel_event
            if cancel_event is not None
            else (context.cancel_event if context is not None else self._coordinator.cancel_command)
        )
        client, char = self._link()
        # Only one app write, including STOP actions which use a fresh event.
        # Cleanup calls _emit directly and remains uncounted.
        with command_frames_counted():
            await self._write_link(client, char, command, self._generation, event)

    async def _emit(
        self,
        client: BleakClient,
        char: BleakGATTCharacteristic,
        command: bytes,
        event: asyncio.Event | None,
        *,
        before_write: Callable[[], None] | None = None,
    ) -> None:
        # The app leaves Android's write type unchanged. Select from live GATT
        # properties, without imposing a service UUID or invented requirement.
        response = "write" in char.properties

        async def write() -> None:
            if before_write is not None:
                before_write()
            self._record_command_trace(char.uuid, command, response=response, characteristic=char)
            await client.write_gatt_char(char, command, response=response)
            note_frame_written(event)

        await settled(write())

    async def _run_motor(self, command: bytes, duration_ms: int) -> None:
        client, char = self._link()
        generation = self._generation
        epoch = self._coordinator.cancel_counter
        caller_cancelled = capture_caller_cancellation()
        context = current_command_context()
        cancel = context.cancel_event if context is not None else self._coordinator.cancel_command
        started = False
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000

        def admit_press() -> None:
            nonlocal started
            self._admit_write(client, generation, cancel, epoch, caller_cancelled)
            # The dispatched press needs release even if its write fails.
            started = True

        async def press() -> None:
            async with self._ble_lock:
                await self._emit(client, char, command, cancel, before_write=admit_press)

        try:
            await press()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining > 0:
                try:
                    await asyncio.wait_for(cancel.wait(), remaining)
                except TimeoutError:
                    pass
        finally:
            if (
                started
                and client.is_connected
                and (client is not self.client or generation == self._generation)
            ):

                async def release() -> None:
                    def admit_release() -> None:
                        if (
                            not client.is_connected
                            or client is self.client
                            and generation != self._generation
                        ):
                            raise ConnectionError("FlexiRest release session ended")

                    async with self._ble_lock:
                        await self._emit(
                            client, char, codec.STOP, asyncio.Event(), before_write=admit_release
                        )
                    if context is not None:
                        context.cleanup_stop_sent = True

                await settled(release())

    @property
    def protocol_diagnostics(self) -> dict[str, str]:
        return {
            "app_profile": "Sealy FlexiRest 1.0.4 (4)",
            "app_audio_flag": str(self._audio),
            **self._raw,
        }

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = tuple(
            replace(
                spec,
                key=spec.key.replace("sophie", "flexirest"),
                translation_key=(spec.translation_key or spec.key).replace("sophie", "flexirest"),
            )
            for spec in super().controller_button_specs
        )
        specs += (
            ControllerButtonSpec(
                "flexirest_leg_relaxation",
                "Leg relaxation",
                lambda c: c.preset_relaxing_bedtime(),
                translation_key="flexirest_leg_relaxation",
                card=CARD_PRESETS,
                invalidates_position=True,
            ),
            ControllerButtonSpec(
                "flexirest_reapply_alarm",
                "Reapply reported alarm",
                lambda c: require_controller(c, FlexirestController).reapply_alarm(),
                translation_key="flexirest_reapply_alarm",
                requires_confirmation=True,
                entity_registry_enabled_default=False,
            ),
        )
        if app.diagnostics_allowed(self._coordinator.ble_device_name):
            specs += (
                ControllerButtonSpec(
                    "flexirest_query_fault",
                    "Refresh bed fault",
                    lambda c: require_controller(c, FlexirestController).query_fault(),
                    translation_key="flexirest_query_fault",
                    diagnostic=True,
                    entity_registry_enabled_default=False,
                    cancel_movement=False,
                ),
            )
        return specs

    @property
    def replaced_standard_button_keys(self) -> frozenset[str]:
        return frozenset({"preset_relaxing_bedtime"})

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            replace(
                spec,
                key=spec.key.replace("sophie", "flexirest"),
                translation_key=spec.translation_key.replace("sophie", "flexirest"),
            )
            for spec in super().controller_state_sensor_specs
        ) + (
            ControllerStateSensorSpec(
                "flexirest_fault", "flexirest_fault", FAULT, "mdi:alert-circle"
            ),
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return tuple(
            replace(
                spec,
                key=spec.key.replace("sophie", "flexirest"),
                translation_key=spec.translation_key.replace("sophie", "flexirest"),
            )
            for spec in super().controller_state_binary_sensor_specs
        )

    async def query_fault(self) -> None:
        if not app.diagnostics_allowed(self._coordinator.ble_device_name):
            raise ValueError("This FlexiRest name does not expose fault diagnostics")
        await self.write_command(app.FAULT_QUERY)

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self._coordinator.controller_state.get(ALARM_SUPPORTED, False):
            return None
        return AlarmCapability(
            wake_actions=tuple(app.ALARM_MODES),
            weekdays=True,
            massage=app.alarm_massage_allowed(self._coordinator.ble_device_name),
            sounds=("none", *(f"music_{i}" for i in range(1, 6)))
            if self._audio
            else ("none", "alarm"),
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        capability = self.alarm_capability
        if (
            capability is None
            or alarm.wake_action not in capability.wake_actions
            or alarm.sound not in capability.sounds
        ):
            raise ValueError("FlexiRest alarm settings are not available")
        if alarm.massage and not capability.massage:
            raise ValueError("QMS2 does not expose alarm massage")
        sound = 0 if alarm.sound == "none" else 0x10 + int(alarm.sound[-1]) if self._audio else 1
        await self.write_command(
            codec.alarm(
                switch=1 if alarm.enabled else 0xA1,
                hour=alarm.hour,
                minute=alarm.minute,
                weekday_mask=sum(1 << (day + 1) for day in set(alarm.weekdays)),
                repeat=bool(alarm.weekdays),
                mode=app.ALARM_MODES[alarm.wake_action],
                massage=alarm.massage,
                sound=sound,
            )
        )

    async def reapply_alarm(self) -> None:
        """Resave a fresh report, retaining modes the app can display but not select."""
        if self._reported_alarm is None or self._reported_alarm[0] != self._generation:
            raise ValueError("FlexiRest has not reported an alarm on this connection")
        data = self._reported_alarm[1]
        hour, minute = int(f"{data[9]:02x}"), int(f"{data[10]:02x}")
        if hour > 23 or minute > 59 or data[14] not in range(1, 7):
            raise ValueError("The reported FlexiRest alarm cannot be reapplied safely")
        audio = data[8] not in (0x0F, 0xAF)
        await self.write_command(
            codec.alarm(
                switch=1 if data[8] in (0x0F, 0x1F) else 0xA1,
                hour=hour,
                minute=minute,
                weekday_mask=data[12] & 0xFE,
                repeat=bool(data[12] & 0xFE),
                mode=data[14],
                massage=data[15] == 1,
                sound=data[16] if audio else int(data[16] == 1),
            )
        )

    def on_disconnect(self) -> None:
        self._reported_alarm = None
        super().on_disconnect()

    async def lights_off(self) -> None:
        await self.write_command(app.LIGHT_OFF)

    async def set_light_level(self, level: int) -> None:
        if LIGHT_LEVEL not in self._coordinator.controller_state:
            raise ValueError("FlexiRest has not reported brightness support yet")
        if not 0 <= level <= 10:
            raise ValueError("FlexiRest brightness must be 0 through 10")
        await self.write_command(codec.control(0x23, arg=level))

    async def set_light_timer(self, timer_option: str) -> None:
        # Timers are commands, not reported remaining durations.
        from .controller import SolaceController

        if timer_option not in self.light_timer_options:
            raise ValueError("Invalid FlexiRest light timer")
        await SolaceController.set_light_timer(self, timer_option)

    def _parse_notification(self, data: bytes) -> None:
        updates = self._parse_control_updates(data)
        if data.startswith(codec.HEADER + bytes((5, 0, 1))) and len(data) >= 8:
            value = data[7]
            self._raw["light_level"] = str(value)
            if 0 <= value <= 10:
                updates += [LIGHT_LEVEL(value), UNDER_BED_LIGHTS_ON(value > 0)]
            else:
                updates += [LIGHT_LEVEL(None), UNDER_BED_LIGHTS_ON(None)]
            if value == 0:
                updates.append(LIGHT_TIMER_OPTION("Off"))
        if len(data) >= 9 and any(
            data.startswith(codec.HEADER + bytes((1, 0, op, 11))) for op in (9, 10)
        ):
            updates += [SYNC_SUPPORTED(True), SYNCHRO_MODE(data[8] == 1)]
        if data.startswith(codec.HEADER + bytes((1, 0, 3, 11))) and len(data) >= 9:
            self._audio = data[8] != 0
            self._reported_alarm = None
            updates += [
                ALARM_SUPPORTED(True),
                ALARM_AUDIO(self._audio),
                ALARM_ENABLED(False),
                ALARM_TIME(None),
                ALARM_WEEKDAYS(""),
                ALARM_MODE("none"),
                ALARM_MASSAGE(False),
                ALARM_RING(False),
            ]
        elif data.startswith(codec.HEADER + bytes((1, 0, 4, 19))) and len(data) >= 17:
            self._audio = data[8] not in (15, 175)
            self._reported_alarm = (self._generation, bytes(data[:17]))
            self._raw.update(
                alarm_status=f"{data[8]:02X}",
                alarm_mode=f"{data[14]:02X}",
                alarm_sound=f"{data[16]:02X}",
            )
            updates += [
                ALARM_SUPPORTED(True),
                ALARM_AUDIO(self._audio),
                ALARM_ENABLED(data[8] in (15, 31)),
                ALARM_TIME(f"{data[9]:02x}:{data[10]:02x}"),
                ALARM_WEEKDAYS(",".join(str(day) for day in range(1, 8) if data[12] & 1 << day)),
                ALARM_MODE(
                    next(
                        (key for key, value in app.ALARM_MODES.items() if value == data[14]),
                        f"unknown_{data[14]:02x}",
                    )
                ),
                ALARM_MASSAGE(data[15] == 1),
                ALARM_RING(data[16] == 1),
            ]
            # Android Home also posts a default MessageEvent here. That hides
            # its sync rows; it does not prove a change in physical sync state.
            self._raw["android_sync_row_after_alarm"] = "hidden"
        if data.startswith(codec.HEADER + bytes((3, 4))) and len(data) >= 10:
            part, fault = data[6:8].hex().upper(), data[8:10].hex().upper()
            self._raw.update(fault_part=part, fault_code=fault)
            updates.append(
                FAULT(
                    f"{app.PARTS.get(part, 'Unknown component')}: {app.FAULTS.get(fault, 'Unknown fault')}"
                )
            )
        if updates:
            self.forward_controller_state_updates(*updates)
