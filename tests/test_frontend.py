"""Tests for the bundled Adjustable Bed Lovelace card registration."""

from __future__ import annotations

import json
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
from homeassistant.const import (
    CONF_ID,
    CONF_TYPE,
    CONF_URL,
    EVENT_COMPONENT_LOADED,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant.typing import ClientSessionGenerator

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.frontend import (
    CARD_FILENAME,
    CARD_URL,
    DATA_FRONTEND_REGISTERED,
    URL_BASE,
    _async_register_lovelace_resource,
    _card_url,
    _gather,
    async_register_frontend,
)


def _storage_resources(items: list[dict[str, str]]) -> MagicMock:
    """Return a storage resource collection mock with the given items."""
    resources = MagicMock(spec=ResourceStorageCollection)
    resources.async_get_info = AsyncMock(return_value={"resources": len(items)})
    resources.async_items.return_value = items
    resources.async_create_item = AsyncMock()
    resources.async_delete_item = AsyncMock()
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


def test_card_url_embeds_cache_key_in_path() -> None:
    """Bundle identity does not depend on cache-sensitive query parameters."""
    assert _card_url("3.5.0-abc123") == (
        f"{URL_BASE}/3.5.0-abc123/{CARD_FILENAME}"
    )


async def test_register_lovelace_resource_creates_missing_resource(
    hass: HomeAssistant,
) -> None:
    """The card is persisted so Lovelace can load it independently."""
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})
    card_url = _card_url("3.5.0-abc123")

    assert await _async_register_lovelace_resource(hass, card_url)

    assert [
        {CONF_TYPE: item[CONF_TYPE], CONF_URL: item[CONF_URL]}
        for item in resources.async_items()
    ] == [{CONF_TYPE: "module", CONF_URL: card_url}]


async def test_register_lovelace_resource_updates_stale_resource(
    hass: HomeAssistant,
) -> None:
    """Lazy-loaded storage migrates the query-based card resource."""
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
    card_url = _card_url("3.5.0-def456")

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
    card_url = _card_url("3.5.0-abc123")
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
    resources.async_delete_item.assert_not_awaited()
    resources.async_update_item.assert_not_awaited()


async def test_register_lovelace_resource_removes_duplicate_card_resources(
    hass: HomeAssistant,
) -> None:
    """Only one integration-owned card resource survives reconciliation."""
    card_url = _card_url("3.5.0-abc123")
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    await resources.store.async_save(
        {
            "items": [
                {
                    CONF_ID: "legacy-resource",
                    CONF_TYPE: "module",
                    CONF_URL: f"{CARD_URL}?v=3.4.0-old",
                },
                {
                    CONF_ID: "current-resource",
                    CONF_TYPE: "module",
                    CONF_URL: card_url,
                },
            ]
        }
    )
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})

    assert await _async_register_lovelace_resource(hass, card_url)

    assert resources.async_items() == [
        {
            CONF_ID: "current-resource",
            CONF_TYPE: "module",
            CONF_URL: card_url,
        }
    ]


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
        _card_url("3.5.0-abc123"),
    )


async def test_register_frontend_uses_resource_and_module_hook(
    hass: HomeAssistant,
) -> None:
    """Storage mode is durable while retaining early frontend module loading."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.update({"frontend", "lovelace"})

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
        await hass.async_block_till_done()

    card_url = _card_url("3.3.0-abc123")
    register_resource.assert_awaited_once_with(hass, CARD_URL)
    add_extra_js_url.assert_called_once_with(hass, CARD_URL)
    static_paths = hass.http.async_register_static_paths.await_args.args[0]
    assert [(item.url_path, item.cache_headers) for item in static_paths] == [
        (card_url, True),
    ]
    hass.http.register_view.assert_called_once()
    assert hass.data[DOMAIN][DATA_FRONTEND_REGISTERED] is True


async def test_register_frontend_falls_back_for_yaml_resources(
    hass: HomeAssistant,
) -> None:
    """YAML-mode installations retain zero-configuration module loading."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    hass.config.components.update({"frontend", "lovelace"})

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
        await hass.async_block_till_done()

    add_extra_js_url.assert_called_once_with(
        hass,
        CARD_URL,
    )
    register_resource.assert_awaited_once()
    hass.http.async_register_static_paths.assert_awaited_once()
    assert hass.data[DOMAIN][DATA_FRONTEND_REGISTERED] is True


async def test_register_frontend_waits_for_late_dependencies(
    hass: HomeAssistant,
) -> None:
    """A setup-order miss recovers when frontend and Lovelace become ready."""
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

        register_resource.assert_not_awaited()
        add_extra_js_url.assert_not_called()

        hass.config.components.add("frontend")
        hass.bus.async_fire_internal(
            EVENT_COMPONENT_LOADED,
            {"component": "frontend"},
        )
        await hass.async_block_till_done()
        add_extra_js_url.assert_called_once_with(
            hass,
            CARD_URL,
        )

        hass.config.components.add("lovelace")
        hass.bus.async_fire_internal(
            EVENT_COMPONENT_LOADED,
            {"component": "lovelace"},
        )
        await hass.async_block_till_done()
        register_resource.assert_awaited_once_with(
            hass,
            CARD_URL,
        )


@pytest.mark.parametrize("cache_key", ["3.7.1-old", "4.0.0-new"])
async def test_card_loader_serves_current_bundle_through_http(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    tmp_path: Path,
    cache_key: str,
) -> None:
    """Cold clients and saved old URLs load the bundle without authentication."""
    card = tmp_path / CARD_FILENAME
    bundle = b'customElements.define("test-bed-card", class extends HTMLElement {});'
    card.write_bytes(bundle)
    assert await async_setup_component(hass, "http", {})

    with (
        patch("custom_components.adjustable_bed.frontend._dist_dir", return_value=tmp_path),
        patch(
            "custom_components.adjustable_bed.frontend._gather",
            return_value=(True, "test", cache_key),
        ),
    ):
        await async_register_frontend(hass)

    client = await hass_client_no_auth()
    current_url = _card_url(cache_key)
    for url in (CARD_URL, f"{CARD_URL}?v=3.2.1", _card_url("3.6.0-stale")):
        response = await client.get(url)
        assert response.status == 200
        assert response.content_type == "text/javascript"
        assert response.headers["Cache-Control"] == "no-store"
        assert await response.text() == f"import {json.dumps(current_url)};\n"

    # The exact current route must win over the loader's version-path fallback.
    response = await client.get(current_url)
    assert response.status == 200
    assert response.content_type == "text/javascript"
    assert "max-age=" in response.headers["Cache-Control"]
    assert await response.read() == bundle

    # The fallback serves only the loader, never arbitrary integration files.
    assert (await client.get(f"{URL_BASE}/manifest.json")).status == 404
    assert (await client.get(f"{URL_BASE}/old/manifest.json")).status == 404


async def test_resource_migration_preserves_permanent_workaround(
    hass: HomeAssistant,
) -> None:
    """Restart keeps the working permanent URL and removes only old aliases."""
    resources = ResourceStorageCollection(hass, LovelaceStorage(hass, None))
    permanent = {CONF_ID: "manual", CONF_TYPE: "module", CONF_URL: CARD_URL}
    await resources.store.async_save(
        {
            "items": [
                {
                    CONF_ID: "previous-auto-resource",
                    CONF_TYPE: "module",
                    CONF_URL: _card_url("3.7.1-previous"),
                },
                permanent,
            ]
        }
    )
    hass.data[LOVELACE_DATA] = LovelaceData("storage", {}, resources, {})

    assert await _async_register_lovelace_resource(hass, CARD_URL)
    assert resources.async_items() == [permanent]
