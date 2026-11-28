"""Generate the bounded MattressPoint profile reference from production data."""

from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.profiles import mattresspoint as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Box", "Motor controls"), ((box, ", ".join(p.axes)) for box, p in app.PROFILES.items())
        ),
        _table(
            ("Action", "Frame"),
            (
                *(
                    (f"{axis} {direction}", _hex(codec.frame40(word)))
                    for axis, words in app.MOTORS.items()
                    for direction, word in zip(("up", "down"), words, strict=True)
                ),
                ("STOP", _hex(app.STOP)),
                ("Light toggle", _hex(app.LIGHT)),
                *(
                    (f"Massage {name}", _hex(codec.frame40(word)))
                    for name, word in app.MASSAGE.items()
                ),
                ("Massage query", _hex(app.MASSAGE_QUERY)),
                ("Alarm query", _hex(app.ALARM_QUERY)),
                ("Disable alarm", _hex(app.ALARM_DISABLE)),
            ),
        ),
        _table(
            ("Operation", "Timing"),
            (
                ("Held movement", f"Immediate, then every {app.REFRESH_MS} ms until release"),
                ("Release", f"STOP after {app.RELEASE_MS} ms"),
                (
                    "Clock sync",
                    "On connect after 200 ms; manual sync also available; writes at "
                    + str(app.CLOCK_OFFSETS)
                    + " ms",
                ),
                ("Alarm disable", "Immutable writes at " + str(app.ALARM_OFFSETS) + " ms"),
                ("Alarm query", "Writes at " + str(app.QUERY_OFFSETS) + " ms"),
                ("Massage and light controls", "One write; no unproven delayed refresh"),
            ),
        ),
    )
