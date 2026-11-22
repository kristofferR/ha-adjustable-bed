"""Entities that add their own attributes keep the paired side (PLAT-7)."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.adjustable_bed.beds.entity_specs import ControllerStateSensorSpec
from custom_components.adjustable_bed.const import SIDE_LEFT
from custom_components.adjustable_bed.controller_state import StateKey
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

LEVEL = StateKey[int]("level")
MODE = StateKey[str]("mode")


def test_controller_state_sensor_keeps_bed_side_with_its_attributes() -> None:
    runtime = SimpleNamespace(
        entity_side=SIDE_LEFT,
        device_info={},
        entity_unique_id=lambda key: key,
        controller_state={LEVEL: 3, MODE: "wave"},
    )
    spec = ControllerStateSensorSpec("level", "level", LEVEL, "mdi:gauge", attribute_keys=(MODE,))
    sensor = AdjustableBedControllerStateSensor(runtime, spec)

    assert sensor.extra_state_attributes == {"bed_side": SIDE_LEFT, "mode": "wave"}
