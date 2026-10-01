"""Exact shipped VMAT remote selectors, independent of Bluetooth identity."""

from dataclasses import dataclass
from typing import Final

VMAT_METADATA_FIELDS: Final = (
    "xmc_status", "opmode", "device_name", "revision_id", "revision_string", "variant",
)


@dataclass(frozen=True, slots=True)
class VmatRemote:
    asset: str
    control_type: int
    floor_light: bool = False
    rgb: bool = False
    massage: bool = False
    light_extension: bool = False

    @property
    def groups(self) -> tuple[str, ...]:
        if self.control_type in (2, 8):
            return ("back", "legs")
        if self.control_type == 9:
            return ("head", "back", "legs")
        return ("head", "back", "legs", "feet")


VMAT_REMOTES: Final = {
    "00": VmatRemote("sender_010", 2),
    "01": VmatRemote("sender_020", 2, floor_light=True),
    "02": VmatRemote("sender_180", 2),
    "03": VmatRemote("sender_190", 2),
    "04": VmatRemote("sender_200", 2, floor_light=True),
    "05": VmatRemote("sender_210", 2, floor_light=True),
    "06": VmatRemote("sender_220", 2, floor_light=True),
    "07": VmatRemote("sender_230", 8, floor_light=True),
    "08": VmatRemote("sender_240", 8, floor_light=True),
    "09": VmatRemote("sender_250", 8, floor_light=True),
    "10": VmatRemote("sender_260", 8, floor_light=True),
    "11": VmatRemote("sender_270", 9),
    "12": VmatRemote("sender_090", 2, rgb=True, massage=True, light_extension=True),
    "13": VmatRemote("sender_100", 1, rgb=True, massage=True, light_extension=True),
}

# VMAT's shipped floating-point conversion has its own truncation results.
VMAT_MOOD_PALETTE: Final = {
    "#008a00": (0, 138, 0), "#00aba9": (0, 170, 168),
    "#1ba1e2": (26, 161, 226), "#0050ef": (0, 80, 238),
    "#6a00ff": (106, 0, 255), "#aa00ff": (170, 0, 255),
    "#f472d0": (244, 114, 208), "#d80073": (216, 0, 115),
    "#a20025": (162, 0, 36), "#e51400": (229, 19, 0),
    "#fa6800": (250, 104, 0), "#f0a30a": (239, 162, 9),
    "#e3c800": (227, 200, 0), "#825a2c": (130, 90, 44),
    "#6d8764": (109, 135, 100), "#647687": (100, 118, 135),
    "#76708a": (118, 112, 138), "#ffffff": (255, 255, 255),
}


def get_vmat_remote(remote: str | None) -> VmatRemote:
    """Require the exact ordinal, never guess a product from its asset name."""
    if not isinstance(remote, str) or remote not in VMAT_REMOTES:
        raise ValueError("Select one of the fourteen shipped VMAT remotes")
    return VMAT_REMOTES[remote]
