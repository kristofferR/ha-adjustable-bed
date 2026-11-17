"""Okimiki 1.0.1 (10101), accepted row169, frozen 2026-07-14.

Hand-transcribed from the accepted report, no generator. The four concrete
receivers pass supportOkimiki; 1025 library entries do not. Hardware UNVERIFIED.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ..codec import richmat as codec
from .richmat import RichmatProfile
from .richmat_catalog import Action, Catalog
from .richmat_catalog import Product as CatalogProduct


@dataclass(frozen=True, slots=True)
class Product:
    code: str
    enum_index: int
    cid: int
    factory_branch: str
    support_body: str
    menu_body: str
    alarm_body: str
    memory_slots: int
    alarm: Literal["none", "single", "repeat"]


# Equal code addresses do not merge receiver identities or alarm lists.
# fmt: off
PRODUCTS: Final = {
    "HCRN": Product("HCRN", 954, 803, "0x446b98", "0x74e658", "0x7d87dc", "0xa6b1fc", 2, "none"),
    "IPRM": Product("IPRM", 334, 741, "0x441e18", "0x74e720", "0x7eda3c", "0xa6b1fc", 0, "none"),
    "IQRM": Product("IQRM", 335, 740, "0x441e38", "0x74e720", "0x8059a8", "0x74e3dc", 2, "single"),
    "KWRN": Product("KWRN", 1027, 624, "0x4474b8", "0x74e8c8", "0x8059a8", "0x74d194", 2, "repeat"),
}
# fmt: on
PROFILE_CHOICES: Final = {code: code for code in PRODUCTS}
SCAN_KEYWORDS: Final = (
    "QRRM",
    "MlRM",
    "COOL",
    "Cool",
    "MPE_",
    "209A05",
    "208A14",
    "200U",
    "FC200",
    "200I",
    "400I",
    "800I",
    "L&P-",
    "L&P ",
    "BED-",
    *PRODUCTS,
)


def scan_matches(name: str | None) -> bool:
    """Case-sensitive contains, without inferring a product from a shared name."""
    return name is not None and any(keyword in name for keyword in SCAN_KEYWORDS)


# Selected only after all 71 accepted literal rows passed the production codec.
WIRE: Final = RichmatProfile(key="okimiki", transports=("n1", "w1", "w2", "w3", "w4", "w5"))


@dataclass(frozen=True, slots=True)
class Control:
    label: str
    opcode: int
    save: int | None = None
    held: bool = False


# Values and gesture kinds are this app's actual menu bodies, E-MENU/E-CALLBACKS.
CONTROLS: Final = {
    "head_up": Control("HeadUp", 0x24, held=True),
    "head_down": Control("HeadDown", 0x25, held=True),
    "foot_up": Control("FootUp", 0x26, held=True),
    "foot_down": Control("FootDown", 0x27, held=True),
    "head_foot_up": Control("HeadAndFootUp", 0x29, held=True),
    "head_foot_down": Control("HeadAndFootDown", 0x2A, held=True),
    "flat": Control("MotorReset", 0x31),
    "memory_1": Control("MemoryPosition1", 0x2E, 0x2B),
    "memory_2": Control("MemoryPosition2", 0x2F, 0x2C),
    "lounge": Control("LoungePosition", 0x59, 0x65),
    "zero_gravity": Control("ZeroGravity", 0x45, 0x66),
}
ACTIONS: Final = {
    key: Action(
        "deviceFunctionItem" + control.label,
        "sustainPress"
        if control.held
        else "shortAndLongPress"
        if control.save is not None
        else "shortPress",
        False,
        False,
        False,
        False,
        control.opcode,
        control.save or 0,
        control.opcode,
    )
    for key, control in CONTROLS.items()
}
CATALOG: Final = Catalog(
    "okimiki",
    "Okimiki",
    WIRE,
    ACTIONS,
    {
        code: CatalogProduct(
            code,
            tuple(CONTROLS)[:7] if product.memory_slots == 0 else tuple(CONTROLS),
            ("lounge",)
            if product.alarm == "single"
            else ("lounge", "zero_gravity", "memory_1", "memory_2")
            if product.alarm == "repeat"
            else (),
            (0,),
            True,
            "circlePanchromatic",
            product.alarm == "repeat",
            "deviceSleepMonitoringNone",
            False,
        )
        for code, product in PRODUCTS.items()
    },
    {},
    record=codec.record,
    reply_gated_menus=True,
    startup=(("", 0), ("deviceFunctionItemCheckClock", 1), ("deviceFunctionItemCheckLight", 1)),
)
TICK_S: Final = 0.1
QUERY_S: Final = 0.3
SAVE_S: Final = 3.0
LIGHT_DELAY_S: Final = 0.2
