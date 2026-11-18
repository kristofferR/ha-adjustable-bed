// This app-only fixture is checked against actual Python entity metadata by pytest.
import { expect, test } from "bun:test";
import metadata from "../../../../tests/fixtures/okimiki/card_metadata.json";
import { bedEntitiesForDevice } from "./discovery";
import { heldReleaseButton, movementLease } from "./hold";
import type { HomeAssistant } from "./types";

test("Okimiki native metadata resolves the held route and its physical release", async () => {
  const calls: Array<{ domain: string; service: string; data: unknown }> = [];
  const hass = {
    entities: Object.fromEntries(metadata.map(({ entity_id, translation_key }) => [entity_id, {
      entity_id, translation_key, device_id: "okimiki", platform: "adjustable_bed",
    }])),
    states: Object.fromEntries(metadata.map(({ entity_id, attributes }) => [entity_id, {
      entity_id, attributes, state: "unknown", last_changed: "", last_updated: "",
    }])),
    devices: {},
    callService: async (domain: string, service: string, data: unknown) => {
      calls.push({ domain, service, data });
    },
  } as HomeAssistant;
  const [motor] = bedEntitiesForDevice(hass, "okimiki").motors;
  expect(motor.heldControls?.up.control).toBe("okimiki_head_up");
  expect(motor.releaseButton).toBe("button.okimiki_release");
  expect(heldReleaseButton(hass, motor.cover!)).toBe(motor.releaseButton);
  await movementLease(hass, motor, "up", { owner: "card", generation: 1 });
  await hass.callService("button", "press", { entity_id: motor.releaseButton });
  expect(calls).toEqual([
    {
      domain: "adjustable_bed", service: "hold_control",
      data: {
        device_id: ["okimiki"], control: "okimiki_head_up", duration: 0.75,
        hold_owner: "card", hold_generation: 1,
      },
    },
    { domain: "button", service: "press", data: { entity_id: "button.okimiki_release" } },
  ]);
});
