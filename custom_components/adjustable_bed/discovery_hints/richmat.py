"""Richmat discovery hints: the WiLinke services and Nordic UART.

The classic apps' services are W1, W2, Nordic UART and W4. Their scan names
are wider than a matcher, so detection offers them only beside these hints.
"""

from ..const import (
    BED_TYPE_ATLAS_LIFT,
    BED_TYPE_JEROME_ADJUSTABLE_BASE,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    RICHMAT_NORDIC_SERVICE_UUID,
    RICHMAT_WILINKE_W4_SERVICE_UUID,
)
from ..profiles.jerome_adjustable_base import SCAN_TERMS
from ..profiles.richmat import ATLAS_LIFT_SCAN_KEYWORD
from ._hints import Hint, names, services

ATLAS_LIFT_NAME_HINT = names(
    ATLAS_LIFT_SCAN_KEYWORD, bed_types={BED_TYPE_ATLAS_LIFT}, anywhere=True
)

HINTS: tuple[Hint, ...] = (
    ATLAS_LIFT_NAME_HINT,
    # Luuna's case-sensitive contains filters. HA can gate their prefix subset;
    # common services cover interior matches. They never select its product.
    names(*SCAN_TERMS, bed_types={BED_TYPE_RICHMAT, BED_TYPE_JEROME_ADJUSTABLE_BASE}, anywhere=True),
    # Some Richmat remotes advertise a fixed name instead of a code.
    names("Sleep Function", bed_types={BED_TYPE_RICHMAT}),
    # Germany Motions beds on the W4 service (#163).
    names("DHN-", bed_types={BED_TYPE_RICHMAT}),
    *services("8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7", bed_types={BED_TYPE_RICHMAT, BED_TYPE_LEGGETT_WILINKE, BED_TYPE_RICHMAT_CLASSIC_APPS}),  # WiLinke custom
    *services(
        "0000fee9-0000-1000-8000-00805f9b34fb",  # WiLinke W1
        "0000fee9-0000-1000-8000-00805f9b34bb",  # WiLinke W2
        bed_types={BED_TYPE_RICHMAT, BED_TYPE_LEGGETT_WILINKE, BED_TYPE_RICHMAT_CLASSIC_APPS},
    ),
    # W4 is a generic short UUID; detection requires a Richmat name with it.
    *services(RICHMAT_WILINKE_W4_SERVICE_UUID, bed_types={BED_TYPE_RICHMAT, BED_TYPE_RICHMAT_CLASSIC_APPS}),
    *services(
        RICHMAT_NORDIC_SERVICE_UUID,
        bed_types={BED_TYPE_RICHMAT, BED_TYPE_RICHMAT_CLASSIC_APPS},
        connectable=True,
    ),
)
