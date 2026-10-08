"""Durable decision exports, atomic history and selector-only snapshots."""

import asyncio
import json
from unittest.mock import patch

import pytest
from homeassistant.helpers.storage import Store

from custom_components.adjustable_bed.app_state_store import (
    AppStateStore,
    app_state_store,
    async_remove_app_states,
)
from custom_components.adjustable_bed.profile_decisions import (
    PROFILE_DECISIONS_SLOT,
    ProfileDecision,
    async_profile_decision_history,
    async_record_profile_decision,
    profile_selection,
)

ADDRESS = "AA:BB:CC:DD:EE:30"
OTHER = "AA:BB:CC:DD:EE:31"


def record(rule: str) -> ProfileDecision:
    return {
        "decided_at": "2026-10-07T00:00:00+00:00",
        "decision": "accepted",
        "source": "configure",
        "rule": rule,
        "current": "richmat",
        "suggested": "linak",
        "choices": ["linak"],
        "previous_profile": {"bed_type": "richmat", "protocol_variant": "auto"},
        "selected_profile": {"bed_type": "linak", "protocol_variant": "auto"},
        "confirmed_rules": [rule],
    }


async def test_concurrent_decisions_survive_restart_and_are_isolated_by_address(hass):
    await asyncio.gather(
        async_record_profile_decision(hass, ADDRESS, record("first"), ("first",)),
        async_record_profile_decision(hass, ADDRESS.lower(), record("second"), ("second",)),
        async_record_profile_decision(hass, OTHER, record("other_bed"), ("other_bed",)),
    )
    hass.data["adjustable_bed"]["app_state_stores"].clear()
    exported = await async_profile_decision_history(hass, ADDRESS)
    assert {event["rule"] for event in exported["history"]} == {"first", "second"}
    assert exported["legacy_dismissed_rules"] == []
    assert len((await async_profile_decision_history(hass, OTHER))["history"]) == 1
    # Redaction or a consumer changing its copy cannot rewrite stored history.
    exported["history"][0]["selected_profile"]["bed_type"] = "modified"
    assert "modified" not in json.dumps(await async_profile_decision_history(hass, ADDRESS))


async def test_unload_cannot_overwrite_a_decision_with_an_older_app_state_snapshot(hass):
    store = app_state_store(hass, ADDRESS)
    await store.async_slot("linak:auto")
    store.update("linak:auto", {"memory_name": "Latest preference"})
    write_started = asyncio.Event()
    finish_write = asyncio.Event()
    unload_started = asyncio.Event()
    snapshots = []
    save = Store.async_save

    async def held_save(storage, data):
        snapshots.append(data)
        if len(snapshots) == 1:
            write_started.set()
            await finish_write.wait()
        await save(storage, data)

    async def unload():
        unload_started.set()
        await store.async_save()

    with patch.object(Store, "async_save", new=held_save):
        decision = asyncio.create_task(
            async_record_profile_decision(hass, ADDRESS, record("first"), ("first",))
        )
        await write_started.wait()
        shutdown = asyncio.create_task(unload())
        await unload_started.wait()
        try:
            assert len(snapshots) == 1
        finally:
            finish_write.set()
            await asyncio.gather(decision, shutdown)

    restored = AppStateStore(hass, ADDRESS)
    assert await restored.async_slot("linak:auto") == {"memory_name": "Latest preference"}
    decisions = await restored.async_slot(PROFILE_DECISIONS_SLOT)
    assert decisions["first"] is True
    assert decisions["history"] == [record("first")]


@pytest.mark.parametrize("delayed_snapshot", [False, True])
async def test_deferred_history_failure_cannot_abort_unload_or_lose_retry(
    hass, mock_config_entry, delayed_snapshot
):
    from custom_components.adjustable_bed import async_unload_entry
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    address = coordinator.address
    store = app_state_store(hass, address)
    hass.data[DOMAIN][mock_config_entry.entry_id] = coordinator
    await store.async_slot("linak:auto")
    store.update("linak:auto", {"memory_name": "Latest preference"})
    with patch.object(Store, "async_save", side_effect=OSError("storage unavailable")):
        await async_record_profile_decision(
            hass, address, record("first"), ("first",), defer_on_error=True
        )
        if delayed_snapshot:
            # A background retry can take its snapshot before unload starts.
            assert store._snapshot()[PROFILE_DECISIONS_SLOT]["first"] is True
        with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
            assert await async_unload_entry(hass, mock_config_entry)
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]
    assert (await async_profile_decision_history(hass, address))["history"] == [record("first")]
    await store.async_save()
    restored = AppStateStore(hass, address)
    assert await restored.async_slot("linak:auto") == {"memory_name": "Latest preference"}
    assert (await restored.async_slot(PROFILE_DECISIONS_SLOT))["history"] == [record("first")]


async def test_legacy_boolean_dismissals_export_without_fabricating_decision_details(hass):
    await app_state_store(hass, ADDRESS).async_write(
        PROFILE_DECISIONS_SLOT,
        {
            "old_rule": True,
            "upgrade_review_old": True,
        },
    )
    assert await async_profile_decision_history(hass, ADDRESS) == {
        "history": [],
        "legacy_dismissed_rules": ["old_rule"],
    }
    await async_record_profile_decision(hass, ADDRESS, record("new_rule"), ("new_rule",))
    exported = await async_profile_decision_history(hass, ADDRESS)
    assert exported["legacy_dismissed_rules"] == ["old_rule"]
    assert exported["history"] == [record("new_rule")]


async def test_all_newly_confirmed_rules_keep_their_decision_provenance(hass):
    await app_state_store(hass, ADDRESS).async_write(
        PROFILE_DECISIONS_SLOT, {"old_rule": True}
    )
    await async_record_profile_decision(
        hass,
        ADDRESS,
        record("presented_rule"),
        ("presented_rule", "selected_rule", "upgrade_review_current"),
    )
    hass.data["adjustable_bed"]["app_state_stores"].clear()
    exported = await async_profile_decision_history(hass, ADDRESS)
    assert exported["legacy_dismissed_rules"] == ["old_rule"]
    event = exported["history"][0]
    assert event["confirmed_rules"] == [
        "presented_rule", "selected_rule", "upgrade_review_current"
    ]
    assert event["decided_at"] == record("presented_rule")["decided_at"]
    assert event["selected_profile"] == record("presented_rule")["selected_profile"]


async def test_old_history_without_confirmed_rules_exports_unchanged(hass):
    old_event = record("documented_rule")
    old_event.pop("confirmed_rules")
    await app_state_store(hass, ADDRESS).async_write(
        PROFILE_DECISIONS_SLOT,
        {"documented_rule": True, "unrecorded_rule": True, "history": [old_event]},
    )
    assert await async_profile_decision_history(hass, ADDRESS) == {
        "history": [old_event],
        "legacy_dismissed_rules": ["unrecorded_rule"],
    }


async def test_removing_and_readding_a_bed_keeps_support_history_but_clears_app_preferences(hass):
    await async_record_profile_decision(hass, ADDRESS, record("first"), ("first",))
    store = app_state_store(hass, ADDRESS)
    await store.async_write("linak:auto", {"memory_name": "Old preference"})
    await async_remove_app_states(hass, [ADDRESS])
    store.update("linak:auto", {"memory_name": "Late write after removal"})
    await store.async_save()
    assert await app_state_store(hass, ADDRESS).async_slot("linak:auto") == {}
    assert (await async_profile_decision_history(hass, ADDRESS))["history"] == [record("first")]


def test_selection_snapshot_preserves_app_and_remote_choices_without_secrets():
    assert profile_selection(
        {
            "bed_type": "richmat",
            "protocol_variant": "auto",
            "richmat_remote": "LP-QRRM",
            "vibradorm_app_profile": "vmat",
            "octo_pin": "1234",
            "jensen_pin": "1234",
            "name": "Private bedroom",
            "address": ADDRESS,
            "connection_profile": "balanced",
        }
    ) == {
        "bed_type": "richmat",
        "protocol_variant": "auto",
        "richmat_remote": "LP-QRRM",
        "vibradorm_app_profile": "vmat",
    }
