"""HTTP download view for support bundle files."""

from __future__ import annotations

import re
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

# Storage key for download tokens within hass.data[DOMAIN]
DATA_DOWNLOAD_TOKENS = "download_tokens"

# Only serve files matching this pattern (prevents path traversal)
_BUNDLE_FILENAME_RE = re.compile(
    r"^adjustable_bed_support_(bundle|report)_[0-9a-f]+_\d{8}_\d{6}\.json$"
)


class SupportBundleDownloadView(HomeAssistantView):
    """Serve support bundle files for download via one-time tokens."""

    url = "/api/adjustable_bed/download/{token}"
    name = "api:adjustable_bed:download"
    requires_auth = False  # Token-based auth

    async def get(self, request: web.Request, token: str) -> web.Response:
        """Handle download request."""
        hass: HomeAssistant = request.app["hass"]
        tokens: dict[str, Path] = hass.data.get(DOMAIN, {}).get(
            DATA_DOWNLOAD_TOKENS, {}
        )

        filepath = tokens.get(token)
        if filepath is None or not filepath.is_file():
            return web.Response(status=404, text="File not found or link expired")

        filename = filepath.name
        if not _BUNDLE_FILENAME_RE.match(filename):
            return web.Response(status=403, text="Invalid file")

        data = await hass.async_add_executor_job(filepath.read_bytes)
        return web.Response(
            body=data,
            content_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )


@callback
def register_download(hass: HomeAssistant, filepath: Path) -> str:
    """Register a file for download and return the download URL path."""
    import secrets

    token = secrets.token_urlsafe(32)
    tokens: dict[str, Path] = hass.data[DOMAIN].setdefault(DATA_DOWNLOAD_TOKENS, {})
    tokens[token] = filepath
    return f"/api/adjustable_bed/download/{token}"
