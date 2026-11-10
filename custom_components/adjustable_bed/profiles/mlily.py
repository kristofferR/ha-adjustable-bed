"""MLILY Control 5.0.2/code50200, accepted APK Protocol Audit row159.

The compact app catalog comes from the frozen reconciliation002 inputs. It
retains product identities and ordered control occurrences, not presumed
hardware aliases. Load it in the controller builder's executor.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from ..catalog_json import Node, load
from .richmat import MLILY
from .richmat_app import Action, AppCatalog, Product


def _action(n: Node) -> Action:
    label, gesture, local, force, toggle, flagged, short, long, nordic, hidden, enabled, recovered = n.row(12)
    return Action(
        label.text(), gesture.text(), local.flag(), force.flag(), toggle.flag(), flagged.flag(),
        short.integer(), long.integer(), nordic.integer(), hidden.flag(), enabled.flag(),
        None if recovered.value is None else recovered.integer(),
    )


def _strings(n: Node) -> tuple[str, ...]:
    return tuple(item.text() for item in n.items())


def _product(n: Node) -> Product:
    label, controls, alarms, sides, light, display, repeat, sleep, timer = n.row(9)
    return Product(
        label.text(), _strings(controls), _strings(alarms),
        tuple(side.integer() for side in sides.items()), light.flag(), display.text(),
        repeat.flag(), sleep.text(), timer.flag(),
    )


@cache
def catalog() -> AppCatalog:
    """Read and validate this app only; shared constructors never choose its data."""
    data = load(Path(__file__).with_name("data"), "mlily").record(
        "actions", "products", "expansions", "remotes"
    )
    actions = {key: _action(row) for key, row in data["actions"].entries().items()}
    products = {key: _product(row) for key, row in data["products"].entries().items()}
    for route, target in data["remotes"].entries().items():
        products[route] = products[target.text()]
    return AppCatalog(
        MLILY, actions, products,
        {key: _strings(row) for key, row in data["expansions"].entries().items()},
        reply_gated_menus=True, mask_when_release=True, release_initially=False,
    )
