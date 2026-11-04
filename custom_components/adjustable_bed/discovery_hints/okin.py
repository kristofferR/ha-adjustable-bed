"""Okin discovery hints: the shared 62741523 service, receivers and CB24."""

from ..const import (
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_NECTAR,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_UUID,
    MANUFACTURER_ID_OKIN,
    OKIMAT_SERVICE_UUID,
)
from ._hints import Hint, manufacturer, names, services

HINTS: tuple[Hint, ...] = (
    *services(
        OKIMAT_SERVICE_UUID,
        bed_types={BED_TYPE_OKIMAT, BED_TYPE_OKIN_UUID, BED_TYPE_LEGGETT_OKIN, BED_TYPE_NECTAR},
    ),
    # Pairing-only receivers advertise just a name until bonded.
    names(
        *(
            f"{okin}*{receiver}"
            for okin in ("OKIN", "Okin", "okin")
            for receiver in ("Receiver", "receiver")
        ),
        bed_types={BED_TYPE_OKIN_UUID},
    ),
    # Nordic's company ID; detection requires an OKIN or SmartBed name with it.
    manufacturer(MANUFACTURER_ID_OKIN, bed_types={BED_TYPE_OKIN_CB24}),
)
