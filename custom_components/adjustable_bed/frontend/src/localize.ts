// Card-owned translations for section headers and editor labels. Entity display
// names come from Home Assistant's own localized friendly_name, so this only
// covers the card's structural chrome.
import en from "./translations/en.json";
import nb from "./translations/nb.json";
import type { HomeAssistant } from "./types";

type Strings = Record<string, string>;

const LANGUAGES: Record<string, Strings> = { en, nb };

function pickLanguage(hass?: HomeAssistant): Strings {
  const lang = (hass?.locale?.language || hass?.language || "en").toLowerCase();
  // Match primary subtag, e.g. "nb-NO" -> "nb", "nn" -> Norwegian fallback.
  const primary = lang.split("-")[0];
  if (LANGUAGES[lang]) return LANGUAGES[lang];
  if (LANGUAGES[primary]) return LANGUAGES[primary];
  if (primary === "nn" || primary === "no") return LANGUAGES.nb;
  return LANGUAGES.en;
}

export function localize(
  hass: HomeAssistant | undefined,
  key: string,
  params?: Record<string, string>,
): string {
  const strings = pickLanguage(hass);
  let value = strings[key] ?? LANGUAGES.en[key] ?? key;
  if (params) {
    for (const [name, replacement] of Object.entries(params)) {
      value = value.replace(`{${name}}`, replacement);
    }
  }
  return value;
}
