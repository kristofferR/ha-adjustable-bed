// Test helper: give mock entities the card placement the integration publishes
// for their translation key. The fixture is generated from the integration's
// entities by tests/card_placements.py.
import placements from "../../../../tests/fixtures/card_placements.json";
import type { HassEntity, HomeAssistant } from "./types";

const PLACEMENTS: Record<string, Record<string, string | number>> = placements;

// Every cover is its own motor and every light is lit, whatever its key.
function placementFor(domain: string, key: string): Record<string, string | number> | undefined {
  return PLACEMENTS[`${domain}:${key}`] ??
    (domain === "cover" ? { card_section: "motors", card_motor: key }
      : domain === "light" ? { card_section: "lighting" } : undefined);
}

// Add its placement to each adjustable_bed entity's state when it is read,
// creating a state for an entity the test registered without one. Tests may
// keep assigning hass.states[id] and its attributes afterwards.
export function placed<T extends HomeAssistant>(hass: T): T {
  if (!hass.states) return hass;
  hass.states = new Proxy(hass.states, {
    get(target, property, receiver) {
      const state = Reflect.get(target, property, receiver) as HassEntity | undefined;
      if (typeof property !== "string") return state;
      const entry = hass.entities?.[property];
      const placement =
        entry?.platform === "adjustable_bed" && entry.translation_key !== undefined
          ? placementFor(property.split(".", 1)[0], entry.translation_key)
          : undefined;
      if (!placement) return state;
      if (!state) {
        const created: HassEntity = {
          entity_id: property, state: "unknown", attributes: { ...placement },
          last_changed: "", last_updated: "",
        };
        target[property] = created;
        return created;
      }
      if (state.attributes.card_section === undefined) {
        state.attributes = { ...placement, ...state.attributes };
      }
      return state;
    },
  });
  return hass;
}

// Publish the placement of an entity only a live bed creates, which the
// fixture cannot reach.
export function publish(
  hass: HomeAssistant,
  entityId: string,
  placement: Record<string, string | number>,
): void {
  const state: HassEntity = hass.states[entityId] ?? {
    entity_id: entityId, state: "unknown", attributes: {}, last_changed: "", last_updated: "",
  };
  hass.states[entityId] = { ...state, attributes: { ...state.attributes, ...placement } };
}
