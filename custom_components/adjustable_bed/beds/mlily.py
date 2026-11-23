"""MLILY Control's catalog over the shared Flutter Richmat runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..import_executor import async_import_modules
from ..profiles.mlily_choices import PROFILE_CHOICES
from .builder import BuildContext

if TYPE_CHECKING:
    from .goodvibe.controller import GoodVibeController


def suggested_profile(name: str | None) -> str | None:
    """Offer the artifact's name mapping only within MLILY's admitted catalog."""
    from .goodvibe.discovery import name_product

    if name is not None and name.startswith("RM-"):
        return "sleep_rm"
    if name is not None and name.startswith("HJ-"):
        return "sleep_hj"
    try:
        key = name_product(name).lower()
    except ValueError:
        return None
    return key if key in PROFILE_CHOICES else None


def scan_matches(name: str | None) -> bool:
    """The scan list is case-sensitive even though the selection helper uppercases."""
    return isinstance(name, str) and (
        name.startswith(("RM-", "HJ-", "MPE_"))
        or any(code.upper() in name for code in PROFILE_CHOICES
               if "/" not in code and not code.startswith("sleep_"))
        or any(prefix in name for prefix in ("B6RU", "200I", "200i", "400I", "400i", "800I", "800i"))
    )


async def build_controller(ctx: BuildContext) -> GoodVibeController:
    await ctx.preload("goodvibe.controller")
    await async_import_modules(ctx.coordinator.hass, "profiles.mlily")
    from ..profiles.mlily import catalog
    from .goodvibe.controller import GoodVibeController

    app = await ctx.coordinator.hass.async_add_executor_job(catalog)
    return GoodVibeController(ctx.coordinator, profile=ctx.variant or "", catalog=app)
