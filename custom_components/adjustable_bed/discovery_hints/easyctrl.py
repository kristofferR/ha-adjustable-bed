"""EasyCtrl service-filtered scan; manufacturer admission is refined in detection."""

from ..codec.cheerssleep import SERVICE
from ._hints import services

HINTS = services(SERVICE, bed_types={"easyctrl"})
