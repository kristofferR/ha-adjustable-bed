"""Kaidi mesh: the ``kaidi`` Seat and Floyd Home routes and the ISleep app."""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.kaidi import (
    FloydProfile,
    IsleepProfile,
    KaidiCommandProfile,
)
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.kaidi_vectors import FROZEN_PAYLOADS, SESSION_FRAMES

_SEAT_KEYS = ("seat_1", "seat_2", "seat_3", "seat_1_2")

FAMILY = CodecFamily(
    profiles={
        KaidiCommandProfile: {key: FROZEN_PAYLOADS[key] for key in _SEAT_KEYS},
        FloydProfile: {"floyd": FROZEN_PAYLOADS["floyd"]},
        IsleepProfile: {"isleep": FROZEN_PAYLOADS["isleep"]},
    },
    bed_types=frozenset({const.BED_TYPE_ISLEEP, const.BED_TYPE_KAIDI}),
    guide=CodecGuide(
        path="docs/beds/kaidi.md",
        # Complete session and control frames; templates and opcodes are not frames.
        spelled=spelled_frames(r"`((?:01 16 01|01 03|03)(?: [0-9A-Fa-f]{2}){9,})`"),
        frozen=frozenset(frame for _, _, frame in SESSION_FRAMES),
        variant=lambda key, bed_type: key if bed_type == const.BED_TYPE_KAIDI else None,
        entry_data={
            const.BED_TYPE_ISLEEP: {const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000}
        },
    ),
)
