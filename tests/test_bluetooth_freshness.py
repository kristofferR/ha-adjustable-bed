"""Tests for the fresh-advertisement gate (issue #458)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import async_fire_time_changed

from custom_components.adjustable_bed.bluetooth_freshness import (
    MAX_ADVERTISEMENT_AGE_SECONDS,
    RSSI_INVALIDATED,
    FreshnessStatus,
    async_check_advertisement,
    async_gate_connection,
    async_wait_for_advertisement,
)

TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"

_FRESHNESS = "custom_components.adjustable_bed.bluetooth_freshness"

# A fixed "now" keeps the age arithmetic exact instead of racing the clock.
NOW = 10_000.0


@pytest.fixture(autouse=True)
def _frozen_clock():
    """Freeze the coarse monotonic clock the gate compares against."""
    with patch(f"{_FRESHNESS}._monotonic", return_value=NOW):
        yield


@pytest.fixture(autouse=True)
def _no_path_lookup():
    """Transport labelling is covered by its own tests."""
    with patch(f"{_FRESHNESS}.async_path_for_source", return_value=None):
        yield


def _service_info(*, age: float | None, rssi: int | None = -60, source: str = "hci0") -> Any:
    """Build a stand-in advertisement snapshot with a chosen age."""
    return SimpleNamespace(
        source=source,
        rssi=rssi,
        time=None if age is None else NOW - age,
        address=TEST_ADDRESS,
    )


def _patch_last_service_info(service_info: Any):
    return patch(
        f"{_FRESHNESS}.bluetooth.async_last_service_info",
        return_value=service_info,
    )


class TestFreshnessStatus:
    """The gate must only pass evidence it can actually stand behind."""

    async def test_recent_advertisement_is_fresh(self, hass: HomeAssistant) -> None:
        with _patch_last_service_info(_service_info(age=2.0)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.is_fresh
        assert evidence.age_seconds == pytest.approx(2.0)

    async def test_expired_advertisement_is_stale(self, hass: HomeAssistant) -> None:
        with _patch_last_service_info(
            _service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 1)
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.STALE
        assert not evidence.is_fresh

    async def test_fresh_non_connectable_view_wins_over_stale_connectable_history(
        self, hass: HomeAssistant
    ) -> None:
        """A stale strict snapshot must not hide a proxy's current fallback view."""

        def lookup(
            _hass: HomeAssistant, _address: str, *, connectable: bool
        ) -> Any:
            return _service_info(
                age=1.0 if not connectable else MAX_ADVERTISEMENT_AGE_SECONDS + 1,
                source="proxy",
            )

        with patch(
            f"{_FRESHNESS}.bluetooth.async_last_service_info",
            side_effect=lookup,
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)

        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.source == "proxy"
        assert evidence.age_seconds == pytest.approx(1.0)

    async def test_advertisement_exactly_at_the_limit_still_passes(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_last_service_info(_service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.FRESH

    async def test_required_newer_advertisement_rejects_cached_history(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_last_service_info(_service_info(age=1.0)):
            evidence = async_check_advertisement(
                hass,
                TEST_ADDRESS,
                seen_after=NOW,
            )
        assert evidence.status is FreshnessStatus.BEFORE_REQUIRED_TIME
        assert not evidence.is_fresh

    async def test_missing_history_is_missing(self, hass: HomeAssistant) -> None:
        with _patch_last_service_info(None):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.MISSING

    async def test_invalidated_rssi_blocks_even_when_recent(
        self, hass: HomeAssistant
    ) -> None:
        """BlueZ publishes -127 when it has no reading; that is not a weak signal."""
        with _patch_last_service_info(_service_info(age=1.0, rssi=RSSI_INVALIDATED)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.RSSI_INVALID
        assert evidence.rssi == RSSI_INVALIDATED

    async def test_rssi_below_the_invalidation_value_also_blocks(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_last_service_info(_service_info(age=1.0, rssi=-130)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.RSSI_INVALID

    async def test_a_weak_but_valid_signal_passes(self, hass: HomeAssistant) -> None:
        with _patch_last_service_info(_service_info(age=1.0, rssi=-126)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.FRESH

    async def test_missing_rssi_does_not_block_a_recent_advertisement(
        self, hass: HomeAssistant
    ) -> None:
        with _patch_last_service_info(_service_info(age=1.0, rssi=None)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.rssi is None

    @pytest.mark.parametrize(
        "bad_time", [None, "not-a-number", object(), float("nan"), float("inf")]
    )
    async def test_malformed_timestamp_is_unproven(
        self, hass: HomeAssistant, bad_time: Any
    ) -> None:
        """Without a usable timestamp we cannot claim freshness, so we do not."""
        info = _service_info(age=1.0)
        info.time = bad_time
        with _patch_last_service_info(info):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.INVALID_TIMESTAMP
        assert not evidence.is_fresh

    async def test_future_timestamp_is_unproven(self, hass: HomeAssistant) -> None:
        """A timestamp from a different clock is not evidence of a fresh sighting."""
        with _patch_last_service_info(_service_info(age=-30.0)):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.INVALID_TIMESTAMP

    async def test_history_lookup_failure_is_treated_as_missing(
        self, hass: HomeAssistant
    ) -> None:
        with patch(
            f"{_FRESHNESS}.bluetooth.async_last_service_info",
            side_effect=RuntimeError("no manager"),
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)
        assert evidence.status is FreshnessStatus.MISSING


class TestPerScannerFreshness:
    """A chosen adapter's own view is what decides whether it can reach the bed."""

    def _scanner_device(self, source: str, *, seen_at: float | None, rssi: int) -> Any:
        return SimpleNamespace(
            scanner=SimpleNamespace(
                source=source,
                discovered_device_timestamps=(
                    {} if seen_at is None else {TEST_ADDRESS: seen_at}
                ),
            ),
            advertisement=SimpleNamespace(rssi=rssi),
        )

    async def test_selected_scanner_view_is_used(self, hass: HomeAssistant) -> None:
        devices = [
            self._scanner_device("proxy", seen_at=NOW - 1.0, rssi=-50),
            self._scanner_device("hci0", seen_at=NOW - 5.0, rssi=-70),
        ]
        with patch(
            f"{_FRESHNESS}.bluetooth.async_scanner_devices_by_address",
            return_value=devices,
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS, source="hci0")
        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.rssi == -70
        assert evidence.age_seconds == pytest.approx(5.0)

    async def test_stale_on_the_selected_scanner_blocks_despite_another_seeing_it(
        self, hass: HomeAssistant
    ) -> None:
        """Another proxy hearing the bed says nothing about the chosen adapter."""
        devices = [
            self._scanner_device("proxy", seen_at=NOW - 1.0, rssi=-50),
            self._scanner_device(
                "hci0", seen_at=NOW - MAX_ADVERTISEMENT_AGE_SECONDS - 10, rssi=-90
            ),
        ]
        with patch(
            f"{_FRESHNESS}.bluetooth.async_scanner_devices_by_address",
            return_value=devices,
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS, source="hci0")
        assert evidence.status is FreshnessStatus.STALE

    async def test_selected_scanner_no_longer_sees_the_bed(
        self, hass: HomeAssistant
    ) -> None:
        """Distinct from MISSING: the bed is there, the chosen adapter is not."""
        devices = [self._scanner_device("proxy", seen_at=NOW - 1.0, rssi=-50)]
        with patch(
            f"{_FRESHNESS}.bluetooth.async_scanner_devices_by_address",
            return_value=devices,
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS, source="hci0")
        assert evidence.status is FreshnessStatus.SOURCE_UNAVAILABLE


class TestConflictingScannerViews:
    """One scanner saying "no signal" must not discard another's real reading."""

    def _scanner_device(self, source: str, *, seen_at: float, rssi: int) -> Any:
        return SimpleNamespace(
            scanner=SimpleNamespace(
                source=source,
                discovered_device_timestamps={TEST_ADDRESS: seen_at},
            ),
            advertisement=SimpleNamespace(rssi=rssi),
        )

    async def test_a_newer_invalidated_rssi_does_not_hide_a_valid_reading(
        self, hass: HomeAssistant
    ) -> None:
        """A -127 published a second later would otherwise block a reachable bed."""
        with patch(
            f"{_FRESHNESS}.bluetooth.async_last_service_info",
            side_effect=lambda _hass, _address, connectable=True: (
                _service_info(age=5.0, rssi=-60, source="hci0")
                if connectable
                else _service_info(age=1.0, rssi=RSSI_INVALIDATED, source="proxy")
            ),
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)

        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.rssi == -60
        assert evidence.source == "hci0"

    async def test_an_invalidated_rssi_still_wins_when_it_is_all_there_is(
        self, hass: HomeAssistant
    ) -> None:
        """Nothing can hear the bed, and that is the honest answer."""
        with patch(
            f"{_FRESHNESS}.bluetooth.async_last_service_info",
            side_effect=lambda _hass, _address, connectable=True: _service_info(
                age=1.0, rssi=RSSI_INVALIDATED
            ),
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS)

        assert evidence.status is FreshnessStatus.RSSI_INVALID

    async def test_the_selected_adapter_also_prefers_its_usable_view(
        self, hass: HomeAssistant
    ) -> None:
        """The per-scanner path compares two views of one adapter the same way."""
        devices = [self._scanner_device("hci0", seen_at=NOW - 5.0, rssi=-70)]
        invalid = [self._scanner_device("hci0", seen_at=NOW - 1.0, rssi=RSSI_INVALIDATED)]
        with patch(
            f"{_FRESHNESS}.bluetooth.async_scanner_devices_by_address",
            side_effect=lambda _hass, _address, connectable=True: (
                invalid if connectable else devices
            ),
        ):
            evidence = async_check_advertisement(hass, TEST_ADDRESS, source="hci0")

        assert evidence.status is FreshnessStatus.FRESH
        assert evidence.rssi == -70


class TestGateConnection:
    """The BLEDevice must be resolved after the gate, never before it."""

    async def test_fresh_evidence_resolves_a_current_device(
        self, hass: HomeAssistant
    ) -> None:
        device = SimpleNamespace(address=TEST_ADDRESS)
        with (
            _patch_last_service_info(_service_info(age=1.0)),
            patch(
                f"{_FRESHNESS}.async_resolve_ble_device", return_value=device
            ) as resolve,
        ):
            evidence, resolved = async_gate_connection(hass, TEST_ADDRESS)
        assert evidence.is_fresh
        assert resolved is device
        resolve.assert_called_once()

    async def test_fresh_evidence_without_a_device_is_not_reported_as_fresh(
        self, hass: HomeAssistant
    ) -> None:
        """A resolution gap is its own status, never a silent bed.

        Home Assistant's scanner view can change between the history check and
        the device lookup. Reporting that as FRESH-with-no-device leaves the
        caller to invent a reason, and the reason it used to invent was "this
        bed is not advertising" - advice that sends the user to wake a bed that
        is advertising perfectly well.
        """
        with (
            _patch_last_service_info(_service_info(age=1.0)),
            patch(f"{_FRESHNESS}.async_resolve_ble_device", return_value=None),
        ):
            evidence, resolved = async_gate_connection(hass, TEST_ADDRESS)
        assert resolved is None
        assert evidence.status is FreshnessStatus.DEVICE_UNRESOLVED
        assert not evidence.is_fresh
        assert evidence.error_key == "device_unresolved"
        # The advertising evidence itself is still carried through.
        assert evidence.age_seconds == pytest.approx(1.0)
        assert evidence.rssi == -60

    async def test_stale_evidence_never_resolves_a_device(
        self, hass: HomeAssistant
    ) -> None:
        """Nothing may reach establish_connection once the gate has refused."""
        with (
            _patch_last_service_info(
                _service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 60)
            ),
            patch(f"{_FRESHNESS}.async_resolve_ble_device") as resolve,
        ):
            evidence, resolved = async_gate_connection(hass, TEST_ADDRESS)
        assert not evidence.is_fresh
        assert resolved is None
        resolve.assert_not_called()

    async def test_missing_evidence_never_resolves_a_device(
        self, hass: HomeAssistant
    ) -> None:
        with (
            _patch_last_service_info(None),
            patch(f"{_FRESHNESS}.async_resolve_ble_device") as resolve,
        ):
            _evidence, resolved = async_gate_connection(hass, TEST_ADDRESS)
        assert resolved is None
        resolve.assert_not_called()

    async def test_a_fresh_advertisement_after_a_refusal_allows_the_next_attempt(
        self, hass: HomeAssistant
    ) -> None:
        """Retry must work without restarting the flow."""
        stale = _service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 5)
        fresh = _service_info(age=1.0)
        # Each check consults both scanner views, so two lookups per call.
        with patch(
            f"{_FRESHNESS}.bluetooth.async_last_service_info",
            side_effect=[stale, stale, fresh, fresh],
        ):
            assert not async_check_advertisement(hass, TEST_ADDRESS).is_fresh
            assert async_check_advertisement(hass, TEST_ADDRESS).is_fresh


class TestWaitForAdvertisement:
    """A bed between advertising intervals deserves a second look, not a refusal.

    The wait runs on the event loop clock, which ``freezer`` controls, so these
    tests advance time explicitly and deliver packets through the callback the
    wait registers.
    """

    @staticmethod
    @contextmanager
    def _packets() -> Iterator[dict[str, Any]]:
        """Capture the per-packet callback the wait registers."""
        registered: dict[str, Any] = {"unsubscribe": MagicMock()}

        def _register(_hass: HomeAssistant, callback: Any, address: str) -> MagicMock:
            registered["callback"], registered["address"] = callback, address
            return registered["unsubscribe"]

        with patch(
            f"{_FRESHNESS}.bluetooth.async_register_advertisement_callback",
            side_effect=_register,
        ):
            yield registered

    @staticmethod
    async def _settle() -> None:
        for _ in range(5):
            await asyncio.sleep(0)

    async def _advance(self, hass: HomeAssistant, freezer: Any, seconds: float) -> None:
        freezer.tick(timedelta(seconds=seconds))
        async_fire_time_changed(hass)
        await self._settle()

    async def test_an_already_fresh_bed_returns_without_waiting(
        self, hass: HomeAssistant
    ) -> None:
        device = SimpleNamespace(address=TEST_ADDRESS)
        with (
            self._packets() as packets,
            _patch_last_service_info(_service_info(age=1.0)) as lookup,
            patch(f"{_FRESHNESS}.async_resolve_ble_device", return_value=device),
        ):
            evidence, resolved = await async_wait_for_advertisement(hass, TEST_ADDRESS)
        assert evidence.is_fresh
        assert resolved is device
        # One glance at the history - both scanner views - and no listener.
        assert lookup.call_count == 2
        assert "callback" not in packets

    async def test_the_first_fresh_packet_ends_the_wait(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        device = SimpleNamespace(address=TEST_ADDRESS)
        history = {"info": _service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 5)}
        seen: list[float] = []
        with (
            self._packets() as packets,
            patch(
                f"{_FRESHNESS}.bluetooth.async_last_service_info",
                side_effect=lambda *_args, **_kwargs: history["info"],
            ),
            patch(f"{_FRESHNESS}.async_resolve_ble_device", return_value=device),
        ):
            task = asyncio.create_task(
                async_wait_for_advertisement(
                    hass, TEST_ADDRESS.lower(), wait_timeout=60.0, on_progress=seen.append
                )
            )
            await self._settle()
            assert packets["address"] == TEST_ADDRESS
            history["info"] = _service_info(age=0.0)
            packets["callback"](history["info"])
            await self._settle()

            assert task.done()
            evidence, resolved = task.result()
        assert evidence.is_fresh
        assert resolved is device
        # No time passed: the packet, not a later check, ended the wait.
        assert seen == [0.0, 1.0]
        packets["unsubscribe"].assert_called_once()

    async def test_fresh_evidence_without_a_device_waits_for_the_next_packet(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """Scanner history can change between freshness and device resolution."""
        device = SimpleNamespace(address=TEST_ADDRESS)
        with (
            self._packets() as packets,
            _patch_last_service_info(_service_info(age=1.0)),
            patch(
                f"{_FRESHNESS}.async_resolve_ble_device",
                side_effect=[None, None, device],
            ) as resolve,
        ):
            task = asyncio.create_task(
                async_wait_for_advertisement(hass, TEST_ADDRESS, wait_timeout=60.0)
            )
            await self._settle()
            packets["callback"](_service_info(age=0.0))
            await self._settle()
            assert not task.done()
            packets["callback"](_service_info(age=0.0))
            await self._settle()

            evidence, resolved = task.result()
        assert evidence.is_fresh
        assert resolved is device
        assert resolve.call_count == 3

    async def test_a_silent_bed_gives_up_at_the_deadline(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        with (
            self._packets() as packets,
            _patch_last_service_info(_service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 5)),
            patch(f"{_FRESHNESS}.async_resolve_ble_device") as resolve,
        ):
            task = asyncio.create_task(
                async_wait_for_advertisement(hass, TEST_ADDRESS, wait_timeout=10.0)
            )
            await self._settle()
            await self._advance(hass, freezer, 8.0)
            assert not task.done()
            await self._advance(hass, freezer, 2.0)

            evidence, resolved = task.result()
        assert evidence.status is FreshnessStatus.STALE
        assert resolved is None
        resolve.assert_not_called()
        packets["unsubscribe"].assert_called_once()

    async def test_progress_is_reported_over_the_known_wait(
        self, hass: HomeAssistant, freezer: Any
    ) -> None:
        """The wait is the only setup phase whose duration is genuinely known."""
        seen: list[float] = []
        with (
            self._packets(),
            _patch_last_service_info(_service_info(age=MAX_ADVERTISEMENT_AGE_SECONDS + 5)),
        ):
            task = asyncio.create_task(
                async_wait_for_advertisement(
                    hass, TEST_ADDRESS, wait_timeout=4.0, on_progress=seen.append
                )
            )
            await self._settle()
            for _ in range(4):
                await self._advance(hass, freezer, 1.0)
            assert task.done()
        assert seen == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])
