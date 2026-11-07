"""Frozen HHC ``$#`` frames, the vectors the codec must reproduce.

``REPORT_VECTORS`` are the test vectors of the accepted MotoMotion 3.1.9 report
(``com.HHC.MotoMotion``, row113; ``analysis.json`` SHA-256
``b56fe6ab9dd878f3fc4c4937bf490653aa2308feb316c0a8305212201a7d0b5f``), split
into their frames. The ledger is ``tests/fixtures/motomotion_ledger.json``.

``MOTOSLEEP_FRAMES`` are the MotoSleep 5.1.5 and Power Bob 2.0.3 profiles'
frames. Their reports were not retained, so these are every fixed frame the
pre-v5 controller could send: the wire snapshot's ``legacy`` route,
``test_motosleep.py``'s vectors and each panel's commands, with the RGB light
at its default white and off.
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


def _hex(*frames: bytes) -> frozenset[str]:
    return frozenset(frame.hex() for frame in frames)


# The letter commands both apps send, raw.
_RAW_LETTERS = (
    *(b"$A", b"$B", b"$C", b"$D", b"$E", b"$F", b"$G", b"$H", b"$I", b"$J", b"$K", b"$L"),
    *(b"$M", b"$N", b"$O", b"$P", b"$Q", b"$R", b"$S", b"$T", b"$U", b"$V", b"$Z", b"$a"),
    *(b"$b", b"$p", b"$q"),
)

MOTOSLEEP_FRAMES: dict[str, frozenset[str]] = {
    "power_bob": _hex(
        *_RAW_LETTERS,
        # RGB white and off, selector before level.
        b"$#003150012000004R\r",
        b"$#003160012000007R\r",
        b"$#003170012000006R\r",
        b"$#003150000000007R\r",
        b"$#003160000000004R\r",
        b"$#003170000000005R\r",
    ),
    "motosleep": _hex(
        *_RAW_LETTERS,
        b"$W",
        # Wrapped letters (name index 22 is M).
        *(b"$#$AR\r", b"$#$BR\r", b"$#$CR\r", b"$#$DR\r", b"$#$ER\r", b"$#$FR\r"),
        *(b"$#$GR\r", b"$#$HR\r", b"$#$IR\r", b"$#$JR\r", b"$#$KR\r", b"$#$LR\r"),
        *(b"$#$MR\r", b"$#$NR\r", b"$#$OR\r", b"$#$PR\r", b"$#$QR\r", b"$#$RR\r"),
        *(b"$#$SR\r", b"$#$TR\r", b"$#$UR\r", b"$#$VR\r", b"$#$WR\r", b"$#$ZR\r"),
        *(b"$#$aR\r", b"$#$bR\r", b"$#$pR\r", b"$#$qR\r"),
        # RGB white and off, level before selector.
        b"$#001200031500004R\r",
        b"$#001200031600007R\r",
        b"$#001200031700006R\r",
        b"$#000000031500007R\r",
        b"$#000000031600004R\r",
        b"$#000000031700005R\r",
        # MainPanel sync enable and disable.
        b"$#000120000000003R\r",
        b"$#000150000000004R\r",
        # MOTO binary: motors, presets, memory, swing and the two releases.
        *map(
            bytes.fromhex,
            (
                "24230000000000410d",
                "24230001000001410d",
                "24230002000002410d",
                "24230004000004410d",
                "24230005000005410d",
                "24230008000008410d",
                "2423000a00000a410d",
                "24230010000010410d",
                "24230020000020410d",
                "24230040000040410d",
                "24230050000050410d",
                "24230080000080410d",
                "242300a00000a0410d",
                "24230100000001410d",
                "24230200000002410d",
                "24235555000000410d",
                "24238009000089410d",
                "2423800a00008a410d",
                "2423800b00008b410d",
                "2423800c00008c410d",
                "2423800d00008d410d",
                "2423800e00008e410d",
                "24238014000094410d",
                "2423811d00009c410d",
                "2423811e00009f410d",
                "24239088000119410d",
                "24239089000019410d",
            ),
        ),
    ),
    # Manual entries without a usable name: back, legs, Flat and STOP, wrapped.
    "legacy": _hex(b"$#$KR\r", b"$#$LR\r", b"$#$MR\r", b"$#$NR\r", b"$#$OR\r", b"$#$bR\r"),
}
