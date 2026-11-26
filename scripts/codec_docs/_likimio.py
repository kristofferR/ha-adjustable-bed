"""Command tables for Likimio's ABM10 and no-product profiles."""

from custom_components.adjustable_bed.beds.dreamsense.protocol import light_seconds
from custom_components.adjustable_bed.beds.dreamsense.receive import SIGNALS
from custom_components.adjustable_bed.beds.dreamsense.transport import LIKIMIO_ROUTES
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.dreamsense import PROBE_MS, TICK_MS
from custom_components.adjustable_bed.profiles.likimio import ABM10, PROFILES
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    profile = PROFILES[ABM10]
    return _block(
        "##### GATT routes",
        _table(
            ("Service", "Write", "Generic commands"),
            (
                (f"`{service}`", f"`{write}`", "Single byte" if single else "Checksummed")
                for service, write, single in LIKIMIO_ROUTES
            ),
        ),
        "##### ABM10 controls",
        _table(
            ("Control", "Nordic", "W1–W5", "Release"),
            (
                (
                    action.label,
                    _hex(profile.frame(action.code, single=True)),
                    _hex(profile.frame(action.code, single=False)),
                    "STOP" if action.release else "None",
                )
                for action in profile.controls
            ),
        ),
        "##### Save presets",
        _table(
            ("Preset", "Nordic", "W1–W5"),
            (
                (
                    action.label,
                    _hex(profile.frame(action.save, single=True)),
                    _hex(profile.frame(action.save, single=False)),
                )
                for action in profile.controls
                if action.save is not None
            ),
        ),
        "##### Setup, release and settings",
        _table(
            ("Operation", "Nordic", "W1–W5"),
            (
                (
                    "STOP",
                    _hex(codec.function(codec.STOP, single=True)),
                    _hex(codec.function(codec.STOP)),
                ),
                (
                    "Exit limit",
                    "`00`",
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit")),
                ),
                *(
                    (name, "`01`", _hex(codec.function(1, action="deviceFunctionItemCheck" + name)))
                    for name in ("Clock", "Light", "Music")
                ),
                ("Light off", _hex(codec.function(0x75, single=True)), _hex(codec.function(0x75))),
                (
                    "Light duration, 0 or 300 seconds",
                    "Same as W1–W5",
                    f"{_hex(light_seconds(0))} / {_hex(light_seconds(300))}",
                ),
                ("RGB color, red example", "Same as W1–W5", _hex(codec.rgb(255, 0, 0))),
                (
                    "Cancel alarm (no product)",
                    "Same as W1–W5",
                    " then ".join(map(_hex, codec.countdown(0, 0))),
                ),
            ),
        ),
        f"Direction commands first send at {TICK_MS} ms and refresh at {TICK_MS} ms intervals. "
        f"Clock, Light and Music probes are paced at {PROBE_MS} ms intervals after Exit limit.",
        "##### Capability and alarm replies",
        _table(
            ("Reply", "Frame"),
            (
                (signal.replace("_", " ").capitalize(), _hex(frame))
                for frame, signal in SIGNALS.items()
                if signal in ("light", "clock", "alarm_cancelled")
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "likimio", render)]
