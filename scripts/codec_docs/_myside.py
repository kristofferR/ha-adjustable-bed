"""My Side's own product gates, codes and timing over the Richmat codec."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import myside as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    controls = {
        **{key: (value, None) for key, value in app.MOTORS.items()},
        **app.PRESETS,
        **{key: (value, None) for key, value in app.MASSAGE.items()},
    }
    return _block(
        _table(
            ("Product", "Memory slots", "Coaxing / massage / repeat alarms", "Sleep name"),
            (
                (p.label, str(p.memories), "Yes" if p.coaxing else "No", "Yes" if p.sleep else "No")
                for p in app.PROFILES.values()
            ),
        ),
        _table(
            ("Control", "Nordic", "Framed side 0", "Save opcode"),
            (
                (
                    name.replace("_", " "),
                    _hex(codec.function(code, single=True)),
                    _hex(codec.command(code)),
                    _hex(codec.function(save, single=True)) if save is not None else "None",
                )
                for name, (code, save) in controls.items()
            ),
        ),
        _table(
            ("Operation", "Nordic", "Framed side 0"),
            (
                (
                    "STOP",
                    _hex(codec.function(codec.STOP, single=True)),
                    _hex(codec.command(codec.STOP)),
                ),
                (
                    "Flat / timer long hold",
                    _hex(codec.function(0, single=True)),
                    _hex(codec.command(0)),
                ),
                *(
                    (
                        "Startup " + name,
                        _hex(codec.function(1, single=True)),
                        _hex(codec.function(1, action="deviceFunctionItemCheck" + name)),
                    )
                    for name in ("Clock", "Light", "Music")
                ),
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "myside-controls", render)]
