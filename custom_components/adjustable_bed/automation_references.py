"""Find what automations and scripts reference, as written and as loaded.

The repairs that name automations and scripts still using something v5
removed or changed share this scan. Templates are not checked.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import EntityComponent


def automation_configs(hass: HomeAssistant) -> Iterator[tuple[str, object]]:
    """Yield each automation and script with its config as written and as loaded."""
    for domain in ("automation", "script"):
        component = hass.data.get(domain)
        if not isinstance(component, EntityComponent):
            continue
        for entity in component.entities:
            # The loaded sequence holds what a blueprint expands to.
            script = getattr(entity, "action_script", None) or getattr(entity, "script", None)
            yield entity.entity_id, (
                getattr(entity, "raw_config", None),
                getattr(script, "sequence", None),
            )


def _names(config: object, references: Collection[str]) -> bool:
    """Whether a config names one of the references in any of its values."""
    if isinstance(config, str):
        # An entity_id field may list several IDs in one string.
        return any(part.strip().lower() in references for part in config.split(","))
    if isinstance(config, Mapping):
        return any(_names(value, references) for value in config.values())
    if isinstance(config, list | tuple):
        return any(_names(value, references) for value in config)
    return False


def entity_users(hass: HomeAssistant, references: Collection[str]) -> set[str]:
    """Return the automations and scripts naming an entity by its ID or registry ID."""
    from homeassistant.components.automation import automations_with_entity  # noqa: PLC0415
    from homeassistant.components.script import scripts_with_entity  # noqa: PLC0415

    wanted = {reference.lower() for reference in references}
    # Triggers and conditions as loaded, which the sequence leaves out.
    users = {
        user
        for reference in wanted
        for user in (*automations_with_entity(hass, reference), *scripts_with_entity(hass, reference))
    }
    users.update(entity_id for entity_id, config in automation_configs(hass) if _names(config, wanted))
    return users
