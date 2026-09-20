# V4 migration and stabilization validation

Ref #598 and #526. This matrix records automated coverage for v4; it does not
replace installed release-candidate, backup-restore, or physical beta testing.

| Scenario | Automated evidence | Invariant |
| --- | --- | --- |
| Standalone v3 upgrade | `tests/test_init.py::TestMigration::test_migrate_v3_to_v4_is_byte_identical` | Only the schema version changes; entry data and options survive. |
| Combine two existing addresses | `tests/test_paired_setup.py` conversion tests; `tests/test_paired_devices.py` | Existing entity IDs and device IDs survive ownership transfer to parent/children. |
| Existing paired beta | `tests/test_paired_setup.py` paired-entry setup tests | Existing side devices become native children with preserved identities and physical metadata. |
| Single-address combination and unpair | `tests/test_paired_setup.py` enable/revert tests; `tests/test_paired_registry.py` | One physical parent and original entities survive; failures restore config ownership. |
| Offline side | `tests/test_paired_setup.py` offline entity and restored-bed tests | A missing side does not remove stable capabilities/entities or prevent restoring standalone entries. |
| Unpair failure and cancellation | `tests/test_paired_registry.py`; `tests/test_paired_devices.py` | Registry ownership, customizations, and entity identity survive rollback; cleanup failures stay visible. |
| Parent/child service targets | `tests/test_paired_devices.py`; `tests/test_paired_setup.py` STOP routing tests | Child targets operate only their side; contradictory targets are rejected; both children coalesce safely. |
| Feedback lost on one side | `tests/test_position_feedback.py`; `tests/test_paired_coordinator.py` | Seek cleanup finishes before failure reaches callers; a paired failure stops both sides. |
| Direct position command | `tests/test_position_feedback.py`; `tests/test_paired_coordinator.py` | An accepted target never becomes an unverified position report. |
| Saved card device targets | `frontend/src/discovery.test.ts` | Parent and child device IDs resolve consistently, including native child metadata. |
| Hold abandonment and side STOP | `frontend/src/hold.test.ts` | Abandoning a held control sends STOP to its side; the hold state machine ends its repeats. |

Frontend paths are relative to `custom_components/adjustable_bed/`. These are
component tests. They do not establish that actual browser/card removal events
reach the hold state machine in an installed dashboard.

## Reproduce automated validation

Use the project's development dependencies and HA-managed Bluetooth pins:

```sh
uv sync --extra dev
uv run --no-sync python scripts/ha_bluetooth_test_requirements.py > /tmp/ha-bluetooth-requirements.txt
uv pip install -r /tmp/ha-bluetooth-requirements.txt
uv run --no-sync pytest -q
```

Run the card checks from `custom_components/adjustable_bed/frontend`:

```sh
bun install --frozen-lockfile
bun run check
bun test
```

Also run the repository's Ruff and Pyright checks. CI checks that rebuilding
leaves the committed card bundle unchanged. The import-isolation tests use a
fresh interpreter, so an earlier test cannot hide eager imports.

## Final release-candidate gates

Keep these open in #526 until evidence is recorded against the selected release
candidate, including the exact integration and HA versions:

- Restore a pre-v4 backup on an isolated installation, verify the old code and
  config entries load together, then repeat the standalone upgrade. Follow the
  [backup and rollback procedure](HA_2026_9.md#backup-and-rollback).
- Exercise existing paired-beta migration, two-address conversion, single-address
  conversion, one unavailable side, and unpairing in the installed system. Check
  entity IDs, device ownership, custom names/areas, saved automation targets, and
  dashboard configuration before and after each operation.
- Load the shipped card in a browser with restored configuration. Verify
  parent/child discovery and side-specific STOP, then remove/navigate away from
  the card during a hold and confirm the backend receives cleanup.
- Record available beta evidence for STOP/cancellation and partial failures.
  Clearly label physical behavior that has not been verified; testing every
  supported bed is not a maintainer prerequisite.

The discovery collision in #577 remains separate: its replacement signature
requires accepted clean-room evidence through the ordered #436/#443 workflow.
No protocol commands, timing, or detection signatures change in this batch.
