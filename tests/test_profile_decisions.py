"""Durable decision exports, atomic history and selector-only snapshots."""

import asyncio
import json

from custom_components.adjustable_bed.app_state_store import (
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
