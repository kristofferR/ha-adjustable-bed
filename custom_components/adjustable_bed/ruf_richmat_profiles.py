"""Explicit app identities for the RUF, W.Silver, AMERICANSTAR, Bailey and TX remotes.

Each app's catalog is ``ruf_richmat_data/<app>.json.gz``, generated outside this
repository from its accepted APK Protocol Audit report; no generator is checked in.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import TypedDict

from .catalog_json import JsonValue, Node, load
from .const import RUF_RICHMAT_APPS

DISPLAY_NAMES = {
    "ruf_betten": "RUF | Betten (Motor 2)",
    "wsilver_products": "W.Silver Products",
    "richmat_americanstar": "AMERICANSTAR (Richmat app)",
    "bailey_bed_control": "Bailey's Bed Control",
    "richmat_tx": "TX (Richmat app)",
}

# route, gesture, kind, app group, app label, opcode, repeat interval ms
type ControlRow = tuple[str, str, str, str, str, int, int]
type Field = JsonValue


class Profile(TypedDict):
    controls: tuple[ControlRow, ...]
    fields: dict[str, Field]


def _codes(node: Node) -> Field:
    return None if node.value is None else [item.text() for item in node.items()]


def _object(node: Node) -> Field:
    return None if node.value is None else {key: item.json() for key, item in node.entries().items()}


_FLAG_FIELDS = (
    "hasAroma", "hasBtnLed", "hasLed", "hasMattress", "hasMusic", "hasNewAlarm", "hasSleep",
    "hasSmartLightLock", "hasSmartSetLock", "hasSnore", "hasSpeech", "isNewAlarm", "newAlarm",
)
_MAP_FIELDS = (
    "alarmMap", "alarmMap2", "massageMap", "massageMap2", "motorMap", "motorMap2", "motorModeMap",
)
# The model fields the catalogs hold, and how each is read.
_FIELDS: dict[str, Callable[[Node], Field]] = {
    **dict.fromkeys(_FLAG_FIELDS, Node.flag),
    **dict.fromkeys(_MAP_FIELDS, _object),
    "alarmList": _codes,
    "snoreList": _codes,
    "sleepType": Node.optional_text,
}


def _control(node: Node) -> ControlRow:
    route, gesture, kind, group, label, opcode, interval = node.row(7)
    return (
        route.text(), gesture.text(), kind.text(), group.text(), label.text(),
        opcode.integer(), interval.integer(),
    )


def _field(key: str, node: Node) -> Field:
    if (read := _FIELDS.get(key)) is None:
        node.fail("a known model field")
    return read(node)


def _profile(node: Node) -> Profile:
    data = node.record("controls", "fields")
    return Profile(
        controls=tuple(_control(row) for row in data["controls"].items()),
        fields={key: _field(key, value) for key, value in data["fields"].entries().items()},
    )


@cache
def profiles(app: str) -> dict[str, Profile]:
    """Load and validate only the explicitly selected app's catalog, off the event loop."""
    if app not in RUF_RICHMAT_APPS.values():
        raise ValueError(f"Unknown app: {app}")
    return {model: _profile(node) for model, node in load("ruf_richmat_data", app).entries().items()}


def fields(app: str, model: str) -> dict[str, Field]:
    return profiles(app)[model]["fields"]
