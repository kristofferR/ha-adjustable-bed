"""Linak discovery hints."""

from collections.abc import Collection
from typing import Final

from ..const import (
    BED_TYPE_LINAK,
    BED_TYPE_VINDO,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_POSITION_SERVICE_UUID,
)
from ._hints import Hint, names, services

_VINDO_NAME_PARTS: Final = ("linak", "lin2ble", "ble2lin")

HINTS: tuple[Hint, ...] = (
    *services(LINAK_CONTROL_SERVICE_UUID, bed_types={BED_TYPE_LINAK, BED_TYPE_VINDO}),
    *services(LINAK_POSITION_SERVICE_UUID, bed_types={BED_TYPE_LINAK}),
    # Some Linak beds advertise only a name such as "Bed 1696".
    names("Bed", bed_types={BED_TYPE_LINAK}),
)


def matches_vindo_advertisement(name: str, service_uuids: Collection[str]) -> bool:
    """Offer Vindö for the app's name matches on the Linak control service."""
    return LINAK_CONTROL_SERVICE_UUID in service_uuids and any(
        part in name.lower() for part in _VINDO_NAME_PARTS
    )
