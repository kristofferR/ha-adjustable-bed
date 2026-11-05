"""The MotoMotion 3.1.9 app as a profile over ``codec/motomotion.py``.

The app has one profile. Its exact Bluetooth name selects the panel and the
independent feature flags, each read from a name position as the app reads it.
"""

from dataclasses import dataclass
from typing import ClassVar

from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

PANELS = {
    "1": "One",
    "2": "One",
    "3": "Three",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "One",
    "9": "One",
    "A": "A",
    "D": "D",
    "E": "E",
    "G": "G",
    "H": "H",
    "J": "J",
}


def name_length(name: str) -> int:
    """Dart String.length counts UTF-16 code units, including surrogate pairs."""
    return sum(2 if ord(character) > 0xFFFF else 1 for character in name)


def name_character(name: str, index: int) -> str:
    """Preserve the app's String[] indexing and its out-of-range failure."""
    unit = name.encode("utf-16-le", errors="surrogatepass")[index * 2 : index * 2 + 2]
    if len(unit) != 2:
        raise IndexError("MotoMotion name index is out of range")
    return unit.decode("utf-16-le", errors="surrogatepass")


def eligible(name: str | None) -> bool:
    return name is not None and (
        ("SOFA" in name and name_length(name) == 15)
        or ("BT201" in name and name_length(name) == 9)
        or "MOTO" in name
    )


# The app's one profile key; the name's panel and flags are its settings.
PROFILE_KEY = "motomotion"


@dataclass(frozen=True)
class Profile:
    name: str
    # No hold yet: the held controls need a per-control scope
    # (docs/design/execution-capabilities.md).
    execution: ClassVar[ExecutionCapabilities] = NO_EXECUTION_CAPABILITIES

    @property
    def key(self) -> str:
        return PROFILE_KEY


    def __post_init__(self) -> None:
        if not eligible(self.name):
            raise ValueError("Enter the exact MotoMotion Bluetooth local name")
        if "BT201" not in self.name and name_length(self.name) < 11:
            raise ValueError("MotoMotion panel selection needs name positions 9 and 10")

        if self.sofa and name_length(self.name) < 15:
            raise ValueError("MotoMotion SOFA flags need name positions through 14")
        if self.panel == "Five" and name_length(self.name) < 15:
            raise ValueError("MotoMotion panel Five needs name position 14")

    def char(self, index: int) -> str:
        try:
            return name_character(self.name, index)
        except IndexError:
            return ""

    @property
    def panel(self) -> str:
        if "BT201" in self.name:
            return "Binary music"
        if self.char(9) == "M" and self.char(10) == "M":
            return "Music"
        return PANELS.get(self.char(9), "One")

    @property
    def sofa(self) -> bool:
        return "SOFA" in self.name

    @property
    def sides(self) -> bool:
        return self.sofa and self.char(10) == "S"

    @property
    def binary(self) -> bool:
        return "MOTO" in self.name

    @property
    def light_kind(self) -> int:
        return {"B": 1, "D": 1, "C": 2}.get(self.char(11), 0) if self.sofa else 0

    @property
    def music(self) -> bool:
        return "music" in self.panel.lower() or (
            self.sofa and (self.char(9) in ("M", "8") or self.char(10) in ("M", "S"))
        )

    @property
    def rgb(self) -> bool:
        return (
            self.sofa
            and self.char(11) == "D"
            and not (self.char(9) == "6" and self.char(10) == "A")
        )

    @property
    def users(self) -> bool:
        return self.sofa and self.char(10) == "A"

    @property
    def heat(self) -> bool:
        return (
            (self.sofa and (self.char(14) == "H" or (self.char(14) == "M" and self.char(9) != "6")))
            or (self.panel == "Five" and self.char(14) not in ("N", "M", "X"))
            or self.panel == "H"
        )

    @property
    def massage(self) -> bool:
        return self.sofa and self.char(14) == "M"
