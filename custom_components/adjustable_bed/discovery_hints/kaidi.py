"""Kaidi discovery hints."""

from ..const import (
    BED_TYPE_COMFYDS,
    BED_TYPE_KAIDI,
    BED_TYPE_KOMFYD,
    BED_TYPE_RIZE,
    KAIDI_DISCOVERY_SERVICE_UUID,
    KAIDI_MANUFACTURER_COMPANY_ID,
    KAIDI_MESH_SERVICE_UUID,
)
from ._hints import Hint, manufacturer, names, services

HINTS: tuple[Hint, ...] = (
    *services(KAIDI_DISCOVERY_SERVICE_UUID, bed_types={BED_TYPE_KAIDI}, connectable=True),
    *services(KAIDI_MESH_SERVICE_UUID, bed_types={BED_TYPE_KAIDI}),
    # The PairLink mesh payload marker; detection requires corroboration.
    manufacturer(KAIDI_MANUFACTURER_COMPANY_ID, data_start=b"\xc0\xff", bed_types={BED_TYPE_KAIDI, BED_TYPE_RIZE, BED_TYPE_KOMFYD, BED_TYPE_COMFYDS}),
    names("Mouselet", bed_types={BED_TYPE_KAIDI}),
)
