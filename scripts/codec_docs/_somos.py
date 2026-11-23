"""Somos profile tables, derived only from its shipped data and codec."""

from custom_components.adjustable_bed.profiles import somos as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    rows = []
    for variant, product in app.PRODUCTS.items():
        profile = product.profile
        for axis, up, down in product.axes:
            for direction, word in (("up", up), ("down", down)):
                rows.append(
                    (
                        product.label,
                        f"{axis} {direction}",
                        _hex(encode(profile, word)),
                        f"held, {product.initial_ms} ms then 300 ms",
                    )
                )
        for preset, word in profile.presets.items():
            rows.append((product.label, preset, _hex(encode(profile, word)), "once"))
        for slot, word in profile.memory.items():
            rows.append(
                (
                    product.label,
                    "favorite M" if variant == "d" else f"memory {slot}",
                    _hex(encode(profile, word)),
                    "once",
                )
            )
        if product.massage:
            for action, word in {**app.MASSAGE_ACTIONS, "light": app.LIGHT_BUTTON}.items():
                rows.append((product.label, action, _hex(encode(profile, word)), "once"))
        if product.query:
            rows.append((product.label, "status query", _hex(product.query), "after 2 s, then 1 s"))
    return "\n".join(_table(("Product", "Control", "Frame", "Timing"), rows))


BLOCKS = [("docs/beds/keeson.md", "keeson-somos", render)]
