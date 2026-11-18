import { expect, test } from "bun:test";
import { bedEntitiesForDevice } from "./discovery";
import { placed } from "./test-placements";
import type { EntityRegistryDisplayEntry, HomeAssistant } from "./types";

for (const route of ["p1", "p2", "p3"]) {
  test(`BetterLiving2 ${route} keeps native controls with their physical child`, () => {
    const keys = [
      "cover:back", "cover:feet", "cover:betterliving2_all_sections",
      "button:betterliving2_program_zero_g",
      ...(route === "p1"
        ? ["number:betterliving2_massage_head"]
        : ["button:betterliving2_massage_timer", "sensor:betterliving2_massage_head"]),
    ];
    const entries: Record<string, EntityRegistryDisplayEntry> = {};
    for (const side of ["left", "right"]) {
      for (const key of keys) {
        const [domain, translationKey] = key.split(":");
        const id = `${domain}.${side}_${translationKey}`;
        entries[id] = {
          entity_id: id, translation_key: translationKey,
          device_id: side, platform: "adjustable_bed",
        };
      }
    }
    const hass: HomeAssistant = placed({
      entities: entries, states: {}, devices: {},
      locale: { language: "en" }, language: "en", themes: {},
      callService: async () => undefined,
    });
    hass.states["cover.left_betterliving2_all_sections"] = {
      entity_id: "cover.left_betterliving2_all_sections", state: "unknown",
      last_changed: "", last_updated: "",
      attributes: {
        held_control_up: "combined_up", held_control_down: "combined_down",
        held_stop_scope: "side", hold_start_delay_ms: 0, hold_release_delay_ms: 0,
      },
    };
    const bed = bedEntitiesForDevice(hass, "left");
    expect(bed.motors.map((motor) => motor.key)).toEqual(["back", "feet", "betterliving2_all_sections"]);
    expect(bed.motors.find((motor) => motor.key === "betterliving2_all_sections")).toMatchObject({
      cover: "cover.left_betterliving2_all_sections", coverStopScope: "side",
      heldControls: {
        up: { control: "combined_up", startDelayMs: 0, releaseDelayMs: 0 },
        down: { control: "combined_down", startDelayMs: 0, releaseDelayMs: 0 },
      },
    });
    expect(bed.utility).toEqual(["button.left_betterliving2_program_zero_g"]);
    expect(bed.utilityStates).toEqual([]);
    if (route === "p1") {
      expect(bed.massage.numbers).toEqual(["number.left_betterliving2_massage_head"]);
      expect(bed.massage.buttons).toEqual([]);
      expect(bed.massage.timer).toBeUndefined();
    } else {
      expect(bed.massage.buttons).toEqual(["button.left_betterliving2_massage_timer"]);
      expect(bed.massage.states).toEqual(["sensor.left_betterliving2_massage_head"]);
    }
    expect(JSON.stringify(bed)).not.toContain("right_");
  });
}
