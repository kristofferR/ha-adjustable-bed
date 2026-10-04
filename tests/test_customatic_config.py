"""Explicit Customatic profile selection and fixed layout gates."""

from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
from custom_components.adjustable_bed.config_flow import (
    _default_motor_count,
    _is_valid_motor_count,
    _motor_count_options,
    _normalize_fixed_motor_count,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    BED_TYPE_ZSERIES,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import _create_from_registry
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES, detect_bed_type
from tests.test_controller_contract import _FactoryCoordinator

PROFILES = [
    (BED_TYPE_CUSTOMATIC_CLARITY, "clarity", 2),
    (BED_TYPE_CUSTOMATIC_JEROMES, "jeromes", 2),
    (BED_TYPE_CUSTOMATIC_REMEDY, "remedy", 3),
]


@pytest.mark.parametrize(("bed_type", "profile", "motors"), PROFILES)
async def test_explicit_selection_constructs_matching_profile(bed_type, profile, motors):
    controller = await _create_from_registry(_FactoryCoordinator(), bed_type)
    assert controller is not None
    assert controller.protocol_diagnostics["profile"] == profile
    assert {spec.key for spec in controller.motor_control_specs} == (
        {"back", "legs", "lumbar"} if motors == 3 else {"back", "legs"}
    )
    assert BED_TYPE_DISPLAY_NAMES[bed_type]


@pytest.mark.parametrize(("bed_type", "profile", "motors"), PROFILES)
def test_layout_counts_and_no_invented_feedback_or_pairing(bed_type, profile, motors):
    assert _motor_count_options(bed_type) == [motors]
    assert _default_motor_count(bed_type) == motors
    for count in (1, 2, 3, 4):
        assert _is_valid_motor_count(bed_type, "auto", count) is (count == motors)
        assert _normalize_fixed_motor_count(bed_type, "auto", count) == motors
    assert not requires_pairing(bed_type)
    assert not bed_type_has_position_feedback(bed_type, "auto")
    assert get_motor_pulse_defaults(bed_type)[1] == 120


def test_customatic_group_lists_each_explicit_package_profile():
    variants = ACTUATOR_GROUPS["customatic"]["variants"]
    assert variants is not None
    assert {item["type"] for item in variants} == {item[0] for item in PROFILES} | {
        BED_TYPE_ZSERIES
    }
    assert [item.get("variant") for item in variants if item["type"] == BED_TYPE_ZSERIES] == [
        "z230",
        "z280",
    ]


@pytest.mark.parametrize("name", ["OKIN-Receiver", "OKIN", "iFlex_Bed", "iFlex_Bed-1234"])
def test_shared_bluetooth_name_does_not_infer_customatic_package(name):
    service_info = MagicMock()
    service_info.name = name
    service_info.address = "AA:BB:CC:DD:EE:FF"
    service_info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    service_info.manufacturer_data = {}
    result = detect_bed_type(service_info)
    assert result not in {item[0] for item in PROFILES}
