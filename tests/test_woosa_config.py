"""Explicit Woosa selection must survive setup, options, and offline routing."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.solace import SolaceController, SolaceProfile
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    ALL_PROTOCOL_VARIANTS,
    BED_TYPE_OCTO,
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
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
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    effective_child_data,
    supports_single_address_pairing,
)
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
        CONF_DISCONNECT_AFTER_COMMAND: False,
    }


def test_woosa_is_an_explicit_solace_variant() -> None:
    variants = get_variants_for_bed_type(BED_TYPE_SOLACE)
    assert variants is not None
    assert SOLACE_VARIANT_WOOSA in variants
    assert SOLACE_VARIANT_WOOSA in ALL_PROTOCOL_VARIANTS
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
        assert controller.profile is SolaceProfile.WOOSA
    else:
        assert type(controller) is SolaceController
        assert controller.profile is SolaceProfile.COMMON
        assert not controller.supports_massage


async def test_manual_setup_saves_woosa_profile(hass: HomeAssistant) -> None:
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow._selected_bed_type = BED_TYPE_SOLACE
    with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
        result = await flow.async_step_manual_entry(
            {**_entry_data(), CONF_MOTOR_COUNT: 4}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROTOCOL_VARIANT] == SOLACE_VARIANT_WOOSA
    assert result["data"][CONF_MOTOR_COUNT] == 2


async def test_options_select_woosa_and_offline_reload(hass: HomeAssistant) -> None:
    from custom_components.adjustable_bed.beds.woosa import WoosaController

    entry = MockConfigEntry(domain=DOMAIN, data=_entry_data(variant=VARIANT_AUTO))
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    initial = await flow.async_step_settings()
    variants_marker = next(
        marker for marker in initial["data_schema"].schema
        if marker.schema == CONF_PROTOCOL_VARIANT
    )
    assert SOLACE_VARIANT_WOOSA in initial["data_schema"].schema[variants_marker].container
    result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: SOLACE_VARIANT_WOOSA})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_PROTOCOL_VARIANT] == SOLACE_VARIANT_WOOSA

    # A fresh coordinator after reload must retain the explicit app profile,
    # even when discovery is unavailable and the user-facing name was changed.
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert isinstance(coordinator.capability_controller, WoosaController)
    assert coordinator.capability_controller.profile is SolaceProfile.WOOSA
    assert coordinator.capability_controller.supports_massage


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
        (left_data, SolaceProfile.WOOSA), (right_data, SolaceProfile.COMMON)
    ):
        child = AdjustableBedCoordinator(hass, MockConfigEntry(domain=DOMAIN, data=side_data))
        await child.async_prime_offline_controller()
        assert child.capability_controller.profile is expected


@pytest.mark.parametrize(
    ("initial", "requested"),
    [(VARIANT_AUTO, SOLACE_VARIANT_WOOSA), (SOLACE_VARIANT_WOOSA, VARIANT_AUTO)],
)
async def test_paired_options_reject_woosa_profile_change(
    hass: HomeAssistant, initial: str, requested: str
) -> None:
    left = _entry_data(variant=initial)
    right = {**_entry_data(variant=VARIANT_AUTO), CONF_ADDRESS: "AA:BB:CC:DD:EE:22"}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(left, right, name="Paired bed"),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: requested})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "woosa_unpair_first"}
    assert effective_child_data(entry.data, "left")[CONF_PROTOCOL_VARIANT] == initial
    assert effective_child_data(entry.data, "right")[CONF_PROTOCOL_VARIANT] == VARIANT_AUTO


async def test_explicit_woosa_mints_offline_without_ble_name(hass: HomeAssistant) -> None:
    from custom_components.adjustable_bed.beds.woosa import WoosaController

    data = _entry_data()
    data.pop(CONF_BLE_DEVICE_NAME)
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    coordinator = AdjustableBedCoordinator(hass, entry)

    await coordinator.async_prime_offline_controller()

    assert isinstance(coordinator.capability_controller, WoosaController)
