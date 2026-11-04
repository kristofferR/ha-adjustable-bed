"""Keeson guide checks beyond the generic ones in ``tests/test_codec_docs.py``."""

from __future__ import annotations

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
