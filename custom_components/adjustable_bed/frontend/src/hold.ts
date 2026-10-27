// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and service calls, this owns hold ownership,
// timing, and invalidation when a STOP overlaps a held target.
import type { HomeAssistant, HoldTarget, HoldTargetSide, MotorEntity } from "./types";

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

// A refresh-based held control uses the shared bounded service. The service
// owns the controller cadence and release frame; the card starts one maximum
// 60-second window and routes STOP through the held entity's owning device.
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
  // Stops a cover-backed motor through its exact cover entity.
  stopCover: (coverEntityId: string, stopEntityId?: string) => void;
  // Stops the held motor through the exact bed or side Stop entity retained at start.
  stopBed: (stopEntityId?: string) => void;
}

export interface HoldTimers {
  setTimeout: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimeout: (timer: ReturnType<typeof setTimeout>) => void;
}

interface PendingRelease {
  id: number;
  motor: MotorEntity;
  stopEntityId?: string;
  target?: HoldTarget;
  timer?: ReturnType<typeof setTimeout>;
}

interface ReleaseTarget {
  motor: MotorEntity;
  cover?: string;
  stopEntityId?: string;
  target?: HoldTarget;
}

export interface PartialHoldCleanup {
  motor: MotorEntity;
  target: HoldTarget;
  side: Exclude<HoldTargetSide, "both">;
}

export class MotorHold {
  // Ownership uses stable controller keys and typed registry targets, not
  // object identity: HA rebuilds these objects whenever an entity updates.
  private _key: string | null = null;
  private _cover: string | null = null;
  private _stop: string | null = null;
  private _target?: HoldTarget;
  private _motor?: MotorEntity;
  private _heldControl?: MotorEntity["heldControl"];
  private _started = false;
  private _startTimer?: ReturnType<typeof setTimeout>;
  private _pointerId: number | null = null;
  private _generation = 0;
  private _releaseId = 0;
  private readonly _pendingReleases = new Map<number, PendingRelease>();

  constructor(
    private readonly actions: HoldActions,
    public readonly timers: HoldTimers = {
      setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
      clearTimeout: (timer) => globalThis.clearTimeout(timer),
    },
  ) {}

  get heldKey(): string | null {
    return this._key;
  }

  start(
    motor: MotorEntity,
    dir: Direction,
    pointerId: number | null,
    stopEntityId?: string,
    target?: HoldTarget,
  ): void {
    if (this._key !== null) return;
    this._flushPendingForTarget(target, stopEntityId ?? motor.cover ?? motor.key);
    this._key = motor.key;
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._target = target;
    this._motor = motor;
    this._heldControl = motor.heldControl ?? motor.heldControls?.[dir];
    this._pointerId = pointerId;
    const generation = ++this._generation;
    if (this._heldControl) {
      const delay = this._heldControl.startDelayMs;
      if (delay <= 0) {
        this._startHeldControl(motor, dir, generation);
      } else {
        this._startTimer = this.timers.setTimeout(
          () => this._startHeldControl(motor, dir, generation),
          delay,
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
      // Home Assistant reports service errors; allow a later press to retry.
    } finally {
      if (generation === this._generation) this._reset();
    }
  }

  private async _repeat(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    // Await each finite pulse so a STOP invalidates work before another pulse
    // can be queued behind the integration's command lane.
    while (generation === this._generation) {
      try {
        const pending = this.actions.pulse(motor, dir);
        if (!pending) return;
        await pending;
      } catch {
        return;
      }
    }
  }

  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
    target?: HoldTarget,
  ): void {
    if (this._pointerId !== null && pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    this.end(motor, target);
  }

  end(motor: MotorEntity, target?: HoldTarget): void {
    if (!this._owns(motor, target)) return;
    const started = this._started;
    const heldControl = this._heldControl;
    const release = this._captureRelease();
    this._reset();
    if (!started) return;
    if (heldControl) {
      this._scheduleRelease(release, heldControl.releaseDelayMs);
    } else {
      this._release(release);
    }
  }

  cancel(motor: MotorEntity | null, target?: HoldTarget): boolean {
    if (!motor || !this._owns(motor, target)) return false;
    this._reset();
    return true;
  }

  // Invalidate only active and pending work whose real stop scope overlaps this
  // cover. The caller still issues the clicked cover's own stop service.
  stopCover(motor: MotorEntity, target?: HoldTarget): PartialHoldCleanup[] {
    const scope = motor.coverStopScope ?? "motor";
    const cleanup: PartialHoldCleanup[] = [];
    if (
      this._motor && this._key !== null &&
      this._coverStopMatches(this._motor, this._target, motor, target, scope)
    ) {
      const started = this._started;
      const active = this._captureRelease();
      const partial = started
        ? this._partialTargetSide(active.motor, active.target, target)
        : undefined;
      if (partial) cleanup.push(partial);
      this._reset();
    }
    for (const release of [...this._pendingReleases.values()]) {
      if (!this._coverStopMatches(release.motor, release.target, motor, target, scope)) continue;
      const partial = this._partialTargetSide(release.motor, release.target, target);
      if (partial) cleanup.push(partial);
      this._discardRelease(release);
    }
    return cleanup;
  }

  stopAll(stopEntityId?: string, stopTarget?: HoldTarget): PartialHoldCleanup[] {
    if (stopEntityId === undefined) {
      const hadWork = this._key !== null || this._pendingReleases.size > 0;
      this.abandon();
      if (!hadWork) this.actions.stopBed();
      return [];
    }

    const cleanup: PartialHoldCleanup[] = [];
    for (const release of [...this._pendingReleases.values()]) {
      const ownsRetainedStop = release.stopEntityId === stopEntityId;
      if (!ownsRetainedStop && !targetsOverlap(
        release.target,
        stopTarget,
        release.stopEntityId ?? release.motor.cover ?? release.motor.key,
        stopEntityId,
      )) continue;
      const partial = this._partialTargetSide(release.motor, release.target, stopTarget);
      if (partial) cleanup.push(partial);
      this._discardRelease(release);
    }
    const ownsRetainedStop = this._stop === stopEntityId;
    if (
      this._motor && this._key !== null &&
      (ownsRetainedStop || targetsOverlap(
        this._target,
        stopTarget,
        this._stop ?? this._cover ?? this._key,
        stopEntityId,
      ))
    ) {
      const started = this._started;
      const active = this._captureRelease();
      const partial = started
        ? this._partialTargetSide(active.motor, active.target, stopTarget)
        : undefined;
      if (partial) cleanup.push(partial);
      this._reset();
    }
    this.actions.stopBed(stopEntityId);
    return cleanup;
  }

  // A disappearing card must release every callback it still owns. Flush a
  // delayed release now so its timer cannot fire into a newly mounted card.
  abandon(): void {
    for (const release of [...this._pendingReleases.values()]) {
      this._discardRelease(release);
      this._release({
        motor: release.motor,
        cover: release.motor.cover,
        stopEntityId: release.stopEntityId,
        target: release.target,
      });
    }
    if (!this._motor || this._key === null) return;
    const release = this._captureRelease();
    const started = this._started;
    this._reset();
    if (started) this._release(release);
  }

  private _owns(motor: MotorEntity, target?: HoldTarget): boolean {
    if (this._key !== motor.key) return false;
    if (!target || !this._target) return true;
    return this._target.deviceId === target.deviceId && this._target.side === target.side;
  }

  private _captureRelease(): ReleaseTarget {
    return {
      motor: this._motor!,
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
      target: this._target,
    };
  }

  private _coverStopMatches(
    ownedMotor: MotorEntity,
    ownedTarget: HoldTarget | undefined,
    stoppedMotor: MotorEntity,
    stopTarget: HoldTarget | undefined,
    scope: "motor" | "side",
  ): boolean {
    return (scope === "side" || ownedMotor.key === stoppedMotor.key) &&
      targetsOverlap(
        ownedTarget,
        stopTarget,
        ownedMotor.cover ?? ownedMotor.holdEntityId ?? ownedMotor.key,
        stoppedMotor.cover ?? stoppedMotor.key,
      );
  }

  private _partialTargetSide(
    motor: MotorEntity,
    operationTarget: HoldTarget | undefined,
    stopTarget: HoldTarget | undefined,
  ): PartialHoldCleanup | undefined {
    if (
      !operationTarget || !stopTarget ||
      operationTarget.deviceId !== stopTarget.deviceId ||
      operationTarget.side !== "both" ||
      (stopTarget.side !== "left" && stopTarget.side !== "right")
    ) return undefined;
    return {
      motor,
      target: operationTarget,
      side: stopTarget.side === "left" ? "right" : "left",
    };
  }

  private _scheduleRelease(release: ReleaseTarget, delayMs: number): void {
    if (delayMs <= 0) {
      this._release(release);
      return;
    }
    const pending: PendingRelease = {
      id: ++this._releaseId,
      motor: release.motor,
      stopEntityId: release.stopEntityId,
      target: release.target,
    };
    pending.timer = this.timers.setTimeout(() => {
      this._discardRelease(pending);
      this._release(release);
    }, delayMs);
    this._pendingReleases.set(pending.id, pending);
  }

  private _flushPendingForTarget(
    target: HoldTarget | undefined,
    fallbackKey: string,
  ): void {
    for (const release of [...this._pendingReleases.values()]) {
      if (!targetsOverlap(
        release.target,
        target,
        release.stopEntityId ?? release.motor.cover ?? release.motor.key,
        fallbackKey,
      )) continue;
      this._discardRelease(release);
      this._release({
        motor: release.motor,
        cover: release.motor.cover,
        stopEntityId: release.stopEntityId,
        target: release.target,
      });
    }
  }

  private _discardRelease(release: PendingRelease): void {
    this._pendingReleases.delete(release.id);
    if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
  }

  private _release(release: ReleaseTarget): void {
    if (release.cover) {
      this.actions.stopCover(release.cover, release.stopEntityId);
    } else {
      this.actions.stopBed(release.stopEntityId);
    }
  }

  private _reset(): void {
    if (this._startTimer !== undefined) this.timers.clearTimeout(this._startTimer);
    this._key = null;
    this._cover = null;
    this._stop = null;
    this._target = undefined;
    this._motor = undefined;
    this._heldControl = undefined;
    this._started = false;
    this._startTimer = undefined;
    this._pointerId = null;
    this._generation++;
  }
}

function targetsOverlap(
  left: HoldTarget | undefined,
  right: HoldTarget | undefined,
  leftFallback: string,
  rightFallback: string,
): boolean {
  if (!left || !right) return leftFallback === rightFallback;
  if (left.deviceId !== right.deviceId) return false;
  return !left.side || !right.side || left.side === "both" ||
    right.side === "both" || left.side === right.side;
}
