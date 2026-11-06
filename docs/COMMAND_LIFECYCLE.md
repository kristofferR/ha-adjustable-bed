# Rapid control and connection ownership

The September 2026 Linak investigation exercised both physical sides and the
combined HA controls. Its baseline failed five of twelve services; the final
Linak build completed 217 actions without service errors. That build released
both links about 1.1 seconds after STOP and stayed disconnected throughout a
three-minute idle watch. These measurements belong to the Linak build at
`ccdccb8d`; they are not hardware validation of other controllers.

The shared changes below apply those observations to integration-owned behavior.
They do not change protocol bytes, authentication handshakes, repeat cadence,
notification requirements, or preset semantics of other beds.

| Observation | Shared behavior | Validation |
| --- | --- | --- |
| Reconnecting between taps repeatedly pays startup cost | One-second renewable handoff when Disconnect After Command is enabled | Consecutive commands reuse the link, then the idle lane releases it; explicit disconnect remains immediate |
| One side finishes while its partner is still running | Concurrent groups hold both links through completion and failure/STOP cleanup, then start their configured idle timeout together | Nested connection holds and paired success/failure cleanup |
| Background work takes back the remote's link | Quick handoff disables periodic reconciliation; a queued light refresh rechecks whether the live link still needs hydration | No connection attempt after a queued refresh loses its link |
| Missing initial feedback keeps the connection reserved for retries | Quick handoff permits one initial position/light-state read attempt; longer hydration retries remain available when quick disconnect is off | Missing-feedback tests read once and arm the short handoff timer |
| Reads delay STOP | Final and background position reads are preemptible; queued user commands skip redundant final reads | A blocked read releases the wire before STOP, without consuming its three-second timeout |
| Cancellation races with a write or an error | Shared writes recheck cancellation after acquiring the GATT lock; simultaneous cancellation does not hide operation failure | Cancelled queued write sends nothing and cannot invoke the successful-write callback; fresh release events still write |
| Shared movement helpers silently discard a failed release | Base movement/preset helpers propagate cleanup failures, retaining the original movement exception as context | Successful, failed, and cancelled movement all report a failed STOP |
| A nominal duration grows with every write acknowledgement | Timed Move bounds elapsed controller movement, then waits for existing release cleanup | Slow writes, transport timeout, deadline expiry, external cancellation, and failed cleanup |
| Strongest proxy repeatedly fails before another route is chosen | Multiple usable paths receive at least five attempts with capped backoff | Non-Linak and Linak fallback succeeds on a later attempt; single-path and exhausted cases remain bounded |

## Boundaries

- Persistent-connection controllers keep their existing connection requirement.
  An idle timeout of `0` gives any bed the same lifecycle while Disconnect After
  Command is off: no idle timer, and a dropped link reconnects on demand.
  Sequential pairs still explicitly disconnect before switching sides; a group
  hold never overrides explicit disconnect.
- The scheduler continues to serialize opaque controller operations. Same-resource
  movements can replace one another, unrelated resources queue, and STOP invalidates
  accepted movement. Non-idempotent operations are not automatically replayed after
  a transport error.
- A seek completes the controller's position-read preparation before starting
  its initial feedback timeout. Preparation remains preemptible by STOP and
  replacement; stale feedback is never substituted for a failed read.
- A timed service starts its movement budget after connection and the controller's
  movement preparation. Linak uses its existing readiness handshake here so a
  cold connection cannot consume the entire movement allowance without moving.
  Other setup inside a controller's movement still consumes the budget.
  STOP and controller cleanup can extend the total service time. Reaching the
  ceiling is normal; a real transport or cleanup timeout is an error.
- Linak's readiness window, acknowledged readiness probe, deferred capability
  discovery, subscription recovery, and default preset ceiling remain specific to
  its controller. Other protocols need their own accepted artifact evidence before
  those details can change. Existing per-controller schedules are not inferred
  from Linak or shortened globally.
- Unit and integration tests exercise other controllers through simulated BLE.
  Only the owner's Linak hardware is available for physical testing. Field reports
  should distinguish service outcomes, actual movement, cleanup latency, and idle
  reconnections, rather than treating an accepted service as proof of movement.

## Card hold ownership

Held controls keep the existing flat entity attributes: button `held_control`,
cover `held_control_up` / `held_control_down`, and the two delay fields.
Cover `held_stop_scope` explicitly distinguishes a whole-side STOP from a
motor-specific STOP; timing metadata alone does not imply either scope.
Combined hold metadata is exposed only while both current receivers have matching
contracts and concurrent execution is available. A declared-hold combined button
still uses a finite timed operation when that metadata is absent, including
sequential mode. Sleepy's retains its native action duration; other declared
holds retain the one-second card pulse. Each receiver keeps its own controller
cleanup. Sleepy's app delay fields govern card gestures, not additional delays
around the controller's finite service action.

Window blur and hidden-document transitions release the captured hold target.
An unrelated side's STOP leaves the other side's hold owner intact. Exact STOP
and cover identities remain owned even if composite scope metadata disappears;
a newer hold or assistive activation supersedes older deferred cleanup.
Keyboard release matches the original activation key and STOP target.

Registered hold/timed and Reverie comfort, routine, and diagnostic operations
capture physical STOP epochs and pair resource generations before preflight.
A STOP on a later target also invalidates its pending dispatch while an earlier
target is still starting. Paired admission rechecks ownership after lane waits,
before reservations can cancel newer work, and before committing movement.

## Useful regression scenarios

Use the existing coordinator, controller-contract, scheduler, paired, and timed
service tests. For a hardware regression run, capture connection-attempt paths,
service completion times, reported positions when available, and the final link
release time. Exercise cold commands, overlapping replacements, STOP during
startup/read/cleanup, full recalls, combined failure cleanup, and several minutes
of idle after release. Keep raw device logs private.

Controller-declared motor holds also bound ordinary native cover actions. Most
covers use a one-second caller pulse and the declared start/release policy.
OCTO Standard covers, including the TV lift, retain their configured motor pulse
count and delay for native Open/Close actions. Long PIN-enabled movements refresh
authentication inside the same command lane, including during pulse delays. The
bundled card uses the separate
bounded hold service while pressed and sends STOP on release.
Motor-specific cover Stops invalidate only an overlapping axis. Declared
side-wide cover Stops and bed Stops retain their physical side scope.
Activation-key endings handled by a row do not reach the unscoped window release
fallback.
