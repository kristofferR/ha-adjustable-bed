"""Static bed traits: the defaults a new entry and the coordinator start from."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.bed_traits import (
    bed_traits,
    disconnect_after_command_default_enabled,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDJET_POWERLAYER,
    BED_TYPE_DOUBLESLEEP,
    BED_TYPE_GOODVIBE,
    BED_TYPE_JENSEN,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_OKIN_RF_ECO_BT,
    BED_TYPE_REVERIE,
    BED_TYPE_REVERIE_NIGHTSTAND,
    BED_TYPE_SBI,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_STARCODE_ABM5_4,
    CONF_BED_TYPE,
    DOMAIN,
    KEESON_VARIANT_DYNASTY_BASES,
    KEESON_VARIANT_ERGOMOTION,
    KEESON_VARIANT_OKIN,
    STARCODE_APP_CONNECTION_TIMEOUT_SECONDS,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.mark.parametrize("variant", [VARIANT_AUTO, "both", "side_a", "side_b"])
def test_sbi_reports_positions(variant: str) -> None:
    """The pulse-table feedback enabled in #239 reaches setup and entities."""
    assert bed_traits(BED_TYPE_SBI, variant).position_feedback


@pytest.mark.parametrize(
    ("bed_type", "variant"),
    [
        (BED_TYPE_DOUBLESLEEP, "p1"),
        (BED_TYPE_OKIN_RF_ECO_BT, None),
        ("richmat_sleep_receiver", "wsilver2"),
    ],
)
def test_persistent_beds_keep_the_link_by_default(bed_type: str, variant: str | None) -> None:
    """A controller that holds its link must not default to disconnecting."""
    traits = bed_traits(bed_type, variant)
    assert traits.persistent_connection
    assert not disconnect_after_command_default_enabled(bed_type, variant)


@pytest.mark.parametrize(
    ("variant", "feedback", "percent", "scoped"),
    [
        (VARIANT_AUTO, False, True, True),
        (KEESON_VARIANT_ERGOMOTION, True, True, True),
        (KEESON_VARIANT_OKIN, False, True, False),
        (KEESON_VARIANT_DYNASTY_BASES, False, False, False),
    ],
)
def test_keeson_traits_follow_the_variant(
    variant: str, feedback: bool, percent: bool, scoped: bool
) -> None:
    traits = bed_traits(BED_TYPE_KEESON, variant)
    assert traits.position_feedback is feedback
    assert traits.percentage_positions is percent
    assert traits.connection_scoped_state is scoped


def test_reverie_model_without_positions_has_no_position_traits() -> None:
    traits = bed_traits(BED_TYPE_REVERIE_NIGHTSTAND, "3E")
    assert not (traits.position_feedback or traits.angle_sensors or traits.percentage_positions)
    assert bed_traits(BED_TYPE_REVERIE_NIGHTSTAND, "R650").percentage_positions


@pytest.mark.parametrize(("profile", "expected"), [("sleep_rm", False), ("selector-0001", True)])
def test_goodvibe_sleep_sensors_keep_the_link(profile: str, expected: bool) -> None:
    assert disconnect_after_command_default_enabled(BED_TYPE_GOODVIBE, profile) is expected


@pytest.mark.parametrize(("bed_type", "expected"), [(BED_TYPE_LINAK, True), (BED_TYPE_JENSEN, False)])
async def test_runtime_default_matches_the_setup_default(
    hass: HomeAssistant, bed_type: str, expected: bool
) -> None:
    """An entry that never stored the option uses the bed type's default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bed", CONF_BED_TYPE: bed_type},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    coordinator = AdjustableBedCoordinator(hass, entry)

    assert coordinator._disconnect_after_command is expected


@pytest.mark.parametrize("bed_type", [BED_TYPE_DOUBLESLEEP, BED_TYPE_OKIN_RF_ECO_BT])
async def test_persistent_beds_hold_the_link_before_first_connect(
    hass: HomeAssistant, bed_type: str
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bed", CONF_BED_TYPE: bed_type},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    coordinator = AdjustableBedCoordinator(hass, entry)

    assert coordinator._controller is None
    assert coordinator._uses_persistent_connection()


async def test_starcode_app_connect_timeout_overrides_the_profile(hass: HomeAssistant) -> None:
    """The StarCode app's own connect timeout replaces the connection profile's."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Bed",
            CONF_BED_TYPE: BED_TYPE_STARCODE_ABM5_4,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    coordinator = AdjustableBedCoordinator(hass, entry)

    assert coordinator._connection_timeout == STARCODE_APP_CONNECTION_TIMEOUT_SECONDS
    assert bed_traits(BED_TYPE_LINAK).connection_timeout is None


@pytest.mark.parametrize(
    ("bed_type", "expected"),
    [
        (BED_TYPE_SBI, {"back": 60.0, "head": 68.0, "legs": 32.0, "feet": 45.0}),
        (BED_TYPE_SERTA_MP_REMOTE, {"back": 60.0, "head": 68.0, "legs": 45.0, "feet": 45.0}),
        (BED_TYPE_REVERIE, {"back": 60.0, "head": 60.0, "legs": 45.0, "feet": 45.0}),
        (BED_TYPE_BEDJET_POWERLAYER, {"back": 73.0, "head": 73.0, "legs": 47.0, "feet": 47.0}),
        (BED_TYPE_LINAK, {"back": 68.0, "head": 68.0, "legs": 45.0, "feet": 45.0}),
    ],
)
async def test_max_angles_come_from_the_bed_before_connecting(
    hass: HomeAssistant, bed_type: str, expected: dict[str, float]
) -> None:
    """Set-position validation uses the frame's travel, and the configured default otherwise."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bed", CONF_BED_TYPE: bed_type},
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)

    coordinator = AdjustableBedCoordinator(hass, entry)

    assert coordinator.controller is None
    assert {axis: coordinator.get_max_angle(axis) for axis in expected} == expected
