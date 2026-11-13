"""The brand groups behind setup's "Which brand is on the bed?" list.

Each group lists its brand's routes as bed-type list choices. The brand list
shows a group's family rows, or the group's own rows when it has no family
question. Labels come from the bed-type list itself.
"""

from __future__ import annotations

from typing import Final

from .beds.ruf_richmat.profiles import DISPLAY_NAMES as RUF_RICHMAT_DISPLAY_NAMES
from .const import (
    BED_TYPE_ADJUSTABLE_BED,
    BED_TYPE_ADJUSTABLE_LUMBAR,
    BED_TYPE_BEDTECH,
    BED_TYPE_COMFORT_MOTION,
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_GLIDEAWAY_MOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GMMOTOR_SLEEP_MM,
    BED_TYPE_GMMOTOR_SLEEP_SXB,
    BED_TYPE_ISLEEP,
    BED_TYPE_JIECANG,
    BED_TYPE_JIECANG_APP,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_GEN2,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LEGGETT_WILINKE,
    BED_TYPE_LIMOSS,
    BED_TYPE_LINAK,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MOTOSLEEP,
    BED_TYPE_OCTO,
    BED_TYPE_OKIN_7BYTE,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_OKIN_CB35,
    BED_TYPE_OKIN_CST,
    BED_TYPE_OKIN_FFE,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_NORDIC,
    BED_TYPE_OKIN_ORE,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_RICHMAT,
    BED_TYPE_RICHMAT_BEST_MATTRESS,
    BED_TYPE_RICHMAT_BLVD_HOME,
    BED_TYPE_RICHMAT_HARMONY,
    BED_TYPE_RICHMAT_IDEALBED,
    BED_TYPE_RICHMAT_REVIVE,
    BED_TYPE_RIZE,
    BED_TYPE_SERENITY,
    BED_TYPE_SIMMONS,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SOLACE,
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_ABM5_4,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_STARCODE_M5X5,
    BED_TYPE_SVANE,
    BED_TYPE_TRANQUIL,
    BED_TYPE_ZSERIES,
    GLIDEAWAY_MOTION_MODELS,
    KAIDI_VARIANT_FLOYD,
    KEESON_VARIANT_ADJUSTABLE_LITE,
    KEESON_VARIANT_AMERICANSTAR,
    KEESON_VARIANT_AVANTI_BASES,
    KEESON_VARIANT_BASE,
    KEESON_VARIANT_BEDSENSE_BASES,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_HEAL_EVERY_NIGHT,
    KEESON_VARIANT_INNOVA,
    KEESON_VARIANT_KSBT,
    KEESON_VARIANT_MAXCOIL_UNA,
    KEESON_VARIANT_OKIN_SEATING,
    KEESON_VARIANT_PURPLE,
    KEESON_VARIANT_RESTONIC_A,
    KEESON_VARIANT_RESTONIC_B,
    KEESON_VARIANT_SERTA,
    KEESON_VARIANT_SIMON_LI,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    ZSERIES_VARIANT_Z230,
    ZSERIES_VARIANT_Z280,
)

# A route: a bed type, and the app variant its own row selects.
Route = tuple[str, str | None]

# Groups are in alphabetical order by key.
ACTUATOR_GROUPS: Final[dict[str, tuple[Route, ...]]] = {
    "starcode_abm5_4": (
        (BED_TYPE_STARCODE_ABM5_4, None),
        (BED_TYPE_STARCODE_M5X5, None),
        (BED_TYPE_STARCODE_M1X12, None),
    ),
    "glideaway_motion": tuple(
        (BED_TYPE_GLIDEAWAY_MOTION, model) for model, label in GLIDEAWAY_MOTION_MODELS.items()
    ),
    "bedtech": ((BED_TYPE_BEDTECH, None),),
    "comfort_motion": ((BED_TYPE_COMFORT_MOTION, None),),
    "customatic": (
        (BED_TYPE_CUSTOMATIC_CLARITY, None),
        (BED_TYPE_CUSTOMATIC_JEROMES, None),
        (BED_TYPE_CUSTOMATIC_REMEDY, None),
        (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z230),
        (BED_TYPE_ZSERIES, ZSERIES_VARIANT_Z280),
    ),
    "ergomotion": ((BED_TYPE_ERGOMOTION, None),),
    "gmmotor": (
        (BED_TYPE_GMMOTOR, None),
        (BED_TYPE_GMMOTOR_SLEEP_MM, None),
        (BED_TYPE_GMMOTOR_SLEEP_SXB, None),
    ),
    "jensen": ((BED_TYPE_SVANE, None),),
    "jiecang": (
        (BED_TYPE_JIECANG, None),
        (BED_TYPE_JIECANG_APP, None),
    ),
    "kaidi": (
        (BED_TYPE_KAIDI, None),
        (BED_TYPE_KAIDI, KAIDI_VARIANT_FLOYD),
        (BED_TYPE_ISLEEP, None),
        (BED_TYPE_RIZE, None),
    ),
    "keeson": (
        (BED_TYPE_KEESON, KEESON_VARIANT_BASE),
        (BED_TYPE_KEESON, KEESON_VARIANT_KSBT),
        (BED_TYPE_KEESON, KEESON_VARIANT_ADJUSTABLE_LITE),
        (BED_TYPE_KEESON, KEESON_VARIANT_SIMON_LI),
        (BED_TYPE_KEESON, KEESON_VARIANT_HEAL_EVERY_NIGHT),
        (BED_TYPE_KEESON, KEESON_VARIANT_OKIN_SEATING),
        (BED_TYPE_KEESON, KEESON_VARIANT_AVANTI_BASES),
        (BED_TYPE_KEESON, KEESON_VARIANT_AMERICANSTAR),
        (BED_TYPE_KEESON, KEESON_VARIANT_BEDSENSE_BASES),
        (BED_TYPE_KEESON, KEESON_VARIANT_INNOVA),
        (BED_TYPE_KEESON, KEESON_VARIANT_MAXCOIL_UNA),
        (BED_TYPE_KEESON, KEESON_VARIANT_DYNASTY_BASES),
        (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_A),
        (BED_TYPE_KEESON, KEESON_VARIANT_RESTONIC_B),
        (BED_TYPE_KEESON, KEESON_VARIANT_SERTA),
        (BED_TYPE_KEESON, KEESON_VARIANT_PURPLE),
    ),
    "leggett": (
        (BED_TYPE_LEGGETT_GEN2, None),
        (BED_TYPE_LEGGETT_OKIN, None),
        (BED_TYPE_LEGGETT_WILINKE, None),
    ),
    "linak": ((BED_TYPE_LINAK, None),),
    "limoss": ((BED_TYPE_LIMOSS, None),),
    "malouf": ((BED_TYPE_MALOUF_APP, None),),
    "logicdata": ((BED_TYPE_LOGICDATA_APP, None),),
    "motosleep": ((BED_TYPE_MOTOSLEEP, None),),
    "octo": ((BED_TYPE_OCTO, None),),
    "okin": (
        ("smart_sleep", None),
        (BED_TYPE_OKIN_HANDLE, None),
        (BED_TYPE_OKIN_UUID, None),
        (BED_TYPE_OKIN_7BYTE, None),
        (BED_TYPE_OKIN_CST, None),
        (BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE),
        (BED_TYPE_OKIN_NORDIC, None),
        (BED_TYPE_FURNIMOVE, None),
        (BED_TYPE_SERENITY, None),
        (BED_TYPE_TRANQUIL, None),
        (BED_TYPE_SIMMONS, None),
        (BED_TYPE_ADJUSTABLE_BED, None),
        (BED_TYPE_ADJUSTABLE_LUMBAR, None),
        (BED_TYPE_OKIN_FFE, None),
        (BED_TYPE_OKIN_64BIT, None),
        (BED_TYPE_OKIN_CB24, None),
        (BED_TYPE_OKIN_CB35, None),
        (BED_TYPE_OKIN_ORE, None),
        (BED_TYPE_OKIN_RF_ECO_BT, None),
        (BED_TYPE_STARCODE_M5X5, None),
        (BED_TYPE_STAR_ELEVATE, None),
    ),
    "reverie": ((BED_TYPE_REVERIE_NIGHTSTAND, None),),
    "richmat": ((BED_TYPE_RICHMAT, None),),
    "richmat_apps": (
        *((bed_type, None) for bed_type in RUF_RICHMAT_DISPLAY_NAMES),
        *(("richmat_sleep_receiver", app) for app in ("wsilver2", "americanstar", "bailey2", "tx")),
        (BED_TYPE_RICHMAT_REVIVE, None),
        (BED_TYPE_RICHMAT_BEST_MATTRESS, None),
        (BED_TYPE_RICHMAT_BLVD_HOME, None),
        (BED_TYPE_RICHMAT_HARMONY, None),
        (BED_TYPE_RICHMAT_IDEALBED, None),
    ),
    "sleepys": ((BED_TYPE_SLEEPYS_ELITE_APP, None),),
    "solace": ((BED_TYPE_SOLACE, None),),
}


def actuator_group_for(bed_type: str) -> str | None:
    """Return the brand group a bed type belongs to, if any."""
    return next(
        (
            key
            for key, routes in ACTUATOR_GROUPS.items()
            if any(route_bed_type == bed_type for route_bed_type, _variant in routes)
        ),
        None,
    )
