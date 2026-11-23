"""Galaxy Bed Control 3.3.0/330002 product and copied-configuration records.

Accepted primary arm64 evidence, row A09. Products keep independent selectors;
shared constructors and getters are not treated as product aliases. The compact
catalog is data extracted from CATALOG-JOIN, ACTION-JOIN and RUNTIME-JOIN.
"""

from __future__ import annotations

from pathlib import Path

from ...catalog_json import Node, load
from ...codec import richmat as codec
from ...profiles.richmat import GALAXY
from ...profiles.richmat_catalog import Action, Catalog, Product, Runtime


def _action(node: Node) -> Action:
    row = node.row(9)
    return Action(
        row[0].text(),
        row[1].text(),
        row[2].flag(),
        row[3].flag(),
        row[4].flag(),
        row[5].flag(),
        row[6].integer(),
        row[7].integer(),
        row[8].integer(),
    )


def _product(node: Node) -> Product:
    row = node.row(9)
    return Product(
        row[0].text(),
        tuple(item.text() for item in row[1].items()),
        tuple(item.text() for item in row[2].items()),
        tuple(item.integer() for item in row[3].items()),
        row[4].flag(),
        row[5].text(),
        row[6].flag(),
        row[7].text(),
        row[8].flag(),
    )


def _runtime(node: Node) -> Runtime:
    data = node.entries()
    advanced = data["advanced"].entries()
    targets: list[str] = []
    for item in data["remote_targets"].items():
        target = item.entries()
        if "code" in target:
            if target["support_gate_passes"].flag():
                targets.append(target["code"].text())
        else:
            targets.extend((target["confirm"].text(), target["other_button"].text()))
    return Runtime(
        data["code"].text(),
        data["route"].text(),
        tuple(targets),
        data["initial_release"].flag(),
        tuple(item.text() for item in advanced["query_order"].items()),
        advanced["time_zone_sync"].flag(),
        advanced["sleep_adv_query"].flag(),
        advanced["initial_alarm_menu"].flag(),
        advanced["snore_menu_after_name"].flag(),
    )


_DATA = load(Path(__file__).parent, "products").record(
    "actions", "products", "metadata", "selectors"
)
ACTIONS = {key: _action(value) for key, value in _DATA["actions"].entries().items()}
PRODUCTS = {key: _product(value) for key, value in _DATA["products"].entries().items()}
RUNTIMES = {key: _runtime(value) for key, value in _DATA["metadata"].entries().items()}
SELECTORS = tuple(
    (row[0].text(), row[1].text(), row[2].flag(), row[3].text())
    for node in _DATA["selectors"].items()
    if (row := node.row(4))
)
CATALOG = Catalog(
    "galaxy",
    "Galaxy Bed Control",
    GALAXY,
    ACTIONS,
    PRODUCTS,
    {},
    record=codec.record,
    substitute_when_release=True,
    notification_menus=True,
    runtimes=RUNTIMES,
    timer_codes={
        "D1RM": {0: 0x5E, 10: 0x5F, 20: 0x63, 30: 0x61},
        "D9RM": {0: 0x8B, 10: 0x5F, 20: 0x63, 30: 0x61},
    },
)
del _DATA


PICKERS = {
    key: runtime.remote_targets for key, runtime in RUNTIMES.items() if runtime.remote_targets
}


# One searchable question avoids a dependent dropdown whose choices cannot
# update until the HA form is submitted. Picker paths retain both identities.
PROFILE_CHOICES = {
    key: product.label + (" / " + key.split("/", 1)[1] if "/" in key else "")
    for key, product in PRODUCTS.items()
    if key not in PICKERS
}
for _picker, _targets in PICKERS.items():
    for _target in _targets:
        _remote = (
            ("H158B / " if _target in ("HNRN", "HQRN") else "H109 / ") if _picker == "MHRN" else ""
        )
        PROFILE_CHOICES[f"{_picker}>{_target}"] = f"{_picker} / {_remote}{_target}"


def resolve_product(profile: str) -> str:
    """Resolve only an explicitly selected path through an admitted picker."""
    picker, separator, target = profile.partition(">")
    if separator:
        if target not in PICKERS.get(picker, ()):
            raise ValueError("Choose the remote shown for this Galaxy product")
        return target
    if profile not in PRODUCTS or profile in PICKERS:
        raise ValueError("Choose an admitted Galaxy product and its exact remote")
    return profile
