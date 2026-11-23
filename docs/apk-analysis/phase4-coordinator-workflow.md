# APK Protocol Audit coordinator workflow

How coordinators run the #436 queue. The pinned [analyst prompt](phase4-analyst-prompt.md),
[schema](analysis.schema.json), completion gates and clean-room boundary stay as
they are. Everything around them exists to get merged implementation PRs out
quickly. Where older wording in #436, #443, #447 or a run handoff is stricter
about rounds, seals or ordering, this page wins.

## Ship, do not prove

The product is a merged PR that makes beds work. A report is evidence for that
PR, not a deliverable of its own. Lean units have gone from analyst start to an
open PR in about an hour. Units that turned their evidence into a project
stalled for days without one.

- **Budget.** Aim for an open PR within 8 hours of the analyst starting, or 16
  hours for a cluster or a sharded catalog. A unit is stalled when it passes its
  budget or its report would need a third audit round. Apply the stall rule at
  once instead of starting another round.
- **Stall rule.** Implement everything the audit verified. Give each claim it
  could not verify a `DEFERRED` disposition with the open finding and its next
  step, list them in the PR body, and open the PR. If nothing is verified, set
  the unit to `PARTIAL` with a one-line next step and move on. Tell the
  maintainer in one sentence either way.
- **No blocking queue.** A stuck, blocked or stopped unit never holds back the
  units after it. Run independent units in parallel up to the available slots.
  When both are ready, finish an accepted unit's PR before starting new analysis.
- **No proof infrastructure.** Do not build reader libraries, CLIs, lease or pin
  managers, provenance or relation graphs, seals of seals, protected-input
  rescans or preservation sweeps. Hash the input set (`INPUTS.SHA256`) and the
  final report (`REPORT.SHA256`); nothing else needs a seal. When a unit's state
  outside decompiler output grows past a few hundred megabytes, it has become a
  project: stop and apply the stall rule.
- **Effort.** Run workers at their default or high reasoning effort. Use xhigh
  only for a named hard slice, such as one obfuscated packet builder.
- **Short messages.** Status to the maintainer or a parent thread is one or two
  plain sentences about a stage change. Leave out hashes, seal IDs, receipt
  paths and "no credit" disclaimers.

## Select work

- Take units from the single ordered queue in #436. #443 holds the method and
  accepted evidence for scheduled rows; #447 is the early-work registry, not
  another queue.
- Target integration changes at `main`. Verify linked PR states before treating
  old implementation debt as current.
- A formal cluster ships one PR covering its accepted members. A member that is
  `BLOCKED`, `PARTIAL` or stopped does not hold its siblings: the PR names it,
  and it stays open in the unit's row as a follow-up.
- Untouched bulk ranges start only when the maintainer starts them.
- Give each stage one owner, and state file ownership before parallel work. One
  coordinator owns tracker publication.

## Keep the handoff small

Keep one short handoff per unit: work-unit ID, owner, stage, workspace, input and
report hashes, open findings and the next action. Point to files; never paste
reports or decompiler output into messages. A resumed worker reads the handoff
and continues from it instead of redoing finished work.

Before acceptance, the analyst or coordinator fixes report errors in place and
refreshes `REPORT.SHA256`. Only an accepted report is frozen. Keep earlier
attempts read-only where they are; do not copy them into new round directories.

Fresh analysts receive only their artifact-local inputs and the unchanged pinned
prompt and schema, never coordinator history or comparison findings. A fresh
context alone is not a filesystem boundary, so keep the wrapper isolation below
and do not claim isolation that was not provided.

## Launch workers as visible threads

The maintainer must be able to watch and steer every analyst, auditor, repair
and reconciliation worker.

- Start each worker as a visible T3 thread with `delegate_task` (for example
  Codex `gpt-6.1-sol`). Share the child thread link when it starts, and wait
  for its result instead of polling logs.
- Never launch a worker as a hidden process: no direct `codex exec`, `setsid`,
  `nohup` or detached jobs, and no older launcher scripts that do this
  (`run-isolated.sh`, `launch-detached.sh`).
- Isolation comes from the run workspace's namespace. Stage `sandbox.sh`,
  `heavy-tool.sh`, `namespace.sh` and `execution-driver.py` in the run root,
  re-rooted from the latest staged workspace under
  `disassembly/output/phase4-early/`. Seal `input/` in `INPUTS.SHA256` and run
  `verify-inputs.py` through `sandbox.sh` before launch. Give the worker only
  `input/ANALYST-BRIEF.txt`, which requires every operation to go through those
  wrappers.
- Workers may run a shell inside the wrapper (`sandbox.sh bash -c '...'`), with
  pipes and heredocs. The namespace is the boundary, so do not add bans on
  command shape. Reserve `heavy-tool.sh` slots for decompilers and compilers,
  not for reading reports or running checks.

## Acquire runtime catalogs without asking

Some apps download the product, model or capability catalog that selects their
BLE profile from a vendor backend at runtime. When a report is PARTIAL or
BLOCKED only because such a catalog is absent, the coordinator fetches it
without asking the maintainer. This standing authorization covers:

- Replaying exactly the request the artifact builds, as identified in the
  report and its cited source: the same endpoint, method, headers, parameters,
  and signing or token derived from keys embedded in the app.
- Read-only catalog, model, configuration or remote-code lookups only, one
  request per response the report needs. No retries in loops and no endpoint
  enumeration.

It never covers user accounts or personal credentials, login, registration,
pairing or device-bound requests, or anything that writes or changes state on
the backend. If the app's request needs any of those, record the blocker and
ask instead.

Then:

1. Store the response body untouched, plus the URL, method, header names,
   timestamp, HTTP status, body SHA-256 and the app source that builds the
   request. Never write a token or key value to disk or logs. Keep the response
   machine-local under the unit's state directory, never committed.
2. Add the response under `input/runtime-catalog/` and give the analyst a scoped
   repair: check its provenance against the artifact and reconcile every catalog
   row without network access.
3. Record the acquisition in the unit's handoff and evidence row.

## Analyze

- Reuse working decompilers, toolchain builds and caches instead of rebuilding
  them. A candidate index helps navigation but never proves completeness.
- Within one package, analyze a shared implementation once while tracing each
  variant's callers, selectors and dynamic fields.
- FULL promotion completes missing coverage; keep valid work instead of
  restarting the analysis.
- Before the audit, check that `analysis.json` validates and the reproducers
  run. That is the whole pre-audit check.

## Audit once, recheck once

1. One independent audit per report checks the claims that change integration
   behavior against the cited source: discovery rules and UUIDs, command bytes
   and framing, checksums, parsers, timing, STOP/release, authentication, and
   variant and capability selection. It also searches for reachable BLE paths
   the report missed.
2. Only defects in those claims are material. Findings about the report's own
   tooling, file layout, hashes, seals, labels, wording or bookkeeping never
   block acceptance or start another round; fix trivial ones in place.
3. The analyst fixes material findings in place. One scoped recheck covers only
   the fixed claims and what depends on them. Anything still unresolved after
   that recheck becomes `DEFERRED`; accept the rest.
4. An accepted report reopens only for a concrete protocol defect or a changed
   input, with a scoped repair and a scoped recheck, never a fresh full run.

## Reconcile clusters by command table

Reconciliation compares accepted member reports behavior by behavior. For each
command, discovery rule and capability, it records whether members are SAME or
DIFFERENT, citing each member's source. It is one table in one document. It does
not re-verify member reports, which their audits already accepted, and it never
builds relation inventories or class-by-class semantic proofs. It gets one
review under the audit rules above.

## Implement

After acceptance, one implementer per unit builds the discovery ledger, gives
each item one disposition (`IMPLEMENTED`, `ALREADY_IMPLEMENTED`, `EXCLUDED`, or
`DEFERRED` under the stall rule), implements, tests, writes the bed guide and
opens a real PR. The PR body lists the ledger totals, every exclusion and every
deferral. Run the repository's configured review loop. The convergence rules are
in [AGENTS.md](../../AGENTS.md#mandatory-post-freeze-implementation-convergence).

The ledger also records, for every `IMPLEMENTED` or `ALREADY_IMPLEMENTED`
item, which wire codec carries it: an existing codec only when its vector
harness reproduces the item's frozen literals byte for byte, otherwise a new
codec with its own vectors. New app support then lands as a profile over that
codec ([design](../design/protocol-codecs.md)). The analyst prompt, schema and
clean-room analysis do not change; the comparison stays in the post-freeze pass.

## Publish milestones

After acceptance, reopening or implementation changes, update the trackers and
the published queue in the same task, following [the tracker rules](TRACKERS.md):
change the affected #436 queue row and counts in place and add one evidence row
to #443 or #447. Publish transitions only, never progress. Make one edit per
transition and check it with `.github/scripts/apk_tracker_guard.py`; no readback
receipts, delta files or verification scripts.

The last step of every unit, and the one that matters most, is recording its
implementation PR: link it in the #436 row and the evidence row when it opens
and again when it merges, regenerate the queue view with
`.github/scripts/apk_queue_view.py`, and update the live status page. The unit
is not finished until they all show the PR.

## Workflow experiments

Issue #542 owns workflow improvements and #550 the accepted-artifact pilot,
whose own body holds its selection, telemetry and pass gates. Neither is a
prerequisite for queue work, and neither is a competing queue. Add automation
only for repetition the next unit actually needs.
