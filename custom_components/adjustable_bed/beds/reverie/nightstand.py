"""Reverie Nightstand bed controller implementation (Protocol 110).

Verified from ReverieBLEProtocolV1.java and PositionController.java.

Reverie Nightstand uses direct writes to specific characteristics:
- Linear motor control: write 0x01 (up), 0x02 (down), 0x00 (stop)
- Position control: write position value directly (0-100)
- Presets: write to PRESETS characteristic
- LED: write to LED characteristic (0x64 on, 0x00 off)
- Massage: write level * 4 (0-40) to HEAD_WAVE/FOOT_WAVE characteristics
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final

from bleak.exc import BleakError

from ...card import CARD_MASSAGE, motor_card
from ...const import (
    REVERIE_NIGHTSTAND_FOOT_POSITION_UUID,
    REVERIE_NIGHTSTAND_FOOT_WAVE_UUID,
    REVERIE_NIGHTSTAND_HEAD_POSITION_UUID,
    REVERIE_NIGHTSTAND_HEAD_WAVE_UUID,
    REVERIE_NIGHTSTAND_LED_UUID,
    REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
    REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
    REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
    REVERIE_NIGHTSTAND_LUMBAR_UUID,
    REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID,
    REVERIE_NIGHTSTAND_PRESETS_UUID,
    REVERIE_NIGHTSTAND_RGB_UUID,
    REVERIE_STK_SIDE_DATA_UUID,
    REVERIE_STK_SIDE_NO_DATA_UUID,
)
from ...controller_state import StateKey, StateUpdate
from ...state_keys import (
    LIGHT_LEVEL,
    UNDER_BED_LIGHTS_ON,
    UNDER_BED_LIGHTS_RGB,
    massage_intensity,
)
from ..base import BedController
from ..builder import BuildContext
from ..entity_specs import (
    POSITION_UNIT_PERCENT,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .comfort import (
    ReverieComfortActions,
    ReverieComfortRequest,
    RoutineSteps,
    build_p1_composer_payload,
    build_stk_composer_payload,
    validate_comfort_request,
)
from .profiles import (
    REVERIE_MODEL_FALLBACK,
    ReverieModelProfile,
    resolve_reverie_model,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

STK_SIDE_DATA_UUID = REVERIE_STK_SIDE_DATA_UUID
STK_SIDE_NO_DATA_UUID = REVERIE_STK_SIDE_NO_DATA_UUID


STK_SIDE: Final = StateKey[str | None]("reverie_stk_side")
MASSAGE_HEAD_INTENSITY: Final = massage_intensity("head")
MASSAGE_FOOT_INTENSITY: Final = massage_intensity("foot")
# The full wave byte; the generic wave slider shows the same value.
MASSAGE_WAVE: Final = massage_intensity("wave")
STK_HEAD_WAVE: Final = StateKey[int | None]("reverie_stk_head_wave")
STK_GLOBAL_MASSAGE: Final = StateKey[int | None]("reverie_stk_global_massage")
BODY_TILT: Final = StateKey[float | None]("reverie_body_tilt")
STK_HEAD_POSITION: Final = StateKey[int]("reverie_stk_head_position")
STK_HEAD2_POSITION: Final = StateKey[int]("reverie_stk_head2_position")


def _position_key(axis: str) -> StateKey[float | None]:
    return StateKey[float | None](f"reverie_{axis}_position")


class ReverieNightstandCommands:
    """Reverie Nightstand command constants."""

    # Linear motor control values
    MOTOR_UP: int = 0x01
    MOTOR_DOWN: int = 0x02
    MOTOR_STOP: int = 0x00

    # LED control values
    LED_ON: int = 64
    LED_OFF: int = 0x00

    # Preset mode values (write to PRESETS characteristic)
    # Mode 1 = Zero-G, Mode 2 = Anti-Snore, Mode 3 = Flat
    # Source: ReverieBLEProtocolV2.presetsMode in APK
    MODE_ZERO_G: int = 0x01
    MODE_ANTI_SNORE: int = 0x02
    MODE_FLAT: int = 0x03

    @staticmethod
    def memory_preset(memory_num: int) -> int:
        """Get command value for memory preset (1-4).

        Memory 1 = 0x04, Memory 2 = 0x05, etc.
        """
        return memory_num + 3

    @staticmethod
    def store_memory(memory_num: int) -> int:
        """Get command value to store current position to memory (1-4).

        The source adds decimal 83 before converting the resulting number to a
        byte, so slots 1-4 map to 0x54-0x57.
        """
        return memory_num + 83


class ReverieNightstandController(BedController, ReverieComfortActions):
    """Controller for Reverie Nightstand beds (Protocol 110).

    This protocol uses direct writes to specific characteristics rather than
    a single command characteristic with checksums.
    """

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, model: str | None = None
    ) -> None:
        """Initialize the controller with its selected app model profile."""
        super().__init__(coordinator)
        self.model_id = model or REVERIE_MODEL_FALLBACK
        self.model: ReverieModelProfile = resolve_reverie_model(self.model_id)
        if model in (None, "", "auto"):
            # Keep pre-profile Protocol 110 entries' working lumbar control.
            # Explicit app-model selections continue to use the accepted model
            # capability table, including its "Other" row.
            self.model = replace(self.model, lumbar=True)
        self._notify_callback: Callable[[str, float], None] | None = None
        self._massage_head_level = 0
        self._massage_foot_level = 0
        self._massage_wave_level = 0
        self.forward_controller_state_updates(
            MASSAGE_HEAD_INTENSITY(0), MASSAGE_FOOT_INTENSITY(0), MASSAGE_WAVE(0)
        )
        self._light_brightness: int | None = None
        self._last_nonzero_light_brightness: int | None = None
        self._light_rgb: tuple[int, int, int] | None = None
        retained_side = coordinator.controller_state.get(STK_SIDE, "1")
        self._stk_selected_side = retained_side if retained_side in ("1", "2", "3") else "1"
        self._stk_head_positions: dict[str, int] = {}
        # Release retains its target even when the initial GATT write fails.
        self._active_stk_motion_side: int | None = None
        self._diagnostic_timer: asyncio.TimerHandle | None = None
        self._diagnostic_connection_release: Callable[[], None] | None = None
        self._routine_timer: asyncio.TimerHandle | None = None
        self._routine_steps: list[tuple[ReverieComfortRequest, int]] = []
        self._routine_generation = 0
        self._routine_connection_release: Callable[[], None] | None = None
        self._active_notify_characteristics: list[str] = []
        if self.model.tandem:
            self.forward_controller_state_update(STK_SIDE, self._stk_selected_side)
        _LOGGER.debug("ReverieNightstandController initialized")

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the primary control characteristic UUID.

        Note: This controller writes to multiple characteristics, but this
        returns the linear head UUID as the primary one.
        """
        return REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.model.presets

    @property
    def supports_preset_flat(self) -> bool:
        return self.model.presets

    @property
    def supports_memory_presets(self) -> bool:
        """Return True - Reverie Nightstand supports memory presets (slots 1-4)."""
        return self.model.memory_positions

    @property
    def memory_slot_count(self) -> int:
        """Return 4 - Reverie Nightstand supports memory slots 1-4."""
        return 4 if self.model.memory_positions else 0

    @property
    def supports_memory_programming(self) -> bool:
        """Return True - Reverie Nightstand supports programming memory positions."""
        return self.model.memory_positions

    @property
    def supports_lights(self) -> bool:
        return self.model.nightlight

    @property
    def supports_under_bed_lights(self) -> bool:
        return self.model.nightlight

    @property
    def supports_discrete_light_control(self) -> bool:
        """Return True - Reverie Nightstand supports discrete on/off light control."""
        return self.model.nightlight

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.model.nightlight

    @property
    def supports_light_level_control(self) -> bool:
        return self.model.nightlight

    @property
    def light_level_min(self) -> int:
        return 0

    @property
    def light_level_max(self) -> int:
        return 100

    @property
    def supports_light_color_control(self) -> bool:
        return self.model.nightlight

    @property
    def supported_color_mode(self) -> str | None:
        return "rgb" if self.model.nightlight else None

    @property
    def has_lumbar_support(self) -> bool:
        """Return True - Reverie Nightstand has lumbar motor control."""
        return self.model.lumbar

    @property
    def supports_direct_position_control(self) -> bool:
        return self.model.positions

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.model.massage

    @property
    def supports_massage(self) -> bool:
        return self.model.massage

    @property
    def supports_massage_off_control(self) -> bool:
        return self.model.massage

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.model.massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.model.massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.model.massage

    @property
    def massage_intensity_zones(self) -> list[str]:
        # Keep the established generic wave number key for existing entries.
        # The source-backed Reverie-specific number below exposes the full
        # characteristic byte; the shared slider retains its legacy UI shape.
        return ["head", "foot", "wave"] if self.model.massage else []

    @property
    def legacy_massage_wave_available(self) -> bool:
        """Keep the old global wave entity usable only on its source side."""
        return not self.model.tandem or self._stk_selected_side == "1"

    @property
    def massage_intensity_max(self) -> int:
        return 10

    @property
    def supports_motor_control(self) -> bool:
        return self.model.positions

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if not self.model.positions:
            return ()
        specs = [
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                position_key="back",
                max_angle=100,
                hold=ControllerMotorHoldSpec("back_up", "back_down"),
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                position_key="legs",
                max_angle=100,
                hold=ControllerMotorHoldSpec("legs_up", "legs_down"),
            ),
        ]
        if self.model.lumbar:
            specs.append(
                MotorControlSpec(
                    key="lumbar",
                    translation_key="lumbar",
                    open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                    close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                    stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
                    position_key="lumbar",
                    max_angle=100,
                    hold=ControllerMotorHoldSpec("lumbar_up", "lumbar_down"),
                )
            )
        return tuple(specs)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        if not self.model.positions:
            return ()
        controls = ["back_up", "back_down", "legs_up", "legs_down"]
        if self.model.lumbar:
            controls.extend(("lumbar_up", "lumbar_down"))
        return tuple(controls)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if not self.model.massage:
            return ()
        return (
            ControllerStateSensorSpec(
                key="reverie_head_massage_intensity",
                translation_key="reverie_head_massage_intensity",
                state_key=MASSAGE_HEAD_INTENSITY,
                icon="mdi:vibrate",
                card=CARD_MASSAGE,
            ),
            ControllerStateSensorSpec(
                key="reverie_foot_massage_intensity",
                translation_key="reverie_foot_massage_intensity",
                state_key=MASSAGE_FOOT_INTENSITY,
                icon="mdi:vibrate",
                card=CARD_MASSAGE,
            ),
            ControllerStateSensorSpec(
                key="reverie_massage_wave",
                translation_key="reverie_massage_wave",
                state_key=MASSAGE_WAVE,
                icon="mdi:vibrate",
                card=CARD_MASSAGE,
            ),
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        if not self.model.positions:
            return ()
        specs = [
            build_position_number_spec(
                "back", max_value=100, unit=POSITION_UNIT_PERCENT
            ),
            build_position_number_spec(
                "legs", max_value=100, unit=POSITION_UNIT_PERCENT
            ),
        ]
        if self.model.lumbar:
            specs.append(
                build_position_number_spec(
                    "lumbar", max_value=100, unit=POSITION_UNIT_PERCENT
                )
            )
        return tuple(specs)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self.model.tandem:
            return ()
        return (
            ControllerSelectSpec(
                key="reverie_stk_side",
                translation_key="reverie_stk_side",
                state_key=STK_SIDE,
                options=("1", "2", "3"),
                select_fn=lambda _ctrl, side: self._select_stk_side(side),
                local_select_fn=self._set_stk_side,
            ),
        )

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        specs: list[ControllerNumberSpec] = []
        if self.model.massage:
            specs.append(
                ControllerNumberSpec(
                    key="reverie_massage_wave",
                    translation_key="reverie_massage_wave",
                    state_key=MASSAGE_WAVE,
                    native_min_value=0,
                    native_max_value=255,
                    native_step=1,
                    set_fn=lambda ctrl, value: ctrl.set_massage_intensity(
                        "wave", int(value)
                    ),
                    card=CARD_MASSAGE,
                )
            )
            if self.model.tandem:
                specs.extend(
                    (
                        ControllerNumberSpec(
                            key="reverie_stk_head_wave",
                            translation_key="reverie_stk_head_wave",
                            state_key=STK_HEAD_WAVE,
                            native_min_value=0,
                            native_max_value=10,
                            native_step=1,
                            set_fn=lambda ctrl, value: ctrl.set_massage_intensity(
                                "stk_head_wave", int(value)
                            ),
                            card=CARD_MASSAGE,
                        ),
                        ControllerNumberSpec(
                            key="reverie_stk_global_massage",
                            translation_key="reverie_stk_global_massage",
                            state_key=STK_GLOBAL_MASSAGE,
                            native_min_value=0,
                            native_max_value=191,
                            native_step=1,
                            set_fn=lambda ctrl, value: ctrl.set_massage_intensity(
                                "stk_global", int(value)
                            ),
                            card=CARD_MASSAGE,
                        ),
                    )
                )
        if self.model.body_tilt:
            specs.append(
                ControllerNumberSpec(
                    key="reverie_body_tilt",
                    translation_key="reverie_body_tilt",
                    state_key=BODY_TILT,
                    native_min_value=-100,
                    native_max_value=100,
                    native_step=1,
                    set_fn=lambda ctrl, value: ctrl.set_motor_position(
                        "lumbar", int(value)
                    ),
                    card=motor_card("lumbar"),
                )
            )
        return tuple(specs)

    async def _write_to_char(
        self,
        char_uuid: str,
        value: int,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a single byte value to a specific characteristic."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command
        command = bytes([value])

        _LOGGER.debug(
            "Writing 0x%02X to %s (repeat: %d, delay: %dms, response=True)",
            value,
            char_uuid,
            repeat_count,
            repeat_delay_ms,
        )
        self._record_command_trace(
            char_uuid,
            command,
            response=True,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
        )

        for i in range(repeat_count):
            if effective_cancel is not None and effective_cancel.is_set():
                _LOGGER.info("Command cancelled after %d/%d writes", i, repeat_count)
                return

            async with self._ble_lock:
                try:
                    if effective_cancel is not None and effective_cancel.is_set():
                        return
                    await self.client.write_gatt_char(char_uuid, command, response=True)
                except BleakError:
                    _LOGGER.exception("Failed to write to %s", char_uuid)
                    raise

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _write_bytes_to_char(
        self,
        char_uuid: str,
        value: bytes,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write one exact app payload to a specific characteristic."""
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")
        effective_cancel = cancel_event or self._coordinator.cancel_command
        if effective_cancel is not None and effective_cancel.is_set():
            return
        self._record_command_trace(char_uuid, value, response=True)
        async with self._ble_lock:
            if effective_cancel is not None and effective_cancel.is_set():
                return
            try:
                await self.client.write_gatt_char(char_uuid, value, response=True)
            except BleakError:
                _LOGGER.exception("Failed to write to %s", char_uuid)
                raise

    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Start listening for position notifications."""
        self._notify_callback = callback

        if not self.model.positions:
            return

        if self.client is None or not self.client.is_connected:
            return

        if self._active_notify_characteristics:
            return

        # The app subscribes to position and head/foot massage state.
        started: list[str] = []
        try:

            def head_handler(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Reverie Nightstand head position: %s", data.hex())
                self.forward_raw_notification(
                    REVERIE_NIGHTSTAND_HEAD_POSITION_UUID, bytes(data)
                )
                if len(data) >= 1:
                    self._handle_position("back", data[0])

            def foot_handler(_: Any, data: bytearray) -> None:
                _LOGGER.debug("Reverie Nightstand foot position: %s", data.hex())
                self.forward_raw_notification(
                    REVERIE_NIGHTSTAND_FOOT_POSITION_UUID, bytes(data)
                )
                if len(data) >= 1:
                    self._handle_position("legs", data[0])

            def lumbar_handler(_: Any, data: bytearray) -> None:
                self.forward_raw_notification(
                    REVERIE_NIGHTSTAND_LUMBAR_UUID, bytes(data)
                )
                if data:
                    self._handle_position("lumbar", data[0])

            def head_wave_handler(_: Any, data: bytearray) -> None:
                if data:
                    self._massage_head_level = data[0] // 4
                    self.forward_controller_state_update(
                        MASSAGE_HEAD_INTENSITY, self._massage_head_level
                    )

            def foot_wave_handler(_: Any, data: bytearray) -> None:
                if data:
                    self._massage_foot_level = data[0] // 4
                    self.forward_controller_state_update(
                        MASSAGE_FOOT_INTENSITY, self._massage_foot_level
                    )

            await self.client.start_notify(
                REVERIE_NIGHTSTAND_HEAD_POSITION_UUID, head_handler
            )
            started.append(REVERIE_NIGHTSTAND_HEAD_POSITION_UUID)
            await self.client.start_notify(
                REVERIE_NIGHTSTAND_FOOT_POSITION_UUID, foot_handler
            )
            started.append(REVERIE_NIGHTSTAND_FOOT_POSITION_UUID)
            if self.model.lumbar or self.model.body_tilt or self.model.tandem:
                await self.client.start_notify(
                    REVERIE_NIGHTSTAND_LUMBAR_UUID, lumbar_handler
                )
                started.append(REVERIE_NIGHTSTAND_LUMBAR_UUID)
            if self.model.massage:
                await self.client.start_notify(
                    REVERIE_NIGHTSTAND_HEAD_WAVE_UUID, head_wave_handler
                )
                started.append(REVERIE_NIGHTSTAND_HEAD_WAVE_UUID)
                await self.client.start_notify(
                    REVERIE_NIGHTSTAND_FOOT_WAVE_UUID, foot_wave_handler
                )
                started.append(REVERIE_NIGHTSTAND_FOOT_WAVE_UUID)
            self._active_notify_characteristics = started.copy()
            _LOGGER.debug("Started Reverie Nightstand position notifications")
        except BaseException as subscribe_error:
            failures: list[BaseException] = [subscribe_error]
            for char_uuid in reversed(started):
                try:
                    await self.client.stop_notify(char_uuid)
                except BaseException as cleanup_error:
                    failures.append(cleanup_error)
                    _LOGGER.exception(
                        "Could not roll back Reverie notification %s", char_uuid
                    )
            self._active_notify_characteristics.clear()
            self._notify_callback = None
            if len(failures) > 1:
                raise BaseExceptionGroup(
                    "Reverie notification setup and rollback failed", failures
                ) from subscribe_error
            raise

    async def stop_notify(self) -> None:
        """Stop listening for position notifications."""
        if self.client is None or not self.client.is_connected:
            self._cancel_protocol_timers()
            self._active_notify_characteristics.clear()
            self._notify_callback = None
            return

        failures: list[Exception] = []
        for char_uuid in reversed(self._active_notify_characteristics):
            try:
                await self.client.stop_notify(char_uuid)
            except Exception as err:
                failures.append(err)
                _LOGGER.warning("Could not stop Reverie notification %s: %s", char_uuid, err)
        self._cancel_protocol_timers()
        self._active_notify_characteristics.clear()
        self._notify_callback = None
        if failures:
            raise ExceptionGroup("Reverie notification cleanup failed", failures)

    def _cancel_routine(self) -> None:
        self._routine_generation += 1
        if self._routine_timer is not None:
            self._routine_timer.cancel()
            self._routine_timer = None
        self._routine_steps.clear()
        self._release_routine_connection()

    def _hold_routine_connection(self) -> None:
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._routine_connection_release = release

    def _release_routine_connection(self) -> None:
        release = self._routine_connection_release
        self._routine_connection_release = None
        if release is not None:
            release()

    def _cancel_protocol_timers(self) -> None:
        self._cancel_routine()
        self._cancel_diagnostic()

    def on_disconnect(self) -> None:
        self._cancel_protocol_timers()
        self._active_stk_motion_side = None
        self._stk_head_positions.clear()
        super().on_disconnect()

    def validate_comfort_request(self, request: ReverieComfortRequest) -> None:
        if not self.model.comfort_settings:
            raise ValueError(f"Model {self.model_id} has no comfort settings")
        self._validate_composer_values(request)

    def _validate_composer_values(self, request: ReverieComfortRequest) -> None:
        if request.force:
            raise ValueError("Composer comfort does not define forced writes")
        validate_comfort_request(
            request,
            supported_fields=frozenset(
                {
                    "head_position",
                    "foot_position",
                    "lumbar_position",
                    "head_massage",
                    "foot_massage",
                }
            ),
        )
        fields = (
            request.head_position,
            request.foot_position,
            request.lumbar_position,
            request.head_massage,
            request.foot_massage,
        )
        if any(value is None for value in fields):
            raise ValueError("Protocol 110 comfort requires all five Composer values")
        if not self.model.massage and (
            request.head_massage != 0 or request.foot_massage != 0
        ):
            raise ValueError(f"Model {self.model_id} does not support massage")

    async def async_set_comfort(self, request: ReverieComfortRequest) -> None:
        """Send the V1 Composer frame, or preserve the STK V2 no-op route."""
        self.validate_comfort_request(request)
        if self.model.tandem:
            return
        await self._apply_composer_values(request)

    async def _apply_composer_values(self, request: ReverieComfortRequest) -> None:
        if request.lumbar_position is not None and request.lumbar_position < 0 and not self.model.body_tilt:
            return
        payload = build_p1_composer_payload(request, body_tilt=self.model.body_tilt)
        if payload is None:
            return
        await self._write_bytes_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, payload)

    def validate_routine(
        self, steps: RoutineSteps
    ) -> None:
        if not self.model.routines:
            raise ValueError(f"Model {self.model_id} has no Composer routines")
        for request, duration_minutes in steps:
            if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
                raise ValueError("Routine step duration must be an integer number of minutes")
            if request is None:
                break
            self._validate_composer_values(request)
            if self.model.tandem and self._stk_selected_side in ("1", "2"):
                state = self._coordinator.controller_state
                key = STK_HEAD2_POSITION if self._stk_selected_side == "1" else STK_HEAD_POSITION
                current = state.get(key)
                if (
                    isinstance(current, bool)
                    or not isinstance(current, int)
                    or not 0 <= current <= 255
                ):
                    raise ValueError(
                        f"STK side {self._stk_selected_side} routine needs current axis feedback"
                    )

    async def _write_routine_comfort(self, request: ReverieComfortRequest) -> None:
        if request.lumbar_position is not None and request.lumbar_position < 0 and not self.model.body_tilt:
            return
        if not self.model.tandem:
            await self._apply_composer_values(request)
            return
        state = self._coordinator.controller_state
        selected_side = int(self._stk_selected_side)
        current_head = state.get(STK_HEAD_POSITION)
        current_head2 = state.get(STK_HEAD2_POSITION)
        payload = build_stk_composer_payload(
            request,
            side=selected_side,
            current_head=(
                current_head
                if isinstance(current_head, int) and not isinstance(current_head, bool)
                else None
            ),
            current_head2=(
                current_head2
                if isinstance(current_head2, int) and not isinstance(current_head2, bool)
                else None
            ),
        )
        await self._write_bytes_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, payload)

    async def async_start_routine(
        self, steps: RoutineSteps
    ) -> None:
        """Replace this physical address's Composer queue and start its first step."""
        self.validate_routine(steps)
        if self.client is None or not self.client.is_connected:
            return
        self._cancel_routine()
        stopped_on_missing = False
        for request, duration in steps:
            if request is None:
                stopped_on_missing = True
                break
            if duration is None:  # validate_routine already rejects this
                raise ValueError("Routine step duration must be an integer number of minutes")
            self._routine_steps.append((request, duration))
        if stopped_on_missing or not self._routine_steps:
            return
        self._hold_routine_connection()
        await self._run_routine_step(self._routine_generation)

    async def _run_routine_step(self, generation: int) -> None:
        if generation != self._routine_generation:
            return
        if not self._routine_steps:
            self._routine_timer = None
            self._release_routine_connection()
            return
        request, duration_minutes = self._routine_steps.pop(0)
        assert request is not None
        self._routine_timer = self._coordinator.hass.loop.call_later(
            duration_minutes * 60,
            self._enqueue_routine_step,
            generation,
        )
        try:
            await self._write_routine_comfort(request)
        except BaseException:
            self._cancel_routine()
            raise

    def _enqueue_routine_step(self, generation: int) -> None:
        self._routine_timer = None

        async def execute(controller: BedController) -> None:
            if controller is self and generation == self._routine_generation:
                await self._run_routine_step(generation)

        self._coordinator.hass.async_create_task(
            self._coordinator.async_execute_controller_command(
                execute,
                cancel_running=False,
                resource="reverie:routine",
                read_positions_after_operation=False,
            ),
            "adjustable_bed.reverie_routine_step",
        )

    async def async_start_diagnostic(self) -> None:
        """Run the P1 scan-screen LED and massage test for ten seconds."""
        self.validate_diagnostic()
        self._cancel_diagnostic()
        context = self._coordinator.hold_command_connection()
        context.__enter__()

        def release() -> None:
            context.__exit__(None, None, None)

        self._diagnostic_connection_release = release
        self._diagnostic_timer = self._coordinator.hass.loop.call_later(
            10, self._enqueue_diagnostic_stop, release
        )
        failures: list[Exception] = []
        for char_uuid, value in (
            (REVERIE_NIGHTSTAND_LED_UUID, 0x64),
            (REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID, 0x01),
        ):
            try:
                await self._write_to_char(char_uuid, value)
            except Exception as err:
                failures.append(err)
                _LOGGER.exception("Reverie Protocol 110 diagnostic start write failed")
        if failures:
            raise ExceptionGroup("Reverie diagnostic start writes failed", failures)

    def validate_diagnostic(self) -> None:
        if not self.model.nightlight or not self.model.massage:
            raise ValueError("Protocol 110 diagnostic test requires lights and massage")

    def _cancel_diagnostic(self) -> None:
        if self._diagnostic_timer is not None:
            self._diagnostic_timer.cancel()
            self._diagnostic_timer = None
        release = self._diagnostic_connection_release
        self._diagnostic_connection_release = None
        if release is not None:
            release()

    def _enqueue_diagnostic_stop(self, release: Callable[[], None]) -> None:
        if release is not self._diagnostic_connection_release:
            return
        self._diagnostic_timer = None
        self._coordinator.hass.async_create_task(
            self._stop_diagnostic(release), "adjustable_bed.reverie_diagnostic_stop"
        )

    async def _stop_diagnostic(self, release: Callable[[], None] | None = None) -> None:
        if release is None:
            release = self._diagnostic_connection_release
        failures: list[Exception] = []
        async def write_stops(controller: BedController) -> None:
            if controller is not self or release is not self._diagnostic_connection_release:
                return
            for char_uuid, value in (
                (REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID, 0x00),
                (REVERIE_NIGHTSTAND_LED_UUID, 0x00),
            ):
                try:
                    await self._write_to_char(
                        char_uuid, value, cancel_event=asyncio.Event()
                    )
                except Exception as err:
                    failures.append(err)
                    _LOGGER.exception(
                        "Reverie Protocol 110 diagnostic stop write failed"
                    )

        try:
            await self._coordinator.async_execute_controller_command(
                write_stops,
                cancel_running=False,
                resource="reverie:diagnostic",
                read_positions_after_operation=False,
            )
        finally:
            if release is self._diagnostic_connection_release:
                self._cancel_diagnostic()
        if failures:
            raise ExceptionGroup("Reverie diagnostic stop writes failed", failures)

    async def read_positions(self, motor_count: int = 2) -> None:
        """Read current position data."""
        if not self.model.positions or self.client is None or not self.client.is_connected:
            return

        # Read each supported axis independently so a failed read does not hide
        # later responses. Preserve every GATT failure for the caller.
        async with self._ble_lock:
            axes = [
                ("back", REVERIE_NIGHTSTAND_HEAD_POSITION_UUID),
                ("legs", REVERIE_NIGHTSTAND_FOOT_POSITION_UUID),
            ]
            if self.model.lumbar or self.model.body_tilt or self.model.tandem:
                axes.append(("lumbar", REVERIE_NIGHTSTAND_LUMBAR_UUID))
            failures: list[Exception] = []
            for axis, char_uuid in axes:
                try:
                    data = await self.client.read_gatt_char(char_uuid)
                except Exception as err:
                    failures.append(err)
                    continue
                if data:
                    self._handle_position(axis, data[0])
            if failures:
                raise ExceptionGroup("Reverie position reads failed", failures)

    async def _move_linear(
        self,
        char_uuid: str,
        direction: int,
    ) -> None:
        """Send the app's one write on press; callers release this same axis."""
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no motor controls")
        if char_uuid == REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID and not self.model.lumbar:
            raise ValueError(f"Model {self.model_id} has no lumbar actuator")
        await self._write_to_char(char_uuid, direction)

    @staticmethod
    def _body_tilt_to_wire(position: int) -> int:
        if position < 0:
            return int((position + 100) * 36 / 100)
        return int(position * 64 / 100 + 36)

    @staticmethod
    def _body_tilt_from_wire(position: int) -> float:
        if position < 36:
            return position * 100 / 36 - 100
        return (position - 36) * 100 / 64

    def _handle_position(self, axis: str, raw_position: int) -> None:
        value: float = float(raw_position)
        if self.model.tandem and axis == "back":
            self._stk_head_positions["1"] = raw_position
            self.forward_controller_state_update(STK_HEAD_POSITION, raw_position)
            self._publish_stk_head_position()
            return
        elif self.model.tandem and axis == "lumbar":
            # The accepted Protocol 110 profile names this characteristic
            # lumbar/head2. Preserve its raw byte without deriving it from legs.
            self._stk_head_positions["2"] = raw_position
            self.forward_controller_state_update(STK_HEAD2_POSITION, raw_position)
        if axis == "lumbar" and self.model.body_tilt:
            value = self._body_tilt_from_wire(raw_position)
            self.forward_controller_state_update(BODY_TILT, value)
        self.forward_controller_state_update(_position_key(axis), value)
        if self._notify_callback is not None:
            self._notify_callback(axis, value)
        if self.model.tandem and axis == "lumbar":
            self._publish_stk_head_position()

    def _publish_stk_head_position(self) -> None:
        """Expose the selected head, or unknown when Both heads do not agree."""
        sides = ("1", "2") if self._stk_selected_side == "3" else (self._stk_selected_side,)
        values = tuple(self._stk_head_positions.get(side) for side in sides)
        value = values[0]
        if value is None or any(other != value for other in values):
            self.forward_controller_state_update(_position_key("back"), None)
            self._coordinator.clear_position_feedback(("back",))
            return
        self.forward_controller_state_update(_position_key("back"), float(value))
        if self._notify_callback is not None:
            self._notify_callback("back", float(value))

    def angle_to_native_position(self, motor: str, angle: float) -> int:
        """Return the P1 raw percentage for direct position writes."""
        if motor in ("head", "back"):
            return max(0, min(100, int(round(angle))))
        if motor in ("feet", "legs"):
            return max(0, min(100, int(round(angle))))
        if motor == "lumbar" and self.model.body_tilt:
            return max(-100, min(100, int(round(angle))))
        return max(0, min(100, int(round(angle))))

    async def set_motor_position(self, motor: str, position: int) -> None:
        """Write one P1 or STK absolute-position command."""
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no position controls")
        axis = {
            "head": "back",
            "back": "back",
            "foot": "legs",
            "feet": "legs",
            "legs": "legs",
            "lumbar": "lumbar",
        }.get(motor)
        if axis is None:
            raise ValueError(f"Unsupported Reverie position axis: {motor}")
        if self.model.tandem and self._stk_selected_side != "1":
            if axis == "back":
                side = int(self._stk_selected_side)
                await self._write_bytes_to_char(
                    STK_SIDE_DATA_UUID,
                    bytes((side, 0x51, self._position_byte(position))),
                )
                return
        if axis == "lumbar" and not self.model.lumbar and not self.model.body_tilt:
            raise ValueError(f"Model {self.model_id} has no lumbar position")
        if axis == "back":
            characteristic = REVERIE_NIGHTSTAND_HEAD_POSITION_UUID
            value = self._position_byte(position)
        elif axis == "legs":
            characteristic = REVERIE_NIGHTSTAND_FOOT_POSITION_UUID
            value = self._position_byte(position)
        else:
            characteristic = REVERIE_NIGHTSTAND_LUMBAR_UUID
            if self.model.body_tilt:
                if not -100 <= position <= 100:
                    raise ValueError("Reverie body tilt must be between -100 and 100")
                value = self._body_tilt_to_wire(position)
            else:
                value = self._position_byte(position)
        await self._write_to_char(characteristic, value)

    @staticmethod
    def _position_byte(position: int) -> int:
        if isinstance(position, bool) or not isinstance(position, int):
            raise ValueError("Reverie position must be an integer")
        return position & 0xFF

    def _set_stk_side(self, side: str) -> None:
        if side not in ("1", "2", "3"):
            raise ValueError("STK side must be 1, 2, or 3")
        self._stk_selected_side = side
        self.forward_controller_state_update(STK_SIDE, side)
        self._publish_stk_head_position()

    async def _select_stk_side(self, side: str) -> None:
        self._set_stk_side(side)

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head up."""
        if self.model.tandem and self._stk_selected_side != "1":
            self._active_stk_motion_side = int(self._stk_selected_side)
            await self._write_stk_axis(0x01, side=self._active_stk_motion_side)
            return
        if self.model.tandem:
            self._active_stk_motion_side = 1
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID, ReverieNightstandCommands.MOTOR_UP
        )

    async def move_head_down(self) -> None:
        """Move head down."""
        if self.model.tandem and self._stk_selected_side != "1":
            self._active_stk_motion_side = int(self._stk_selected_side)
            await self._write_stk_axis(0x03, side=self._active_stk_motion_side)
            return
        if self.model.tandem:
            self._active_stk_motion_side = 1
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID, ReverieNightstandCommands.MOTOR_DOWN
        )

    async def move_head_stop(self) -> None:
        """Stop head motor."""
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no motor controls")
        stop_side = self._active_stk_motion_side
        if self.model.tandem:
            side = stop_side
            if side is None and self._stk_selected_side != "1":
                side = int(self._stk_selected_side)
            if side is not None and side != 1:
                try:
                    await self._write_stk_axis(
                        0xFF,
                        no_data=True,
                        side=side,
                        cancel_event=asyncio.Event(),
                    )
                finally:
                    self._active_stk_motion_side = None
                return
            if side == 1:
                try:
                    await self._write_to_char(
                        REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
                        ReverieNightstandCommands.MOTOR_STOP,
                        cancel_event=asyncio.Event(),
                    )
                finally:
                    self._active_stk_motion_side = None
                return
        await self._write_to_char(
            REVERIE_NIGHTSTAND_LINEAR_HEAD_UUID,
            ReverieNightstandCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        """Move back up (same as head)."""
        await self.move_head_up()

    async def move_back_down(self) -> None:
        """Move back down (same as head)."""
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        """Stop back motor."""
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        """Move legs up."""
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID, ReverieNightstandCommands.MOTOR_UP
        )

    async def move_legs_down(self) -> None:
        """Move legs down."""
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID, ReverieNightstandCommands.MOTOR_DOWN
        )

    async def move_legs_stop(self) -> None:
        """Stop legs motor."""
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no motor controls")
        await self._write_to_char(
            REVERIE_NIGHTSTAND_LINEAR_FOOT_UUID,
            ReverieNightstandCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        """Move feet up."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet down."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor."""
        await self.move_legs_stop()

    # Lumbar motor control
    async def move_lumbar_up(self) -> None:
        """Move lumbar up."""
        if not self.model.lumbar:
            raise ValueError(f"Model {self.model_id} has no lumbar actuator")
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID, ReverieNightstandCommands.MOTOR_UP
        )

    async def move_lumbar_down(self) -> None:
        """Move lumbar down."""
        if not self.model.lumbar:
            raise ValueError(f"Model {self.model_id} has no lumbar actuator")
        await self._move_linear(
            REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID, ReverieNightstandCommands.MOTOR_DOWN
        )

    async def move_lumbar_stop(self) -> None:
        """Stop lumbar motor."""
        if not self.model.lumbar:
            raise ValueError(f"Model {self.model_id} has no lumbar actuator")
        await self._write_to_char(
            REVERIE_NIGHTSTAND_LINEAR_LUMBAR_UUID,
            ReverieNightstandCommands.MOTOR_STOP,
            cancel_event=asyncio.Event(),
        )

    async def stop_all(self) -> None:
        """Release each axis exposed by the selected model."""
        self._cancel_routine()
        if not self.model.positions:
            raise ValueError(f"Model {self.model_id} has no motor controls")
        stops = [self.move_head_stop, self.move_legs_stop]
        if self.model.lumbar:
            stops.append(self.move_lumbar_stop)
        failures: list[Exception] = []
        for stop in stops:
            try:
                await stop()
            except Exception as err:
                failures.append(err)
        if failures:
            raise ExceptionGroup("Reverie motor STOP writes failed", failures)

    async def _write_stk_axis(
        self,
        command: int,
        *,
        no_data: bool = False,
        side: int | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        selected_side = side if side is not None else int(self._stk_selected_side)
        char_uuid = STK_SIDE_NO_DATA_UUID if no_data else STK_SIDE_DATA_UUID
        await self._write_bytes_to_char(
            char_uuid,
            bytes((selected_side, command)),
            cancel_event=cancel_event or (asyncio.Event() if no_data else None),
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise ValueError(f"Unsupported Reverie Nightstand held control: {control}")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
            raise ValueError("Reverie hold duration must be an integer number of milliseconds")
        if not 100 <= duration_ms <= 60_000:
            raise ValueError("Reverie hold duration must be between 100 and 60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        """Hold one axis once and release that same physical axis and STK side."""
        self.validate_hold_control(control, duration_ms)
        is_up = control.endswith("_up")
        axis = control.rsplit("_", 1)[0]
        stk_side = (
            int(self._stk_selected_side)
            if self.model.tandem and axis == "back"
            else None
        )
        start = {
            ("back", True): self.move_back_up,
            ("back", False): self.move_back_down,
            ("legs", True): self.move_legs_up,
            ("legs", False): self.move_legs_down,
            ("lumbar", True): self.move_lumbar_up,
            ("lumbar", False): self.move_lumbar_down,
        }[(axis, is_up)]

        async def release() -> None:
            if stk_side is not None and stk_side != 1:
                await self.move_head_stop()
            elif axis == "back":
                await self.move_back_stop()
            elif axis == "legs":
                await self.move_legs_stop()
            else:
                await self.move_lumbar_stop()

        try:
            if stk_side is not None and stk_side != 1:
                self._active_stk_motion_side = stk_side
                await self._write_stk_axis(0x01 if is_up else 0x03, side=stk_side)
            else:
                await start()
            await asyncio.sleep(duration_ms / 1000)
        except BaseException as operation_error:
            try:
                await release()
            except BaseException as release_error:
                raise BaseExceptionGroup(
                    "Reverie Nightstand hold and release both failed",
                    [operation_error, release_error],
                ) from operation_error
            raise
        else:
            await release()

    # Preset methods
    async def preset_flat(self) -> None:
        """Select the app's flat preset."""
        await self._write_preset_mode(3)

    async def preset_zero_g(self) -> None:
        """Go to zero gravity position (Mode 1)."""
        await self._write_preset_mode(1)

    async def preset_anti_snore(self) -> None:
        """Select the app's anti-snore preset."""
        await self._write_preset_mode(2)

    async def _write_preset_mode(self, mode: int) -> None:
        if isinstance(mode, bool) or not isinstance(mode, int) or mode not in (1, 2, 3):
            raise ValueError("Reverie preset mode must be 1, 2, or 3")
        if not self.model.presets:
            raise ValueError(f"Model {self.model_id} has no preset modes")
        if self.model.tandem and self._stk_selected_side != "1":
            command = {1: 0x21, 2: 0x22}.get(mode, 0x05)
            await self._write_bytes_to_char(
                STK_SIDE_DATA_UUID,
                bytes((int(self._stk_selected_side), command)),
            )
            return
        if self.model.body_tilt:
            command = {
                1: bytes.fromhex("00204724000000000000"),
                2: bytes.fromhex("000C0024000000000000"),
            }.get(mode, bytes.fromhex("00000024000000000000"))
            await self._write_bytes_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, command)
            return
        mode_byte = {
            1: ReverieNightstandCommands.MODE_ZERO_G,
            2: ReverieNightstandCommands.MODE_ANTI_SNORE,
        }.get(mode, ReverieNightstandCommands.MODE_FLAT)
        await self._write_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, mode_byte)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset (1-4)."""
        if (
            isinstance(memory_num, bool)
            or not isinstance(memory_num, int)
            or not self.model.memory_positions
            or not 1 <= memory_num <= 4
        ):
            raise ValueError("This model does not support the requested memory slot")
        if self.model.tandem and self._stk_selected_side != "1":
            await self._write_bytes_to_char(
                STK_SIDE_DATA_UUID,
                bytes((int(self._stk_selected_side), memory_num + 16)),
            )
            return
        command = ReverieNightstandCommands.memory_preset(memory_num)
        await self._write_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, command)

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory (1-4)."""
        if (
            isinstance(memory_num, bool)
            or not isinstance(memory_num, int)
            or not self.model.memory_positions
            or not 1 <= memory_num <= 4
        ):
            raise ValueError("This model does not support the requested memory slot")
        if self.model.tandem and self._stk_selected_side != "1":
            await self._write_bytes_to_char(
                STK_SIDE_DATA_UUID,
                bytes((int(self._stk_selected_side), memory_num + 32)),
            )
            return
        command = ReverieNightstandCommands.store_memory(memory_num)
        await self._write_to_char(REVERIE_NIGHTSTAND_PRESETS_UUID, command)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed lights."""
        if not self.model.nightlight:
            raise ValueError(f"Model {self.model_id} has no under-bed lights")
        value = self._light_brightness or self._last_nonzero_light_brightness or 64
        await self._write_to_char(REVERIE_NIGHTSTAND_LED_UUID, value)
        self._light_brightness = value
        self._last_nonzero_light_brightness = value
        self.forward_controller_state_updates(LIGHT_LEVEL(value), UNDER_BED_LIGHTS_ON(True))

    async def lights_off(self) -> None:
        """Turn off under-bed lights."""
        if not self.model.nightlight:
            raise ValueError(f"Model {self.model_id} has no under-bed lights")
        if self._light_brightness:
            self._last_nonzero_light_brightness = self._light_brightness
        await self._write_to_char(REVERIE_NIGHTSTAND_LED_UUID, ReverieNightstandCommands.LED_OFF)
        self._light_brightness = 0
        self.forward_controller_state_updates(LIGHT_LEVEL(0), UNDER_BED_LIGHTS_ON(False))

    async def lights_toggle(self) -> None:
        """Toggle the current light state using the app's readable state."""
        state = await self.read_light_state()
        lights_on = next(
            (update.value for update in reversed(state) if update.key == UNDER_BED_LIGHTS_ON),
            False,
        )
        if lights_on:
            await self.lights_off()
        else:
            await self.lights_on()

    async def set_light_level(self, level: int) -> None:
        """Write RGB brightness while preserving the last known RGB values."""
        if not self.model.nightlight:
            raise ValueError(f"Model {self.model_id} has no under-bed lights")
        if not 0 <= level <= 100:
            raise ValueError("Reverie light brightness must be 0-100")
        if self._light_rgb is None:
            await self.read_light_state()
        if self._light_rgb is None:
            raise ValueError("Reverie RGB state is unavailable; refusing to guess a color")
        await self._write_bytes_to_char(
            REVERIE_NIGHTSTAND_RGB_UUID,
            bytes((0x01, level, *self._light_rgb)),
        )
        self._light_brightness = level
        if level > 0:
            self._last_nonzero_light_brightness = level
        self.forward_controller_state_updates(LIGHT_LEVEL(level), UNDER_BED_LIGHTS_ON(level > 0))

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        """Write an exact RGB color at the last known brightness."""
        if not self.model.nightlight:
            raise ValueError(f"Model {self.model_id} has no under-bed lights")
        if len(rgb_color) != 3 or any(not 0 <= value <= 255 for value in rgb_color):
            raise ValueError("RGB values must each be in the range 0-255")
        if self._light_brightness is None:
            await self.read_light_state()
        brightness = self._light_brightness
        if brightness is None:
            raise ValueError("Reverie light brightness is unavailable")
        await self._write_bytes_to_char(
            REVERIE_NIGHTSTAND_RGB_UUID,
            bytes((0x01, brightness, *rgb_color)),
        )
        self._light_rgb = rgb_color
        self.forward_controller_state_updates(
            UNDER_BED_LIGHTS_RGB(rgb_color),
            UNDER_BED_LIGHTS_ON(brightness > 0),
            LIGHT_LEVEL(brightness),
        )

    async def read_light_state(self) -> tuple[StateUpdate, ...]:
        """Read LED, RGB and massage state from their P1 characteristics."""
        if not self.model.nightlight and not self.model.massage:
            raise ValueError(f"Model {self.model_id} has no readable light or massage state")
        if self.client is None or not self.client.is_connected:
            raise ConnectionError("Not connected to bed")
        async with self._ble_lock:
            state: list[StateUpdate] = []
            if self.model.nightlight:
                led_data = await self.client.read_gatt_char(REVERIE_NIGHTSTAND_LED_UUID)
                rgb_data = await self.client.read_gatt_char(REVERIE_NIGHTSTAND_RGB_UUID)
                if led_data:
                    brightness = led_data[0]
                    self._light_brightness = brightness
                    if brightness > 0:
                        self._last_nonzero_light_brightness = brightness
                    state.append(UNDER_BED_LIGHTS_ON(brightness > 0))
                if len(rgb_data) == 5 and rgb_data[0] == 0x01:
                    brightness = rgb_data[1]
                    self._light_brightness = brightness
                    if brightness > 0:
                        self._last_nonzero_light_brightness = brightness
                    self._light_rgb = (rgb_data[2], rgb_data[3], rgb_data[4])
                    state += [
                        LIGHT_LEVEL(brightness),
                        UNDER_BED_LIGHTS_RGB(self._light_rgb),
                        UNDER_BED_LIGHTS_ON(brightness > 0),
                    ]
            if self.model.massage:
                head_data = await self.client.read_gatt_char(
                    REVERIE_NIGHTSTAND_HEAD_WAVE_UUID
                )
                foot_data = await self.client.read_gatt_char(
                    REVERIE_NIGHTSTAND_FOOT_WAVE_UUID
                )
                wave_data = await self.client.read_gatt_char(
                    REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID
                )
                if head_data:
                    self._massage_head_level = head_data[0] // 4
                if foot_data:
                    self._massage_foot_level = foot_data[0] // 4
                if wave_data:
                    self._massage_wave_level = wave_data[0]
                state += [
                    MASSAGE_HEAD_INTENSITY(self._massage_head_level),
                    MASSAGE_FOOT_INTENSITY(self._massage_foot_level),
                    MASSAGE_WAVE(self._massage_wave_level),
                ]
        self.forward_controller_state_updates(*state)
        return tuple(state)

    # Massage methods
    async def massage_off(self) -> None:
        """Turn off massage."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        await self._write_to_char(REVERIE_NIGHTSTAND_HEAD_WAVE_UUID, 0)
        self._massage_head_level = 0
        self.forward_controller_state_update(MASSAGE_HEAD_INTENSITY, 0)
        await self._write_to_char(REVERIE_NIGHTSTAND_FOOT_WAVE_UUID, 0)
        self._massage_foot_level = 0
        self.forward_controller_state_update(MASSAGE_FOOT_INTENSITY, 0)
        await self._write_to_char(REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID, 0)
        self._massage_wave_level = 0
        self.forward_controller_state_updates(MASSAGE_WAVE(0))

    async def massage_head_up(self) -> None:
        """Increase head massage intensity (0-10, written as level * 4)."""
        await self.set_massage_intensity("head", min(10, self._massage_head_level + 1))

    async def massage_head_down(self) -> None:
        """Decrease head massage intensity (0-10, written as level * 4)."""
        await self.set_massage_intensity("head", max(0, self._massage_head_level - 1))

    async def massage_foot_up(self) -> None:
        """Increase foot massage intensity (0-10, written as level * 4)."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = min(10, self._massage_foot_level + 1)
        await self._write_to_char(
            REVERIE_NIGHTSTAND_FOOT_WAVE_UUID, level * 4
        )
        self._massage_foot_level = level
        self.forward_controller_state_update(MASSAGE_FOOT_INTENSITY, self._massage_foot_level)

    async def massage_foot_down(self) -> None:
        """Decrease foot massage intensity (0-10, written as level * 4)."""
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        level = max(0, self._massage_foot_level - 1)
        await self._write_to_char(
            REVERIE_NIGHTSTAND_FOOT_WAVE_UUID, level * 4
        )
        self._massage_foot_level = level
        self.forward_controller_state_update(MASSAGE_FOOT_INTENSITY, self._massage_foot_level)

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if not self.model.massage:
            raise ValueError(f"Model {self.model_id} does not support massage")
        if zone in ("head", "foot"):
            if not 0 <= level <= 10:
                raise ValueError("Reverie massage strength must be 0-10")
            if self.model.tandem and self._stk_selected_side != "1" and zone == "head":
                await self._write_bytes_to_char(
                    STK_SIDE_DATA_UUID,
                    bytes((int(self._stk_selected_side), 0x53, level * 4)),
                )
                self._massage_head_level = level
                self.forward_controller_state_update(MASSAGE_HEAD_INTENSITY, level)
                return
            characteristic = (
                REVERIE_NIGHTSTAND_HEAD_WAVE_UUID
                if zone == "head"
                else REVERIE_NIGHTSTAND_FOOT_WAVE_UUID
            )
            await self._write_to_char(characteristic, level * 4)
            if zone == "head":
                self._massage_head_level = level
            else:
                self._massage_foot_level = level
            self.forward_controller_state_update(massage_intensity(zone), level)
            return
        if zone == "wave":
            if self.model.tandem and self._stk_selected_side != "1":
                raise ValueError("Use the STK head wave number for side 2 or 3")
            if not 0 <= level <= 255:
                raise ValueError("Reverie global massage wave must be 0-255")
            await self._write_to_char(REVERIE_NIGHTSTAND_MASSAGE_WAVE_UUID, level)
            self._massage_wave_level = level
            self.forward_controller_state_update(MASSAGE_WAVE, level)
            return
        if zone == "stk_head_wave":
            if not self.model.tandem or self._stk_selected_side == "1":
                raise ValueError("STK head wave requires numeric side 2 or 3")
            if not 0 <= level <= 10:
                raise ValueError("STK head wave must be between 0 and 10")
            await self._write_bytes_to_char(
                STK_SIDE_DATA_UUID,
                bytes((int(self._stk_selected_side), 0x40, level * 4)),
            )
            self.forward_controller_state_update(STK_HEAD_WAVE, level)
            return
        if zone == "stk_global":
            if not self.model.tandem or self._stk_selected_side == "1":
                raise ValueError("STK global massage requires numeric side 2 or 3")
            if not 0 <= level <= 191:
                raise ValueError("STK global massage value must fit in the offset byte")
            await self._write_bytes_to_char(
                STK_SIDE_DATA_UUID,
                bytes((int(self._stk_selected_side), level + 64)),
            )
            self.forward_controller_state_update(STK_GLOBAL_MASSAGE, level)
            return
        raise ValueError(f"Unsupported Reverie massage zone: {zone}")


async def build_controller(ctx: BuildContext) -> ReverieNightstandController:
    """Build the controller for the selected Reverie model."""
    return ReverieNightstandController(ctx.coordinator, model=ctx.variant)
