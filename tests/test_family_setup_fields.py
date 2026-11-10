"""Family rows keep what each route's own row offered (#676).

A family row's form is drawn for one route, and the family question can pick
another one afterwards. Each answer must still let the user set the motor
count, massage and angle sensing its old row offered, unless its profile sets
them itself: on the first form, kept through the answer, or on a later step.
An existing entry on any route must also reach every other route the
question offers: through Reconfigure for a guided family, or through Configure,
which lists the routes outside it by name.
"""

from contextlib import ExitStack
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.const import CONF_ADDRESS
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_families import APP_FAMILIES, GUIDED_FAMILIES
from custom_components.adjustable_bed.bed_traits import (
    bed_type_has_position_feedback,
    disconnect_after_command_default_enabled,
)
from custom_components.adjustable_bed.config_flow import (
    _APP_SETUP_STEPS,
    _SETUP_ROUTE_EXCLUSIONS,
    AdjustableBedConfigFlow,
    _bed_type_selector,
    _motor_count_options,
)
from custom_components.adjustable_bed.const import (
    resolve_explicit_bed_type,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import (
    bed_type_choice,
    get_bed_type_options,
    resolve_bed_type_choice,
)
from custom_components.adjustable_bed.profile_id import app_profile_key, resolve_profile_id
from custom_components.adjustable_bed.profile_migration import reconfigure_family
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)
from tests.form_helpers import form_answers as _answers
from tests.form_helpers import form_fields as _fields
from tests.form_helpers import marker_default as _default
from tests.form_helpers import options_of as _options
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

ADDRESS = "11:22:33:44:55:66"
# Steps that pick the route, by the field that picks it.
_ROUTE_STEPS = {
    **{family.step: "choice" for family in APP_FAMILIES},
    "keeson_app": "choice",
}


def _route_field(flow: AdjustableBedConfigFlow, step: str) -> str | None:
    """The field that picks the route on this step, if it picks one.

    A family answer's own questions that ask the route, such as the Restonic BT
    style, pick it on the generic step.
    """
    if step == "profile_questions" and flow._asking is not None:
        asked = {question.key for question in flow._asking[0].questions}
        return const.CONF_PROTOCOL_VARIANT if const.CONF_PROTOCOL_VARIANT in asked else None
    return _ROUTE_STEPS.get(step)
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


def _finishing(flow: AdjustableBedConfigFlow):
    """Patch the steps after the final settings to stop with the entry they would save."""

    def finish(*_args: Any, **kwargs: Any) -> None:
        raise _Finished(kwargs.get("data") or flow._pending_entry or flow._manual_data or {})

    stack = ExitStack()
    for name in ("async_step_setup_progress", "async_step_manual_pairing", "_async_create_selected_app_entry"):
        stack.enter_context(patch.object(flow, name, side_effect=finish))
    return stack


def _new_flow(hass, row: str) -> AdjustableBedConfigFlow:
    """A setup that chose this row in the app question, for a typed address."""
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._async_transport_note = AsyncMock(return_value="")
    flow._selected_bed_type, flow._selected_protocol_variant = resolve_bed_type_choice(row)
    return flow


async def _run(
    hass, row: str, path: list[Any], motor_count: int, *, change_disconnect: bool | None = None
) -> dict[str, Any]:
    """Set the row up with these route answers; return the saved route or the next choice.

    The final settings submit the answers a route's own default would never
    give. With ``change_disconnect``, they also submit disconnect after each
    command: as drawn, or changed from it.
    """
    flow = _new_flow(hass, row)
    sentinels = {
        const.CONF_MOTOR_COUNT: motor_count,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_DISABLE_ANGLE_SENSING: True,
    }
    submitted: dict[str, Any] = {}
    drawn: bool | None = None
    later: set[str] = set()
    with _finishing(flow):
        try:
            result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
            answered = 0
            for attempt in range(8):
                if result["type"] == "menu" and result["step_id"] == "keep_detected":
                    # Keep on a new bed first explains the detected controls.
                    result = await flow.async_step_keep_continue()
                    continue
                assert result["type"] == "form", result
                step = result["step_id"]
                fields = _fields(result["data_schema"])
                answers = _answers(result, attempt)
                errors = result.get("errors") or {}
                if step == "finish_settings":
                    shown = {m.schema for m in fields}
                    submitted = {
                        key: value
                        for key, value in sentinels.items()
                        if key in shown and key not in errors
                    }
                    answers.update(submitted)
                    drawn = next(
                        _default(m) for m in fields if m.schema == const.CONF_DISCONNECT_AFTER_COMMAND
                    )
                    if change_disconnect is not None:
                        answers[const.CONF_DISCONNECT_AFTER_COMMAND] = drawn != change_disconnect
                elif (key := _route_field(flow, step)) is not None:
                    if answered == len(path):
                        marker = next(m for m in fields if m.schema == key)
                        return {"choices": _options(fields[marker])}
                    answers[key] = path[answered]
                    answered += 1
                    later |= {m.schema for m in fields} & set(_FIELDS)
                else:
                    later |= {m.schema for m in fields} & set(_FIELDS)
                result = await getattr(flow, f"async_step_{step}")(answers)
        except _Finished as finished:
            saved = finished.data
            return {
                "saved": saved,
                # A field the journey set itself, such as an app's own layout, is settled.
                "set": later
                | flow._journey_set
                | {key for key, value in submitted.items() if saved.get(key) == value},
                "drawn_disconnect": drawn,
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
        const.CONF_DISABLE_ANGLE_SENSING: bed_type_has_position_feedback(bed_type, variant),
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


async def test_angle_sensing_starts_at_the_routes_own_default(hass):
    """A JMC400 box reports positions, so its question starts with them read."""
    flow = _new_flow(hass, const.BED_TYPE_JENSEN)
    result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
    result = await flow.async_step_jensen_family({"choice": "jensen_jmc400"})
    assert result["step_id"] == "profile_questions"
    sensing = next(
        marker
        for marker in result["data_schema"].schema
        if marker.schema == const.CONF_DISABLE_ANGLE_SENSING
    )
    assert sensing.default() is False


def _route(data: dict[str, Any]) -> str:
    """The route and app an entry runs; the saved ID a family question keeps counts as it."""
    saved, variant = data[const.CONF_BED_TYPE], data.get(const.CONF_PROTOCOL_VARIANT)
    bed_type = resolve_explicit_bed_type(saved, variant) or saved
    if bed_type == const.BED_TYPE_OKIMAT:
        # Okimat is the Okin UUID route under its older saved ID.
        bed_type = const.BED_TYPE_OKIN_UUID
    route = bed_type_choice(bed_type, variant)
    if (key := app_profile_key(saved, variant)) is not None and isinstance(data.get(key), str):
        route += f"@{data[key]}"
    return route


async def _family_routes(hass, row: str) -> dict[str, dict[str, Any]]:
    """The routes the row's family question offers, with the setup each saves.

    Keep saves the drawn route, and an app the review suggests belongs to
    another family, so neither is a sibling.
    """
    routes: dict[str, dict[str, Any]] = {}
    paths: list[list[Any]] = [[]]
    with (
        patch("custom_components.adjustable_bed.profile_review.related_app_choices", return_value=[]),
        patch("custom_components.adjustable_bed.profile_review.suggested_apps", return_value=[]),
    ):
        while paths:
            path = paths.pop()
            result = await _run(hass, row, path, 3)
            if "choices" in result:
                paths.extend([*path, choice] for choice in result["choices"] if choice != "keep")
            elif result["saved"] is not None:
                routes.setdefault(_route(result["saved"]), result["saved"])
    # The Sleep Smart pump is its own device, never a route a bed changes to.
    routes.pop(const.BED_TYPE_LOGICDATA_AIR_PUMP, None)
    return routes


def _configure_routes(data: dict[str, Any]) -> set[str]:
    """The routes Configure lists by name, outside the entry's guided family."""
    family = next((f for f in GUIDED_FAMILIES if data[const.CONF_BED_TYPE] in f.managed), None)
    routes = set()
    for choice in _bed_type_selector(_route(data), show_saved_id=True).rows().values():
        bed_type, variant = resolve_bed_type_choice(choice)
        if family is not None and bed_type in family.managed:
            # Configure sends a change within a guided family to Reconfigure.
            continue
        variants = [variant] if variant else [None, *(get_variants_for_bed_type(bed_type) or {})]
        routes |= {
            _route({const.CONF_BED_TYPE: bed_type, const.CONF_PROTOCOL_VARIANT: v}) for v in variants
        }
    return routes


async def _reconfigure_routes(hass, entry: MockConfigEntry) -> set[str]:
    """The routes Reconfigure stages from the entry, through every answer."""
    routes: set[str] = set()
    paths: list[list[Any]] = [[]]
    while paths:
        path = paths.pop()
        flow = AdjustableBedConfigFlow()
        flow.hass = hass
        flow.context = {"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        result = await flow.async_step_reconfigure()
        answered = 0
        while True:
            fields = _fields(result["data_schema"]) if result["type"] == "form" else {}
            if result["type"] == "form" and not fields:
                # A note, such as Woosa Sleep's, stages its route when submitted.
                result = await getattr(flow, f"async_step_{result['step_id']}")({})
                continue
            key = _route_field(flow, result.get("step_id", "")) if result["type"] == "form" else None
            if key is None:
                if result["type"] != "abort":
                    routes.add(_route(flow._manual_data or {}))
                break
            if answered == len(path):
                marker = next(m for m in fields if m.schema == key)
                paths.extend([*path, c] for c in _options(fields[marker]) if c != "keep")
                break
            answers = {**_answers(result, 0), key: path[answered]}
            answered += 1
            result = await getattr(flow, f"async_step_{result['step_id']}")(answers)
    return routes


@pytest.mark.parametrize(
    "row",
    sorted(
        option["value"]
        for option in get_bed_type_options()
        if _APP_SETUP_STEPS.get(resolve_bed_type_choice(option["value"])[0]) in _ROUTE_STEPS
    ),
)
async def test_an_entry_on_any_route_reaches_every_sibling_route(
    hass, enable_custom_integrations, row
):
    """Reconfigure for a guided family, or Configure by name, reaches each sibling."""
    routes = await _family_routes(hass, row)
    gaps = {}
    for route, data in routes.items():
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            unique_id=route,
            version=5,
            data={**data, const.CONF_PROFILE_ID: resolve_profile_id(data)},
        )
        entry.add_to_hass(hass)
        reached = {route} | _configure_routes(data)
        if reconfigure_family(data) is not None:
            reached |= await _reconfigure_routes(hass, entry)
        if missing := set(routes) - reached:
            gaps[route] = sorted(missing)
    assert not gaps, gaps


@pytest.mark.parametrize("row", _starting_rows())
@pytest.mark.parametrize("change", [False, True], ids=["left", "changed"])
async def test_disconnect_after_command_follows_the_route_unless_changed(hass, row, change):
    """Left as drawn it saves the chosen route's own default; a change is kept."""
    gaps = {}
    paths: list[list[Any]] = [[]]
    while paths:
        path = paths.pop()
        result = await _run(hass, row, path, 3, change_disconnect=change)
        if "choices" in result:
            paths.extend([*path, choice] for choice in result["choices"])
            continue
        if (saved := result["saved"]) is None:
            continue
        drawn = result["drawn_disconnect"]
        expected = not drawn if change else disconnect_after_command_default_enabled(
            saved[const.CONF_BED_TYPE], saved.get(const.CONF_PROTOCOL_VARIANT)
        )
        if saved.get(const.CONF_DISCONNECT_AFTER_COMMAND) != expected:
            gaps[" > ".join(map(str, path)) or "(row)"] = (_route(saved), expected)
    assert not gaps, gaps


def _app_rows() -> list[str]:
    """Each app row of the app question whose bed type has a family question.

    Restonic BT's row asks the app's remote style, which is its own question.
    """
    return sorted(
        option["value"]
        for option in get_bed_type_options()
        if (route := resolve_bed_type_choice(option["value"]))[1] is not None
        and _APP_SETUP_STEPS.get(route[0]) in _ROUTE_STEPS
        and route[1] not in (const.KEESON_VARIANT_RESTONIC_A, const.KEESON_VARIANT_RESTONIC_B)
    )


@pytest.mark.parametrize("choice", _app_rows())
async def test_an_app_row_is_not_asked_its_family_question_again(hass, choice):
    """Picking an app's own row in the app question answers its family question."""
    flow = _new_flow(hass, choice)
    flow._selected_bed_type = None
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info", return_value=[]
    ):
        form = await flow.async_step_select_app({const.CONF_BED_TYPE: choice})
    assert form["step_id"] == "manual_entry"
    with _finishing(flow), pytest.raises(_Finished) as finished:
        result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
        for attempt in range(4):
            fields = {m.schema for m in _fields(result["data_schema"])}
            assert _route_field(flow, result["step_id"]) is None, result["step_id"]
            assert const.CONF_PROTOCOL_VARIANT not in fields, result["step_id"]
            result = await getattr(flow, f"async_step_{result['step_id']}")(
                _answers(result, attempt)
            )
    saved = finished.value.data
    assert (saved[const.CONF_BED_TYPE], saved[const.CONF_PROTOCOL_VARIANT]) == (
        resolve_bed_type_choice(choice)
    )


def _plain_rows() -> list[str]:
    """Every row the generic form sets up without an app or family step."""
    return sorted(
        option["value"]
        for option in get_bed_type_options()
        if resolve_bed_type_choice(option["value"])[0] not in _APP_SETUP_STEPS
    )


@pytest.mark.parametrize("row", _plain_rows())
@pytest.mark.parametrize("disable", [None, True], ids=["left", "disabled"])
async def test_the_final_settings_save_each_beds_angle_sensing(hass, row, disable):
    """Left as drawn it saves the bed's own default; a reporting bed can turn it off (#863)."""
    flow = _new_flow(hass, row)
    form = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
    assert form["step_id"] == "finish_settings"
    markers = {m.schema: m for m in _fields(form["data_schema"])}
    shown = const.CONF_DISABLE_ANGLE_SENSING in markers
    bed_type, variant = resolve_bed_type_choice(row)
    routes = (variant or const.VARIANT_AUTO, *(get_variants_for_bed_type(bed_type) or {}))
    # Shown exactly where a route of the row reports positions.
    assert shown == any(bed_type_has_position_feedback(bed_type, r) for r in routes)
    answers = _answers(form, 0)
    if shown and disable:
        answers[const.CONF_DISABLE_ANGLE_SENSING] = True
    with _finishing(flow), pytest.raises(_Finished) as finished:
        result = await flow.async_step_finish_settings(answers)
        for attempt in range(4):
            result = await getattr(flow, f"async_step_{result['step_id']}")(
                _answers(result, attempt)
            )
    saved = finished.value.data
    reports = bed_type_has_position_feedback(
        saved[const.CONF_BED_TYPE], saved.get(const.CONF_PROTOCOL_VARIANT)
    )
    expected = True if disable and shown else not reports
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is expected


# Bed types whose controller reads positions, on routes the integration does not
# read them for by default (``bed_type_has_position_feedback`` is False), so
# angle sensing starts disabled.
_QUIET_BED_TYPES = (
    const.BED_TYPE_COMFORTBASE,
    const.BED_TYPE_COOLBASE,
    const.BED_TYPE_DOUBLESLEEP,
    const.BED_TYPE_FURNIMOVE,
    const.BED_TYPE_ISLEEP,
    const.BED_TYPE_KEESON,
    const.BED_TYPE_LIMOSS_REMOTE,
    const.BED_TYPE_OCTO,
    const.BED_TYPE_OKIN_DOT,
    const.BED_TYPE_OKIN_FFE,
    const.BED_TYPE_OKIN_RF_ECO_BT,
    const.BED_TYPE_REVERIE,
    const.BED_TYPE_REVERIE_NIGHTSTAND,
    const.BED_TYPE_SCOTT_LIVING,
    const.BED_TYPE_SERTA,
    const.BED_TYPE_SLEEPTRACKER,
    const.BED_TYPE_SLEEPYS_ELITE_APP,
    const.BED_TYPE_STARCODE_ABM5_4,
    const.BED_TYPE_SVANE,
)


def _routes_of(bed_type: str) -> list[str]:
    return list(dict.fromkeys((const.VARIANT_AUTO, *(get_variants_for_bed_type(bed_type) or {}))))


def _quiet_routes() -> list[tuple[str, str]]:
    """Each route of a quiet bed type that a new setup can save."""
    return [
        (bed_type, variant)
        for bed_type in _QUIET_BED_TYPES
        for variant in _routes_of(bed_type)
        if not bed_type_has_position_feedback(bed_type, variant)
        and variant not in _SETUP_ROUTE_EXCLUSIONS.get(bed_type, ())
        and is_valid_variant_for_bed_type(bed_type, variant)
    ]


async def test_the_quiet_bed_types_are_those_whose_controller_reads_positions(hass):
    from custom_components.adjustable_bed.beds.base import BedController
    from tests.test_controller_contract import _create_controller_for_bed_type

    found = set()
    for bed_type in const.SUPPORTED_BED_TYPES:
        controller = await _create_controller_for_bed_type(bed_type)
        if type(controller).read_positions is not BedController.read_positions and any(
            not bed_type_has_position_feedback(bed_type, v) for v in _routes_of(bed_type)
        ):
            found.add(bed_type)
    assert found == set(_QUIET_BED_TYPES)


@pytest.mark.parametrize(("bed_type", "variant"), _quiet_routes())
async def test_an_untouched_setup_leaves_a_quiet_route_unread(hass, bed_type, variant):
    """Left as drawn, every setup of the route saves angle sensing disabled."""
    saved = []
    paths: list[list[Any]] = [[]]
    while paths:
        path = paths.pop()
        # Chosen as the route, as discovery or a brand list stages it.
        flow = _new_flow(hass, bed_type)
        flow._selected_protocol_variant = variant
        with _finishing(flow):
            try:
                result = await flow.async_step_manual_entry({CONF_ADDRESS: ADDRESS})
                answered = 0
                for attempt in range(8):
                    if result["type"] == "menu" and result["step_id"] == "keep_detected":
                        # Keep on a new bed first explains the detected controls.
                        result = await flow.async_step_keep_continue()
                        continue
                    answers = _answers(result, attempt)
                    if variant in _options(
                        next(
                            (v for m, v in _fields(result["data_schema"]).items()
                             if m.schema == const.CONF_PROTOCOL_VARIANT),
                            None,
                        )
                    ):
                        # The route's own pick, such as a remote code or model.
                        answers.update({const.CONF_PROTOCOL_VARIANT: variant})
                        if "advanced" in answers:
                            answers["advanced"][const.CONF_PROTOCOL_VARIANT] = variant
                    if (key := _route_field(flow, result["step_id"])) is not None:
                        marker = next(m for m in _fields(result["data_schema"]) if m.schema == key)
                        options = _options(_fields(result["data_schema"])[marker])
                        if answered == len(path):
                            paths.extend([*path, o] for o in (["keep"] if "keep" in options else options))
                            break
                        answers[key] = path[answered]
                        answered += 1
                    result = await getattr(flow, f"async_step_{result['step_id']}")(answers)
            except _Finished as finished:
                saved.append(finished.data)
    routes = [
        s for s in saved
        if s[const.CONF_BED_TYPE] == bed_type
        and (s.get(const.CONF_PROTOCOL_VARIANT) or const.VARIANT_AUTO) == variant
    ]
    assert routes, f"no untouched setup reached {bed_type}:{variant}"
    assert all(s[const.CONF_DISABLE_ANGLE_SENSING] is True for s in routes), routes
