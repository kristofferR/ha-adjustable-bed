from __future__ import annotations

import json
from typing import cast

import pytest

from tools.phase4_v2.ir import (
    SOURCE_SCHEMA_REVISION,
    IRValidationError,
    MigrationDomain,
    MigrationStatus,
    migration_json,
    plan_v112_migration,
    require_complete_migration,
)


def _payload() -> bytes:
    return json.dumps(
        {
            "actions": [{"id": "raise", "opcode": "01"}],
            "limitations": [],
            "schema_revision": SOURCE_SCHEMA_REVISION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def test_migration_inventory_is_content_bound_and_lists_every_unmodeled_leaf() -> None:
    payload = _payload()

    plan = plan_v112_migration(
        payload,
        {
            "/actions/0/id": MigrationDomain.ACTION,
            "/schema_revision": MigrationDomain.METADATA,
        },
    )

    assert plan.status is MigrationStatus.INCOMPLETE
    assert plan.unmodeled_paths == ("/actions/0/opcode", "/limitations")
    assert len(plan.source_sha256) == 64
    assert migration_json(plan) == migration_json(plan)


def test_complete_migration_requires_every_leaf_without_rewriting_source() -> None:
    payload = _payload()
    mappings = {
        "/actions/0/id": MigrationDomain.ACTION,
        "/actions/0/opcode": MigrationDomain.PACKET,
        "/limitations": MigrationDomain.LIMITATION,
        "/schema_revision": MigrationDomain.METADATA,
    }

    plan = plan_v112_migration(payload, mappings)

    assert plan.status is MigrationStatus.COMPLETE
    require_complete_migration(plan)
    assert payload == _payload()


def test_incomplete_migration_fails_at_first_unmodeled_path() -> None:
    plan = plan_v112_migration(_payload(), {})

    with pytest.raises(IRValidationError) as caught:
        require_complete_migration(plan)

    assert caught.value.diagnostics[0].code == "migration_incomplete"
    assert caught.value.diagnostics[0].path == "/actions/0/id"


def test_migration_rejects_non_leaf_and_non_enum_mappings() -> None:
    with pytest.raises(IRValidationError) as caught:
        plan_v112_migration(_payload(), {"/actions": MigrationDomain.ACTION})
    assert caught.value.diagnostics[0].code == "migration_mapping_not_leaf"

    with pytest.raises(ValueError, match="MigrationDomain"):
        plan_v112_migration(
            _payload(),
            {"/actions/0/id": cast(MigrationDomain, "ACTION")},
        )


def test_migration_rejects_duplicate_keys_and_wrong_revision() -> None:
    with pytest.raises(IRValidationError) as duplicate:
        plan_v112_migration(
            (f'{{"schema_revision":"{SOURCE_SCHEMA_REVISION}","x":1,"x":2}}').encode(),
            {},
        )
    assert duplicate.value.diagnostics[0].code == "migration_source_invalid"

    with pytest.raises(IRValidationError) as revision:
        plan_v112_migration(b'{"schema_revision":"future"}', {})
    assert revision.value.diagnostics[0].code == "migration_source_revision_mismatch"


@pytest.mark.parametrize("number", ("1.0", "1e999"))
def test_migration_rejects_decimal_numbers_deterministically(number: str) -> None:
    payload = f'{{"schema_revision":"{SOURCE_SCHEMA_REVISION}","value":{number}}}'

    with pytest.raises(IRValidationError) as caught:
        plan_v112_migration(payload, {})

    assert caught.value.diagnostics[0].code == "migration_source_invalid"


def test_migration_value_digest_changes_with_exact_source_semantics() -> None:
    first = plan_v112_migration(_payload(), {"/actions/0/opcode": MigrationDomain.PACKET})
    second_payload = _payload().replace(b'"01"', b'"02"')
    second = plan_v112_migration(
        second_payload,
        {"/actions/0/opcode": MigrationDomain.PACKET},
    )

    assert first.mapped_claims[0].value_sha256 != second.mapped_claims[0].value_sha256
    assert first.content_id != second.content_id
