"""Okin 5A controller over Nordic UART (Mattress Firm 900 / iFlex).

Reverse-engineered by @kristofferR based on discovery from @Zrau5454.
Source: https://github.com/kristofferR/ha-adjustable-bed/issues/50

The ``okin_nordic`` profile sends the Mattress Firm handshake and wake before
the first command and writes with response. See ``docs/beds/okin-5a.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..profiles.okin_5a import OKIN_NORDIC
from .okin_7byte import Okin7ByteController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


class OkinNordicController(Okin7ByteController):
    """The Okin 5A controller over the ``okin_nordic`` profile."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=OKIN_NORDIC)
