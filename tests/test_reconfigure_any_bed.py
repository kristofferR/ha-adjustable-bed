"""Reconfigure changes any bed's type or app; Add Integration owns discovery."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.discovery_settings import async_is_discovery_disabled
from custom_components.adjustable_bed.profile_migration import reconfigure_context


def _schema(result):
    schema = result["data_schema"]
    assert schema is not None
    return schema


def _entry(hass: HomeAssistant, bed_type: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bed",
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:41", CONF_NAME: "Bed", const.CONF_BED_TYPE: bed_type},
        unique_id="AA:BB:CC:DD:EE:41",
    )
    entry.add_to_hass(hass)
    return entry


async def test_reconfigure_changes_a_bed_without_a_guided_family(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Before, Reconfigure aborted for bed types without a guided family."""
    del enable_custom_integrations
    entry = _entry(hass, const.BED_TYPE_LINAK)
    manager = hass.config_entries.flow

    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    assert result["step_id"] == "reconfigure_bed_type"
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_SERTA}
    )
    assert result["step_id"] == "migration_confirm"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LINAK
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await manager.async_configure(result["flow_id"], {"action": "apply"})

    assert result["reason"] == "migration_applied"
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_SERTA


async def test_reconfigure_to_the_same_bed_changes_nothing(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    del enable_custom_integrations
    entry = _entry(hass, const.BED_TYPE_LINAK)
    before = dict(entry.data)
    manager = hass.config_entries.flow

    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    # The current bed is preselected.
    result = await manager.async_configure(result["flow_id"], _schema(result)({}))
    if result.get("step_id") == "reconfigure_route":
        result = await manager.async_configure(result["flow_id"], _schema(result)({}))

    assert result.get("reason") == "migration_unchanged", result
    assert dict(entry.data) == before


async def test_reconfigure_preselects_a_suggested_app(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    del enable_custom_integrations
    entry = _entry(hass, const.BED_TYPE_LINAK)

    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context=reconfigure_context(entry, const.BED_TYPE_SERTA)
    )

    assert _schema(result)({})[const.CONF_BED_TYPE] == const.BED_TYPE_SERTA
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_add_integration_turns_discovery_off_and_on(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """The integration-wide switch lives where beds are added, not in each bed."""
    del enable_custom_integrations
    manager = hass.config_entries.flow
    result = await manager.async_init(const.DOMAIN, context={"source": "user"})
    result = await manager.async_configure(result["flow_id"], {CONF_ADDRESS: "discovery"})
    assert result["step_id"] == "discovery_settings"
    assert _schema(result)({})["discover_new_beds"] is True

    result = await manager.async_configure(result["flow_id"], {"discover_new_beds": False})

    assert result["reason"] == "discovery_saved"
    assert await async_is_discovery_disabled(hass)


async def test_a_picked_device_lets_home_assistant_choose_the_adapter(hass: HomeAssistant) -> None:
    """The scanner that listed a picked bed is no preference: it warned on every connect."""
    from homeassistant.config_entries import SOURCE_USER

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.test_detection import _make_service_info

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": SOURCE_USER}
    info = _make_service_info(name="Bed 1234", address="AA:BB:CC:DD:EE:42")
    info.source = "esphome_bedroom"
    flow._all_ble_devices = {info.address: info}
    flow._selected_bed_type = const.BED_TYPE_LINAK

    result = await flow.async_step_manual({CONF_ADDRESS: info.address})

    assert result["step_id"] == "finish_settings"
    assert flow._manual_data[const.CONF_PREFERRED_ADAPTER] == const.ADAPTER_AUTO


async def test_reconfigure_to_a_checked_route_checks_its_link_first(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A destination whose family checks its link is checked before the review."""
    del enable_custom_integrations
    entry = _entry(hass, const.BED_TYPE_LINAK)
    manager = hass.config_entries.flow

    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_SLEEPYS_BOX25}
    )

    if result.get("step_id") == "profile_questions":
        result = await manager.async_configure(result["flow_id"], _schema(result)({}))
    assert result.get("step_id") == "migration_check", result
    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LINAK
    manager.async_abort(result["flow_id"])


async def test_reconfigure_drops_the_previous_apps_own_settings(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """A VMAT app's settings must not follow the bed to another bed type."""
    del enable_custom_integrations
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:45",
            CONF_NAME: "Bed",
            const.CONF_BED_TYPE: const.BED_TYPE_LINAK,
            const.CONF_VIBRADORM_APP_PROFILE: "vmat",
        },
        unique_id="AA:BB:CC:DD:EE:45",
    )
    entry.add_to_hass(hass)
    manager = hass.config_entries.flow
    result = await manager.async_init(const.DOMAIN, context=reconfigure_context(entry))
    result = await manager.async_configure(
        result["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_SERTA}
    )
    assert result["step_id"] == "migration_confirm"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await manager.async_configure(result["flow_id"], {"action": "apply"})

    assert entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_SERTA
    assert const.CONF_VIBRADORM_APP_PROFILE not in entry.data


async def test_reconfigure_to_adjustablem5x4_needs_a_proven_transport(hass: HomeAssistant) -> None:
    """An unresolved AdjustableM5X4 transport fails the check rather than reaching Apply."""
    from unittest.mock import AsyncMock

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        CapabilityReport,
    )
    from custom_components.adjustable_bed.profile_migration import MigrationSnapshot
    from custom_components.adjustable_bed.setup_operation import OperationOutcome

    entry = _entry(hass, const.BED_TYPE_LINAK)
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, reconfigure_context(entry)
    flow._migration = MigrationSnapshot.of(entry)
    flow._pending_entry = {**entry.data, const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4}
    report = CapabilityReport(device_found=True, connected=True)
    with patch.object(
        AdjustableBedConfigFlow, "_probe_capabilities", AsyncMock(return_value=report)
    ):
        result = await flow._async_probe_worker_reserved()

    assert result.outcome is OperationOutcome.CONNECTION_FAILED
