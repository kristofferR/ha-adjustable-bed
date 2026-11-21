"""Name the automations and scripts that still call what v5 removed.

A removed action fails as an unknown action when an automation runs, and a
removed field or option fails validation; neither says what replaces it. Once
Home Assistant has started, one repair lists every automation and script that
still calls one, with its replacement, and goes away at the first start where
none does. Templates are not checked.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.start import async_at_started
from homeassistant.loader import async_get_integration

from .automation_references import automation_configs
from .beta_feedback import breaking_changes_url
from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class Removal:
    """An action, one of its fields or one value of a field that 4.x or a beta had."""

    action: str
    # A field, or a dotted path into a mapping field.
    field: str | None = None
    # The field's removed value, or None when the field itself is gone.
    value: str | None = None
    # What a call uses now, as the call writes it; None where nothing in an
    # action replaces it (the upgrade guide says what does).
    use: str | None = None

    def matches(self, action: str, data: Mapping[object, object]) -> bool:
        if action != self.action:
            return False
        if self.field is None:
            return True
        value: object = data
        for name in self.field.split("."):
            if not isinstance(value, Mapping) or name not in value:
                return False
            value = value[name]
        if self.value is None:
            return True
        # Templates compile to objects that keep their source; 4.x read "01" as 1.
        given = str(getattr(value, "template", value)).strip()
        if given.isdecimal() and self.value.isdecimal():
            return int(given) == int(self.value)
        return given == self.value

    @property
    def line(self) -> str:
        call = f"`{DOMAIN}.{self.action}`"
        if self.field is not None:
            call += f" `{self.field}`" if self.value is None else f" `{self.field}: {self.value}`"
        return call if self.use is None else f"{call} → `{self.use}`"


def _actions(actions: str, use: str | None) -> tuple[Removal, ...]:
    return tuple(Removal(action, use=use) for action in actions.split())


# What 4.4.2 or a v5 beta offered and v5 no longer accepts, from the upgrade guide.
# A later removal may add a row so callers get a repair; it is not required.
REMOVALS: Final[tuple[Removal, ...]] = (
    *_actions(
        "bf_cherish_set_alarm comfort_enhancements_set_alarm configure_alarm_schedule "
        "eshine_set_alarm glideaway_set_alarm jiecang_set_alarm leggett_alarm_timer "
        "linak_set_alarm logicdata_set_alarm malouf_set_alarm motion_bed_alarm "
        "richmat_mh_alarm richmat_mh_waist_alarm rmcontrol_alarm simmons_set_alarm "
        "solace_set_alarm zseries_set_alarm",
        f"{DOMAIN}.set_alarm",
    ),
    *_actions("jiecang_rename linak_rename logicdata_rename", f"{DOMAIN}.rename"),
    *_actions("leggett_hold_control", f"{DOMAIN}.hold_control"),
    *_actions("malouf_sync_clock motion_bed_clock", f"{DOMAIN}.sync_clock"),
    *_actions("reverie_test", None),
    # A call matching one of these is listed by it, not by its action's row.
    Removal("rmcontrol_alarm", "operation", "sync", f"{DOMAIN}.sync_clock"),
    Removal("rmcontrol_alarm", "operation", "query"),
    Removal("rmcontrol_alarm", "operation", "cancel_single", f"{DOMAIN}.set_alarm enabled: false"),
    Removal(
        "rmcontrol_alarm",
        "operation",
        "delete",
        f"{DOMAIN}.set_alarm enabled: false, slot: <its alarm_id>",
    ),
    # Only in v5 betas.
    *_actions(
        "comfort_enhancement3_set_wakeup "
        "comfortbase_set_alarm jalon_bed_set_alarm jalon_set_alarm mline_set_alarm "
        "n32_motion_bed_alarm richmat_app_alarm smart_sleep_set_alarm "
        "symphony_sense_set_alarm symphony_set_alarm yamada_set_alarm",
        f"{DOMAIN}.set_alarm",
    ),
    Removal("comfort_enhancement3_delete_wakeup", use=f"{DOMAIN}.set_alarm enabled: false"),
    *(
        Removal(old, use=f"{DOMAIN}.estimate_{new}")
        for old, new in (
            ("save_position", "save_position"),
            ("rename_position", "rename_position"),
            ("update_position", "update_position"),
            ("delete_position", "delete_position"),
            ("recall_position", "recall_position"),
            ("set_position_reference", "set_reference"),
            ("confirm_position_unchanged", "confirm_unchanged"),
            ("mark_position_unknown", "mark_unknown"),
        )
    ),
    *(
        Removal(action, "operation", operation, f"{DOMAIN}.sync_clock")
        for action, operation in (
            ("galaxy", "sync"),
            ("mlily", "sync"),
            ("sonicsleep", "sync_clock"),
            ("richmat_app", "sync"),
            ("richmat_app", "sleep_sync"),
        )
    ),
    Removal("luuna", "operation", "time_sync", f"{DOMAIN}.sync_clock"),
    *(
        Removal(action, "operation", operation, f"{DOMAIN}.set_alarm{use}")
        for action, operation, use in (
            ("bedgear", "alarm", ""),
            ("luuna", "alarm", ""),
            ("luuna", "alarm_cancel", " enabled: false"),
            ("richmat_resource_bed", "alarm", ""),
            ("richmat_resource_bed", "cancel_alarm", " enabled: false"),
            ("richmat_rise", "alarm", ""),
            ("richmat_rise", "cancel_alarm", " enabled: false"),
        )
    ),
    Removal("gmmotor", "operation", "clock_sync", f"{DOMAIN}.sync_clock"),
    Removal("gmmotor", "repeat"),
    Removal("gmmotor", "status"),
    *(
        Removal("gmmotor", field, old, f"{field}: {new}")
        for field, values in (("part", ("left", "right")), ("report_type", ("day", "month")))
        for old, new in zip(("1", "2"), values, strict=True)
    ),
    Removal("goodvibe", "operation", "sync", f"{DOMAIN}.sync_clock"),
    Removal("furnimove_action", "consumer"),
    Removal("sleep_number_command", "command", "set_system_time", f"{DOMAIN}.sync_clock"),
    # Only the app's single local outlet and light remain.
    *(
        Removal("sleep_number_command", "parameters.device", str(device), "parameters.device: 0")
        for device in range(1, 16)
    ),
    *(
        Removal("sleep_number_command", "command", command)
        for command in (
            "reboot_system",
            "starts_actuator_homing",
            "get_frosty_mode",
            "set_frosty_mode",
            "get_frosty_presence",
            "get_heidi_mode",
            "set_heidi_mode",
            "get_heidi_presence",
            "get_system_status",
            # Resetting saved positions needs the button's confirmation.
            "preset_reset",
            "reset_articulation_presets",
        )
    ),
    # Factory motor tests and motor programming, only in v5 betas.
    *(
        Removal(action, "operation", operation)
        for action, operation in (
            ("richmat_rise", "diagnostic_cycle"),
            ("richmat_rise", "program_schedule"),
            ("lp2", "motor_program"),
            ("lp2", "movement_test"),
            ("bedsmart", "movement_test"),
        )
    ),
    Removal("richmat_rise", "schedule"),
    Removal("lp2", "schedule"),
    Removal("bedsmart", "confirm"),
    # Beta 8 only; the bed's preset, memory and save buttons replace it.
    Removal("symphony_preset"),
)

ISSUE_ID: Final = "removed_actions"


def _calls(config: object) -> Iterator[tuple[str, Mapping[object, object]]]:
    """Yield each call of this integration's actions in a config, with its data."""
    if isinstance(config, Mapping):
        # Older configs may still name a literal action in service_template.
        action = next(
            (config[key] for key in ("action", "service", "service_template") if key in config),
            None,
        )
        if isinstance(action, str) and action.startswith(f"{DOMAIN}."):
            data: dict[object, object] = {}
            for key in ("data", "data_template"):
                if isinstance(given := config.get(key), Mapping):
                    data.update(given)
            yield action.removeprefix(f"{DOMAIN}."), data
        for value in config.values():
            yield from _calls(value)
    elif isinstance(config, list | tuple):
        for value in config:
            yield from _calls(value)


def removed_calls(hass: HomeAssistant) -> dict[str, set[str]]:
    """Return each removed call's line with the automations and scripts that make it."""
    callers: dict[str, set[str]] = {}
    for entity_id, config in automation_configs(hass):
        for action, data in _calls(config):
            matched = [removal for removal in REMOVALS if removal.matches(action, data)]
            # A field's own row says more than its action's.
            if any(removal.field is not None for removal in matched):
                matched = [removal for removal in matched if removal.field is not None]
            for removal in matched:
                callers.setdefault(removal.line, set()).add(entity_id)
    return callers


@callback
def async_report_removed_calls(hass: HomeAssistant) -> None:
    """Raise or withdraw the repair once automations and scripts have loaded."""

    async def report(_hass: HomeAssistant) -> None:
        callers = removed_calls(hass)
        if not callers:
            ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
            return
        version = (await async_get_integration(hass, DOMAIN)).version
        guide = breaking_changes_url(version) if version is not None else None
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_ID,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=f"{guide}#actions-and-automations" if guide else None,
            translation_key=ISSUE_ID,
            translation_placeholders={
                "calls": "\n".join(
                    f"- {line}: {', '.join(sorted(users))}"
                    for line, users in sorted(callers.items())
                ),
            },
        )

    async_at_started(hass, report)
