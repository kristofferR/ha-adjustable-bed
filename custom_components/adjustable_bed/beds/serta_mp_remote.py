"""Serta MP Remote, com.ore.serta330 1.1, direct BLE only.

Local angle memories send calibrated pulse targets. Remote M4 is a separate
opaque key. Neither operation is a physical memory-save instruction.
"""

from __future__ import annotations

import asyncio
import bisect
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from ..cluster033_profiles import app_profile
from ..command_scheduler import CommandKind, CommandOutcome, current_command_context
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .cluster033 import AppController, finish

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

HEAD_TABLE = (
    0,
    336,
    532,
    714,
    918,
    1108,
    1309,
    1508,
    1712,
    1915,
    2132,
    2324,
    2537,
    2748,
    2981,
    3197,
    3435,
    3663,
    3913,
    4151,
    4386,
    4649,
    4884,
    5158,
    5393,
    5669,
    5917,
    6192,
    6461,
    6748,
    7023,
    7296,
    7575,
    7851,
    8146,
    8409,
    8708,
    9018,
    9295,
    9591,
    9889,
    10173,
    10475,
    10772,
    11075,
    11357,
    11655,
    11940,
    12241,
    12520,
    12760,
    13116,
    13413,
    13701,
    14015,
    14286,
    14581,
    14859,
    15147,
    15430,
    15500,
)
FOOT_TABLE = (
    0,
    663,
    935,
    1206,
    1471,
    1730,
    1987,
    2260,
    2517,
    2767,
    3051,
    3329,
    3583,
    3843,
    4097,
    4365,
    4623,
    4895,
    5145,
    5425,
    5668,
    5938,
    6185,
    6455,
    6689,
    6951,
    7199,
    7443,
    7703,
    7943,
    8193,
    8435,
    8674,
    8918,
    9146,
    9379,
    9625,
    9859,
    10089,
    10304,
    10551,
    10774,
    11004,
    11211,
    11453,
    11667,
)


def pulse_frame(head: int, foot: int) -> bytes:
    """Encode two source pulse fields, including the app's 0x8000 other axis."""
    return finish(
        b"\xe5\xfe\x17"
        + (head & 65535).to_bytes(2, "little")
        + (foot & 65535).to_bytes(2, "little")
    )


def pulse_angle(pulse: int, table: tuple[int, ...], threshold: int) -> int:
    if pulse >= 32768:
        pulse = 65535 - pulse
    if pulse > threshold:
        return len(table) - 1
    index = bisect.bisect_left(table, pulse)
    if index and pulse - table[index - 1] <= table[index] - pulse:
        return index - 1
    return index


class SertaMPRemoteController(AppController):
    """Exact MP Remote keys, pulse targets and session-scoped UI request state."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        memories: Sequence[tuple[int, int]] = ((15, 35), (15, 35), (15, 35), (15, 0)),
    ) -> None:
        super().__init__(coordinator, app_profile("serta_mp_remote", layout))
        if len(memories) != 4 or any(
            type(head) is not int
            or type(foot) is not int
            or not 0 <= head <= 60
            or not 0 <= foot <= 45
            for head, foot in memories
        ):
            raise ValueError("Four local memory targets require head 0..60 and foot 0..45 degrees")
        self._memories = tuple(memories)
        self._angles = (0, 0)
        self._memory_target: tuple[int, int] | None = None
        self._memory_active = False
        self._setters: list[asyncio.TimerHandle] = []
        self._local_release_stop: tuple[object, int, asyncio.Event] | None = None

    @property
    def supports_position_feedback(self) -> bool:
        return True

    @property
    def supports_direct_position_control(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return (
            build_position_number_spec("back", max_value=60, unit="°"),
            build_position_number_spec("legs", max_value=45, unit="°"),
        )

    @property
    def motor_max_angles(self) -> dict[str, float]:
        return {"back": 60.0, "legs": 45.0}

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        limits = self.motor_max_angles
        return tuple(
            replace(spec, max_angle=limits[spec.key]) for spec in super().motor_control_specs
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return super().held_control_options + (
            "head_target_up",
            "head_target_down",
            "foot_target_up",
            "foot_target_down",
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        from typing import cast

        def press(key: str):
            async def adjust(controller: BedController) -> None:
                current = cast(SertaMPRemoteController, controller)
                await current.hold_control(
                    key, max(1, min(60000, current._coordinator.motor_pulse_count * 200))
                )

            return adjust

        return super().controller_button_specs + tuple(
            ControllerButtonSpec(
                key,
                key.replace("_", " ").title(),
                press(key),
                hold=ControllerHoldSpec(key, 0, 0),
            )
            for key in ("head_target_up", "head_target_down", "foot_target_up", "foot_target_down")
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self._local_release_stop = None
        if "_target_" not in control:
            await super().hold_control(control, duration_ms)
            return
        self.validate_hold_control(control, duration_ms)
        self._ready()
        motor = "back" if control.startswith("head_") else "legs"
        target = self._angles[0 if motor == "back" else 1]
        maximum = 60 if motor == "back" else 45
        elapsed = 0
        context = current_command_context()
        session = self._session_cancel
        try:
            while elapsed < duration_ms and not self._coordinator.cancel_command.is_set():
                target = max(0, min(maximum, target + (1 if control.endswith("_up") else -1)))
                step = min(200, duration_ms - elapsed)
                if await self._wait(step):
                    break
                elapsed += step
        finally:
            # Local editing sends no intermediate movement or zero-key frame.
            # A valid current session receives one pulse target on release.
            if not self._session_cancel.is_set():
                scheduler = self._coordinator._command_scheduler
                stop_epoch = scheduler.stop_epoch
                table = HEAD_TABLE if motor == "back" else FOOT_TABLE
                await self.write_command(
                    pulse_frame(
                        table[target] if motor == "back" else 0x8000,
                        table[target] if motor == "legs" else 0x8000,
                    ),
                    cancel_event=asyncio.Event(),
                )
                if (
                    context is not None
                    and context.kind in (CommandKind.COMMAND, CommandKind.GROUP)
                    and context.scheduler_token is scheduler.token
                    and context.cancel_reason is CommandOutcome.STOPPED
                    and context.cancel_event.is_set()
                    and session is self._session_cancel
                    and not session.is_set()
                    and self.client is self._session_client
                    and self.client is not None
                    and self.client.is_connected
                ):
                    # Only the STOP that cancelled this edit may acknowledge
                    # its successful target write. Completion, replacement or
                    # failed writes cannot suppress a later global movement STOP.
                    self._local_release_stop = (context.scheduler_token, stop_epoch, session)

    async def stop_all(self) -> None:
        acknowledgement, self._local_release_stop = self._local_release_stop, None
        context = current_command_context()
        if (
            acknowledgement is not None
            and context is not None
            and context.kind is CommandKind.STOP
            and context.scheduler_token is acknowledgement[0]
            and context.admitted_stop_epoch == acknowledgement[1]
            and self._session_cancel is acknowledgement[2]
            and not self._session_cancel.is_set()
            and self.client is self._session_client
            and self.client is not None
            and self.client.is_connected
        ):
            return
        await super().stop_all()

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return super().controller_state_sensor_specs + (
            ControllerStateSensorSpec(
                "app_memory_request",
                "app_memory_request",
                "app_memory_request",
                "mdi:progress-check",
                attribute_keys=(
                    "app_memory_head_target",
                    "app_memory_foot_target",
                    "app_memory_progress_visible",
                    "app_head_flag",
                    "app_foot_flag",
                ),
            ),
        )

    async def set_motor_position(self, motor: str, position: int) -> None:
        if motor not in ("back", "legs"):
            raise ValueError("MP Remote has head/back and foot/legs pulse targets only")
        table = HEAD_TABLE if motor == "back" else FOOT_TABLE
        if type(position) is not int or not 0 <= position < len(table):
            raise ValueError("Angle target outside app calibration table")
        await self.write_command(
            pulse_frame(
                table[position] if motor == "back" else 0x8000,
                table[position] if motor == "legs" else 0x8000,
            )
        )

    async def preset_memory(self, memory_num: int) -> None:
        if not 1 <= memory_num <= 4:
            raise ValueError("MP Remote local memory slots are 1 through 4")
        head, foot = self._memories[memory_num - 1]
        await self.write_command(pulse_frame(HEAD_TABLE[head], FOOT_TABLE[foot]))
        self._memory_target = head, foot
        # Source schedules a state setter, not a second packet or an ACK.
        session = self._session_cancel

        def activate() -> None:
            if session is self._session_cancel and not session.is_set():
                self._memory_active = True
                latest = self._memory_target
                assert latest is not None
                self.forward_controller_state_updates(
                    {
                        "app_memory_request": "active",
                        "app_memory_head_target": latest[0],
                        "app_memory_foot_target": latest[1],
                    }
                )
            self._setters.remove(handle)

        handle = asyncio.get_running_loop().call_later(1.5, activate)
        self._setters.append(handle)

    def on_disconnect(self) -> None:
        self._local_release_stop = None
        for setter in getattr(self, "_setters", ()):
            setter.cancel()
        self._setters = []
        self._memory_active = False
        super().on_disconnect()

    def _parse_notification(self, data: bytes | None) -> None:
        if not data or len(data) != 16 or data[13] & 32:
            return
        head = pulse_angle(int.from_bytes(data[3:5], "little"), HEAD_TABLE, 15430)
        foot = pulse_angle(int.from_bytes(data[5:7], "little"), FOOT_TABLE, 11667)
        self._angles = head, foot
        if self._notify_callback is not None:
            self._notify_callback("back", float(head))
            self._notify_callback("legs", float(foot))
        updates: dict[str, object] = {
            "app_head_flag": bool(data[13] & 1),
            "app_foot_flag": bool(data[13] & 2),
        }
        if self._memory_active:
            complete = self._angles == self._memory_target or not data[13] & 3
            if complete:
                self._memory_active = False
            updates.update(
                {
                    "app_memory_request": "inactive" if complete else "active",
                    "app_memory_progress_visible": not complete,
                }
            )
        self.forward_controller_state_updates(updates)
        super()._parse_notification(data)
