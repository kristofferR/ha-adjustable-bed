"""Read a config-flow form the way the frontend shows it."""

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.helpers.field_visibility import get_hidden_fields


def shown_markers(result: Mapping[str, Any], **values: Any) -> dict[str, probatio.Marker]:
    """Return the top-level markers a form shows, given its defaults and ``values``."""
    markers = {marker.schema: marker for marker in result["data_schema"].schema}
    data = {
        name: marker.default()
        for name, marker in markers.items()
        if not isinstance(marker.default, probatio.Undefined)
    }
    data.update(values)
    conditions = {
        name: visible
        for name, marker in markers.items()
        if (visible := getattr(marker, "visible", None)) is not None
    }
    hidden = get_hidden_fields(conditions, data)
    return {name: marker for name, marker in markers.items() if name not in hidden}


def select_options(result: Mapping[str, Any], key: str) -> dict[str, str]:
    """Return a form field's select options, value to label."""
    marker = next(marker for marker in result["data_schema"].schema if marker == key)
    selector = result["data_schema"].schema[marker]
    return {option["value"]: option["label"] for option in selector.config["options"]}


def suggested(result: Mapping[str, Any], key: str) -> Any:
    """Return a form field's default, or None when it has none."""
    marker = next(marker for marker in result["data_schema"].schema if marker == key)
    return None if isinstance(marker.default, probatio.Undefined) else marker.default()


async def answer_app(hass: Any, result: Mapping[str, Any], choice: str) -> Any:
    """Answer the app question with a bed-type row, when the flow asks it.

    A route the app question does not list, such as a protocol-named one, is
    chosen from the brand list its last answer opens.
    """
    if result.get("step_id") != "select_app":
        return result
    marker = next(marker for marker in result["data_schema"].schema if marker == "bed_type")
    if choice in result["data_schema"].schema[marker].rows().values():
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], {"bed_type": choice}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"bed_type": "not_listed"}
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"bed_type": choice})


def form_fields(schema: Any) -> dict[Any, Any]:
    """Return every field marker, those inside a collapsed section included."""
    fields = {}
    for marker, validator in schema.schema.items():
        inner = getattr(validator, "schema", None)
        fields.update(form_fields(inner) if isinstance(inner, probatio.Schema) else {marker: validator})
    return fields


def options_of(validator: Any) -> list[Any]:
    """Return a select's or a ``vol.In``'s values."""
    if isinstance(config := getattr(validator, "config", None), dict) and "options" in config:
        return [o["value"] if isinstance(o, dict) else o for o in config["options"]]
    for item in (validator, *getattr(validator, "validators", ())):
        if isinstance(item, probatio.In):
            return list(item.container)
    return []


def marker_default(marker: Any) -> Any:
    """Return a marker's default, or ``probatio.UNDEFINED``."""
    default = getattr(marker, "default", probatio.UNDEFINED)
    return default() if callable(default) else default


def form_answers(
    result: Mapping[str, Any], attempt: int = 0, schema: Any = None
) -> dict[str, Any]:
    """Defaults, or a listed answer for a required or refused field, sections nested."""
    errors = result.get("errors") or {}
    answers: dict[str, Any] = {}
    for marker, validator in (schema or result["data_schema"]).schema.items():
        if isinstance(inner := getattr(validator, "schema", None), probatio.Schema):
            answers[marker.schema] = form_answers(result, attempt, inner)
            continue
        key, default = marker.schema, marker_default(marker)
        options = [option for option in options_of(validator) if option != "auto"]
        if key in errors and options:
            answers[key] = options[attempt % len(options)]
        elif not isinstance(default, probatio.Undefined):
            answers[key] = default
        elif options:
            answers[key] = options[0]
        elif isinstance(marker, probatio.Required):
            answers[key] = "00001234-0000-1000-8000-00805f9b34fb" if "uuid" in key else "1"
    return answers


async def complete(
    hass: Any,
    result: Mapping[str, Any],
    answers: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    limit: int = 12,
) -> Any:
    """Answer each form with its defaults, or ``answers[step_id]``, until the flow ends.

    An answer for a field the form does not show is left out.
    """
    for attempt in range(limit):
        if result["type"] != "form":
            return result
        step = result["step_id"]
        values = form_answers(result, attempt)
        values.update(
            (key, value) for key, value in (answers or {}).get(step, {}).items() if key in values
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], values)
    raise AssertionError(f"the flow did not end: {result}")


# How a new bed reaches its app's journey: a typed address, a device picked
# from the list, or a discovered bed whose app is searched for.
NEW_BED_ROUTES = ("typed", "picked", "discovered")


async def start_new_bed(
    flow: Any, route: str, choice: str, address: str = "11:22:33:44:55:66"
) -> Any:
    """Start a new bed's journey with ``choice`` from the app question, as ``route`` does.

    A picked or discovered device is the flow's ``_discovery_info``.
    """
    from custom_components.adjustable_bed.detection import resolve_bed_type_choice

    if route == "typed":
        flow._discovery_info = None
        flow._selected_bed_type, flow._selected_protocol_variant = resolve_bed_type_choice(choice)
        return await flow.async_step_manual_entry({"address": address})
    # As the app question continues once a row is chosen.
    flow._new_bed_origin = route
    flow._selected_bed_type, flow._selected_protocol_variant = resolve_bed_type_choice(choice)
    flow._app_after_device = "device"
    return await flow._async_after_app_choice()


async def finish_new_bed(flow: Any, result: Any, settings: Mapping[str, Any] | None = None) -> Any:
    """Submit a new bed's final settings, once its journey has reached them."""
    if isinstance(result, Mapping) and result.get("step_id") == "finish_settings":
        return await flow.async_step_finish_settings(dict(settings or {}))
    return result
