// Compact layouts use the same entity buckets and commands as the full card.
import { SECTION_ORDER, bedEntitiesForDevice, isSingleAddressPairedDevice,
  pairedChildDeviceIds, resolvePairedParentId } from "./discovery";
import { localize } from "./localize";
import { deviceName, entityLabel } from "./names";
import type { AdjustableBedCardConfig, BedEntities, HomeAssistant } from "./types";

export type CompactPreset = "glance" | "quick" | "controls";
export const COMPACT_PRESETS: readonly CompactPreset[] = ["glance", "quick", "controls"];

// Every full-card section is shown, whatever the compact card hides.
const FULL_CARD_SECTIONS: Partial<AdjustableBedCardConfig> = Object.fromEntries(
  SECTION_ORDER.map((key) => [`show_${key}`, true]),
);

// A full card's value for each option its editor sets. The dialog editor
// stores these explicitly, so clearing an option there never re-inherits a
// different compact setting when the dialog opens.
export const FULL_CARD_EDITOR_DEFAULTS: Partial<AdjustableBedCardConfig> = {
  name: "", show_header: true, animate: true, show_graphic_labels: true,
  show_percentage_graphic: false, show_lumbar_graphic: false, ...FULL_CARD_SECTIONS,
  section_order: [], memory_save: true, memory_slots: [], tap_to_move: false,
};

export function fullCardDialogConfig(config: AdjustableBedCardConfig): AdjustableBedCardConfig {
  return {
    ...config,
    show_header: true,
    ...FULL_CARD_SECTIONS,
    ...config.dialog_config,
    // A dialog must not recursively open dialogs or silently target another bed.
    type: config.type,
    device_id: config.device_id,
    layout: "full",
    open_dialog: false,
    navigation_path: undefined,
    dialog_config: undefined,
  };
}

// Recipes write ordinary options so later customization has one source of truth.
export function applyCompactPreset(
  config: AdjustableBedCardConfig,
  preset: CompactPreset,
): AdjustableBedCardConfig {
  const next: AdjustableBedCardConfig = {
    ...config,
    layout: "compact",
    show_header: true,
    show_graphic: true,
    compact_labels: preset === "glance" ? "names" : "angles",
    show_side_selector: true,
    show_motors: preset === "controls",
    show_lighting: false,
    show_connection: false,
    animate: true,
  };
  if (preset === "glance") next.compact_actions = [];
  else delete next.compact_actions;
  return next;
}

export interface CompactAction {
  // The entity's translation key, shared by its counterparts on other sides.
  key: string;
  entityId: string;
}

export function compactActionOptions(hass: HomeAssistant, bed: BedEntities): CompactAction[] {
  return [...bed.presets, ...bed.memory.flatMap((slot) => slot.goto ? [slot.goto] : [])]
    .flatMap((entityId) => {
      const key = hass.entities[entityId]?.translation_key;
      return key ? [{ key, entityId }] : [];
    });
}

// `compact_actions` stores entity ids, because several presets can share one
// translation key (app-labelled presets). A side resolves an id saved from
// another side to its counterpart: the same key and, when the key is shared,
// the same name. Older cards stored translation keys; those still resolve to
// the first action with that key.
export function resolveCompactAction(
  hass: HomeAssistant,
  options: CompactAction[],
  saved: string,
): CompactAction | undefined {
  if (!saved.includes(".")) return options.find((a) => a.key === saved);
  const exact = options.find((a) => a.entityId === saved);
  if (exact) return exact;
  const key = hass.entities[saved]?.translation_key;
  const sameKey = options.filter((a) => a.key === key);
  if (sameKey.length <= 1) return sameKey[0];
  const name = entityLabel(hass, saved);
  return sameKey.find((a) => entityLabel(hass, a.entityId) === name);
}

export function compactActions(
  hass: HomeAssistant,
  bed: BedEntities,
  selected?: string[],
): CompactAction[] {
  const options = compactActionOptions(hass, bed);
  if (selected) {
    const resolved = selected.flatMap((saved) => {
      const action = resolveCompactAction(hass, options, saved);
      return action ? [action] : [];
    });
    return resolved.filter((a, i) => resolved.findIndex((b) => b.entityId === a.entityId) === i);
  }
  // Do not assume which memory means "sit". Names and icons follow the entity.
  const flat = options.find((a) => a.key === "preset_flat");
  const favourite = options.find((a) => a.key.startsWith("preset_memory_")) ??
    options.find((a) => a !== flat);
  return [flat, favourite].filter((a): a is CompactAction => a !== undefined);
}

// The editor's list: every action of the default side first, then actions only
// another side has. Each option stands for its counterparts on the other sides.
// The selection is returned as entity ids, so saving it migrates a card that
// stored translation keys.
export function compactActionChoices(
  hass: HomeAssistant,
  targets: CompactTarget[],
  defaultTarget: CompactTarget | undefined,
  saved: string[] | undefined,
): { options: CompactAction[]; selected: string[] } {
  const listed: { action: CompactAction; sideOptions: CompactAction[] }[] = [];
  const findListed = (savedId: string) => listed.find(({ action, sideOptions }) =>
    resolveCompactAction(hass, sideOptions, savedId)?.entityId === action.entityId);
  const ordered = defaultTarget
    ? [defaultTarget, ...targets.filter((t) => t !== defaultTarget)] : targets;
  for (const target of ordered) {
    const sideOptions = compactActionOptions(hass, target.bed);
    for (const action of sideOptions) {
      if (!findListed(action.entityId)) listed.push({ action, sideOptions });
    }
  }
  const selectedIds = (saved ?? (defaultTarget
    ? compactActions(hass, defaultTarget.bed).map((a) => a.entityId) : []))
    .flatMap((value) => {
      const match = findListed(value);
      return match ? [match.action.entityId] : [];
    });
  return { options: listed.map(({ action }) => action), selected: [...new Set(selectedIds)] };
}

export function compactStopEntities(bed: BedEntities): string[] {
  return bed.stop ? [bed.stop] : bed.motors.flatMap((m) => m.cover ? [m.cover] : []);
}

// Only local HA navigation is accepted, including when configured via YAML.
export function cardNavigationPath(path?: string): string | undefined {
  if (!path || !path.startsWith("/") || /^\/[/\\]/.test(path) || /[\\\s]/.test(path))
    return undefined;
  return path;
}

export interface CompactTarget {
  key: string;
  label: string;
  bed: BedEntities;
}

export function compactTargets(hass: HomeAssistant, deviceId?: string): CompactTarget[] {
  const parent = resolvePairedParentId(hass, deviceId);
  const children = pairedChildDeviceIds(hass, parent);
  if (parent && children.length) {
    return [{ key: "both", label: localize(hass, "card.both_sides"),
      bed: bedEntitiesForDevice(hass, parent) }, ...children.map((id) => ({
        key: id, label: deviceName(hass, id) ?? id,
        bed: bedEntitiesForDevice(hass, id),
      }))];
  }
  if (isSingleAddressPairedDevice(hass, deviceId)) {
    return (["both", "left", "right"] as const).map((side) => ({
      key: side,
      label: localize(hass, `card.${side === "both" ? "both_sides" : `${side}_side`}`),
      bed: bedEntitiesForDevice(hass, deviceId, side),
    }));
  }
  return [{ key: "both", label: localize(hass, "card.both_sides"),
    bed: bedEntitiesForDevice(hass, deviceId) }];
}
