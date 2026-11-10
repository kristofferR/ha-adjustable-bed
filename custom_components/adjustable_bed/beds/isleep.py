"""ISleep 1.6.3 profile over the shared Kaidi app session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..profiles.kaidi import validate_isleep_profile
from .kaidi.app import KaidiAppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class IsleepController(KaidiAppController):
    """ISleep commands and product gates from accepted row064."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, validate_isleep_profile(coordinator.entry.data))
