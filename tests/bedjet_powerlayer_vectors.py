"""Frozen BedJet PowerLayer frames, the vectors the codec must reproduce.

No accepted APK Protocol Audit report covers the frame. Its command opcode and
remote keys are ported from the MIT-licensed ``powerlayer`` branch of
https://github.com/natekspencer/ha-bedjet (``pybedjet/powerlayer.py`` and
``const.py``), and the contributor confirmed the frame answers them. These are
every frame the controller sent when it arrived from ``main`` (#891).
"""

from __future__ import annotations

FROZEN_FRAMES: dict[str, frozenset[str]] = {
    "powerlayer": frozenset(
        {
            # Movement: head up/down, foot up/down.
            "0102",
            "0103",
            "0104",
            "0105",
            # Presets: flat, anti-snore, zero gravity, TV.
            "0110",
            "0111",
            "0112",
            "0113",
            # Memory recall 1-3.
            "0120",
            "0121",
            "0122",
        }
    ),
}
