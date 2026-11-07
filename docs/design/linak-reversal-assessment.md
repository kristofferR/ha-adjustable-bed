# Linak reversal assessment for v4

Ref #518. Assessed 2026-09-19 against `release/4.0` at `5cb286ce`, with the
runtime/registry hardening changes. This is a source and deterministic-test
assessment, not a new hardware test or APK analysis.

## Disposition

Retain the current conservative movement behavior. The old approximately
six-second physical reversal delay is **not confirmed fixed or reproduced** on
current firmware by this assessment. No new release/settle timing or command
sequence is justified by the available current-behavior evidence.

The b4 report predates PR #539's continuous Linak seek lifecycle. Current code
already differs from the old report's automatic-stop premise:

- `LinakPositionSeekPolicy.async_issue_step()` refreshes the held movement without
  intermediate release.
- `auto_stops_on_idle` is false. `PositionSeekRunner` sends terminal STOP in its
  cleanup, including replacement cancellation.
- The device scheduler waits for that cleanup before starting the replacement.
- `LinakPositionSeekPolicy` does not override `async_on_seek_start()`. The default
  adds neither a special reversal packet nor an extra settling delay between
  separate seeks. Overshoot correction is a different transition.
- A user STOP invalidates the queued replacement while old-command cleanup is
  pending.

## Deterministic evidence

`test_current_seek_replacement_releases_old_motion_before_new_target` in
`tests/test_linak.py` exercises the real coordinator, scheduler, seek runner and
Linak controller with a mocked BLE transport and injected reference feedback:

1. Start a downward back seek.
2. Submit a new same-direction or opposite-direction target.
3. Hold the old seek's STOP write pending and prove that no new motion is written.
4. Complete that write and observe the new direction followed by terminal STOP.
5. In a separate case, request user STOP during cleanup and prove the replacement
   never writes motion.

Both replacements complete within the test's one-second post-cleanup deadline
with immediate modeled feedback. This proves software ordering and excludes an
unconditional six-second software wait on that tested path. It says nothing about
actuator inertia, firmware reversal inhibition, proxy latency, reconnect delays,
or how quickly a real bed moves after accepting a new command.

## Beta feedback request

If the pause remains on a fresh beta, collect a support bundle spanning a
same-axis downward seek replaced by an upward target. Include controller model,
firmware if available, transport/proxy details, start and replacement targets,
and an observation of when physical motion reverses. Compare scheduler admission,
old STOP completion, first upward write, and reference position/speed timestamps.
Repeat a same-direction target replacement for comparison and check that user
STOP interrupts the transition. Use ordinary comfortable travel limits.

Hardware access is not required from the maintainer. Keep physical behavior
explicitly unverified until a user supplies current-beta evidence. Reopen wire
behavior optimization only with evidence supporting a bounded, safe improvement;
do not guess a release or settle sequence.
