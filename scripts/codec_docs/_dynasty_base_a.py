"""Dynasty Base A guide tables, derived from its shipped profile and codec."""

from datetime import datetime

from custom_components.adjustable_bed.profiles import dynasty_base_a as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        "##### Layouts",
        _table(("App layout", "Controls"), ((key, label) for key, label in app.CHOICES.items())),
        "##### Transports",
        _table(
            (
                "Format",
                "Write service",
                "Write characteristic",
                "Receive service",
                "Receive characteristic",
            ),
            (
                (
                    route.upper(),
                    app.codec.TRANSPORTS[p.transport].service_uuid,
                    app.codec.TRANSPORTS[p.transport].write_uuid,
                    app.NOTIFY_SERVICE
                    if route == "p1"
                    else app.codec.TRANSPORTS[p.transport].service_uuid,
                    app.codec.TRANSPORTS[p.transport].notify_uuid,
                )
                for route, p in app.PROFILES.items()
            ),
        ),
        "##### Commands",
        _table(
            ("Control", "P1", "P2"),
            (
                (
                    key,
                    _hex(app.frame("p1", word)),
                    _hex(app.frame("p2", app.controls("p2", "40")[key])),
                )
                for key, word in app.controls("p1", "40").items()
            ),
        ),
        _table(
            ("Accessory", "P1", "P2"),
            (
                *(
                    (
                        key,
                        _hex(app.frame("p1", word)),
                        _hex(app.frame("p2", app.actions("p2")[key])),
                    )
                    for key, word in app.actions("p1").items()
                ),
                ("P2 massage power when on", "Unavailable", _hex(app.frame("p2", 0x2000000))),
                (
                    "Light toggle",
                    _hex(app.frame("p1", app.LIGHT)),
                    _hex(app.frame("p2", app.LIGHT)),
                ),
                ("Release", _hex(app.frame("p1", 0)), _hex(app.frame("p2", 0))),
            ),
        ),
        "##### Bed clock and alarm",
        _table(
            ("Operation", "Both formats"),
            (
                (
                    "Clock, 2026-11-27 06:30:00",
                    _hex(app.codec.clock(datetime(2026, 11, 27, 6, 30))),
                ),
                *(
                    (f"Alarm 06:30, weekdays, {wake}", _hex(app.alarm(6, 30, 0xBE, mode)))
                    for wake, mode in app.WAKE.items()
                ),
                ("Disable alarm", _hex(app.alarm(0, 0, 0, 0))),
            ),
        ),
        "##### Schedules",
        _table(
            ("Operation", "Schedule"),
            (
                (
                    "Movement",
                    f"Three zero words, refresh every {app.REFRESH_MS} ms, three zero words on cleanup",
                ),
                ("Preset / memory tap", "Three back-to-back action writes, one zero word"),
                (
                    "Preset / memory / combined Flat and zero gravity hold",
                    f"Refresh every {app.REFRESH_MS} ms, at most {app.PRESET_HOLD_MAX_MS} ms; end refresh without a release frame",
                ),
                ("Massage / light tap", "Three back-to-back action writes, two zero words"),
                ("P2 foot massage / massage power", "One write, no zero word"),
                ("P2 status", "Read after each write completion"),
                (
                    "Alarm enable / change",
                    f"Clock once, wait {app.ALARM_DELAY_S * 1000:g} ms, alarm once, zero word once",
                ),
                ("Alarm disable", "Zeroed alarm twice, zero word once"),
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-dynasty-base-a", render)]
