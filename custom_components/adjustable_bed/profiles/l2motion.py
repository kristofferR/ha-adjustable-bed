"""Leon's L2Motion 2.0.2: name-selected controls over the HHC letter carrier."""

from typing import ClassVar

from .bedgear import eligible
from .bedgear import panel as panel
from .hhc_layout import HhcLetterLayout

LAYOUT_EXAMPLES = (
    "15",
    "35",
    "E1",
    "81",
    "51",
    "44",
    "91",
    "13",
    "71",
    "61",
    "D1",
    "34",
    "23",
    "01",
    "97",
)


class L2MotionProfile(HhcLetterLayout):
    key: ClassVar[str] = "l2motion"

    def __post_init__(self) -> None:
        if not eligible(self.name):
            raise ValueError("Enter the exact L2 Motion Bluetooth name")

    @property
    def music(self) -> bool:
        return self.wrapped

    @property
    def timer(self) -> bool:
        return self.char(10) != "B"

    @property
    def rgb(self) -> bool:
        return self.timer and self.char(11) != "D"
