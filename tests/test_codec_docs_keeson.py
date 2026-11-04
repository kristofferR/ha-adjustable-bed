"""Keeson guide checks beyond the generic ones in ``tests/test_codec_docs.py``."""

from __future__ import annotations

from pathlib import Path

from custom_components.adjustable_bed.profiles import keeson as profiles
from scripts.codec_docs import keeson as docs


def test_keeson_routes_match_the_profiles() -> None:
    """The guide's sub-routes resolve as described, and its aliases are the factory's."""
    samples = {
        "ksbt03c": {"device_name": "KSBT03C1234"},
        "sleep_harmony_base_i5": {"device_name": "base-i5.1234"},
        "purple_plus": {"device_name": "KSBT04C1234"},
        "adjustable_lite_ksbt03c": {"device_name": "Bed KSBT03C"},
        "betterliving": {"device_name": None, "betterliving": True},
        "cb1322": {"device_name": None, "cb1322": True},
    }
    assert samples.keys() == docs.KEESON_SUB_ROUTES.keys()
    for key, (variant, _rule) in docs.KEESON_SUB_ROUTES.items():
        assert profiles.resolve(variant, **samples[key]).key == key
    assert docs.keeson_aliases() == {
        "ergomotion": ("ergomotion",),
        "serta": ("serta",),
        "okin": ("okin_ffe",),
    }


def test_keeson_guide_has_a_section_per_cluster033_app() -> None:
    """Each cluster033 app has a section with its generated key table."""
    text = (Path(__file__).resolve().parents[1] / docs.GUIDE).read_text(encoding="utf-8")
    for app in profiles.APP_LAYOUTS:
        assert f"\n### {docs._c033_heading(app)}\n" in text, app
        assert f"<!-- generated:keeson-app-{app.replace('_', '-')} -->" in text, app
