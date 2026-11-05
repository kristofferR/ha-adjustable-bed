"""Richmat discovery hints: the WiLinke services and Nordic UART.

The classic apps' services are W1, W2, Nordic UART and W4. Their scan names
are wider than a matcher, so detection offers them only beside these hints.
"""

from ..const import (
    BED_TYPE_CLUSTER018,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_RICHMAT,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_W4_SERVICE_UUID,
)
from ._hints import Hint, services

HINTS: tuple[Hint, ...] = (
    *services("8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7", bed_types={BED_TYPE_RICHMAT, BED_TYPE_LEGGETT_WILINKE}),  # WiLinke custom
    *services(
        "0000fee9-0000-1000-8000-00805f9b34fb",  # WiLinke W1
        "0000fee9-0000-1000-8000-00805f9b34bb",  # WiLinke W2
        bed_types={BED_TYPE_RICHMAT, BED_TYPE_LEGGETT_WILINKE, BED_TYPE_CLUSTER018},
    ),
    # W4 is a generic short UUID; detection requires a Richmat name with it.
    *services(RICHMAT_WILINKE_W4_SERVICE_UUID, bed_types={BED_TYPE_RICHMAT, BED_TYPE_CLUSTER018}),
    *services(
        RICHMAT_NORDIC_SERVICE_UUID,
        bed_types={BED_TYPE_RICHMAT, BED_TYPE_CLUSTER018},
        connectable=True,
    ),
)
