"""Separate Nisco and MLILY Supreme app identities over the proven 6E codec.

The accepted catalogs contain the same identifiers. Their declarations, caller
gates and runtime policies remain app-local. A mode is never a physical side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .richmat import RICHMAT_MH, RichmatProfile


@dataclass(frozen=True, slots=True)
class AppProfile:
    app: str
    label: str
    package: str
    version: str
    code: int
    wire: RichmatProfile
    manual_short_models: bool
    diagnostic_results: bool
    normal_mattress: bool
    rewrite_light_timer_mode: bool
    waist_combined_lengths: tuple[int, ...]
    sleep_notify_attempts: int


APPS: Final = {
    "nisco": AppProfile(
        "nisco", "Nisco", "com.richmat.nisco", "1.1.1", 3, RICHMAT_MH["nisco"],
        False, False, False, False, (14, 15, 19), 4,
    ),
    "mlily_supreme": AppProfile(
        "mlily_supreme", "MLILY Supreme", "com.richmat.mlily_supreme", "1.3.1", 5,
        RICHMAT_MH["mlily_supreme"], True, True, True, True, (14, 18, 19), 3,
    ),
}

# Catalog identity only. Presence here grants neither controls nor capabilities.
SURFACE_IDS: Final = (
    "3i", "4i", "4it", "5i", "6brm", "6crm", "6drm", "6erm", "6frm", "6hrm", "6i", "7i", "a0rm",
    "a1rm", "a2rm", "a3rm", "a6rm", "a7rm", "a8rm", "a9rm", "aarm", "abrm", "acrm", "adrm",
    "aerm", "afrm", "agrm", "ahrm", "airm", "ajrm", "akrm", "awrm", "axrm", "b0rm", "b1rm",
    "b2rm", "b3rm", "b4rm", "b5rm", "b6rm", "b6ru", "b7rm", "b8rm", "b8tt", "b9rm", "b9tt",
    "barm", "bbrm", "bcrm", "bdrm", "berm", "bfrm", "bgrm", "bhrm", "birm", "bjrm", "bkrm",
    "blrm", "bmrm", "bnrm", "bprm", "bqrm", "bzrm", "cerm", "cfrm", "cwrm", "cxrm", "d0rm",
    "d1rm", "d2rm", "d4rm", "d5rm", "d6rm", "d7rm", "dfrm", "dgrm", "dnrm", "dzrm", "e1rm",
    "e6rm", "earm", "ebrm", "eerm", "efrm", "ehrm", "elrm", "f0rm", "firm", "fjrm", "frrm",
    "garm", "gmrm", "i0rm", "i1rm", "i2rm", "i3rm", "i4rm", "i5rm", "i6rm", "i7rm", "i8rm",
    "i9rm", "iarm", "ibrm", "icrm", "idrm", "ierm", "ifrm", "igrm", "ihrm", "iirm", "ijrm",
    "ikrm", "ilrm", "imrm", "inrm", "iorm", "iprm", "iqrm", "irrm", "isrm", "m3rm", "m4rm",
    "m5rm", "m6rm", "m7rm", "m9rm", "marm", "mlrm", "mmrm", "mrrm", "o0rm", "o1rm", "o2rm",
    "o3rm", "o4rm", "o5rm", "o6rm", "o7rm", "o8rm", "o9rm", "oarm", "omrm", "onrm", "oorm",
    "oqrm", "orrm", "osrm", "otrm", "ourm", "ovrm", "owrm", "oxrm", "oyrm", "ozrm", "p0rm",
    "p1rm", "p2rm", "p3rm", "p4rm", "p5rm", "p6rm", "p9rm", "qrrm", "r2rm", "r5rm", "r6rm",
    "s9rm", "sarm", "t0rm", "t1rm", "t2rm", "t3rm", "t4rm", "t5rm", "t6rm", "t7rm", "t8rm",
    "t9rm", "tarm", "tbrm", "thrm", "tlrm", "twrm", "tzrm", "u0rm", "u1rm", "u2rm", "u3rm",
    "u4rm", "u5rm", "u6rm", "u7rm", "u8rm", "u9rm", "uarm", "ucrm", "udrm", "uerm", "ufrm",
    "ugrm", "uhrm", "uirm", "ujrm", "ukrm", "ulrm", "umrm", "unrm", "uorm", "uprm", "uqrm",
    "urrm", "utrm", "uurm", "uvrm", "uwrm", "uxrm", "uyrm", "uzrm", "v0rm", "v1rm", "v2rm",
    "v3rm", "v4rm", "v5rm", "v6rm", "v7rm", "v8rm", "v9rm", "varm", "vbrm", "vcrm", "vdrm",
    "verm", "vfrm", "vgrm", "vhrm", "virm", "vjrm", "vkrm", "vlrm", "vmrm", "vnrm", "vorm",
    "vprm", "vqrm", "vrrm", "vsrm", "vtrm", "vurm", "vvrm", "vwrm", "vxrm", "vyrm", "vzrm",
    "w0rm", "w1rm", "w2rm", "w3rm", "w4rm", "w5rm", "w6rm", "w7rm", "w8rm", "w9rm", "warm",
    "wbrm", "wcrm", "wdrm", "werm", "wgrm", "whrm", "wirm", "wjrm", "wkrm", "wlrm", "wmrm",
    "wnrm", "worm", "wprm", "wqrm", "wrrm", "wsrm", "wtrm", "wurm", "wvrm", "wwrm", "wxrm",
    "wyrm", "wzrm", "x1rm", "x2rm", "xcrm", "xfrm", "xgrm", "xlrm", "y0rm", "y1rm", "y2rm",
    "y3rm", "y4rm", "y5rm", "y6rm", "y7rm", "y8rm", "y9rm", "yarm", "ybrm", "ycrm", "ydrm",
    "yerm", "yfrm", "ygrm", "yhrm", "yirm", "yjrm", "ykrm", "ymrm", "ynrm", "yorm", "yprm",
    "zqrm", "zr00", "zr01", "zr10", "zr11", "zr12", "zr20", "zr21", "zr30", "zr40", "zr50",
    "zr51", "zr60", "zr70", "zr80", "zr90", "zra0", "zra1", "zra2", "zri0",
)
SHORT_IDS: Final = frozenset({"3i", "4i", "4it", "5i", "6i", "7i"})
NAMED_MODELS: Final = {
    "a7rm": "BT2000", "t3rm": "BT2500", "ufrm": "BT3000 / BT3000FH",
    "vcrm": "BT4000", "vfrm": "BT6500", "u5rm": "BT7000",
}


def models(app: str) -> tuple[str, ...]:
    profile = APPS[app]
    return tuple(
        model for model in SURFACE_IDS
        if model != "qrrm" and (profile.manual_short_models or model not in SHORT_IDS)
    )


def variants(app: str) -> dict[str, str]:
    choices = {
        "auto": "Model from the Bluetooth name (first four characters)",
        **{f"model_{model}": NAMED_MODELS.get(model, model.upper()) for model in models(app)},
    }
    if APPS[app].normal_mattress:
        choices.update({
            f"model_{model}_mattress": f"{NAMED_MODELS.get(model, model.upper())} with normal mattress"
            for model in models(app)
        })
    return choices
