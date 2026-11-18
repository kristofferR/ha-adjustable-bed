"""Customatic Z-Series app alarm and clock actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from homeassistant.core import ServiceCall

from ...import_executor import async_import_modules
from ...services import (
    _call_targets,
    _command_targets,
    _execute_sided,
    _family_command,
    _get_controller_for_service,
    _invalid,
    _preflight_capability,
    _release_preflighted,
    _validation_error,
)
from ..base import controller_as

if TYPE_CHECKING:
    from .controller import ZSeriesController




async def _execute_zseries_alarm(
    call: ServiceCall,
    label: str,
    command: Callable[[ZSeriesController], Awaitable[None]],
    validate: Callable[[ZSeriesController], None] | None = None,
) -> None:
    """Preflight every physical Z-Series target before any alarm or clock write."""
    await async_import_modules(call.hass, "beds.serenity.controller")
    from .controller import ZSeriesController

    targets = _call_targets(call)
    # The alarm page exists only after an exact CST13/CST14 manufacturer read.
    # A cached controller can only rule a bed out on a confirmed other string.
    preflighted = await _preflight_capability(
        targets,
        ZSeriesController,
        label,
        supported=lambda zseries: zseries.alarm_not_ruled_out,
        validate=validate,
    )
    try:
        # All-or-nothing: resolve every unknown state on a live connection before
        # any bed receives a clock or alarm frame.
        physical = [
            (coordinator, target)
            for coordinator, side in targets
            for target in _command_targets(coordinator, side)
        ]
        for coordinator, target in physical:
            cached = controller_as(target.capability_controller, ZSeriesController)
            state = cached.alarm_state if cached is not None else None
            if state is None:
                opened = not target.is_connected
                if not any(known is target for _, known in preflighted):
                    preflighted.append((coordinator, target))
                live = controller_as(await _get_controller_for_service(target), ZSeriesController)
                if live is None:
                    raise _invalid(
                        "feature_not_supported",
                        f"Device '{target.name}' does not support {label}",
                        device_name=target.name,
                        feature=label,
                    )
                state = await live.resolve_alarm_state()
                if opened and len(physical) > 1:
                    # Like _validation_controller, never hold a capability-only link
                    # while probing the next target: a sequential or one-slot path
                    # cannot open a second one. The read result is persisted, and
                    # execution reconnects each side through its normal path.
                    released = await target.async_disconnect("capability_probe")
                    if released is False or target.is_connected:
                        raise _invalid(
                            "bed_release_failed",
                            f"Could not release '{target.name}' before checking the next bed",
                            device_name=target.name,
                        )
                    preflighted[:] = [item for item in preflighted if item[1] is not target]
            if state is None:
                raise _invalid(
                    "zseries_alarm_unknown",
                    f"Could not read the manufacturer string of '{target.name}' that "
                    "enables Z-Series alarms; try again",
                    device_name=target.name,
                )
            if not state:
                raise _invalid(
                    "feature_not_supported",
                    f"Device '{target.name}' does not support {label}",
                    device_name=target.name,
                    feature=label,
                )
        for coordinator, side in targets:
            # The app cancels the running stream first; HA also releases it safely.
            await _execute_sided(
                coordinator, side, _family_command(ZSeriesController, label, command)
            )
    except ValueError as err:
        await _release_preflighted(preflighted)
        raise _validation_error(err) from err
    except BaseException:
        await _release_preflighted(preflighted)
        raise
