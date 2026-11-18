"""Construct the shared catalog controller from Bob's persisted product/layout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import CONF_PRODUCT_TYPE
from ..profiles.bobpowerbase import CATALOG, LAYOUTS
from .builder import BuildContext

if TYPE_CHECKING:
    from .goodvibe.controller import GoodVibeController


async def build_controller(ctx: BuildContext) -> GoodVibeController:
    await ctx.preload("goodvibe.controller")
    from .goodvibe.controller import GoodVibeController

    layout = ctx.data.get(CONF_PRODUCT_TYPE, "standard")
    if layout not in LAYOUTS:
        raise ValueError("Choose the Power Bob Base layout")
    # Layout describes the installation, never a new wire side or product.
    return GoodVibeController(ctx.coordinator, profile=ctx.variant or "", catalog=CATALOG)
