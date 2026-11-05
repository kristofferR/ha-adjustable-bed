// Drives the real card state machine for the Python pointer-to-wire test.
import { heldButtonMotor, MotorHold, movementHold, type HoldTimers } from "../hold";
import type { HassEntityAttributes, HomeAssistant } from "../types";

export function pointerTrace(attributes: HassEntityAttributes, releaseAt: number) {
  let now = 0;
  let nextId = 0;
  const pending = new Map<number, { at: number; callback: () => void }>();
  const timers: HoldTimers = {
    setTimeout(callback, delay) {
      const id = ++nextId;
      pending.set(id, { at: now + delay, callback });
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimeout(timer) { pending.delete(timer as unknown as number); },
  };
  function advance(to: number) {
    while (true) {
      const next = [...pending].filter(([, timer]) => timer.at <= to)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      const [id, timer] = next;
      pending.delete(id);
      now = timer.at;
      timer.callback();
    }
    now = to;
  }
  const events: Array<{ at: number; domain: string; service: string; data?: Record<string, unknown> }> = [];
  const hass: HomeAssistant = {
    states: { "button.action": {
      entity_id: "button.action", state: "unknown", attributes, last_changed: "", last_updated: "",
    } },
    devices: {}, locale: { language: "en" }, language: "en", themes: null,
    formatEntityName: (state) => state.entity_id,
    entities: {
      "button.action": { entity_id: "button.action", device_id: "chair", translation_key: "motomotion_action" },
      "button.release": { entity_id: "button.release", device_id: "chair", translation_key: "motomotion_release" },
    },
    callService(domain, service, data) {
      events.push({ at: now, domain, service, data });
      return new Promise(() => {});
    },
  };
  const motor = heldButtonMotor(hass, "button.action");
  if (!motor) throw new Error("Missing admitted hold/release metadata");
  const hold = new MotorHold({
    pulse: () => { throw new Error("Held control must use hold_control"); },
    holdControl: (m, direction) => movementHold(hass, m, direction),
    stopCover: () => { throw new Error("Button hold must retain its release actor"); },
    stopBed: (entityId) => { void hass.callService("button", "press", { entity_id: entityId }); },
  }, timers);
  hold.start(motor, "up", 1, "button.general_stop");
  advance(releaseAt);
  hold.endFromPointer(motor, 1, true, "button.general_stop");
  advance(releaseAt + 1000);
  return events;
}
