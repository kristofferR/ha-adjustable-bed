"""Ask beta testers for feedback, and point upgraders at what changed, once each.

The first time Home Assistant loads a pre-release of major version N, its time
is stored. Twenty-four hours later a persistent notification asks for feedback.
Home Assistant keeps notifications in memory only, so major N counts as
answered once the user dismisses it; until then each start shows it again once
the day has passed. Later betas of an answered major stay quiet. The running
version only changes with a restart, and a stable version never arms the
timer, so moving to a stable release before the day is up means no request.

A stable version of major N that finds an entry migrated from an earlier major
raises one repair linking to what changed, unless a beta of major N already ran
here. It stays until the user ignores it and is never raised again.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Final, TypedDict

from awesomeversion import AwesomeVersion
from homeassistant.components import persistent_notification
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import CONF_PROFILE_MIGRATION, DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = f"{DOMAIN}.beta_feedback"
NOTIFICATION_ID: Final = f"{DOMAIN}_beta_feedback"
UPGRADE_ISSUE_ID: Final = "upgraded"
FEEDBACK_DELAY: Final = timedelta(hours=24)

# The pinned feedback issue of each major version's betas.
FEEDBACK_ISSUES: Final[dict[int, str]] = {
    5: "https://github.com/kristofferR/ha-adjustable-bed/issues/914",
}
REPOSITORY: Final = "https://github.com/kristofferR/ha-adjustable-bed"
# What each major version changes for users upgrading from the one before.
BREAKING_CHANGES: Final[dict[int, str]] = {5: "docs/V5_BREAKING_CHANGES.md"}
BUG_REPORT_URL: Final = (
    "https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml"
)


class _MajorRecord(TypedDict, total=False):
    """What is stored for one major version, keyed by its number."""

    installed_at: str
    dismissed: bool
    upgrade_notice: bool


def is_prerelease(version: AwesomeVersion) -> bool:
    """Return whether a version is an alpha, beta, release candidate or dev build."""
    return bool(version.alpha or version.beta or version.release_candidate or version.dev)


def breaking_changes_url(version: AwesomeVersion) -> str | None:
    """Return what this version's major changed, as released with this version."""
    page = BREAKING_CHANGES.get(version.section(0))
    return f"{REPOSITORY}/blob/v{version}/{page}" if page else None


def feedback_message(version: AwesomeVersion) -> str:
    """Return the notification body for one major version's beta."""
    major = version.section(0)
    url = FEEDBACK_ISSUES.get(major, BUG_REPORT_URL)
    changes = breaking_changes_url(version)
    return (
        f"Thanks for trying the Adjustable Bed v{major} beta! Please tell us what works "
        "with your bed and what does not. Even a quick \"it works\" helps, since most "
        "beds cannot be tested by the maintainer.\n\n"
        f"[Share your feedback on GitHub]({url})\n\n"
        + (f"[See what changed in v{major}]({changes}) before you report a change "
           "as a bug.\n\n" if changes else "")
        + "If something is broken, attach a support bundle from the "
        "`adjustable_bed.generate_support_bundle` action."
    )


async def async_setup_beta_feedback(hass: HomeAssistant) -> None:
    """Arm the one-time feedback request while a beta is running."""
    version = (await async_get_integration(hass, DOMAIN)).version
    if version is None or not is_prerelease(version):
        return
    major = version.section(0)
    key = str(major)

    store: Store[dict[str, _MajorRecord]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    loaded = await store.async_load()
    data = loaded if isinstance(loaded, dict) else {}
    record = data.get(key)
    if not isinstance(record, dict):
        record = _MajorRecord()
    if record.get("dismissed"):
        return

    stored_at = record.get("installed_at")
    installed_at = dt_util.parse_datetime(stored_at) if isinstance(stored_at, str) else None
    if installed_at is None:
        installed_at = dt_util.utcnow()
        record = _MajorRecord(installed_at=installed_at.isoformat())
        await store.async_save({**data, key: record})

    dismissed: _MajorRecord = {**record, "dismissed": True}

    @callback
    def _async_on_update(
        update_type: persistent_notification.UpdateType,
        notifications: dict[str, persistent_notification.Notification],
    ) -> None:
        # Only this module creates the notification id, and only once per run, so
        # its removal is the dismissal. The stop listener unsubscribes.
        if (
            update_type is persistent_notification.UpdateType.REMOVED
            and NOTIFICATION_ID in notifications
        ):
            hass.async_create_task(
                store.async_save({**data, key: dismissed}), "adjustable_bed beta feedback dismissed"
            )

    @callback
    def _async_ask(_now: datetime) -> None:
        persistent_notification.async_create(
            hass,
            feedback_message(version),
            title="How is the Adjustable Bed beta working?",
            notification_id=NOTIFICATION_ID,
        )

    due = installed_at + FEEDBACK_DELAY
    _LOGGER.debug("Asking for v%s beta feedback at %s", major, due)
    unsubscribe = persistent_notification.async_register_callback(hass, _async_on_update)
    cancel = async_track_point_in_utc_time(hass, _async_ask, due)

    @callback
    def _async_stop(_event: Event) -> None:
        cancel()
        unsubscribe()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)


async def async_setup_upgrade_notice(hass: HomeAssistant) -> None:
    """Once entries have migrated, raise the what-changed repair if it is due."""
    version = (await async_get_integration(hass, DOMAIN)).version
    if version is None or is_prerelease(version) or (url := breaking_changes_url(version)) is None:
        return
    major = version.section(0)
    key = str(major)

    async def notify(_hass: HomeAssistant) -> None:
        store: Store[dict[str, _MajorRecord]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        loaded = await store.async_load()
        data = loaded if isinstance(loaded, dict) else {}
        # A beta of this major already pointed here, or this repair was raised.
        if key in data or not any(
            _migrated_from_before(entry.data, major)
            for entry in hass.config_entries.async_entries(DOMAIN)
        ):
            return
        ir.async_create_issue(
            hass,
            DOMAIN,
            UPGRADE_ISSUE_ID,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=url,
            translation_key=UPGRADE_ISSUE_ID,
            translation_placeholders={"version": key},
        )
        # Raising it again would not show it again once ignored.
        await store.async_save({**data, key: _MajorRecord(upgrade_notice=True)})

    async_at_started(hass, notify)


def _migrated_from_before(data: Mapping[str, Any], major: int) -> bool:
    """Return whether an entry was migrated from a schema before ``major``."""
    record = data.get(CONF_PROFILE_MIGRATION)
    from_version = record.get("from_version") if isinstance(record, Mapping) else None
    return isinstance(from_version, int) and from_version < major
