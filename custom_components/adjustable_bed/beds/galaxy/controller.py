"""Build Galaxy's profile on the shared Richmat catalog lifecycle."""

from ..builder import BuildContext
from ..goodvibe.controller import GoodVibeController
from .catalog import CATALOG, resolve_product


async def build_controller(ctx: BuildContext) -> GoodVibeController:
    profile = resolve_product(ctx.variant or "")
    return GoodVibeController(ctx.coordinator, profile=profile, catalog=CATALOG)
