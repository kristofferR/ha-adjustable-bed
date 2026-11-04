"""Codec guides keep their generated tables in step with the codec and profile data.

The checks run for every family module in ``scripts/codec_docs/`` and
``tests/codec_families/``. Checks only one family needs live in
``tests/test_codec_docs_<family>.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.adjustable_bed.controller_factory import create_controller
from scripts import generate_codec_docs as generator
from tests.codec_families import families
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = families()
DOC_MODULES = generator.family_modules()
GUIDED = sorted(name for name, family in FAMILIES.items() if family.guide is not None)
WITH_BED_TYPES = sorted(name for name, module in DOC_MODULES.items() if hasattr(module, "bed_types"))


def test_generated_blocks_are_current() -> None:
    assert generator.stale_guides() == [], (
        "Run `uv run --no-sync python scripts/generate_codec_docs.py` and commit the guides"
    )


def test_every_block_has_one_marked_region() -> None:
    assert generator.BLOCKS
    for guide, name, _ in generator.BLOCKS:
        text = (ROOT / guide).read_text(encoding="utf-8")
        assert text.count(f"<!-- generated:{name} -->") == 1, f"{guide} needs one {name} block"


def test_doc_modules_are_registered_families() -> None:
    assert DOC_MODULES.keys() <= FAMILIES.keys()


@pytest.mark.parametrize("name", GUIDED)
def test_guide_frames_are_frozen_vectors(name: str) -> None:
    """Every frame spelled in the guide is one a profile was frozen sending.

    The generated tables build their frames through the codec, so a swapped row
    makes the block stale; this catches frames spelled by hand outside them.
    """
    guide = FAMILIES[name].guide
    assert guide is not None
    frames = guide.spelled((ROOT / guide.path).read_text(encoding="utf-8"))
    assert frames
    unknown = sorted(frames - guide.frozen)
    assert not unknown, f"Frames no profile was frozen sending: {unknown}"


@pytest.mark.parametrize("name", WITH_BED_TYPES)
async def test_guide_bed_types_match_the_factory(name: str) -> None:
    """The profile summary lists every profile, with the bed types the factory builds it for."""
    family = FAMILIES[name]
    keys = {key for vectors in family.profiles.values() for key in vectors}
    bed_types = DOC_MODULES[name].bed_types()
    assert bed_types.keys() == keys
    for key, types in bed_types.items():
        assert types, f"{key} has no bed type"
        for bed_type in types:
            coordinator = _FactoryCoordinator()
            # Some routes read entry options or keep per-entry session state.
            coordinator.entry.options = {}
            coordinator.entry.entry_id = f"codec-docs-{bed_type}"
            for config_key, _ in family.app_routes.values():
                coordinator.entry.data[config_key] = key
            variant = family.guide.variant(key, bed_type) if family.guide else None
            controller = await create_controller(
                coordinator, bed_type, variant, _make_connected_client()
            )
            profile = getattr(controller, "profile", None)
            assert type(profile) in family.profiles, (key, bed_type)
            assert getattr(profile, "key", None) == key, (key, bed_type)
