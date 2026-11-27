"""Purely Sleep's explicitly selected normal-mode controls on a physical session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from functools import partial
from typing import TYPE_CHECKING, Final

from ...command_scheduler import note_frame_skipped, note_frame_written, note_write_not_counted
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles.purely_sleep import INITIALIZATION, PROFILES
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from .atlas_lift import RichmatSessionController, _Link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

VERSION: Final = StateKey[int | None]("purely_sleep_protocol_version")
CLOCK: Final = StateKey[bool | None]("purely_sleep_clock_available")
LIGHT: Final = StateKey[bool | None]("purely_sleep_light_available")


async def _save(controller: BedController, code: int) -> None:
    selected = require_controller(controller, PurelySleepController)
    await selected.write_command(selected._build_command(code))


async def _combined(controller: BedController, up: bool, duration_ms: int | None = None) -> None:
    selected = require_controller(controller, PurelySleepController)
    await selected._move_with_stop(
        selected._code("head_feet_up" if up else "head_feet_down"), duration_ms=duration_ms
    )


class PurelySleepController(RichmatSessionController):
    """Normal JLRN/VJRM; no capabilities borrowed from other catalog products."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        if product not in PROFILES:
            raise invalid("purely_sleep_product_required")
        self.product = PROFILES[product]
        super().__init__(coordinator, self.product, INITIALIZATION, "purely_sleep_gatt")
        self._next_write = 0.0
        self._version = 0  # The app's fresh normal-mode model, E48.

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_massage(self) -> bool:
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    def _require_normal(self) -> None:
        if self._version == 1:
            raise invalid("purely_sleep_version_one")

    @property
    def persisted_app_state(self) -> Mapping[str, object]:
        # The existing store scopes this exclusion by physical address and product.
        return {"protocol_version": self._version}

    def restore_persisted_app_state(self, state: Mapping[str, object]) -> None:
        version = state.get("protocol_version")
        if type(version) is int and 0 <= version <= 255:
            self._version = version

    @property
    def retain_live_controller_offline(self) -> bool:
        return True

    def validate_button_press(self, key: str) -> None:
        if key.startswith(("preset_", "program_memory_", "purely_sleep_save_")):
            self._require_normal()

    def validate_memory_recall(self, memory_num: int) -> None:
        super().validate_memory_recall(memory_num)
        self._require_normal()

    def validate_timed_movement(self, motor: str, direction: str, duration_ms: int) -> None:
        self._require_normal()

    @property
    def supports_memory_programming(self) -> bool:
        return self._version != 1

    async def _write_on(
        self,
        link: _Link,
        command: bytes,
        cancel: asyncio.Event,
        *,
        before_write: Callable[[], None] | None = None,
        track_command_write: bool = True,
    ) -> None:
        # The command lock owns the operation, this lock owns FIFO GATT order.
        # A single awaited write has no app retry or acknowledgement claim.
        caller = asyncio.current_task()
        async with self.ble_lock:
            await asyncio.sleep(max(0, self._next_write - asyncio.get_running_loop().time()))
            self._current_link(link)
            if cancel.is_set() or caller is not None and caller.cancelling():
                note_frame_skipped()
                raise asyncio.CancelledError
            if track_command_write:
                self._require_normal()
            if before_write is not None:
                before_write()
            response = "write-without-response" not in link.tx.properties
            self._record_command_trace(
                link.tx.uuid, command, characteristic=link.tx, response=response
            )
            self._next_write = asyncio.get_running_loop().time() + 0.1

            async def write() -> None:
                await link.client.write_gatt_char(link.tx, command, response=response)
                if track_command_write:
                    note_frame_written(cancel)
                else:
                    note_write_not_counted()

            await settled(write(), eager_start=True)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._current_link().notify is None:
            raise invalid("purely_sleep_gatt")
        await super().start_notify(callback)

    def _receive_notification(self, sender: str, data: bytes) -> None:
        super()._receive_notification(sender, data)
        # Only the accepted complete common-parser branches. Extended framing,
        # cache reconstruction and capability-to-control inference are deferred.
        if len(data) == 5 and data[:3] == b"\x6e\x90\x00":
            self._version = data[3]
            self.forward_controller_state_updates(VERSION(self._version))
        elif data == b"\x6e\x09\x01\x00\x78":
            self.forward_controller_state_updates(CLOCK(True))
        elif data == b"\x6e\x0e\x00\x03\x7f":
            self.forward_controller_state_updates(LIGHT(True))

    def on_disconnect(self) -> None:
        super().on_disconnect()
        self._next_write = 0.0
        # A known V1 connection must not become normal merely by reconnecting.
        self.forward_controller_state_updates(VERSION(None), CLOCK(None), LIGHT(None))

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                str(VERSION), str(VERSION), VERSION, "mdi:information-outline"
            ),
            ControllerStateSensorSpec(str(CLOCK), str(CLOCK), CLOCK, "mdi:clock-outline"),
            ControllerStateSensorSpec(str(LIGHT), str(LIGHT), LIGHT, "mdi:lightbulb-outline"),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = super().motor_control_specs
        if "head_feet_up" not in (self.product.codes or {}):
            return axes
        return (
            *axes,
            MotorControlSpec(
                "both",
                "both",
                partial(_combined, up=True),
                partial(_combined, up=False),
                lambda controller: controller.stop_all(),
                scheduler_resource="motor:both",
                stop_scope="side",
                timed_move_fn=_combined,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            save_button(
                f"purely_sleep_save_{key}",
                f"Save {label}",
                partial(_save, code=code),
                combine_sides=True,
            )
            for key, label, code in self.product.saves
        )


async def build_controller(ctx: BuildContext) -> PurelySleepController:
    return PurelySleepController(ctx.coordinator, product=ctx.variant or "")
