// Minimal Home Assistant frontend typings used by the card. We avoid pulling in
// custom-card-helpers so the bundle stays small and dependency-light.

export interface HassEntityAttributes {
  icon?: string;
  current_position?: number;
  rgb_color?: [number, number, number];
  [key: string]: unknown;
}

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: HassEntityAttributes;
  last_changed: string;
  last_updated: string;
}

// Lightweight entity-registry entry exposed to the frontend (hass.entities).
export interface EntityRegistryDisplayEntry {
  entity_id: string;
  device_id?: string;
  area_id?: string;
  platform?: string;
  translation_key?: string;
  // The entity's own name, without its device's name.
  name?: string;
  hidden?: boolean;
  entity_category?: "config" | "diagnostic";
}

export interface DeviceRegistryEntry {
  id: string;
  name?: string | null;
  name_by_user?: string | null;
  // Set on a paired side's child device, pointing at the synthetic parent.
  parent_device_id?: string | null;
  via_device_id?: string | null;
}

export type BedSide = "left" | "right" | "both";

// One part of a composed entity name (see hass.formatEntityName).
export type EntityNameItem =
  | { type: "floor" | "area" | "parent_device" | "device" | "entity" }
  | { type: "text"; text: string };

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  entities: Record<string, EntityRegistryDisplayEntry>;
  devices: Record<string, DeviceRegistryEntry>;
  locale: { language: string };
  language: string;
  themes: unknown;
  formatEntityName(
    stateObj: HassEntity,
    name?: string | EntityNameItem | EntityNameItem[],
    options?: { separator?: string },
  ): string;
  callService: (
    domain: string,
    service: string,
    serviceData?: Record<string, unknown>,
    target?: Record<string, unknown>,
  ) => Promise<unknown>;
}

export interface AdjustableBedCardConfig {
  type: string;
  device_id?: string;
  name?: string;
  layout?: "full" | "compact";
  show_header?: boolean;
  compact_labels?: "angles" | "names" | "none";
  show_side_selector?: boolean;
  // "both", a native child device ID, or "left"/"right" for one-address pairs.
  default_target?: string;
  // Stable preset translation keys; omitted = flat + first recall, [] = none.
  compact_actions?: string[];
  navigation_path?: string;
  animate?: boolean;
  show_graphic?: boolean;
  show_motors?: boolean;
  show_firmness?: boolean;
  show_presets?: boolean;
  show_saved_positions?: boolean;
  show_memory?: boolean;
  show_lighting?: boolean;
  show_massage?: boolean;
  show_utility?: boolean;
  show_climate?: boolean;
  show_connection?: boolean;
  // Section render order (keys without the "show_" prefix). Unlisted sections
  // fall back to the default order. Omitted = default order.
  section_order?: string[];
  // Show the "Save…" button in the Memory section (default true).
  memory_save?: boolean;
  // Memory positions (slot numbers) to show. Omitted/empty = show all.
  memory_slots?: number[];
  // A tap on a motor arrow starts it and the next tap stops it (default false).
  tap_to_move?: boolean;
}

export interface LovelaceCard extends HTMLElement {
  hass?: HomeAssistant;
  setConfig(config: AdjustableBedCardConfig): void;
  getCardSize(): number | Promise<number>;
}

export interface LovelaceCardEditor extends HTMLElement {
  hass?: HomeAssistant;
  setConfig(config: AdjustableBedCardConfig): void;
}

// One controllable motor and its related feedback entities.
export interface HeldControl {
  control: string;
  startDelayMs: number;
  releaseDelayMs: number;
}

// A renewable hold (#483) the controller declares. `motor` names the
// timed_move axis for a motor without a held control or timed route of its own.
export interface HoldLeaseRoute {
  deviceId: string;
  motor?: string;
  side?: BedSide;
}

export interface MotorEntity {
  key: string;
  cover?: string;
  coverStopScope?: "motor" | "side";
  deviceId?: string;
  heldControls?: Partial<Record<"up" | "down", HeldControl>>;
  heldControl?: HeldControl;
  holdEntityId?: string;
  releaseButton?: string;
  // Discrete up/down buttons, used by beds that expose buttons instead of covers.
  up?: string;
  down?: string;
  // Existing bounded movement route for controller-declared held controls.
  timedMove?: {
    deviceId: string;
    motor: "back" | "legs" | "lumbar";
    side?: BedSide;
  };
  holdLease?: HoldLeaseRoute;
  angle?: string; // sensor.* angle in degrees
  position?: string; // number.* position
  estimate?: string; // number.* <motor>_position_estimated (travel-time estimate)
  reference?: string; // button.* set_<motor>_reference
}

export interface MemorySlot {
  slot: number;
  goto?: string; // button.* preset_memory_N
  save?: string; // button.* program_memory_N
}

export interface LightEntities {
  buttons?: string[];
  light?: string; // light.* under_bed_lights (color)
  switch?: string; // switch.* under_bed_lights
  state?: string; // binary_sensor.* under_bed_lights (read-only)
  states?: string[]; // read-only light telemetry
  level?: string; // number.* light_level (brightness)
  numbers?: string[]; // app-scoped light values without color or brightness semantics
  toggle?: string; // button.* toggle_light
  cycle?: string; // button.* light_cycle
  timer?: string; // select.* light_timer, or number.* timeout applied on release
  timerMinutes?: string; // number.* pending floor timer duration
  timerToggle?: string; // button.* enable/disable the pending floor timer
  timerAppliesImmediately?: boolean;
  mood?: {
    selects: string[]; // bounded palette and effect choices
    numbers: string[]; // effect speed, without an arbitrary RGB/brightness control
    toggle?: string;
    buttons?: string[];
  };
}

export interface BedEntities {
  motors: MotorEntity[];
  synchro?: string; // switch.* synchro_mode (link split-bed sides)
  controlSide?: string; // select.* choosing which side shared controls drive
  firmness: string[]; // number.* sleep_number_setting[_left|_right]
  presets: string[]; // button.* in preferred display order
  stop?: string; // button.* stop
  memory: MemorySlot[];
  connect?: string;
  disconnect?: string;
  connectivity?: string; // binary_sensor.* ble_connection
  presence: string[]; // binary_sensor.* bed_presence*
  lights: LightEntities;
  massage: { buttons: string[]; numbers: string[]; selects?: string[]; states?: string[]; timer?: string };
  climate: { entities: string[]; selects: string[]; numbers: string[] }; // numbers: fan_level
  utility: string[]; // button.* sync_positions / child_lock_toggle
  utilityNumbers?: string[]; // controller-declared number controls without a card section
  utilitySelects?: string[]; // select.* active app/module surface
  utilityStates?: string[]; // read-only app/device state
  estimateRemote?: string; // button.* estimate_remote_used
  savedPositions?: string; // sensor.* saved_positions (whole bed)
}

// Replaced at build time with the integration version (see build.mjs).
declare const __CARD_VERSION__: string;
export const CARD_VERSION: string =
  typeof __CARD_VERSION__ === "string" ? __CARD_VERSION__ : "dev";
