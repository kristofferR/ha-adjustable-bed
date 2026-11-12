"""Kaidi mesh: the ``kaidi`` Seat and Floyd Home routes and the ISleep app."""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.profiles.comfy import ComfyDSProfile, ComfyProfile
from custom_components.adjustable_bed.profiles.kaidi import (
    FloydProfile,
    IsleepProfile,
    KaidiCommandProfile,
    RizeProfile,
)
from tests.codec_families import CodecFamily, CodecGuide, spelled_frames
from tests.kaidi_vectors import FROZEN_PAYLOADS, SESSION_FRAMES
from tests.rize_vectors import FROZEN_PAYLOADS as RIZE_PAYLOADS
from tests.test_comfy_vectors import FROZEN_PAYLOADS as COMFY_PAYLOADS

_SEAT_KEYS = ("seat_1", "seat_2", "seat_3", "seat_1_2")

FAMILY = CodecFamily(
    profiles={
        KaidiCommandProfile: {key: FROZEN_PAYLOADS[key] for key in _SEAT_KEYS},
        FloydProfile: {"floyd": FROZEN_PAYLOADS["floyd"]},
        IsleepProfile: {"isleep": FROZEN_PAYLOADS["isleep"]},
        RizeProfile: {"rize": RIZE_PAYLOADS},
        ComfyProfile: {"komfyd": COMFY_PAYLOADS["komfyd"]},
        ComfyDSProfile: {"comfyds": COMFY_PAYLOADS["comfyds"]},
    },
    bed_types=frozenset({const.BED_TYPE_ISLEEP, const.BED_TYPE_KAIDI, const.BED_TYPE_RIZE, const.BED_TYPE_KOMFYD, const.BED_TYPE_COMFYDS}),
    guide=CodecGuide(
        path="docs/beds/kaidi.md",
        # Complete session and control frames; templates and opcodes are not frames.
        spelled=spelled_frames(r"`((?:01 16 01|01 03|03)(?: [0-9A-Fa-f]{2}){7,})`"),
        frozen=frozenset(frame for _, _, frame in SESSION_FRAMES),
        variant=lambda key, bed_type: key if bed_type == const.BED_TYPE_KAIDI else None,
        entry_data={
            **{bed_type: {const.CONF_BED_TYPE: bed_type, const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000} for bed_type in (const.BED_TYPE_KOMFYD, const.BED_TYPE_COMFYDS)},
            const.BED_TYPE_RIZE: {const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000},
            const.BED_TYPE_ISLEEP: {const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000}
        },
    ),
)
