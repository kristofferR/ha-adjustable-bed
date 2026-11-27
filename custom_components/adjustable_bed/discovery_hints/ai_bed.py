"""AI Bed app candidates; explicit selection is required on shared names."""

from ._hints import Hint, names

HINTS: tuple[Hint, ...] = (
    names(
        "limos",
        "QRRM",
        "MPE_HJ001",
        "MPE_HJ010",
        "MPE_HJ011",
        "MpeV3B-5",
        "MpeV3L-5",
        "MpeV3B-7",
        "MpeV3L-7",
        "MpeV3B-9",
        "MpeV3L-9",
        bed_types={"ai_bed"},
        anywhere=True,
    ),
)
