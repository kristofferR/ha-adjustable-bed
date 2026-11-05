"""Tests for the one-time beta feedback notification."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from awesomeversion import AwesomeVersion
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components import persistent_notification as pn
from homeassistant.const import CONF_ADDRESS, CONF_NAME, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.adjustable_bed.beta_feedback import (
    BUG_REPORT_URL,
    NOTIFICATION_ID,
    STORAGE_KEY,
    async_setup_beta_feedback,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_LINAK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_MOTOR_COUNT,
    DOMAIN,
)

FEEDBACK_ISSUE = "https://github.com/kristofferR/ha-adjustable-bed/issues/914"


@pytest.fixture
def asked(hass: HomeAssistant) -> Generator[list[pn.Notification]]:
    """Record every creation of the feedback notification, overwrites included."""
    created: list[pn.Notification] = []

    @callback
    def _record(update_type: pn.UpdateType, notifications: dict[str, pn.Notification]) -> None:
        if update_type is not pn.UpdateType.REMOVED and NOTIFICATION_ID in notifications:
            created.append(notifications[NOTIFICATION_ID])

    unsubscribe = pn.async_register_callback(hass, _record)
    yield created
    unsubscribe()


def _running(version: str) -> Any:
    """Patch the integration version Home Assistant's loader reports."""
    integration = SimpleNamespace(version=AwesomeVersion(version))
    return patch(
        "custom_components.adjustable_bed.beta_feedback.async_get_integration",
        AsyncMock(return_value=integration),
    )


async def _start(hass: HomeAssistant, version: str) -> None:
    with _running(version):
        await async_setup_beta_feedback(hass)
    await hass.async_block_till_done()


async def _stop(hass: HomeAssistant) -> None:
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _stored(hass_storage: dict[str, Any]) -> dict[str, Any]:
    return hass_storage[STORAGE_KEY]["data"]


async def test_beta_asks_once_a_day_after_install(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
) -> None:
    """The first beta load starts the clock and asks once, 24 hours later."""
    installed = dt_util.utcnow()
    await _start(hass, "5.0.0b1")
    assert _stored(hass_storage) == {"5": {"installed_at": installed.isoformat()}}

    await _advance(hass, freezer, timedelta(hours=23, minutes=59))
    assert asked == []

    await _advance(hass, freezer, timedelta(minutes=1))
    assert len(asked) == 1
    assert asked[0]["title"] == "How is the Adjustable Bed beta working?"
    assert "v5 beta" in asked[0]["message"]
    assert FEEDBACK_ISSUE in asked[0]["message"]
    assert _stored(hass_storage)["5"]["asked"] is True

    await _advance(hass, freezer, timedelta(days=3))
    assert len(asked) == 1


async def test_restart_before_the_day_keeps_the_install_time(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    asked: list[pn.Notification],
) -> None:
    """A restart re-arms the request for the stored time, not a new day."""
    await _start(hass, "5.0.0b1")
    await _advance(hass, freezer, timedelta(hours=20))
    await _stop(hass)
    await _start(hass, "5.0.0b1")

    await _advance(hass, freezer, timedelta(hours=3, minutes=59))
    assert asked == []

    await _advance(hass, freezer, timedelta(minutes=1))
    assert len(asked) == 1


async def test_restart_after_the_day_asks_on_startup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
) -> None:
    """A day that passed while Home Assistant was stopped asks once at start."""
    await _start(hass, "5.0.0b1")
    await _stop(hass)
    await _advance(hass, freezer, timedelta(days=2))
    assert asked == []

    await _start(hass, "5.0.0b1")
    # The overdue timer is due at once: run the loop's due timers without moving the clock.
    await _advance(hass, freezer, timedelta())
    assert len(asked) == 1
    assert _stored(hass_storage)["5"]["asked"] is True

    await _stop(hass)
    await _start(hass, "5.0.0b1")
    await _advance(hass, freezer, timedelta(days=2))
    assert len(asked) == 1


async def test_later_beta_of_the_same_major_never_asks_again(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
) -> None:
    """Once v5 has asked, b2 and later v5 betas stay quiet."""
    await _start(hass, "5.0.0b1")
    await _advance(hass, freezer, timedelta(hours=24))
    assert len(asked) == 1
    stored = _stored(hass_storage)

    await _stop(hass)
    await _start(hass, "5.0.0b2")
    await _advance(hass, freezer, timedelta(days=3))

    assert len(asked) == 1
    assert _stored(hass_storage) == stored


async def test_new_major_beta_asks_once_more(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
) -> None:
    """A new major's first beta starts its own day, linking the bug form without an issue."""
    await _start(hass, "5.0.0b1")
    await _advance(hass, freezer, timedelta(hours=24))
    await _stop(hass)

    await _start(hass, "6.0.0b1")
    assert _stored(hass_storage)["5"]["asked"] is True
    assert "asked" not in _stored(hass_storage)["6"]
    await _advance(hass, freezer, timedelta(hours=23))
    assert len(asked) == 1

    await _advance(hass, freezer, timedelta(hours=1))
    assert len(asked) == 2
    assert "v6 beta" in asked[1]["message"]
    assert BUG_REPORT_URL in asked[1]["message"]
    assert FEEDBACK_ISSUE not in asked[1]["message"]


@pytest.mark.parametrize("version", ["5.0.0", "4.2.1"])
async def test_stable_version_never_stores_or_asks(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
    version: str,
) -> None:
    """A stable release neither starts a clock nor asks."""
    await _start(hass, version)
    await _advance(hass, freezer, timedelta(days=3))

    assert STORAGE_KEY not in hass_storage
    assert asked == []


@pytest.mark.parametrize("stable", ["5.0.0", "4.2.1"])
async def test_switching_to_stable_before_the_day_never_asks(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
    asked: list[pn.Notification],
    stable: str,
) -> None:
    """Leaving the beta before the day is up drops the pending request."""
    await _start(hass, "5.0.0b1")
    stored = _stored(hass_storage)
    await _advance(hass, freezer, timedelta(hours=12))
    await _stop(hass)

    await _start(hass, stable)
    await _advance(hass, freezer, timedelta(days=3))

    assert asked == []
    assert _stored(hass_storage) == stored


async def test_several_entries_arm_one_request(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    asked: list[pn.Notification],
    mock_coordinator_connected: None,
    enable_custom_integrations: None,
) -> None:
    """The request is integration-wide: two beds arm one timer and ask once."""
    entries = [
        MockConfigEntry(
            domain=DOMAIN,
            title=f"Bed {index}",
            data={
                CONF_ADDRESS: f"AA:BB:CC:DD:EE:0{index}",
                CONF_NAME: f"Bed {index}",
                CONF_BED_TYPE: BED_TYPE_LINAK,
                CONF_MOTOR_COUNT: 2,
                CONF_DISABLE_ANGLE_SENSING: True,
            },
            unique_id=f"AA:BB:CC:DD:EE:0{index}",
        )
        for index in (1, 2)
    ]
    with (
        _running("5.0.0b1"),
        patch(
            "custom_components.adjustable_bed.beta_feedback.async_track_point_in_utc_time",
            wraps=async_track_point_in_utc_time,
        ) as arm,
    ):
        for entry in entries:
            entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert arm.call_count == 1
    await _advance(hass, freezer, timedelta(hours=24))
    assert len(asked) == 1
