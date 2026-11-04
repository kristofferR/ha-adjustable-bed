"""The card learns which controls may lease a renewable hold (#483)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import MotorControlSpec
from custom_components.adjustable_bed.button import PairedBedCombinedMotorButton
from custom_components.adjustable_bed.const import SIDE_LEFT, SIDE_RIGHT
from custom_components.adjustable_bed.cover import (
    AdjustableBedCover,
    _build_cover_description,
)
from custom_components.adjustable_bed.entity import hold_lease_attributes
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)

STREAM = SimpleNamespace(execution=ExecutionCapabilities(hold="stream"))
LATCHED = SimpleNamespace(execution=ExecutionCapabilities(hold="latched"))
NO_HOLD = SimpleNamespace(execution=NO_EXECUTION_CAPABILITIES)


@pytest.mark.parametrize(
    ("controllers", "motor", "expected"),
    [
        ([STREAM], "back", {"hold_lease_mode": "stream", "hold_lease_motor": "back"}),
        ([LATCHED, LATCHED], None, {"hold_lease_mode": "latched"}),
        # A motor timed_move cannot name leaves only the held-control route.
        ([STREAM], "massage", {"hold_lease_mode": "stream"}),
        ([NO_HOLD], "back", {}),
        ([STREAM, LATCHED], "back", {}),
        ([STREAM, None], "back", {}),
        ([STREAM, NO_HOLD], "back", {}),
        ([], "back", {}),
    ],
)
def test_one_declared_mode_across_every_target_offers_a_lease(controllers, motor, expected):
    assert hold_lease_attributes(controllers, motor) == expected


def _spec(key: str = "back") -> MotorControlSpec:
    return MotorControlSpec(key, key, AsyncMock(), AsyncMock(), AsyncMock())


def test_cover_advertises_its_controller_hold_and_timed_motor():
    runtime = SimpleNamespace(
        capability_controller=STREAM,
        entity_side=SIDE_LEFT,
        device_info={},
        entity_translation_key=lambda key: key,
        entity_unique_id=lambda key: key,
    )
    cover = AdjustableBedCover(runtime, _build_cover_description(_spec()))
    assert cover.extra_state_attributes == {
        "bed_side": SIDE_LEFT,
        "hold_lease_mode": "stream",
        "hold_lease_motor": "back",
    }
    runtime.capability_controller = NO_HOLD
    assert cover.extra_state_attributes == {"bed_side": SIDE_LEFT}


@pytest.mark.parametrize(
    ("mode", "right", "expected"),
    [
        ("concurrent", STREAM, {"hold_lease_mode": "stream", "hold_lease_motor": "back"}),
        ("concurrent", LATCHED, {}),
        ("concurrent", NO_HOLD, {}),
        # Separate receivers held one after another cannot hold together.
        ("sequential", STREAM, {}),
    ],
)
def test_combined_motor_offers_a_hold_only_when_both_sides_agree(mode, right, expected):
    spec = _spec()
    coordinator = MagicMock(pair_id="pair", device_info={}, connection_mode=mode)
    coordinator.children = {
        side: SimpleNamespace(
            capability_controller=SimpleNamespace(
                execution=controller.execution, motor_control_specs=[spec]
            ),
            bed_type="linak",
        )
        for side, controller in ((SIDE_LEFT, STREAM), (SIDE_RIGHT, right))
    }
    attributes = PairedBedCombinedMotorButton(coordinator, spec, "up").extra_state_attributes
    assert {key: attributes[key] for key in attributes if key.startswith("hold_lease")} == expected
