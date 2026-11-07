import { expect, test } from "bun:test";
import { applyCompactPreset, cardNavigationPath, compactActions,
  compactActionOptions, compactStopEntities, compactTargets, fullCardDialogConfig } from "./compact";
import { bedEntitiesForDevice } from "./discovery";
import type { HomeAssistant } from "./types";

function fixture(): HomeAssistant {
  const hass: HomeAssistant = {
    states: {}, entities: {}, devices: {}, themes: {},
    locale: { language: "en" }, language: "en", callService: async () => undefined,
  };
  for (const [device, keys] of Object.entries({
    pair: ["preset_flat", "preset_memory_1", "program_memory_2", "stop_both"],
    left: ["preset_flat", "preset_memory_1", "preset_tv", "stop"],
    right: ["preset_flat", "preset_memory_1", "stop"],
  })) {
    hass.devices[device] = { id: device, name: device,
      ...(device === "pair" ? {} : { parent_device_id: "pair" }) };
    for (const key of keys) {
      const id = `button.${device}_${key}`;
      hass.entities[id] = { entity_id: id, translation_key: key,
        device_id: device, platform: "adjustable_bed" };
    }
  }
  return hass;
}

test("full-card dialog preserves its bed, target and memory safety settings", () => {
  const config = {type: "custom:adjustable-bed-card", device_id: "bed", default_target: "right", memory_save: false, layout: "compact" as const, open_dialog: true, navigation_path: "/other", show_motors: false, show_lighting: false};
  const full = fullCardDialogConfig(config);
  expect(full.device_id).toBe("bed");
  expect(full.default_target).toBe("right");
  expect(full.memory_save).toBe(false);
  expect(full.layout).toBe("full");
  expect(full.open_dialog).toBe(false);
  expect(full.navigation_path).toBeUndefined();
  expect(full.show_motors).toBe(true);
  expect(full.show_lighting).toBe(true);
  expect(config.show_motors).toBe(false);
});

test("dialog sections are configurable without recursion or changing device identity", () => {
  const full = fullCardDialogConfig({type: "custom:adjustable-bed-card", device_id: "bed", open_dialog: true, show_percentage_graphic: true, show_lumbar_graphic: false, dialog_config: {device_id: "another-bed", type: "another-card", layout: "compact", open_dialog: true, show_motors: false, show_massage: false, show_graphic: false, section_order: ["presets", "memory"]}});
  expect(full.type).toBe("custom:adjustable-bed-card");
  expect(full.device_id).toBe("bed");
  expect(full.layout).toBe("full");
  expect(full.open_dialog).toBe(false);
  expect(full.show_motors).toBe(false);
  expect(full.show_massage).toBe(false);
  expect(full.show_graphic).toBe(false);
  expect(full.show_percentage_graphic).toBe(true);
  expect(full.show_lumbar_graphic).toBe(false);
  expect(full.section_order).toEqual(["presets", "memory"]);
});

test("the dialog shows saved positions and keeps tap to move unless the dialog sets it", () => {
  const config = {type: "custom:adjustable-bed-card", device_id: "bed", layout: "compact" as const,
    open_dialog: true, tap_to_move: true, show_saved_positions: false};
  expect(fullCardDialogConfig(config).show_saved_positions).toBe(true);
  expect(fullCardDialogConfig(config).tap_to_move).toBe(true);
  expect(fullCardDialogConfig({...config, dialog_config: {tap_to_move: false}}).tap_to_move).toBe(false);
});

test("recipes are customizable settings and preserve the configured bed and navigation", () => {
  const config = { type: "custom:adjustable-bed-card", device_id: "pair",
    name: "My bed", navigation_path: "/dashboard/bed", compact_actions: ["preset_tv"] };
  const glance = applyCompactPreset(config, "glance");
  expect(glance.compact_actions).toEqual([]);
  expect(glance.show_motors).toBe(false);
  expect(glance.compact_labels).toBe("names");
  expect(glance.navigation_path).toBe(config.navigation_path);
  expect(glance.device_id).toBe("pair");
  const quick = applyCompactPreset(glance, "quick");
  expect(quick.compact_actions).toBeUndefined();
  expect(quick.show_motors).toBe(false);
  expect(quick.compact_labels).toBe("angles");
  expect(applyCompactPreset(quick, "controls").show_motors).toBe(true);
  expect(config.compact_actions).toEqual(["preset_tv"]);
});

test("favourites resolve only within the selected side, in user order, never save-only memory", () => {
  const hass = fixture();
  const left = bedEntitiesForDevice(hass, "left");
  const right = bedEntitiesForDevice(hass, "right");
  const selection = ["preset_tv", "preset_memory_1", "preset_flat", "preset_flat"];
  expect(compactActions(hass, left, selection).map((a) => a.entityId)).toEqual([
    "button.left_preset_tv", "button.left_preset_memory_1", "button.left_preset_flat",
  ]);
  expect(compactActions(hass, right, selection).map((a) => a.entityId)).toEqual([
    "button.right_preset_memory_1", "button.right_preset_flat",
  ]);
  const both = bedEntitiesForDevice(hass, "pair");
  expect(compactActions(hass, both).map((a) => a.key)).toEqual(["preset_flat", "preset_memory_1"]);
  expect(compactActionOptions(hass, both).some((a) => a.key === "program_memory_2")).toBe(false);
  expect(compactActions(hass, both, [])).toEqual([]);
});

test("native pair targets preserve device identity when names reorder and when selecting a child", () => {
  const hass = fixture();
  expect(compactTargets(hass, "left").map((t) => t.key).sort()).toEqual(["both", "left", "right"]);
  hass.devices.left.name_by_user = "Z side";
  hass.devices.right.name_by_user = "A side";
  const targets = compactTargets(hass, "pair");
  expect(targets.find((t) => t.key === "left")?.bed.stop).toBe("button.left_stop");
  expect(targets.find((t) => t.key === "right")?.bed.stop).toBe("button.right_stop");
});

test("one-address pairs resolve scoped favourites by their shared key", () => {
  const hass = fixture();
  hass.devices = { pair: { id: "pair" } };
  hass.entities = {};
  for (const side of ["both", "left", "right"] as const) {
    for (const key of ["preset_flat", "preset_memory_1", "stop"]) {
      const entity_id = `button.${key}_${side}`;
      hass.entities[entity_id] = { entity_id, platform: "adjustable_bed",
        device_id: "pair", translation_key: key === "stop" && side === "both" ? "stop_both" : key };
      hass.states[entity_id] = { entity_id, state: "unknown", attributes: { bed_side: side },
        last_changed: "", last_updated: "" };
    }
  }
  const targets = compactTargets(hass, "pair");
  expect(targets.map((t) => t.key)).toEqual(["both", "left", "right"]);
  for (const target of targets) {
    expect(compactActions(hass, target.bed, ["preset_flat"])[0]?.entityId)
      .toBe(`button.preset_flat_${target.key}`);
    expect(compactStopEntities(target.bed)).toEqual([`button.stop_${target.key}`]);
  }
});

test("STOP uses native stop when present, otherwise each controllable cover", () => {
  const bed = bedEntitiesForDevice(fixture(), "left");
  bed.motors = [{ key: "back", cover: "cover.back" }, { key: "legs", cover: "cover.legs" }];
  expect(compactStopEntities(bed)).toEqual(["button.left_stop"]);
  bed.stop = undefined;
  expect(compactStopEntities(bed)).toEqual(["cover.back", "cover.legs"]);
});

test("navigation stays on the current Home Assistant origin", () => {
  expect(cardNavigationPath("/dashboard/bed?view=compact#top")).toBe("/dashboard/bed?view=compact#top");
  for (const path of [undefined, "", "https://example.com", "//example.com", "/\\example.com", "/\n/example.com", "javascript:alert(1)"])
    expect(cardNavigationPath(path)).toBeUndefined();
});
