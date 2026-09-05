# Phase 4 v2 tooling

Phase 4 v2 is a fail-closed forensic pipeline. Its package-local stages never use sibling reports,
integration code, historical protocol notes, or human semantic annotations. Every accepted boundary
is content-addressed and pins the exact upstream revisions and digests it consumed.

## Pipeline components

- `preflight/` verifies the complete artifact set, selects every required application-stack route,
  executes pinned tools with bounded resources, requires authoritative fallbacks, and freezes a
  package-local candidate index and output manifest. Production execution uses root-owned authority
  and signing-key files, a sealed minimal runtime filesystem, kernel-enforced output limits, signed
  persistent cache entries, and an authenticated preparation receipt.
- `equivalence/` proves exact executable-root reuse or routes the root to FULL analysis. A frozen
  package execution plan includes its formal cluster identity and exact accepted preparation.
  Preparation, target-root inventory, and package validation are reserved queue units. Inventory and
  validator results enter through protected signed envelopes rather than caller-supplied trust pins,
  and package identities retain that authenticated provenance through reconciliation.
- `raw_source.py` authenticates evidence from prepared outputs before it enters the protocol model.
  Reused roots retain their source evidence; package-local facts require separate evidence from the
  target package, including when every executable root is reused.
- `ir/` defines the closed typed protocol domains, exact evidence coverage, semantic universes,
  canonical rendering, and lossless migration planning.
- `reconciliation/` compares every package in one formal cluster, records exact same/different/
  incomplete decisions, and produces the cluster union, intersection, contradictions, promotions,
  and implementation dispositions. Final surfaces retain each root's authenticated source package,
  source occurrence, validation receipt, evidence members, and exact anchor metadata. Cluster input
  is admitted only as the exact package set covered by completed signed package audits.
- `queue/` provides fenced SQLite leases, immutable attempts and completions, bounded orchestration,
  deterministic Markdown/HTML trackers, and atomic multi-file publication. Reserved semantic stages
  can finish only from receipts that the queue reauthenticates against the unit's exact active
  authority capability. Publication completion is bound to the exact target paths, formats,
  configuration, document set, queue generation, and remote readback.
- `orchestration/` derives one immutable cluster graph from accepted package plans and protected
  stage authorities. It enforces package audit, whole-cluster reconciliation, implementation, and
  tracker publication in order with signed, graph-bound receipts.
- `benchmark/` keeps real holdout findings outside the blinded plan and authorizes rollout only when
  all quality, mutation, audit, throughput, and token gates pass. Its root-owned authority commits
  the exact plan contract, oracle, ordered trial schedule, and one-to-one corpus membership, and is
  reloaded before finalization so a rotated generation invalidates an older in-memory authority.

The production-path tracker publisher writes dedicated generated documents. It creates all Markdown
and HTML blobs and one Git tree/commit, then advances the tracker branch with a non-force fast-forward.
The gateway verifies that branch protection forbids force pushes and deletion before publishing.
Concurrent publishers therefore cannot expose a mixture of queue generations, and uncertain write
outcomes are reconciled against exact readback. GitHub issue bodies should contain stable links to
those generated documents; automation does not rewrite manual issue prose.

Real APK selection, corpus materialization, holdout execution, and bulk workers remain separate
operator-controlled actions. Synthetic validation of this tooling does not cross that boundary.

## Production trust configuration

Phase 4 v2 reads fixed files beneath root-owned `/etc/ha-adjustable-bed`. Callers cannot provide an
alternate authority-pin path or expected digest at those loaders. The preparation executor key and
preparation, validator, raw-source, exact-reuse, stage, and benchmark authority pins are deployment
inputs, not analyst inputs. Authenticated consumers check retained evidence against those deployment
inputs.

Test-only helpers emulate those deployment inputs for synthetic hostile and recovery tests. They are
not imported or selectable by the production loaders, and a test-created value cannot pass a
production consuming boundary without matching the protected deployment state.

The test-only seeded acceptance runner exercises the complete production API chain with synthetic
inputs: preflight and signed preparation, authenticated source validation, signed target inventory,
bound package report validation, package audit, cluster reconciliation, implementation, and atomic
tracker fanout. It emulates protected deployment configuration inside the test process and expires
leases in its private queue to inject worker crashes. It never patches queue trust guards or inserts
reserved completions through the generic finish API.

## Rollout limitations

Synthetic tests cover FULL, mixed FULL/EXACT_REUSE, and all-EXACT_REUSE execution. They do not establish
real-corpus quality or throughput. Issue #550 still requires the blinded benchmark before adoption.

The pre-bulk implementation also has outstanding deployment-hardening review items: consistent
authority-rotation and document-size checks, protection of the queue database, isolation of the
preparation signing API, and pinning the GitHub CLI executable, host, environment, and streaming
output limits. Formal cluster cardinality must also be aligned across orchestration and
reconciliation before admitting unsupported cluster sizes. These items are not certified by a green
synthetic test run. Treat this tooling as a development implementation until they are dispositioned
and the rollout gates pass.

## Legacy preservation inventory

`legacy_inventory` creates a deterministic, protocol-neutral index of an existing Phase 4 tree:

```bash
uv run python -m tools.phase4_v2.legacy_inventory \
  "<legacy-root>" "<new-output-directory>" \
  --active-path "<relative-active-workspace>"
```

Repeat `--active-path` for every workspace that another approved process may still change. Each
path must exist beneath the source root and may not traverse a symlink.

The command:

- never follows source symlinks or opens the source tree for writing;
- records every observable node's path, type, size, ownership, mode, timestamps and provenance;
- extracts report status, schema and package identity without retaining protocol content;
- records and verifies existing SHA-256 declarations without hashing unrelated decompilation files;
- reports malformed, duplicate, possibly stale, rejected, failed, audit, repair, reconciliation,
  handoff and frozen history without modifying it;
- compares device, inode, size, mode, modification time and change time before and after the scan;
- inventories active paths but reports their changes separately from the mandatory stable-tree
  equality gate; and
- publishes to a new, external directory without replacing an existing destination.

The output directory is fully covered only when `INVENTORY.COMPLETE` is present and verifies
`manifest.json`. `INVENTORY.PARTIAL` is used instead when permissions made any historical path
opaque. The manifest hashes every generated payload, and the marker hashes that manifest.
`entries.ndjson`, `reports.ndjson`, `workspaces.ndjson`,
`declared_hashes.ndjson`, `duplicate_reports.ndjson` and `diagnostics.ndjson` are streaming,
machine-readable inputs for later Phase 4 v2 stages. `SUMMARY.md` is the human overview.

An inaccessible historical path is recorded as opaque in the diagnostics and coverage summary.
The scanner never changes permissions to inspect it.
