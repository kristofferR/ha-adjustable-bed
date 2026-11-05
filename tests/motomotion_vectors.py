"""Frozen MotoMotion frames, the vectors the codec must reproduce.

Each entry is a test vector of the accepted MotoMotion 3.1.9 report
(``com.HHC.MotoMotion``, row113; ``analysis.json`` SHA-256
``b56fe6ab9dd878f3fc4c4937bf490653aa2308feb316c0a8305212201a7d0b5f``), split
into its frames. The ledger is ``tests/fixtures/motomotion_ledger.json``.
"""

from __future__ import annotations

# Report test vector id -> its frames, in order, as hex.
REPORT_VECTORS: dict[str, tuple[str, ...]] = {
    # headrestdown
    "a-left": ("2423303030303130303030303030303031520d",),
    # saveslot1right
    "a-right-save": ("2423303032363331303030303030303036520d",),
    # unpair
    "a-unpair": ("2423303035303031323334353030303034520d",),
    # Sixsave
    "b-save": ("2423811a00009b410d",),
    # musicvolume
    "b-vol": ("24230009003f36410d",),
    # musictreble
    "b-treble": ("24230001001f1e410d",),
    # widemode
    "c-mode": (
        "24234d30380d",
        "24235431300d",
        "24234230350d",
        "24235630350d",
    ),
    # fieldorder
    "d-order": ("41494f4b00010004000300020005520d",),
    # saturating16bit
    "d-clamp": ("41494f4b0000ffff0000ffff0000520d",),
    # rawrandomsample
    "e-bind": ("000102037f80fdfe",),
    # RGB red on right
    "a-right-red": ("2423303033313531303132303030303035520d",),
    # Known E panel: valid -> malformed37 -> next lumbar
    "repair-e-after-failure": (
        "2423303033353330303030303030303035520d",
        "2423303033353330303030303030303035520d",
        "2423303033353330303030303030303035520d",
    ),
    # TV generator helper with NaN buttocks
    "repair-tv-nan-helper": ("41494f4b00a70364055801a0026f520d",),
    # BLE invocation while persistence Future pending
    "repair-bind-pending": ("000102037f80fdfe",),
    # Established CM -> malformed16 retains RGB -> real kind2 callback selects white after wrap
    "repair-rgb-native64-zero": (
        "2423303033313530303132303030303034520d",
        "2423303033313630303132303030303037520d",
        "2423303033313730303132303030303036520d",
    ),
    # 38-token DMAX -> OK delivery/build ->200ms action32788
    "repair-d-native64-max": ("2423333237383830303030303030303036520d",),
    # Fragmented notification -> stored padded decimal -> kind2 callback component sequence
    "repair-long-RGB-0": (
        "2423303033313530303132303030303034520d",
        "2423303033313630303132303030303037520d",
        "2423303033313730303132303030303036520d",
    ),
    # Fragmented notification -> stored padded decimal -> known-local build and200ms command
    "repair-long-D-0": ("2423333237383830303030303030303036520d",),
    # Fragmented notification -> stored padded decimal -> kind2 callback component sequence
    "repair-long-RGB-7": (
        "2423303033313530303030303030303037520d",
        "2423303033313630303030303030303034520d",
        "2423303033313730303030303030303035520d",
    ),
    # Fragmented notification -> stored padded decimal -> known-local build and200ms command
    "repair-long-D-7": ("2423333237393530303030303030303130520d",),
    # Fragmented notification -> stored padded decimal -> kind2 callback component sequence
    "repair-long-RGB-9223372036854775807": (
        "2423303033313530303030303030303037520d",
        "2423303033313630303030303030303034520d",
        "2423303033313730303030303030303035520d",
    ),
    # Fragmented notification -> stored padded decimal -> known-local build and200ms command
    "repair-long-D-9223372036854775807": ("2423333237383830303030303030303036520d",),
}

FROZEN_FRAMES: dict[str, frozenset[str]] = {
    "motomotion": frozenset(frame for frames in REPORT_VECTORS.values() for frame in frames),
}
