"""Ronco Motion 1.2 profile tables in the shared Richmat guide."""

from custom_components.adjustable_bed.codec import richmat as richmat_codec
from custom_components.adjustable_bed.profiles import ronco_motion as ronco_profiles
from scripts.codec_docs._common import _block, _hex, _table


def render_ronco_motion() -> str:
    return _block(
        _table(
            ("Layout", "Motors", "Light", "Bed type"),
            (
                (
                    p.label,
                    ", ".join(p.motors),
                    "toggle" if p.light else "absent",
                    "ronco_motion:" + p.key,
                )
                for p in ronco_profiles.PROFILES.values()
            ),
        ),
        _table(
            ("Action", "Frame", "Layouts"),
            (
                *(
                    (
                        f"{key} {direction}",
                        _hex(richmat_codec.command(codes[i])),
                        "PREMIUM" if key == "pillow" else "both",
                    )
                    for key, codes in ronco_profiles.MOTORS.items()
                    for i, direction in enumerate(("up", "down"))
                ),
                *(
                    (
                        key,
                        _hex(richmat_codec.command(code)),
                        "PREMIUM" if key == "light_toggle" else "both",
                    )
                    for key, code in ronco_profiles.SHORT.items()
                ),
                ("SHORT trailer only", _hex(ronco_profiles.END), "both"),
            ),
        ),
        _table(
            ("Schedule", "Milliseconds", "Frames"),
            (
                (
                    "Held refresh; no release frame",
                    str(ronco_profiles.PROFILES["economy"].refresh_ms),
                    "motor frame",
                ),
                (
                    "SHORT trailer after completed write",
                    str(ronco_profiles.PROFILES["economy"].short_ms),
                    _hex(ronco_profiles.END),
                ),
                (
                    "Startup post-write spacing",
                    str(ronco_profiles.PROFILES["economy"].startup_ms),
                    ", ".join(_hex(frame) for frame in ronco_profiles.STARTUP),
                ),
                (
                    "Alarm post-write spacing, including last",
                    str(ronco_profiles.PROFILES["economy"].alarm_ms),
                    "countdown low byte then high byte + preset",
                ),
            ),
        ),
        _table(
            ("Service", "Write", "Notify/indicate"),
            ((t.service_uuid, t.write_uuid, t.notify_uuid) for t in ronco_profiles.TRANSPORTS),
        ),
        _table(
            ("Once-alarm example", "Frames"),
            (
                (
                    str(minutes) + " min, " + preset,
                    ", ".join(
                        _hex(frame)
                        for frame in richmat_codec.countdown(minutes, ronco_profiles.SHORT[preset])
                    ),
                )
                for minutes, preset in ((525, "zero_g"), (1440, "memory"), (1, "anti_snore"))
            ),
        ),
        _table(
            ("Delete alarm", "Frames"),
            (("Delete", ", ".join(_hex(frame) for frame in richmat_codec.countdown(0, 0))),),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "ronco-motion", render_ronco_motion)]
