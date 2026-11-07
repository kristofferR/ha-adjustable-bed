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
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Literal, TypedDict

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from ..card import CARD_LIGHT_MOOD, CARD_MASSAGE, CARD_UTILITY, CardPlacement, CardRole, CardSection
from ..codec import vibradorm as codec
from ..const import (
    CONF_HAS_MASSAGE,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VIBRADORM_CONTROL_TYPE,
    CONF_VIBRADORM_FLOOR_DEFAULT,
    CONF_VIBRADORM_FLOOR_LIGHT,
    CONF_VIBRADORM_LIGHT_EXTENSION,
    CONF_VIBRADORM_RESTORED,
    CONF_VIBRADORM_RGB,
    CONF_VIBRADORM_VMAT_REMOTE,
)
from ..controller_state import StateKey, StateUpdate
from ..execution import ExecutionCapabilities
from ..profiles.vibradorm import (
    ARTICLE_REQUEST,
    EXTENSION,
    FLOOR,
    MASSAGE,
    MASSAGE_OFF,
    MASSAGE_WAVES,
    MEMORY,
    MOOD,
    MOOD_EFFECTS,
    MOOD_PALETTE,
    MOTORS,
    STORE,
    SYNC_ACTIVE,
    SYNC_INACTIVE,
    SYNC_REQUEST,
    VMAT_METADATA_FIELDS,
    VMAT_MOOD_PALETTE,
    ControlType,
    VibradormAppProfile,
    get_vmat_remote,
    validate_vibradorm_app_profile,
    vibradorm_app_metadata_key,
)
from ..state_keys import LIGHT_LEVEL, LIGHT_TIMER_OPTION
from ..vibradorm_app_state import (
    VibradormAppFloorIntent,
    VibradormAppMassageIntent,
    VibradormAppTimerIntent,
)
from .base import (
    POSITION_AXIS_COMMANDS,
    BedController,
    ControllerButtonSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorCommandCallable,
    MotorControlSpec,
    PositionNumberSpec,
)
from .builder import BuildContext

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

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
_RELEASES: Final = (codec.motor(codec.STOP), codec.command(codec.STOP))


@dataclass(frozen=True, slots=True)
class VibradormAppMetadata:
    model: str
    firmware: str
    software: str
    main_firmware_article: str | None = None


MOOD_PALETTE_OPTION: Final = StateKey[str | None]("vibradorm_app_mood_palette")
MOOD_EFFECT_OPTION: Final = StateKey[str | None]("vibradorm_app_mood_effect")
MOOD_SPEED: Final = StateKey[int | None]("vibradorm_app_mood_speed")
FLOOR_TIMER_ENABLED: Final = StateKey[bool]("vibradorm_app_floor_timer_enabled")
FLOOR_TIMER_MINUTES: Final = StateKey[int | None]("vibradorm_app_floor_timer_minutes")
MASSAGE_WAVE: Final = StateKey[str | None]("vibradorm_app_massage_wave")
MASSAGE_SPEED: Final = StateKey[int | None]("vibradorm_app_massage_speed")
MASSAGE_HEAD_LEVEL: Final = StateKey[int]("massage_head_level")
MASSAGE_FOOT_LEVEL: Final = StateKey[int]("massage_foot_level")
MASSAGE_AUTOMATIC: Final = StateKey[bool]("vibradorm_app_massage_automatic")
MASSAGE_INDIVIDUAL: Final = StateKey[bool]("vibradorm_app_massage_individual")


def _mood_update(key: str, value: str | int) -> StateUpdate:
    """Mood intent: the speed slider's number, or a palette or effect option."""
    if key == "speed":
        return MOOD_SPEED(value if isinstance(value, int) else None)
    option = MOOD_PALETTE_OPTION if key == "palette" else MOOD_EFFECT_OPTION
    return option(value if isinstance(value, str) else None)


class VibradormAppMetadataProgress(TypedDict, total=False):
    """Completed fields only; empty strings are successful read results."""

    model: str
    firmware: str
    software: str
    main_firmware_article: str
    xmc_status: str
    opmode: str
    device_name: str
    revision_id: str
    revision_string: str
    variant: str


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


def validate_profile_roles(client: BleakClient, profile: VibradormAppProfile) -> None:
    """Validate the same selected GATT roles during setup and runtime."""
    if profile.app_profile == "vmat":
        from ..vibradorm_vmat_setup import validate_vmat_roles

        validate_vmat_roles(client, basic=profile.basic)
        return
    write = codec.MOTOR_CHAR_UUID if profile.basic else codec.CBI_CHAR_UUID
    _characteristic(client, write, "write")
    if not profile.basic:
        _characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")


def _write_response(client: BleakClient, uuid: str) -> bool:
    # Android inherits the runtime mode. This preference is the host policy.
    return "write" in _characteristic(client, uuid, "write").properties


def decode_standard_info(data: bytes | bytearray | None) -> str:
    if data is None:
        return ""
    return codec.decode_text(bytes(data)).strip("".join(map(chr, range(33))))


def parse_article(data: bytes) -> str | None:
    return codec.decode_text(data[3:]) if len(data) > 4 and data[:3] == b"\x21\xa0\xc8" else None


def parse_sync(data: bytes) -> bool | None:
    reply = codec.status_reply(data) if len(data) >= 3 else None
    return None if reply is None else bool(reply[0] & 0x40)


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
        if profile.app_profile == "vmat":
            from ..vibradorm_vmat_setup import async_read_vmat_dis

            return await async_read_vmat_dis(client, cancel_event, metadata_progress)
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
                        _characteristic(client, codec.CBI_CHAR_UUID, "write"),
                        ARTICLE_REQUEST,
                        response=_write_response(client, codec.CBI_CHAR_UUID),
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
    remote: str | None = None,
) -> VibradormAppMetadata:
    """Read app information before native pairing; the caller owns native proof."""
    if app_profile == "vmat":
        from ..vibradorm_vmat_setup import async_prepare_vmat_pairing

        selected = get_vmat_remote(remote)
        if isinstance(control_type, bool) or control_type != selected.control_type:
            raise ValueError("VMAT control type must match the selected remote")
        return await async_prepare_vmat_pairing(
            client, basic=selected.control_type == 2, deadline=deadline,
            cancel_event=cancel_event, metadata_progress=metadata_progress,
        )
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
                notify_char = _characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")
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


def _button(action: str) -> MotorCommandCallable:
    async def invoke(controller: BedController) -> None:
        if isinstance(controller, VibradormAppController):
            await controller.execute_app_action(action)
            return
        raise TypeError("Requires a Vibradorm app profile")

    return invoke


async def _timer_number(controller: BedController, value: float) -> None:
    if isinstance(controller, VibradormAppController):
        await controller.set_pending_floor_timer(value)
        return
    raise TypeError("Requires a Vibradorm app profile")


_BUTTON_CARDS: Final = {
    "floor_timer_toggle": CardPlacement(CardSection.LIGHTING, CardRole.TIMER_TOGGLE),
    "mood_toggle": CardPlacement(CardSection.LIGHTING, CardRole.MOOD_TOGGLE),
    "massage_automatic": CARD_MASSAGE,
    "massage_individual": CARD_MASSAGE,
}


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
        remote: str | None = None,
        massage_intent: VibradormAppMassageIntent | None = None,
        mood_intent: dict[str, str | int] | None = None,
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
            remote=remote,
        )
        self._toggle = 0
        self._next_write_at = 0.0
        self._floor_intent = floor_intent or VibradormAppFloorIntent(
            level=0, default_level=8 if app_profile == "vmat" and not light_extension else 6,
        )
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
        self._massage = massage_intent or VibradormAppMassageIntent()
        self._committed_massage = replace(self._massage)
        self._mood_intent: dict[str, str | int] = mood_intent if mood_intent is not None else {}
        self._metadata: VibradormAppMetadata | None = None
        self._metadata_values: VibradormAppMetadataProgress = {}
        self._metadata_progress_pending: VibradormAppMetadataProgress | None = None
        self._subscribed = False
        self._notify_client: BleakClient | None = None
        self._notify_characteristic: BleakGATTCharacteristic | None = None
        self._notify_generation = 0
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
        if self.profile.app_profile == "vmat":
            from typing import cast

            if isinstance(cached, Mapping):
                self._metadata_values.update(cast(VibradormAppMetadataProgress, {
                    field: cached[field] for field in VMAT_METADATA_FIELDS
                    if isinstance(cached.get(field), str)
                }))
                self._publish_metadata()
            self._publish_floor()
            if self.profile.massage:
                self._publish_massage()
            self.forward_controller_state_updates(
                *(_mood_update(key, value) for key, value in self._mood_intent.items())
            )

    @property
    def execution(self) -> ExecutionCapabilities:
        """The apps refresh held motion every 100 ms, then send STOP (#483)."""
        return ExecutionCapabilities(hold="stream")

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
        return codec.MOTOR_CHAR_UUID if self.profile.basic else codec.CBI_CHAR_UUID

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(axis, axis, *POSITION_AXIS_COMMANDS[axis], scheduler_resource="*")
            for axis in self.profile.groups
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if self.profile.app_profile == "vmat":
            return ()
        return super().position_number_specs

    @property
    def requires_notification_channel(self) -> bool:
        return self.profile.app_profile == "vmat" or not self.profile.basic

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
    def prunes_stale_light_level(self) -> bool:
        return True

    @property
    def light_switch_follows_level_intent(self) -> bool:
        return True

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
        return 6 if self.profile.light_extension and self.profile.app_profile != "vmat" else 8

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
                card=_BUTTON_CARDS.get(action, CARD_UTILITY),
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
                    MOOD_PALETTE_OPTION,
                    tuple(self.mood_palette),
                    lambda c, v: c.set_mood_palette(v),
                    card=CARD_LIGHT_MOOD,
                ),
                ControllerSelectSpec(
                    "vibradorm_app_mood_effect",
                    "vibradorm_app_mood_effect",
                    MOOD_EFFECT_OPTION,
                    MOOD_EFFECTS,
                    lambda c, v: c.set_mood_effect(v),
                    card=CARD_LIGHT_MOOD,
                ),
            ]
        if self.profile.massage:
            specs += [
                ControllerSelectSpec(
                    "vibradorm_app_massage_wave",
                    "vibradorm_app_massage_wave",
                    MASSAGE_WAVE,
                    MASSAGE_WAVES,
                    lambda c, v: c.set_massage_wave(v),
                    card=CARD_MASSAGE,
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
                    FLOOR_TIMER_MINUTES,
                    1,
                    60,
                    1,
                    _timer_number,
                    "min",
                    card=CardPlacement(CardSection.LIGHTING, CardRole.PENDING_TIMER_MINUTES),
                )
            ]
        if self.profile.rgb:
            specs += [
                ControllerNumberSpec(
                    "vibradorm_app_mood_speed",
                    "vibradorm_app_mood_speed",
                    MOOD_SPEED,
                    0,
                    8,
                    1,
                    lambda c, v: c.set_mood_speed(v),
                    card=CARD_LIGHT_MOOD,
                )
            ]
        if self.profile.massage:
            specs += [
                ControllerNumberSpec(
                    "vibradorm_app_massage_speed",
                    "vibradorm_app_massage_speed",
                    MASSAGE_SPEED,
                    1,
                    5,
                    1,
                    lambda c, v: c.set_massage_speed(v),
                    card=CARD_MASSAGE,
                )
            ]
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        fields = ("model", "firmware", "software") + (
            ("main_firmware_article",)
            if self.profile.article_requests or self.profile.app_profile == "vmat"
            else ()
        ) + (("sync_observed",) if self.profile.sync else ())
        if self.profile.app_profile == "vmat":
            fields += VMAT_METADATA_FIELDS
        return tuple(
            ControllerStateSensorSpec(
                f"vibradorm_app_{field}",
                f"vibradorm_app_{field}",
                vibradorm_app_metadata_key(field),
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
        self._toggle ^= codec.TOGGLE
        return current

    def _header(self, word: int, parameters: bytes = b"") -> bytes:
        return codec.command(word, parameters, self._consume_toggle())

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
            if self.profile.app_profile == "vmat" and packet not in _RELEASES:
                delay = self._next_write_at - asyncio.get_running_loop().time()
                if delay > 0:
                    await _cancellable(asyncio.sleep(delay), effective_event)
            client = self.client
            if client is None or not client.is_connected:
                raise ConnectionError("Not connected")
            if self.profile.app_profile == "vmat":
                from ..vibradorm_vmat_setup import vmat_characteristic

                response = uuid != codec.CBI_CHAR_UUID
                char = vmat_characteristic(client, uuid, "write" if response else "write-without-response")
            else:
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
            if self.profile.app_profile == "vmat":
                self._next_write_at = asyncio.get_running_loop().time() + 0.1

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
        validate_profile_roles(client, self.profile)

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
            self.forward_controller_state_update(
                vibradorm_app_metadata_key("sync_observed"), "on" if sync else "off"
            )
            if self._sync_reply is not None and not self._sync_reply.done():
                self._sync_reply.set_result(sync)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        if self.profile.app_profile == "vmat" and self._subscribed and self.client is not self._notify_client:
            await self.stop_notify()
        if not self.requires_notification_channel or self._subscribed:
            return
        client = self.client
        if client is None:
            raise ConnectionError("Not connected")
        if self.profile.app_profile == "vmat":
            from ..vibradorm_vmat_setup import vmat_characteristic

            await _cancellable(asyncio.sleep(0.5), self._coordinator.cancel_command)
            char = vmat_characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")
            self._notify_generation += 1
            generation = self._notify_generation

            def notification(sender: BleakGATTCharacteristic, data: bytearray) -> None:
                if (
                    generation == self._notify_generation and self._subscribed
                    and self.client is client and client.is_connected
                    and self._notify_client is client and self._notify_characteristic is char
                    and sender.uuid.lower() == char.uuid.lower() and sender.handle == char.handle
                ):
                    self._notification(sender, data)

            await client.start_notify(char, notification)
            if generation != self._notify_generation or self.client is not client:
                await client.stop_notify(char)
                return
        else:
            char = _characteristic(client, codec.RESPONSE_CHAR_UUID, "notify")
            await client.start_notify(char, self._notification)
        self._notify_client = client
        self._notify_characteristic = char
        self._subscribed = True

    async def stop_notify(self) -> None:
        self._notify_generation += 1
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
            self.forward_controller_state_update(
                vibradorm_app_metadata_key(field), value if isinstance(value, str) else None
            )

    def _record_metadata_progress(self, delta: VibradormAppMetadataProgress) -> None:
        self._metadata_values.update(delta)
        if self._metadata_progress_pending is not None:
            self._metadata_progress_pending.update(delta)
        for field, value in delta.items():
            self.forward_controller_state_update(
                vibradorm_app_metadata_key(field), value if isinstance(value, str) else None
            )

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
                            codec.motor(codec.STOP)
                            if self.profile.basic
                            else codec.command(codec.STOP),
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
                        await self._write(codec.CBI_CHAR_UUID, self._header(*SYNC_REQUEST))

                        async def receive() -> bool:
                            assert self._sync_reply is not None
                            return await self._sync_reply

                        active = await _cancellable(receive(), event)
                        self._sync_reply = None
                        opcode = SYNC_ACTIVE if active else SYNC_INACTIVE
                    else:
                        opcode = (
                            MEMORY[int(control[7:]) - 1]
                            if control.startswith("memory_")
                            else MOTORS[control]
                        )
                    toggle = self._consume_toggle()
                    packet = (
                        codec.motor(opcode)
                        if self.profile.basic
                        else codec.command(opcode, toggle=toggle)
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
        await self.hold_control("head_up", self.leased_hold_ms(1000))

    async def move_head_down(self) -> None:
        await self.hold_control("head_down", self.leased_hold_ms(1000))

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_back_up(self) -> None:
        await self.hold_control("back_up", self.leased_hold_ms(1000))

    async def move_back_down(self) -> None:
        await self.hold_control("back_down", self.leased_hold_ms(1000))

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.hold_control("legs_up", self.leased_hold_ms(1000))

    async def move_legs_down(self) -> None:
        await self.hold_control("legs_down", self.leased_hold_ms(1000))

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.hold_control("feet_up", self.leased_hold_ms(1000))

    async def move_feet_down(self) -> None:
        await self.hold_control("feet_down", self.leased_hold_ms(1000))

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
        headers = [self._header(STORE) for _ in range(4)]
        self._consume_toggle()  # Source applies the fifth toggle to the wrong receiver.
        try:
            for packet in (*headers, codec.command(MEMORY[memory_num - 1])):
                if self._coordinator.cancel_command.is_set():
                    break
                await self._write(codec.CBI_CHAR_UUID, packet)
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
            await self._write(codec.CBI_CHAR_UUID, self._header(MOOD | EXTENSION))
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
            LIGHT_LEVEL(self._floor_level),
            LIGHT_TIMER_OPTION(self._effective_timer_option),
            FLOOR_TIMER_ENABLED(self._effective_timer_option != "Off"),
            FLOOR_TIMER_MINUTES(self._timer_minutes),
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
        if self.profile.app_profile != "vmat":
            self._floor_level = level
        raw = level if self.profile.light_extension else level * 32 if level * 32 <= 255 else (
            250 if self.profile.app_profile == "vmat" else 200
        )
        timer = self._timer_minutes if self._timer_enabled else 0
        if self.profile.basic and not self.profile.light_extension:
            await self._write(codec.LIGHT_CHAR_UUID, codec.light(raw, timer))
        else:
            extended = not self.profile.basic and self.profile.light_extension
            packet = self._header(FLOOR | EXTENSION if extended else FLOOR, bytes((raw, timer)))
            if self._coordinator.cancel_command.is_set():
                return
            await self._write(codec.CBI_CHAR_UUID, packet, advance_at_execution=True)
        if self.profile.app_profile == "vmat":
            self._floor_level = level
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
        previous = self._floor_level
        if previous and self.profile.app_profile != "vmat":
            self._floor_default = previous
        await self._floor(0, toggle=True)
        if previous and self.profile.app_profile == "vmat" and not self._coordinator.cancel_command.is_set():
            self._floor_default = previous

    async def lights_toggle(self) -> None:
        if self._coordinator.cancel_command.is_set():
            return
        if self._floor_level:
            previous = self._floor_level
            if self.profile.app_profile != "vmat":
                self._floor_default = previous
            await self._floor(0, toggle=True)
            if self.profile.app_profile == "vmat" and not self._coordinator.cancel_command.is_set():
                self._floor_default = previous
        else:
            await self._floor(self._floor_default or 1, toggle=True)

    async def _mood(self, parameters: bytes, key: str, value: str | int) -> None:
        if not self.profile.rgb:
            raise ValueError("This profile has no mood-light route")
        if self.profile.app_profile != "vmat":
            self._mood_intent[key] = value
        word = MOOD if self.profile.basic else MOOD | EXTENSION
        await self._write(codec.CBI_CHAR_UUID, self._header(word, parameters))
        self._mood_intent[key] = value
        self.forward_controller_state_updates(_mood_update(key, value))

    @property
    def mood_palette(self) -> dict[str, tuple[int, int, int]]:
        return VMAT_MOOD_PALETTE if self.profile.app_profile == "vmat" else MOOD_PALETTE

    async def set_mood_palette(self, option: str) -> None:
        if option not in self.mood_palette:
            raise ValueError("Choose a shipped mood option")
        await self._mood(b"\x01\x00" + bytes(self.mood_palette[option]), "palette", option)

    async def set_mood_effect(self, option: str) -> None:
        if option not in MOOD_EFFECTS:
            raise ValueError("Choose sunrise, rainbow or disco")
        await self._mood(bytes((8, MOOD_EFFECTS.index(option) + 1)), "effect", option)

    async def set_mood_speed(self, value: float) -> None:
        value = _integer(value, 0, 8, "Mood value")
        await self._mood(bytes((9, 20 - 2 * (value + 1))), "speed", value)

    def _massage_packet(self, off: bool = False) -> bytes:
        m = self._massage
        group = 0 if self.profile.basic else EXTENSION
        return self._header(
            group | (MASSAGE_OFF if off else MASSAGE),
            b"\x00" if off else bytes((m.effect, m.speed, *m.zones, 0, 0, 0, 0)),
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
        await self._write_massage_packets([self._plan_massage_callback(code)])

    async def _send_massage(self) -> None:
        packet = self._massage_packet()
        self._massage.indicators()
        await self._write_massage_packets([packet])

    async def _write_massage_packets(self, packets: list[bytes]) -> None:
        try:
            for index, packet in enumerate(packets):
                if index:
                    await _cancellable(asyncio.sleep(0.1), self._coordinator.cancel_command)
                await self._write(codec.CBI_CHAR_UUID, packet)
        except BaseException:
            if self.profile.app_profile == "vmat":
                # Preserve the shared reconnect holder, including saved flags.
                for field, value in asdict(self._committed_massage).items():
                    setattr(self._massage, field, value)
            raise
        self._publish_massage()

    def _publish_massage(self) -> None:
        m = self._massage
        self._committed_massage = replace(m)
        self.forward_controller_state_updates(
            MASSAGE_WAVE(str(m.effect) if m.effect else None),
            MASSAGE_SPEED(m.speed),
            MASSAGE_HEAD_LEVEL(m.zones[0]),
            MASSAGE_FOOT_LEVEL(m.zones[1]),
            MASSAGE_AUTOMATIC(m.automatic == 7),
            MASSAGE_INDIVIDUAL(m.individual == 9),
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
        await self._write_massage_packets(self._plan_massage_mode(automatic))

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


async def build_controller(ctx: BuildContext) -> VibradormAppController:
    """Build the controller for the stored app profile and session intent."""
    from ..vibradorm_app_state import get_vibradorm_app_session_intent

    coordinator = ctx.coordinator
    data = ctx.data
    stored_control = data[CONF_VIBRADORM_CONTROL_TYPE]
    control_type: int | Literal["other"]
    if stored_control == "other":
        control_type = "other"
    elif isinstance(stored_control, int) and not isinstance(stored_control, bool):
        control_type = stored_control
    elif isinstance(stored_control, str):
        control_type = int(stored_control)
    else:
        raise ValueError("Invalid retained Vibradorm control type")
    app_profile = data[CONF_VIBRADORM_APP_PROFILE]
    vmat = app_profile == "vmat"
    restored = data.get(CONF_VIBRADORM_RESTORED, False)
    light_extension = data.get(CONF_VIBRADORM_LIGHT_EXTENSION)
    missing_default = 6 if (not restored and not vmat) or light_extension else 8
    intent = get_vibradorm_app_session_intent(
        coordinator.hass,
        coordinator.address,
        app_profile=app_profile,
        control_type=control_type,
        remembered_floor_default=data.get(CONF_VIBRADORM_FLOOR_DEFAULT, missing_default),
        remote=data.get(CONF_VIBRADORM_VMAT_REMOTE),
    )
    return VibradormAppController(
        coordinator,
        app_profile=app_profile,
        control_type=control_type,
        restored=restored,
        floor_light=data.get(CONF_VIBRADORM_FLOOR_LIGHT),
        rgb=data.get(CONF_VIBRADORM_RGB, False),
        massage=data.get(CONF_HAS_MASSAGE, False),
        light_extension=data.get(CONF_VIBRADORM_LIGHT_EXTENSION, False),
        floor_intent=intent.floor,
        timer_intent=intent.timer,
        remote=data.get(CONF_VIBRADORM_VMAT_REMOTE),
        massage_intent=intent.massage if vmat else None,
        mood_intent=intent.mood if vmat else None,
    )
