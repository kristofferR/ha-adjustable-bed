"""Connect-time lifecycle hooks declared on BedController."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.octo.controller import OctoController
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_VARIANT_STANDARD,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

ADDRESS = "AA:BB:CC:DD:EE:FF"


class RecordingSession:
    """A ControllerSession that records which services a hook used, in order."""

    def __init__(self, hass: HomeAssistant, calls: list[str]) -> None:
        self.hass = hass
        self.entry_id = "octo_entry"
        self.address = ADDRESS
        self.name = "Octo"
        self.model = "Model"
        self.client = None
        self.angle_sensing_disabled = True
        self._calls = calls

    def disable_angle_sensing(self) -> None:
        self._calls.append("disable_angle_sensing")

    def is_current(self) -> bool:
        return True

    async def async_start_notify(self) -> None:
        self._calls.append("start_notify")

    async def async_record_verified_bond(self) -> None:
        self._calls.append("record_verified_bond")

    def persist_capability_snapshot(self) -> None:
        self._calls.append("persist_capability_snapshot")

    def store_device_info(self, manufacturer: str | None, model: str | None) -> None:
        self._calls.append("store_device_info")


def _octo_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Octo",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
        },
        entry_id="octo_entry",
    )
    entry.add_to_hass(hass)
    return entry


async def test_octo_startup_runs_discovery_snapshot_pin_keepalive_in_order(
    hass: HomeAssistant,
) -> None:
    """PIN and keepalive follow a completed discovery and the snapshot persist."""
    controller = OctoController(AdjustableBedCoordinator(hass, _octo_entry(hass)))
    calls: list[str] = []

    async def record(name: str, result: Any = None) -> Any:
        calls.append(name)
        return result

    async def discover() -> bool:
        controller._pin_feature_active = True
        controller._has_pin = True
        controller._pin_locked = True
        return await record("discover_features", True)

    with (
        patch.object(controller, "discover_features", discover),
        patch.object(controller, "send_pin", lambda: record("send_pin")),
        patch.object(controller, "start_keepalive", lambda: record("start_keepalive")),
    ):
        await controller.async_on_connect(RecordingSession(hass, calls))

    assert calls == [
        "start_notify",
        "discover_features",
        "persist_capability_snapshot",
        "send_pin",
        "start_keepalive",
    ]
    # Locked with no configured PIN: the repair is raised last.
    assert ir.async_get(hass).async_get_issue(DOMAIN, "octo_pin_required_aa_bb_cc_dd_ee_ff")


async def test_octo_incomplete_discovery_fails_before_pin(hass: HomeAssistant) -> None:
    controller = OctoController(AdjustableBedCoordinator(hass, _octo_entry(hass)))
    calls: list[str] = []

    async def discover() -> bool:
        return False

    with (
        patch.object(controller, "discover_features", discover),
        pytest.raises(ConnectionError),
    ):
        await controller.async_on_connect(RecordingSession(hass, calls))

    assert calls == ["start_notify"]


async def test_octo_snapshot_persists_only_for_a_paired_side(hass: HomeAssistant) -> None:
    """A standalone Octo entry keeps its discovered capabilities session-only."""
    entry = _octo_entry(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = OctoController(coordinator)
    coordinator._controller = controller

    with patch.object(controller, "capability_snapshot", return_value={"memory_count": 2}):
        coordinator._persist_capability_snapshot()

    assert "capabilities" not in entry.data
    assert coordinator._offline_controller is None

