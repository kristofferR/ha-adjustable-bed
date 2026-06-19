// Discover a bed's entities from the Home Assistant entity registry and bucket
// them into UI sections by their translation_key. Every entity created by the
// integration sets a stable translation_key (see strings.json), so this mapping
// is robust across all supported bed types — a section only appears when its
// entities exist.
import type {
  BedEntities,
  EntityRegistryDisplayEntry,
  HomeAssistant,
  MemorySlot,
  MotorEntity,
} from "./types";

export const PLATFORM = "adjustable_bed";

// Default render order of the card's sections (keys without the "show_" prefix).
export const SECTION_ORDER = [
  "graphic",
  "motors",
  "firmness",
  "presets",
  "memory",
  "lighting",
  "massage",
  "climate",
  "connection",
];

// Display order for motors and presets (entities are rendered in this order
// regardless of registry order). Unknown motors/presets are appended after.
export const MOTOR_ORDER = [
  "back",
  "legs",
  "head",
  "feet",
  "lumbar",
  "pillow",
  "neck",
  "tilt",
  "hip",
  "bed_height",
  "stair",
];

export const PRESET_ORDER = [
  "preset_flat",
  "preset_zero_g",
  "preset_anti_snore",
  "preset_tv",
  "preset_lounge",
  "preset_incline",
  "preset_both_up",
  "preset_yoga",
];

const domainOf = (entityId: string): string => entityId.split(".", 1)[0];

// The translation_key the integration assigned, falling back to the registry
// display name slug only if a key is somehow absent.
const keyOf = (entry: EntityRegistryDisplayEntry): string =>
  entry.translation_key ?? "";

function emptyBed(): BedEntities {
  return {
    motors: [],
    firmness: [],
    presets: [],
    memory: [],
    presence: [],
    lights: {},
    massage: { buttons: [], numbers: [] },
    climate: { entities: [], selects: [] },
  };
}

export function bedEntitiesForDevice(
  hass: HomeAssistant,
  deviceId: string | undefined,
): BedEntities {
  const bed = emptyBed();
  if (!deviceId || !hass?.entities) return bed;

  const motorMap = new Map<string, MotorEntity>();
  const motor = (key: string): MotorEntity => {
    let m = motorMap.get(key);
    if (!m) {
      m = { key };
      motorMap.set(key, m);
    }
    return m;
  };
  const presetMap = new Map<string, string>();
  const memoryMap = new Map<number, MemorySlot>();
  const memory = (slot: number): MemorySlot => {
    let s = memoryMap.get(slot);
    if (!s) {
      s = { slot };
      memoryMap.set(slot, s);
    }
    return s;
  };

  for (const entry of Object.values(hass.entities)) {
    if (entry.device_id !== deviceId || entry.platform !== PLATFORM) continue;
    if (entry.hidden) continue;
    const id = entry.entity_id;
    const domain = domainOf(id);
    const key = keyOf(entry);
    if (!key) continue;

    let match: RegExpMatchArray | null;

    switch (domain) {
      case "cover":
        motor(key).cover = id;
        break;

      case "sensor":
        if (key.endsWith("_angle")) motor(key.slice(0, -6)).angle = id;
        break;

      case "number":
        if (key.endsWith("_position")) motor(key.slice(0, -9)).position = id;
        else if (key.startsWith("massage_") && key.endsWith("_intensity"))
          bed.massage.numbers.push(id);
        else if (key === "light_level") bed.lights.level = id;
        else if (key.startsWith("sleep_number_setting")) bed.firmness.push(id);
        break;

      case "button":
        if (PRESET_ORDER.includes(key) || key.startsWith("preset_")) {
          if ((match = key.match(/^preset_memory_(\d+)$/)))
            memory(Number(match[1])).goto = id;
          else presetMap.set(key, id);
        } else if ((match = key.match(/^program_memory_(\d+)$/))) {
          memory(Number(match[1])).save = id;
        } else if (key === "stop") {
          bed.stop = id;
        } else if (key === "connect") {
          bed.connect = id;
        } else if (key === "disconnect") {
          bed.disconnect = id;
        } else if (key === "toggle_light") {
          bed.lights.toggle = id;
        } else if (key === "light_cycle") {
          bed.lights.cycle = id;
        } else if (key.startsWith("massage_")) {
          bed.massage.buttons.push(id);
        } else if ((match = key.match(/^(.+)_(up|down)$/))) {
          motor(match[1])[match[2] as "up" | "down"] = id;
        }
        break;

      case "switch":
        if (key === "under_bed_lights") bed.lights.switch = id;
        break;

      case "light":
        bed.lights.light = id;
        break;

      case "binary_sensor":
        if (key === "ble_connection") bed.connectivity = id;
        else if (key.startsWith("bed_presence")) bed.presence.push(id);
        break;

      case "select":
        if (key === "light_timer") bed.lights.timer = id;
        else if (key === "massage_timer") bed.massage.timer = id;
        else if (/thermal|footwarming|foundation/.test(key))
          bed.climate.selects.push(id);
        break;

      case "climate":
        bed.climate.entities.push(id);
        break;
    }
  }

  // Order motors: known order first, then any extras alphabetically.
  const motorKeys = [...motorMap.keys()];
  const ordered = [
    ...MOTOR_ORDER.filter((k) => motorMap.has(k)),
    ...motorKeys.filter((k) => !MOTOR_ORDER.includes(k)).sort(),
  ];
  bed.motors = ordered
    .map((k) => motorMap.get(k)!)
    .filter((m) => m.cover || m.up || m.down || m.angle || m.position);

  // Order presets.
  const presetKeys = [...presetMap.keys()];
  bed.presets = [
    ...PRESET_ORDER.filter((k) => presetMap.has(k)),
    ...presetKeys.filter((k) => !PRESET_ORDER.includes(k)).sort(),
  ].map((k) => presetMap.get(k)!);

  // Order memory slots ascending; keep only slots with at least one action.
  bed.memory = [...memoryMap.values()]
    .filter((s) => s.goto || s.save)
    .sort((a, b) => a.slot - b.slot);

  return bed;
}

// True when the bed exposes nothing the card renders. Presence sensors are not
// counted because the card has no presence section (it would otherwise produce a
// header-only card with no controls).
export function bedIsEmpty(bed: BedEntities): boolean {
  const l = bed.lights;
  return (
    bed.motors.length === 0 &&
    bed.firmness.length === 0 &&
    bed.presets.length === 0 &&
    bed.memory.length === 0 &&
    !bed.stop &&
    !bed.connect &&
    !bed.disconnect &&
    !bed.connectivity &&
    !l.light &&
    !l.switch &&
    !l.level &&
    !l.toggle &&
    !l.cycle &&
    !l.timer &&
    bed.massage.buttons.length === 0 &&
    bed.massage.numbers.length === 0 &&
    !bed.massage.timer &&
    bed.climate.entities.length === 0 &&
    bed.climate.selects.length === 0
  );
}
