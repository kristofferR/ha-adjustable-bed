"""Frozen JMC400 frames, the vectors the codec must reproduce.

``jensen`` holds the Adjustable Sleep frames the pre-v5 controller tests froze:
the 2.0.29 audit's PIN, config, motion and preset frames, the 2.0.37 light-off
vector TV078, and the go-to and massage frames of the #631 JMC400 capture. It
adds the frames the wire snapshot records for the ``jensen`` bed type: every
light and fan level, the massage sweeps, and the position query the integration
sends.

``svane_remote`` holds the JMC400 and lamp frames of the accepted Svane Remote
1.8 vectors (row130, ``tests/test_svane_artifact_vectors.py``), and the lamp
levels the wire snapshot records for the ``svane`` bed type.

``FROZEN_REPORTS`` are the reports the controller tests feed back: the Jensen
config example, a flat JMC400 position reply and the Svane old-role record.
"""

from __future__ import annotations


def _frames(text: str) -> frozenset[str]:
    return frozenset(text.split())


FROZEN_FRAMES: dict[str, frozenset[str]] = {
    "jensen": _frames(
        # Session: PIN 3060, config request, position query.
        "1e03000600 0a00000000 10ff00000000"
        # STOP, then head and foot up and down, alone and together.
        " 100000000000 100100000000 100200000000 101000000000 102000000000"
        " 101100000000 102100000000 101200000000 102200000000"
        # Flat, device memory save and recall, and the #631 go-to (head 30771, foot 30000).
        " 108100000000 104000000000 108000000000 100433783075"
        # Massage: off, the #631 sweep (head 6, wave 6), and the snapshot's levels.
        " 120000000000 120600060000"
        " 120005000000 120105000000 120205000000 120305000000 120405000000 120505000000"
        " 120605000000 120705000000 120805000000 120905000000 120a00000000 120a01000000"
        " 120a02000000 120a03000000 120a04000000 120a05000000 120a06000000 120a07000000"
        " 120a08000000 120a09000000 120a0a000000 120a0a010000 120a0a020000 120a0a030000"
        " 120a0a040000 120a0a050000 120a0a060000 120a0a070000 120a0a080000 120a0a090000"
        " 120a0a0a0000"
        # Light off (TV078) and levels 1-10.
        " 130200000032 130201000000 130202000000 130203000000 130204000000 130205000000"
        " 130206000000 130207000000 130208000000 130209000000 13020a000000"
        # Fan levels 0-10.
        " 140000000050 140100000050 140200000050 140300000050 140400000050 140500000050"
        " 140600000050 140700000050 140800000050 140900000050 140a00000050"
    ),
    "svane_remote": _frames(
        # STOP, then head and feet up and down, alone and together.
        "100000000000 100100000000 100200000000 101000000000 102000000000"
        " 101100000000 102100000000 101200000000 102200000000"
        # Svane position, and the Read and TV defaults' recall.
        " 108100000000 100481388113 100482738204"
        # Lamp off, then levels as Java ints: 5, 10, 90, 95, 100, 256 and -1.
        " 130200000000 130205010064 13020a010064 13025a010064 13025f010064 130264010064"
        " 130200010064 1302ff010064"
        # Lamp levels the snapshot adds: 50 and the held adjustment's 85 down to 60.
        " 130232010064 130255010064 130250010064 13024b010064 130246010064 130241010064"
        " 13023c010064"
    ),
}

FROZEN_REPORTS: frozenset[str] = _frames("0a0503080175 10ff30753075 109981388113")
