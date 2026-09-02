# Phase 4 v2 tooling

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
