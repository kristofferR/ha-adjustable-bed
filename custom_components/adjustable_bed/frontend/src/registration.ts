import { PLATFORM } from "./discovery";
import { localizeLanguage } from "./localize";
import type { AdjustableBedCardConfig, HomeAssistant } from "./types";

export interface CustomCardSuggestion {
  config: AdjustableBedCardConfig;
}

export interface CustomCardEntry {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
  documentationURL?: string;
  getEntitySuggestion?: (
    hass: HomeAssistant,
    entityId: string,
  ) => CustomCardSuggestion | null;
}

export interface CustomCardsWindow {
  customCards?: CustomCardEntry[];
}

const CARD_TYPE = "adjustable-bed-card";

// The card picker has no hass object yet, so it follows the page language.
function pageLanguage(): string | undefined {
  return typeof document !== "undefined"
    ? document.documentElement.lang || navigator.language : undefined;
}

const cardEntry = (language?: string): CustomCardEntry => ({
  type: CARD_TYPE,
  name: localizeLanguage(language, "card.picker_name"),
  description: localizeLanguage(language, "card.picker_description"),
  preview: true,
  documentationURL: "https://github.com/kristofferR/ha-adjustable-bed",
  getEntitySuggestion: (hass, entityId) => {
    const entity = hass.entities[entityId];
    if (entity?.platform !== PLATFORM || !entity.device_id) return null;

    return {
      config: {
        type: `custom:${CARD_TYPE}`,
        device_id: entity.device_id,
      },
    };
  },
});

export function registerCustomCard(
  target: CustomCardsWindow,
  language: string | undefined = pageLanguage(),
): void {
  const cards = (target.customCards ??= []);
  const existingIndex = cards.findIndex((card) => card.type === CARD_TYPE);

  if (existingIndex === -1) {
    cards.push(cardEntry(language));
  } else {
    cards[existingIndex] = cardEntry(language);
  }
}

// Define once, so a cache-busted second copy of the bundle does not throw on a
// duplicate definition. Since 2026.11 the frontend loads extra modules after its
// scoped-registry polyfill (home-assistant/frontend#54444), so the element lands
// in the registry Lovelace reads.
export function defineElement(
  tag: string,
  element: CustomElementConstructor,
  registry: CustomElementRegistry = window.customElements,
): void {
  if (!registry.get(tag)) registry.define(tag, element);
}

// Register before the custom elements are defined. A cache-busted second copy
// can then refresh picker metadata even if the browser rejects duplicate custom
// element definitions later in that module evaluation.
if (typeof window !== "undefined") {
  registerCustomCard(window as CustomCardsWindow);
}
