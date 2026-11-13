"""Rize Remedy II 1.0.1 (2), row180, over the shared OKIN Bedding controller.

The source's A0/positive-byte notification acknowledges local save intent;
there is no position, lighting, massage or persistent-memory telemetry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from ...card import CARD_MASSAGE, CARD_UTILITY
from ...command_scheduler import CommandOutcome, current_command_context
from ...controller_state import StateKey
from ..entity_specs import ControllerButtonSpec, ControllerStateSensorSpec, PositionNumberSpec
from .controller import OkinBeddingAppController

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator

_INFO_READ_DELAY_S: Final = 1.0

_NOTIFY: Final = "62741625-52f9-8864-b1ab-3b3a8d65950b"
SAVE_ACK: Final = StateKey[int | None]("rize_remedy_ii_save_acknowledged")
_SAVE_ACTIONS: Final = ("save_zero_g", "save_incline", "save_lounge")


class RizeRemedyIIController(OkinBeddingAppController):
    """One fixed product, without the other apps' parsers or save thresholds."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app="rize_remedy_ii")
        self._session = object()
        self._command_session = self._session
        self._session_client: BleakClient | None = None
        self._command_client: BleakClient | None = None
        self._pending_save: int | None = None
        # Untagged replies cannot distinguish overlapping unresolved saves.
        self._save_ambiguous = False

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key=SAVE_ACK,
                translation_key="rize_remedy_ii_save_acknowledged",
                state_key=SAVE_ACK,
                icon="mdi:content-save-check-outline",
                card=CARD_UTILITY,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            replace(spec, card=CARD_MASSAGE, translation_key=f"rize_remedy_ii_{action}")
            for spec, (action, _) in zip(super().controller_button_specs, self._app.buttons, strict=True)
        )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "cst_profile": self.profile.key,
            "save_pending_code": self._pending_save,
            "save_ack_ambiguous": self._save_ambiguous,
        }

    def _clear_session(self) -> None:
        self._session = object()
        self._session_client = None
        self._pending_save = None
        self._save_ambiguous = False
        self.forward_controller_state_update(SAVE_ACK, None)

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._clear_session()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.require_roles()
        self._clear_session()
        client = self.client
        if client is None:
            raise ConnectionError("Rize Remedy II is not connected")
        self._session_client = client
        self._notify_callback = callback
        session = self._session

        def receive(sender: object, data: bytearray) -> None:
            if session is self._session and client is self.client and client.is_connected:
                self._handle_notification(sender, data)

        async with self._ble_lock:
            await client.start_notify(_NOTIFY, receive)
        # The app's optional 2a24 read is diagnostic only, one second after connect.
        await asyncio.sleep(_INFO_READ_DELAY_S)
        if session is self._session and client is self.client and client.is_connected:
            await self.refresh_manufacturer()

    async def stop_notify(self) -> None:
        self._clear_session()
        await super().stop_notify()

    def _manufacturer_read(self, manufacturer: str) -> None:
        """The source only logs device information; it never gates capabilities."""

    def _handle_notification(self, _: object, data: bytearray) -> None:
        if self._session_client is not self.client or self.client is None or not self.client.is_connected:
            return
        self.forward_raw_notification(_NOTIFY, bytes(data))
        if (
            len(data) > 10 and data[6] == 0xA0 and 0 < data[10] < 0x80
            and self._pending_save is not None and not self._save_ambiguous
        ):
            code, self._pending_save = self._pending_save, None
            self.forward_controller_state_update(SAVE_ACK, code)

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self._app.actions:
            raise ValueError("Unknown Rize Remedy II control")
        if isinstance(duration_ms, bool) or not isinstance(duration_ms, int) or not 0 < duration_ms <= 60000:
            raise ValueError("Duration must be a positive integer, at most 60000 ms")

    def _hold_ms(self, action: str) -> int:
        # 500 ms is the active voice one-shot deadline. Save chords have no
        # source threshold; HA gives a tap the same bounded press, or an explicit hold.
        return 500

    def _memory_action(self, memory_num: int, prefix: str = "") -> str:
        if isinstance(memory_num, bool) or not isinstance(memory_num, int) or memory_num not in (1, 2, 3):
            raise ValueError("Rize Remedy II has Zero Gravity, Incline and Leisure memories")
        action = _SAVE_ACTIONS[memory_num - 1]
        return action if prefix else action.removeprefix("save_")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        self._command_client = self.client
        self._command_session = self._session
        if control in self._app.save_codes:
            if self._pending_save is not None:
                self._save_ambiguous = True
            self._pending_save = self._app.save_codes[control]
            self.forward_controller_state_update(SAVE_ACK, None)
        elif self._pending_save is not None:
            # A subsequent operation makes an untagged, late response ambiguous.
            self._pending_save = None
            self._save_ambiguous = True
        try:
            await super().hold_control(control, duration_ms)
        except BaseException as error:
            context = current_command_context()
            stopped = (
                isinstance(error, asyncio.CancelledError)
                and context is not None and context.cancel_reason is CommandOutcome.STOPPED
            )
            if not stopped:
                self._pending_save = None
                self._save_ambiguous = True
            raise

    async def _move_motor(self, motor: str, command_value: int | None) -> None:
        if command_value is None:
            await self.stop_all()
            return
        action = next(key for key, fields in self._app.actions.items() if fields == (command_value, 0))
        # Count remains effective for ordinary covers. Only a scheduler lease
        # extends the stream; its cancellation/expiry owns release under the lock.
        await self.hold_control(action, self.leased_hold_ms(self._coordinator.motor_pulse_count * 100))

    async def write_command(
        self, command: bytes, repeat_count: int = 1, repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        client = self._command_client
        session = self._command_session

        def require_session() -> None:
            if session is not self._session or client is None or client is not self.client or not client.is_connected:
                raise ConnectionError("Rize Remedy II command session ended")

        require_session()
        await self._write_gatt_with_retry(
            self.control_characteristic_uuid, command,
            repeat_count=repeat_count, repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event, response=self._write_response(),
            wall_clock_pacing=True, expected_client=client, before_write=require_session,
        )

    async def stop_all(self) -> None:
        # Explicit STOP preserves a pending save, just as the source does.
        self._command_client = self.client
        self._command_session = self._session
        await self._send_stop_sequence()

    async def massage_mode_step(self) -> None:
        await self._send_next_wave(1)
