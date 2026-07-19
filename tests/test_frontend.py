"""Tests for the bundled Adjustable Bed Lovelace card registration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.lovelace import LovelaceData
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.components.lovelace.resources import (
    ResourceStorageCollection,
    ResourceYAMLCollection,
)
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.frontend import (
    CARD_URL,
    DATA_FRONTEND_REGISTERED,
    URL_BASE,
    _async_register_lovelace_resource,
    _gather,
    async_register_frontend,
)


def _storage_resources(items: list[dict[str, str]]) -> MagicMock:
    """Return a storage resource collection mock with the given items."""
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.async_get_info = AsyncMock(return_value={"resources": len(items)})
    resources.async_items.return_value = items
    resources.async_create_item = AsyncMock()
    resources.async_update_item = AsyncMock()
    return resources


def test_gather_uses_bundle_digest_in_cache_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Card changes invalidate the browser cache without a version bump."""
    card = tmp_path / "adjustable-bed-card.js"
    card.write_bytes(b"first bundle")
    monkeypatch.setattr(
        "custom_components.adjustable_bed.frontend._dist_dir",
        lambda: tmp_path,
    )

    exists, version, first_cache_key = _gather()
    card.write_bytes(b"changed bundle")
    _, changed_version, changed_cache_key = _gather()

    assert exists
    assert changed_version == version
    assert first_cache_key.startswith(f"{version}-")
    assert changed_cache_key.startswith(f"{version}-")
    assert changed_cache_key != first_cache_key


async def test_register_lovelace_resource_creates_missing_resource(
    hass: HomeAssistant,
) -> None:
    """The card is persisted so Lovelace can load it independently."""
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})
    card_url = f"{CARD_URL}?v=3.3.0-abc123"

    assert await _async_register_lovelace_resource(hass, card_url)

    assert [
        {CONF_TYPE: item[CONF_TYPE], CONF_URL: item[CONF_URL]}
        for item in resources.async_items()
    ] == [{CONF_TYPE: "module", CONF_URL: card_url}]


async def test_register_lovelace_resource_updates_stale_resource(
    hass: HomeAssistant,
) -> None:
    """Lazy-loaded storage updates the card without touching other resources."""
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    await resources.store.async_save(
        {
            "items": [
                {
                    CONF_ID: "resource-id",
                    CONF_TYPE: "js",
                    CONF_URL: f"{CARD_URL}?v=3.2.1",
                },
                {
                    CONF_ID: "other-resource",
                    CONF_TYPE: "module",
                    CONF_URL: "/local/unrelated-card.js",
                },
            ]
        }
    )
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})
    assert not resources.loaded
    card_url = f"{CARD_URL}?v=3.3.0-def456"

    assert await _async_register_lovelace_resource(hass, card_url)

    assert resources.loaded
    assert sorted(resources.async_items(), key=lambda item: item[CONF_ID]) == [
        {
            CONF_ID: "other-resource",
            CONF_TYPE: "module",
            CONF_URL: "/local/unrelated-card.js",
        },
        {
            CONF_ID: "resource-id",
            CONF_TYPE: "module",
            CONF_URL: card_url,
        },
    ]


async def test_register_lovelace_resource_leaves_current_resource_unchanged(
    hass: HomeAssistant,
) -> None:
    """Repeated setup is idempotent."""
    card_url = f"{CARD_URL}?v=3.3.0-abc123"
    resources = _storage_resources(
        [
            {
                CONF_ID: "resource-id",
                CONF_TYPE: "module",
                CONF_URL: card_url,
            }
        ]
    )
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})

    assert await _async_register_lovelace_resource(hass, card_url)

    resources.async_create_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()


async def test_register_lovelace_resource_rejects_yaml_resources(
    hass: HomeAssistant,
) -> None:
    """YAML resource collections are immutable and use the module fallback."""
    hass.data[LOVELACE_DATA] = LovelaceData(
        "yaml",
        {},
        ResourceYAMLCollection([]),
        {},
    )

    assert not await _async_register_lovelace_resource(
        hass,
        f"{CARD_URL}?v=3.3.0-abc123",
    )


async def test_register_frontend_uses_resource_and_module_hook(
    hass: HomeAssistant,
) -> None:
    """Storage mode is durable while retaining early frontend module loading."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with (
        patch(
            "custom_components.adjustable_bed.frontend._gather",
            return_value=(True, "3.3.0", "3.3.0-abc123"),
        ),
        patch(
            "custom_components.adjustable_bed.frontend._async_register_lovelace_resource",
            new_callable=AsyncMock,
            return_value=True,
        ) as register_resource,
        patch(
            "custom_components.adjustable_bed.frontend.add_extra_js_url"
        ) as add_extra_js_url,
    ):
        await async_register_frontend(hass)
        await async_register_frontend(hass)

    card_url = f"{CARD_URL}?v=3.3.0-abc123"
    register_resource.assert_awaited_once_with(hass, card_url)
    add_extra_js_url.assert_called_once_with(hass, card_url)
    hass.http.async_register_static_paths.assert_awaited_once()
    assert hass.data[DOMAIN][DATA_FRONTEND_REGISTERED] is True


async def test_register_frontend_falls_back_for_yaml_resources(
    hass: HomeAssistant,
) -> None:
    """YAML-mode installations retain zero-configuration module loading."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with (
        patch(
            "custom_components.adjustable_bed.frontend._gather",
            return_value=(True, "3.3.0", "3.3.0-abc123"),
        ),
        patch(
            "custom_components.adjustable_bed.frontend._async_register_lovelace_resource",
            new_callable=AsyncMock,
            return_value=False,
        ) as register_resource,
        patch(
            "custom_components.adjustable_bed.frontend.add_extra_js_url"
        ) as add_extra_js_url,
    ):
        await async_register_frontend(hass)
        await async_register_frontend(hass)

    add_extra_js_url.assert_called_once_with(
        hass,
        f"{URL_BASE}/adjustable-bed-card.js?v=3.3.0-abc123",
    )
    register_resource.assert_awaited_once()
    hass.http.async_register_static_paths.assert_awaited_once()
    assert hass.data[DOMAIN][DATA_FRONTEND_REGISTERED] is True
