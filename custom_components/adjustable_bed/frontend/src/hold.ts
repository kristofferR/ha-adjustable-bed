// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { HomeAssistant, MotorEntity } from "./types";

export type Direction = "up" | "down";

export function heldButtonMotor(
  hass: HomeAssistant | undefined,
  entityId: string,
): MotorEntity | undefined {
  const deviceId = hass?.entities[entityId]?.device_id;
  const attributes = hass?.states[entityId]?.attributes;
  const control = attributes?.held_control;
  const startDelayMs = attributes?.hold_start_delay_ms;
  const releaseDelayMs = attributes?.hold_release_delay_ms;
  if (
    !deviceId || typeof control !== "string" ||
    typeof startDelayMs !== "number" || typeof releaseDelayMs !== "number"
  ) return undefined;
  return {
    key: entityId,
    up: entityId,
    deviceId,
    holdEntityId: entityId,
    heldControl: { control, startDelayMs, releaseDelayMs },
  };
}

export function movementPulse(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  if (motor.timedMove) {
    // A shared movement window preserves each receiver's cadence without
    // making the faster side wait out its partner's configured finite pulse.
    return hass?.callService("adjustable_bed", "timed_move", {
      device_id: motor.timedMove.deviceId,
      side: "both",
      motor: motor.timedMove.motor,
      direction,
      duration_ms: 1000,
    });
  }
  if (motor.cover) {
    return hass?.callService("cover", direction === "up" ? "open_cover" : "close_cover", {
      entity_id: motor.cover,
    });
  }
  const entityId = direction === "up" ? motor.up : motor.down;
  return entityId ? hass?.callService("button", "press", { entity_id: entityId }) : undefined;
}

// Controller-declared refresh holds use the shared bounded service. The
// release entity remains the owner of STOP and side routing.
export function movementHold(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  const spec = motor.heldControl ?? motor.heldControls?.[direction];
  if (!spec || !motor.deviceId) return undefined;
  const side = hass?.states[motor.holdEntityId ?? motor.cover ?? ""]?.attributes.bed_side;
  const serviceData: Record<string, unknown> = {
    device_id: [motor.deviceId],
    control: spec.control,
    duration: 60,
  };
  if (side === "left" || side === "right" || side === "both") {
    serviceData.side = side;
  }
  return hass?.callService("adjustable_bed", "hold_control", serviceData);
}

export interface HoldActions {
  // Runs one finite movement pulse and resolves when the bed has finished it.
  // Resolving is what paces the repeat loop; rejecting stops it.
  pulse: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  holdControl: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  // Stops a cover-backed motor, which is the only kind with its own stop. The
  // bed stop identifies the compact target retained when the hold began.
  stopCover: (coverEntityId: string, stopEntityId?: string) => void;
  // The stop that covers the held motor. Cancels the command in flight.
  // `stopEntityId` is the stop belonging to the bed the motor is on, which on a
  // paired bed is the side's own stop rather than the parent's; omitted falls
  // back to the single bed's stop.
  stopBed: (stopEntityId?: string) => void;
}

export interface HoldLifecycleTarget {
  addEventListener(
    type: "visibilitychange" | "pagehide",
    listener: () => void,
  ): void;
  removeEventListener(
    type: "visibilitychange" | "pagehide",
    listener: () => void,
  ): void;
}

export type HoldTargetSide = "left" | "right" | "both";

export interface HoldTarget {
  deviceId: string;
  side?: HoldTargetSide;
}

export function holdTargetForEntity(
  hass: HomeAssistant | undefined,
  entityId?: string,
): HoldTarget | undefined {
  if (!hass || !entityId) return undefined;
  const deviceId = hass.entities[entityId]?.device_id;
  if (!deviceId) return undefined;

  const devices = hass.devices ?? {};
  const device = devices[deviceId];
  const declaredSide = hass.states[entityId]?.attributes.bed_side ??
    hass.states[entityId]?.attributes.side;
  const parentId = device?.parent_device_id ?? device?.via_device_id;
  const side: HoldTargetSide | undefined =
    declaredSide === "left" || declaredSide === "right" || declaredSide === "both"
      ? declaredSide
      : Object.values(devices).some((candidate) =>
          (candidate.parent_device_id ?? candidate.via_device_id) === deviceId)
        ? "both"
        : undefined;

  return {
    deviceId: parentId && devices[parentId] ? parentId : deviceId,
    side,
  };
}

// This is the callback used by both Stop buttons rendered by the card. Keep
// target resolution here so the state-machine tests exercise the same path as
// the DOM handlers without needing a browser runtime.
export function stopFromCard(
  hold: MotorHold,
  hass: HomeAssistant | undefined,
  stopEntityId?: string,
): void {
  const target = holdTargetForEntity(hass, stopEntityId);
  hold.stopAll(stopEntityId, target);
}

export class MotorHold {
  // Discovery rebuilds MotorEntity objects. Retain both the logical resource
  // key and its actual control identity across renders and paired panes.
  private _key: string | null = null;
  private _motorId: string | null = null;
  private _cover: string | null = null;
  // The stop entity that covers the held motor. Tracked per hold because a
  // paired bed renders one section per side, each with its own stop, so there
  // is no single bed-wide stop to fall back on.
  private _stop: string | null = null;
  private _target?: HoldTarget;
  // The pointer that owns the hold. Pointer-end events from any other pointer
  // must be ignored: a second touch on the same control would otherwise cancel
  // the primary hold and stop the motor early.
  private _pointerId: number | null = null;
  // Bumping this is what stops an in-flight repeat loop: the loop's next
  // iteration sees a stale value and exits.
  private _generation = 0;
  private _repeatBlocked = false;
  private _direction?: Direction;
  private _started = false;
  private _onStarted?: () => void;
  private _startTimer?: ReturnType<typeof setTimeout>;
  constructor(
    private readonly actions: HoldActions,
    private readonly timers = {
      setTimeout: (callback: () => void, delay: number) => globalThis.setTimeout(callback, delay),
      clearTimeout: (timer: ReturnType<typeof setTimeout>) => globalThis.clearTimeout(timer),
    },
  ) {}

  get heldKey(): string | null {
    return this._key;
  }

  generationFor(motor: MotorEntity, direction: Direction): number | undefined {
    return this._motorId === this._identity(motor) && this._direction === direction
      ? this._generation : undefined;
  }

  // Begin a hold. `pointerId` is null for keyboard activation, which has no
  // owning pointer. `stopEntityId` is the stop for the bed this motor belongs
  // to. Ignored when another motor already holds.
  start(
    motor: MotorEntity,
    dir: Direction,
    pointerId: number | null,
    stopEntityId?: string,
    target?: HoldTarget,
    onStarted?: () => void,
  ): number | undefined {
    if (this._key !== null) return;
    this._key = motor.key;
    this._motorId = this._identity(motor);
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._target = target;
    this._pointerId = pointerId;
    this._direction = dir;
    this._onStarted = onStarted;
    const generation = ++this._generation;
    const spec = motor.heldControl ?? motor.heldControls?.[dir];
    const begin = (): void => {
      this._startTimer = undefined;
      if (generation !== this._generation) return;
      if (spec) void this._holdControl(motor, dir, generation);
      else void this._repeat(motor, dir, generation);
    };
    if (spec && spec.startDelayMs > 0) this._startTimer = this.timers.setTimeout(begin, spec.startDelayMs);
    else begin();
    return generation;
  }

  private _markStarted(generation: number): void {
    if (generation !== this._generation || this._started) return;
    this._started = true;
    const onStarted = this._onStarted;
    this._onStarted = undefined;
    onStarted?.();
  }

  private async _holdControl(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    try {
      const pending = this.actions.holdControl(motor, dir);
      if (pending) {
        this._markStarted(generation);
        await pending;
      }
    } catch {
      // Home Assistant reports service errors; forget the hold so it can retry.
    } finally {
      if (generation === this._generation) this._reset();
    }
  }

  // One iteration moves the bed for a single configured pulse and then stops,
  // for cover-backed motors too: cover.py runs open_cover/close_cover as one
  // finite controller command that performs its own STOP/release cleanup rather
  // than running until stop_cover. So both kinds of motor need re-issuing.
  private async _repeat(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    // Awaiting each call before issuing the next keeps commands from queueing
    // up behind each other, so the integration never has to cancel one
    // mid-flight. It does not make the motion continuous: each backend command
    // is finite and ends with the protocol's release burst, so a hold is a
    // train of pulses with a short stop between them. Only declared held
    // controls use the bounded service; other profiles retain finite pulses.
    while (generation === this._generation && !this._repeatBlocked) {
      try {
        const pending = this.actions.pulse(motor, dir);
        if (!pending) {
          if (generation === this._generation) this._reset();
          return;
        }
        this._markStarted(generation);
        await pending;
      } catch {
        // The bed rejected the command (usually a dropped BLE link). Stop
        // hammering it; the user can press again.
        return;
      }
    }
  }

  private _targetKey(
    stopEntityId = this._stop ?? undefined,
    cover = this._cover ?? undefined,
  ): string {
    return stopEntityId ?? cover ?? this._key ?? "";
  }

  private _identity(motor: MotorEntity): string {
    // Logical motor keys repeat across paired panes. Event ownership belongs
    // to the actual control, including after discovery rebuilds its object.
    return motor.cover ?? motor.holdEntityId ?? motor.up ?? motor.down ?? motor.key;
  }

  private _partialBoth(target: HoldTarget | undefined, stopTarget: HoldTarget | undefined): boolean {
    return target?.side === "both" && target.deviceId === stopTarget?.deviceId &&
      (stopTarget?.side === "left" || stopTarget?.side === "right");
  }

  private _targetsOverlap(
    targetKey: string,
    target: HoldTarget | undefined,
    stopEntityId: string | undefined,
    stopTarget: HoldTarget | undefined,
  ): boolean {
    if (stopEntityId !== undefined && targetKey === stopEntityId) return true;
    if (!target || !stopTarget || target.deviceId !== stopTarget.deviceId) return false;
    return !target.side || !stopTarget.side ||
      target.side === "both" || stopTarget.side === "both" ||
      target.side === stopTarget.side;
  }

  // A pointer-driven release. Only the pointer that started the hold may end
  // it, and a non-primary button release must not.
  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
    generation?: number,
  ): void {
    if (this._pointerId !== null && pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    this.end(motor, generation);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity, generation?: number): void {
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    const started = this._started;
    if (!this.cancel(motor, generation) || !started) return;
    if (cover) this.actions.stopCover(cover, stop);
    else this.actions.stopBed(stop);
  }

  cancel(motor: MotorEntity | null, generation?: number): boolean {
    if (generation !== undefined && generation !== this._generation) return false;
    if (!motor || this._motorId !== this._identity(motor)) return false;
    this._reset();
    return true;
  }

  // A cover STOP owns its motor resource. Held metadata describes cadence,
  // not the scope of stop_fn. The exact clicked service remains the card's job.
  stopCover(motor: MotorEntity, target: HoldTarget | undefined): void {
    if (!motor.cover || this._key === null || !this._targetsOverlap(
      this._targetKey(), this._target, motor.cover, target,
    )) return;
    if (this._partialBoth(this._target, target)) {
      if (!this._started) {
        this._reset();
        return;
      }
      // End Both repetition, retaining the remaining side's cleanup
      // owner until release or abandonment. Do not admit a new card hold yet.
      this._repeatBlocked = true;
    } else if (this._key === motor.key) this._reset();
  }

  // Explicit STOP invalidates only overlapping physical targets. A partial
  // Both stop blocks re-issue but retains release ownership for the other side.
  stopAll(
    stopEntityId?: string,
    stopTarget?: HoldTarget,
  ): void {
    const stop = stopEntityId ?? this._stop ?? undefined;
    if (stopEntityId === undefined) {
      this._reset();
    } else if (this._key !== null && this._targetsOverlap(
      this._targetKey(), this._target, stopEntityId, stopTarget,
    )) {
      if (this._started && this._partialBoth(this._target, stopTarget)) this._repeatBlocked = true;
      else this._reset();
    }
    this.actions.stopBed(stop);
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): void {
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    const wasHolding = this._started;
    this._reset();
    if (!wasHolding) return;
    if (cover) this.actions.stopCover(cover, stop);
    else this.actions.stopBed(stop);
  }

  private _reset(): void {
    if (this._startTimer !== undefined) this.timers.clearTimeout(this._startTimer);
    this._startTimer = undefined;
    this._onStarted = undefined;
    this._started = false;
    this._direction = undefined;
    this._key = null;
    this._motorId = null;
    this._cover = null;
    this._stop = null;
    this._target = undefined;
    this._pointerId = null;
    this._repeatBlocked = false;
    this._generation++;
  }
}

export function attachHoldLifecycle(
  hold: MotorHold,
  documentTarget: HoldLifecycleTarget & { visibilityState: string },
  windowTarget: HoldLifecycleTarget,
): () => void {
  const abandon = (): void => hold.abandon();
  const onVisibilityChange = (): void => {
    if (documentTarget.visibilityState === "hidden") abandon();
  };
  documentTarget.addEventListener("visibilitychange", onVisibilityChange);
  windowTarget.addEventListener("pagehide", abandon);
  return () => {
    documentTarget.removeEventListener("visibilitychange", onVisibilityChange);
    windowTarget.removeEventListener("pagehide", abandon);
  };
}
