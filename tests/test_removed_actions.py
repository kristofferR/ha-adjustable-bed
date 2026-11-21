"""A repair names the automations and scripts that call what v5 removed."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.removed_actions import (
    ISSUE_ID,
    REMOVALS,
    async_report_removed_calls,
)

AUTOMATIONS = {
    "automation": [
        {
            "id": "wake",
            "alias": "Wake up",
            "trigger": {"platform": "event", "event_type": "wake"},
            "action": [
                {
                    "choose": [
                        {
                            "conditions": [],
                            "sequence": [
                                # 4.x automations often still say service.
                                {"service": "adjustable_bed.linak_set_alarm", "data": {"time": "07:00"}},
                            ],
                        }
                    ]
                },
                {"action": "adjustable_bed.set_alarm", "data": {"time": "07:00"}},
            ],
        },
        {
            "id": "quiet",
            "alias": "Quiet",
            "trigger": {"platform": "event", "event_type": "quiet"},
            "action": {"action": "adjustable_bed.goodvibe", "data": {"operation": "sync"}},
        },
    ]
}
SCRIPTS = {
    "script": {
        "report": {
            "sequence": [
                {
                    "action": "adjustable_bed.gmmotor",
                    # 4.x read a quoted number as the number.
                    "data": {"operation": "sleep_report", "part": "01", "report_type": "day"},
                },
                {"action": "adjustable_bed.reverie_test"},
                # Listed by the operation that moved, not as an alarm.
                {"action": "adjustable_bed.rmcontrol_alarm", "data": {"operation": "sync"}},
                {
                    "action": "adjustable_bed.sleep_number_command",
                    "data": {"command": "kid_outlet", "parameters": {"device": 2, "outlet_on": True}},
                },
            ]
        }
    }
}


async def _report(hass: HomeAssistant) -> ir.IssueEntry | None:
    async_report_removed_calls(hass)
    await hass.async_block_till_done()
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)


async def test_repair_names_each_caller_and_its_replacement(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "automation", AUTOMATIONS)
    assert await async_setup_component(hass, "script", SCRIPTS)

    issue = await _report(hass)

    assert issue is not None
    assert issue.translation_placeholders == {
        "calls": "\n".join(
            (
                "- `adjustable_bed.gmmotor` `part: 1` → `part: left`: script.report",
                "- `adjustable_bed.goodvibe` `operation: sync` → `adjustable_bed.sync_clock`: "
                "automation.quiet",
                "- `adjustable_bed.linak_set_alarm` → `adjustable_bed.set_alarm`: "
                "automation.wake_up",
                "- `adjustable_bed.reverie_test`: script.report",
                "- `adjustable_bed.rmcontrol_alarm` `operation: sync` → "
                "`adjustable_bed.sync_clock`: script.report",
                "- `adjustable_bed.sleep_number_command` `parameters.device: 2` → "
                "`parameters.device: 0`: script.report",
            )
        )
    }


async def test_no_repair_once_nothing_calls_a_removed_action(hass: HomeAssistant) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={"calls": "- adjustable_bed.linak_set_alarm: automation.old"},
    )
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "alias": "Wake up",
                "trigger": {"platform": "event", "event_type": "wake"},
                "action": {"action": "adjustable_bed.set_alarm", "data": {"time": "07:00"}},
            }
        },
    )

    assert await _report(hass) is None


def test_every_removal_is_on_the_upgrade_page_and_gone_from_the_actions() -> None:
    root = Path(__file__).parents[1]
    page = (root / "docs/V5_BREAKING_CHANGES.md").read_text()
    listed = {
        action
        for heading in ("| 4.x action | Use now |", "| Beta action | Use now |")
        for row in page.split(heading, 1)[1].split("\n\n", 1)[0].splitlines()[2:]
        for action in re.findall(r"`(\w+)`", row.split("|")[1])
    }
    actions = yaml.safe_load((root / "custom_components/adjustable_bed/services.yaml").read_text())

    assert {removal.action for removal in REMOVALS if removal.field is None} == listed
    assert not listed & actions.keys()
    for removal in REMOVALS:
        # A field of an action that is gone only refines that action's advice.
        if removal.field is None or removal.action not in actions:
            continue
        field = actions[removal.action].get("fields", {}).get(removal.field)
        if removal.value is None:
            assert field is None, removal
        elif field is not None:
            options = field["selector"]["select"]["options"]
            assert removal.value not in options, removal
