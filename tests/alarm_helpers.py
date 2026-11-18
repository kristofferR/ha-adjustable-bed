"""Drive the shared ``set_alarm`` action against one real controller.

Target resolution and BLE scheduling are replaced; validation and the
controller's own frame building run for real, so a per-bed test can assert the
exact bytes the new action writes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.services import async_register_services


async def call_set_alarm(
    hass: HomeAssistant,
    controller: BedController,
    data: dict[str, Any],
    *,
    owner: object | None = None,
    side: str = "both",
    bed_type: str | None = None,
) -> list[dict[str, Any]]:
    """Call ``set_alarm`` for one physical target and return each write's scheduling."""
    target = MagicMock(
        bed_type=bed_type,
        capability_controller=controller,
        operation_identity=1,
    )
    target.name = "Bed"
    owner = owner if owner is not None else MagicMock()
    scheduled: list[dict[str, Any]] = []

    async def preflight_each(targets, check):
        check(target, controller)
        return []

    async def execute(coordinator, target_side, command, **kwargs):
        scheduled.append(kwargs)
        side_scope = getattr(controller, "side_scope", None)
        if side_scope is None:
            await command(controller)
            return
        with side_scope(target_side):
            await command(controller)

    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(owner, side)], []),
        ),
        patch("custom_components.adjustable_bed.services._command_targets", return_value=[target]),
        patch("custom_components.adjustable_bed.services._preflight_each", side_effect=preflight_each),
        patch("custom_components.adjustable_bed.services._execute_sided", side_effect=execute),
    ):
        if not hass.services.has_service(DOMAIN, "set_alarm"):
            await async_register_services(hass)
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": "bed", **data}, blocking=True
        )
    return scheduled
