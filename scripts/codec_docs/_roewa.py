"""Generate the RÖWA profile reference from its production codec and tables."""

from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.profiles import roewa as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    full = app.PROFILES["remote4Drive"]
    return _block(
        _table(
            ("Layout", "Stored variant", "Motors", "Memory slots"),
            (
                (p.name, f"`{p.key}`", ", ".join(p.axes), str(p.memory_slots))
                for p in app.PROFILES.values()
            ),
        ),
        _table(
            ("Action", "Frame", "Layouts"),
            (
                (
                    key.replace("_", " ").capitalize(),
                    _hex(codec.frame(word, full.width)),
                    ", ".join(p.key for p in app.PROFILES.values() if key in p.keys),
                )
                for key, word in full.keys.items()
            ),
        ),
        _table(
            ("Role", "Characteristic", "Mode"),
            (
                ("Movement / controls", f"`{app.WRITE_UUID}`", "Write with response"),
                ("Feedback", f"`{app.FEEDBACK_UUID}`", "Read property; notify or indicate"),
                ("Firmware", f"`{app.FIRMWARE_UUID}`", "UTF-8 read, required nonempty"),
                ("Model", f"`{app.MODEL_UUID}`", "UTF-8 read, required nonempty"),
                ("Bluetooth name", f"`{app.NAME_UUID}`", "Write with response"),
            ),
        ),
        _table(
            ("Operation", "Value"),
            (
                ("Scan service alternatives", ", ".join(f"`{u}`" for u in app.SCAN_SERVICES)),
                ("Reconnect startup", _hex(app.INITIALIZE) + ", once after subscription"),
                ("Connection timeout", f"{bed_traits('roewa').connection_timeout} seconds"),
                ("Held refresh", f"Await write completion, then {app.REFRESH_MS} ms"),
                ("One-shot latch", f"{app.LATCH_MS} ms; HA also awaits delivery"),
                ("Release / explicit Stop", "End refresh; no packet"),
                ("Rename example: AB", _hex(app.rename_frame("AB"))),
                ("Light feedback mask", f"`0x{app.COMMON['light_toggle']:08X}`"),
                ("Memory-store feedback mask", f"`0x{app.COMMON['memory_store']:08X}`"),
            ),
        ),
    )
