// Unit tests for entity discovery across different bed shapes.
// Run with: bun test
import { expect, test } from "bun:test";
import { bedEntitiesForDevice, bedIsEmpty } from "./discovery";
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

test("empty for unknown device", () => {
  const hass = hassWith([entry("cover.b_back", "back", "dev1")]);
  expect(bedIsEmpty(bedEntitiesForDevice(hass, "nope"))).toBe(true);
});
