"""K1 Keeson E5/E6: the core routes, their aliases and the app profiles over the codec."""

from __future__ import annotations

import json
import re
from pathlib import Path

from custom_components.adjustable_bed.profiles.enso import EnsoProfile
from custom_components.adjustable_bed.profiles.keeson import AppProfile, KeesonProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.keeson_vectors import FROZEN_FRAMES
from tests.ormatek_vectors import VECTORS as ORMATEK_VECTORS
from tests.somos_vectors import FROZEN_FRAMES as SOMOS_FRAMES

_ENSO_FRAMES = frozenset(row["expected_bytes"] for row in json.loads((Path(__file__).parents[1] / "fixtures/enso/vectors.json").read_text()) if row["kind"] != "notification")
_SOMOS = {f"somos_{key}": value for key, value in SOMOS_FRAMES.items()}

# The guide's AdjustaMattress section also spells its P3/P4 Okin N-frames, which
# its accepted AdjustaMattress report freezes in this fixture.
_ADJUSTAMATTRESS = frozenset(
    row["expected_bytes"].replace(" ", "").lower()
    for row in json.loads(
        (Path(__file__).parents[1] / "fixtures/adjustamattress/commands.json").read_text()
    )
    if row["expected_bytes"] != "NO WRITE"
)

_SYMPHONY = json.loads((Path(__file__).parents[1] / "fixtures/symphony_sleep/vectors.json").read_text())["builders"]
_SYMPHONY_FRAMES = {
    f"symphony_sleep_{route}": frozenset(row["expected_bytes"] for row in _SYMPHONY
        if row["protocol"] == ("P2" if route == "box2" else "P1"))
    for route in ("box1", "box2", "fallback")
}

FAMILY = CodecFamily(
    # The Keeson layout apps: one AppProfile per layout, vectors per app.
    profiles={EnsoProfile: {str(n): _ENSO_FRAMES for n in (2, 3, 4)}, KeesonProfile: {**FROZEN_FRAMES, **_SYMPHONY_FRAMES, **{f"ormatek_{wire}": frozenset(v[3] for v in ORMATEK_VECTORS if v[0] == wire) for wire in ("okin15", "okin24")}, **_SOMOS,
        "agingplace": frozenset(row["expected_bytes"] for row in json.loads(
            (Path(__file__).parents[1] / "fixtures/agingplace/vectors.json").read_text()))}, AppProfile: FROZEN_FRAMES},
    bed_types=frozenset(
        {
            "symphony_sleep",
            "ormatek",
            "jalon",
            "ergomotion",
            "keeson",
            "jalon_bed",
            "yamada",
            "enso",
            "somos",
            "okin_ffe",
            "serta",
            "ergo_slim",
            "ergomotion_app",
            "omazz_adjusto_iii",
            "qplus_app",
            "row_control",
            "serta_mp_remote",
            "tempur_au",
            "tempur_curve",
            "adjustamattress",
            "glideaway_motion",
            "malouf_legacy_okin",
            "scott_living",
            "sleepys_box15",
            "sbi",
            "rondure",
            "coolbase",
            "bf",
            "cherish",
            "comfort_enhancements",
            "comfortbase",
            "agingplace",
            "ergomotion_4",
        }
    ),
    app_routes={"enso": ("product_type", ("2", "3", "4"))},
    guide=CodecGuide(
        path="docs/beds/keeson.md",
        spelled=spelled_frames(
            r"`((?:E[56] ?FE ?16|0[45] ?02)(?: ?[0-9A-F]{2}){4,})`", re.IGNORECASE
        ),
        frozen=frozenset().union(*FROZEN_FRAMES.values(), *_SYMPHONY_FRAMES.values(), *_SOMOS.values(), _ENSO_FRAMES, (v[3] for v in ORMATEK_VECTORS), _ADJUSTAMATTRESS),
    ),
)
