"""Dreamotion Smart's app-specific Jiecang records, built from shipping code."""

from custom_components.adjustable_bed.codec import jiecang as codec
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    rows = []
    for axis in app.AXES:
        for up in (True, False):
            rows.append(
                (f"{axis} {'up' if up else 'down'}", _hex(codec.motion(axis, up, codec.BILATERAL)))
            )
    for name in codec.PRESET_OPCODES:
        rows.append((name, _hex(codec.preset(name, codec.BILATERAL))))
    for slot in (1, 2):
        for save in (False, True):
            rows.append(
                (
                    f"Memory {slot} {'save' if save else 'recall'}",
                    _hex(codec.memory(slot, save=save, payload=app.PROFILE.memory_payload)),
                )
            )
    rows.append(("Release", _hex(codec.LONG_RELEASE)))
    for op, name in ((0x40, "Human detection"), (0x43, "Light")):
        for value in (0, 1):
            rows.append((f"{name} {'on' if value else 'off'}", _hex(app.setting(op, value))))
    rows.extend(
        (
            ("Inherent vibration mode", _hex(app.setting(0x80, 0x32))),
            ("Acoustic vibration mode", _hex(app.setting(0x80, 0))),
        )
    )
    for name, command in (
        (
            "Massage record (back=1, foot=2, pattern=1, timer=30 min)",
            app.Massage(1, 2, 1, 3).frame(),
        ),
        ("Timed RGB (100%, red, 300 s)", app.timed(app.Color(100, 255, 0, 0), 300)),
        (
            "Saved RGB entries (red/green/blue)",
            app.slots(
                (app.Color(100, 255, 0, 0), app.Color(50, 0, 255, 0), app.Color(25, 0, 0, 255))
            ),
        ),
        ("Preview entry (red)", app.preview(app.Color(100, 255, 0, 0))),
    ):
        rows.append((name, _hex(command)))
    for op in (0, 0x43, 0x40, 0x80, 0x81, 0x45, 0x44):
        rows.append((f"Query {op:02X}", _hex(app.query(op))))
    transport = _table(
        ("Role", "UUID"), (("Service", app.SERVICE), ("Write", app.WRITE), ("Notify", app.NOTIFY))
    )
    timing = _table(
        ("Action", "Timing"),
        (
            ("Movement refresh", f"{app.PROFILE.hold.repeat_ms} ms"),
            ("Movement release", f"{app.PROFILE.hold.releases[0][0]} ms after refresh ends"),
            ("Presets and memory", "One write, no release"),
            (
                "Main queries",
                ", ".join(f"{frame[2]:02X} at {offset} ms" for offset, frame in app.MAIN_QUERIES),
            ),
            (
                "Massage page queries",
                ", ".join(
                    f"{frame[2]:02X} at {offset} ms" for offset, frame in app.MASSAGE_QUERIES
                ),
            ),
            ("Light durations (seconds)", ", ".join(map(str, app.DURATIONS))),
        ),
    )
    return _block(transport, _table(("Control / example", "Bytes (hex)"), rows), timing)
