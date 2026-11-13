"""Every execution-capability declaration needs reviewed evidence (#483, #516).

``EVIDENCE`` maps each bed type or family profile that declares a capability
to the keys proving it, per declared field. Keys are defined in the
"Evidence keys" section of ``docs/design/execution-capabilities.md``. A
declaration without a row fails here, so adding a capability needs a reviewed
evidence row, and a row whose declaration is gone fails too.

Profiles are identified as ``"<ProfileClass>:<key>"``; standalone controllers
by bed type. Runtime checks cover every bed type and app route; a source scan
also requires each place that declares a capability to be listed in
``DECLARATION_SITES``, so variants, layouts and runtime-built profiles cannot
declare one unreviewed.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.ergomotion4.profiles import (
    PRODUCTS as ERGOMOTION_4_PRODUCTS,
)
from custom_components.adjustable_bed.const import (
    ESHINE_OKIN_PROFILES,
    SUPPORTED_BED_TYPES,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from custom_components.adjustable_bed.profiles import keeson as keeson_profiles
from custom_components.adjustable_bed.profiles import vibradorm as vibradorm_profiles
from tests.codec_families import families
from tests.test_controller_contract import (
    _create_controller_for_bed_type,
    _FactoryCoordinator,
    _make_connected_client,
)

FAMILIES = families()
APP_ROUTES = {
    bed_type: route for family in FAMILIES.values() for bed_type, route in family.app_routes.items()
}
DESIGN = Path(__file__).parents[1] / "docs" / "design" / "execution-capabilities.md"

# Keeson E5/E6 (K1) profiles with stream evidence, by profile key. The base,
# OKIN, Sino, KSBT CR, OKIN FFE, Sleepy's Box15, Rondure and Scott Living routes
# are blocked and declare nothing.
KEESON_STREAM: dict[str, tuple[str, ...]] = {
    "jalon_bed": ("jalon",),
    "ergomotion": ("sfdergo",),
    "serta": ("serta330",),
    "restonic_a": ("restonic",),
    "restonic_b": ("restonic",),
    "innova": ("sfm",),
    "bedsense_bases": ("sfmc2",),
    "avanti_bases": ("avanti",),
    "dynasty_bases": ("dynasty",),
    "maxcoil_una": ("maxcoil",),
    "americanstar": ("americanstar",),
    "okin_comfort_bed": ("okincomfort",),
    "simon_li": ("simon",),
    "heal_every_night": ("heal",),
    "okin_seating": ("minghua",),
    "adjustable_lite": ("adjlite",),
    "adjustable_lite_ksbt03c": ("adjlite",),
    "ksbt": ("hump",),
    "ksbt03c": ("mancini",),
    "sbi": ("costco",),
    "coolbase": ("coolbase",),
    "bf": ("bf",),
    "cherish": ("cherish",),
    "comfort_enhancements": ("enh",),
    "jalon_13": ("row132",),
    "jalon_15": ("row132",),
    "jalon_24": ("row132",),
    "comfortbase": ("row161",),
    "glideaway_motion": ("glide",),
    # Malouf's legacy OKIN route over the E6 frame (row023).
    "malouf_legacy_okin": ("malouf", "row023"),
    "adjustamattress": ("row067",),
    "adjustamattress_p2": ("row067",),
}
# Keeson layout app layouts, and Ergomotion 4.0 per catalog product style.
KEESON_APP_STREAM: dict[str, tuple[str, ...]] = {
    "tempur_curve": ("tempur",),
    "qplus_app": ("costco",),
    "serta_mp_remote": ("serta330",),
    "omazz_adjusto_iii": ("omazz",),
    "ergomotion_app": ("sfdergo",),
    "row_control": ("row",),
    "ergo_slim": ("slim",),
    "tempur_au": ("tempur_au",),
}
ERGOMOTION_4_STYLES = frozenset(product.style for product in ERGOMOTION_4_PRODUCTS.values())

# Declaration -> declared field -> evidence keys from the design document.
EVIDENCE: dict[str, Mapping[str, tuple[str, ...]]] = {
    "SmartSleepProfile:p1": {"hold": ("row094",)},
    "SmartSleepProfile:p2": {"hold": ("row094",), "hold_controls": ("row094",)},
    **{f"OkinNFrameProfile:apex_{i}": {"hold": ("row083",)} for i in range(15)},
    "ParamountProfile:paramount": {"hold": ("paramount",)},
    **{f"AdjustableAppProfile:{key}": {"hold": ("adjustbed",)}
       for key in ("adjustable_bed_okin", "adjustable_bed_star", "adjustable_bed_star_5a")},
    "SmartComfortProfile:synargy": {"hold": ("smart-comfort-synargy",)},
    "SmartComfortProfile:synergy": {"hold": ("smart-comfort-synergy",)},
    **{f"LuunaProfile:{key}": {"hold": ("luuna",)} for key in ("rise", "risepro", "riseprolight")},
    # Rows sort by identity, so parallel declarations merge cleanly.
    # Keeson layout apps and Ergomotion 4.0 (#483) stream a held key.
    **{
        f"AppProfile:{app}@{layout}": {"hold": KEESON_APP_STREAM[app]}
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    },
    **{
        f"AppProfile:ergomotion_4@{style}": {"hold": ("hump", "issue558")}
        for style in ERGOMOTION_4_STYLES
    },
    # Latched (FFFF frame): one start, STOP at release.
    "BedSenseProfile:bedsense": {"hold": ("bedsense",)},
    # Jiecang F1: Comfort Motion (jcbed PARTIAL) and the legacy route stay blocked.
    "JiecangProfile:dreamask": {"hold": ("dreamask",)},
    "JiecangProfile:dreamhd": {"hold": ("dreamhd",)},
    "JiecangProfile:dreamotion": {"hold": ("dreamotion",)},
    # Keeson E5/E6 (#483): the K1 profiles that stream a held key.
    **{f"KeesonProfile:{key}": {"hold": keys} for key, keys in KEESON_STREAM.items()},
    # Limoss DD (L1). The legacy ``limoss`` route keeps finite pulses: its
    # cadence is the entry's pulse settings, not the app's.
    "LimossProfile:fsm_relax": {"hold": ("fsm",)},
    "LimossProfile:limoss_remote": {"hold": ("limoss",)},
    "LogicdataProfile:phone": {"hold": ("ld-phone",)},
    "LogicdataProfile:sleep_smart": {"hold": ("ld-mattress",)},
    "LogicdataProfile:tablet": {"hold": ("ld-pad",)},
    # Malouf / Lucid (#483, row023).
    "MaloufAppProfile:lucid": {"hold": ("lucid", "row023")},
    "MaloufAppProfile:malouf": {"hold": ("malouf", "row023")},
    "MaloufRouteProfile:malouf_new_okin": {"hold": ("lucid", "malouf", "row023")},
    # Okin 5A (O2). Nectar and MF900 evidence reaches the Okin CST frame, not
    # the 5A keys those profiles send, so only ELEVATE declares.
    "Okin5AProfile:star_elevate": {"hold": ("abm5_5", "m1x12")},
    # Okin N-frame (#483): each app streams a held key until release. Nectar
    # Move is the Nectar app's CST route; Prodigy CE and U Series also compose (#516).
    "RizeHomeProfile:rize_home_remedy_iii": {"hold": ("rize-home",)},
    "RizeHomeProfile:rize_home_contempo_iv": {"hold": ("rize-home",)},
    "OkinNFrameProfile:okin_motionbed": {"hold": ("row150",)},
    "OkinNFrameProfile:resident": {"hold": ("resident-base",)},
    "OkinNFrameProfile:adjustable_lumbar_okin": {"hold": ("lumbar",)},
    "OkinNFrameProfile:adjustable_lumbar_star": {"hold": ("lumbar",)},
    # Customatic: held motor keys OR into one shared mask; a release clears one bit (#516).
    "OkinNFrameProfile:clarity": {
        "hold": ("clarity", "row028"),
        "concurrent": ("clarity", "row028"),
    },
    "OkinNFrameProfile:cst_aviada": {"hold": ("aviada",)},
    "OkinNFrameProfile:cst_bob": {"hold": ("bob",)},
    "OkinNFrameProfile:cst_carefree": {"hold": ("carefree",)},
    "OkinNFrameProfile:cst_clarity": {"hold": ("iiclarity",)},
    "OkinNFrameProfile:cst_contempo": {"hold": ("contempo",)},
    "OkinNFrameProfile:cst_mf900": {"hold": ("mf900",)},
    "OkinNFrameProfile:cst_nectar_move": {"hold": ("nectar", "row042")},
    "OkinNFrameProfile:cst_resident": {"hold": ("resident",)},
    "OkinNFrameProfile:cst_sanctuary": {"hold": ("sanctuary",)},
    "OkinNFrameProfile:cst_support": {"hold": ("support",)},
    "OkinNFrameProfile:eshine_e2000": {"hold": ("eshine-okin",)},
    "OkinNFrameProfile:eshine_e30003100": {"hold": ("eshine-okin",)},
    "OkinNFrameProfile:eshine_e5000": {"hold": ("eshine-okin",)},
    "OkinNFrameProfile:jeromes": {
        "hold": ("jeromes", "row028"),
        "concurrent": ("jeromes", "row028"),
    },
    "OkinNFrameProfile:prodigy2": {"hold": ("p2", "leggett-disp")},
    "OkinNFrameProfile:prodigy2l": {"hold": ("p2l", "leggett-disp")},
    "OkinNFrameProfile:prodigy4": {
        "hold": ("p4", "leggett-disp", "#483c"),
        # CU170 watchdog onset measured on hardware: 217-218 ms.
        "sustain_ms": ("#368", "#483c", "#516c"),
        # Normal keys combine by OR; release removes one key (#516).
        "concurrent": ("p4", "#516c"),
    },
    "OkinNFrameProfile:remedy": {
        "hold": ("remedy", "row028"),
        "concurrent": ("remedy", "row028"),
    },
    "OkinNFrameProfile:serenity": {"hold": ("serenity",)},
    "OkinNFrameProfile:simmons_okin": {"hold": ("simmons",)},
    "OkinNFrameProfile:simmons_smartbed": {"hold": ("simmons",)},
    "OkinNFrameProfile:starcode_abm5_4": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box1220": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box15": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box25": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:starcode_abm5_4_box3633": {"hold": ("abm5_4",)},
    "OkinNFrameProfile:rize_remedy_ii": {"hold": ("rize-remedy-ii", "row180")},
    "OkinNFrameProfile:tranquil": {"hold": ("tranquil",)},
    "OkinNFrameProfile:useries": {
        "hold": ("useries", "leggett-disp"),
        # The output thread's accumulator ORs keys; ACTION_UP removes one.
        "concurrent": ("useries",),
    },
    "OkinNFrameProfile:zseries_z230": {"hold": ("glory",)},
    "OkinNFrameProfile:zseries_z280": {"hold": ("glory",)},
    # Richmat 6E (#483): explicit BedTech 7.1.3 models end refresh with no release.
    **{f"RichmatProfile:bedtech_{model}": {"hold": ("bedtech713",)}
       for model in ("bt2000", "bt2500", "bt3000", "bt3000fh", "bt6500", "btx4", "btx4fh", "btx5", "btx5fh")},
    "RichmatProfile:eshine": {"hold": ("eshine",)},
    "RichmatProfile:hjbed": {"hold": ("row121",)},
    "RichmatProfile:richmat_app": {"hold": ("row173",)},
    "RichmatProfile:leggett_wilinke": {"hold": ("lp2",)},
    "RichmatProfile:richmat_mh_best_mattress": {"hold": ("best", "row055")},
    "RichmatProfile:richmat_mh_blvd_home": {"hold": ("blvd", "row055")},
    "RichmatProfile:richmat_mh_harmony": {"hold": ("harmony", "row055")},
    "RichmatProfile:richmat_mh_idealbed": {"hold": ("ideal", "row055")},
    "RichmatProfile:richmat_mh_revive": {"hold": ("revive", "row055")},
    # The RUF and Richmat apps reuse the MH library's KEEP stream and app-specific release.
    "RichmatProfile:richmat_mh_americanstar": {"hold": ("rmamericanstar", "row061")},
    "RichmatProfile:richmat_mh_bailey2": {"hold": ("bailey", "row061")},
    "RichmatProfile:richmat_mh_ruf": {"hold": ("ruf", "row061")},
    "RichmatProfile:richmat_mh_tx": {"hold": ("tx", "row061")},
    "RichmatProfile:richmat_mh_wsilver2": {"hold": ("wsilver", "row061")},
    "RichmatProfile:richmat_nordic": {"hold": ("rmc2",)},
    "RichmatProfile:richmat_prefix55": {"hold": ("rmc2",)},
    "RichmatProfile:richmat_prefixaa": {"hold": ("rmc2",)},
    "RichmatProfile:richmat_wilinke": {"hold": ("rmc2",)},
    # Latched Solace routes. S4-Y and unidentified entries have no report, and
    # Motion Bed has no route a lease could renew.
    "SolaceProfile:common": {"hold": ("homekobo", "dianqi")},
    "SolaceProfile:home_k1": {"hold": ("homekobo",)},
    "SolaceProfile:home_k2": {"hold": ("homekobo",)},
    "SolaceProfile:motion_flex": {"hold": ("motionflex",)},
    "SolaceProfile:woosa": {"hold": ("woosa",)},
    # Standalone controllers. Stream holds need stream evidence; latched holds
    # (#821) a latched row. The generic ``vibradorm`` route keeps finite pulses
    # and ``leggett_lp_legacy`` is not declared yet (see the design note). Svane
    # Remote declares hold and composition on its controller (#516), and Sleepy's
    # BOX25 declares on the controller for both dialects.
    "furnimove": {"hold": ("fm157",)},
    # Scoped to held controls whose effective gesture is a sustained press:
    # short, long and short-and-long gestures and memory mode keep theirs.
    "galaxy": {"hold": ("galaxy",), "hold_controls": ("galaxy",)},
    "goodvibe": {"hold": ("goodvibe",), "hold_controls": ("goodvibe",)},
    "mlily": {"hold": ("mlily159",), "hold_controls": ("mlily159",)},
    # Scoped to the held controls that run the keep mode under the current
    # Hold/Release, memory-arm and head/foot selection (row066, five reports).
    "richmat_classic_apps": {
        "hold": ("avocado", "coaster", "fortywinks", "milemont", "superior", "row066"),
        "hold_controls": ("avocado", "coaster", "fortywinks", "milemont", "superior", "row066"),
    },
    "isleep": {"hold": ("kaidi",)},
    "ComfyProfile:komfyd": {"hold": ("komfyd084",)},
    "ComfyDSProfile:comfyds": {"hold": ("comfyds084",)},
    "RizeProfile:rize": {"hold": ("rize149",)},  # latched
    "jensen": {"hold": ("jensen", "jensen-disp")},
    # Latched; Floyd (no report) and dual-seat beds stay finite.
    "kaidi": {"hold": ("kaidi",)},
    "leggett_gen2": {"hold": ("universal",)},
    "linak": {"hold": ("linak-iot", "linak-lp", "linak-mem", "linak-guide")},
    "octo": {"hold": ("octo",)},
    "remacro": {"hold": ("brick", "jewmes", "slumber", "row050")},  # latched
    "reverie": {"hold": ("reverie", "row041")},  # latched
    "sleepys_box25": {"hold": ("sleepy",)},
    "sleepys_elite_app": {"hold": ("sleepy",)},
    "starcode_m1x12": {"hold": ("m1x12",)},
    "starcode_m5x5": {"hold": ("abm5_5",)},
    # The Svane Remote routes, and the Jensen LinOn route's hold (jensen_linon).
    "svane": {
        "hold": ("svane", "svane-guide", "jensen", "jensen-disp"),
        "concurrent": ("svane", "svane-guide"),
    },
    "timotion_ahf": {"hold": ("ahf",)},
    "vibradorm_app": {"hold": ("diamant", "werkmeister", "vmat")},
    "vmatbasic": {"hold": ("vmatbasic",)},
}

_ABM = tuple(identity for identity in EVIDENCE if identity.startswith("OkinNFrameProfile:starcode"))
# Okin CST and the OKIN Bedding apps (Serenity, Tranquil, Z-Series) share ``_cst``.
_CST = tuple(
    identity
    for identity in EVIDENCE
    if identity.startswith("OkinNFrameProfile:cst_")
    or identity.removeprefix("OkinNFrameProfile:")
    in ("serenity", "tranquil", "zseries_z230", "zseries_z280", "rize_remedy_ii")
)
_CUSTOMATIC = (
    "OkinNFrameProfile:clarity",
    "OkinNFrameProfile:jeromes",
    "OkinNFrameProfile:remedy",
)
_ESHINE = tuple(f"OkinNFrameProfile:{key}" for key in ESHINE_OKIN_PROFILES)
_LEGGETT_STREAM = ("OkinNFrameProfile:prodigy2", "OkinNFrameProfile:prodigy2l")
_LUMBAR = (
    "OkinNFrameProfile:adjustable_lumbar_okin",
    "OkinNFrameProfile:adjustable_lumbar_star",
)
_SIMMONS = ("OkinNFrameProfile:simmons_okin", "OkinNFrameProfile:simmons_smartbed")

# Source site -> the EVIDENCE identities it declares. A site is
# "<path under custom_components/adjustable_bed>:<enclosing name>". Runtime
# enumeration cannot reach every variant, layout or product, so every place
# that can declare a capability must be listed and reviewed here.
DECLARATION_SITES: dict[str, tuple[str, ...]] = {
    "profiles/smart_sleep.py:<module>.PROFILES": ("SmartSleepProfile:p2",),
    "profiles/smart_sleep.py:<module>.SmartSleepProfile": ("SmartSleepProfile:p1", "SmartSleepProfile:p2"),
    "profiles/comfort_enhancement3.py:<module>.profile": tuple(f"OkinNFrameProfile:apex_{i}" for i in range(15)),
    "profiles/paramount.py:<module>.ParamountProfile": ("ParamountProfile:paramount",),
    **{
        f"profiles/adjustable_bed.py:<module>.{site}": tuple(
            f"AdjustableAppProfile:{key}" for key in
            ("adjustable_bed_okin", "adjustable_bed_star", "adjustable_bed_star_5a")
        ) for site in ("AdjustableAppProfile", "PROFILES")
    },
    "profiles/smart_comfort.py:<module>.SmartComfortProfile": ("SmartComfortProfile:synargy", "SmartComfortProfile:synergy"),
    "profiles/rize_home.py:<module>.RizeHomeProfile": (
        "RizeHomeProfile:rize_home_remedy_iii", "RizeHomeProfile:rize_home_contempo_iv",
    ),
    "profiles/okin_nframe.py:<module>.OKIN_MOTIONBED": ("OkinNFrameProfile:okin_motionbed",),
    "profiles/okin_nframe.py:<module>.RESIDENT": ("OkinNFrameProfile:resident",),
    "profiles/luuna.py:<module>.LuunaProfile": tuple(f"LuunaProfile:{key}" for key in ("rise", "risepro", "riseprolight")),
    "beds/richmat_classic/controller.py:<module>.RichmatClassicController": ("richmat_classic_apps",),
    "beds/richmat_classic/controller.py:<module>.RichmatClassicController.execution": ("richmat_classic_apps",),
    "beds/eshine_okin/controller.py:<module>.EshineOkinController": _ESHINE,
    "beds/furnimove/controller.py:<module>.FurniMoveController": ("furnimove",),
    "beds/furnimove/controller.py:<module>.FurniMoveController.execution": ("furnimove",),
    "beds/goodvibe/controller.py:<module>.GoodVibeController": ("goodvibe", "mlily", "galaxy"),
    "beds/goodvibe/controller.py:<module>.GoodVibeController.execution": ("goodvibe", "mlily", "galaxy"),
    "beds/kaidi/app.py:<module>.KaidiAppController": ("isleep",),
    "profiles/comfy.py:<module>.ComfyProfile": ("ComfyProfile:komfyd", "ComfyDSProfile:comfyds"),
    "beds/kaidi/comfy.py:<module>.ComfyController": ("ComfyProfile:komfyd", "ComfyDSProfile:comfyds"),
    "profiles/kaidi.py:<module>.RizeProfile": ("RizeProfile:rize",),
    "beds/kaidi/rize.py:<module>.RizeController": ("RizeProfile:rize",),
    "beds/kaidi/app.py:<module>.KaidiAppController.execution": ("isleep",),
    "beds/jensen/controller.py:<module>.JensenController": ("jensen",),
    "beds/jensen/controller.py:<module>.JensenController.execution": ("jensen",),
    "beds/kaidi/controller.py:<module>.KaidiController": ("kaidi",),
    "beds/kaidi/controller.py:<module>.KaidiController.execution": ("kaidi",),
    "beds/leggett/gen2.py:<module>.LeggettGen2Controller": ("leggett_gen2",),
    "beds/leggett/gen2.py:<module>.LeggettGen2Controller.execution": ("leggett_gen2",),
    "beds/jensen/linon.py:<module>.JensenLinonController": ("svane",),
    "beds/jensen/linon.py:<module>.JensenLinonController.execution": ("svane",),
    "beds/linak/controller.py:<module>.LinakController": ("linak",),
    "beds/linak/controller.py:<module>.LinakController.execution": ("linak",),
    "beds/octo/controller.py:<module>.OctoController": ("octo",),
    "beds/octo/controller.py:<module>.OctoController.execution": ("octo",),
    "beds/remacro/controller.py:<module>.RemacroController": ("remacro",),
    "beds/remacro/controller.py:<module>.RemacroController.execution": ("remacro",),
    "beds/reverie/controller.py:<module>.ReverieController": ("reverie",),
    "beds/reverie/controller.py:<module>.ReverieController.execution": ("reverie",),
    # RMControl narrows its framing's declaration to sustain-press products.
    "beds/rmcontrol/controller.py:<module>.RmcontrolController": (
        "RichmatProfile:richmat_nordic",
        "RichmatProfile:richmat_wilinke",
    ),
    "beds/sleepys/app.py:<module>.SleepysEliteAppController": ("sleepys_elite_app",),
    "beds/sleepys/app.py:<module>.SleepysEliteAppController.execution": ("sleepys_elite_app",),
    "beds/sleepys/box25.py:<module>.SleepysBox25Controller": ("sleepys_box25",),
    "beds/starcode/m1x12.py:<module>.StarcodeM1X12Controller": ("starcode_m1x12",),
    "beds/starcode/m1x12.py:<module>.StarcodeM1X12Controller.execution": ("starcode_m1x12",),
    "beds/starcode/m5x5.py:<module>.StarcodeM5X5Controller": ("starcode_m5x5",),
    "beds/starcode/m5x5.py:<module>.StarcodeM5X5Controller.execution": ("starcode_m5x5",),
    "beds/svane/controller.py:<module>.SVANE_EXECUTION": ("svane",),
    "beds/svane/controller.py:<module>.SvaneController": ("svane",),
    "beds/timotion_ahf.py:<module>.TiMOTIONAhfController": ("timotion_ahf",),
    "beds/timotion_ahf.py:<module>.TiMOTIONAhfController.execution": ("timotion_ahf",),
    "beds/vibradorm/app.py:<module>.VibradormAppController": ("vibradorm_app",),
    "beds/vibradorm/app.py:<module>.VibradormAppController.execution": ("vibradorm_app",),
    "beds/vmatbasic/controller.py:<module>.VMatBasicController": ("vmatbasic",),
    "beds/vmatbasic/controller.py:<module>.VMatBasicController.execution": ("vmatbasic",),
    "profiles/ff_frame.py:<module>.BEDSENSE": ("BedSenseProfile:bedsense",),
    "profiles/ff_frame.py:<module>.SOLACE_PROFILES": (
        "SolaceProfile:common",
        "SolaceProfile:home_k1",
        "SolaceProfile:home_k2",
        "SolaceProfile:motion_flex",
        "SolaceProfile:woosa",
    ),
    "profiles/jiecang.py:<module>.DREAMASK": ("JiecangProfile:dreamask",),
    "profiles/jiecang.py:<module>.DREAMHD": ("JiecangProfile:dreamhd",),
    "profiles/jiecang.py:<module>.DREAMOTION": ("JiecangProfile:dreamotion",),
    **{
        f"profiles/keeson.py:<module>.{key.upper()}": (f"KeesonProfile:{key}",)
        for key in KEESON_STREAM
    },
    "profiles/keeson.py:<module>.app_profile": tuple(
        f"AppProfile:{app}@{layout}"
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    ),
    "profiles/keeson.py:<module>.ergomotion_4_profile": tuple(
        f"AppProfile:ergomotion_4@{style}" for style in sorted(ERGOMOTION_4_STYLES)
    ),
    "profiles/limoss.py:<module>.FSM_RELAX": ("LimossProfile:fsm_relax",),
    "profiles/limoss.py:<module>.LIMOSS_REMOTE": ("LimossProfile:limoss_remote",),
    "profiles/logicdata.py:<module>.PHONE": ("LogicdataProfile:phone",),
    "profiles/logicdata.py:<module>.SLEEP_SMART": ("LogicdataProfile:sleep_smart",),
    "profiles/logicdata.py:<module>.TABLET": ("LogicdataProfile:tablet",),
    "profiles/malouf.py:<module>.LUCID": ("MaloufAppProfile:lucid",),
    "profiles/malouf.py:<module>.MALOUF": ("MaloufAppProfile:malouf",),
    "profiles/malouf.py:<module>.NEW_OKIN": ("MaloufRouteProfile:malouf_new_okin",),
    "profiles/okin_5a.py:<module>.ELEVATE": ("Okin5AProfile:star_elevate",),
    "profiles/okin_nframe.py:<module>.CU170_EXECUTION": ("OkinNFrameProfile:prodigy4",),
    "profiles/okin_nframe.py:<module>.LEGGETT_EXECUTION": _LEGGETT_STREAM,
    "profiles/okin_nframe.py:<module>.USERIES_EXECUTION": ("OkinNFrameProfile:useries",),
    "profiles/okin_nframe.py:<module>._abm": _ABM,
    "profiles/okin_nframe.py:<module>._cst": _CST,
    "profiles/okin_nframe.py:<module>._customatic": _CUSTOMATIC,
    "profiles/okin_nframe.py:<module>._eshine": _ESHINE,
    "profiles/okin_nframe.py:<module>._leggett": (
        *_LEGGETT_STREAM,
        "OkinNFrameProfile:prodigy4",
        "OkinNFrameProfile:useries",
    ),
    "profiles/okin_nframe.py:<module>._lumbar": _LUMBAR,
    "profiles/okin_nframe.py:<module>._simmons": _SIMMONS,
    "profiles/richmat.py:<module>.BEDTECH_APP_PROFILES": tuple(
        f"RichmatProfile:bedtech_{model}"
        for model in ("bt2000", "bt2500", "bt3000", "bt3000fh", "bt6500", "btx4", "btx4fh", "btx5", "btx5fh")
    ),
    "profiles/richmat.py:<module>.ESHINE": ("RichmatProfile:eshine",),
    "profiles/richmat.py:<module>.RICHMAT_APP": ("RichmatProfile:richmat_app",),
    "profiles/richmat.py:<module>.HJBED": ("RichmatProfile:hjbed",),
    "profiles/richmat.py:<module>.LEGGETT_WILINKE": ("RichmatProfile:leggett_wilinke",),
    "profiles/richmat.py:<module>.RICHMAT": tuple(
        f"RichmatProfile:richmat_{framing}"
        for framing in ("nordic", "prefix55", "prefixaa", "wilinke")
    ),
    "profiles/richmat.py:<module>.RICHMAT_MH": tuple(
        f"RichmatProfile:richmat_mh_{app}"
        for app in (
            *("best_mattress", "blvd_home", "harmony", "idealbed", "revive"),
            *("americanstar", "bailey2", "ruf", "tx", "wsilver2"),
        )
    ),
}

PACKAGE = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
CAPABILITY_FIELDS = frozenset({"hold", "sustain_ms", "concurrent", "hold_controls"})
# Family profiles have their own ``hold`` timing field, so only these names
# identify a replace() of a declaration.
DISTINCT_FIELDS = frozenset({"execution", "sustain_ms", "concurrent", "hold_controls"})


def _design_evidence_keys() -> frozenset[str]:
    """Keys of both tables in the design's "Evidence keys" section."""
    section = DESIGN.read_text().split("\n## Evidence keys\n", 1)[1]
    keys = {
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"\|\s*([^|\s]+)\s*\|", line))
    }
    return frozenset(keys - {"Key", "---"})


def _instances(value: object, cls: type, depth: int = 0) -> Iterator[object]:
    if isinstance(value, cls):
        yield value
    elif depth < 2 and isinstance(value, Mapping):
        for item in value.values():
            yield from _instances(item, cls, depth + 1)
    elif depth < 2 and isinstance(value, (tuple, list, frozenset, set)):
        for item in value:
            yield from _instances(item, cls, depth + 1)


async def _family_profiles() -> dict[str, ExecutionCapabilities]:
    """Every reachable family profile's declaration, by identity.

    Static profiles are found in their modules; profiles built at runtime are
    reached through each bed type's and app route's controller.
    """
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    profiles = [
        profile
        for cls in registered
        for value in vars(sys.modules[cls.__module__]).values()
        for profile in _instances(value, cls)
    ]
    for bed_type in SUPPORTED_BED_TYPES:
        profiles.append(getattr(await _create_controller_for_bed_type(bed_type), "profile", None))
    # Layouts are built at runtime and never stored; reach every one.
    profiles.extend(
        keeson_profiles.app_profile(app, layout)
        for app, layouts in keeson_profiles.APP_LAYOUTS.items()
        for layout in layouts
    )
    profiles.extend(keeson_profiles.ergomotion_4_profile(style) for style in ERGOMOTION_4_STYLES)
    # Werkmeister and VMAT layouts are validated from entry data at runtime.
    profiles += [
        vibradorm_profiles.validate_vibradorm_app_profile("werkmeister", 5),
        vibradorm_profiles.validate_vibradorm_app_profile("vmat", 2, floor_light=False, remote="00"),
    ]
    for bed_type, (config_key, choices) in APP_ROUTES.items():
        for choice in choices:
            coordinator = _FactoryCoordinator()
            coordinator.entry.data[config_key] = choice
            controller = await create_controller(
                coordinator, bed_type, VARIANT_AUTO, _make_connected_client()
            )
            profiles.append(getattr(controller, "profile", None))

    declared: dict[str, ExecutionCapabilities] = {}
    for profile in profiles:
        if type(profile) not in registered:
            continue
        execution = getattr(profile, "execution", None)
        assert isinstance(execution, ExecutionCapabilities), profile
        identity = _identity(profile)
        # One identity must not carry two different declarations.
        assert declared.setdefault(identity, execution) == execution, identity
    # Vectors are frozen per profile key, so the scan must reach every
    # profile that has them. Otherwise a declaration could hide.
    for name, family in FAMILIES.items():
        reached = {
            identity.split(":", 1)[1].split("@", 1)[0]
            for identity in declared
            if identity.split(":", 1)[0] in {cls.__name__ for cls in family.profiles}
        }
        frozen = {key for vectors in family.profiles.values() for key in vectors}
        assert frozen <= reached, (name, frozen - reached)
    return declared


def _identity(profile: object) -> str:
    """Profile class and key, plus the layout when one key has several."""
    identity = f"{type(profile).__name__}:{getattr(profile, 'key', None)}"
    layout = getattr(profile, "layout", None)
    return f"{identity}@{layout}" if isinstance(layout, str) else identity


async def _declarations() -> dict[str, frozenset[str]]:
    return {
        identity: execution.declared
        for identity, execution in (await _family_profiles()).items()
        if execution.declared
    }


def test_evidence_keys_exist_in_design() -> None:
    known = _design_evidence_keys()
    assert {"p4", "useries", "clarity", "svane"} <= known
    for identity, fields in EVIDENCE.items():
        for name, keys in fields.items():
            assert keys, f"{identity}.{name} needs at least one evidence key"
            assert not set(keys) - known, (identity, name, set(keys) - known)


async def test_every_profile_declaration_has_evidence() -> None:
    for identity, declared in (await _declarations()).items():
        assert identity in EVIDENCE, f"{identity} declares {sorted(declared)} without evidence"
        assert set(EVIDENCE[identity]) == declared, (identity, sorted(declared))


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_every_controller_declaration_has_evidence(bed_type: str) -> None:
    """A controller declares through its family profile, or has its own row."""
    controller = await _create_controller_for_bed_type(bed_type)
    execution = controller.execution
    assert isinstance(execution, ExecutionCapabilities)
    if not execution.declared:
        return
    profile = getattr(controller, "profile", None)
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    if type(profile) in registered and getattr(profile, "execution", None) is execution:
        identity = _identity(profile)
    else:
        identity = bed_type
    assert identity in EVIDENCE, f"{identity} declares {sorted(execution.declared)}"
    assert set(EVIDENCE[identity]) == execution.declared, identity


STREAM_HOOKS = ("stream_tick_s", "write_stream_tick", "end_stream_member", "release_stream")


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_concurrent_declaration_implements_the_stream_hooks(bed_type: str) -> None:
    """A controller that merges motors must compose its own frames (#516)."""
    controller = await _create_controller_for_bed_type(bed_type)
    if not controller.execution.concurrent:
        return
    for hook in STREAM_HOOKS:
        assert getattr(type(controller), hook) is not getattr(BedController, hook), (
            bed_type,
            hook,
        )


async def test_evidence_rows_match_live_declarations() -> None:
    """A row whose declaration was removed must go too."""
    assert {identity for identity in EVIDENCE if ":" in identity} <= set(await _declarations())
    assert {identity for identity in EVIDENCE if ":" not in identity} <= set(
        SUPPORTED_BED_TYPES
    )


def _declaration_sites(root: Path = PACKAGE) -> dict[str, set[str]]:
    """Every source site that constructs, passes, assigns or overrides a declaration.

    Maps each site to the capability fields its ``ExecutionCapabilities`` calls
    name, so a conditional or layout-specific field cannot hide behind a
    reviewed site. ``"**"`` marks a call whose fields cannot be read.
    """
    sites: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "execution.py":
            continue
        tree = ast.parse(path.read_text(), filename=relative)
        for scope, node in _walk_scoped(tree, "<module>"):
            if _names_field_by_string(node):
                # A field named by string (a ``**{...}`` key, setattr) is unreadable.
                sites.setdefault(f"{relative}:{scope}", set()).add("**")
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                    node.func.id if isinstance(node.func, ast.Name) else ""
                )
                site = f"{relative}:{scope}"
                if name == "ExecutionCapabilities" and (node.args or node.keywords):
                    fields = sites.setdefault(site, set())
                    fields.update(keyword.arg or "**" for keyword in node.keywords)
                    if node.args:
                        fields.add("**")
                if any(keyword.arg == "execution" for keyword in node.keywords):
                    sites.setdefault(site, set())
                source = ast.unparse(node)
                if name in ("replace", "__replace__") and (
                    "execution" in source.lower()
                    or any(keyword.arg in DISTINCT_FIELDS for keyword in node.keywords)
                ):
                    # replace() can add a field to a reviewed declaration.
                    fields = sites.setdefault(site, set())
                    fields.update(
                        keyword.arg if keyword.arg is not None else "**"
                        for keyword in node.keywords
                        if keyword.arg is None or keyword.arg in CAPABILITY_FIELDS
                    )
            elif (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "execution"
                and relative != "beds/base.py"
            ):
                sites.setdefault(f"{relative}:{scope}", set())
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and relative != "beds/base.py":
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                empty_default = (
                    isinstance(node.value, ast.Name) and node.value.id == "NO_EXECUTION_CAPABILITIES"
                )
                if not empty_default and any(
                    (isinstance(t, ast.Name) and t.id == "execution")
                    or (isinstance(t, ast.Attribute) and t.attr in ("execution", "_execution"))
                    for t in targets
                ):
                    sites.setdefault(f"{relative}:{scope}", set())
    return sites


def _names_field_by_string(node: ast.AST) -> bool:
    if isinstance(node, ast.Dict):
        return any(
            isinstance(key, ast.Constant) and key.value in DISTINCT_FIELDS for key in node.keys
        )
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in DISTINCT_FIELDS
    )


def _walk_scoped(node: ast.AST, scope: str) -> Iterator[tuple[str, ast.AST]]:
    for child in ast.iter_child_nodes(node):
        yield scope, child
        name = (
            child.name
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            else None
        )
        if name is None and isinstance(child, (ast.Assign, ast.AnnAssign)) and scope == "<module>":
            target = child.targets[0] if isinstance(child, ast.Assign) else child.target
            name = target.id if isinstance(target, ast.Name) else None
        yield from _walk_scoped(child, f"{scope}.{name}" if name else scope)


def test_every_declaration_site_is_reviewed() -> None:
    """No variant, layout or runtime profile can declare a capability unlisted."""
    sites = _declaration_sites()
    assert set(sites) == set(DECLARATION_SITES), (
        "list each new execution declaration site in DECLARATION_SITES with its evidence"
    )
    for site, identities in DECLARATION_SITES.items():
        assert identities, site
        assert set(identities) <= set(EVIDENCE), (site, set(identities) - set(EVIDENCE))
        # Every field a site can declare, on any branch, needs evidence on
        # every identity the site produces.
        for identity in identities:
            assert sites[site] <= set(EVIDENCE[identity]), (site, identity, sites[site])


def test_site_guard_finds_declarations(tmp_path: Path) -> None:
    """The guard recognizes each way of declaring, so it cannot pass vacuously."""
    samples = {
        "built.py": "def make():\n    return ExecutionCapabilities(hold='stream')\n",
        "passed.py": "PROFILE = Profile(key='x', execution=STREAM)\n",
        "replaced.py": "MX = replace(BASE, execution=STREAM)\n",
        "override.py": (
            "class C:\n    @property\n    def execution(self):\n        return STREAM\n"
        ),
        "assigned.py": "class P:\n    execution: ExecutionCapabilities = STREAM\n",
        "empty.py": "class P:\n    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES\n",
    }
    samples["conditional.py"] = (
        "def make(mx):\n"
        "    return ExecutionCapabilities(hold='stream', concurrent=AXES if mx else frozenset())\n"
    )
    samples["spread.py"] = "X = ExecutionCapabilities(**FIELDS)\n"
    samples["variant.py"] = (
        "class V:\n    @property\n    def execution(self):\n"
        "        return replace(ExecutionCapabilities(hold='stream'),"
        " concurrent=AXES if self.v else frozenset())\n"
    )
    samples["copied.py"] = "X = replace(BASE_EXECUTION, **CHANGES)\n"
    samples["keyed.py"] = "CHANGES = {'concurrent': AXES}\n"
    samples["setattr.py"] = "def f(p):\n    setattr(p, 'execution', STREAM)\n"
    for name, source in samples.items():
        (tmp_path / name).write_text(source)
    sites = _declaration_sites(tmp_path)
    assert {site.split(":", 1)[0] for site in sites} == set(samples) - {"empty.py"}
    assert sites["conditional.py:<module>.make"] == {"hold", "concurrent"}
    assert sites["spread.py:<module>.X"] == {"**"}
    assert sites["variant.py:<module>.V.execution"] == {"hold", "concurrent"}
    assert sites["copied.py:<module>.X"] == {"**"}
    assert sites["keyed.py:<module>.CHANGES"] == {"**"}
    assert sites["setattr.py:<module>.f"] == {"**"}


def test_default_declares_nothing() -> None:
    assert NO_EXECUTION_CAPABILITIES.declared == frozenset()
    assert ExecutionCapabilities(
        hold="stream", sustain_ms=217, concurrent=frozenset({"motor:back", "motor:legs"})
    ).declared == {"hold", "sustain_ms", "concurrent"}
    assert ExecutionCapabilities(hold="stream", hold_controls=frozenset({"x"})).declared == {
        "hold",
        "hold_controls",
    }


def test_a_scoped_hold_admits_only_its_controls() -> None:
    scoped = ExecutionCapabilities(hold="stream", hold_controls=frozenset({"held"}))
    assert scoped.hold_for("held") == "stream"
    assert scoped.hold_for("gesture") is None
    # A motor route is outside every control scope.
    assert scoped.hold_for() is None
    whole = ExecutionCapabilities(hold="latched")
    assert whole.hold_for("any") == whole.hold_for() == "latched"
    assert NO_EXECUTION_CAPABILITIES.hold_for("any") is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hold": "pulsed"},
        {"sustain_ms": 200},
        {"hold": "stream", "sustain_ms": 0},
        {"concurrent": frozenset({"motor:back"})},
        {"concurrent": frozenset({"motor:back", ""})},
        {"hold_controls": frozenset({"held"})},
        {"hold": "stream", "hold_controls": frozenset()},
        {"hold": "stream", "hold_controls": frozenset({""})},
    ],
)
def test_invalid_declarations_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ExecutionCapabilities(**kwargs)  # type: ignore[arg-type]
