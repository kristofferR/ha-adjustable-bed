"""HTTP download view for support bundle files."""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from aiohttp import web
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN

# Storage key for download tokens within hass.data[DOMAIN]
DATA_DOWNLOAD_TOKENS = "download_tokens"
DOWNLOAD_TOKEN_TTL = 60 * 60
MAX_DOWNLOAD_TOKENS = 32
_NO_STORE = {"Cache-Control": "no-store"}
_LOGGER = logging.getLogger(__name__)

# Only serve files matching this pattern (prevents path traversal)
_BUNDLE_FILENAME_RE = re.compile(
    r"^adjustable_bed_support_(bundle|report)_[0-9a-f]+_\d{8}_\d{6}\.json$"
)


@dataclass(frozen=True, slots=True)
class DownloadGrant:
    """A reusable download permission with a bounded lifetime."""

    path: Path
    expires_at: float


def _prune_expired(tokens: dict[str, DownloadGrant]) -> None:
    now = monotonic()
    for token, grant in list(tokens.items()):
        if grant.expires_at <= now:
            del tokens[token]


def _read_bundle(filepath: Path) -> bytes:
    """Perform all filesystem access in the executor."""
    if not filepath.is_file():
        raise FileNotFoundError
    return filepath.read_bytes()


class SupportBundleDownloadView(HomeAssistantView):
    """Serve support bundles using reusable, one-hour bearer grants."""

    url = "/api/adjustable_bed/download/{token}"
    name = "api:adjustable_bed:download"
    requires_auth = False  # Token-based auth

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Handle download request."""
        hass: HomeAssistant = request.app["hass"]
        tokens: dict[str, DownloadGrant] = hass.data.get(DOMAIN, {}).get(
            DATA_DOWNLOAD_TOKENS, {}
        )

        _prune_expired(tokens)
        grant = tokens.get(token)
        if grant is None:
            return web.Response(status=404, text="File not found or link expired", headers=_NO_STORE)

        filepath = grant.path
        filename = filepath.name
        if not _BUNDLE_FILENAME_RE.match(filename):
            return web.Response(status=403, text="Invalid file", headers=_NO_STORE)

        try:
            data = await hass.async_add_executor_job(_read_bundle, filepath)
        except FileNotFoundError:
            tokens.pop(token, None)
            return web.Response(status=404, text="File not found or link expired", headers=_NO_STORE)
        except OSError:
            _LOGGER.warning("Could not read a support bundle for download")
            return web.Response(status=500, text="Could not read file; try again", headers=_NO_STORE)
        return web.Response(
            body=data,
            content_type="application/json",
            headers={
                **_NO_STORE,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


@callback
def register_download(hass: HomeAssistant, filepath: Path) -> str:
    """Register a reusable one-hour download, retaining at most 32 grants."""
    token = secrets.token_urlsafe(32)
    tokens: dict[str, DownloadGrant] = hass.data[DOMAIN].setdefault(DATA_DOWNLOAD_TOKENS, {})
    _prune_expired(tokens)
    while len(tokens) >= MAX_DOWNLOAD_TOKENS:
        del tokens[next(iter(tokens))]
    tokens[token] = DownloadGrant(filepath, monotonic() + DOWNLOAD_TOKEN_TTL)
    return f"/api/adjustable_bed/download/{token}"
