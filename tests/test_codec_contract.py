"""Every bed type is a profile over a wire codec, or a listed exception (#742, #746).

A route is codec-backed when its controller's ``profile`` is the profile class
of a registered codec family and has frozen vectors in that family's harness.
Every other bed type is listed in ``UNMIGRATED`` with its #745 family or the
reason it stays a standalone controller. Each app-profile choice of a
codec-backed bed type is checked separately, so a new app cannot reach that
bed type through its own controller. When a family moves onto a codec, register
it here and delete its entries; the test fails until you do.
"""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.jiecang import JiecangProfile
from custom_components.adjustable_bed.profiles.richmat import RichmatProfile
from tests.jiecang_vectors import FROZEN_FRAMES as JIECANG_VECTORS
from tests.richmat_vectors import FROZEN_FRAMES as RICHMAT_VECTORS
from tests.test_controller_contract import (
    _create_controller_for_bed_type,
    _FactoryCoordinator,
    _make_connected_client,
)

# Codec families: profile class -> frozen vectors by profile key.
CODEC_FAMILIES: dict[type, dict[str, frozenset[str]]] = {
    JiecangProfile: JIECANG_VECTORS,
    RichmatProfile: RICHMAT_VECTORS,
}

# App choices of codec-backed bed types: bed type -> (config key, choices).
APP_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    const.BED_TYPE_JIECANG_APP: (const.CONF_JIECANG_APP_PROFILE, tuple(const.JIECANG_APP_PROFILES)),
}

UNMIGRATED: dict[str, str] = {
    "adjustable_lumbar": "#745 O1 Okin N-frame",
    "adjustamattress": "#745 K1 Keeson E5/E6",
    "bedsense": "#745 S1 FFFF",
    "bf": "#745 K1 Keeson E5/E6",
    "casper_base": "standalone: own wire format",
    "casper_remote": "standalone: remote without bed commands",
    "casper_sleep_mm": "standalone: sleep sensor without bed commands",
    "casper_sleep_sxb": "standalone: sleep sensor without bed commands",
    "cherish": "#745 K1 Keeson E5/E6",
    "comfort_enhancements": "#745 K1 Keeson E5/E6",
    "coolbase": "#745 K1 Keeson E5/E6",
    "customatic_clarity": "#745 O1 Okin N-frame",
    "customatic_jeromes": "#745 O1 Okin N-frame",
    "customatic_remedy": "#745 O1 Okin N-frame",
    "customatic_zseries": "#745 O1 Okin N-frame",
    "dewertokin": "#745 O1 Okin N-frame",
    "doublesleep": "#745 O1 Okin N-frame",
    "ergo_slim": "#745 K1 Keeson E5/E6",
    "ergomotion": "#745 K1 Keeson E5/E6",
    "ergomotion_app": "#745 K1 Keeson E5/E6",
    "eshine": "standalone: own wire format",
    "fsm_relax": "#745 L1 Limoss DD",
    "furnimove": "#745 K1 Keeson E5/E6",
    "glideaway_motion": "#745 K1 Keeson E5/E6",
    "gmmotor": "#745 R1 Richmat 6E: frames use codec/richmat.py, catalog session stays",
    "gmmotor_sleep_mm": "standalone: sleep sensor without bed commands",
    "gmmotor_sleep_sxb": "standalone: sleep sensor without bed commands",
    "isleep": "standalone: Kaidi mesh frames",
    "jensen": "standalone: own wire format",
    "kaidi": "standalone: Kaidi mesh frames",
    "keeson": "#745 K1 Keeson E5/E6",
    "leggett_gen2": "standalone: own wire format",
    "leggett_lp_legacy": "standalone: own wire format",
    "leggett_okin": "#745 O1 Okin N-frame",
    "leggett_platt": "#745 O1 Okin N-frame",
    "limoss": "#745 L1 Limoss DD",
    "limoss_remote": "#745 L1 Limoss DD",
    "linak": "standalone: own wire format",
    "logicdata": "standalone: own wire format",
    "logicdata_air_pump": "standalone: own wire format",
    "logicdata_app": "#745 J1 LOGICDATA",
    "malouf_app": "#745 O2 Okin 5A, Okin-like Malouf frames",
    "malouf_legacy_okin": "#745 K1 Keeson E5/E6",
    "malouf_new_okin": "#745 O2 Okin 5A, Okin-like Malouf frames",
    "mattressfirm": "#745 O2 Okin 5A",
    "motion_bed": "#745 S1 FFFF",
    "motosleep": "standalone: own wire format",
    "nectar": "#745 O2 Okin 5A",
    "octo": "standalone: own wire format",
    "okimat": "#745 O1 Okin N-frame",
    "okin_64bit": "#745 O1 Okin N-frame",
    "okin_7byte": "#745 O2 Okin 5A",
    "okin_cb24": "#745 O1 Okin N-frame",
    "okin_cb35": "#745 O2 Okin 5A",
    "okin_cst": "#745 O1 Okin N-frame",
    "okin_dot": "#745 O1 Okin N-frame",
    "okin_ffe": "#745 K1 Keeson E5/E6",
    "okin_handle": "#745 O1 Okin N-frame",
    "okin_nordic": "#745 O2 Okin 5A",
    "okin_ore": "standalone: own wire format",
    "okin_rf_eco_bt": "#745 O1 Okin N-frame",
    "okin_uuid": "#745 O1 Okin N-frame",
    "omazz_adjusto_iii": "#745 K1 Keeson E5/E6",
    "qplus_app": "#745 K1 Keeson E5/E6",
    "remacro": "standalone: own wire format",
    "reverie": "standalone: own wire format",
    "reverie_nightstand": "standalone: own wire format",
    "reverie_pairlink": "standalone: own wire format behind a Pairlink session",
    "rondure": "#745 K1 Keeson E5/E6",
    "row_control": "#745 K1 Keeson E5/E6",
    "sbi": "#745 K1 Keeson E5/E6",
    "scott_living": "#745 K1 Keeson E5/E6",
    "serenity": "#745 O1 Okin N-frame",
    "serta": "#745 K1 Keeson E5/E6",
    "serta_mp_remote": "#745 K1 Keeson E5/E6",
    "simmons": "#745 O1 Okin N-frame",
    "sleep_number": "standalone: own wire format",
    "sleep_number_mcr": "standalone: own wire format",
    "sleepstar": "standalone: own wire format",
    "sleeptracker": "standalone: own wire format",
    "sleepys_box15": "#745 K1 Keeson E5/E6",
    "sleepys_box24": "standalone: own wire format",
    "sleepys_box25": "#745 O1 Okin N-frame",
    "sleepys_elite_app": "standalone: own wire format",
    "solace": "#745 S1 FFFF",
    "star_elevate": "#745 O2 Okin 5A",
    "starcode_abm5_4": "#745 O1 Okin N-frame",
    "starcode_m1x12": "standalone: own wire format",
    "starcode_m5x5": "standalone: own wire format",
    "suta": "standalone: own wire format",
    "svane": "standalone: own wire format",
    "tempur_au": "#745 K1 Keeson E5/E6",
    "tempur_curve": "#745 K1 Keeson E5/E6",
    "timotion_ahf": "standalone: own wire format",
    "tranquil": "#745 O1 Okin N-frame",
    "vibradorm": "standalone: own wire format",
    "vibradorm_app": "standalone: own wire format",
    "vmatbasic": "standalone: own wire format",
}


def _codec_profile_key(controller: BedController) -> str | None:
    """Return the profile key when the controller is a profile over a codec."""
    profile = getattr(controller, "profile", None)
    vectors = CODEC_FAMILIES.get(type(profile))
    key = getattr(profile, "key", None)
    return key if vectors is not None and key in vectors else None


def test_unmigrated_entries_are_supported_and_explained() -> None:
    assert set(UNMIGRATED) <= set(SUPPORTED_BED_TYPES)
    assert not set(UNMIGRATED) & set(APP_ROUTES)
    for bed_type, reason in UNMIGRATED.items():
        assert reason.startswith(("#745 ", "standalone: ")), bed_type


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_bed_type_is_a_profile_over_a_codec_or_listed(bed_type: str) -> None:
    controller = await _create_controller_for_bed_type(bed_type)
    codec_backed = _codec_profile_key(controller) is not None
    if bed_type in UNMIGRATED:
        assert not codec_backed, f"{bed_type} uses a codec profile; remove it from UNMIGRATED"
    else:
        assert codec_backed, f"{bed_type} needs a codec profile or an UNMIGRATED reason"


@pytest.mark.parametrize(
    ("bed_type", "choice"),
    [(bed_type, choice) for bed_type, (_, choices) in APP_ROUTES.items() for choice in choices],
)
async def test_every_app_choice_is_a_profile_over_a_codec(bed_type: str, choice: str) -> None:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[APP_ROUTES[bed_type][0]] = choice
    controller = await create_controller(
        coordinator, bed_type, VARIANT_AUTO, _make_connected_client()
    )
    assert _codec_profile_key(controller) == choice
