"""Shared GATT services wake discovery; detection also requires a bed name."""

from ..const import BED_TYPE_SUPERIOR_SLEEP
from ..profiles.superior_sleep import TRANSPORTS
from ._hints import services

HINTS = services(
    *(t.service for t in TRANSPORTS.values()), bed_types={BED_TYPE_SUPERIOR_SLEEP}, connectable=True
)
