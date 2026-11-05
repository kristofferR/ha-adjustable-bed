# APK Protocol Audit coordinator workflow

This is the small v3 operating amendment for #443, not a new analysis schema or
execution platform. The canonical analyst prompt and all 17 completion gates
remain authoritative. Do not migrate accepted reports to a new representation.

## Select and resume work

- Read the single ordered queue in #436. #443 is the evidence specification and
  batch ledger; #447 is the accepted-early exclusion registry, not another queue.
- Target integration changes at `main`. Verify linked PR merge states and
  target branches before treating historical implementation debt as current.
- Clear the accepted prefix's implementation debt before untouched analysis.
  A formal cluster still needs every member, audit and reconciliation accepted
  before one comprehensive implementation PR. Do not create partial feature PRs
  and call the cluster finished.
- Untouched bulk remains stopped until the maintainer explicitly starts it.
  The separately authorized #550 pilot uses accepted artifacts and does not
  advance corpus completion counts.
- Assign an explicit implementer, analyst and auditor as those stages become
  ready. With four slots, allocate the remaining workers to the current unit's
  independent packages or disjoint shards, not competing coordinators. One
  coordinator owns tracker publication. Do not overlap later clusters in breach
  of the canonical queue gate.

## Keep the handoff small and persistent

Record the work-unit ID, owner, stage, target branch, exact input/report hashes,
workspace, completed coverage, unresolved finding IDs and next action. Point to
the evidence files; do not copy decompiler trees or whole reports into messages.
Use unique persistent attempt paths. A resumed worker checks the handoff and
hashes before repeating work. Never overwrite a prior attempt or frozen report.

Fresh analysts receive only their allowed artifact-local inputs and unchanged
pinned prompt/schema, never coordinator history or comparison findings. Fresh
conversation context alone is not a filesystem security boundary. Preserve the
existing clean-room restrictions and do not claim isolation that was not provided.

## Launch workers as visible threads

The maintainer must be able to watch and steer every analyst, auditor, repair
and reconciliation worker.

- Start each worker as a visible T3 thread with `delegate_task` (for example
  Codex `gpt-6.1-sol`). Share the child thread link when it starts, and wait
  for its result instead of polling logs.
- Never launch a worker as a hidden process: no direct `codex exec`, `setsid`,
  `nohup` or detached jobs, and no older launcher scripts that do this
  (`run-isolated.sh`, `launch-detached.sh`).
- Isolation comes from the run workspace, not from hiding the process. Stage
  `sandbox.sh`, `heavy-tool.sh`, `namespace.sh` and `execution-driver.py` in the
  run root, re-rooted from the latest staged workspace under
  `disassembly/output/phase4-early/`. Seal `input/` in `INPUTS.SHA256` and run
  `verify-inputs.py` through `sandbox.sh` before launch. Give the worker only
  `input/ANALYST-BRIEF.txt`, which requires every operation to go through those
  wrappers.

## Acquire runtime catalogs without asking

Some apps download the product, model or capability catalog that selects their
BLE profile from a vendor backend at runtime. When a report is PARTIAL or
BLOCKED only because such a catalog is absent, the coordinator fetches it
without asking the maintainer. This standing authorization covers:

- Replaying exactly the request the artifact builds, as identified in the
  frozen report and its cited source: the same endpoint, method, headers,
  parameters, and signing or token derived from keys embedded in the app.
- Read-only catalog, model, configuration or remote-code lookups only, one
  request per response the report needs. No retries in loops and no endpoint
  enumeration.

It never covers user accounts or personal credentials, login, registration,
pairing or device-bound requests, or anything that writes or changes state on
the backend. If the app's request needs any of those, record the blocker and
ask instead.

Then:

1. Store the response body untouched, plus acquisition metadata: URL, method,
   header names, timestamps, HTTP status, response headers, body SHA-256 and the
   app source references that build the request. Never write a token or key
   value to disk or logs. Keep the response machine-local under the unit's
   state directory, never committed, and make it read-only.
2. Stage a new attempt with the same sealed inputs plus the response under
   `input/runtime-catalog/`, with the prior attempt mounted read-only. Launch a
   visible scoped-repair worker that checks the response's provenance against
   the artifact and reconciles every catalog row without network access.
3. Record the acquisition in the unit's handoff and in its evidence row with the
   report (#443 for scheduled rows, #447 for early work).

## Prepare useful evidence before audit

- Reuse already operational artifact checks, decompilers, warning logs, safe
  caches, indexes and validators where their actual dependencies are available.
  Retain authoritative fallbacks and all required stack coverage. A candidate
  index helps navigation but never proves completeness or semantic equivalence.
- Make each material claim independently checkable against complete source
  references and reproducible vectors. Verify referenced files/ranges, ownership,
  required members, schema validity and report agreement before the auditor starts.
  Mechanical checks supplement, not replace, semantic inspection.
- Within one package, analyze an actual shared implementation once while tracing
  every variant's callers, selectors, resources, state and dynamic fields. Distinct
  implementations need their own coverage unless equivalence is proven. Do not
  import sibling semantics before the package-local freeze/comparison boundary.
- FULL promotion means complete missing coverage; retain valid package-local work
  instead of restarting the analysis or discarding its evidence.
- During reconciliation, compare behavior rather than report layout. A missing
  key is an unresolved mapping until evidence proves absence. Provenance checks
  are separate from SAME/DIFFERENT decisions.

## Audit once fully, then verify affected scope

The first independent audit retains the complete #443 checks and independent
omission search. Maintain one stable finding ledger: requirement, source evidence,
affected claims, repair and verification status. Recheck corrected claims and
their affected dependencies in subsequent rounds. Expand the audit when a fix
invalidates earlier coverage, rather than automatically repeating all of it.

Every unresolved material behavior, coverage, evidence, reproducibility, schema or
report-agreement defect still blocks acceptance. Cosmetic prose preferences do
not create new requirements. Keep mutable audit-round bookkeeping outside frozen
findings; do not require a report to predict its future accepting audit number.
Prevent reproducers from writing caches or generated files into frozen evidence.

Repeated material failures trigger a short cause diagnosis and, where useful,
fresh help on the failing slice. There is no acceptance-round cap, automatic
waiver, or assumption that later hardware testing will catch known defects.

An accepted report is reopened only for a concrete defect or changed input.
Preserve the original, quarantine affected claims from implementation/reuse, and
record the exact counterexample and scope uncertainty. Assign an appropriately
isolated evidence-repair context, without integration-derived answers. Revalidate
affected extraction and dependent claims, independently review the repair, and
freeze an explicit addendum/replacement with new hashes. Do not call a scoped
repair a fresh FULL clean-room run or reopen unrelated accepted work by default.

## Measure improvement without another framework

Issue #542 owns the bounded workflow task; #550 owns the pilot. Freeze the pilot's
8–12 accepted-artifact selection, blinded oracle, trial order, tool/workflow
versions and telemetry before analysts start. Evaluate the first two contrasting
cases before expanding; an early stop is not a passed benchmark. Keep all originals.

Record real decompilation, analysis, audit/rework and orchestration durations and
token costs separately. Missing historical telemetry remains unknown; measure a
valid baseline when needed for ratios. Retain all quality, historical regression,
3x throughput and 5x cost gates unless the maintainer explicitly changes them.
State sample limitations and never substitute synthetic results for real trials.

The experimental v2 service, signing infrastructure, generalized report migration
and corpus-wide rerouting are not prerequisites. Preserve their code and tests
without repairing or extracting the whole platform. Add automation only for
demonstrated repetition in the next work unit, and keep its scope tied to that need.

## Publish milestones

After acceptance, reopening or implementation changes, update the trackers and the
published queue in the same task, following [the tracker rules](TRACKERS.md):
change the affected #436 queue row and counts in place and add one evidence row
to #443 or #447. Publish transitions only, never progress. Run windows, worker
launches, review rounds, CI results, receipts and handoffs stay in the
machine-local handoff and on the live status page, so a tracker edit never needs
a size budget, compaction or a publication bundle. Check each draft with
`.github/scripts/apk_tracker_guard.py` before editing the issue.

The last step of every unit, and the one that matters most, is recording its
implementation PR: link it in the #436 row and the evidence row when it opens
and again when it merges, regenerate the queue view with
`.github/scripts/apk_queue_view.py`, and update the live status page. The unit
is not finished until they all show the PR.

Distinguish historical acceptance from currently usable evidence. Issue closures
marked superseded/deferred do not mean their former gates passed. Keep #542/#550
status current without turning them into competing work queues.
