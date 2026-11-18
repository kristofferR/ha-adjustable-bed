"""Explicit Woosa selection must survive setup, options, and offline routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.solace.controller import SolaceController
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_CONNECTION_MODE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SOLACE_VARIANT_WOOSA,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import get_bed_type_options
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    effective_child_data,
    supports_single_address_pairing,
)
from custom_components.adjustable_bed.profiles.ff_frame import SOLACE_PROFILES
from custom_components.adjustable_bed.validators import (
    get_variants_for_bed_type,
    is_valid_variant_for_bed_type,
)


def _entry_data(name: str = "QMS2", variant: str = SOLACE_VARIANT_WOOSA) -> dict:
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:11",
        CONF_NAME: "Bedroom bed",
        CONF_BLE_DEVICE_NAME: name,
        CONF_BED_TYPE: BED_TYPE_SOLACE,
        CONF_PROTOCOL_VARIANT: variant,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
        CONF_CONNECTION_MODE: "idle",
    }


def test_woosa_is_an_explicit_solace_variant() -> None:
    variants = get_variants_for_bed_type(BED_TYPE_SOLACE)
    assert variants is not None
    assert SOLACE_VARIANT_WOOSA in variants
    assert any(
        option["value"] == f"{BED_TYPE_SOLACE}:{SOLACE_VARIANT_WOOSA}"
        for option in get_bed_type_options()
    )
    assert is_valid_variant_for_bed_type(BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA)
    assert not is_valid_variant_for_bed_type(BED_TYPE_OCTO, SOLACE_VARIANT_WOOSA)
    assert not supports_single_address_pairing(BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA)


@pytest.mark.parametrize("name", ["QMS2", "QMS-MQ-123"])
@pytest.mark.parametrize("variant", [None, VARIANT_AUTO, SOLACE_VARIANT_WOOSA])
async def test_factory_requires_explicit_woosa_selection(
    hass: HomeAssistant, name: str, variant: str | None
) -> None:
    from custom_components.adjustable_bed.beds.woosa import WoosaController

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(name))
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(
        coordinator, BED_TYPE_SOLACE, variant, None, device_name=name
    )
    if variant == SOLACE_VARIANT_WOOSA:
        assert isinstance(controller, WoosaController)
        assert controller.profile is SOLACE_PROFILES["woosa"]
    else:
        assert type(controller) is SolaceController
        assert controller.profile is SOLACE_PROFILES["common"]
        assert not controller.supports_massage


async def test_manual_setup_saves_woosa_profile(hass: HomeAssistant) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow._selected_bed_type, flow._selected_protocol_variant = BED_TYPE_SOLACE, SOLACE_VARIANT_WOOSA
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await flow.async_step_manual_entry({CONF_ADDRESS: _entry_data()[CONF_ADDRESS]})
        # The Woosa Sleep row is the answer; its different controls are shown first.
        assert result["step_id"] == "solace_woosa"
        result = await flow.async_step_solace_woosa({})
        # The app's fixed layout ignores a motor count a client still submits.
        result = await flow.async_step_finish_settings(
            {CONF_NAME: "Bedroom bed", CONF_MOTOR_COUNT: 4, CONF_CONNECTION_MODE: "idle"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROTOCOL_VARIANT] == SOLACE_VARIANT_WOOSA
    assert result["data"][CONF_MOTOR_COUNT] == 2


async def test_paired_options_preserve_different_side_profiles(hass: HomeAssistant) -> None:
    left = _entry_data()
    right = {**_entry_data(variant=VARIANT_AUTO), CONF_ADDRESS: "AA:BB:CC:DD:EE:22"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(left, right, name="Paired bed"),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    result = await flow.async_step_settings({CONF_IDLE_DISCONNECT_SECONDS: 60})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    left_data = effective_child_data(entry.data, "left")
    right_data = effective_child_data(entry.data, "right")
    assert left_data[CONF_PROTOCOL_VARIANT] == SOLACE_VARIANT_WOOSA
    assert right_data[CONF_PROTOCOL_VARIANT] == VARIANT_AUTO
    for side_data, expected in (
        (left_data, SOLACE_PROFILES["woosa"]), (right_data, SOLACE_PROFILES["common"])
    ):
        child = AdjustableBedCoordinator(hass, MockConfigEntry(domain=DOMAIN, data=side_data))
        await child.async_prime_offline_controller()
        assert child.capability_controller.profile is expected


async def test_explicit_woosa_mints_offline_without_ble_name(hass: HomeAssistant) -> None:
    from custom_components.adjustable_bed.beds.woosa import WoosaController

    data = _entry_data()
    data.pop(CONF_BLE_DEVICE_NAME)
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    coordinator = AdjustableBedCoordinator(hass, entry)

    await coordinator.async_prime_offline_controller()

    assert isinstance(coordinator.capability_controller, WoosaController)
