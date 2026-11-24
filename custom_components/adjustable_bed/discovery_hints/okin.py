"""Okin discovery hints: the shared 62741523 service, receivers and CB24."""

from ..const import (
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RESIDENT,
    BED_TYPE_RIZE_REMEDY_II,
    BED_TYPE_SHUDA,
    MANUFACTURER_ID_OKIN,
    NORDIC_UART_SERVICE_UUID,
    OKIMAT_SERVICE_UUID,
)
from ._hints import Case, Hint, manufacturer, names, services

HINTS: tuple[Hint, ...] = (
    names("OKIN", case=Case.FOLD, bed_types={BED_TYPE_RIZE_REMEDY_II}),
    *services(NORDIC_UART_SERVICE_UUID, bed_types={BED_TYPE_SHUDA}, connectable=True),
    *services(
        OKIMAT_SERVICE_UUID,
        bed_types={BED_TYPE_OKIN_UUID, BED_TYPE_LEGGETT_OKIN, BED_TYPE_OKIN_7BYTE, BED_TYPE_RESIDENT},
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
    manufacturer(MANUFACTURER_ID_OKIN, bed_types={"smartbed"}),
    names("Headboard126", "Headboard265", bed_types={"smartbed"}),
)
