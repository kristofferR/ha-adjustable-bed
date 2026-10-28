"""Ergo Slim direct-BLE app profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..cluster033_profiles import app_profile
from .cluster033 import AppController

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
