"""TEMPUR AU direct-BLE app profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import CONF_PRODUCT_TYPE
from ..profiles.keeson import app_profile
from .builder import BuildContext
from .keeson.layout_app import AppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class TempurAUController(AppController):
    """Explicit TEMPUR AU app profile; physical effects remain unverified."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        side: str = "both",
    ) -> None:
        super().__init__(coordinator, app_profile("tempur_au", layout), side=side)


async def build_controller(ctx: BuildContext) -> TempurAUController:
    """Build the controller for the stored layout."""
    return TempurAUController(ctx.coordinator, layout=ctx.data.get(CONF_PRODUCT_TYPE))
