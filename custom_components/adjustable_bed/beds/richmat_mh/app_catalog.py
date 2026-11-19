"""Typed app-local catalogs for the accepted Nisco and MLILY Supreme scopes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from ...catalog_json import Node, load
from ...profiles.richmat_mh_apps import APPS, models
from .controller import Control, Features, Model


@dataclass(frozen=True, slots=True)
class Surface:
    model: Model
    mode_groups: dict[str, tuple[str, ...]]
    aliases: tuple[tuple[int, int, str], ...]
    speech: tuple[tuple[int, int], ...]
    remote_long: tuple[int, ...]


def _control(node: Node) -> Control:
    route, kind, area, group, label, code, interval = node.row(7)
    return Control(
        route.text(), kind.text(), area.text(), group.text(), label.text(),
        code.integer(), interval.integer(),
    )


def _features(node: Node) -> Features:
    (led, button_led, aroma, snore, music, sleep, sleep_type, speech, set_lock,
     light_lock, new_alarm, alarm, snore_list, alarm_call, angles, intensity,
     motor_modes, call) = node.row(18)
    alarm_rows = []
    for item in alarm_call.items():
        name, code = item.row(2)
        alarm_rows.append((name.optional_text(), code.integer()))
    angle_rows = []
    for item in angles.items():
        bits, name, low, high, offset = item.row(5)
        angle_rows.append((bits.integer(), name.text(), low.integer(), high.integer(), offset.integer()))
    intensity_rows = []
    for item in intensity.items():
        zone, name, low, high = item.row(4)
        intensity_rows.append((zone.text(), name.optional_text(), low.integer(), high.integer()))
    return Features(
        led.flag(), button_led.flag(), aroma.flag(), snore.flag(), music.flag(),
        sleep.flag(), sleep_type.optional_text(), speech.flag(), set_lock.flag(),
        light_lock.flag(), new_alarm.flag(), tuple(v.integer() for v in alarm.items()),
        tuple(v.integer() for v in snore_list.items()), tuple(alarm_rows),
        tuple(angle_rows), tuple(intensity_rows), tuple(v.text() for v in motor_modes.items()),
        call.flag(),
    )


@cache
def _surfaces(app: str) -> dict[str, Surface]:
    """Load off the HA event loop, only for the explicitly selected app."""
    if app not in APPS:
        raise ValueError("Choose the app that owns this receiver")
    result = {}
    for model, node in load(Path(__file__).with_name("data"), app).entries().items():
        record = node.record("controls", "features", "mode_groups", "aliases", "speech", "remote_long")
        groups = {
            group: tuple(value.text() for value in values.items())
            for group, values in record["mode_groups"].entries().items()
        }
        parsed = Model(
            app, model, tuple(_control(item) for item in record["controls"].items()),
            _features(record["features"]),
        )
        aliases = []
        for item in record["aliases"].items():
            target, source, label = item.row(3)
            aliases.append((target.integer(), source.integer(), label.text()))
        speech = []
        for item in record["speech"].items():
            source, target = item.row(2)
            speech.append((source.integer(), target.integer()))
        result[model] = Surface(
            parsed, groups, tuple(aliases), tuple(speech),
            tuple(value.integer() for value in record["remote_long"].items()),
        )
    return result


@cache
def catalog(app: str) -> dict[str, Model]:
    return {name: surface.model for name, surface in _surfaces(app).items()}


def details(app: str, model: str) -> Surface:
    return _surfaces(app)[model.removesuffix("_mattress")]


def mode_groups(app: str, model: str) -> dict[str, tuple[str, ...]]:
    return details(app, model).mode_groups


def load_model(app: str, model_id: str) -> Model | None:
    base = model_id.removesuffix("_mattress")
    if base not in models(app) or (base != model_id and not APPS[app].normal_mattress):
        return None
    model = catalog(app).get(base)
    if model is None:
        return None
    return Model(app, model_id, model.controls, model.features)
