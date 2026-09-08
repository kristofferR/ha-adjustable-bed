# Phase 4 coordinator workflow

This is the small v3 operating amendment for #443, not a new analysis schema or
execution platform. The canonical analyst prompt and all 17 completion gates
remain authoritative. Do not migrate accepted reports to a new representation.

## Select and resume work

- Read the single ordered queue in #436. #443 is the evidence specification and
  batch ledger; #447 is the accepted-early exclusion registry, not another queue.
- Target integration changes at `release/4.0`. Verify linked PR merge states and
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

After acceptance, reopening or implementation changes, update #436, #443, #447
and the published queue together, including arithmetic, PR links and target
branches. Distinguish historical acceptance from currently usable evidence.
Issue closures marked superseded/deferred do not mean their former gates passed.
Keep #542/#550 status current without turning them into competing work queues.
