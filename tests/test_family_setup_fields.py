"""Fresh setup reaches every generic field a family route leaves to the user (#676).

A family row's form is drawn for one route, and the family question can pick
another one afterwards. Each answer must still let the user set the motor
count, massage and angle sensing its old row offered, unless its profile sets
them itself: on the first form, kept through the answer, or on a later step.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.field_visibility import get_hidden_fields

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import (
    _APP_SETUP_STEPS,
    _FAMILY_STEPS,
    AdjustableBedConfigFlow,
    _motor_count_options,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import (
    bed_type_choice,
    get_bed_type_options,
    resolve_bed_type_choice,
)
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

ADDRESS = "11:22:33:44:55:66"
# Steps that pick the route, by the field that picks it. The family steps ask
# "choice", except Vibradorm's.
_ROUTE_STEPS = {
    **dict.fromkeys(_FAMILY_STEPS | {"logicdata_family", "starcode_family", "keeson_app"}, "choice"),
    "vibradorm": "app",
    "keeson_restonic": const.CONF_PROTOCOL_VARIANT,
    "keeson_route": const.CONF_PROTOCOL_VARIANT,
}
_FIELDS = (const.CONF_MOTOR_COUNT, const.CONF_HAS_MASSAGE, const.CONF_DISABLE_ANGLE_SENSING)


def _starting_rows() -> list[str]:
    """Every row that opens a family question, and every route a form may be drawn for."""
    rows = {
        option["value"]
        for option in get_bed_type_options()
        if _APP_SETUP_STEPS.get(resolve_bed_type_choice(option["value"])[0]) in _ROUTE_STEPS
    }
    for bed_type, step in _APP_SETUP_STEPS.items():
        if step in _ROUTE_STEPS:
            # A bed type without an automatic route is drawn as its first one.
            variant = None
            if not is_valid_variant_for_bed_type(bed_type, const.VARIANT_AUTO):
                variant = next(iter(get_variants_for_bed_type(bed_type) or {}), None)
            rows.add(bed_type_choice(bed_type, variant))
    return sorted(rows)


class _Finished(Exception):
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = dict(data)


def _fields(schema: vol.Schema) -> dict[vol.Marker, Any]:
    """Every field marker, those inside a collapsed section included."""
    fields = {}
    for marker, validator in schema.schema.items():
        inner = getattr(validator, "schema", None)
        fields.update(_fields(inner) if isinstance(inner, vol.Schema) else {marker: validator})
    return fields


def _options(validator: Any) -> list[Any]:
    if isinstance(config := getattr(validator, "config", None), dict) and "options" in config:
        return [o["value"] if isinstance(o, dict) else o for o in config["options"]]
    for item in (validator, *getattr(validator, "validators", ())):
        if isinstance(item, vol.In):
            return list(item.container)
    return []


def _default(marker: vol.Marker) -> Any:
    default = getattr(marker, "default", vol.UNDEFINED)
    return default() if callable(default) else default


def _answers(result: dict[str, Any], attempt: int) -> dict[str, Any]:
    """Defaults, or a listed answer for a required or refused field."""
    errors = result.get("errors") or {}
    answers = {}
    for marker, validator in _fields(result["data_schema"]).items():
        key, default = marker.schema, _default(marker)
        options = [option for option in _options(validator) if option != "auto"]
        if key in errors and options:
            answers[key] = options[attempt % len(options)]
        elif not isinstance(default, vol.Undefined):
            answers[key] = default
        elif options:
            answers[key] = options[0]
        elif isinstance(marker, vol.Required):
            answers[key] = "00001234-0000-1000-8000-00805f9b34fb" if "uuid" in key else "1"
    return answers


async def _run(hass, row: str, path: list[Any], motor_count: int) -> dict[str, Any]:
    """Set the row up with these route answers; return the saved route or the next choice."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._async_transport_note = AsyncMock(return_value="")
    # Drawn for the row's own route, as a detected bed or a brand list draws it.
    flow._selected_bed_type, variant = resolve_bed_type_choice(row)
    flow._selected_protocol_variant = variant or const.VARIANT_AUTO
    form = await flow.async_step_manual_entry()
    hidden = get_hidden_fields(
        {m.schema: m.visible for m in form["data_schema"].schema if getattr(m, "visible", None)},
        {const.CONF_BED_TYPE: row},
    )
    first = {m.schema for m in form["data_schema"].schema} - hidden
    submitted = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Bed",
        const.CONF_BED_TYPE: row,
        # The answers a route's own default would never give.
        const.CONF_MOTOR_COUNT: motor_count,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_DISABLE_ANGLE_SENSING: True,
    }
    submitted = {key: value for key, value in submitted.items() if key not in _FIELDS or key in first}
    sentinels = {key: value for key, value in submitted.items() if key in _FIELDS}
    flow._disconnect_choice_confirmed = True

    def finish(data: dict[str, Any] | None = None, *_args: Any, **kwargs: Any) -> None:
        raise _Finished(kwargs.get("data") or data or flow._manual_data or {})

    later: set[str] = set()
    with (
        patch.object(flow, "_finish_with_verify", side_effect=finish),
        patch.object(flow, "async_step_manual_pairing", side_effect=finish),
        patch.object(flow, "_async_create_selected_app_entry", side_effect=finish),
    ):
        try:
            result = await flow.async_step_manual_entry(submitted)
            answered = 0
            for attempt in range(8):
                assert result["type"] == "form", result
                step = result["step_id"]
                assert step != "manual_entry", (row, result.get("errors"))
                fields = _fields(result["data_schema"])
                answers = _answers(result, attempt)
                if (key := _ROUTE_STEPS.get(step)) is not None:
                    if answered == len(path):
                        marker = next(m for m in fields if m.schema == key)
                        return {"choices": _options(fields[marker])}
                    answers[key] = path[answered]
                    answered += 1
                later |= {m.schema for m in fields} & set(_FIELDS)
                result = await getattr(flow, f"async_step_{step}")(answers)
        except _Finished as finished:
            saved = finished.data
            return {
                "saved": saved,
                "set": later | {key for key, value in sentinels.items() if saved.get(key) == value},
            }
    # A step the answers above cannot satisfy: its profile must own every field.
    data = flow._manual_data or {}
    profile = setup_profile_for(data)
    assert profile is not None and set(_FIELDS) <= set(profile.owns), (row, path, result["step_id"])
    return {"saved": None}


async def _massage_is_a_choice(data: dict[str, Any]) -> bool:
    """Whether the route can show massage controls only when has_massage is on.

    A route whose variant is asked later counts when any of its answers can.
    """
    profile = setup_profile_for(data)
    variants = [data.get(const.CONF_PROTOCOL_VARIANT)]
    for question in profile.questions if profile else ():
        if question.key == const.CONF_PROTOCOL_VARIANT:
            variants = list(question.options(data) or variants)
    for variant in variants:
        coordinator = _FactoryCoordinator()
        coordinator.entry.data.update({**data, const.CONF_PROTOCOL_VARIANT: variant})
        coordinator.entry.options, coordinator.entry.entry_id = {}, "fields"
        controller = await create_controller(
            coordinator, data[const.CONF_BED_TYPE], variant, _make_connected_client()
        )
        if controller.auto_enable_massage:
            continue
        if any(
            getattr(controller, name) is True
            for name in dir(type(controller))
            if name.startswith("supports_massage")
        ):
            return True
    return False


async def _missing(data: dict[str, Any], reached: set[str]) -> set[str]:
    """The generic fields this route leaves to the user that setup never let them set."""
    bed_type = data[const.CONF_BED_TYPE]
    variant = data.get(const.CONF_PROTOCOL_VARIANT) or const.VARIANT_AUTO
    profile = setup_profile_for(data)
    owned = set(profile.owns) if profile else set()
    choices = {
        const.CONF_MOTOR_COUNT: len(_motor_count_options(bed_type, variant)) > 1,
        const.CONF_DISABLE_ANGLE_SENSING: const.bed_type_has_position_feedback(bed_type, variant),
    }
    missing = {key for key, matters in choices.items() if matters} - owned - reached
    if const.CONF_HAS_MASSAGE not in owned | reached and await _massage_is_a_choice(data):
        missing.add(const.CONF_HAS_MASSAGE)
    return missing


@pytest.mark.parametrize("row", _starting_rows())
async def test_every_route_reaches_the_generic_fields_it_leaves_to_the_user(hass, row):
    gaps = {}
    paths: list[list[Any]] = [[]]
    while paths:
        path = paths.pop()
        reached: set[str] = set()
        result: dict[str, Any] = {}
        # A motor count the route does not offer is replaced, so try another.
        for motor_count in (3, 4):
            result = await _run(hass, row, path, motor_count)
            if "choices" in result:
                break
            reached |= result.get("set", set())
        if "choices" in result:
            paths.extend([*path, choice] for choice in result["choices"])
        elif (saved := result["saved"]) is not None and (
            missing := await _missing(saved, reached)
        ):
            route = bed_type_choice(saved[const.CONF_BED_TYPE], saved.get(const.CONF_PROTOCOL_VARIANT))
            gaps[" > ".join(map(str, path)) or "(row)"] = (route, sorted(missing))
    assert not gaps, gaps


async def test_angle_sensing_the_form_hid_starts_at_the_routes_own_default(hass):
    """A form drawn for a detected JMC400 hides angle sensing, which its question asks."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._async_transport_note = AsyncMock(return_value="")
    flow._selected_bed_type = const.BED_TYPE_JENSEN
    flow._disconnect_choice_confirmed = True
    await flow.async_step_manual_entry()
    result = await flow.async_step_manual_entry(
        {CONF_ADDRESS: ADDRESS, CONF_NAME: "Bed", const.CONF_BED_TYPE: const.BED_TYPE_JENSEN}
    )
    result = await flow.async_step_jensen_family({"choice": "jensen_jmc400"})
    assert result["step_id"] == "profile_questions"
    sensing = next(
        marker
        for marker in result["data_schema"].schema
        if marker.schema == const.CONF_DISABLE_ANGLE_SENSING
    )
    # The box reports positions, so they are read unless the user says otherwise.
    assert sensing.default() is False
