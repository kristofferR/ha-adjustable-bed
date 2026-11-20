"""R1 Richmat 6E: Richmat, BedTech, WiLinke, the catalog apps, Casper Base and Hush Base."""

from __future__ import annotations

import re

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.casper import CasperProfile
from custom_components.adjustable_bed.profiles.dreamsense import DreamSenseProfile
from custom_components.adjustable_bed.profiles.hush import HushProfile
from custom_components.adjustable_bed.profiles.luniosmart import LunioSmartProfile
from custom_components.adjustable_bed.profiles.luuna import LuunaProfile
from custom_components.adjustable_bed.profiles.mlily_remote import PROFILES as MLILY_REMOTE_PROFILES
from custom_components.adjustable_bed.profiles.mlily_remote import MlilyRemoteProfile
from custom_components.adjustable_bed.profiles.richmat import RICHMAT_CLASSIC, RichmatProfile
from custom_components.adjustable_bed.profiles.richmat_legacy import LegacyProfile
from custom_components.adjustable_bed.profiles.richmat_legacy import choices as legacy_choices
from custom_components.adjustable_bed.profiles.sonicsleep import SonicSleepProfile
from tests import (
    casper_base_vectors,
    hush_vectors,
    luniosmart_vectors,
    luuna_vectors,
    mlily_remote_vectors,
    sonicsleep_vectors,
)
from tests.codec_families import CodecFamily, CodecGuide
from tests.dreamsense_vectors import FRAMES as DREAMSENSE_LITERALS
from tests.dreamsense_vectors import FROZEN_FRAMES as DREAMSENSE_FRAMES
from tests.richmat_legacy_vectors import FROZEN_FRAMES as LEGACY_FRAMES
from tests.richmat_vectors import FROZEN_FRAMES
from tests.saatva_vectors import FROZEN_FRAMES as SAATVA_FRAMES
from tests.saatva_vectors import VECTORS as SAATVA_VECTORS

_SPELLED = re.compile(r"`((?:6E|5E|55|AA|04)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE)
# Profiles reached through a protocol variant of their bed type.
_VARIANTS = {
    "richmat_wilinke": const.RICHMAT_VARIANT_WILINKE,
    "richmat_nordic": const.RICHMAT_VARIANT_NORDIC,
    "richmat_prefix55": const.RICHMAT_VARIANT_PREFIX55,
    "richmat_prefixaa": const.RICHMAT_VARIANT_PREFIXAA,
    **{f"bedtech_{model}": model for model in ("bt2000", "bt2500", "bt3000", "bt3000fh", "bt6500", "btx4", "btx4fh", "btx5", "btx5fh")},
    "richmat_mh_bedtech_classic": "model_5i",
    "hjbed": "hj_bedbjrn",
    "galaxy": "6BRM",
    "richmat_app": "6BRM",
    "goodvibe": "selector-0001",
    "mlily": "6brm",
    "majestichome": "FARM",
    "okimiki": "HCRN",
    "bobpowerbase": "elite",
    **{f"richmat_classic_{app}": app for app in RICHMAT_CLASSIC},
}
# The Casper Base and Hush Base products are their bed type's protocol variant.
_PRODUCT_VARIANTS = frozenset({const.BED_TYPE_CASPER_BASE, const.BED_TYPE_HUSH_BASE, const.BED_TYPE_LUUNA, const.BED_TYPE_MLILY_REMOTE})
_FROZEN = frozenset().union(
    DREAMSENSE_LITERALS,
    *LEGACY_FRAMES.values(),
    *FROZEN_FRAMES.values(),
    *luniosmart_vectors.FROZEN_FRAMES.values(),
    mlily_remote_vectors.FROZEN_FRAMES,
    frozenset(row[2] for row in SAATVA_VECTORS),
    *(frozenset(r["expected_bytes"] for r in sonicsleep_vectors.VECTORS["commands"] + sonicsleep_vectors.VECTORS["alarm_repair"]),),
    *(
        vectors.SHARED_FRAMES.union(*vectors.FROZEN_FRAMES.values())
        for vectors in (casper_base_vectors, hush_vectors, luuna_vectors)
    ),
)


def _spelled(text: str) -> set[str]:
    """Fully spelled 6E/5E/55/AA/04 frames outside the Notifications sections."""
    sections = re.split(r"^(#+ .*)$", text, flags=re.M)
    sent = "".join(
        body
        for heading, body in zip(["", *sections[1::2]], sections[0::2], strict=True)
        if "Notifications" not in heading
    )
    frames = set()
    for literal in _SPELLED.findall(sent):
        data = bytes.fromhex(literal.replace(" ", ""))
        # One write may carry back-to-back 5-byte frames.
        if len(data) % 5 == 0 and sum(data[:-1]) & 255 != data[-1]:
            frames |= {data[i : i + 5].hex() for i in range(0, len(data), 5)}
        else:
            frames.add(data.hex())
    return frames


FAMILY = CodecFamily(
    profiles={
        DreamSenseProfile: DREAMSENSE_FRAMES,
        RichmatProfile: FROZEN_FRAMES | SAATVA_FRAMES,
        LunioSmartProfile: luniosmart_vectors.FROZEN_FRAMES,
        LegacyProfile: LEGACY_FRAMES,
        MlilyRemoteProfile: dict.fromkeys(MLILY_REMOTE_PROFILES, mlily_remote_vectors.FROZEN_FRAMES),
        CasperProfile: casper_base_vectors.FROZEN_FRAMES,
        HushProfile: hush_vectors.FROZEN_FRAMES,
        LuunaProfile: luuna_vectors.FROZEN_FRAMES,
        SonicSleepProfile: {"one": frozenset(r["expected_bytes"] for r in sonicsleep_vectors.VECTORS["commands"] + sonicsleep_vectors.VECTORS["alarm_repair"])},
    },
    bed_types=frozenset(
        {
            "bailey_bed_control",
            "bedtech",
            "bedtech_classic",
            "casper_base",
            "eshine",
            "galaxy",
            "goodvibe",
            "mlily",
            "majestichome",
            "okimiki",
            "bobpowerbase",
            "mlily_remote",
            "hjbed",
            "richmat_app",
            "hush_base",
            "luuna",
            "sonicsleep",
            "dreamsense",
            "saatva",
            "luniosmart",
            "sleep_evolution",
            "wsilver_legacy",
            "leggett_lp_legacy",
            "leggett_wilinke",
            "richmat",
            "richmat_americanstar",
            "richmat_best_mattress",
            "richmat_blvd_home",
            "richmat_classic_apps",
            "richmat_harmony",
            "richmat_idealbed",
            "richmat_revive",
            "richmat_tx",
            "richmat_nisco",
            "richmat_mlily_supreme",
            "ruf_betten",
            "wsilver_products",
        }
    ),
    app_routes={app: (const.CONF_PROTOCOL_VARIANT, tuple(legacy_choices(app))) for app in ("sleep_evolution", "wsilver_legacy")},
    guide=CodecGuide(
        path="docs/beds/richmat.md",
        spelled=_spelled,
        frozen=_FROZEN,
        variant=lambda key, bed_type: key.removeprefix("dreamsense_") if bed_type == "dreamsense" else key.removeprefix("saatva_") if bed_type == "saatva" else key.split(":", 1)[1] if bed_type in ("sleep_evolution", "wsilver_legacy") else key if bed_type in _PRODUCT_VARIANTS else _VARIANTS.get(key),
        entry_data={
            "bobpowerbase": {const.CONF_PRODUCT_TYPE: "standard"},
            "sonicsleep": {const.CONF_PRODUCT_TYPE: "one"},
            **{app: {const.CONF_BED_TYPE: app, const.CONF_PROTOCOL_VARIANT: "A1"} for app in ("sleep_evolution", "wsilver_legacy")},
            "mlily_remote": {const.CONF_PRODUCT_TYPE: "single"},
            # A layout every classic app ships.
            "richmat_classic_apps": {const.CONF_PRODUCT_TYPE: "6BRM"},
            "leggett_lp_legacy": {
                const.CONF_LP_LEGACY_MODEL: "6BRM",
                const.CONF_LP_LEGACY_MODE: "legacy",
                const.CONF_LP_LEGACY_WRITE_UUID: "11111111-2222-3333-4444-555555555555",
            },
        },
    ),
)
