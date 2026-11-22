"""Q-Plus Adjustable Remote direct-BLE app profile (com.sbi.costco)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import CONF_PRODUCT_TYPE, QPLUS_VARIANT_BOTH, QPLUS_VARIANTS
from ..profiles.keeson import app_profile
from .builder import BuildContext
from .keeson.layout_app import AppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class QPlusAppController(AppController):
    """Explicit Q-Plus Adjustable Remote app profile; physical effects remain unverified."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        side: str = QPLUS_VARIANT_BOTH,
    ) -> None:
        super().__init__(coordinator, app_profile("qplus_app", layout), side=side)


async def build_controller(ctx: BuildContext) -> QPlusAppController:
    """Build the controller for the stored layout and selected side."""
    return QPlusAppController(
        ctx.coordinator,
        layout=ctx.data.get(CONF_PRODUCT_TYPE),
        side=ctx.variant if ctx.variant in QPLUS_VARIANTS else QPLUS_VARIANT_BOTH,
    )
