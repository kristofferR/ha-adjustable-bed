import { expect, test } from "bun:test";
import controls from "../../../../tests/fixtures/myside/combined_controls.json";
import { bedEntitiesForDevice } from "./discovery";
import { hasHoldLease, MotorHold, movementLease, type HoldTimers } from "./hold";
import type { HomeAssistant } from "./types";

// These attributes are also checked against the real ControllerActionButton.
for (const direction of ["up", "down"] as const) {
  test(`My Side combined ${direction} uses renewable hold_control, with no finite pulse restart`, () => {
    const calls: Array<{ domain: string; service: string; data: Record<string, unknown> }> = [];
    const hass: HomeAssistant = {
      entities: {}, states: {}, devices: {}, locale: { language: "en" },
      language: "en", themes: {},
      callService: (domain, service, data) => {
        calls.push({ domain, service, data: data ?? {} });
        return new Promise<void>(() => {});
      },
    };
    for (const control of Object.values(controls)) {
      hass.entities[control.entity_id] = {
        entity_id: control.entity_id, device_id: "physical-bed", platform: "adjustable_bed",
      };
      hass.states[control.entity_id] = {
        entity_id: control.entity_id, state: "unknown", last_changed: "", last_updated: "",
        attributes: control.attributes,
      };
    }
    const [motor] = bedEntitiesForDevice(hass, "physical-bed").motors;
    expect(motor.key).toBe("head_feet");
    expect(hasHoldLease(motor, direction)).toBe(true);
    expect(motor.heldControls?.[direction]?.control).toBe(`head_and_foot_${direction}`);
    let renew: (() => void) | undefined;
    const delays: number[] = [];
    const timers: HoldTimers = {
      setTimeout: (callback, delay) => {
        renew = callback;
        delays.push(delay);
        return {} as ReturnType<typeof setTimeout>;
      },
      clearTimeout: () => { renew = undefined; },
    };
    let pulses = 0;
    let stops = 0;
    const hold = new MotorHold({
      pulse: () => { pulses++; return Promise.resolve(); },
      lease: (motor, dir, lease) => movementLease(hass, motor, dir, lease),
      stopCover: () => { stops++; },
      stopBed: () => { stops++; },
    }, timers);
    hold.start(motor, direction, null);
    // Nine 250 ms renewals span more than two finite one-second tap windows.
    for (let i = 0; i < 9; i++) {
      const callback = renew;
      expect(callback).toBeDefined();
      callback?.();
    }
    expect(pulses).toBe(0);
    expect(stops).toBe(0);
    expect(calls).toHaveLength(10);
    expect(delays.every((delay) => delay === 250)).toBe(true);
    const owner = calls[0].data.hold_owner;
    const generation = calls[0].data.hold_generation;
    for (const call of calls) {
      expect(call).toEqual({
        domain: "adjustable_bed", service: "hold_control", data: {
          device_id: ["physical-bed"], control: `head_and_foot_${direction}`,
          duration: .75, hold_owner: owner, hold_generation: generation,
        },
      });
    }
    hold.end(motor);
    expect(stops).toBe(1);
    expect(renew).toBeUndefined();
  });
}
