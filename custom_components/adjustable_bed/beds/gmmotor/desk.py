"""GM Control's dedicated FWRM/WFRM desk route, separate from primary controls."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..base import ControllerButtonSpec, ControllerHoldSpec
from .controller import GmmotorController
from .protocol import Material, desk_packet, stop_packet
from .requests import Request

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_DESK_ACTIONS = {
    "desk_up": Material("deviceFunctionItemDeskUp", 1),
    "desk_down": Material("deviceFunctionItemDeskDown", 2),
    "desk_reset": Material("deviceFunctionItemDeskReset", 0),
    "desk_memory_1": Material("deviceFunctionItemDeskMemory1", 4),
    "desk_memory_2": Material("deviceFunctionItemDeskMemory2", 8),
    "desk_memory_3": Material("deviceFunctionItemDeskMemory3", 16),
}
_HELD = frozenset(("desk_up", "desk_down", "desk_reset"))


class GmmotorDeskController(GmmotorController):
    """The dedicated widget uses a desk builder and has a no-op long callback."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, profile: str) -> None:
        if profile not in ("FWRM", "WFRM"):
            raise ValueError("Choose the exact GM Control desk product")
        super().__init__(coordinator, profile=profile)

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(_DESK_ACTIONS)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in _DESK_ACTIONS
            or type(duration_ms) is not int
            or not 0 <= duration_ms <= 60000
        ):
            raise ValueError("Invalid GM Control desk control/duration")

    def controller_button_available(self, key: str) -> bool:
        return key in _DESK_ACTIONS

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return tuple(
            ControllerButtonSpec(
                key=control,
                name=control.replace("_", " ").capitalize(),
                press_fn=lambda ctrl, c=control: ctrl.hold_control(c, 1000 if c in _HELD else 0),
                hold=ControllerHoldSpec(control, 100, 0) if control in _HELD else None,
            )
            for control in _DESK_ACTIONS
        )

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        cancel = self._coordinator.cancel_command
        if control not in _HELD:
            # The desk binds a TFA-empty long callback. Its enum's long opcode
            # is compiled metadata and is never sent by the dedicated widget.
            if duration_ms < 3000 and await self._pause(duration_ms / 1000, cancel):
                await self.write_command(desk_packet(_DESK_ACTIONS[control]))
            return
        ticks = duration_ms // 100
        sent = False
        try:
            for _ in range(ticks):
                if not await self._pause(0.1, cancel):
                    return
                sent = True
                await self.write_command(desk_packet(_DESK_ACTIONS[control]))
        finally:
            if sent:
                await self.stop_all()

    async def stop_all(self) -> None:
        # The dedicated desk has no side picker, even when HA routes a second
        # physical desk through a logical Right child.
        await self.write_command(
            stop_packet(side=0, single=self._single), cancel_event=asyncio.Event()
        )

    async def _setup_menu(self) -> None:
        await self._pause(0.3, self._coordinator.cancel_command)
        await self.write_command(desk_packet(Material("deviceFunctionItemDeskRequestData", 0)))

    def _height_bounds(self, unit: str) -> tuple[float, float]:
        data = self._events.get("desk_data")
        defaults = (60.0, 125.0) if unit == "cm" else (23.6, 49.21)
        if not isinstance(data, dict):
            return defaults
        lower, upper = (
            data.get("min_" + unit if unit == "cm" else "min_inches"),
            data.get("max_" + unit if unit == "cm" else "max_inches"),
        )
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            return float(lower), float(upper)
        return defaults

    def validate_gmmotor_request(self, request: Request) -> None:
        if request.operation not in ("desk_height", "desk_unit", "desk_query", "refresh"):
            raise ValueError("This GM Control route admits only dedicated desk operations")
        if request.operation == "desk_height":
            lower, upper = self._height_bounds(request.unit)
            if not lower <= request.height <= upper:
                raise ValueError(f"Desk height must be between {lower} and {upper} {request.unit}")

    async def async_execute_gmmotor_request(self, request: Request) -> None:
        self.validate_gmmotor_request(request)
        if request.operation == "desk_height":
            # Dedicated ruler callback 0x799b74 converts inches to cm first,
            # then scales by ten before the builder's decimal-pair truncation.
            value = request.height * (2.54 if request.unit == "inch" else 1) * 10
            packet = desk_packet(Material("deviceFunctionItemDeskSetHeight", 0), height=value)
        elif request.operation == "desk_unit":
            packet = desk_packet(
                Material(
                    "deviceFunctionItemDeskChangeInch"
                    if request.unit == "inch"
                    else "deviceFunctionItemDeskChangeCentimetre",
                    1 if request.unit == "inch" else 0,
                )
            )
        else:
            packet = desk_packet(Material("deviceFunctionItemDeskRequestData", 0))
        await self.write_command(packet)
