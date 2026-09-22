"""First-time setup must expose diagnostics before a bed is configured."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.download import DATA_DOWNLOAD_TOKENS
from custom_components.adjustable_bed.services import SERVICE_GENERATE_SUPPORT_BUNDLE


@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_BLUETOOTH])
async def test_unfinished_first_setup_can_generate_and_download_bundle(
    hass, hass_client, enable_custom_integrations, mock_bluetooth_service_info, source, tmp_path,
):
    assert not hass.config_entries.async_entries(DOMAIN)
    assert not hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": source},
        data=mock_bluetooth_service_info if source == SOURCE_BLUETOOTH else None,
    )
    assert result["type"] == FlowResultType.FORM
    assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE)
    assert not hass.config_entries.async_entries(DOMAIN)
    hass.config_entries.flow.async_abort(result["flow_id"])

    path = tmp_path / "adjustable_bed_support_bundle_ab12_20260922_120000.json"
    path.write_text('{"notifications": [], "errors": []}')
    with (
        patch(
            "custom_components.adjustable_bed.support_bundle.generate_support_bundle",
            new=AsyncMock(return_value={"notifications": [], "errors": []}),
        ) as generate,
        patch("custom_components.adjustable_bed.support_bundle.save_support_bundle", return_value=path),
    ):
        await hass.services.async_call(
            DOMAIN, SERVICE_GENERATE_SUPPORT_BUNDLE,
            {"target_address": "80:16:09:0A:76:F4", "capture_duration": 10, "include_logs": False},
            blocking=True,
        )
    assert generate.await_args.kwargs["address"] == "80:16:09:0A:76:F4"
    assert generate.await_args.kwargs["coordinator"] is None
    assert generate.await_args.kwargs["entry"] is None
    token = next(iter(hass.data[DOMAIN][DATA_DOWNLOAD_TOKENS]))
    client = await hass_client()
    response = await client.get(f"/api/adjustable_bed/download/{token}")
    assert response.status == 200
    assert await response.json() == {"notifications": [], "errors": []}
