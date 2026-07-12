// Unit tests for entity discovery across different bed shapes.
// Run with: bun test
import { expect, test } from "bun:test";
import {
  bedEntitiesForDevice,
  bedIsEmpty,
  isSingleAddressPairedDevice,
  pairedChildDeviceIds,
  resolvePairedParentId,
} from "./discovery";
import type { EntityRegistryDisplayEntry, HomeAssistant } from "./types";

function entry(
  entity_id: string,
  translation_key: string,
  device_id = "dev1",
  platform = "adjustable_bed",
): EntityRegistryDisplayEntry {
  return { entity_id, translation_key, device_id, platform };
}

function hassWith(entries: EntityRegistryDisplayEntry[]): HomeAssistant {
  const entities: Record<string, EntityRegistryDisplayEntry> = {};
  for (const e of entries) entities[e.entity_id] = e;
  return {
    entities,
    states: {},
    devices: {},
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: async () => undefined,
  };
}

test("2-motor bed with light switch and no massage/climate", () => {
  const hass = hassWith([
    entry("cover.seng_back", "back"),
    entry("cover.seng_legs", "legs"),
    entry("sensor.seng_back_angle", "back_angle"),
    entry("sensor.seng_legs_angle", "legs_angle"),
    entry("button.seng_flat", "preset_flat"),
    entry("button.seng_zero_g", "preset_zero_g"),
    entry("button.seng_save_1", "program_memory_1"),
    entry("button.seng_stop", "stop"),
    entry("button.seng_connect", "connect"),
    entry("button.seng_disconnect", "disconnect"),
    entry("switch.seng_under_bed_lights", "under_bed_lights"),
    entry("binary_sensor.seng_ble", "ble_connection"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");

  expect(bed.motors.map((m) => m.key)).toEqual(["back", "legs"]);
  expect(bed.motors[0].cover).toBe("cover.seng_back");
  expect(bed.motors[0].angle).toBe("sensor.seng_back_angle");
  expect(bed.presets).toEqual(["button.seng_flat", "button.seng_zero_g"]);
  expect(bed.stop).toBe("button.seng_stop");
  expect(bed.connect).toBe("button.seng_connect");
  expect(bed.disconnect).toBe("button.seng_disconnect");
  expect(bed.lights.switch).toBe("switch.seng_under_bed_lights");
  expect(bed.lights.light).toBeUndefined();
  expect(bed.connectivity).toBe("binary_sensor.seng_ble");
  expect(bed.massage.buttons).toHaveLength(0);
  expect(bed.climate.entities).toHaveLength(0);
  expect(bed.memory).toEqual([{ slot: 1, save: "button.seng_save_1" }]);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("paired parent's stop_both maps to the stop slot", () => {
  const hass = hassWith([entry("button.master_bed_stop_both", "stop_both")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.stop).toBe("button.master_bed_stop_both");
});

test("single-address paired entities split by bed_side on one device", () => {
  const hass = hassWith([
    entry("cover.b_back_left", "back"),
    entry("cover.b_back_right", "back"),
    entry("button.b_flat_both", "preset_flat"),
  ]);
  const sideState = (entity_id: string, bed_side: "left" | "right" | "both") => {
    hass.states[entity_id] = {
      entity_id,
      state: "unknown",
      attributes: { bed_side },
      last_changed: "",
      last_updated: "",
    };
  };
  sideState("cover.b_back_left", "left");
  sideState("cover.b_back_right", "right");
  sideState("button.b_flat_both", "both");

  expect(isSingleAddressPairedDevice(hass, "dev1")).toBe(true);
  expect(bedEntitiesForDevice(hass, "dev1", "left").motors[0].cover).toBe(
    "cover.b_back_left",
  );
  expect(bedEntitiesForDevice(hass, "dev1", "right").motors[0].cover).toBe(
    "cover.b_back_right",
  );
  expect(bedEntitiesForDevice(hass, "dev1", "both").presets).toEqual([
    "button.b_flat_both",
  ]);
});

test("side-suffixed translation keys remain a supported fallback", () => {
  const hass = hassWith([
    entry("button.b_head_up_left", "head_up_left"),
    entry("button.b_head_up_right", "head_up_right"),
    entry("button.b_stop_both", "stop_both"),
  ]);

  expect(bedEntitiesForDevice(hass, "dev1", "left").motors[0].up).toBe(
    "button.b_head_up_left",
  );
  expect(bedEntitiesForDevice(hass, "dev1", "right").motors[0].up).toBe(
    "button.b_head_up_right",
  );
  expect(isSingleAddressPairedDevice(hass, "dev1")).toBe(true);
});

test("Okin utility buttons (sync / child lock) bucket into utility", () => {
  const hass = hassWith([
    entry("cover.seng_back", "back"),
    entry("button.seng_sync", "sync_positions"),
    entry("button.seng_lock", "child_lock_toggle"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");

  expect(bed.utility).toEqual(["button.seng_sync", "button.seng_lock"]);
  // Utility buttons must not leak into presets or massage.
  expect(bed.presets).toHaveLength(0);
  expect(bed.massage.buttons).toHaveLength(0);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("bed with only utility buttons is not empty", () => {
  const hass = hassWith([entry("button.b_sync", "sync_positions")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.utility).toEqual(["button.b_sync"]);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("memory asymmetry: goto for some slots, save for all", () => {
  const hass = hassWith([
    entry("button.b_save1", "program_memory_1"),
    entry("button.b_save2", "program_memory_2"),
    entry("button.b_goto3", "preset_memory_3"),
    entry("button.b_save3", "program_memory_3"),
    entry("button.b_goto4", "preset_memory_4"),
    entry("button.b_save4", "program_memory_4"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.memory).toEqual([
    { slot: 1, save: "button.b_save1" },
    { slot: 2, save: "button.b_save2" },
    { slot: 3, goto: "button.b_goto3", save: "button.b_save3" },
    { slot: 4, goto: "button.b_goto4", save: "button.b_save4" },
  ]);
});

test("4-motor bed with massage, climate, and colour light", () => {
  const hass = hassWith([
    entry("cover.b_back", "back"),
    entry("cover.b_legs", "legs"),
    entry("cover.b_head", "head"),
    entry("cover.b_feet", "feet"),
    entry("button.b_mhead", "massage_head_toggle"),
    entry("button.b_mfoot", "massage_foot_toggle"),
    entry("number.b_mhi", "massage_head_intensity"),
    entry("select.b_mtimer", "massage_timer"),
    entry("climate.b_thermal", "sleep_number_thermal_climate"),
    entry("select.b_ttimer", "thermal_timer"),
    entry("light.b_light", "under_bed_lights"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");

  expect(bed.motors.map((m) => m.key)).toEqual(["back", "legs", "head", "feet"]);
  expect(bed.massage.buttons).toHaveLength(2);
  expect(bed.massage.numbers).toEqual(["number.b_mhi"]);
  expect(bed.massage.timer).toBe("select.b_mtimer");
  expect(bed.climate.entities).toEqual(["climate.b_thermal"]);
  expect(bed.climate.selects).toEqual(["select.b_ttimer"]);
  expect(bed.lights.light).toBe("light.b_light");
  expect(bed.lights.switch).toBeUndefined();
});

test("discrete up/down motor buttons without covers", () => {
  const hass = hassWith([
    entry("button.b_head_up", "head_up"),
    entry("button.b_head_down", "head_down"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.motors).toHaveLength(1);
  expect(bed.motors[0]).toMatchObject({
    key: "head",
    up: "button.b_head_up",
    down: "button.b_head_down",
  });
});

test("filters out other devices and platforms", () => {
  const hass = hassWith([
    entry("cover.mine_back", "back", "dev1"),
    entry("cover.other_back", "back", "dev2"),
    entry("cover.alien_back", "back", "dev1", "some_other_platform"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.motors).toHaveLength(1);
  expect(bed.motors[0].cover).toBe("cover.mine_back");
});

test("buckets light level, light timer, and firmness numbers", () => {
  const hass = hassWith([
    entry("number.b_light", "light_level"),
    entry("select.b_ltimer", "light_timer"),
    entry("number.b_firm", "sleep_number_setting"),
    entry("number.b_firm_l", "sleep_number_setting_left"),
  ]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.lights.level).toBe("number.b_light");
  expect(bed.lights.timer).toBe("select.b_ltimer");
  expect(bed.firmness).toEqual(["number.b_firm", "number.b_firm_l"]);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("position-only motor (number, no cover) is discovered", () => {
  const hass = hassWith([entry("number.b_back_pos", "back_position")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.motors).toHaveLength(1);
  expect(bed.motors[0]).toMatchObject({
    key: "back",
    position: "number.b_back_pos",
  });
  expect(bedIsEmpty(bed)).toBe(false);
});

test("synchro switch is bucketed and not empty", () => {
  const hass = hassWith([entry("switch.b_sync", "synchro_mode")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.synchro).toBe("switch.b_sync");
  expect(bed.lights.switch).toBeUndefined();
  expect(bedIsEmpty(bed)).toBe(false);
});

test("timer-only massage is not empty", () => {
  const hass = hassWith([entry("select.b_mtimer", "massage_timer")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.massage.timer).toBe("select.b_mtimer");
  expect(bed.massage.buttons).toHaveLength(0);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("not empty when only climate select controls exist", () => {
  const hass = hassWith([entry("select.b_thermal_timer", "thermal_timer")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.climate.selects).toEqual(["select.b_thermal_timer"]);
  expect(bedIsEmpty(bed)).toBe(false);
});

test("presence-only device is treated as empty (no presence section)", () => {
  const hass = hassWith([entry("binary_sensor.b_pres", "bed_presence")]);
  const bed = bedEntitiesForDevice(hass, "dev1");
  expect(bed.presence).toEqual(["binary_sensor.b_pres"]);
  expect(bedIsEmpty(bed)).toBe(true);
});

test("empty for unknown device", () => {
  const hass = hassWith([entry("cover.b_back", "back", "dev1")]);
  expect(bedIsEmpty(bedEntitiesForDevice(hass, "nope"))).toBe(true);
});

test("pairedChildDeviceIds returns sided children ordered by name", () => {
  const hass = hassWith([]);
  hass.devices = {
    parent: { id: "parent", name: "Master Bed" },
    right: { id: "right", name: "Master Bed Right", via_device_id: "parent" },
    left: { id: "left", name: "Master Bed Left", via_device_id: "parent" },
    other: { id: "other", name: "Unrelated" },
  };
  // Both sides, ordered Left before Right; unrelated devices excluded.
  expect(pairedChildDeviceIds(hass, "parent")).toEqual(["left", "right"]);
  // A single (non-parent) device has no children -> single-device rendering.
  expect(pairedChildDeviceIds(hass, "left")).toEqual([]);
  expect(pairedChildDeviceIds(hass, undefined)).toEqual([]);
});

test("resolvePairedParentId resolves a side device up to its parent", () => {
  const hass = hassWith([]);
  hass.devices = {
    parent: { id: "parent", name: "Master Bed" },
    left: { id: "left", name: "Master Bed Left", via_device_id: "parent" },
    right: { id: "right", name: "Master Bed Right", via_device_id: "parent" },
    single: { id: "single", name: "Guest Bed" },
    stale: { id: "stale", name: "Orphan", via_device_id: "ghost" },
  };
  // A side device resolves to the parent; the parent and a single device stay.
  expect(resolvePairedParentId(hass, "left")).toBe("parent");
  expect(resolvePairedParentId(hass, "parent")).toBe("parent");
  expect(resolvePairedParentId(hass, "single")).toBe("single");
  expect(resolvePairedParentId(hass, undefined)).toBeUndefined();
  // A stale via_device_id (parent gone from the registry) stays on the device.
  expect(resolvePairedParentId(hass, "stale")).toBe("stale");
});
