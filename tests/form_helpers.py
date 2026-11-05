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
