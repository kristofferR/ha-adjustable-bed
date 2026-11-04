"""One profile id per config entry (schema 5, #778).

A profile id names the route an entry runs: its bed type, then the protocol
variant when one is stored, then the app profile for the bed types that choose
one through an app key. Examples: ``linak``, ``keeson:sino``,
``jiecang_app@dreamask``, ``leggett_platt:okin@prodigy``.

The saved ``bed_type``, ``protocol_variant`` and app keys stay exactly as the
user chose them. The id is derived from them by :func:`resolve_profile_id`,
stored beside them, and is the key the runtime builds from: the coordinator
reads it and hands its :class:`ProfileRoute` to the controller factory.
Setup re-derives the stored ids before building, so an edit in Configure,
a repair or a runtime protocol correction never leaves a stale one behind.

Two routes share an id only when they are proven equivalent beyond the wire:
setup fields, capabilities, entities and Repairs. None is yet, so every route
keeps its own id; ``docs/design/profile-id.md`` records each byte-identical
group and why it stays separate. Merging one later changes this resolver and
bumps :data:`PROFILE_RESOLVER_VERSION`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import unquote

from .const import (
    BED_TYPE_JIECANG_APP,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_LOGICDATA_APP,
    BED_TYPE_MALOUF_APP,
    BED_TYPE_VIBRADORM_APP,
    CONF_BED_TYPE,
    CONF_JIECANG_APP_PROFILE,
    CONF_LEGGETT_APP_PROFILE,
    CONF_LOGICDATA_APP_PROFILE,
    CONF_MALOUF_APP_PROFILE,
    CONF_PAIR_CHILDREN,
    CONF_PROFILE_ID,
    CONF_PROFILE_MIGRATION,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    CONF_VIBRADORM_APP_PROFILE,
    PAIR_SIDES,
    VARIANT_AUTO,
    resolve_explicit_bed_type,
)

# Bump whenever resolve_profile_id maps any stored fields to a different id.
PROFILE_RESOLVER_VERSION: Final = 1

# The app key that picks a bed type's app profile, by the bed type it builds.
APP_PROFILE_KEYS: Final[Mapping[str, str]] = {
    BED_TYPE_JIECANG_APP: CONF_JIECANG_APP_PROFILE,
    BED_TYPE_LEGGETT_OKIN: CONF_LEGGETT_APP_PROFILE,
    BED_TYPE_LOGICDATA_APP: CONF_LOGICDATA_APP_PROFILE,
    BED_TYPE_MALOUF_APP: CONF_MALOUF_APP_PROFILE,
    BED_TYPE_VIBRADORM_APP: CONF_VIBRADORM_APP_PROFILE,
}
# The saved fields a profile id is derived from.
RESOLVER_FIELDS: Final = (CONF_BED_TYPE, CONF_PROTOCOL_VARIANT, *APP_PROFILE_KEYS.values())

_VARIANT_SEPARATOR: Final = ":"
_APP_SEPARATOR: Final = "@"


def _escape(value: str) -> str:
    # Only the separators are escaped, so saved values stay readable.
    return value.replace("%", "%25").replace(":", "%3A").replace("@", "%40")


@dataclass(frozen=True, slots=True)
class ProfileRoute:
    """The bed type, variant and app profile a profile id builds.

    ``variant`` is None when no variant is stored or it is ``auto``; the
    coordinator then passes ``auto``, as it always has.
    """

    bed_type: str
    variant: str | None = None
    app_profile: str | None = None

    @property
    def profile_id(self) -> str:
        profile_id = _escape(self.bed_type)
        if self.variant is not None:
            profile_id += _VARIANT_SEPARATOR + _escape(self.variant)
        if self.app_profile is not None:
            profile_id += _APP_SEPARATOR + _escape(self.app_profile)
        return profile_id


def app_profile_key(bed_type: str, variant: str | None) -> str | None:
    """Return the app key that picks this route's app profile, if it has one."""
    return APP_PROFILE_KEYS.get(resolve_explicit_bed_type(bed_type, variant))


def profile_route_from_data(data: Mapping[str, Any]) -> ProfileRoute:
    """Return the route saved fields select. Raises ValueError without a bed type."""
    bed_type = data.get(CONF_BED_TYPE)
    if not isinstance(bed_type, str) or not bed_type:
        raise ValueError("A profile id needs a saved bed type")
    stored_variant = data.get(CONF_PROTOCOL_VARIANT)
    variant = (
        stored_variant
        if isinstance(stored_variant, str) and stored_variant != VARIANT_AUTO
        else None
    )
    app_profile = None
    if (key := app_profile_key(bed_type, variant)) is not None:
        stored_app = data.get(key)
        app_profile = stored_app if isinstance(stored_app, str) else None
    return ProfileRoute(bed_type, variant, app_profile)


def resolve_profile_id(data: Mapping[str, Any]) -> str:
    """Return the profile id saved fields select. Raises ValueError without a bed type."""
    return profile_route_from_data(data).profile_id


def profile_route(profile_id: str) -> ProfileRoute:
    """Return the route a profile id builds; the inverse of :func:`resolve_profile_id`."""
    head, app_separator, app_profile = profile_id.partition(_APP_SEPARATOR)
    bed_type, variant_separator, variant = head.partition(_VARIANT_SEPARATOR)
    if not bed_type:
        raise ValueError(f"Invalid profile id {profile_id!r}")
    return ProfileRoute(
        unquote(bed_type),
        unquote(variant) if variant_separator else None,
        unquote(app_profile) if app_separator else None,
    )


def entry_profile_id(data: Mapping[str, Any]) -> str:
    """Return the stored profile id, or derive it for data that has none yet."""
    stored = data.get(CONF_PROFILE_ID)
    if isinstance(stored, str) and stored:
        return stored
    return resolve_profile_id(data)


def _resolver_fields(data: Mapping[str, Any]) -> dict[str, Any]:
    return {key: data[key] for key in RESOLVER_FIELDS if key in data}


def _side_profile_ids(
    data: Mapping[str, Any], options: Mapping[str, Any]
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Return each paired side's profile id and resolver fields, from its effective config."""
    from .pairing import effective_child_data, get_child

    sides: dict[str, tuple[str, dict[str, Any]]] = {}
    for side in PAIR_SIDES:
        if get_child(data, side) is None:
            continue
        view = effective_child_data(data, side, options)
        if isinstance(view.get(CONF_BED_TYPE), str) and view[CONF_BED_TYPE]:
            sides[side] = (resolve_profile_id(view), _resolver_fields(view))
    return sides


def with_profile_ids(
    data: Mapping[str, Any], options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return entry data with the entry's and every paired side's profile id derived.

    A side's id comes from its effective config, as its coordinator reads it, so
    a parent option that changes the side's variant changes its id too. Data
    without a bed type is returned unchanged.
    """
    updated = dict(data)
    if isinstance(data.get(CONF_BED_TYPE), str) and data[CONF_BED_TYPE]:
        updated[CONF_PROFILE_ID] = resolve_profile_id(data)
    sides = _side_profile_ids(data, options or {})
    if sides and isinstance(children := data.get(CONF_PAIR_CHILDREN), list):
        updated[CONF_PAIR_CHILDREN] = [
            {**child, CONF_PROFILE_ID: sides[child[CONF_SIDE]][0]}
            if isinstance(child, dict) and child.get(CONF_SIDE) in sides
            else child
            for child in children
        ]
    return updated


def migrate_v5_data(
    data: Mapping[str, Any],
    options: Mapping[str, Any] | None,
    *,
    from_version: int,
    from_minor_version: int,
) -> dict[str, Any]:
    """Return schema 5 data: profile ids plus a migration record for diagnostics.

    The record keeps the schema the entry came from, the saved fields the ids
    were derived from (unchanged in the entry itself) and the resolver version.
    """
    migrated = with_profile_ids(data, options)
    record: dict[str, Any] = {
        "from_version": from_version,
        "from_minor_version": from_minor_version,
        "resolver_version": PROFILE_RESOLVER_VERSION,
        "profile_id": migrated.get(CONF_PROFILE_ID),
        "fields": _resolver_fields(data),
    }
    if sides := _side_profile_ids(data, options or {}):
        record["sides"] = {
            side: {"profile_id": profile_id, "fields": fields}
            for side, (profile_id, fields) in sides.items()
        }
    migrated[CONF_PROFILE_MIGRATION] = record
    return migrated
