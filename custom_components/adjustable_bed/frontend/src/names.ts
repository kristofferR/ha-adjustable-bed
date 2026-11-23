// Display names from Home Assistant's entity naming model (2026.11): an entity
// is named once, and its device supplies the context. The card header already
// names the bed and each paired pane names its side, so labels inside the card
// show only the entity's own name, never the composed friendly name.
import type { HomeAssistant } from "./types";

export function deviceName(
  hass: HomeAssistant | undefined,
  deviceId: string | undefined,
): string | undefined {
  const device = deviceId ? hass?.devices[deviceId] : undefined;
  return (device?.name_by_user || device?.name)?.trim() || undefined;
}

// An entity without a name of its own goes by its device's name, which the
// formatter applies. `fallback` covers an entity that has no state yet.
export function entityLabel(
  hass: HomeAssistant | undefined,
  entityId: string,
  fallback: string = entityId,
): string {
  const stateObj = hass?.states[entityId];
  const name = stateObj
    ? hass!.formatEntityName(stateObj, { type: "entity" })
    : hass?.entities[entityId]?.name;
  return name || fallback;
}

// A paired side's own part of its name: "Bed Left" under the parent "Bed" is
// "Left". A side named on its own keeps its whole name.
export function sideName(name: string, parentName: string | undefined): string {
  if (!parentName || name.length <= parentName.length ||
    !name.toLowerCase().startsWith(parentName.toLowerCase())) return name;
  const rest = name.slice(parentName.length);
  return /^[\s\-·:,]/.test(rest) ? rest.replace(/^[\s\-·:,]+/, "") || name : name;
}
