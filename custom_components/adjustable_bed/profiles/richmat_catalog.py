"""Typed product data for apps driving the Richmat catalog controller."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ..codec.richmat import Record, record_20_len
from .richmat import RichmatProfile
from .richmat_app import Action, Product


@dataclass(frozen=True, slots=True)
class Runtime:
    code: str
    route: str
    remote_targets: tuple[str, ...]
    initial_release: bool
    query_order: tuple[str, ...]
    time_sync: bool
    sleep_query: bool
    initial_alarm: bool
    snore: bool


@dataclass(frozen=True, slots=True)
class Catalog:
    key: str
    name: str
    wire: RichmatProfile
    actions: Mapping[str, Action]
    products: Mapping[str, Product]
    expansions: Mapping[str, tuple[str, ...]]
    record: Record = record_20_len
    # Galaxy's reconciled runtime state differs from Good Vibe's accepted route.
    substitute_when_release: bool = False
    notification_menus: bool = False
    runtimes: Mapping[str, Runtime] = field(default_factory=dict)
    timer_codes: Mapping[str, Mapping[int, int]] = field(default_factory=dict)
    reply_gated_menus: bool = False
    release_initially: bool = True
    startup: tuple[tuple[str, int], ...] = (
        ("deviceFunctionItemExitLimit", 0),
        ("deviceFunctionItemCheckClock", 1),
        ("deviceFunctionItemCheckLight", 1),
    )
