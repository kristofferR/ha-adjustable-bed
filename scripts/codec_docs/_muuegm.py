"""MUUEGM current product tables, generated from its own profile data."""

from custom_components.adjustable_bed.beds.dreamsense.muuegm import ROUTES
from custom_components.adjustable_bed.beds.dreamsense.muuegm_receive import LITERALS, Alarm
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.muuegm import PALETTE, PROFILES
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        "##### Products",
        _table(
            ("Product", "Alarm", "Dedicated lighting", "Side selector"),
            (
                (
                    key,
                    "Repeat, slots 1–7" if p.repeat else "Single" if p.clock else "None",
                    "Current reply required" if p.light else "None",
                    "None",
                )
                for key, p in PROFILES.items()
            ),
        ),
        "##### GATT routes",
        _table(
            ("Recognized service", "Qualifying writer", "Ordinary encoding"),
            (
                (f"`{service}`", f"`{write}`", "Single byte" if single else "Checksummed")
                for service, write, single in ROUTES
            ),
        ),
        "Only recognized services enter selection. The first qualifying write and notify handles "
        "are retained independently across the pass. The last recognized service selects ordinary "
        "encoding, independently of those handles. A writer needs the write property; when it "
        "also has write-without-response, writes use that mode. Notifications use the first notify "
        "property, irrespective of its UUID. Direct settings use the retained writer unchanged.",
        "##### Controls and preset saves",
        _table(
            ("Product", "Control", "Single byte", "Checksummed, side 0", "Save", "Release"),
            (
                (
                    key,
                    action.label,
                    _hex(codec.function(action.code, single=True)),
                    _hex(codec.function(action.code)),
                    _hex(codec.function(action.save)) if action.save is not None else "None",
                    "STOP" if action.release else "None",
                )
                for key, p in PROFILES.items()
                for action in p.controls
            ),
        ),
        "##### Startup and timing",
        _table(
            ("Operation", "Timing", "Single byte", "Checksummed"),
            (
                (
                    "Exit limit",
                    "After discovery/subscription",
                    _hex(codec.function(0, single=True)),
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit")),
                ),
                (
                    "Check clock",
                    "First menu tick, 300 ms",
                    _hex(codec.function(1, single=True)),
                    _hex(codec.function(1, action="deviceFunctionItemCheckClock")),
                ),
                (
                    "Check light",
                    "Second menu tick, 600 ms",
                    _hex(codec.function(1, single=True)),
                    _hex(codec.function(1, action="deviceFunctionItemCheckLight")),
                ),
                (
                    "STOP",
                    "After delivered movement, Reset, massage or ordinary light",
                    _hex(codec.function(codec.STOP, single=True)),
                    _hex(codec.function(codec.STOP)),
                ),
            ),
        ),
        "Direction controls first send at 100 ms and refresh every 100 ms. Reset, massage and the "
        "ordinary ABF03 light send immediately once and release with STOP. Preset recall sends once; "
        "saving waits 3000 ms, then sends once, without STOP. The writer spaces packets by 100 ms. "
        "Light duration waits 200 ms. Repeat save, enable and delete refresh the list after 200 ms. "
        "ABF03 and ABF07 send the two clock synchronization records before menu queries.",
        "##### Light palette and duration",
        _table(
            ("Color", "RGB", "One write"),
            ((name, str(rgb), _hex(codec.rgb(*rgb))) for name, rgb in PALETTE.items()),
        ),
        _table(
            ("Seconds", "Frame"),
            (
                (str(n), _hex(codec.light_timer(n >> 8, n) if n else codec.light_timer(255, 255)))
                for n in range(0, 901, 60)
            ),
        ),
        "##### Alarm modes",
        _table(
            ("Product", "Wake action", "Mode"),
            (
                (key, name, f"`{code:02X}`")
                for key, p in PROFILES.items()
                for name, code in p.alarm.items()
            ),
        ),
        "##### Alarm and clock records",
        _table(
            ("Operation", "Fields / encoding"),
            (
                ("Single alarm", "6E 05 minutes-low 00 sum8, then 6E 06 minutes-high mode sum8"),
                ("Single cancel", " then ".join(map(_hex, codec.countdown(0, 0)))),
                ("Repeat query", _hex(codec.record_20_len(5, 1, 0, (0,)))),
                ("Repeat save", "6E 20 0D 05 01 01 id reserved hour minute mode repeat-mask sum8"),
                ("Repeat example", _hex(Alarm(1, 0, 7, 30, 69, 249).frame())),
                ("Repeat delete", "6E 20 08 05 02 01 id sum8"),
                (
                    "Clock epoch / zone",
                    "6E 20 0C 08 02 01 epoch-seconds-BE4 whole-hour-offset sum8",
                ),
                (
                    "Clock calendar",
                    "6E 20 0D 08 03 01 year-minus-1970 month day hour minute second sum8",
                ),
            ),
        ),
        "##### Exact acknowledgements",
        _table(
            ("Event", "Frame"),
            (
                (event, _hex(bytes.fromhex(frame)))
                for frame, (event, scope) in LITERALS.items()
                if scope != "EXCLUDED"
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "muuegm", render)]
