# Phase 4 v2 tooling

Phase 4 v2 is a fail-closed forensic pipeline. Its package-local stages never use sibling reports,
integration code, historical protocol notes, or human semantic annotations. Every accepted boundary
is content-addressed and pins the exact upstream revisions and digests it consumed.

## Pipeline components

- `preflight/` verifies the complete artifact set, selects every required application-stack route,
  executes pinned tools with bounded resources, requires authoritative fallbacks, and freezes a
  package-local candidate index and output manifest.
- `equivalence/` proves exact executable-root reuse or routes the root to FULL analysis. A frozen
  package execution plan includes its formal cluster identity and materializes that identity into
  the queue.
- `ir/` defines the closed typed protocol domains, exact evidence coverage, semantic universes,
  canonical rendering, and lossless migration planning.
- `reconciliation/` compares every package in one formal cluster, records exact same/different/
  incomplete decisions, and produces the cluster union, intersection, contradictions, promotions,
  and implementation dispositions.
- `queue/` provides fenced SQLite leases, immutable attempts and completions, bounded orchestration,
  deterministic Markdown/HTML trackers, and atomic multi-file publication.
- `benchmark/` keeps real holdout findings outside the blinded plan and authorizes rollout only when
  all quality, mutation, audit, throughput, and token gates pass.

The production tracker publisher writes dedicated generated documents. It creates all Markdown and
HTML blobs and one Git tree/commit, then advances the tracker branch with a non-force fast-forward.
Concurrent publishers therefore cannot expose a mixture of queue generations. GitHub issue bodies
should contain stable links to those generated documents; automation does not rewrite manual issue
prose.

Real APK selection, corpus materialization, holdout execution, and bulk workers remain separate
operator-controlled actions. Synthetic validation of this tooling does not cross that boundary.

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
