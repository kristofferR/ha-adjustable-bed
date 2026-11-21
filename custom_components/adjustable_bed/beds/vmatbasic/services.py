"""VMAT Basic floor-light hold and rename routes for the generic actions."""

from __future__ import annotations

from ...errors import invalid, rejected
from ...services import BedTarget, _command_targets, _preflight_and_execute


def _single_receiver(targets: list[tuple[BedTarget, str]]) -> None:
    """Reject a selection that is not exactly one physical receiver."""
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    if len(physical) != 1:
        raise invalid("one_bed_only")


async def _hold_vmatbasic_floor(
    targets: list[tuple[BedTarget, str]], control: str, duration_ms: int
) -> None:
    """Refresh the XT floor light; it belongs to one physical receiver, never mirrored."""
    from .controller import VMatBasicController

    _single_receiver(targets)

    def validate(controller: VMatBasicController) -> None:
        if control not in controller.held_control_options:
            raise invalid("not_supported_by_bed", feature="the floor light refresh")

    await _preflight_and_execute(
        targets,
        VMatBasicController,
        lambda controller: controller.hold_control(control, duration_ms),
        supported=lambda controller: controller.supports_held_control,
        validate=validate,
        cancel_running=True,
        resource="lighting",
    )


async def _rename_vmatbasic(targets: list[tuple[BedTarget, str]], name: str) -> None:
    """Rename exactly one selected primary receiver, retaining the old name on failure."""
    from ...coordinator import AdjustableBedCoordinator
    from ...profiles.vmatbasic import rename
    from .controller import VMatBasicController

    try:
        packet = rename(name)
        if len(packet) > 20:
            raise ValueError("Encoded name exceeds the safe twenty-byte write payload")
    except (ValueError, UnicodeError) as error:
        raise rejected(error) from error
    _single_receiver(targets)
    receiver = _command_targets(*targets[0])[0]
    if not isinstance(receiver, AdjustableBedCoordinator):
        raise invalid("one_bed_only")
    name = packet.decode("utf-8")

    async def rename_and_remember(controller: VMatBasicController) -> None:
        await controller.rename_device(name)
        receiver.remember_vmatbasic_name(name)

    await _preflight_and_execute(
        targets,
        VMatBasicController,
        rename_and_remember,
        supported=lambda controller: controller.supports_device_rename,
        cancel_running=True,
    )
