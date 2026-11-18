"""Linx's four carriers, independent of the existing Keeson JSON route."""

from custom_components.adjustable_bed.profiles.linx import LinxProfile
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.linx_vectors import FROZEN

FAMILY = CodecFamily(
    profiles={LinxProfile: dict.fromkeys(("quest", "orbes"), FROZEN)},
    bed_types=frozenset({"linx"}),
    app_routes={"linx": ("product_type", ("quest", "orbes"))},
    guide=CodecGuide(
        path="docs/beds/linx.md",
        spelled=spelled_frames(r"`((?:AA 03|AB 03)(?: [0-9A-Fa-f]{2})+)`"),
        variant=lambda _key, _bed: "a00a",
        entry_data={"linx": {"ble_device_name": "KSWF07D00000000"}},
        frozen=FROZEN,
    ),
)
