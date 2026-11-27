"""MUUEGM 1.0.2 current product catalogs over the Richmat codec."""

import json
from pathlib import Path
from typing import Final

from .dreamsense import Action, DreamSenseProfile

SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")


class MuuegmProfile(DreamSenseProfile):
    @property
    def key(self) -> str:
        return "muuegm_" + self.product


PROFILES: Final = {
    key: MuuegmProfile(**{**row, "controls": tuple(Action(**a) for a in row["controls"])})
    for key, row in json.loads(Path(__file__).with_suffix(".json").read_text()).items()
}
CHOICES: Final = {key: key for key in PROFILES}
PALETTE: Final = {
    "yellow": (255, 255, 0),
    "green": (0, 255, 0),
    "azure": (0, 127, 255),
    "blue": (0, 0, 255),
    "violet": (139, 0, 255),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
}
