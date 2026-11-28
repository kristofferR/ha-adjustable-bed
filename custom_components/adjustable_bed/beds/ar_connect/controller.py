"""Choose only the explicit AR Connect physical route."""

from ...errors import invalid
from ...profiles.ar_connect import AR_CONNECT, LAYOUTS
from ..builder import BuildContext
from .headboard import HeadboardController
from .native import NativeController


async def build_controller(ctx: BuildContext) -> NativeController | HeadboardController:
    if ctx.variant == "headboard":
        controller = HeadboardController(ctx.coordinator)
        saved = ctx.stored_capabilities("ar_connect")
        if saved is not None and type(saved.get("config")) is int:
            controller.config = saved["config"]
        return controller
    if ctx.variant not in (None, "auto", "native"):
        raise invalid("ar_connect_route")
    layout = ctx.data.get("product_type", "back_legs")
    if layout not in LAYOUTS:
        raise invalid("ar_connect_layout")
    native = NativeController(ctx.coordinator, layout)
    saved = ctx.stored_capabilities("ar_connect")
    if saved is not None:
        axes = saved.get("axes")
        if (
            saved.get("layout") == layout
            and isinstance(axes, list)
            and all(axis in AR_CONNECT.axes for axis in axes)
            and {"back", "legs"} <= set(axes)
        ):
            native.axes = tuple(axis for axis in AR_CONNECT.axes if axis in axes)
        if ctx.client is None and type(saved.get("mask")) is int:
            native.mask = saved["mask"]
    return native
