"""Omazz Adjusto III direct-BLE app profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..cluster033_profiles import app_profile
from .cluster033 import AppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class OmazzAdjustoIIIController(AppController):
    """Explicit Omazz Adjusto III app profile; physical effects remain unverified."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        side: str = "both",
    ) -> None:
        super().__init__(coordinator, app_profile("omazz_adjusto_iii", layout), side=side)
