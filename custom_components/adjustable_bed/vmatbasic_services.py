"""VMAT Basic floor-light hold and rename routes for the generic actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import ServiceValidationError

from .const import BED_TYPE_VMATBASIC
from .services import (
    BedTarget,
    _command_targets,
    _execute_sided,
    _preflight_capability,
    _release_preflighted,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController


async def _hold_vmatbasic_floor(
    targets: list[tuple[BedTarget, str]], control: str, duration_ms: int
) -> None:
    """Refresh the XT floor light; it belongs to one physical receiver, never mirrored."""
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    if len(physical) != 1 or physical[0].bed_type != BED_TYPE_VMATBASIC:
        raise ServiceValidationError("Target one physical V-MAT Basic receiver for floor refresh")

    def validate(controller: BedController | SideBoundController) -> None:
        if control not in controller.held_control_options:
            raise ServiceValidationError("XT floor refresh requires the XT-Box profile")

    preflighted = await _preflight_capability(
        targets, "supports_held_control", "V-MAT Basic floor refresh", validate
    )
    try:
        await _execute_sided(
            targets[0][0],
            targets[0][1],
            lambda controller: controller.hold_control(control, duration_ms),
            resource="lighting",
        )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


async def _rename_vmatbasic(targets: list[tuple[BedTarget, str]], name: str) -> None:
    """Rename exactly one selected primary receiver, retaining the old name on failure."""
    from .coordinator import AdjustableBedCoordinator
    from .profiles.vmatbasic import rename

    try:
        packet = rename(name)
        if len(packet) > 20:
            raise ValueError("Encoded name exceeds the safe twenty-byte write payload")
    except (ValueError, UnicodeError) as error:
        raise ServiceValidationError(str(error)) from error
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    if len(physical) != 1:
        raise ServiceValidationError("Rename one physical V-MAT Basic receiver at a time")
    receiver = physical[0]
    if (
        not isinstance(receiver, AdjustableBedCoordinator)
        or receiver.bed_type != BED_TYPE_VMATBASIC
    ):
        raise ServiceValidationError("Rename one physical V-MAT Basic receiver at a time")
    preflighted = await _preflight_capability(
        targets, "supports_device_rename", "V-MAT Basic rename"
    )
    name = packet.decode("utf-8")

    async def rename_and_remember(controller: BedController) -> None:
        await controller.rename_device(name)
        receiver.remember_vmatbasic_name(name)

    try:
        await _execute_sided(
            targets[0][0], targets[0][1], rename_and_remember, resource="configuration"
        )
    except BaseException:
        await _release_preflighted(preflighted)
        raise
