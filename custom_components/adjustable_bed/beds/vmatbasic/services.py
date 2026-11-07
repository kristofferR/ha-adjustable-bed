"""VMAT Basic floor-light hold and rename routes for the generic actions."""

from __future__ import annotations

from homeassistant.exceptions import ServiceValidationError

from .services import BedTarget, _command_targets, _preflight_and_execute


def _single_receiver(targets: list[tuple[BedTarget, str]], message: str) -> None:
    """Reject a selection that is not exactly one physical receiver."""
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    if len(physical) != 1:
        raise ServiceValidationError(message)


async def _hold_vmatbasic_floor(
    targets: list[tuple[BedTarget, str]], control: str, duration_ms: int
) -> None:
    """Refresh the XT floor light; it belongs to one physical receiver, never mirrored."""
    from .beds.vmatbasic import VMatBasicController

    _single_receiver(targets, "Target one physical V-MAT Basic receiver for floor refresh")

    def validate(controller: VMatBasicController) -> None:
        if control not in controller.held_control_options:
            raise ServiceValidationError("XT floor refresh requires the XT-Box profile")

    await _preflight_and_execute(
        targets,
        VMatBasicController,
        "V-MAT Basic floor refresh",
        lambda controller: controller.hold_control(control, duration_ms),
        supported=lambda controller: controller.supports_held_control,
        validate=validate,
        cancel_running=True,
        resource="lighting",
    )


async def _rename_vmatbasic(targets: list[tuple[BedTarget, str]], name: str) -> None:
    """Rename exactly one selected primary receiver, retaining the old name on failure."""
    from .beds.vmatbasic import VMatBasicController
    from .coordinator import AdjustableBedCoordinator
    from .profiles.vmatbasic import rename

    try:
        packet = rename(name)
        if len(packet) > 20:
            raise ValueError("Encoded name exceeds the safe twenty-byte write payload")
    except (ValueError, UnicodeError) as error:
        raise ServiceValidationError(str(error)) from error
    message = "Rename one physical V-MAT Basic receiver at a time"
    _single_receiver(targets, message)
    receiver = _command_targets(*targets[0])[0]
    if not isinstance(receiver, AdjustableBedCoordinator):
        raise ServiceValidationError(message)
    name = packet.decode("utf-8")

    async def rename_and_remember(controller: VMatBasicController) -> None:
        await controller.rename_device(name)
        receiver.remember_vmatbasic_name(name)

    await _preflight_and_execute(
        targets,
        VMatBasicController,
        "V-MAT Basic rename",
        rename_and_remember,
        supported=lambda controller: controller.supports_device_rename,
        cancel_running=True,
    )
