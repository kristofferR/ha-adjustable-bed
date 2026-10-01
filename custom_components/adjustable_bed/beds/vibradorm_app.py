"""Explicit Caresse/Werkmeister app paths from the accepted row031 artifacts.

Published feature state is local intent, never a device acknowledgment. The
legacy Vibradorm controller remains independent of these app-selected layouts.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..vibradorm_app_state import VibradormAppFloorIntent, VibradormAppTimerIntent
from .base import (
    POSITION_AXIS_COMMANDS,
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    SideBoundController,
)

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

ControlType = int | Literal["other"]
COMMAND: Final = "00001526-9f03-0de5-96c5-b8f4f3081186"
LIGHT: Final = "00001529-9f03-0de5-96c5-b8f4f3081186"
CBI: Final = "00001550-9f03-0de5-96c5-b8f4f3081186"
RESPONSE: Final = "00001551-9f03-0de5-96c5-b8f4f3081186"
INFO_FIELDS: Final = tuple(
    (field, f"0000{uuid}-0000-1000-8000-00805f9b34fb")
    for field, uuid in (
        ("device_name", "2a00"),
        ("manufacturer", "2a29"),
        ("model", "2a24"),
        ("firmware", "2a26"),
        ("software", "2a28"),
    )
)
MOTORS: Final = {
    "head_up": 3,
    "head_down": 2,
    "back_up": 11,
    "back_down": 10,
    "legs_up": 9,
    "legs_down": 8,
    "feet_up": 5,
    "feet_down": 4,
    "all_up": 16,
    "all_down": 0,
}
MEMORY: Final = (14, 15, 12, 26, 27, 28)
MOOD_EFFECTS: Final = ("sunrise", "rainbow", "disco")
MASSAGE_WAVES: Final = ("1", "2", "3", "4")
# The shipped fixed-100 HSV conversion has truncation, so retain its outputs.
MOOD_PALETTE: Final = {
    "#008a00": (0, 138, 0),
    "#00aba9": (0, 171, 169),
    "#1ba1e2": (26, 161, 226),
    "#0050ef": (0, 80, 239),
    "#6a00ff": (106, 0, 255),
    "#aa00ff": (170, 0, 255),
    "#f472d0": (244, 114, 208),
    "#d80073": (216, 0, 115),
    "#a20025": (162, 0, 36),
    "#e51400": (229, 19, 0),
    "#fa6800": (250, 104, 0),
    "#f0a30a": (240, 163, 9),
    "#e3c800": (227, 200, 0),
    "#825a2c": (130, 90, 44),
    "#6d8764": (109, 135, 100),
    "#647687": (100, 118, 135),
    "#76708a": (118, 112, 138),
    "#ffffff": (255, 255, 255),
}


@dataclass(frozen=True, slots=True)
class VibradormAppProfile:
    app_profile: str
    control_type: ControlType
    restored: bool
    floor_light: bool
    rgb: bool
    massage: bool
    light_extension: bool
    groups: tuple[str, ...]
    basic: bool
    memory_slots: int

    @property
    def article_requests(self) -> bool:
        return self.control_type in (5, 6, 7)

    @property
    def sync(self) -> bool:
        return self.app_profile == "werkmeister" and self.control_type == 7


def validate_vibradorm_app_profile(
    app_profile: str,
    control_type: ControlType,
    *,
    restored: bool = False,
    floor_light: bool | None = None,
    rgb: bool = False,
    massage: bool = False,
    light_extension: bool = False,
) -> VibradormAppProfile:
    """Validate an explicit app layout without consulting BLE or generic options."""
    if app_profile not in ("caresse", "werkmeister"):
        raise ValueError("App profile must be caresse or werkmeister")
    if isinstance(control_type, bool) or (
        control_type != "other"
        and (not isinstance(control_type, int) or control_type not in (-1, 0, 1, 2, 3, 4, 5, 6, 7))
    ):
        raise ValueError("Use an exact control type or the explicit other layout")
    if any(type(flag) is not bool for flag in (restored, rgb, massage, light_extension)):
        raise ValueError("Retained feature flags must be booleans")
    if floor_light is not None and type(floor_light) is not bool:
        raise ValueError("Floor-light flag must be boolean")
    floor = app_profile == "werkmeister" if floor_light is None else floor_light
    if app_profile == "werkmeister":
        if control_type not in (5, 7) or restored or not floor or rgb or massage or light_extension:
            raise ValueError("Werkmeister exposes only its two shipped floor-light profiles")
    elif not restored and (control_type != 2 or floor or rgb or massage or light_extension):
        raise ValueError("Fresh Caresse is type 2 with all optional features disabled")
    groups = (
        ()
        if control_type == "other"
        else ("back", "legs")
        if control_type in (0, 2, 5)
        else ("head", "back", "legs")
        if control_type in (3, 4, 6)
        else ("head", "back", "legs", "feet")
    )
    basic = control_type in (2, 3)
    slots = 0 if control_type == 2 else 3 if control_type == 3 else 6
    return VibradormAppProfile(
        app_profile,
        control_type,
        restored,
        floor,
        rgb,
        massage,
        light_extension,
        groups,
        basic,
        slots,
    )


@dataclass(frozen=True, slots=True)
class VibradormAppMetadata:
    model: str
    firmware: str
    software: str
    main_firmware_article: str | None = None


class VibradormAppMetadataProgress(TypedDict, total=False):
    """Completed fields only; empty strings are successful read results."""

    model: str
    firmware: str
    software: str
    main_firmware_article: str


def _characteristic(client: BleakClient, uuid: str, operation: str) -> BleakGATTCharacteristic:
    if not client.is_connected or not client.services:
        raise ConnectionError("Vibradorm app requires discovered services")
    # SweetBlue resolves the first exact UUID in native service/characteristic
    # order. Validate that selected role rather than searching a later duplicate.
    selected = next(
        (
            char
            for service in client.services
            for char in service.characteristics
            if char.uuid.lower() == uuid
        ),
        None,
    )
    if selected is None:
        raise ValueError(f"Missing exact {uuid} characteristic")
    properties = selected.properties
    acceptable = (
        {"write", "write-without-response"}
        if operation == "write"
        else ({"notify", "indicate"} if operation == "notify" else {"read"})
    )
    if not acceptable.intersection(properties):
        raise ValueError(f"Characteristic {uuid} cannot {operation}")
    return selected


def _write_response(client: BleakClient, uuid: str) -> bool:
    # Android inherits the runtime mode. This preference is the host policy.
    return "write" in _characteristic(client, uuid, "write").properties


def _decode_java_utf8(data: bytes) -> str:
    """Match Java UTF-8 replacement lengths, including encoded surrogates."""
    result: list[str] = []
    offset = 0
    while offset < len(data):
        remaining = data[offset:]
        try:
            result.append(remaining.decode("utf-8"))
            break
        except UnicodeDecodeError as error:
            result.append(remaining[: error.start].decode("utf-8"))
            consumed = error.end
            start = error.start
            if (
                remaining[start] == 0xED
                and start + 1 < len(remaining)
                and 0xA0 <= remaining[start + 1] <= 0xBF
            ):
                # Java's malformed surrogate sequence includes its valid
                # continuation bytes; CPython instead rejects the lead byte.
                consumed = start + 2
                if consumed < len(remaining) and 0x80 <= remaining[consumed] <= 0xBF:
                    consumed += 1
            result.append("\ufffd")
            offset += consumed
    return "".join(result)


def decode_standard_info(data: bytes | bytearray | None) -> str:
    if data is None:
        return ""
    return _decode_java_utf8(bytes(data)).strip("".join(map(chr, range(33))))


def parse_article(data: bytes) -> str | None:
    return _decode_java_utf8(data[3:]) if len(data) > 4 and data[:3] == b"\x21\xa0\xc8" else None


def parse_sync(data: bytes) -> bool | None:
    if len(data) < 3:
        return None
    if data[:2] == b"\x20\x3f":
        return bool(data[2] & 0x40)
    if data[0] == 0x3F:
        return bool(data[1] & 0x40)
    return None


async def _cancellable[T](operation: Coroutine[Any, Any, T], event: asyncio.Event | None) -> T:
    if event is None:
        return await operation
    if event.is_set():
        operation.close()
        raise asyncio.CancelledError
    task = asyncio.create_task(operation)
    cancellation = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait((task, cancellation), return_when=asyncio.FIRST_COMPLETED)
        if cancellation in done:
            raise asyncio.CancelledError
        return task.result()
    finally:
        for pending in (task, cancellation):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, cancellation, return_exceptions=True)


async def _information_transaction(
    client: BleakClient,
    profile: VibradormAppProfile,
    deadline: float,
    cancel_event: asyncio.Event | None,
    *,
    prepare_reply: Callable[[], asyncio.Future[str]] | None = None,
    metadata_progress: Callable[[VibradormAppMetadataProgress], None] | None = None,
) -> VibradormAppMetadata:
    """One ordered transaction under the caller's whole onboarding deadline."""
    values: dict[str, str] = {}
    article: str | None = None
    async with asyncio.timeout_at(deadline):
        for field, uuid in INFO_FIELDS:
            char = _characteristic(client, uuid, "read")
            raw = await _cancellable(client.read_gatt_char(char), cancel_event)
            values[field] = decode_standard_info(raw)
            if metadata_progress is not None:
                if field == "model":
                    metadata_progress({"model": values[field]})
                elif field == "firmware":
                    metadata_progress({"firmware": values[field]})
                elif field == "software":
                    metadata_progress({"software": values[field]})
        if profile.article_requests:
            for _ in range(3):
                if prepare_reply is None:
                    raise RuntimeError("Article reply routing is required")
                article_reply = prepare_reply()
                await _cancellable(
                    client.write_gatt_char(
                        _characteristic(client, CBI, "write"),
                        b"\x01\xa0\xc8",
                        response=_write_response(client, CBI),
                    ),
                    cancel_event,
                )

                async def receive(reply: asyncio.Future[str] = article_reply) -> str:
                    return await reply

                article = await _cancellable(receive(), cancel_event)
    return VibradormAppMetadata(values["model"], values["firmware"], values["software"], article)


async def async_prepare_vibradorm_app_pairing(
    client: BleakClient,
    app_profile: str,
    control_type: ControlType,
    *,
    deadline: float,
    cancel_event: asyncio.Event | None = None,
    metadata_progress: Callable[[VibradormAppMetadataProgress], None] | None = None,
) -> VibradormAppMetadata:
    """Read app information before native pairing; the caller owns native proof."""
    profile = validate_vibradorm_app_profile(
        app_profile,
        control_type,
        restored=app_profile == "caresse" and control_type != 2,
    )
    if not math.isfinite(deadline) or deadline <= asyncio.get_running_loop().time():
        raise TimeoutError("The whole onboarding deadline has expired")
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError
    reply: asyncio.Future[str] | None = None
    subscribed = False
    notify_char: BleakGATTCharacteristic | None = None

    def prepare() -> asyncio.Future[str]:
        nonlocal reply
        reply = asyncio.get_running_loop().create_future()
        return reply

    def callback(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
        result = parse_article(bytes(data))
        if result is not None and reply is not None and not reply.done():
            if metadata_progress is not None:
                metadata_progress({"main_firmware_article": result})
            reply.set_result(result)

    try:
        async with asyncio.timeout_at(deadline):
            if not profile.basic:
                notify_char = _characteristic(client, RESPONSE, "notify")
                subscribed = True
                await _cancellable(client.start_notify(notify_char, callback), cancel_event)
            return await _information_transaction(
                client,
                profile,
                deadline,
                cancel_event,
                prepare_reply=prepare,
                metadata_progress=metadata_progress,
            )
    finally:
        if reply is not None and not reply.done():
            reply.cancel()
        if subscribed:
            # Cleanup has its own bounded window even when the outer budget expired.
            async def unsubscribe() -> None:
                async with asyncio.timeout(2):
                    if notify_char is not None:
                        await client.stop_notify(notify_char)

            original = sys.exception()
            try:
                await _shield_cleanup(unsubscribe())
            except Exception:
                if original is None:
                    raise
                _LOGGER.debug(
                    "Unsubscribe failed after an earlier information failure", exc_info=True
                )


async def _shield_cleanup(operation: Coroutine[Any, Any, None]) -> None:
    task = asyncio.create_task(operation)
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
    task.result()
    if interrupted:
        raise asyncio.CancelledError


@dataclass(slots=True)
class _Massage:
    effect: int = 0
    speed: int = 1
    zones: tuple[int, int] = (0, 0)
    saved_zones: tuple[int, int] = (3, 3)
    saved_effect: int = 1
    saved_speed: int = 1
    flags: tuple[bool, bool] = (False, False)
    saved_flags: tuple[bool, bool] = (False, False)
    automatic: int = 8
    individual: int = 10
    zone_states: tuple[int, int] = (8, 8)
    wave: int = 8

    def indicators(self) -> None:
        if all(self.zones):
            if self.effect:
                self.automatic, self.wave, self.individual, self.zone_states = 7, 7, 10, (8, 8)
            else:
                self.individual, self.zone_states = 9, (7, 7)
        if not any(self.zones):
            self.wave, self.zone_states = 8, (8, 8)
        states = list(self.zone_states)
        for index, flag in enumerate(self.flags):
            if flag:
                self.individual, states[index] = 9, 7
        self.zone_states = (states[0], states[1])
        self.wave = 7 if self.effect else 8

    def callback(self, code: int) -> bool:
        """Mutate the distinct saved settings/flags; return whether OFF is written."""
        zones, saved = list(self.zones), list(self.saved_zones)
        flags, saved_flags = list(self.flags), list(self.saved_flags)
        if code in (1, 2, 3, 4):
            index = 0 if code < 3 else 1
            zones[index] = (
                min(5, zones[index] + 1)
                if code in (1, 3)
                else max(1 if self.effect else 0, zones[index] - 1)
            )
        elif code in (5, 6):
            index = code - 5
            if not zones[index]:
                zones[index], flags[index] = saved[index] or 3, True
            else:
                saved[index], saved_flags[index], zones[index], flags[index] = (
                    zones[index],
                    flags[index],
                    0,
                    False,
                )
        elif code == 7:
            self.effect, self.speed = self.saved_effect, self.saved_speed
            zones = saved.copy()
            if not any(zones):
                zones = [3, 3]
        elif code == 8:
            saved, zones = zones.copy(), [0, 0]
            self.saved_effect, self.saved_speed, self.effect, self.speed = (
                self.effect,
                self.speed,
                0,
                1,
            )
        elif code == 9:
            flags = saved_flags.copy()
            for index, flag in enumerate(flags):
                if flag:
                    zones[index] = saved[index] or 3
        elif code == 10:
            saved_flags, flags = flags.copy(), [False, False]
            for index, flag in enumerate(saved_flags):
                if flag:
                    saved[index], zones[index] = zones[index], 0
        self.zones, self.saved_zones = (zones[0], zones[1]), (saved[0], saved[1])
        self.flags, self.saved_flags = (flags[0], flags[1]), (saved_flags[0], saved_flags[1])
        return code in (8, 10)


def _button(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController | SideBoundController) -> None:
        if isinstance(controller, VibradormAppController):
            await controller.execute_app_action(action)
            return
        if isinstance(controller, SideBoundController) and isinstance(
            controller._controller, VibradormAppController
        ):
            await controller.execute_app_action(action)
            return
        raise TypeError("Requires a Vibradorm app profile")

    return invoke


async def _timer_number(controller: BedController, value: float) -> None:
    if isinstance(controller, VibradormAppController):
        await controller.set_pending_floor_timer(value)
        return
    if isinstance(controller, SideBoundController) and isinstance(
        controller._controller, VibradormAppController
    ):
        await controller.set_pending_floor_timer(value)
        return
    raise TypeError("Requires a Vibradorm app profile")


class VibradormAppController(BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app_profile: str,
        control_type: ControlType,
        restored: bool = False,
        floor_light: bool | None = None,
        rgb: bool = False,
        massage: bool = False,
        light_extension: bool = False,
        floor_intent: VibradormAppFloorIntent | None = None,
        timer_intent: VibradormAppTimerIntent | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.profile = validate_vibradorm_app_profile(
            app_profile,
            control_type,
            restored=restored,
            floor_light=floor_light,
            rgb=rgb,
            massage=massage,
            light_extension=light_extension,
        )
        self._toggle = 0
        self._floor_intent = floor_intent or VibradormAppFloorIntent(level=0, default_level=6)
        self._timer_intent = timer_intent or VibradormAppTimerIntent(enabled=False, minutes=0)
        if not isinstance(self._floor_intent, VibradormAppFloorIntent) or not isinstance(
            self._timer_intent, VibradormAppTimerIntent
        ):
            raise ValueError("Local intent must use the typed app session holders")
        _integer(self._floor_intent.level, 0, 8, "Local floor level")
        _integer(self._floor_intent.default_level, 1, 8, "Remembered floor level")
        _integer(self._timer_intent.minutes, 0, 60, "Local pending timer")
        if type(self._timer_intent.enabled) is not bool:
            raise ValueError("Local timer enable must be boolean")
        self._massage = _Massage()
        self._mood_intent: dict[str, str | int] = {}
        self._metadata: VibradormAppMetadata | None = None
        self._metadata_values: VibradormAppMetadataProgress = {}
        self._metadata_progress_pending: VibradormAppMetadataProgress | None = None
        self._subscribed = False
        self._notify_client: BleakClient | None = None
        self._notify_characteristic: BleakGATTCharacteristic | None = None
        self._article_reply: asyncio.Future[str] | None = None
        self._sync_reply: asyncio.Future[bool] | None = None
        self._sync_observed: bool | None = None
        self._info_lock = asyncio.Lock()
        cached = coordinator.entry.data.get("vibradorm_app_metadata")
        if (
            isinstance(cached, Mapping)
            and all(
                isinstance(value, str)
                for field, value in cached.items()
                if field in ("model", "firmware", "software")
            )
            and (
                cached.get("main_firmware_article") is None
                or isinstance(cached.get("main_firmware_article"), str)
            )
        ):
            if "model" in cached:
                self._metadata_values["model"] = cached["model"]
            if "firmware" in cached:
                self._metadata_values["firmware"] = cached["firmware"]
            if "software" in cached:
                self._metadata_values["software"] = cached["software"]
            if isinstance(cached.get("main_firmware_article"), str):
                self._metadata_values["main_firmware_article"] = cached["main_firmware_article"]
            if all(field in cached for field in ("model", "firmware", "software")):
                self._metadata = VibradormAppMetadata(
                    cached["model"],
                    cached["firmware"],
                    cached["software"],
                    cached.get("main_firmware_article"),
                )
            self._publish_metadata()

    @property
    def _floor_level(self) -> int:
        return self._floor_intent.level

    @_floor_level.setter
    def _floor_level(self, value: int) -> None:
        self._floor_intent.level = value

    @property
    def _floor_default(self) -> int:
        return self._floor_intent.default_level

    @_floor_default.setter
    def _floor_default(self, value: int) -> None:
        if value != self._floor_intent.default_level:
            self._floor_intent.default_level = value
            self._coordinator.remember_vibradorm_app_floor_default(value)

    @property
    def _timer_enabled(self) -> bool:
        return self._timer_intent.enabled

    @_timer_enabled.setter
    def _timer_enabled(self, value: bool) -> None:
        self._timer_intent.enabled = value

    @property
    def _timer_minutes(self) -> int:
        return self._timer_intent.minutes

    @_timer_minutes.setter
    def _timer_minutes(self, value: int) -> None:
        self._timer_intent.minutes = value

    @property
    def control_characteristic_uuid(self) -> str:
        return COMMAND if self.profile.basic else CBI

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(axis, axis, *POSITION_AXIS_COMMANDS[axis], scheduler_resource="*")
            for axis in self.profile.groups
        )

    @property
    def supports_position_feedback(self) -> bool:
        return False

    @property
    def requires_notification_channel(self) -> bool:
        return not self.profile.basic

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self.memory_slot_count)

    @property
    def supports_memory_programming(self) -> bool:
        return not self.profile.basic

    @property
    def supports_lights(self) -> bool:
        return self.profile.floor_light

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_level_control(self) -> bool:
        return self.supports_lights

    @property
    def light_level_min(self) -> int:
        return 1

    @property
    def light_level_max(self) -> int:
        return 6 if self.profile.light_extension else 8

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_lights

    @property
    def light_timer_options(self) -> list[str]:
        return (
            ["Off", *(f"{minute} min" for minute in range(1, 61))] if self.supports_lights else []
        )

    @property
    def supports_massage(self) -> bool:
        return self.profile.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            tuple(
                action
                for action in MOTORS
                if action.startswith("all_")
                and self.profile.groups
                or action.rsplit("_", 1)[0] in self.profile.groups
            )
            + tuple(f"memory_{slot}" for slot in range(1, self.memory_slot_count + 1))
            + (("sync",) if self.profile.sync else ())
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        actions = [("refresh_info", "Refresh Device Information")]
        if self.profile.groups:
            actions += [
                ("all_up", "All Up (hold 1 second)"),
                ("all_down", "All Down (hold 1 second)"),
            ]
        if self.profile.sync:
            actions += [("sync", "Sync (hold 1 second)")]
        if self.profile.floor_light:
            actions += [("floor_timer_toggle", "Toggle Pending Floor Timer")]
        if self.profile.rgb:
            actions += [("mood_toggle", "Toggle Mood Light")]
        if self.profile.massage:
            actions += [
                ("massage_automatic", "Automatic Massage"),
                ("massage_individual", "Individual Massage"),
            ]
        return tuple(
            ControllerButtonSpec(
                f"vibradorm_app_{action}",
                name,
                _button(action),
                translation_key=f"vibradorm_app_{action}",
            )
            for action, name in actions
        )

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        specs: list[ControllerSelectSpec] = []
        if self.profile.rgb:
            specs += [
                ControllerSelectSpec(
                    "vibradorm_app_mood_palette",
                    "vibradorm_app_mood_palette",
                    "vibradorm_app_mood_palette",
                    tuple(MOOD_PALETTE),
                    lambda c, v: c.set_mood_palette(v),
                ),
                ControllerSelectSpec(
                    "vibradorm_app_mood_effect",
                    "vibradorm_app_mood_effect",
                    "vibradorm_app_mood_effect",
                    MOOD_EFFECTS,
                    lambda c, v: c.set_mood_effect(v),
                ),
            ]
        if self.profile.massage:
            specs += [
                ControllerSelectSpec(
                    "vibradorm_app_massage_wave",
                    "vibradorm_app_massage_wave",
                    "vibradorm_app_massage_wave",
                    MASSAGE_WAVES,
                    lambda c, v: c.set_massage_wave(v),
                )
            ]
        return tuple(specs)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self.profile.floor_light:
            specs += [
                ControllerNumberSpec(
                    "vibradorm_app_floor_timer_minutes",
                    "vibradorm_app_floor_timer_minutes",
                    "vibradorm_app_floor_timer_minutes",
                    1,
                    60,
                    1,
                    _timer_number,
                    "min",
                )
            ]
        if self.profile.rgb:
            specs += [
                ControllerNumberSpec(
                    "vibradorm_app_mood_speed",
                    "vibradorm_app_mood_speed",
                    "vibradorm_app_mood_speed",
                    0,
                    8,
                    1,
                    lambda c, v: c.set_mood_speed(v),
                )
            ]
        if self.profile.massage:
            specs += [
                ControllerNumberSpec(
                    "vibradorm_app_massage_speed",
                    "vibradorm_app_massage_speed",
                    "vibradorm_app_massage_speed",
                    1,
                    5,
                    1,
                    lambda c, v: c.set_massage_speed(v),
                )
            ]
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = ("model", "firmware", "software") + (
            ("main_firmware_article",) if self.profile.article_requests else ()
        ) + (("sync_observed",) if self.profile.sync else ())
        return tuple(
            ControllerStateSensorSpec(
                f"vibradorm_app_{field}",
                f"vibradorm_app_{field}",
                f"vibradorm_app_{field}",
                "mdi:information-outline",
            )
            for field in fields
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": asdict(self.profile),
            "toggle": self._toggle,
            "metadata": dict(self._metadata_values) or None,
            "sync_observed": self._sync_observed,
            "state_source": "local_intent",
            "floor_intent": self.get_light_state(),
            "pending_timer": {"enabled": self._timer_enabled, "minutes": self._timer_minutes},
            "mood_intent": dict(self._mood_intent),
            "massage_intent": asdict(self._massage) if self.profile.massage else None,
        }

    def _consume_toggle(self) -> int:
        current = self._toggle
        self._toggle ^= 0x8000
        return current

    def _header(self, opcode: int) -> bytes:
        return (opcode | self._consume_toggle()).to_bytes(2, "big")

    async def _write(
        self,
        uuid: str,
        packet: bytes,
        event: asyncio.Event | None = None,
        *,
        advance_at_execution: bool = False,
    ) -> None:
        effective_event = event or self._coordinator.cancel_command
        async with self._ble_lock:
            if effective_event.is_set():
                raise asyncio.CancelledError
            client = self.client
            if client is None or not client.is_connected:
                raise ConnectionError("Not connected")
            char = _characteristic(client, uuid, "write")
            response = "write" in char.properties
            if advance_at_execution:
                self._consume_toggle()  # CmdLightCBI.execute begins after lane admission.
            payload = self._format_command_trace_payload(packet)
            if payload is not None:
                self._coordinator.record_command_trace(
                    payload=payload,
                    characteristic_uuid=uuid,
                    characteristic_handle=char.handle,
                    response=response,
                    repeat_count=1,
                    repeat_delay_ms=100,
                    command_origin="_floor" if advance_at_execution else "_write",
                    controller_class=type(self).__name__,
                )
            await client.write_gatt_char(char, packet, response=response)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        effective_event = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if effective_event.is_set():
                return
            try:
                await self._write(self.control_characteristic_uuid, command, effective_event)
            except asyncio.CancelledError:
                if effective_event.is_set():
                    return
                raise
            if index < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def async_discover_capabilities(self) -> None:
        client = self.client
        if client is None:
            raise ConnectionError("Not connected")
        _characteristic(client, self.control_characteristic_uuid, "write")
        if self.requires_notification_channel:
            _characteristic(client, RESPONSE, "notify")

    def _notification(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        raw = bytes(data)
        self.forward_raw_notification(sender.uuid, raw)
        article = parse_article(raw)
        if (
            article is not None
            and self._article_reply is not None
            and not self._article_reply.done()
        ):
            self._record_metadata_progress({"main_firmware_article": article})
            self._article_reply.set_result(article)
        sync = parse_sync(raw) if self.profile.sync else None
        if sync is not None:
            self._sync_observed = sync
            self.forward_controller_state_update("vibradorm_app_sync_observed", "on" if sync else "off")
            if self._sync_reply is not None and not self._sync_reply.done():
                self._sync_reply.set_result(sync)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self.profile.basic or self._subscribed:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Not connected")
        char = _characteristic(client, RESPONSE, "notify")
        await client.start_notify(char, self._notification)
        self._notify_client = client
        self._notify_characteristic = char
        self._subscribed = True

    async def stop_notify(self) -> None:
        self._notify_callback = None
        self._clear_waiters()
        if self._subscribed:
            self._subscribed = False
            client, char = self._notify_client, self._notify_characteristic
            self._notify_client = None
            self._notify_characteristic = None
            if client is not None and char is not None:
                await client.stop_notify(char)

    def _clear_waiters(self) -> None:
        for waiter in (self._article_reply, self._sync_reply):
            if waiter is not None and not waiter.done():
                waiter.cancel()
        self._article_reply = self._sync_reply = None

    async def refresh_device_info(self) -> None:
        async with self._info_lock:
            client = self.client
            if client is None:
                raise ConnectionError("Not connected")
            await self.start_notify()

            def prepare() -> asyncio.Future[str]:
                self._article_reply = asyncio.get_running_loop().create_future()
                return self._article_reply

            completed: VibradormAppMetadataProgress = {}
            self._metadata_progress_pending = completed
            try:
                async with self._ble_lock:
                    result = await _information_transaction(
                        client,
                        self.profile,
                        asyncio.get_running_loop().time() + 10,
                        self._coordinator.cancel_command,
                        prepare_reply=prepare,
                        metadata_progress=self._record_metadata_progress,
                    )
                self._metadata = result
                self._publish_metadata()
            finally:
                if self._article_reply is not None and not self._article_reply.done():
                    self._article_reply.cancel()
                self._article_reply = None
                self._metadata_progress_pending = None
                if completed:
                    self._coordinator.remember_vibradorm_app_metadata(
                        {
                            field: value
                            for field, value in completed.items()
                            if isinstance(value, str)
                        }
                    )

    def _publish_metadata(self) -> None:
        for field, value in self._metadata_values.items():
            self.forward_controller_state_update(f"vibradorm_app_{field}", value)

    def _record_metadata_progress(self, delta: VibradormAppMetadataProgress) -> None:
        self._metadata_values.update(delta)
        if self._metadata_progress_pending is not None:
            self._metadata_progress_pending.update(delta)
        for field, value in delta.items():
            self.forward_controller_state_update(f"vibradorm_app_{field}", value)

    async def _release(self, count: int = 1) -> None:
        async def cleanup() -> None:
            error: Exception | None = None
            for index in range(count):
                if index:
                    await asyncio.sleep(0.1)
                try:
                    async with asyncio.timeout(2):
                        await self._write(
                            self.control_characteristic_uuid,
                            b"\xff" if self.profile.basic else b"\x00\xff",
                            asyncio.Event(),
                        )
                except Exception as failure:
                    error = error or failure
            if error:
                raise error

        task = asyncio.create_task(cleanup())
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
        task.result()
        if interrupted:
            raise asyncio.CancelledError

    async def _cleanup_preserving_error(self, count: int = 1) -> None:
        original = sys.exception()
        try:
            await self._release(count)
        except Exception:
            if original is None:
                raise
            _LOGGER.debug("Release failed after an earlier operation failure", exc_info=True)

    async def stop_all(self) -> None:
        if self._sync_reply is not None and not self._sync_reply.done():
            self._sync_reply.cancel()
        self._sync_reply = None
        await self._release()

    async def hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError("Control is not reachable in this app profile")
        _integer(duration_ms, 100, 60000, "Hold duration")
        event = self._coordinator.cancel_command
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        try:
            budget = asyncio.timeout_at(deadline)
            try:
                async with budget:
                    if control == "sync":
                        self._sync_reply = asyncio.get_running_loop().create_future()
                        await self._write(CBI, self._header(0x003D) + b"\x3f")

                        async def receive() -> bool:
                            assert self._sync_reply is not None
                            return await self._sync_reply

                        active = await _cancellable(receive(), event)
                        self._sync_reply = None
                        opcode = 0x19 if active else 0x18
                    else:
                        opcode = (
                            MEMORY[int(control[7:]) - 1]
                            if control.startswith("memory_")
                            else MOTORS[control]
                        )
                    toggle = self._consume_toggle()
                    packet = (
                        bytes([opcode])
                        if self.profile.basic
                        else (opcode | toggle).to_bytes(2, "big")
                    )
                    while not event.is_set():
                        await self._write(self.control_characteristic_uuid, packet)
                        await _cancellable(asyncio.sleep(0.1), event)
            except TimeoutError:
                if not budget.expired():
                    raise
        finally:
            self._sync_reply = None
            await self._cleanup_preserving_error()

    async def move_head_up(self) -> None:
        await self.hold_control("head_up", 1000)

    async def move_head_down(self) -> None:
        await self.hold_control("head_down", 1000)

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.hold_control("back_up", 1000)

    async def move_back_down(self) -> None:
        await self.hold_control("back_down", 1000)

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.hold_control("legs_up", 1000)

    async def move_legs_down(self) -> None:
        await self.hold_control("legs_down", 1000)

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.hold_control("feet_up", 1000)

    async def move_feet_down(self) -> None:
        await self.hold_control("feet_down", 1000)

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        raise NotImplementedError("All Down is a held movement, not a flat preset")

    async def preset_memory(self, memory_num: int) -> None:
        _integer(memory_num, 1, self.memory_slot_count, "Memory slot")
        await self.hold_control(f"memory_{memory_num}", 1000)

    async def program_memory(self, memory_num: int) -> None:
        _integer(memory_num, 1, self.memory_slot_count, "Memory slot")
        if not self.supports_memory_programming:
            raise ValueError("Basic profiles have no memory programming route")
        headers = [self._header(0xD) for _ in range(4)]
        self._consume_toggle()  # Source applies the fifth toggle to the wrong receiver.
        try:
            for packet in (*headers, bytes((0, MEMORY[memory_num - 1]))):
                if self._coordinator.cancel_command.is_set():
                    break
                await self._write(CBI, packet)
                await _cancellable(asyncio.sleep(0.1), self._coordinator.cancel_command)
        finally:
            await self._cleanup_preserving_error(4)

    async def execute_app_action(self, action: str) -> None:
        if action in self.held_control_options:
            await self.hold_control(action, 1000)
        elif action == "refresh_info":
            await self.refresh_device_info()
        elif action == "floor_timer_toggle" and self.profile.floor_light:
            self._timer_enabled = not self._timer_enabled
            self._publish_floor()
        elif action == "mood_toggle" and self.profile.rgb:
            await self._write(CBI, self._header(0x1077))
        elif action in ("massage_automatic", "massage_individual") and self.profile.massage:
            await self._massage_mode(action == "massage_automatic")
        else:
            raise ValueError("Action is not reachable in this profile")

    async def set_pending_floor_timer(self, value: float) -> None:
        if not self.profile.floor_light:
            raise ValueError("This profile has no floor-light route")
        self._timer_minutes = _integer(value, 1, 60, "Pending floor timer")
        self._publish_floor()

    async def set_light_timer(self, timer_option: str) -> None:
        if timer_option not in self.light_timer_options:
            raise ValueError("Invalid pending light timer")
        self._timer_enabled = timer_option != "Off"
        if self._timer_enabled:
            self._timer_minutes = int(timer_option.split()[0])
        self._publish_floor()

    @property
    def _effective_timer_option(self) -> str:
        return f"{self._timer_minutes} min" if self._timer_enabled and self._timer_minutes else "Off"

    def _publish_floor(self) -> None:
        self.forward_controller_state_updates(
            {
                "light_level": self._floor_level,
                "light_timer_option": self._effective_timer_option,
                "vibradorm_app_floor_timer_enabled": self._effective_timer_option != "Off",
                "vibradorm_app_floor_timer_minutes": self._timer_minutes,
            }
        )

    def get_light_state(self) -> dict[str, Any]:
        return {
            "is_on": bool(self._floor_level),
            "light_level": self._floor_level,
            "light_timer_option": self._effective_timer_option,
            "light_timer_minutes": self._timer_minutes,
            "state_source": "local_intent",
        }

    async def _floor(self, level: int, *, toggle: bool = False) -> None:
        if not self.profile.floor_light:
            raise ValueError("This profile has no floor-light route")
        if self._coordinator.cancel_command.is_set():
            return
        if toggle:
            self._consume_toggle()
        self._floor_level = level
        raw = level if self.profile.light_extension else level * 32 if level * 32 <= 255 else 200
        timer = self._timer_minutes if self._timer_enabled else 0
        if self.profile.basic and not self.profile.light_extension:
            await self._write(LIGHT, bytes((raw, 0, timer)))
        else:
            packet = self._header(
                0x1011 if not self.profile.basic and self.profile.light_extension else 0x11
            ) + bytes((raw, timer))
            if self._coordinator.cancel_command.is_set():
                return
            await self._write(CBI, packet, advance_at_execution=True)
        self._publish_floor()

    async def set_light_level(self, level: int) -> None:
        level = _integer(level, 1, self.light_level_max, "Floor-light level")
        await self._floor(level)

    async def lights_on(self) -> None:
        # Native ON/OFF resend the requested app branch; they never reverse
        # local intent just because HA repeats an idempotent action.
        await self._floor(self._floor_level or self._floor_default, toggle=True)

    async def lights_off(self) -> None:
        if self._coordinator.cancel_command.is_set():
            return
        if self._floor_level:
            self._floor_default = self._floor_level
        await self._floor(0, toggle=True)

    async def lights_toggle(self) -> None:
        if self._coordinator.cancel_command.is_set():
            return
        if self._floor_level:
            self._floor_default = self._floor_level
            await self._floor(0, toggle=True)
        else:
            await self._floor(self._floor_default or 1, toggle=True)

    async def _mood(self, parameters: bytes, key: str, value: str | int) -> None:
        if not self.profile.rgb:
            raise ValueError("This profile has no mood-light route")
        self._mood_intent[key] = value
        await self._write(CBI, self._header(0x77 if self.profile.basic else 0x1077) + parameters)
        self.forward_controller_state_update(f"vibradorm_app_mood_{key}", value)

    async def set_mood_palette(self, option: str) -> None:
        if option not in MOOD_PALETTE:
            raise ValueError("Choose a shipped mood option")
        await self._mood(b"\x01\x00" + bytes(MOOD_PALETTE[option]), "palette", option)

    async def set_mood_effect(self, option: str) -> None:
        if option not in MOOD_EFFECTS:
            raise ValueError("Choose sunrise, rainbow or disco")
        await self._mood(bytes((8, MOOD_EFFECTS.index(option) + 1)), "effect", option)

    async def set_mood_speed(self, value: float) -> None:
        value = _integer(value, 0, 8, "Mood value")
        await self._mood(bytes((9, 20 - 2 * (value + 1))), "speed", value)

    def _massage_packet(self, off: bool = False) -> bytes:
        m = self._massage
        group = 0 if self.profile.basic else 0x1000
        return self._header(group | (0x34 if off else 0x30)) + (
            b"\x00" if off else bytes((m.effect, m.speed, *m.zones, 0, 0, 0, 0))
        )

    def _plan_massage_callback(self, code: int) -> bytes:
        packet = self._massage_packet(self._massage.callback(code))
        self._massage.indicators()
        return packet

    def get_massage_state(self) -> dict[str, Any]:
        if not self.profile.massage:
            return {}
        m = self._massage
        return {
            "is_on": any(m.zones),
            "head_level": m.zones[0],
            "foot_level": m.zones[1],
            "head_active": m.flags[0],
            "foot_active": m.flags[1],
            "speed": m.speed,
            "wave_mode": m.effect,
            "automatic": m.automatic == 7,
            "individual": m.individual == 9,
            "state_source": "local_intent",
        }

    async def _massage_callback(self, code: int) -> None:
        if not self.profile.massage:
            raise ValueError("This profile has no massage route")
        await self._write(CBI, self._plan_massage_callback(code))
        self._publish_massage()

    async def _send_massage(self) -> None:
        packet = self._massage_packet()
        self._massage.indicators()
        await self._write(CBI, packet)
        self._publish_massage()

    def _publish_massage(self) -> None:
        m = self._massage
        self.forward_controller_state_updates(
            {
                "vibradorm_app_massage_wave": str(m.effect) if m.effect else None,
                "vibradorm_app_massage_speed": m.speed,
                "massage_head_level": m.zones[0],
                "massage_foot_level": m.zones[1],
                "vibradorm_app_massage_automatic": m.automatic == 7,
                "vibradorm_app_massage_individual": m.individual == 9,
            }
        )

    def _plan_massage_mode(self, automatic: bool) -> list[bytes]:
        # Android constructs both nested commands before BLE delivery. Snapshot
        # each packet while preserving its saved settings and local mode intent.
        m = self._massage
        packets: list[bytes] = []
        if automatic:
            if m.individual == 9:
                m.automatic = 8
                packets.extend(self._plan_massage_mode(False))
            code = 7 if m.automatic == 8 else 8
            packets.append(self._plan_massage_callback(code))
            m.automatic = 7 if code == 7 else 8
            if code == 8:
                m.wave = 8
        else:
            if m.automatic == 7:
                m.individual = 10
                packets.extend(self._plan_massage_mode(True))
            code = 9 if m.individual == 10 else 10
            packets.append(self._plan_massage_callback(code))
            m.individual = 9 if code == 9 else 10
            if code == 10:
                m.zone_states = (8, 8)
        m.indicators()
        return packets

    async def _massage_mode(self, automatic: bool) -> None:
        if not self.profile.massage:
            raise ValueError("This profile has no massage route")
        for index, packet in enumerate(self._plan_massage_mode(automatic)):
            if index:
                await _cancellable(asyncio.sleep(0.1), self._coordinator.cancel_command)
            await self._write(CBI, packet)
        self._publish_massage()

    async def _massage_zone(self, index: int, delta: int = 0) -> None:
        m = self._massage
        if not self.profile.massage or (
            m.individual != 9
            if not delta
            else not (
                m.automatic == 7 and m.wave == 7 or m.individual == 9 and m.zone_states[index] == 7
            )
        ):
            raise ValueError("Massage action is disabled in the current app mode")
        if not delta:
            states = list(m.zone_states)
            states[index] = 7 if states[index] == 8 else 8
            m.zone_states = (states[0], states[1])
        await self._massage_callback((5 + index) if not delta else (1 + 2 * index + (delta < 0)))

    async def massage_head_toggle(self) -> None:
        await self._massage_zone(0)

    async def massage_foot_toggle(self) -> None:
        await self._massage_zone(1)

    async def massage_head_up(self) -> None:
        await self._massage_zone(0, 1)

    async def massage_head_down(self) -> None:
        await self._massage_zone(0, -1)

    async def massage_foot_up(self) -> None:
        await self._massage_zone(1, 1)

    async def massage_foot_down(self) -> None:
        await self._massage_zone(1, -1)

    async def set_massage_wave(self, option: str) -> None:
        if not self.profile.massage or option not in MASSAGE_WAVES or self._massage.automatic != 7:
            raise ValueError("Wave requires automatic massage and a shipped option 1..4")
        self._massage.effect = int(option)
        self._massage.zones = (self._massage.zones[0] or 1, self._massage.zones[1] or 1)
        await self._send_massage()
        self._massage.indicators()

    async def set_massage_speed(self, value: float) -> None:
        value = _integer(value, 1, 5, "Massage value")
        if not self.profile.massage:
            raise ValueError("This profile has no massage route")
        self._massage.speed = value
        await self._send_massage()
        self._massage.indicators()


def _integer(value: float, minimum: int, maximum: int, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or int(value) != value
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{label} must be an integer from {minimum} to {maximum}")
    return int(value)
