"""Tempur Relax Control direct BLE contracts over the shared Linak runtime."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

from ...alarm import AlarmCapability, AlarmError, AlarmRequest
from ...card import CARD_HIDDEN
from ...codec.linak import (
    ArtifactParseError,
    build_simultaneous_command,
    configuration_frame,
    configuration_response,
    control_frame,
    massage_selection_frames,
    selected_directions_frame,
    timer_channel_frame,
    timer_event_frame,
    timer_info,
    timer_notification,
)
from ...command_scheduler import (
    CommandContext,
    Delivery,
    current_command_context,
    delivered,
    note_frame_skipped,
)
from ...const import (
    LINAK_CONFIG_CHAR_UUID,
    LINAK_DEVICE_NAME_UUID,
    LINAK_ERROR_CHAR_UUID,
    LINAK_TIMER_CHAR_UUID,
)
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, failed
from ...execution import HOLD_CEILING_MS
from ...profiles.linak import TEMPUR_RELAX, TempurRelaxProfile
from ...state_keys import LINAK_AUTOMATIC_DRIVE
from ..base import CONTROLLER_GESTURE_RELEASE, BedController
from ..entity_specs import (
    POSITION_AXIS_COMMANDS,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .controller import (
    ALARM_ENABLED,
    ALARM_STATUS,
    PROTOCOL_ERROR,
    PROTOCOL_ERROR_CODE,
    PROTOCOL_ERROR_PAYLOAD,
    LinakController,
)
from .protocol import LINAK_ERROR_NAMES, LinakModelVariant, LinakProfile, build_timer_recurrence

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

MASSAGE_SELECTION: Final = StateKey[str | None]("tempur_relax_massage_selection")
SETTINGS_REVISION: Final = StateKey[int]("tempur_relax_settings_revision")


class TempurRelaxController(LinakController):
    """Keep this app's mask, gesture and name semantics separate from Bed Control."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=LinakProfile.TEMPUR_RELAX)
        self._settings: dict[str, Any] = {"memories": {}, "automatic_drive": False, "alarm_enabled": False}
        self._parsed: dict[str, Any] = {}
        self._settings_revision = 0
        self._automatic_favorite: CommandContext | None = None

    @property
    def _app_timing(self) -> TempurRelaxProfile:
        return TEMPUR_RELAX

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    async def async_refresh_auth(self) -> None:
        await self._await_control_ready(expected_client=self.client)

    async def async_discover_capabilities(self) -> None:
        await super().async_discover_capabilities()
        if self._capabilities.discovery_complete and self._coordinator.controller is self:
            self._coordinator.cache_capability_controller()

    def _publish_capability_state(self) -> None:
        if self._capabilities.timer_supported:
            self._settings["alarm_visible"] = True
        super()._publish_capability_state()

    def validate_device_rename(self, name: str) -> None:
        if len(name.encode("utf-16-le")) // 2 > self._app_timing.name_code_units:
            raise ValueError("Use a name of at most 17 UTF-16 code units")

    async def rename_device(self, name: str) -> None:
        self.validate_device_rename(name)
        await self._remember(name=name)
        client = self.client
        # Android runtime default is UTF-8; the artifact calls defaultCharset.
        await self._write_carpe(name.encode("utf-8"), client, characteristic_uuid=LINAK_DEVICE_NAME_UUID)
        if not self._coordinator.cancel_command.is_set():
            readback = await self._read_protocol_characteristic(
                LINAK_DEVICE_NAME_UUID, expected_client=client,
            )
            if readback is None:
                raise failed("tempur_name_readback")
            self._raw_protocol_data[LINAK_DEVICE_NAME_UUID] = bytes(readback).hex()

    @property
    def supports_wake_control(self) -> bool:
        return True

    @property
    def supports_automatic_drive(self) -> bool:
        return self._owns_primary_features

    async def set_automatic_drive(self, enabled: bool) -> None:
        await self._set_tempur_automatic_drive(enabled)

    async def _set_tempur_automatic_drive(self, enabled: bool, *, clear_alarm: bool = True) -> None:
        if not self.supports_automatic_drive:
            raise self.not_supported("automatic drive")
        await self._remember(automatic_drive=enabled)
        client = self.client
        with self.sent_state(
            LINAK_AUTOMATIC_DRIVE(enabled), is_current=lambda: self.client is client
        ):
            await self._write_carpe(
                configuration_frame(0x3B, bytes((enabled,)), write=True, prefix=0x89),
                client,
                characteristic_uuid=LINAK_CONFIG_CHAR_UUID,
            )
        if (clear_alarm and not enabled
                and self._settings.get("alarm_enabled") and self._settings.get("alarm_favorite")):
            await self._remember(alarm_enabled=False)
            await self._clear_timer_packet(client)

    @property
    def has_bed_height_support(self) -> bool:
        return "base" in self._capabilities.position_axes

    @property
    def disconnects_after_rename(self) -> bool:
        return False

    @property
    def simultaneous_movement_axes(self) -> tuple[str, ...]:
        if not self._capabilities.discovery_complete or self._capability_discovery_deferred:
            return ()
        if self._capabilities.model_variant in {LinakModelVariant.STANDARD, LinakModelVariant.TD3}:
            return super().simultaneous_movement_axes
        if self._has_resolved_mask:
            return self._capabilities.position_axes
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        specs = []
        for axis in self.simultaneous_movement_axes:
            if axis == "base":
                open_fn, close_fn, stop_fn = (
                    lambda ctrl: ctrl.move_bed_height_up(),
                    lambda ctrl: ctrl.move_bed_height_down(),
                    lambda ctrl: ctrl.move_bed_height_stop(),
                )
            else:
                open_fn, close_fn, stop_fn = POSITION_AXIS_COMMANDS[axis]

            async def timed_move(
                controller: BedController,
                up: bool,
                duration_ms: int,
                *,
                motor: str = axis,
            ) -> None:
                if not isinstance(controller, TempurRelaxController):
                    raise BedNotConnectedError
                await controller.move_selected_sections(frozenset({motor}), up, duration_ms)

            key = "bed_height" if axis == "base" else axis
            specs.append(
                MotorControlSpec(
                    key=key,
                    translation_key=key,
                    open_fn=open_fn,
                    close_fn=close_fn,
                    stop_fn=stop_fn,
                    timed_move_fn=timed_move,
                )
            )
        return tuple(specs)

    async def move_selected_sections(
        self,
        sections: frozenset[str],
        up: bool,
        duration_ms: int | None = None,
    ) -> None:
        if not sections or sections.difference(self.simultaneous_movement_axes):
            raise self.not_supported("the selected motor sections")
        await self._carpe_move(
            selected_directions_frame(dict.fromkeys(sections, up)),
            duration_ms=duration_ms,
        )

    async def _move_with_stop(self, command: bytes) -> None:
        axis = {
            2: "head",
            3: "head",
            4: "feet",
            5: "feet",
            6: "base",
            7: "base",
            8: "legs",
            9: "legs",
            10: "back",
            11: "back",
        }.get(command[0])
        if axis not in self.simultaneous_movement_axes:
            raise self.not_supported("the selected motor section")
        await super()._move_with_stop(command)

    def _all_sections_command(self, *, up: bool) -> bytes:
        primary = self._primary_controller
        if primary is None:
            raise BedNotConnectedError
        if (
            not primary._capabilities.discovery_complete
            or primary._capability_discovery_deferred
            or primary._capabilities.model_variant is LinakModelVariant.UNKNOWN
            or (
                primary._capabilities.model_variant
                in {
                    LinakModelVariant.ADVANCED,
                    LinakModelVariant.ADVANCED_WITH_ALARM,
                }
                and not primary._has_resolved_mask
            )
        ):
            raise self.not_supported("movement before the bed model is resolved")
        if primary._capabilities.model_variant is LinakModelVariant.TD3:
            return build_simultaneous_command("back", up, "legs", up)
        return control_frame(int(up))

    async def move_simultaneously(
        self,
        first_axis: str,
        first_up: bool,
        second_axis: str,
        second_up: bool,
        duration_ms: int | None = None,
    ) -> None:
        self.validate_simultaneous_directions(first_up, second_up)
        await self.move_selected_sections(
            frozenset({first_axis, second_axis}), first_up, duration_ms
        )

    @property
    def persisted_app_state(self) -> Mapping[str, Any]:
        return dict(self._settings)

    @property
    def persisted_app_state_key(self) -> str:
        return self._app_timing.key

    def restore_persisted_app_state(self, state: Mapping[str, Any]) -> None:
        memories = state.get("memories", {})
        if not isinstance(memories, dict) or any(
            key not in {"1", "2", "3", "4"} or not isinstance(value, str)
            for key, value in memories.items()
        ):
            raise ValueError("Invalid favorite names")
        for key in ("automatic_drive", "alarm_enabled", "alarm_favorite", "alarm_visible"):
            if key in state and not isinstance(state[key], bool):
                raise ValueError("Invalid saved setting")
        if "name" in state and not isinstance(state["name"], str):
            raise ValueError("Invalid saved name")
        self._settings.update(state)
        self._settings["memories"] = dict(memories)

    async def _remember(self, **updates: Any) -> None:
        self._settings = await self._coordinator.async_update_app_state(
            self, lambda saved: {**self._settings, **saved, **updates},
        )
        self._settings_revision += 1
        self.forward_controller_state_updates(SETTINGS_REVISION(self._settings_revision))

    @property
    def memory_slot_names(self) -> tuple[str | None, ...]:
        return tuple(self._settings["memories"].get(str(slot)) for slot in range(1, 5))

    @property
    def supports_memory_naming(self) -> bool:
        return self.memory_slot_count > 0

    async def prepare_device_rename(self, name: str) -> None:
        await self._remember(name=name)

    async def name_memory(self, slot: int, name: str) -> None:
        if not 1 <= slot <= self.memory_slot_count:
            raise ValueError("Choose an available favorite")
        await self._remember(memories={**self._settings["memories"], str(slot): name})

    async def forget_memory(self, slot: int) -> None:
        if not 1 <= slot <= self.memory_slot_count:
            raise ValueError("Choose an available favorite")
        memories = dict(self._settings["memories"])
        memories.pop(str(slot), None)
        clear = (self._settings.get("alarm_enabled") and self._settings.get("alarm_favorite_slot") == slot
                 or self._settings.get("pending_alarm_clear_slot") == slot)
        await self._remember(memories=memories, **(
            {"alarm_enabled": False, "pending_alarm_clear_slot": slot} if clear else {}
        ))
        if clear:
            await self._clear_timer_packet(self.client)

    async def program_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("Choose an available favorite")
        memories = dict(self._settings["memories"])
        memories.setdefault(str(memory_num), f"Favorite {memory_num}")
        # The app commits its local favorite map before the primary write.
        await self._remember(memories=memories)
        await super().program_memory(memory_num)

    def _raw_release_command(self, *, favorite: bool) -> bytes | None:
        from ...profiles.linak import tempur_release_frame

        primary = self._primary_controller
        if primary is None or not primary.controller_entity_discovery_complete:
            raise BedNotConnectedError
        capabilities = primary._capabilities
        return tempur_release_frame(
            alarm=capabilities.timer_supported,
            td3=capabilities.model_variant is LinakModelVariant.TD3,
            favorite=favorite, automatic=bool(self._settings["automatic_drive"]),
        )

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return  # The cancelled gesture owns its exact conditional release.
        packet = self._raw_release_command(favorite=False)
        assert packet is not None
        await self._write_carpe(packet, self.client,
                                cancel_event=asyncio.Event())

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return not CONTROLLER_GESTURE_RELEASE.get()

    async def _send_stop(self) -> None:
        await self.stop_all()

    def on_gesture_release(self) -> bool | None:
        context = self._automatic_favorite
        if context is not None and context.active and not context.cancel_event.is_set():
            return False
        return None

    async def _carpe_move(
        self, command: bytes, *, duration_ms: int | None = None, favorite: bool = False,
    ) -> None:
        primary = self._primary_controller
        automatic = (favorite and primary is not None
                     and primary._capabilities.model_variant is not LinakModelVariant.TD3
                     and self._settings["automatic_drive"])
        context = current_command_context()
        if automatic and context is not None:
            self._automatic_favorite = context
            context.bounded_after_lease = True
            duration_ms = HOLD_CEILING_MS
        try:
            await super()._carpe_move(command, duration_ms=duration_ms, favorite=favorite)
        finally:
            if self._automatic_favorite is context:
                self._automatic_favorite = None

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return ("flat", "all_up", *(f"memory_{slot}" for slot in range(1, self.memory_slot_count + 1)))

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {"preset_flat": "flat", "preset_both_up": "all_up", **{
            f"preset_memory_{slot}": f"memory_{slot}" for slot in range(1, self.memory_slot_count + 1)
        }}.get(key)
        return ControllerHoldSpec(control, release_button_key="release_held_control") if control else None

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (ControllerButtonSpec(
            "tempur_release", "Release held control", lambda controller: controller.stop_all(),
            translation_key="release_held_control", release_only=True, card=CARD_HIDDEN,
        ),)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options or not 0 < duration_ms <= HOLD_CEILING_MS:
            raise ValueError("Choose an available control and a hold of at most 30 seconds")

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_hold_control(f"memory_{slot}", hold_ms)
        await self._carpe_move(control_frame(self._app_timing.memory_opcodes[slot - 1]),
                               duration_ms=hold_ms, favorite=True)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        if control.startswith("memory_"):
            await self.recall_memory(int(control[-1]), hold_ms=duration_ms)
        else:
            await self._carpe_move(self._all_sections_command(up=control == "all_up"), duration_ms=duration_ms)

    @property
    def _primary_controller(self) -> TempurRelaxController | None:
        from ...paired_coordinator import PairedBedCoordinator
        from ...runtime_data import loaded_runtime

        runtime = loaded_runtime(self._coordinator.hass, self._coordinator.entry.entry_id)
        if isinstance(runtime, PairedBedCoordinator):
            primary = runtime.children.get("left")
            controller = primary.capability_controller if primary is not None else None
            if isinstance(controller, TempurRelaxController):
                return controller
            if primary is None or controller is None:
                return None
        return self

    @property
    def _owns_primary_features(self) -> bool:
        primary = self._primary_controller
        return primary is not None and primary._coordinator is self._coordinator

    @property
    def memory_slot_count(self) -> int:
        return self._capabilities.memory_slots if self._owns_primary_features else 0

    @property
    def supports_massage(self) -> bool:
        return self._owns_primary_features and self._coordinator.has_massage

    @property
    def supports_alarm(self) -> bool:
        return self._owns_primary_features and self._capabilities.timer_supported

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self.supports_alarm and not (
            self._owns_primary_features and self._settings.get("alarm_enabled")
        ):
            return None
        return AlarmCapability(
            wake_actions=("none", "memory_1", "memory_2", "memory_3", "memory_4"),
            weekdays=True, massage=self._coordinator.has_massage, live_check=True,
            confirm_actions=frozenset() if self._settings["automatic_drive"] else frozenset(
                f"memory_{slot}" for slot in range(1, 5)
            ),
        )

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        await self._await_control_ready(expected_client=self.client)
        if alarm.enabled and not self.supports_alarm:
            raise self.not_supported("hardware alarms")
        if not alarm.enabled:
            characteristic = self.client.services.get_characteristic(LINAK_TIMER_CHAR_UUID) if self.client else None
            if characteristic is None or not set(characteristic.properties).intersection({"write", "write-without-response"}):
                raise self.not_supported("clearing hardware alarms")
        self.validate_alarm(alarm)

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        if alarm.enabled and alarm.weekdays != tuple(range(7)):
            raise AlarmError("tempur_alarm_daily", "This app programs a daily alarm. Select every day")
        if alarm.enabled and alarm.wake_action == "none" and not alarm.massage:
            raise AlarmError("alarm_needs_effect", "Choose a favorite or massage for the alarm")

    async def _clear_timer_packet(self, client: BleakClient | None) -> None:
        cleared = False

        def show(delivery: Delivery) -> None:
            nonlocal cleared
            cleared = delivery is Delivery.SENT

        with self.sent_state(ALARM_ENABLED(False)), delivered(show):
            await self._write_carpe(timer_channel_frame(clear=True), client, characteristic_uuid=LINAK_TIMER_CHAR_UUID)
        if cleared and self._settings.get("pending_alarm_clear_slot") is not None:
            await self._remember(pending_alarm_clear_slot=None)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        await self.check_alarm(alarm)
        client = self.client
        if not alarm.enabled:
            await self._set_tempur_automatic_drive(False, clear_alarm=False)
            await self._remember(alarm_enabled=False)
            await self._clear_timer_packet(client)
            return
        if alarm.wake_action != "none" and not self._settings["automatic_drive"]:
            await self.set_automatic_drive(True)
        actions = []
        lifetime, pause = self._app_timing.alarm_action_lifetime, self._app_timing.alarm_action_pause
        if alarm.wake_action != "none":
            slot = int(alarm.wake_action.removeprefix("memory_"))
            actions.append((self._app_timing.memory_opcodes[slot - 1], lifetime, pause))
        if alarm.massage:
            actions.append((self._app_timing.alarm_massage_opcode, lifetime, pause))
        # Preserve the artifact's earlier-today signed duration, not tomorrow.
        now = alarm.reference_time
        target = now.replace(hour=alarm.hour, minute=alarm.minute, second=0, microsecond=0)
        seconds = math.floor((target - now).total_seconds())
        packets = (timer_event_frame(seconds, tuple(actions)), build_timer_recurrence(
            self._app_timing.alarm_recurrence_count, self._app_timing.alarm_recurrence_minutes
        ), timer_channel_frame())
        await self._remember(alarm_enabled=True, alarm_visible=True, pending_alarm_clear_slot=None,
                             alarm_hour=alarm.hour, alarm_minute=alarm.minute,
                             alarm_favorite=alarm.wake_action != "none",
                             alarm_favorite_slot=int(alarm.wake_action[-1]) if alarm.wake_action != "none" else None)
        with self.sent_state(ALARM_ENABLED(True)):
            for index, packet in enumerate(packets):
                try:
                    await self._write_carpe(packet, client, characteristic_uuid=LINAK_TIMER_CHAR_UUID)
                except BaseException:
                    for _ in packets[index + 1:]:
                        note_frame_skipped()
                    raise

    def _handle_config_data(self, data: bytes) -> None:
        try:
            self._parsed["configuration"] = configuration_response(data).hex()
        except ArtifactParseError as error:
            self._parsed["configuration_error"] = error.kind

    def _handle_timer_data(self, data: bytes | bytearray) -> None:
        try:
            event = timer_notification(bytes(data))
            if event["kind"] == "GET_TIMER1":
                event["info"] = timer_info(bytes(data))
        except ArtifactParseError as error:
            self._parsed["timer_error"] = error.kind
            return
        self._parsed["timer"] = event
        # Query contents are diagnostic observations, not app ACKs or alarm state.
        status = {"ELAPSED": "elapsed", "INTERRUPTED": "interrupted", "ACT_DONE": "action_done"}.get(str(event["kind"]))
        if status is not None:
            self.forward_controller_state_updates(ALARM_STATUS(status))

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        advanced = self._capabilities.model_variant in {
            LinakModelVariant.ADVANCED, LinakModelVariant.ADVANCED_WITH_ALARM,
        }
        return tuple(spec for spec in super().controller_state_sensor_specs
                     if advanced or spec.key != "linak_protocol_error")

    def _handle_error_data(self, data: bytes | bytearray) -> None:
        self._raw_protocol_data[LINAK_ERROR_CHAR_UUID] = bytes(data).hex()
        code = int.from_bytes(data[2:3], signed=True) if len(data) >= 3 else 0
        if len(data) >= 3 and (int.from_bytes(data[:2], "little", signed=True) != 1
                              or not 0 <= code <= len(LINAK_ERROR_NAMES)):
            self._parsed["control_error"] = "IllegalStateException"
            return
        self.forward_controller_state_updates(
            PROTOCOL_ERROR(LINAK_ERROR_NAMES[code - 1] if code else "none"),
            PROTOCOL_ERROR_CODE(code), PROTOCOL_ERROR_PAYLOAD(bytes(data[2:]).hex() if code else ""),
        )

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        if command and (0x80 <= command[0] <= 0x91 or command[0] in {0xA8, 0xA9}) and not self.supports_massage:
            raise self.not_supported("massage")
        await super().write_command(command, repeat_count, repeat_delay_ms, cancel_event)

    async def _select_massage(self, selection: str) -> None:
        if not self.supports_massage:
            raise self.not_supported("massage")
        client = self.client
        current = self._coordinator.controller_state.get(MASSAGE_SELECTION)
        if selection == current:
            selection = "off"
        sections = {
            "back": frozenset({"back"}),
            "legs": frozenset({"legs"}),
            "both": frozenset({"back", "legs"}),
            "off": frozenset(),
        }[selection]
        with self.sent_state(MASSAGE_SELECTION(selection)):
            frames = massage_selection_frames(sections)
            for index, frame in enumerate(frames):
                if index:
                    try:
                        await asyncio.sleep(self._app_timing.massage_zone_gap_s)
                    except asyncio.CancelledError:
                        note_frame_skipped()
                        raise
                try:
                    await self._write_carpe(frame, client)
                except asyncio.CancelledError:
                    if index < len(frames) - 1:
                        note_frame_skipped()
                    raise

    async def massage_toggle(self) -> None:
        await self._select_massage("both")

    async def massage_head_toggle(self) -> None:
        await self._select_massage("back")

    async def massage_foot_toggle(self) -> None:
        await self._select_massage("legs")

    async def massage_off(self) -> None:
        if not self.supports_massage:
            raise self.not_supported("massage")
        client = self.client
        with self.sent_state(MASSAGE_SELECTION("off")):
            await self._write_carpe(control_frame(0x80), client)

    @property
    def supports_reset_defaults(self) -> bool:
        return self._owns_primary_features

    async def reset_defaults(self) -> None:
        if not self.supports_reset_defaults:
            raise self.not_supported("resetting defaults")
        await self._remember(memories={}, automatic_drive=False, alarm_enabled=False)
        if self._settings.get("alarm_visible") or self.supports_alarm:
            await self._clear_timer_packet(self.client)
        with self.sent_state(MASSAGE_SELECTION(None)):
            await super().reset_defaults()

    @property
    def protocol_diagnostics(self) -> dict[str, Any]:
        return {**super().protocol_diagnostics, "scope": "full_static", "parsed": dict(self._parsed)}
