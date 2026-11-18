"""Ormatek's profile tables in the shared Keeson guide."""

from custom_components.adjustable_bed.profiles import ormatek as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Command", "Okin", "SmartBed"),
            (
                (action, _hex(app.normal("okin15", action)), _hex(app.normal("okin24", action)))
                for action in app.WORDS
            ),
        ),
        "Both formats write without response. The last supported write service selects its complete write/notify tuple: FFE5/FFE9 with FFE0/FFE4, or Nordic UART 6E400001 with 6E400002 write and 6E400003 notify. This does not select a layout or packet format.",
        "Clock sync uses local time. Okin carries year minus 1900 and zero-based month in the checked E7 80 01 record. SmartBed carries year minus 2000, month, day, weekday (Monday 1 through Sunday 7), hour, minute and second in the 07 04 record.",
        _table(
            ("Layout", "Alarm wake choices"),
            (
                (app.LAYOUTS[layout], ", ".join(choices))
                for layout, choices in app.WAKE_CHOICES.items()
            ),
        ),
        "The shared set_alarm action configures one daily alarm, slot one only. Okin encodes both record positions with the second disabled; it then queries immediately and after 100 and 200 ms. SmartBed writes slot one and queries 00 C0 and 00 D0 after 100 ms. Weekly masks and the second-slot builder are not selectable controls.",
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-ormatek", render)]
