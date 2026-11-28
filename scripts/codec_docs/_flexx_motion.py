"""Flexx Motion preset reference; no runnable bed route is registered."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import flexx_motion as profile
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Product menu", "Preset subset"),
            ((s.product, ", ".join(p.label for p in s.presets)) for s in profile.SUBSETS),
        ),
        _table(
            ("Preset operation", "Nordic", "Framed, side 0", "Framed, side 1"),
            (
                (
                    f"{preset.label}: {operation}",
                    _hex(codec.function(code, single=True)),
                    _hex(codec.function(code, 0)),
                    _hex(codec.function(code, 1)),
                )
                for preset in profile.PRESETS
                for operation, code in (("recall", preset.recall), ("save", preset.save))
                if code is not None
            ),
        ),
        _table(
            ("Catalog route", "Service", "Write hint", "Nominal notify hint"),
            (
                (
                    key,
                    f"`{codec.TRANSPORTS[key].service_uuid}`",
                    f"`{codec.TRANSPORTS[key].write_uuid}`",
                    f"`{codec.TRANSPORTS[key].notify_uuid}`",
                )
                for key in profile.CATALOG_TRANSPORTS
            ),
        ),
        _table(
            ("Path", "Schedule"),
            (
                (
                    "Preset callback",
                    f"{profile.PRESET_WRITES} queued write; "
                    + ("release frame" if profile.PRESET_RELEASE else "no release frame"),
                ),
                ("Normal queue scheduling cycle", f"{profile.QUEUE_CYCLE_MS} ms"),
                ("Residual receive-data expiry", f"{profile.RECEIVE_EXPIRY_S:g} s"),
            ),
        ),
    )
