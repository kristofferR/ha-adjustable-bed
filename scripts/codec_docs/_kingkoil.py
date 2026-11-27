"""King Koil command table from its app profiles and existing P2 codec."""

from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.profiles import kingkoil as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    rows = []
    for selector, layout in app.LAYOUTS.items():
        for axis, up, down in layout.axes:
            for direction, word in (("up", up), ("down", down)):
                rows.append(
                    (
                        selector,
                        f"{axis} {direction}",
                        _hex(encode(layout.profile, word)),
                        "held, 300 ms",
                    )
                )
        for action, word in layout.profile.presets.items():
            rows.append((selector, action, _hex(encode(layout.profile, word)), "once"))
        for action, word in layout.actions.items():
            timing = "held, 300 ms" if action == "light" and layout.held_light else "once"
            rows.append((selector, action, _hex(encode(layout.profile, word)), timing))
        rows.append((selector, "status query", _hex(codec.STATUS_QUERY), "500 ms live poll"))
    return "\n".join(_table(("Saved app selector", "Control", "Frame", "Timing"), rows))


BLOCKS = [("docs/beds/keeson.md", "keeson-kingkoil", render)]
