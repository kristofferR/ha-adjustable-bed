"""Bounded in-memory evidence, including installations which log to stdout."""

from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from copy import copy
from datetime import UTC, datetime

from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.util.hass_dict import HassKey

MAX_LOG_ENTRIES = 500
MAX_PAIRING_LOG_ENTRIES = 200
MAX_PAIRING_LOG_ADDRESSES = 4
MAX_LOG_MESSAGE_LENGTH = 4096
_LOGGER_NAMES = (
    "custom_components.adjustable_bed",
    "homeassistant.components.bluetooth",
    "habluetooth",
    "bleak",
    "bleak_esphome",
    "bleak_retry_connector",
)
_SECRETS = re.compile(
    r"(?i)(\b(?:\w*_pin|pin|passkey|password|noise_psk|encryption_key|api_key|ltk|irk|csrk|"
    r"authorization|token|\w*_token|secret|\w*_secret)\b['\"]?\s*[:=]\s*)"
    r"(?:'[^']*'|\"[^\"]*\"|(?:Bearer\s+)?[^\s,;}]+)"
)
_BLE_WRITE_PAYLOAD = re.compile(
    r"(?im)(\b(?:write|writing)\s+(?:gatt\s+)?(?:characteristic|descriptor)\b"
    r"[^\r\n]*?:\s*)[^\r\n]*"
)
_FAILED_BLE_WRITE_PAYLOAD = re.compile(
    r"(?i)(\b(?:could not|failed to)\s+write\s+value\s+).+?"
    r"(\s+to\s+(?:characteristic|descriptor)\b)"
)
DATA_SUPPORT_LOGS: HassKey[SupportLogBuffer] = HassKey("adjustable_bed_support_logs")


def sanitize_log_message(message: str) -> str:
    """Keep useful connection details while removing credentials and BLE writes."""
    message = _SECRETS.sub(r"\1**REDACTED**", message)
    message = _BLE_WRITE_PAYLOAD.sub(r"\1**REDACTED**", message)
    message = _FAILED_BLE_WRITE_PAYLOAD.sub(r"\1**REDACTED**\2", message)
    return message[:MAX_LOG_MESSAGE_LENGTH]


class _SanitizedRecordForwarder(logging.Handler):
    """Forward a sanitized copy to root handlers during debug capture."""

    def emit(self, record: logging.LogRecord) -> None:
        sanitized_record = copy(record)
        sanitized_record.msg = sanitize_log_message(self.format(sanitized_record))
        sanitized_record.args = ()
        sanitized_record.exc_info = None
        sanitized_record.exc_text = None
        sanitized_record.stack_info = None
        logging.getLogger().handle(sanitized_record)


class SupportLogBuffer(logging.Handler):
    """Retain recent records without keeping LogRecords or exception objects alive."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self._entries: deque[dict[str, str]] = deque(maxlen=MAX_LOG_ENTRIES)
        self._active_pairings: dict[str, deque[dict[str, str]]] = {}
        self._pairing_counts: dict[str, int] = {}
        self._pairing_history: dict[str, tuple[list[dict[str, str]], bool]] = {}
        self._captures = 0
        self._levels: dict[logging.Logger, int] = {}
        self._propagates: dict[logging.Logger, bool] = {}
        self._forwarder = _SanitizedRecordForwarder(logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        """Copy relevant records; logging's handler lock serializes writers."""
        if not any(
            record.name == name or record.name.startswith(name + ".")
            for name in _LOGGER_NAMES
        ):
            return
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": sanitize_log_message(self.format(record)),
        }
        self._entries.append(entry)
        for address, pairing in self._active_pairings.items():
            pairing.append(entry)
            self._pairing_counts[address] += 1

    def snapshot(self) -> list[dict[str, str]]:
        """Copy records under the handler lock because workers can log too."""
        self.acquire()
        try:
            return list(self._entries)
        finally:
            self.release()

    def pairing_snapshot(self, address: str) -> tuple[list[dict[str, str]], bool]:
        """Return the latest pairing attempt, even after the general log ring wraps."""
        self.acquire()
        try:
            entries, truncated = self._pairing_history.get(address.upper(), ([], False))
            return list(entries), truncated
        finally:
            self.release()

    @contextmanager
    def capture_pairing(self, address: str) -> Iterator[None]:
        """Keep a bounded, sanitized attempt trace for the next support bundle."""
        address = address.upper()
        entries: deque[dict[str, str]] = deque(maxlen=MAX_PAIRING_LOG_ENTRIES)
        self.acquire()
        try:
            self._active_pairings[address] = entries
            self._pairing_counts[address] = 0
        finally:
            self.release()
        try:
            with self.capture_debug():
                yield
        finally:
            self.acquire()
            try:
                if self._active_pairings.get(address) is entries:
                    self._active_pairings.pop(address, None)
                    # A full ring might have dropped earlier records. Preserve
                    # that limitation instead of presenting it as complete.
                    truncated = self._pairing_counts.pop(address, 0) > MAX_PAIRING_LOG_ENTRIES
                    self._pairing_history.pop(address, None)
                    self._pairing_history[address] = (list(entries), truncated)
                    while len(self._pairing_history) > MAX_PAIRING_LOG_ADDRESSES:
                        self._pairing_history.pop(next(iter(self._pairing_history)))
            finally:
                self.release()

    @contextmanager
    def capture_debug(self) -> Iterator[None]:
        """Temporarily enable debug logs, sharing ownership across captures."""
        if self._captures == 0:
            for name in _LOGGER_NAMES:
                logger = logging.getLogger(name)
                if logger.getEffectiveLevel() > logging.DEBUG:
                    self._levels[logger] = logger.level
                    logger.setLevel(logging.DEBUG)
                self._propagates[logger] = logger.propagate
                logger.addHandler(self._forwarder)
                logger.propagate = False
        self._captures += 1
        try:
            yield
        finally:
            self._captures -= 1
            if self._captures == 0:
                for logger, level in self._levels.items():
                    if logger.level == logging.DEBUG:
                        logger.setLevel(level)
                self._levels.clear()
                for logger, propagate in self._propagates.items():
                    logger.removeHandler(self._forwarder)
                    if logger.propagate is False:
                        logger.propagate = propagate
                self._propagates.clear()


@callback
def async_setup_support_logs(hass: HomeAssistant) -> SupportLogBuffer:
    """Start once per HA instance, before bed setup can fail."""
    if DATA_SUPPORT_LOGS in hass.data:
        return hass.data[DATA_SUPPORT_LOGS]
    buffer = hass.data[DATA_SUPPORT_LOGS] = SupportLogBuffer()
    logging.getLogger().addHandler(buffer)

    @callback
    def close(_event: Event) -> None:
        logging.getLogger().removeHandler(buffer)
        buffer.close()
        hass.data.pop(DATA_SUPPORT_LOGS, None)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, close)
    return buffer
