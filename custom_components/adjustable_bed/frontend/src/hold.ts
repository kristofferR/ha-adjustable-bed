// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { HomeAssistant, MotorEntity } from "./types";

export type Direction = "up" | "down";

export function movementPulse(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  if (motor.timedMove) {
    // Controller-declared held controls use the same bounded service as paired
    // compatible holds. A missing side keeps the selected entity's normal
    // target; only an explicitly compatible combined pair uses Both.
    return hass?.callService("adjustable_bed", "timed_move", {
      device_id: motor.timedMove.deviceId,
      ...(motor.timedMove.side ? { side: motor.timedMove.side } : {}),
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

export function activateWithoutPointer(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): void {
  // Assistive activation has no pointer/key lifetime, so issue one finite
  // pulse through the same controller-declared bounded service route.
  void movementPulse(hass, motor, direction)?.catch(() => undefined);
}

interface EventListenerTarget {
  addEventListener(type: string, listener: EventListener): void;
  removeEventListener(type: string, listener: EventListener): void;
}

export function registerHoldFocusLoss(
  windowTarget: EventListenerTarget,
  documentTarget: EventListenerTarget,
  isDocumentHidden: () => boolean,
  release: () => void,
): () => void {
  const onWindowBlur: EventListener = () => release();
  const onVisibilityChange: EventListener = () => {
    if (isDocumentHidden()) release();
  };
  windowTarget.addEventListener("blur", onWindowBlur);
  documentTarget.addEventListener("visibilitychange", onVisibilityChange);
  let registered = true;
  return () => {
    if (!registered) return;
    registered = false;
    windowTarget.removeEventListener("blur", onWindowBlur);
    documentTarget.removeEventListener("visibilitychange", onVisibilityChange);
  };
}

export interface HoldActions {
  // Runs one finite movement pulse and resolves when the bed has finished it.
  // Resolving is what paces the repeat loop; rejecting stops it.
  pulse: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  // Stops a cover-backed motor, which is the only kind with its own stop. The
  // bed stop identifies the compact target retained when the hold began.
  stopCover: (coverEntityId: string, stopEntityId?: string) => void;
  // The stop that covers the held motor. Cancels the command in flight.
  // `stopEntityId` is the stop belonging to the bed the motor is on, which on a
  // paired bed is the side's own stop rather than the parent's; omitted falls
  // back to the single bed's stop.
  stopBed: (stopEntityId?: string) => void;
}

export class MotorHold {
  // Ownership is tracked by MotorEntity.key rather than object identity: the
  // first pulse completing updates that entity, which re-renders the card and
  // rebuilds every MotorEntity, so a release handler would otherwise hold a
  // different object for the same motor and never stop the loop.
  private _key: string | null = null;
  private _motor: MotorEntity | null = null;
  private _mode: "cover" | "bed" | null = null;
  private _cover: string | null = null;
  // The stop entity that covers the held motor. Tracked per hold because a
  // paired bed renders one section per side, each with its own stop, so there
  // is no single bed-wide stop to fall back on.
  private _stop: string | null = null;
  // Stop targets overlapped by one held operation. A combined parent operation
  // may include both child stop targets even though it has one public target.
  private _scopeStops: string[] = [];
  // Exact child STOP entities that remain after a side-specific stop cancels a
  // combined operation. They are sent after the in-flight combined call settles.
  private _remainingStops: string[] = [];
  // Monotonic ownership per physical STOP target. Deferred Both cleanup must
  // stay stale even when newer work has already ended before its pulse settles.
  private readonly _stopTargetGenerations = new Map<string, number>();
  // The pointer that owns the hold. Pointer-end events from any other pointer
  // must be ignored: a second touch on the same control would otherwise cancel
  // the primary hold and stop the motor early.
  private _pointerId: number | null = null;
  private _keyboardKey: string | null = null;
  // Bumping this is what stops an in-flight repeat loop: the loop's next
  // iteration sees a stale value and exits.
  private _generation = 0;
  private _pulseInFlight: Promise<unknown> | undefined;

  constructor(private readonly actions: HoldActions) {}

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
    scopeStopEntityIds: readonly string[] = stopEntityId ? [stopEntityId] : [],
    remainingStopEntityIds: readonly string[] = [],
    keyboardKey: string | null = null,
  ): void {
    if (this._key !== null) return;
    this._key = motor.key;
    this._motor = Object.freeze({
      ...motor,
      ...(motor.timedMove ? { timedMove: Object.freeze({ ...motor.timedMove }) } : {}),
    });
    this._mode = motor.cover ? "cover" : "bed";
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    // The exact STOP identity still owns this operation when composite scope
    // metadata disappears during a render.
    this._scopeStops = [...new Set([
      ...scopeStopEntityIds,
      ...(stopEntityId ? [stopEntityId] : []),
      ...(motor.cover ? [motor.cover] : []),
    ])];
    this._remainingStops = [...new Set(remainingStopEntityIds)];
    this.claimStopScope(this._scopeStops);
    this._pointerId = pointerId;
    this._keyboardKey = keyboardKey;
    void this._repeat(motor, dir, ++this._generation);
  }

  // Finite assistive activations also supersede cleanup from an older hold,
  // even though they have no pointer/key lifetime to retain.
  claimStopScope(scopeStopEntityIds: readonly string[]): void {
    for (const target of new Set(scopeStopEntityIds)) {
      this._stopTargetGenerations.set(
        target,
        (this._stopTargetGenerations.get(target) ?? 0) + 1,
      );
    }
  }

  // One iteration moves the bed for a single configured pulse and then stops,
  // for cover-backed motors too: cover.py runs open_cover/close_cover as one
  // finite controller command that performs its own STOP/release cleanup rather
  // than running until stop_cover. So both kinds of motor need re-issuing.
  private async _repeat(
    _motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    const motor = this._motor;
    if (!motor) return;
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
        this._pulseInFlight = pending;
        try {
          await pending;
        } finally {
          if (this._pulseInFlight === pending) this._pulseInFlight = undefined;
        }
      } catch {
        // The bed rejected the command (usually a dropped BLE link). Stop
        // hammering it; the user can press again.
        return;
      }
    }
  }

  // A pointer-driven release. Only the pointer that started the hold may end
  // it, and a non-primary button release must not.
  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
    stopEntityId?: string,
  ): void {
    if (this._pointerId === null || pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    this.end(motor, stopEntityId);
  }

  endActiveFromPointer(pointerId: number, isPrimaryButtonRelease: boolean): void {
    if (!this._motor || this._pointerId === null) return;
    this.endFromPointer(this._motor, pointerId, isPrimaryButtonRelease);
  }

  endKeyboard(
    motor?: MotorEntity,
    stopEntityId?: string,
    keyboardKey?: string,
  ): void {
    if (this._pointerId !== null || !this._motor) return;
    if (motor && motor.key !== this._key) return;
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    if (keyboardKey !== undefined && this._keyboardKey !== null &&
        this._keyboardKey !== keyboardKey) return;
    this.end(this._motor);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity, stopEntityId?: string): void {
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    const mode = this._mode;
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    if (!this.cancel(motor)) return;
    if (mode === "cover" && cover) {
      this.actions.stopCover(cover, stop);
      return;
    }
    // Cancelling the loop does not touch the pulse already in flight, and each
    // pulse is a second or more, so without this the bed keeps moving well
    // after the control is released. The stop cancels the running command,
    // which is also what makes a short tap move the bed briefly rather than
    // for a full pulse.
    this.actions.stopBed(stop);
  }

  // Stop re-issuing pulses for this motor without sending anything to the bed.
  // Returns whether there was a matching hold to cancel.
  cancel(motor: MotorEntity | null): boolean {
    if (!motor || this._key !== motor.key) return false;
    this._reset();
    return true;
  }

  // A stop button. Only an overlapping physical stop scope ends the hold.
  // Independent sides retain their pointer/key owner and later send their own
  // captured STOP. `stopEntityId` remains the exact service target the user
  // pressed, even when it differs from the held motor's target. Motor-specific
  // cover Stops restrict overlap to their axis; side-wide Stops do not.
  stopAll(
    stopEntityId?: string,
    scopeStopEntityIds?: readonly string[],
    motorKey?: string,
  ): void {
    const stop = stopEntityId ?? this._stop ?? undefined;
    const scope = [...new Set([
      ...(scopeStopEntityIds ?? (stop ? [stop] : this._scopeStops)),
      ...(stop ? [stop] : []),
    ])];
    const matchesAxis = motorKey === undefined || motorKey === this._key || stop === this._cover;
    const overlaps = this._key !== null && matchesAxis && (
      scope.length === 0 || this._scopeStops.some((target) => scope.includes(target))
    );
    const remaining = overlaps
      ? this._remainingStops.filter((target) => !scope.includes(target))
      : [];
    const pending = overlaps ? this._pulseInFlight : undefined;
    const remainingGenerations = new Map(
      remaining.map((target) => [
        target,
        this._stopTargetGenerations.get(target) ?? 0,
      ]),
    );
    if (overlaps) this._reset();
    this.actions.stopBed(stop);
    if (remaining.length > 0) {
      const releaseRemaining = (): void => {
        // A deferred Both remainder belongs to the operation that was active
        // when Stop was pressed. A newer hold can start and finish before this
        // pulse settles, so current ownership alone would miss that reuse.
        for (const target of remaining) {
          if (
            this._stopTargetGenerations.get(target) === remainingGenerations.get(target)
          ) {
            this.actions.stopBed(target);
          }
        }
      };
      if (pending) void pending.then(releaseRemaining, releaseRemaining);
      else releaseRemaining();
    }
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): void {
    const wasHolding = this._key !== null;
    const mode = this._mode;
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    this._reset();
    if (!wasHolding) return;
    if (mode === "cover" && cover) this.actions.stopCover(cover, stop);
    else this.actions.stopBed(stop);
  }

  // Browser focus/visibility can be lost without delivering the originating
  // pointer or keyboard release. Keep this on the same exact captured target
  // path as a normal release.
  releaseOnFocusLoss(): void {
    this.abandon();
  }

  // Invalidate only a hold whose physical STOP scope intersects the requested
  // targets. The caller owns issuing the exact stop service for those targets.
  cancelForStopScope(scopeStopEntityIds: readonly string[]): boolean {
    if (
      this._key === null ||
      !this._scopeStops.some((target) => scopeStopEntityIds.includes(target)) &&
      (this._stop === null || !scopeStopEntityIds.includes(this._stop)) &&
      (this._cover === null || !scopeStopEntityIds.includes(this._cover))
    ) return false;
    this._reset();
    return true;
  }

  private _reset(): void {
    this._key = null;
    this._motor = null;
    this._mode = null;
    this._cover = null;
    this._stop = null;
    this._scopeStops = [];
    this._remainingStops = [];
    this._pointerId = null;
    this._keyboardKey = null;
    this._pulseInFlight = undefined;
    this._generation++;
  }
}

export function stopCardMotorHold(
  hold: MotorHold,
  stopEntityId?: string,
  scopeStopEntityIds?: readonly string[],
  motorKey?: string,
): void {
  hold.stopAll(
    stopEntityId,
    scopeStopEntityIds ?? (stopEntityId ? [stopEntityId] : undefined),
    motorKey,
  );
}
