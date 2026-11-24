"""Dorsal controls and setup frames from the runtime profiles."""

from custom_components.adjustable_bed.beds.dorsal.controls import label, wake_modes
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.discovery_hints.dorsal import DORSAL_TRANSPORTS
from custom_components.adjustable_bed.profiles import dorsal
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    products = dorsal.products()
    restored = {item for product in products.values() for item in product.controls}

    def opcode(pair: dorsal.Opcode | None, *, framed: bool) -> str:
        if pair is None:
            return ""
        return _hex(richmat.function(pair[1] if framed else pair[0], single=not framed))

    def controls(rows: tuple[dorsal.Control, ...], *, framed: bool) -> list[str]:
        return _table(
            ("Control", "Tap", "Refresh", "Alternate"),
            (
                (
                    label(item),
                    *(
                        opcode(value, framed=framed)
                        for value in (item.short, item.sustain, item.long)
                    ),
                )
                for item in rows
            ),
        )

    return _block(
        _table(
            ("GATT mode", "Service", "Exact writer", "Reference RX"),
            (
                (
                    key.upper(),
                    f"`{route.service_uuid}`",
                    f"`{route.write_uuid}`",
                    f"`{route.notify_uuid}`",
                )
                for key in DORSAL_TRANSPORTS
                if (route := richmat.TRANSPORTS[key])
            ),
        ),
        _table(
            ("Startup request", "Nordic", "Framed"),
            (
                (
                    action.removeprefix("deviceFunctionItem"),
                    _hex(richmat.function(code, action=action, single=True)),
                    _hex(richmat.function(code, action=action)),
                )
                for action, code in dorsal.PROFILE_PROBES
            ),
        ),
        "##### CPRN operations (framed)",
        controls(products["CPRN"].controls, framed=True),
        "##### CORN operations (framed)",
        controls(products["CORN"].controls, framed=True),
        "##### Roomi fixed frames",
        controls(dorsal.ROOMI, framed=True),
        "##### Restored control operands",
        _table(
            ("Control", "Tap N1 / P2", "Refresh N1 / P2", "Alternate N1 / P2"),
            sorted(
                {
                    (
                        label(item),
                        *(
                            " / ".join(f"`{value:02X}`" for value in pair) if pair else ""
                            for pair in (item.short, item.sustain, item.long)
                        ),
                    )
                    for item in restored
                }
            ),
        ),
        "##### Repeating alarm selectors",
        _table(
            ("Wake action", "Selector", "Saved projects"),
            (
                (f"`{name}`", f"`{wire:02X}`", ", ".join(names))
                for (name, wire), names in _alarm_projects().items()
            ),
        ),
    )


def _alarm_projects() -> dict[tuple[str, int], list[str]]:
    groups: dict[tuple[str, int], list[str]] = {}
    for code, product in dorsal.products().items():
        for action, selector in wake_modes(product.alarm_modes).items():
            groups.setdefault((action, selector), []).append(code)
    return dict(sorted(groups.items()))
