"""Smart Base's bounded fixed profile tables."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import smart_base as p

from ._common import _hex, _table


def render() -> str:
    rows = [
        (f"Motor {i} {direction}", _hex(codec.command(code)))
        for i, codes in enumerate(p.MOTORS, 1)
        for direction, code in zip(("up", "down"), codes, strict=True)
    ]
    rows.extend(
        (name.replace("_", " "), _hex(p.PROFILE.frame(code)))
        for name, code in (p.PROFILE.codes or {}).items()
    )
    assert p.PROFILE.stop is not None
    rows.append(("Release / STOP", _hex(p.PROFILE.frame(p.PROFILE.stop))))
    return (
        "\n".join(_table(("Action", "P1 value"), rows))
        + "\n\n"
        + "\n".join(
            _table(
                ("Setting", "Value"),
                [
                    ("Service", f"`{p.SERVICE}`"),
                    ("Write", f"`{p.TX}`"),
                    ("Notify", f"`{p.RX}`"),
                    ("Initialization", _hex(p.INITIALIZE)),
                    ("LED query", _hex(p.QUERIES[0])),
                    ("Aroma capability probe", _hex(p.QUERIES[1])),
                    ("RGB white (one write)", _hex(codec.rgb(255, 255, 255))),
                    ("Timeout: keep on", _hex(codec.light_timer(255, 255))),
                    ("Timeout: 300 seconds", _hex(codec.light_timer(1, 44))),
                    (
                        "Cancel alarm (separate writes)",
                        " / ".join(_hex(frame) for frame in codec.countdown(0, 0)),
                    ),
                    ("Held refresh / release delay", f"{p.TICK_MS} / {p.HELD_RELEASE_MS} ms"),
                    ("Tap release delay / save threshold", f"{p.TAP_RELEASE_MS} / {p.SAVE_MS} ms"),
                    (
                        "Initialization delay / query spacing / alarm spacing",
                        f"{p.STARTUP_MS} / {p.QUERY_MS} / {p.ALARM_MS} ms",
                    ),
                ],
            )
        )
    )


BLOCKS = [("docs/beds/richmat.md", "smart-base", render)]
