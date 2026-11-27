"""AW MOTION tables generated from its own typed product profiles."""

from custom_components.adjustable_bed.beds.dreamsense.protocol import light_seconds
from custom_components.adjustable_bed.beds.dreamsense.transport import LIKIMIO_ROUTES
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.awmotion import CHOICES, PROFILES, SCAN_WORDS
from custom_components.adjustable_bed.profiles.dreamsense import PROBE_MS, TICK_MS
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        "##### Products and controls",
        _table(
            ("Model", "Control", "Nordic", "Other services", "Save, Nordic / framed", "Delivery"),
            (
                (
                    CHOICES[key],
                    a.label,
                    _hex(profile.frame(a.code, single=True)),
                    _hex(profile.frame(a.code, single=False)),
                    " / ".join(
                        (
                            _hex(profile.frame(a.save, single=True)),
                            _hex(profile.frame(a.save, single=False)),
                        )
                    )
                    if a.save is not None
                    else "None",
                    (
                        f"First tick and refresh {TICK_MS} ms; STOP"
                        if a.held
                        else "Once; STOP"
                        if a.release
                        else "Once; no STOP"
                    )
                    + (f"; save after {a.save_delay_ms} ms" if a.save is not None else ""),
                )
                for key, profile in PROFILES.items()
                for a in profile.controls
            ),
        ),
        "##### Discovery and GATT",
        "Case-sensitive name substrings: " + ", ".join(f"`{s}`" for s in SCAN_WORDS) + ".",
        _table(
            ("Service", "Write", "Basic commands"),
            (
                (f"`{service}`", f"`{write}`", "Raw" if single else "Framed")
                for service, write, single in LIKIMIO_ROUTES
            ),
        ),
        "##### Startup, release and settings",
        _table(
            ("Operation", "Nordic", "Other services"),
            (
                (
                    "STOP",
                    _hex(codec.function(codec.STOP, single=True)),
                    _hex(codec.function(codec.STOP)),
                ),
                (
                    "Exit limit",
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit", single=True)),
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit")),
                ),
                *(
                    (
                        f"Query {name}",
                        _hex(codec.function(1, single=True)),
                        _hex(codec.function(1, action="deviceFunctionItemCheck" + name)),
                    )
                    for name in ("Clock", "Light")
                ),
                (
                    "Direct light off",
                    _hex(codec.function(0x75, single=True)),
                    _hex(codec.function(0x75)),
                ),
                (
                    "Light duration, zero / 900 seconds",
                    "Same as other services",
                    _hex(light_seconds(0)) + " / " + _hex(light_seconds(900)),
                ),
                ("RGB example", "Same as other services", _hex(codec.rgb(18, 52, 86))),
                (
                    "Cancel countdown",
                    "Same as other services",
                    " then ".join(map(_hex, codec.countdown(0, 0))),
                ),
                (
                    "60 minute zero-gravity countdown",
                    "Same as other services",
                    " then ".join(
                        map(_hex, codec.countdown(60, PROFILES["SN300"].alarm["ZeroGravity"]))
                    ),
                ),
            ),
        ),
        f"Writes are paced at {TICK_MS} ms; capability probes at {PROBE_MS} ms. "
        "Light duration accepts 0–900 seconds; zero sends the always-on value.",
    )


BLOCKS = [("docs/beds/richmat.md", "awmotion", render)]
