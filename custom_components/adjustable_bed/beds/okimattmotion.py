"""Session and controls for the OkimattMotion app profile."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING, Final, cast

from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..alarm import AlarmCapability, AlarmRequest
from ..app_session import app_session
from ..card import CARD_MASSAGE, CARD_PRESETS
from ..command_scheduler import command_frames_counted, current_command_context, note_frame_skipped
from ..const import CONF_PRODUCT_TYPE
from ..controller_state import StateKey
from ..profiles import okimattmotion as app
from ..profiles.keeson import KeesonProfile
from ..state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, massage_intensity
from .base import BedController, ProfileExecution
from .cancellation import settled
from .entity_specs import ControllerButtonSpec, ControllerSwitchSpec, MotorControlSpec

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_ALARM: Final = AlarmCapability(
    wake_actions=tuple(app.WAKE_MODES),
    sleep_timers=tuple(minutes for minutes in app.SLEEP_TIMERS if minutes is not None),
)
_MASSAGE_POWER: Final = StateKey[bool | None]("okimattmotion_massage_power")
_MEMORY: Final = {1: "memory_1", 2: "memory_2"}


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    response: bool


@dataclass(slots=True)
class _Massage:
    intensity: int = 0
    wave: int = 0


class OkimattMotionController(ProfileExecution[KeesonProfile], BedController):
    """Serialize app commands through the coordinator's current BLE session."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.OKIMATTMOTION
        self._combined = coordinator.entry.data.get(CONF_PRODUCT_TYPE) != "20"
        self._link: _Link | None = None
        self._massage = app_session(
            coordinator.hass, coordinator.address, self.profile.key, _Massage
        )

    @property
    def control_characteristic_uuid(self) -> str:
        return app.WRITE_CHAR

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return True

    async def async_discover_capabilities(self) -> None:
        self._link = None
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("OkimattMotion is disconnected")
        service = next((s for s in client.services if s.uuid.lower() == app.WRITE_SERVICE), None)
        char = service.get_characteristic(app.WRITE_CHAR) if service is not None else None
        if char is None or not {"write", "write-without-response"}.intersection(char.properties):
            raise ConnectionError("OkimattMotion requires writable FFE9 under FFE5")
        self._link = _Link(client, char, "write" in char.properties)

    def on_disconnect(self) -> None:
        self._link = None

    def _current(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _connection(self) -> _Link:
        if (link := self._link) is None or not self._current(link):
            raise ConnectionError("OkimattMotion connection ended")
        return link

    async def _write(
        self,
        link: _Link,
        command: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 0,
        cancel_event: asyncio.Event | None = None,
        command_factory: Callable[[], bytes] | None = None,
        on_write: Callable[[], None] | None = None,
    ) -> None:
        def check_link() -> None:
            if not self._current(link):
                raise ConnectionError("OkimattMotion connection changed before write")

        await self._write_gatt_with_retry(
            app.WRITE_CHAR,
            command,
            repeat_count,
            repeat_delay_ms,
            cancel_event,
            characteristic=link.write,
            response=link.response,
            expected_client=link.client,
            before_write=check_link,
            wall_clock_pacing=True,
            command_factory=command_factory,
            on_write=on_write,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        await self._write(
            self._connection(),
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    async def _key(self, word: int, *, link: _Link | None = None, cleanup: bool = False) -> bool:
        link = link if link is not None else self._connection()
        event = asyncio.Event() if cleanup else self._coordinator.cancel_command
        written = False

        def sent() -> None:
            nonlocal written
            written = True

        await self._write(link, app.control_frame(word), cancel_event=event, on_write=sent)
        return written and self._current(link)

    async def _release_manual(self, link: _Link, *, movement_cleanup: bool = False) -> None:
        error: BleakError | TimeoutError | None = None
        complete = True
        for _ in range(app.MANUAL_STOP_WRITES):
            try:
                sent = await self._key(app.MANUAL_STOP, link=link, cleanup=True)
                complete = complete and sent
            except (BleakError, TimeoutError) as err:
                error = err
        if error is not None:
            raise error
        if movement_cleanup and complete and (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True

    async def _manual_stop(self) -> None:
        await settled(self._release_manual(self._connection()))

    async def _stop_all(self, link: _Link) -> None:
        try:
            await self._release_manual(link)
        finally:
            await self._key(app.PRESET_STOP, link=link, cleanup=True)

    async def stop_all(self) -> None:
        await settled(self._stop_all(self._connection()))

    async def _move(self, axis: str, up: bool) -> None:
        if axis == "back_legs" and not self._combined:
            raise self.not_supported("combined movement")
        if self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            return
        link = self._connection()
        count, _ = self.motor_pulse_settings()
        async with self.releasing(lambda: self._release_manual(link, movement_cleanup=True)):
            await self._write(
                link,
                app.control_frame(app.MOTORS[axis][0 if up else 1]),
                repeat_count=self.leased_hold_refreshes(app.REFRESH_MS) or count,
                repeat_delay_ms=app.REFRESH_MS,
            )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                "both" if axis == "back_legs" else axis,
                axis,
                lambda ctrl, axis=axis: cast(OkimattMotionController, ctrl)._move(axis, True),
                lambda ctrl, axis=axis: cast(OkimattMotionController, ctrl)._move(axis, False),
                lambda ctrl: cast(OkimattMotionController, ctrl)._manual_stop(),
                stop_scope="side",
            )
            for axis in (tuple(app.MOTORS) if self._combined else ("back", "legs"))
        )

    async def move_back_up(self) -> None:
        await self._move("back", True)

    async def move_back_down(self) -> None:
        await self._move("back", False)

    async def move_back_stop(self) -> None:
        await self._manual_stop()

    async def move_legs_up(self) -> None:
        await self._move("legs", True)

    async def move_legs_down(self) -> None:
        await self._move("legs", False)

    async def move_legs_stop(self) -> None:
        await self._manual_stop()

    async def move_head_up(self) -> None:
        raise NotImplementedError("OkimattMotion has no separate headrest control")

    async def move_head_down(self) -> None:
        raise NotImplementedError("OkimattMotion has no separate headrest control")

    async def move_head_stop(self) -> None:
        raise NotImplementedError("OkimattMotion has no separate headrest control")

    async def move_feet_up(self) -> None:
        raise NotImplementedError("OkimattMotion exposes feet movement under legs")

    async def move_feet_down(self) -> None:
        raise NotImplementedError("OkimattMotion exposes feet movement under legs")

    async def move_feet_stop(self) -> None:
        raise NotImplementedError("OkimattMotion exposes feet movement under legs")

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return len(_MEMORY)

    async def _recall(self, name: str) -> None:
        link = self._connection()
        try:
            await self._key(app.PRESETS[name][0], link=link)
        except asyncio.CancelledError:
            if self._current(link):
                await settled(self._key(app.PRESET_STOP, link=link, cleanup=True))
            raise

    async def preset_flat(self) -> None:
        await self._recall("flat")

    async def preset_zero_g(self) -> None:
        await self._recall("zero_g")

    async def preset_anti_snore(self) -> None:
        await self._recall("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._recall(_MEMORY[memory_num])

    async def _program(self, name: str) -> None:
        await self._key(app.PRESETS[name][1])

    async def program_memory(self, memory_num: int) -> None:
        if not self.is_memory_slot_programmable(memory_num):
            raise self.not_supported(f"save memory {memory_num}")
        await self._program(_MEMORY[memory_num])

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        saves = tuple(
            ControllerButtonSpec(
                f"okimattmotion_save_{name}",
                label,
                lambda ctrl, name=name: cast(OkimattMotionController, ctrl)._program(name),
                translation_key=f"okimattmotion_save_{name}",
                requires_confirmation=True,
                card=CARD_PRESETS,
            )
            for name, label in (
                ("zero_g", "Save Zero Gravity"),
                ("flat", "Save Flat"),
                ("anti_snore", "Save Quiet Sleep"),
            )
        )
        if not self._combined:
            return saves
        return (
            *saves,
            ControllerButtonSpec(
                "okimattmotion_book",
                "Book",
                lambda ctrl: ctrl.preset_anti_snore(),
                translation_key="okimattmotion_book",
                invalidates_position=True,
                card=CARD_PRESETS,
            ),
        )

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def light_state_is_assumed(self) -> bool:
        return True

    async def _light(self, enabled: bool) -> None:
        if await self._key(app.LIGHT[enabled]):
            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(enabled))

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_intensity_control(self) -> bool:
        return True

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["all", "wave"]

    @property
    def massage_intensity_max(self) -> int:
        return max(app.MASSAGE_LEVELS)

    def massage_intensity_min(self, zone: str) -> int:
        return min(app.MASSAGE_LEVELS)

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return list(app.MASSAGE_TIMERS)

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in app.MASSAGE_TIMERS:
            raise self.not_supported("massage timer duration")
        if await self._key(app.MASSAGE_TIMERS[minutes]):
            self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(minutes))

    def _set_intensity(self, level: int) -> None:
        self._massage.intensity = level
        self.forward_controller_state_updates(
            massage_intensity("all")(level or None),
            _MASSAGE_POWER(bool(level)),
        )

    def _set_wave(self, level: int) -> None:
        self._massage.wave = level
        self.forward_controller_state_updates(massage_intensity("wave")(level or None))

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones or level not in app.MASSAGE_LEVELS:
            raise self.not_supported("massage level")
        link = self._connection()
        intensity = level if zone == "all" else self._massage.intensity
        wave = level if zone == "wave" else self._massage.wave
        if not await self._key(app.MASSAGE_INTENSITY + intensity, link=link):
            return
        self._set_intensity(intensity)
        if await self._key(app.MASSAGE_WAVE + wave, link=link):
            self._set_wave(wave)

    async def _massage_off(self, link: _Link) -> None:
        try:
            if await self._key(app.MASSAGE_WAVE, link=link, cleanup=True):
                self._set_wave(0)
        finally:
            await asyncio.sleep(app.MASSAGE_POWER_DELAY_S)
            if await self._key(app.MASSAGE_INTENSITY, link=link, cleanup=True):
                self._set_intensity(0)
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(None))

    async def massage_off(self) -> None:
        with command_frames_counted():
            await settled(self._massage_off(self._connection()))

    async def _set_massage_power(self, enabled: bool) -> None:
        if not enabled:
            await self.massage_off()
            return
        if self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            return
        link = self._connection()
        complete = False
        try:
            if not await self._key(app.MASSAGE_WAVE + 1, link=link):
                return
            await asyncio.sleep(app.MASSAGE_POWER_DELAY_S)
            if not await self._key(app.MASSAGE_INTENSITY + 1, link=link):
                return
            if (
                await self._key(app.MASSAGE_TIMERS[10], link=link)
                and not self._coordinator.cancel_command.is_set()
            ):
                complete = True
                self._set_wave(1)
                self._set_intensity(1)
                self.forward_controller_state_updates(MASSAGE_TIMER_MINUTES(10))
        finally:
            if not complete and self._current(link):
                await settled(self._massage_off(link))

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "okimattmotion_massage_power",
                "okimattmotion_massage_power",
                lambda ctrl, on: cast(OkimattMotionController, ctrl)._set_massage_power(on),
                state_key=_MASSAGE_POWER,
                assumed_state=True,
                card=CARD_MASSAGE,
            ),
        )

    @property
    def alarm_capability(self) -> AlarmCapability:
        return _ALARM

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        target = time(alarm.hour, alarm.minute) if alarm.enabled else None
        await self._write(
            self._connection(),
            b"",
            repeat_count=app.ALARM_WRITES,
            command_factory=lambda: app.alarm_frame(
                dt_util.now(),
                target,
                alarm.sleep_timer,
                alarm.wake_action,
            ),
        )
