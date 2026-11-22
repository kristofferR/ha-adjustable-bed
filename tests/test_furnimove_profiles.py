"""Pinned production tables and the artifact's generic JSON parser contract."""

import hashlib
import json

import pytest

from custom_components.adjustable_bed.beds.furnimove.controller import build_furnimove_command
from custom_components.adjustable_bed.beds.furnimove.profiles import (
    FURNIMOVE_PRODUCTION_IDS,
    FURNIMOVE_PROFILES,
    get_furnimove_profile,
)


def test_all_production_rows_match_frozen_encoder_vectors() -> None:
    assert len(FURNIMOVE_PRODUCTION_IDS) == 87
    assert len({FURNIMOVE_PROFILES[key].actions for key in FURNIMOVE_PRODUCTION_IDS}) == 39
    vectors = [
        [
            key,
            index,
            build_furnimove_command(row.keycode).hex(),
            build_furnimove_command(row.keycode, old=True, dot=True).hex(),
            build_furnimove_command(row.keycode, dot=True).hex(),
        ]
        for key in sorted(FURNIMOVE_PRODUCTION_IDS)
        for index, row in enumerate(FURNIMOVE_PROFILES[key].actions)
    ]
    assert len(vectors) == 1092
    # Independently frozen runtime-command-ledger.json frame_candidates, all rows.
    assert (
        hashlib.sha256(json.dumps(vectors, separators=(",", ":")).encode()).hexdigest()
        == "910ddf3ffaa9bd914c3ecf9b6871b97b2a60d0e281a54d28b07a272847e5552a"
    )
    semantic = [
        [
            key,
            index,
            row.action,
            row.type,
            row.keycode,
            row.duration_ms,
            row.frequency_ms,
            row.intensity,
        ]
        for key in sorted(FURNIMOVE_PRODUCTION_IDS)
        for index, row in enumerate(FURNIMOVE_PROFILES[key].actions)
    ]
    # Frozen raw-table replay also pins timing, type and intensity carry.
    assert (
        hashlib.sha256(json.dumps(semantic, separators=(",", ":")).encode()).hexdigest()
        == "b2d5a1ae05cee7a7ac6330bd4e037771d8497001fad61568a9fd0aaff265df34"
    )
    for key in FURNIMOVE_PRODUCTION_IDS:
        profile = FURNIMOVE_PROFILES[key]
        assert profile.source == "production"
        assert len(profile.object_sha256) == len(profile.button_sha256) == 64


def test_local_tables_and_no_unknown_id_fallback() -> None:
    assert len(FURNIMOVE_PROFILES) == 90
    offline = get_furnimove_profile("00000")
    assert len(offline.actions) == 5
    assert offline.first("DisobeyStandbyTime") is None
    assert offline.first("Flat").keycode == "0x10000000"
    first = get_furnimove_profile("280702")
    alias = get_furnimove_profile("280703")
    assert first.actions is alias.actions
    assert len(first.actions) == 9
    assert first.first("Flat").keycode == "0x08000000"
    for key in ("unknown", "82417 ", "01", "9898989898989898"):
        with pytest.raises(ValueError):
            get_furnimove_profile(key)
