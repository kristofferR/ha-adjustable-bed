"""Ergo Slim direct-BLE app profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import CONF_PRODUCT_TYPE
from ..profiles.keeson import app_profile
from .builder import BuildContext
from .keeson_layout_app import AppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class ErgoSlimController(AppController):
    """Explicit Ergo Slim app profile; physical effects remain unverified."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        side: str = "both",
    ) -> None:
        super().__init__(coordinator, app_profile("ergo_slim", layout), side=side)


async def build_controller(ctx: BuildContext) -> ErgoSlimController:
    """Build the controller for the stored layout."""
    return ErgoSlimController(ctx.coordinator, layout=ctx.data.get(CONF_PRODUCT_TYPE))
