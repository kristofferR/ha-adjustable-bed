"""M3 Ambient tables generated from the shipped profile and encoders."""

from custom_components.adjustable_bed.codec import ambient as p1
from custom_components.adjustable_bed.codec import ambient_climate as p2
from custom_components.adjustable_bed.profiles import ambient as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/ambient.md"


def transport() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            tuple(
                (role, f"`{uuid}`")
                for role, uuid in (
                    ("Service", app.SERVICE),
                    ("Write", app.WRITE),
                    ("Notify", app.NOTIFY),
                )
            ),
        )
    )


def commands() -> str:
    labels = {"flat": "Flat", "tv": "TV", "zero_g": "Zero Gravity", "anti_snore": "Anti-snore"}
    return _block(
        "### Motor Control and Presets",
        _table(
            ("Command", "One-piece", "Split left", "Split right"),
            tuple(
                (
                    labels[preset],
                    _hex(p1.position(coords)),
                    *(_hex(p1.position(coords, side)) for side in app.SIDES.values()),
                )
                for preset, coords in app.PRESETS.items()
            )
            + (("Home flat", _hex(p1.HOME_FLAT), "—", "—"),),
        ),
        "### Massage",
        _table(
            ("Level", "Shoulder", "Feet"),
            tuple(
                (str(level), _hex(p1.massage("shoulder", level)), _hex(p1.massage("feet", level)))
                for level in range(4)
            ),
        ),
        "### Lights",
        _table(
            ("Command", "Example frame"),
            (
                ("On", _hex(p1.LIGHT_ON)),
                ("Off", _hex(p1.LIGHT_OFF)),
                *(
                    (f"{channel.title()} channel at 120", _hex(p1.rgb(channel, 120)))
                    for channel in ("red", "green", "blue")
                ),
            ),
        ),
        "### Climate and Status",
        _table(
            ("Command", "Frame or example"),
            (
                ("Query combined bed state", _hex(p1.BED_STATE_QUERY)),
                *(
                    (f"Query {code.name.lower().replace('_', ' ')}", _hex(p2.query(code)))
                    for code in p2.Query
                ),
                (
                    "Six-zone target, all levels 0 (codec example)",
                    _hex(p2.heat((0, 0, 0, 0, 0, 0))),
                ),
                ("Start the two-hour heat timer", _hex(p2.heat_timer(app.HEAT_TIMER_HOURS))),
                ("Left fan off", _hex(p2.fan(p2.Query.LEFT_FAN, 0))),
                ("Right fan level 10", _hex(p2.fan(p2.Query.RIGHT_FAN, 10))),
            ),
        ),
    )


def timing() -> str:
    return _block(
        _table(
            ("Operation", "Timing"),
            (
                ("Minimum gap after a write", f"{app.WRITE_PACING * 1000:g} ms"),
                ("Initial position or heat sample", f"{app.SAMPLE_TIMEOUT:g} s"),
                (
                    "Heat confirmation",
                    f"Up to {app.HEAT_PROBES} probes, {app.HEAT_PROBE_INTERVAL * 1000:g} ms apart, with a {app.HEAT_TIMEOUT:g} s deadline",
                ),
                ("Optional heat timer", f"{app.HEAT_TIMER_DELAY:g} s after a matching report"),
            ),
        )
    )


BLOCKS: tuple[Block, ...] = (
    (GUIDE, "ambient-transport", transport),
    (GUIDE, "ambient-commands", commands),
    (GUIDE, "ambient-timing", timing),
)
