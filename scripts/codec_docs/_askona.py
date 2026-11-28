"""Askona's accepted model, transport and command tables."""

from custom_components.adjustable_bed.profiles import askona as app
from custom_components.adjustable_bed.profiles.keeson import KeesonCommands as K
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _block, _hex, _table


def render_askona() -> str:
    profile = app.PROFILES["633"]
    return _block(
        _table(
            (
                "Model",
                "Head / foot maximum (degrees)",
                "Raw massage levels",
                "Flat / Relax / Zero G / TV positions",
            ),
            (
                (
                    app.MODEL_CHOICES[key],
                    f"{p.max_head} / {p.max_foot}",
                    str(p.massage_values),
                    str(p.preset_positions),
                )
                for key, p in app.PROFILES.items()
            ),
        ),
        _table(
            ("Control", "Frame"),
            (
                ("Flat (custom zero target)", _hex(app.target(0, 0))),
                *((name, _hex(encode(profile, word))) for name, word in profile.presets.items()),
                *(
                    (name, _hex(encode(profile, word)))
                    for name, word in (
                        ("Head massage increase", K.MASSAGE_HEAD_UP),
                        ("Head massage decrease", K.MASSAGE_HEAD_DOWN),
                        ("Foot massage increase", K.MASSAGE_FOOT_UP),
                        ("Foot massage decrease", K.MASSAGE_FOOT_DOWN),
                        ("Combined massage", K.MASSAGE_STEP),
                        ("Massage timer cycle", K.MASSAGE_TIMER_STEP),
                        ("Light toggle", K.TOGGLE_LIGHTS),
                    )
                ),
                ("Example target (21, 37), 633", _hex(app.target(21, 37))),
            ),
        ),
        _table(
            ("Role", "Service", "Characteristic"),
            (
                ("Write", app.WRITE_SERVICE, app.WRITE_UUID),
                ("Notify", app.NOTIFY_SERVICE, app.NOTIFY_UUID),
                ("Software version read", "0000180a-0000-1000-8000-00805f9b34fb", app.VERSION_UUID),
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-askona", render_askona)]
