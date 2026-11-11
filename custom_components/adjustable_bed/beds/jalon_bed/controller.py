"""Session, gesture and alarm behavior of OkinComfortBed Ⅱ (Jalon), row135."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, cast

from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_UTILITY
from ...codec import keeson as codec
from ...const import CONF_PRODUCT_TYPE
from ...controller_state import StateKey
from ...profiles import jalon_bed as app
from ...profiles.keeson import KeesonProfile, encode
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

SERVICE: Final = codec.JALON_WRITE_SERVICE
WRITE: Final = codec.JALON_WRITE
NOTIFY_SERVICE: Final = codec.JALON_NOTIFY_SERVICE
NOTIFY: Final = codec.JALON_NOTIFY
TIMER_BUCKET: Final = StateKey[int | None]("jalon_massage_timer_bucket")


def alarm_frame(
    *, enabled: bool, weekdays: Sequence[int], hour: int, minute: int, preset: str, now: datetime
) -> bytes:
    """The selected alarm fields, distinct from the current Calendar clock sync."""
    if not enabled:
        return codec.alarm_table(3, bytes(4))
    if (
        type(hour) is not int
        or not 0 <= hour <= 23
        or type(minute) is not int
        or not 0 <= minute <= 59
    ):
        raise ValueError("Choose an hour 0–23 and minute 0–59")
    if preset not in app.WAKE_MODES:
        raise ValueError("Choose none, memory_1, memory_2 or massage")
    if any(type(day) is not int or day not in range(7) for day in weekdays) or len(
        set(weekdays)
    ) != len(weekdays):
        raise ValueError("Weekdays must be unique, Monday 0 through Sunday 6")
    if weekdays:
        mask = 0x80 | sum(1 << ((day + 1) % 7) for day in weekdays)
    else:
        # The app compares hours/minutes, so the selected current minute means tomorrow.
        target = now + timedelta(days=int((now.hour, now.minute) >= (hour, minute)))
        mask = 1 << ((target.weekday() + 1) % 7)
    return codec.alarm_table(3, bytes((hour, minute, mask, app.WAKE_MODES[preset])))


class JalonBedController(ProfileExecution[KeesonProfile], BedController):
    """Drive the shared byte codec with this artifact's own behavior and gates."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILE
        self.layout_key = str(coordinator.entry.data.get(CONF_PRODUCT_TYPE, "40"))
        if self.layout_key not in app.LAYOUTS:
            raise ValueError("Choose a supported Jalon physical layout")
        self._notify_char: BleakGATTCharacteristic | None = None
        self._prefix: bytes | None = None
        self._session = 0

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def control_characteristic_uuid(self) -> str:
        return WRITE

    def _role(self, service_uuid: str, char_uuid: str) -> BleakGATTCharacteristic | None:
        client = self.client
        if client is None or not client.is_connected or client.services is None:
            raise ConnectionError("Jalon bed is disconnected")
        for service in client.services:
            if service.uuid.lower() == service_uuid:
                return service.get_characteristic(char_uuid)
        return None

    def _control_role(self) -> BleakGATTCharacteristic:
        char = self._role(SERVICE, WRITE)
        if char is None:
            raise ConnectionError("Jalon bed requires FFE9 under FFE5")
        if not {"write", "write-without-response"} & set(char.properties):
            raise ConnectionError("Jalon FFE9 is not writable")
        return char

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        char = self._control_role()
        props = set(char.properties)
        # The app inherits discovered write type. Choose from the live properties,
        # rather than claiming one fixed ATT mode from static APK evidence.
        await self._write_gatt_with_retry(
            WRITE,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            characteristic=char,
            response="write" in props,
            wall_clock_pacing=repeat_delay_ms == app.REFRESH_MS,
            expected_client=self.client,
        )

    async def _release(self, count: int, session: int | None = None) -> None:
        if session is not None and session != self._session:
            return
        await self.write_command(
            encode(self.profile, 0),
            repeat_count=count,
            repeat_delay_ms=0,
            cancel_event=asyncio.Event(),
        )

    async def _burst(
        self, word: int, *, count: int = app.UTILITY_REPEATS, releases: int = app.UTILITY_RELEASES
    ) -> None:
        session = self._session
        try:
            await self.write_command(
                encode(self.profile, word), repeat_count=count, repeat_delay_ms=0
            )
        finally:
            await self._release(releases, session)

    async def move_axis(self, axis: str, up: bool) -> None:
        if axis not in app.LAYOUTS[self.layout_key].axes:
            raise ValueError("This Jalon layout has no such motor")
        if self._coordinator.cancel_command.is_set():
            return
        session = self._session
        try:
            await self._release(app.MOTOR_RELEASES, session)
            if session != self._session:
                raise ConnectionError("Jalon session ended before movement")
            count, _ = self.motor_pulse_settings()
            await self.write_command(
                encode(self.profile, app.MOTORS[axis][0 if up else 1]),
                repeat_count=self.leased_hold_refreshes(app.REFRESH_MS) or count,
                repeat_delay_ms=app.REFRESH_MS,
            )
        finally:
            await self._release(app.MOTOR_RELEASES, session)

    async def move_head_up(self) -> None:
        await self.move_axis("head", True)

    async def move_head_down(self) -> None:
        await self.move_axis("head", False)

    async def move_back_up(self) -> None:
        await self.move_axis("back", True)

    async def move_back_down(self) -> None:
        await self.move_axis("back", False)

    async def move_feet_up(self) -> None:
        await self.move_axis("feet", True)

    async def move_feet_down(self) -> None:
        await self.move_axis("feet", False)

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def stop_all(self) -> None:
        await self._release(app.MOTOR_RELEASES)

    move_head_stop = stop_all
    move_back_stop = stop_all
    move_feet_stop = stop_all
    move_legs_stop = stop_all

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        def spec(axis: str) -> MotorControlSpec:
            return MotorControlSpec(
                axis,
                app.AXIS_LABELS[axis],
                lambda ctrl: cast(JalonBedController, ctrl).move_axis(axis, True),
                lambda ctrl: cast(JalonBedController, ctrl).move_axis(axis, False),
                lambda ctrl: ctrl.stop_all(),
            )

        return tuple(spec(axis) for axis in app.LAYOUTS[self.layout_key].axes)

    async def preset(self, name: str, *, position_flat: bool = False) -> None:
        await self._burst(
            app.PRESETS[name],
            count=app.POSITION_FLAT_REPEATS if position_flat else app.PRESET_REPEATS,
            releases=1,
        )

    async def preset_flat(self) -> None:
        await self.preset("flat", position_flat=True)

    async def preset_zero_g(self) -> None:
        await self.preset("zero_g")

    async def preset_lounge(self) -> None:
        await self.preset("lounge")

    async def preset_tv(self) -> None:
        await self.preset("tv")

    async def preset_anti_snore(self) -> None:
        await self.preset("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.preset(f"memory_{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Jalon held recall does not prove physical memory programming")

    @property
    def memory_slot_count(self) -> int:
        return 2

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(app.HELD)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in app.HELD or not 1 <= duration_ms <= 30000:
            raise ValueError(
                "Jalon preset gestures must be between 1 and 30000 ms (limited to 8 seconds)"
            )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        # No release frame on preset touch-up in this artifact. No queued Android
        # delayed callback can cancel a later HA gesture or write after teardown.
        duration_ms = min(app.HOLD_LIMIT_MS, self.leased_hold_ms(duration_ms))
        timeout = asyncio.timeout(duration_ms / 1000)
        try:
            async with timeout:
                await self.write_command(
                    encode(self.profile, app.HELD[control]),
                    repeat_count=(duration_ms + app.REFRESH_MS - 1) // app.REFRESH_MS,
                    repeat_delay_ms=app.REFRESH_MS,
                )
        except TimeoutError:
            if not timeout.expired():
                raise
            # The eight-second app gesture ends by ceasing refresh, without STOP.

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        def preset_button(name: str) -> ControllerButtonSpec:
            return ControllerButtonSpec(
                f"jalon_{name}",
                f"{name.replace('_', ' ').title()} (app gesture)",
                lambda ctrl: cast(JalonBedController, ctrl).preset(name),
                hold=ControllerHoldSpec(name),
                card=CARD_UTILITY,
            )

        return (
            *(preset_button(name) for name in app.PRESETS),
            ControllerButtonSpec(
                "jalon_flat_zero_g",
                "Flat + Zero G held gesture",
                lambda ctrl: ctrl.hold_control("flat_zero_g", app.HOLD_LIMIT_MS),
                hold=ControllerHoldSpec("flat_zero_g"),
            ),
            *(
                ControllerButtonSpec(
                    f"jalon_massage_{name}",
                    f"Massage {name}",
                    lambda ctrl, word=word: cast(JalonBedController, ctrl)._burst(word),
                    translation_key="jalon_bed_massage_timer" if name == "timer" else f"jalon_massage_{name}",
                    card=CARD_MASSAGE_TIMER if name == "timer" else CARD_MASSAGE,
                )
                for name, word in app.MASSAGE.items()
                if name not in ("all", "type")
            ),
        )

    async def massage_toggle(self) -> None:
        await self._burst(app.MASSAGE["all"])

    async def massage_mode_step(self) -> None:
        await self._burst(app.MASSAGE["type"])

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_light_state_feedback(self) -> bool:
        return True

    async def _set_light(self, enabled: bool) -> None:
        state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
        if state is None:
            raise ValueError("Jalon light state is unknown; use the light toggle")
        if state != enabled:
            await self.lights_toggle()

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def lights_toggle(self) -> None:
        await self._burst(app.LIGHT)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._control_role()
        self._session += 1
        self._prefix = None
        char = self._role(NOTIFY_SERVICE, NOTIFY)
        if char is None:
            return
        client = self.client
        assert client is not None
        session = self._session
        self._notify_char = char
        await client.start_notify(
            char, lambda sender, data: self._notification(sender, data, session)
        )

    def _notification(
        self, sender: BleakGATTCharacteristic, data: bytearray, session: int | None = None
    ) -> None:
        if session is not None and session != self._session:
            return
        if self._notify_char is None or sender.handle != self._notify_char.handle:
            return
        raw = bytes(data)
        self.forward_raw_notification(NOTIFY, raw)
        if len(raw) > 3 and raw[:3] == codec.JALON_PREFIX:
            self._prefix = raw if len(raw) < 23 else None
            return
        if len(raw) not in (10, 16):
            prefix, self._prefix = self._prefix, None
            if prefix is None or len(prefix) + len(raw) != 23:
                return
            raw = prefix + raw
        else:
            self._prefix = None
        status = codec.parse_jalon_status(raw)
        self.forward_controller_state_updates(
            TIMER_BUCKET(status.timer_minutes), UNDER_BED_LIGHTS_ON(status.light_value > 0)
        )

    async def stop_notify(self) -> None:
        self._session += 1
        char, self._notify_char = self._notify_char, None
        self._prefix = None
        client = self.client
        if char is not None and client is not None and client.is_connected:
            await client.stop_notify(char)

    def on_disconnect(self) -> None:
        self._session += 1
        self._notify_char = None
        self._prefix = None
        self.forward_controller_state_updates(TIMER_BUCKET(None), UNDER_BED_LIGHTS_ON(None))

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "jalon_massage_timer_bucket",
                "jalon_massage_timer_bucket",
                TIMER_BUCKET,
                "mdi:timer-outline",
                native_unit_of_measurement="min",
            ),
        )

    @property
    def supports_clock_sync(self) -> bool:
        return True

    @property
    def supports_clock_alarm(self) -> bool:
        return True

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(app.WAKE_MODES)

    async def sync_clock(self) -> None:
        await self.write_command(codec.clock(dt_util.now()))

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        session = self._session
        now = dt_util.now()
        frame = alarm_frame(
            enabled=enabled, weekdays=weekdays, hour=hour, minute=minute, preset=preset, now=now
        )
        try:
            if enabled:
                await self.write_command(codec.clock(now))
                await asyncio.sleep(app.ALARM_DELAY_MS / 1000)
                if session != self._session:
                    raise ConnectionError("Jalon session ended before scheduled alarm write")
            await self.write_command(
                frame, repeat_count=1 if enabled else app.DISABLE_REPEATS, repeat_delay_ms=0
            )
        finally:
            await self._release(1, session)
