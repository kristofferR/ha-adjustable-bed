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
    typeof startDelayMs !== "number" || !Number.isFinite(startDelayMs) ||
    startDelayMs < 0 || typeof releaseDelayMs !== "number" ||
    !Number.isFinite(releaseDelayMs) || releaseDelayMs < 0
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
  const spec = motor.heldControls?.[direction] ?? motor.heldControl;
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

export interface HoldTimers {
  setTimeout: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimeout: (timer: ReturnType<typeof setTimeout>) => void;
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

interface PendingRelease {
  id: number;
  motorKey: string;
  targetKey: string;
  cover?: string;
  stopEntityId?: string;
  timer?: ReturnType<typeof setTimeout>;
}

export class MotorHold {
  // Ownership is tracked by MotorEntity.key rather than object identity: the
  // first pulse completing updates that entity, which re-renders the card and
  // rebuilds every MotorEntity, so a release handler would otherwise hold a
  // different object for the same motor and never stop the loop.
  private _key: string | null = null;
  private _cover: string | null = null;
  // The stop entity that covers the held motor. Tracked per hold because a
  // paired bed renders one section per side, each with its own stop, so there
  // is no single bed-wide stop to fall back on.
  private _stop: string | null = null;
  // The pointer that owns the hold. Pointer-end events from any other pointer
  // must be ignored: a second touch on the same control would otherwise cancel
  // the primary hold and stop the motor early.
  private _pointerId: number | null = null;
  // Bumping this is what stops an in-flight repeat loop: the loop's next
  // iteration sees a stale value and exits.
  private _generation = 0;
  private _startTimer?: ReturnType<typeof setTimeout>;
  private _started = false;
  private _heldControl?: MotorEntity["heldControl"];
  private _releaseId = 0;
  private readonly _pendingReleases = new Map<number, PendingRelease>();

  constructor(
    private readonly actions: HoldActions,
    private readonly timers: HoldTimers = {
      setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
      clearTimeout: (timer) => globalThis.clearTimeout(timer),
    },
  ) {}

  get heldKey(): string | null {
    return this._key;
  }

  // Begin a hold. `pointerId` is null for keyboard activation, which has no
  // owning pointer. `stopEntityId` is the stop for the bed this motor belongs
  // to. Ignored when another motor already holds.
  start(
    motor: MotorEntity,
    dir: Direction,
    pointerId: number | null,
    stopEntityId?: string,
  ): void {
    if (this._key !== null) return;
    this._key = motor.key;
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._pointerId = pointerId;
    const generation = ++this._generation;
    this._heldControl = motor.heldControls?.[dir] ?? motor.heldControl;
    this._flushPendingForTarget(this._targetKey());
    if (this._heldControl) {
      const delay = this._heldControl.startDelayMs;
      if (delay <= 0) {
        this._startHeldControl(motor, dir, generation);
      } else {
        this._startTimer = this.timers.setTimeout(
          () => this._startHeldControl(motor, dir, generation), delay,
        );
      }
      return;
    }
    this._started = true;
    void this._repeat(motor, dir, generation);
  }

  private _startHeldControl(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): void {
    this._startTimer = undefined;
    if (generation !== this._generation || this._key !== motor.key) return;
    this._started = true;
    void this._holdControl(motor, dir, generation);
  }

  private async _holdControl(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    try {
      const pending = this.actions.holdControl(motor, dir);
      if (pending) await pending;
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
    // train of pulses with a short stop between them. Making it continuous
    // needs a hold-until-released primitive in the integration, which does not
    // exist yet: see issue #483.
    while (generation === this._generation) {
      try {
        const pending = this.actions.pulse(motor, dir);
        if (!pending) return;
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

  private _release(target: Pick<PendingRelease, "cover" | "stopEntityId">): void {
    if (target.cover) this.actions.stopCover(target.cover, target.stopEntityId);
    else this.actions.stopBed(target.stopEntityId);
  }

  private _scheduleRelease(): void {
    const release: PendingRelease = {
      id: ++this._releaseId,
      motorKey: this._key ?? "",
      targetKey: this._targetKey(),
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    this._pendingReleases.set(release.id, release);
    const delay = this._heldControl?.releaseDelayMs ?? 0;
    if (delay <= 0) {
      this._runRelease(release);
      return;
    }
    release.timer = this.timers.setTimeout(() => this._runRelease(release), delay);
  }

  private _runRelease(release: PendingRelease): void {
    if (!this._pendingReleases.delete(release.id)) return;
    if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    this._release(release);
  }

  private _flushPendingForTarget(targetKey: string): Set<string> {
    const released = new Set<string>();
    for (const release of [...this._pendingReleases.values()]) {
      const key = release.targetKey;
      if (key !== targetKey) continue;
      this._runRelease(release);
      released.add(key);
    }
    return released;
  }

  private _flushAllReleases(skipTarget?: string): Set<string> {
    const released = new Set<string>();
    for (const release of [...this._pendingReleases.values()]) {
      const key = release.targetKey;
      if (key === skipTarget) {
        this._pendingReleases.delete(release.id);
        if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
      } else {
        this._runRelease(release);
        released.add(key);
      }
    }
    return released;
  }

  private _discardReleasesForTarget(targetKey: string): void {
    for (const release of [...this._pendingReleases.values()]) {
      if (release.targetKey !== targetKey) continue;
      this._pendingReleases.delete(release.id);
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    }
  }

  private _discardAllReleases(): void {
    for (const release of this._pendingReleases.values()) {
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    }
    this._pendingReleases.clear();
  }

  // A pointer-driven release. Only the pointer that started the hold may end
  // it, and a non-primary button release must not.
  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
  ): void {
    if (this._pointerId !== null && pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    this.end(motor);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity): void {
    if (this._key !== motor.key) return;
    const started = this._started;
    const hasMetadata = this._heldControl !== undefined;
    const releaseTarget = {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    if (started && hasMetadata) this._scheduleRelease();
    this._reset();
    if (!started || hasMetadata) return;
    this._release(releaseTarget);
  }

  // Stop re-issuing pulses for this motor without sending anything to the bed.
  // Returns whether there was a matching hold to cancel.
  cancel(motor: MotorEntity | null, explicitStopFollows = false): boolean {
    if (!motor) return false;
    const matchedActive = this._key === motor.key;
    if (matchedActive) this._reset();
    let matchedRelease = false;
    if (explicitStopFollows) {
      for (const release of [...this._pendingReleases.values()]) {
        if (release.motorKey !== motor.key) continue;
        this._pendingReleases.delete(release.id);
        if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
        matchedRelease = true;
      }
    }
    return matchedActive || matchedRelease;
  }

  // A stop button. Invalidating first matters: otherwise the in-flight pulse
  // resolves after the stop lands and the loop issues another pulse, so the bed
  // starts moving again right after the user asked it to stop. It also has to
  // invalidate *any* hold, not just one motor's, because this stop halts
  // whatever is moving. `stopEntityId` is the pressed button's own stop; it
  // wins over the held motor's, which may belong to a different side.
  stopAll(stopEntityId?: string, stopCoversAllTargets = false): void {
    if (stopEntityId !== undefined) {
      if (stopCoversAllTargets) {
        this._discardAllReleases();
        this._reset();
      } else {
        this._discardReleasesForTarget(stopEntityId);
        if (this._key !== null && this._targetKey() === stopEntityId) this._reset();
      }
      this.actions.stopBed(stopEntityId);
      return;
    }

    const released = this._flushAllReleases(stopEntityId);
    const active = this._key === null ? null : {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    const activeTarget = active
      ? this._targetKey(active.stopEntityId, active.cover)
      : undefined;
    const activeStarted = this._started;
    this._reset();
    if (active && activeStarted && activeTarget !== undefined) {
      this._release(active);
      released.add(activeTarget);
    }
    if (released.size === 0 && (!active || !activeStarted)) {
      this.actions.stopBed(active?.stopEntityId);
    }
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): void {
    const active = this._key === null ? null : {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    const activeStarted = this._started;
    this._reset();
    if (active && activeStarted) this._release(active);
    this._flushAllReleases();
  }

  private _reset(): void {
    if (this._startTimer !== undefined) this.timers.clearTimeout(this._startTimer);
    this._startTimer = undefined;
    this._key = null;
    this._cover = null;
    this._stop = null;
    this._pointerId = null;
    this._started = false;
    this._heldControl = undefined;
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
