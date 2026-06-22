// Minimal Home Assistant frontend typings used by the card. We avoid pulling in
// custom-card-helpers so the bundle stays small and dependency-light.

export interface HassEntityAttributes {
  friendly_name?: string;
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
  name?: string;
  hidden?: boolean;
  entity_category?: "config" | "diagnostic";
}

export interface DeviceRegistryEntry {
  id: string;
  name?: string;
  name_by_user?: string;
  // Set on a paired side's child device, pointing at the synthetic parent.
  via_device_id?: string | null;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  entities: Record<string, EntityRegistryDisplayEntry>;
  devices: Record<string, DeviceRegistryEntry>;
  locale: { language: string };
  language: string;
  themes: unknown;
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
  show_graphic?: boolean;
  show_motors?: boolean;
  show_firmness?: boolean;
  show_presets?: boolean;
  show_memory?: boolean;
  show_lighting?: boolean;
  show_massage?: boolean;
  show_climate?: boolean;
  show_connection?: boolean;
  // Section render order (keys without the "show_" prefix). Unlisted sections
  // fall back to the default order. Omitted = default order.
  section_order?: string[];
  // Show the "Save…" button in the Memory section (default true).
  memory_save?: boolean;
  // Memory positions (slot numbers) to show. Omitted/empty = show all.
  memory_slots?: number[];
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
export interface MotorEntity {
  key: string;
  cover?: string;
  // Discrete up/down buttons, used by beds that expose buttons instead of covers.
  up?: string;
  down?: string;
  angle?: string; // sensor.* angle in degrees
  position?: string; // number.* position
}

export interface MemorySlot {
  slot: number;
  goto?: string; // button.* preset_memory_N
  save?: string; // button.* program_memory_N
}

export interface LightEntities {
  light?: string; // light.* under_bed_lights (color)
  switch?: string; // switch.* under_bed_lights
  level?: string; // number.* light_level (brightness)
  toggle?: string; // button.* toggle_light
  cycle?: string; // button.* light_cycle
  timer?: string; // select.* light_timer
}

export interface BedEntities {
  motors: MotorEntity[];
  synchro?: string; // switch.* synchro_mode (link split-bed sides)
  firmness: string[]; // number.* sleep_number_setting[_left|_right]
  presets: string[]; // button.* in preferred display order
  stop?: string; // button.* stop
  memory: MemorySlot[];
  connect?: string;
  disconnect?: string;
  connectivity?: string; // binary_sensor.* ble_connection
  presence: string[]; // binary_sensor.* bed_presence*
  lights: LightEntities;
  massage: { buttons: string[]; numbers: string[]; timer?: string };
  climate: { entities: string[]; selects: string[] };
}

// Replaced at build time with the integration version (see build.mjs).
declare const __CARD_VERSION__: string;
export const CARD_VERSION: string =
  typeof __CARD_VERSION__ === "string" ? __CARD_VERSION__ : "dev";
