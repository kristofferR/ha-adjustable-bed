"""Why each byte-identical group in the protocol inventory keeps separate profile ids.

Equal wire bytes are not enough to share a profile id (#778): setup fields,
capabilities, entities and Repairs must match too. Each test pins one non-wire
difference per group, so the reasons in docs/design/profile-id.md stay true. If
a test here starts failing because the difference is gone, the group may now be
provable; prove the rest and merge it in profile_id.py rather than deleting the test.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_HAS_LIGHT,
    CONF_HAS_MASSAGE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    RICHMAT_MH_APPS,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import bed_type_label, get_bed_type_options
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_review import related_app_choices

_PICKER = {option["value"] for option in get_bed_type_options()}


def _data(route: str) -> dict[str, Any]:
    bed_type, _, variant = route.partition(":")
    return {CONF_BED_TYPE: bed_type, **({CONF_PROTOCOL_VARIANT: variant} if variant else {})}


def _coordinator(hass: HomeAssistant, route: str) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_NAME: "Bed", **_data(route)},
        version=5,
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


@pytest.mark.parametrize(
    "group",
    [
        ("comfort_motion", "jiecang"),
        # Okin UUID is one answer behind the Okin family row.
        ("okimat", "furnimove"),
        ("dewertokin", "okin_handle"),
        ("nectar", "okin_7byte"),
        ("mattressfirm", "okin_nordic"),
        ("ergomotion", "keeson:ergomotion"),
        ("serta", "keeson:serta"),
        ("leggett_okin", "leggett_platt", "leggett_platt:okin"),
        ("leggett_gen2", "leggett_platt:gen2"),
        (
            "keeson:americanstar",
            "keeson:avanti_bases",
            "keeson:bedsense_bases",
            "keeson:dynasty_bases",
            "keeson:maxcoil_una",
        ),
        ("richmat_best_mattress:model_bfrm", "richmat_blvd_home:model_bfrm"),
    ],
)
def test_byte_identical_groups_keep_one_id_per_route(group: tuple[str, ...]) -> None:
    assert len({resolve_profile_id(_data(route)) for route in group}) == len(group)


@pytest.mark.parametrize(
    ("alias", "canonical", "alias_maker", "canonical_maker"),
    [
        ("comfort_motion", "jiecang", "Comfort Motion", "Jiecang"),
        ("okimat", "okin_uuid", "Okimat", "Okin"),
        ("dewertokin", "okin_handle", "DewertOkin", "Okin"),
        ("nectar", "okin_7byte", "Nectar", "Okin"),
        ("mattressfirm", "okin_nordic", "MattressFirm", "Okin"),
        ("ergomotion", "keeson:ergomotion", "Ergomotion", "Keeson"),
        ("serta", "keeson:serta", "Serta", "Keeson"),
    ],
)
async def test_device_manufacturer_differs(
    hass: HomeAssistant, alias: str, canonical: str, alias_maker: str, canonical_maker: str
) -> None:
    """The device registry's fallback manufacturer is keyed by bed type."""
    assert _coordinator(hass, alias).device_info["manufacturer"] == alias_maker
    assert _coordinator(hass, canonical).device_info["manufacturer"] == canonical_maker


@pytest.mark.parametrize(
    ("legacy", "offered"),
    [
        # Okin UUID is one answer behind the Okin family row.
        ("okimat", "furnimove"),
        ("dewertokin", "okin_handle"),
        ("nectar", "okin_7byte"),
        ("mattressfirm", "okin_nordic"),
        ("leggett_platt", "leggett_okin"),
    ],
)
def test_legacy_bed_types_are_not_offered_in_setup(legacy: str, offered: str) -> None:
    """Setup offers only the canonical bed type; the legacy one exists only in saved entries."""
    assert legacy not in _PICKER
    assert offered in _PICKER


@pytest.mark.parametrize(
    ("route", "other"),
    [("comfort_motion", "jiecang"), ("dewertokin", "okin_handle")],
)
def test_profile_review_repairs_differ(route: str, other: str) -> None:
    """The one-time app profile review (a Repairs issue) lists apps for one route only."""
    assert related_app_choices(route, None)
    assert related_app_choices(other, None) == []


@pytest.mark.parametrize(("alias", "canonical"), [("ergomotion", "keeson:ergomotion"), ("serta", "keeson:serta")])
async def test_offline_entities_differ(hass: HomeAssistant, alias: str, canonical: str) -> None:
    """Only the bed type mints its controller, and so its entities, before connecting."""
    minted = _coordinator(hass, alias)
    await minted.async_prime_offline_controller()
    assert minted.capability_controller is not None

    unminted = _coordinator(hass, canonical)
    await unminted.async_prime_offline_controller()
    assert unminted.capability_controller is None


async def test_leggett_umbrella_picks_its_controller_at_connect(hass: HomeAssistant) -> None:
    coordinator = _coordinator(hass, "leggett_platt")
    with pytest.raises(ConnectionError):
        await create_controller(coordinator, "leggett_platt", "auto", None)


def test_ore_app_routes_differ_in_setup_fields() -> None:
    routes = ("americanstar", "avanti_bases", "bedsense_bases", "dynasty_bases", "maxcoil_una")
    hidden = {route: hidden_generic_fields("keeson", route) for route in routes}
    side = {route: per_side_profile("keeson", route) for route in routes}
    # Avanti Bases hides more generic fields than the other four.
    assert hidden["avanti_bases"] != hidden["americanstar"] == hidden["maxcoil_una"]
    # Every app's 2M, 3M or 4M screen is one receiver's motor count (#745).
    assert all(profile and profile.keys == {"motor_count"} for profile in side.values())
    # Each is its own app: setup names it in the picker and in per-side errors.
    assert len({profile.label for profile in side.values() if profile}) == len(routes)
    labels = {option["value"]: option["label"] for option in get_bed_type_options()}
    assert len({labels[f"keeson:{route}"] for route in routes}) == len(routes)


def test_richmat_bfrm_model_belongs_to_two_apps() -> None:
    assert RICHMAT_MH_APPS["richmat_best_mattress"] != RICHMAT_MH_APPS["richmat_blvd_home"]
    # Each app keeps its own label: the Richmat question names them separately.
    assert bed_type_label("richmat_best_mattress") != bed_type_label("richmat_blvd_home")


def test_fsm_relax_flags_are_settings_of_one_profile() -> None:
    """The light and massage flags are settings, not routes: one profile id."""
    assert (
        resolve_profile_id({CONF_BED_TYPE: "fsm_relax"})
        == resolve_profile_id({CONF_BED_TYPE: "fsm_relax", CONF_HAS_LIGHT: True, CONF_HAS_MASSAGE: True})
        == "fsm_relax"
    )
