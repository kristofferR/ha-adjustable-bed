"""Purely Sleep's bounded normal profile command reference."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.purely_sleep import INITIALIZATION, PROFILES
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    labels = {
        "head_up": "Head up",
        "head_down": "Head down",
        "feet_up": "Foot up",
        "feet_down": "Foot down",
        "head_feet_up": "Head and foot up",
        "head_feet_down": "Head and foot down",
        "flat": "Flat / reset",
        "tv": "TV",
        "anti_snore": "Anti-snore",
        "lounge": "Lounge",
        "zero_g": "Zero gravity",
    }
    rows = []
    for profile in PROFILES.values():
        assert profile.codes is not None and profile.stop is not None
        commands = [
            *((labels[key], code) for key, code in profile.codes.items()),
            ("Recall M1", profile.memory[0][0]),
            ("Save M1", profile.memory[0][1]),
            *((f"Save {label}", code) for _, label, code in profile.saves),
            ("Release / STOP", profile.stop),
        ]
        rows.extend(
            (
                profile.label,
                label,
                _hex(codec.function(code)),
                _hex(codec.function(code, single=True)),
            )
            for label, code in commands
        )
    return _block(
        _table(("Product", "Action", "Framed, left", "Nordic"), rows),
        _table(
            ("Initialization / query", "Framed", "Nordic"),
            (
                (
                    action.removeprefix("deviceFunctionItem"),
                    _hex(codec.function(code, action=action)),
                    _hex(codec.function(code, action=action, single=True)),
                )
                for action, code in INITIALIZATION
            ),
        ),
        _table(
            ("Route", "Service", "Write", "Declared notify"),
            (
                (key, f"`{route.service_uuid}`", f"`{route.write_uuid}`", f"`{route.notify_uuid}`")
                for key in PROFILES["JLRN"].transports
                for route in (codec.TRANSPORTS[key],)
            ),
        ),
        _table(
            ("Product", "Held refresh", "Recall / save count"),
            (
                (profile.label, f"{profile.motor_repeat_ms} ms", "1, without appended STOP")
                for profile in PROFILES.values()
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "purely-sleep", render)]
