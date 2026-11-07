// Discover a bed's entities from the Home Assistant entity registry and bucket
// them into UI sections by the card placement each entity publishes (see the
// integration's card.py): its section, plus a role where its domain does not
// pick its control, and the motor or memory slot it serves. A section only
// appears when its entities exist.
import { heldReleaseButton, holdLeaseRoute } from "./hold";
import { deviceName } from "./names";
import type {
  BedSide,
  BedEntities,
  EntityRegistryDisplayEntry,
  HomeAssistant,
  LightEntities,
  MemorySlot,
  MotorEntity,
} from "./types";

export const PLATFORM = "adjustable_bed";
export type { BedSide } from "./types";

// Default render order of the card's sections (keys without the "show_" prefix).
export const SECTION_ORDER = [
  "graphic",
  "motors",
  "firmness",
  "presets",
  "saved_positions",
  "memory",
  "lighting",
  "massage",
  "utility",
  "climate",
  "connection",
];

// Display order for motors and presets (entities are rendered in this order
// regardless of registry order). Unknown motors/presets are appended after.
export const MOTOR_ORDER = [
  "back",
  "legs",
  "back_legs",
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
  "preset_reading",
  "preset_swing",
  "preset_incline",
  "preset_both_up",
  "preset_yoga",
];

// These covers use a side-wide controller STOP rather than an actuator STOP.
const SIDE_WIDE_STOP_KEYS = new Set([
  "elevate_both",
  "starcode_m1x12_part_1",
  "starcode_m1x12_part_2",
  "starcode_m1x12_part_4",
  "starcode_m1x12_part_8",
  "starcode_m1x12_part_16",
]);

const domainOf = (entityId: string): string => entityId.split(".", 1)[0];

const keyOf = (entry: EntityRegistryDisplayEntry): string =>
  entry.translation_key ?? "";

// Where an entity sits in the card, as the integration publishes it.
interface Placement {
  section: string;
  role?: string;
  motor?: string;
  slot?: number;
}

function placementOf(hass: HomeAssistant, entityId: string): Placement | undefined {
  const attributes = hass.states[entityId]?.attributes;
  const section = attributes?.card_section;
  if (typeof section !== "string") return undefined;
  const { card_role: role, card_motor: motor, card_slot: slot } = attributes!;
  return {
    section,
    ...(typeof role === "string" ? { role } : {}),
    ...(typeof motor === "string" ? { motor } : {}),
    ...(typeof slot === "number" ? { slot } : {}),
  };
}

// The side an entity controls, as the integration publishes it.
const entitySide = (hass: HomeAssistant, entityId: string): BedSide | undefined =>
  (hass.states[entityId]?.attributes.bed_side ?? hass.states[entityId]?.attributes.side) as
    | BedSide
    | undefined;

function emptyBed(): BedEntities {
  return {
    motors: [],
    firmness: [],
    presets: [],
    memory: [],
    lights: {},
    massage: { buttons: [], numbers: [] },
    climate: { entities: [], selects: [], numbers: [] },
    utility: [],
    utilityStates: [],
  };
}

export function bedEntitiesForDevice(
  hass: HomeAssistant,
  deviceId: string | undefined,
  selectedSide?: BedSide,
): BedEntities {
  const bed = emptyBed();
  if (!deviceId || !hass?.entities) return bed;
  const mood = () => bed.lights.mood ??= { selects: [], numbers: [] };

  const deviceEntries = Object.values(hass.entities).filter(
    (entry) => entry.device_id === deviceId && entry.platform === PLATFORM,
  );
  const motorMap = new Map<string, MotorEntity>();
  const motor = (key: string): MotorEntity => {
    let m = motorMap.get(key);
    if (!m) {
      m = SIDE_WIDE_STOP_KEYS.has(key) ? { key, coverStopScope: "side" } : { key };
      motorMap.set(key, m);
    }
    return m;
  };
  const motorButton = (
    id: string,
    key: string,
    direction: "up" | "down",
    ownerDeviceId: string | undefined,
  ): void => {
    const item = motor(key);
    item[direction] = id;
    const holdLease = holdLeaseRoute(hass, id, ownerDeviceId ?? deviceId);
    if (holdLease) item.holdLease = holdLease;
    const attributes = hass.states[id]?.attributes;
    const control = attributes?.held_control;
    const startDelayMs = attributes?.hold_start_delay_ms;
    const releaseDelayMs = attributes?.hold_release_delay_ms;
    if (
      typeof control === "string" &&
      typeof startDelayMs === "number" && Number.isFinite(startDelayMs) && startDelayMs >= 0 &&
      typeof releaseDelayMs === "number" && Number.isFinite(releaseDelayMs) && releaseDelayMs >= 0 &&
      ownerDeviceId
    ) {
      item.deviceId = ownerDeviceId;
      item.holdEntityId = id;
      item.heldControls = {
        ...item.heldControls,
        [direction]: { control, startDelayMs, releaseDelayMs },
      };
    }
    const heldMotor = attributes?.paired_hold_motor;
    if (heldMotor === "back" || heldMotor === "legs" || heldMotor === "lumbar") {
      item.timedMove = {
        deviceId,
        motor: heldMotor,
        ...(attributes?.paired_hold_side === "both" ? { side: "both" as const } : {}),
      };
    } else if (
      (key === "back" || key === "legs" || key === "lumbar") &&
      typeof control === "string"
    ) item.timedMove = {
      deviceId,
      motor: key,
      ...(attributes?.bed_side === "both" ? { side: "both" as const } : {}),
    };
  };
  const motorCover = (id: string, key: string, ownerDeviceId: string | undefined): void => {
    const item = motor(key);
    item.cover = id;
    const attributes = hass.states[id]?.attributes;
    const up = attributes?.held_control_up;
    const down = attributes?.held_control_down;
    const releaseButton = heldReleaseButton(hass, id);
    if (releaseButton) item.releaseButton = releaseButton;
    const holdLease = holdLeaseRoute(hass, id, ownerDeviceId);
    if (holdLease) item.holdLease = holdLease;
    if (attributes?.held_stop_scope === "motor" || attributes?.held_stop_scope === "side") {
      item.coverStopScope = attributes.held_stop_scope;
    }
    if (typeof up === "string" && typeof down === "string" &&
        (typeof attributes?.hold_release_button_key !== "string" || item.releaseButton)) {
      if (key === "back" || key === "legs" || key === "lumbar") {
        item.timedMove = { deviceId, motor: key };
      }
      const startDelayMs = attributes?.hold_start_delay_ms;
      const releaseDelayMs = attributes?.hold_release_delay_ms;
      if ((attributes?.held_stop_scope === "motor" || attributes?.held_stop_scope === "side") &&
          ownerDeviceId && typeof startDelayMs === "number" &&
          Number.isFinite(startDelayMs) && startDelayMs >= 0 &&
          typeof releaseDelayMs === "number" &&
          Number.isFinite(releaseDelayMs) && releaseDelayMs >= 0) {
        item.deviceId = ownerDeviceId;
        item.holdEntityId = id;
        item.heldControls = {
          up: { control: up, startDelayMs, releaseDelayMs },
          down: { control: down, startDelayMs, releaseDelayMs },
        };
      }
    }
  };
  const memoryMap = new Map<number, MemorySlot>();
  const memory = (slot: number): MemorySlot => {
    let s = memoryMap.get(slot);
    if (!s) {
      s = { slot };
      memoryMap.set(slot, s);
    }
    return s;
  };

  const lights = bed.lights;
  const presets: { key: string; id: string }[] = [];

  for (const entry of deviceEntries) {
    if (entry.hidden) continue;
    const id = entry.entity_id;
    const place = placementOf(hass, id);
    if (!place || place.section === "hidden") continue;
    // Paired side devices name their side, so keys never carry it; a trailing
    // side word belongs to the control's own name (Simmons "Inclined left").
    if (selectedSide && entitySide(hass, id) !== selectedSide) continue;
    const domain = domainOf(id);
    const { role } = place;

    switch (place.section) {
      case "motors":
        if (role === "stop") bed.stop = id;
        else if (domain === "switch") bed.synchro = id;
        // A split bed's local left/right selector routes the motor controls.
        else if (domain === "select") bed.controlSide = id;
        else if (place.motor === undefined) break;
        else if (domain === "cover") motorCover(id, place.motor, entry.device_id);
        else if (role === "up" || role === "down") motorButton(id, place.motor, role, entry.device_id);
        else if (role === "reference") motor(place.motor).reference = id;
        else if (role === "estimate") motor(place.motor).estimate = id;
        else if (domain === "sensor" && role !== "position") motor(place.motor).angle = id;
        else motor(place.motor).position = id;
        break;

      case "firmness":
        bed.firmness.push(id);
        break;

      case "presets":
        presets.push({ key: keyOf(entry), id });
        break;

      case "memory":
        if (place.slot === undefined) break;
        if (role === "save") memory(place.slot).save = id;
        else memory(place.slot).goto = id;
        break;

      case "saved_positions":
        if (domain === "button") bed.estimateRemote = id;
        else bed.savedPositions = id;
        break;

      case "connection":
        if (role === "connect") bed.connect = id;
        else if (role === "disconnect") bed.disconnect = id;
        else bed.connectivity = id;
        break;

      case "lighting":
        switch (role) {
          case "state": lights.state = id; break;
          case "level": lights.level = id; break;
          case "toggle": lights.toggle = id; break;
          case "cycle": lights.cycle = id; break;
          case "timer": lights.timer = id; break;
          case "timer_minutes":
            lights.timerMinutes = id;
            lights.timerAppliesImmediately = true;
            break;
          case "pending_timer_minutes": lights.timerMinutes = id; break;
          case "timer_toggle": lights.timerToggle = id; break;
          case "mood_toggle": mood().toggle = id; break;
          case "mood":
            if (domain === "select") mood().selects.push(id);
            else if (domain === "number") mood().numbers.push(id);
            else (mood().buttons ??= []).push(id);
            break;
          default:
            if (domain === "light") lights.light = id;
            else if (domain === "switch") lights.switch = id;
            else if (domain === "binary_sensor") lights.state = id;
            else if (domain === "sensor") (lights.states ??= []).push(id);
            else if (domain === "number") (lights.numbers ??= []).push(id);
            else if (domain === "select") lights.timer = id;
            else (lights.buttons ??= []).push(id);
        }
        break;

      case "massage":
        if (role === "timer") bed.massage.timer = id;
        else if (domain === "button") bed.massage.buttons.push(id);
        else if (domain === "number") bed.massage.numbers.push(id);
        else if (domain === "select") (bed.massage.selects ??= []).push(id);
        else (bed.massage.states ??= []).push(id);
        break;

      case "climate":
        if (domain === "select") bed.climate.selects.push(id);
        else if (domain === "number") bed.climate.numbers.push(id);
        else bed.climate.entities.push(id);
        break;

      case "utility":
        if (domain === "number") (bed.utilityNumbers ??= []).push(id);
        else if (domain === "select") (bed.utilitySelects ??= []).push(id);
        else if (domain === "sensor" || domain === "binary_sensor") (bed.utilityStates ??= []).push(id);
        else bed.utility.push(id);
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

  // Order presets: known order first, then the rest by key (then entity_id,
  // for app-labelled presets that share one key).
  const rank = (key: string): number => {
    const index = PRESET_ORDER.indexOf(key);
    return index < 0 ? PRESET_ORDER.length : index;
  };
  bed.presets = presets
    .sort((a, b) =>
      rank(a.key) - rank(b.key) ||
      (a.key < b.key ? -1 : a.key > b.key ? 1 : 0) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((p) => p.id);

  // Order memory slots ascending; keep only slots with at least one action.
  bed.memory = [...memoryMap.values()]
    .filter((s) => s.goto || s.save)
    .sort((a, b) => a.slot - b.slot);

  return bed;
}

export function isSingleAddressPairedDevice(
  hass: HomeAssistant,
  deviceId: string | undefined,
): boolean {
  if (!deviceId || !hass?.entities) return false;
  return Object.values(hass.entities).some(
    (entry) =>
      entry.device_id === deviceId &&
      entry.platform === PLATFORM &&
      hass.states[entry.entity_id]?.attributes.bed_side === "both",
  );
}

// Child (per-side) device IDs of a paired "Dual Bed" parent, ordered by display
// name (so Left precedes Right). The per-side covers/numbers/sensors live on
// these child devices, linked to the synthetic parent via `via_device_id`; the
// parent itself only carries the combined "both sides" controls. Empty for a
// non-paired (single) device, so the card falls back to single-device rendering.
export function pairedChildDeviceIds(
  hass: HomeAssistant,
  parentId: string | undefined,
): string[] {
  if (!parentId || !hass?.devices) return [];
  const name = (id: string): string => (deviceName(hass, id) ?? id).toLowerCase();
  const sideOrder = (id: string): number => {
    for (const entry of Object.values(hass.entities ?? {})) {
      if (entry.device_id !== id || entry.platform !== "adjustable_bed") continue;
      const side = entitySide(hass, entry.entity_id);
      if (side === "left") return 0;
      if (side === "right") return 1;
    }
    return 2;
  };
  return Object.values(hass.devices)
    .filter((d) => (d.parent_device_id ?? d.via_device_id) === parentId)
    .map((d) => d.id)
    .sort((a, b) => sideOrder(a) - sideOrder(b) || name(a).localeCompare(name(b)));
}

// If `deviceId` is one side (child) of a paired bed, return the synthetic
// parent's id so a card pointed at a side still renders the whole pair (the card
// editor / stub config can easily land on a child device); otherwise return
// `deviceId` unchanged.
export function resolvePairedParentId(
  hass: HomeAssistant,
  deviceId: string | undefined,
): string | undefined {
  if (!deviceId || !hass?.devices) return deviceId;
  const parentId = hass.devices[deviceId]?.parent_device_id ?? hass.devices[deviceId]?.via_device_id;
  // Only resolve to a parent that still exists in the registry (a stale
  // via_device_id would otherwise point at a deleted device).
  if (parentId && hass.devices[parentId] && pairedChildDeviceIds(hass, parentId).length) {
    return parentId;
  }
  return deviceId;
}

// True when the bed exposes nothing the card renders.
export function bedIsEmpty(bed: BedEntities): boolean {
  const l = bed.lights;
  return (
    bed.motors.length === 0 &&
    !bed.synchro &&
    !bed.controlSide &&
    bed.firmness.length === 0 &&
    bed.presets.length === 0 &&
    bed.memory.length === 0 &&
    !bed.stop &&
    !bed.connect &&
    !bed.disconnect &&
    !bed.connectivity &&
    !hasLightingControls(l) &&
    !l.state &&
    bed.massage.buttons.length === 0 &&
    bed.massage.numbers.length === 0 &&
    !bed.massage.selects?.length &&
    !bed.massage.states?.length &&
    !bed.massage.timer &&
    bed.climate.entities.length === 0 &&
    bed.climate.selects.length === 0 &&
    bed.climate.numbers.length === 0 &&
    bed.utility.length === 0 &&
    !bed.utilityNumbers?.length &&
    !bed.utilitySelects?.length &&
    !bed.utilityStates?.length &&
    !bed.savedPositions
  );
}

export function hasLightingControls(lights: LightEntities): boolean {
  return !!(
    lights.light || lights.switch || lights.level || lights.toggle ||
    lights.numbers?.length || lights.buttons?.length || lights.states?.length || lights.cycle || lights.timer || lights.timerMinutes || lights.timerToggle ||
    lights.mood?.toggle || lights.mood?.selects.length || lights.mood?.numbers.length || lights.mood?.buttons?.length
  );
}
