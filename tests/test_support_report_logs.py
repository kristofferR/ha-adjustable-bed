"""Tests for support-report recent-log capture (reads home-assistant.log)."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.support_report import (
    MAX_LOG_ENTRIES,
    _get_recent_logs,
    _read_log_file,
    _tail_text,
)

# A standard HA log line: "<ts> <LEVEL> (<thread>) [<logger>] <message>"
_RELEVANT = (
    "2026-06-24 13:26:56.557 DEBUG (MainThread) "
    "[custom_components.adjustable_bed.coordinator] Sending head up\n"
)
_BLUETOOTH = (
    "2026-06-24 13:26:56.600 INFO (MainThread) "
    "[homeassistant.components.bluetooth] Adapter ready\n"
)
_BLEAK_WITH_TRACEBACK = (
    "2026-06-24 13:26:57.000 ERROR (MainThread) [bleak.backends.device] boom\n"
    "Traceback (most recent call last):\n"
    '  File "x.py", line 1, in <module>\n'
    "ValueError: nope\n"
)
_IRRELEVANT = (
    "2026-06-24 13:26:56.700 WARNING (MainThread) "
    "[homeassistant.components.light] Unrelated entry\n"
    "2026-06-24 13:26:57.500 DEBUG (MainThread) "
    "[custom_components.other] also unrelated\n"
)


def _write_log(tmp_path: Path, content: str) -> str:
    log = tmp_path / "home-assistant.log"
    log.write_text(content, encoding="utf-8")
    return str(log)


def test_read_log_file_filters_and_parses(tmp_path: Path) -> None:
    """Only bed/Bluetooth/bleak loggers are kept, with fields parsed out."""
    path = _write_log(
        tmp_path, _RELEVANT + _BLUETOOTH + _IRRELEVANT + _BLEAK_WITH_TRACEBACK
    )

    entries = _read_log_file(path)

    names = [e["name"] for e in entries]
    assert names == [
        "custom_components.adjustable_bed.coordinator",
        "homeassistant.components.bluetooth",
        "bleak.backends.device",
    ]
    assert all("light" not in n and "other" not in n for n in names)

    coordinator = entries[0]
    assert coordinator["level"] == "DEBUG"
    assert coordinator["timestamp"] == "2026-06-24 13:26:56.557"
    assert coordinator["message"] == "Sending head up"


def test_read_log_file_joins_continuation_lines(tmp_path: Path) -> None:
    """Traceback bodies are appended to the relevant entry they follow."""
    path = _write_log(tmp_path, _BLEAK_WITH_TRACEBACK)

    entries = _read_log_file(path)

    assert len(entries) == 1
    message = entries[0]["message"]
    assert message.startswith("boom")
    assert "Traceback (most recent call last):" in message
    assert "ValueError: nope" in message


def test_read_log_file_drops_orphan_continuation(tmp_path: Path) -> None:
    """A continuation line after an *irrelevant* entry is not captured."""
    path = _write_log(
        tmp_path,
        "2026-06-24 13:26:56.700 ERROR (MainThread) "
        "[homeassistant.components.light] boom\n"
        "Traceback (most recent call last):\n"
        "ValueError: nope\n",
    )

    assert _read_log_file(path) == []


def test_read_log_file_caps_at_max_entries(tmp_path: Path) -> None:
    """Only the most recent MAX_LOG_ENTRIES relevant lines are returned."""
    lines = "".join(
        f"2026-06-24 13:26:{i % 60:02d}.000 DEBUG (MainThread) "
        f"[custom_components.adjustable_bed.coordinator] line {i}\n"
        for i in range(MAX_LOG_ENTRIES + 50)
    )
    path = _write_log(tmp_path, lines)

    entries = _read_log_file(path)

    assert len(entries) == MAX_LOG_ENTRIES
    # The tail is kept, so the last line must be present and the first dropped.
    assert entries[-1]["message"] == f"line {MAX_LOG_ENTRIES + 49}"
    assert entries[0]["message"] == "line 50"


def test_read_log_file_missing_file_returns_notice() -> None:
    """A missing/unreadable log file yields a single explanatory entry."""
    entries = _read_log_file("/nonexistent/path/home-assistant.log")

    assert len(entries) == 1
    assert entries[0]["level"] == "INFO"
    assert "Could not read" in entries[0]["message"]


def test_tail_text_drops_partial_first_line(tmp_path: Path) -> None:
    """When truncating mid-file, the partial leading line is discarded."""
    path = _write_log(tmp_path, "FIRST line aaaaaaaaaa\nSECOND\nTHIRD\n")

    # max_bytes small enough to seek into the middle of the first line.
    tail = _tail_text(path, max_bytes=12)

    assert "FIRST" not in tail
    assert "THIRD" in tail


async def test_get_recent_logs_reads_ha_log(hass: HomeAssistant) -> None:
    """_get_recent_logs reads the configured home-assistant.log path."""
    log_path = Path(hass.config.path("home-assistant.log"))
    log_path.write_text(_RELEVANT + _IRRELEVANT, encoding="utf-8")

    entries = await _get_recent_logs(hass)

    assert len(entries) == 1
    assert entries[0]["name"] == "custom_components.adjustable_bed.coordinator"
    assert entries[0]["message"] == "Sending head up"
