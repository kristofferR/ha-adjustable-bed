"""Support-bundle bearer grant lifetime, retries, and filesystem isolation."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed import download
from custom_components.adjustable_bed.const import DOMAIN


@pytest.fixture
def bundle(hass: HomeAssistant, tmp_path: Path):
    hass.data[DOMAIN] = {}
    path = tmp_path / "adjustable_bed_support_bundle_ab12_20260920_120000.json"
    path.write_bytes(b'{"test": true}')
    token = download.register_download(hass, path).rsplit("/", 1)[1]
    request = MagicMock(app={"hass": hass})
    return path, token, request


async def test_repeated_and_concurrent_downloads_work_off_loop(bundle):
    path, token, request = bundle
    main_thread = threading.get_ident()
    read_threads = []
    original = download._read_bundle

    def read(filepath):
        read_threads.append(threading.get_ident())
        return original(filepath)

    with patch.object(download, "_read_bundle", new=read):
        responses = await asyncio.gather(
            *(download.SupportBundleDownloadView().get(request, token) for _ in range(3))
        )
    for response in responses:
        assert response.status == 200
        assert response.body == b'{"test": true}'
        assert response.headers["Cache-Control"] == "no-store"
        assert path.name in response.headers["Content-Disposition"]
    assert len(read_threads) == 3
    assert main_thread not in read_threads


async def test_expiry_is_enforced_at_deadline_and_prunes_grant(hass, bundle):
    _, token, request = bundle
    grants = hass.data[DOMAIN][download.DATA_DOWNLOAD_TOKENS]
    expiry = grants[token].expires_at
    with patch.object(download, "monotonic", return_value=expiry):
        response = await download.SupportBundleDownloadView().get(request, token)
    assert response.status == 404
    assert response.headers["Cache-Control"] == "no-store"
    assert token not in grants


@pytest.mark.parametrize("reason", ["unknown", "revoked", "missing", "invalid_name"])
async def test_unavailable_downloads_are_not_cacheable(hass, bundle, reason):
    path, token, request = bundle
    grants = hass.data[DOMAIN][download.DATA_DOWNLOAD_TOKENS]
    if reason == "unknown":
        token = "unknown"
    elif reason == "revoked":
        del grants[token]
    elif reason == "missing":
        path.unlink()
    else:
        token = download.register_download(hass, path.with_name("secrets.yaml")).rsplit("/", 1)[1]
    response = await download.SupportBundleDownloadView().get(request, token)
    assert response.status == (403 if reason == "invalid_name" else 404)
    assert response.headers["Cache-Control"] == "no-store"
    if reason == "missing":
        assert token not in grants


async def test_read_failure_does_not_consume_grant(bundle):
    _, token, request = bundle
    with patch.object(download, "_read_bundle", side_effect=OSError("temporary failure")):
        response = await download.SupportBundleDownloadView().get(request, token)
    assert response.status == 500
    assert response.headers["Cache-Control"] == "no-store"
    assert (await download.SupportBundleDownloadView().get(request, token)).status == 200


def test_registration_bounds_storage_and_prunes_expired(hass, bundle):
    path, first_token, _ = bundle
    grants = hass.data[DOMAIN][download.DATA_DOWNLOAD_TOKENS]
    for _ in range(download.MAX_DOWNLOAD_TOKENS):
        download.register_download(hass, path)
    assert len(grants) == download.MAX_DOWNLOAD_TOKENS
    assert first_token not in grants
    expiry = max(grant.expires_at for grant in grants.values())
    with patch.object(download, "monotonic", return_value=expiry):
        last_token = download.register_download(hass, path).rsplit("/", 1)[1]
    assert list(grants) == [last_token]
