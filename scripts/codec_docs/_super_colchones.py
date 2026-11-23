"""Super Colchones tables rendered from its shipped profile and shared codec."""

from custom_components.adjustable_bed.beds.super_colchones.controller import DISPATCH_JITTER_S
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import super_colchones as app
from scripts.codec_docs._common import Block, _block, _hex, _table


def render() -> str:
    return _block(
        _table(("Product", "Metadata", "Controls"), (
            (p.label, p.metadata, ", ".join(app.ACTIONS[key].label for key in p.actions))
            for p in app.PROFILES.values()
        )),
        _table(("GATT route", "Service", "Write", "Nominal notify", "Wire"), (
            (key, f"`{route.service_uuid}`", f"`{route.write_uuid}`", f"`{route.notify_uuid}`", "framed" if key == "n1" else "raw")
            for key in app.ROUTES for route in (codec.TRANSPORTS[key],)
        )),
        _table(("Action", "Raw", "Framed", "Alternate raw", "Alternate framed", "Products"), (
            (item.label, _hex(codec.function(item.code, single=True)), _hex(codec.function(item.code)),
             _hex(codec.function(item.alternate, single=True)) if item.alternate is not None else "none",
             _hex(codec.function(item.alternate)) if item.alternate is not None else "none",
             ", ".join(p.label for p in app.PROFILES.values() if key in p.actions))
            for key, item in app.ACTIONS.items()
        )),
        _table(("Startup/release", "Raw", "Framed"), (
            (name, _hex(codec.function(code, action=name, single=True)), _hex(codec.function(code, action=name)))
            for name, code in (*app.STARTUP, ("STOP", codec.STOP))
        )),
        _table(("Timing", "Value"), (("Movement refresh", f"{app.TICK_S * 1000:g} ms"), ("App alternate threshold", f"{app.LONG_PRESS_MS} ms"), ("Residual expiry", f"{app.RESIDUAL_EXPIRY_S * 1000:g} ms"), ("HA scheduling allowance at exact end tick (not hardware timing)", f"{DISPATCH_JITTER_S * 1000:g} ms"))),
    )


BLOCKS: list[Block] = [("docs/beds/richmat.md", "super-colchones", render)]
