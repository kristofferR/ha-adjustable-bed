"""Package-local product catalogs for the accepted five older Richmat apps."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, TypedDict, cast

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
}


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

    @property
    def label(self) -> str:
        value = self.resource_keys.get("press_short") or self.resource_keys.get("press_long")
        if value:
            return value.removeprefix("@string/").replace("_", " ")
        return self.view_id or f"Control {self.node}"


class ModelData(TypedDict):
    controls: list[list[object]]
    modes: list[int]
    views: list[str]
    aliases: list[dict[str, object]]


class CatalogData(TypedDict):
    models: dict[str, ModelData]
    fields: list[str]
    alarm_allowlist: dict[str, str]


@lru_cache(maxsize=5)
def load_catalog(app: str) -> CatalogData:
    """Load on the import executor before constructing a controller."""
    if app not in APP_NAMES:
        raise ValueError("Choose one of the five supported apps")
    path = Path(__file__).with_name("richmat_classic_data") / f"{app}.json.gz"
    with gzip.open(path, "rt") as source:
        return cast(CatalogData, json.load(source))


def controls(app: str, layout: str) -> tuple[Control, ...]:
    model = load_catalog(app)["models"].get(layout)
    if model is None:
        raise ValueError("This layout is absent from the selected app")
    result: list[Control] = []
    for row in model["controls"]:
        result.append(
            Control(
                node=cast(int, row[0]),
                status=cast(int, row[1]),
                threshold_ms=cast(int, row[2]),
                tag=cast(str | None, row[3]),
                view_id=cast(str, row[4]),
                rich_button=cast(bool, row[5]),
                show_type=cast(int, row[6]),
                extra=cast(str | None, row[7]),
                short=cast(str | None, row[8]),
                short_old=cast(str | None, row[9]),
                long=cast(str | None, row[10]),
                visibility=cast(str, row[11]),
                alarm_clock=cast(str | None, row[12]),
                modes=tuple(cast(list[int], row[13])),
                tv_mem=cast(bool, row[14]),
                select_view=cast(bool, row[15]),
                mem_special=cast(bool, row[16]),
                select_special=cast(bool, row[17]),
                hold_affected=cast(bool, row[18]),
                resource_keys=cast(dict[str, str], row[19]),
                ancestor_visibility=tuple(cast(list[str], row[20])),
            )
        )
    return tuple(result)


def resolve_layout(app: str, value: str, *, from_name: bool = False, russian: bool = False) -> str:
    """Exact alias precedence and four-character manual/QR selection."""
    catalog = load_catalog(app)["models"]
    aliases = {
        str(alias["from"]).upper(): str(alias["to"]).upper()
        for model in catalog.values() for alias in model["aliases"]
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
