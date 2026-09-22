"""Capture proxy-side Bluetooth logs through a temporary ESPHome API connection."""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.const import (
    CONF_SOURCE_CONFIG_ENTRY_ID,
    CONF_SOURCE_DOMAIN,
)
from homeassistant.const import CONF_PASSWORD, CONF_SOURCE
from homeassistant.core import HomeAssistant

from .support_logs import MAX_LOG_ENTRIES, sanitize_log_message

if TYPE_CHECKING:
    from aioesphomeapi.api_pb2 import SubscribeLogsResponse  # type: ignore[attr-defined]
    from aioesphomeapi.client import APIClient

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_BLUETOOTH_LOG = re.compile(r"(?i)bluetooth|\bble\b|ble_|\bbt_|\bgatt|\bgap|\bbond|\bsmp\b")


@asynccontextmanager
async def capture_proxy_logs(
    hass: HomeAssistant, address: str, preferred_source: str | None = None
) -> AsyncIterator[list[dict[str, Any]]]:
    """Best-effort capture from proxies that see this bed, without altering HA's API stream."""
    reports: list[dict[str, Any]] = []
    clients: list[APIClient] = []
    closing = False

    async def start(source: str, entry_id: str) -> None:
        row: dict[str, Any] = {
            "source": source, "config_entry_id": entry_id,
            "status": "unavailable", "entries": [],
            "requested_level": "DEBUG",
            "note": "Only Bluetooth-related messages are retained. Firmware log levels may limit output.",
        }
        reports.append(row)
        entries: deque[dict[str, str]] = deque(maxlen=MAX_LOG_ENTRIES)
        row["dropped_entries"] = 0

        def on_log(message: SubscribeLogsResponse) -> None:
            text = _ANSI.sub("", message.message.decode("utf-8", "backslashreplace"))
            if not _BLUETOOTH_LOG.search(text):
                return
            if len(entries) == MAX_LOG_ENTRIES:
                row["dropped_entries"] += 1
            entries.append({
                "timestamp": datetime.now(UTC).isoformat(),
                "level": str(message.level),
                "message": sanitize_log_message(text),
            })
            row["entries"] = list(entries)
            if row["status"] == "empty":
                row["status"] = "available"

        async def on_stop(_expected: bool) -> None:
            if not closing:
                row["status"] = "disconnected"

        try:
            # ESPHome is optional; import its client only for a registered proxy.
            from aioesphomeapi.client import APIClient
            from aioesphomeapi.model import LogLevel

            entry = hass.config_entries.async_get_entry(entry_id)
            runtime = getattr(entry, "runtime_data", None)
            existing = getattr(runtime, "client", None)
            if entry is None or existing is None or not existing.connected_address:
                row["reason"] = "proxy_not_connected"
                return
            client = APIClient(
                existing.connected_address,
                existing.port,
                entry.data.get(CONF_PASSWORD, ""),
                noise_psk=existing.noise_psk,
                client_info="Adjustable Bed support capture",
            )
            clients.append(client)
            async with asyncio.timeout(5):
                await client.connect(on_stop=on_stop, login=True, log_errors=False)
            row["status"] = "empty"
            client.subscribe_logs(on_log, LogLevel.LOG_LEVEL_DEBUG, dump_config=False)
        except Exception as err:  # noqa: BLE001 - proxy logging must not prevent BLE diagnostics
            row["status"] = "unavailable"
            # Do not serialize exceptions that might contain API credentials.
            row["reason"] = type(err).__name__

    try:
        sources = {preferred_source} if preferred_source else set()
        try:
            for connectable in (True, False):
                sources.update(
                    device.scanner.source
                    for device in bluetooth.async_scanner_devices_by_address(
                        hass, address, connectable=connectable
                    )
                )
            registrations = {
                str(entry.data[CONF_SOURCE]): str(entry.data[CONF_SOURCE_CONFIG_ENTRY_ID])
                for entry in hass.config_entries.async_entries("bluetooth")
                if entry.data.get(CONF_SOURCE_DOMAIN) == "esphome"
                and entry.data.get(CONF_SOURCE) in sources
                and entry.data.get(CONF_SOURCE_CONFIG_ENTRY_ID)
            }
            await asyncio.gather(*(start(source, entry_id) for source, entry_id in registrations.items()))
        except Exception as err:  # noqa: BLE001
            reports.append({"status": "unavailable", "reason": type(err).__name__, "entries": []})
        yield reports
    finally:
        closing = True
        # Force-close only these temporary sockets, including partially connected
        # clients after a timeout or cancellation. HA's control client is untouched.
        await asyncio.gather(*(client.disconnect(force=True) for client in clients), return_exceptions=True)
