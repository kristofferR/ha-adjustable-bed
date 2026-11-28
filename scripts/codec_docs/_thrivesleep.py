"""Tables for the Thrive Sleep profiles over the shared Richmat codec."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import thrivesleep as app
from scripts.codec_docs._common import Block, _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Product", "Controls", "Alarm modes"),
            (
                (
                    p.label,
                    ", ".join(app.ACTIONS[k].label for k in p.actions),
                    ", ".join(app.ACTIONS[k].label for k in p.alarms),
                )
                for p in app.PROFILES.values()
            ),
        ),
        _table(
            ("Route", "Service", "Write", "Nominal notify", "Generic encoding"),
            (
                (
                    key,
                    f"`{r.service_uuid}`",
                    f"`{r.write_uuid}`",
                    f"`{r.notify_uuid}`",
                    "raw" if r.single else "framed",
                )
                for key in app.ROUTES
                for r in (codec.TRANSPORTS[key],)
            ),
        ),
        _table(
            ("Action", "Raw", "Framed", "Save raw", "Save framed"),
            (
                (
                    a.label,
                    _hex(codec.function(a.code, single=True)),
                    _hex(codec.function(a.code)),
                    _hex(codec.function(a.alternate, single=True))
                    if a.alternate is not None
                    else "none",
                    _hex(codec.function(a.alternate)) if a.alternate is not None else "none",
                )
                for a in app.ACTIONS.values()
            ),
        ),
        _table(
            ("Startup/release", "Raw", "Framed"),
            (
                (
                    name,
                    _hex(codec.function(code, single=True, action=name)),
                    _hex(codec.function(code, action=name)),
                )
                for name, code in (*app.STARTUP, ("STOP", codec.STOP))
            ),
        ),
        _table(
            ("Setting", "Frame/example"),
            (
                ("Light timer: always on", _hex(codec.light_timer(255, 255))),
                ("Light timer: 300 seconds", _hex(codec.light_timer(1, 44))),
                ("RGB: 1,2,3", _hex(codec.rgb(1, 2, 3))),
                ("Repeat alarm list", _hex(codec.record_20_len(5, 1, 0, (0,)))),
                ("Delete alarm 1", _hex(codec.record_20_len(5, 2, 1, (1,)))),
                (
                    "Alarm 1: 07:30, Zero Gravity, Mon-Fri, enabled",
                    _hex(codec.record_20_len(5, 1, 1, (1, 0, 7, 30, 69, 249))),
                ),
                ("Anti-snore query", _hex(codec.record_20_len(6, 1, 0, (0,)))),
                ("Anti-snore on", _hex(codec.record_20_len(6, 1, 1, (0, 1)))),
                ("Sleep name query", _hex(codec.record_20_len(6, 3, 0, (0,)))),
                ("ECO therapy close", _hex(codec.record_20_len(4, 4, 1, (0, 0)))),
                *(
                    ("ECO therapy " + name, _hex(codec.record_20_len(4, 1, 1, (0, *rgb))))
                    for name, rgb in app.THERAPY.items()
                ),
            ),
        ),
        _table(
            ("Timing/field", "Value"),
            (
                ("Held refresh and queue cycle", f"{app.TICK_S * 1000:g} ms"),
                ("Capability query startup delay", f"{app.STARTUP_DELAY_S:g} s"),
                ("Residual receive buffer", f"{app.RESIDUAL_EXPIRY_S * 1000:g} ms"),
                ("App alternate long press", f"{app.LONG_PRESS_MS} ms"),
                ("Light timer range", "0–900 s; zero maps to FFFF"),
                ("Repeat bits", "Monday bit 7 through Sunday bit 1; enabled bit 0"),
            ),
        ),
    )


BLOCKS: list[Block] = [("docs/beds/richmat.md", "thrivesleep", render)]
