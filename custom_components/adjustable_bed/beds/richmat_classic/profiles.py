"""Package-local catalogs for the older Richmat apps, Luuna Rise and Power Cool.

Each app's catalog is ``data/<app>.json.gz``, generated outside this
repository from its accepted APK Protocol Audit report; no generator is checked in.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from ...catalog_json import Node, load

DATA_DIR: Final = Path(__file__).with_name("data")

# Entity keys and held controls start with KEY_PREFIX; 4.4 shipped them under
# LEGACY_KEY_PREFIX, which the schema 5.4 migration and hold_control still read.
KEY_PREFIX: Final = "richmat_classic_"
LEGACY_KEY_PREFIX: Final = "cluster018_"
# 4.4 also prefixed each app's stored state slot key (``app:layout``).
LEGACY_APP_STATE_KEY_PREFIX: Final = "cluster018:"

APP_NAMES = {
    "avocadoecobase": "Avocado Eco Base",
    "coastersleep": "CoasterSleep",
    "fortywinks": "Forty Winks",
    "milemont": "Milemont",
    "superior": "Superior",
    "luunarise2": "Luuna Rise",
    "powercool": "Power Cool Sleep System",
}

RISE_APPS: Final = frozenset({"luunarise2", "powercool"})


def current_control_name(control: str) -> str:
    """Return a held control's current name, accepting the name 4.4 shipped."""
    if control.startswith(LEGACY_KEY_PREFIX):
        return KEY_PREFIX + control.removeprefix(LEGACY_KEY_PREFIX)
    return control


@dataclass(frozen=True, slots=True)
class Control:
    """One exact XML node and its actually initialized getter fields."""

    node: int
    status: int
    threshold_ms: int
    tag: str | None
    view_id: str
    rich_button: bool
    show_type: int
    extra: str | None
    short: str | None
    short_old: str | None
    long: str | None
    visibility: str
    alarm_clock: str | None
    modes: tuple[int, ...]
    tv_mem: bool
    select_view: bool
    mem_special: bool
    select_special: bool
    hold_affected: bool
    resource_keys: dict[str, str]
    ancestor_visibility: tuple[str, ...]
    excluded_short: bool = False
    excluded_long: bool = False

    @property
    def label(self) -> str:
        value = self.resource_keys.get("press_short") or self.resource_keys.get("press_long")
        if value:
            return value.removeprefix("@string/").replace("_", " ")
        return self.view_id or f"Control {self.node}"


@dataclass(frozen=True, slots=True)
class Model:
    """One layout: its controls, operating modes, app views and name aliases."""

    controls: tuple[Control, ...]
    modes: tuple[int, ...]
    views: tuple[str, ...]
    aliases: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Catalog:
    """One app's layouts and its alarm opcodes."""

    models: dict[str, Model]
    alarm_allowlist: dict[str, str]


# The catalog's control columns, in order.
_COLUMNS = (
    "node", "status", "threshold_ms", "tag", "view_id", "rich_button", "show_type", "extra",
    "short", "short_old", "long", "visibility", "alarm_clock", "modes", "tvMem", "selectView",
    "mem_special", "select_special", "hold_affected", "resource_keys", "ancestor_visibility",
)


def _control(node: Node, *, scoped: bool = False) -> Control:
    cells = node.row(len(_COLUMNS) + (2 if scoped else 0))
    return Control(
        node=cells[0].integer(),
        status=cells[1].integer(),
        threshold_ms=cells[2].integer(),
        tag=cells[3].optional_text(),
        view_id=cells[4].text(),
        rich_button=cells[5].flag(),
        show_type=cells[6].integer(),
        extra=cells[7].optional_text(),
        short=cells[8].optional_text(),
        short_old=cells[9].optional_text(),
        long=cells[10].optional_text(),
        visibility=cells[11].text(),
        alarm_clock=cells[12].optional_text(),
        modes=tuple(mode.integer() for mode in cells[13].items()),
        tv_mem=cells[14].flag(),
        select_view=cells[15].flag(),
        mem_special=cells[16].flag(),
        select_special=cells[17].flag(),
        hold_affected=cells[18].flag(),
        resource_keys={key: value.text() for key, value in cells[19].entries().items()},
        ancestor_visibility=tuple(value.text() for value in cells[20].items()),
        excluded_short=cells[21].flag() if scoped else False,
        excluded_long=cells[22].flag() if scoped else False,
    )


def _model(node: Node, *, scoped: bool = False) -> Model:
    data = node.record("controls", "modes", "views", "aliases")
    aliases = (alias.record("from", "to") for alias in data["aliases"].items())
    return Model(
        controls=tuple(_control(row, scoped=scoped) for row in data["controls"].items()),
        modes=tuple(mode.integer() for mode in data["modes"].items()),
        views=tuple(view.text() for view in data["views"].items()),
        aliases=tuple((alias["from"].text(), alias["to"].text()) for alias in aliases),
    )


@lru_cache(maxsize=7)
def load_catalog(app: str) -> Catalog:
    """Load and validate on an executor before constructing a controller."""
    if app not in APP_NAMES:
        raise ValueError("Choose a supported app")
    data = load(DATA_DIR, app).record("models", "fields", "alarm_allowlist")
    columns = _COLUMNS + (("excluded_short", "excluded_long") if app in RISE_APPS else ())
    if tuple(column.text() for column in data["fields"].items()) != columns:
        data["fields"].fail(f"the control columns {_COLUMNS}")
    return Catalog(
        models={layout: _model(model, scoped=app in RISE_APPS) for layout, model in data["models"].entries().items()},
        alarm_allowlist={
            key: value.text() for key, value in data["alarm_allowlist"].entries().items()
        },
    )


def controls(app: str, layout: str) -> tuple[Control, ...]:
    model = load_catalog(app).models.get(layout)
    if model is None:
        raise ValueError("This layout is absent from the selected app")
    return model.controls


def resolve_layout(app: str, value: str, *, from_name: bool = False, russian: bool = False) -> str:
    """Exact alias precedence and four-character manual/QR selection."""
    catalog = load_catalog(app).models
    aliases = {
        source.upper(): target.upper()
        for model in catalog.values() for source, target in model.aliases
    }
    name = value.upper() if from_name else value.strip().upper()
    if from_name:
        selected = next((aliases[name[:n]] for n in (9, 8, 7, 6, 5, 4) if name[:n] in aliases and len(name) >= n), None)
        if selected is None and len(name) == 10:
            selected = aliases.get(name)
        selected = selected or name[:4]
    else:
        if len(name) != 4:
            raise ValueError("A manual/QR layout must contain exactly four characters")
        selected = aliases.get(name, name)
    if russian and selected == "OTRM":
        selected = "O0RM"
    if selected not in catalog:
        raise ValueError("The selected app has no matching layout")
    return selected
