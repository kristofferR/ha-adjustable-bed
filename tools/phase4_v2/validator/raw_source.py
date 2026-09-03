"""Derive validator-receipt provenance from authenticated raw-source genesis."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import TYPE_CHECKING, cast

from tools.phase4_v2.raw_source import (
    AuthenticatedRawSourceRegistry,
    RawSourceAuthenticationError,
    RawSourceReauthenticationInput,
    reauthenticate_raw_source_registry,
)

from .bundle import _canonical_receipt_bytes

RAW_SOURCE_VALIDATION_BINDING_REVISION = "phase4-v2-raw-source-validator-binding-v1"

if TYPE_CHECKING:
    from tools.phase4_v2.equivalence.core import AuthenticatedValidatorEnvelope


class RawSourceValidationError(ValueError):
    """Raw-source evidence could not be admitted into a validator receipt."""


def derive_raw_source_validator_receipt(
    base_envelope: AuthenticatedValidatorEnvelope,
    *,
    raw_source_registry: AuthenticatedRawSourceRegistry,
    raw_source_inputs: tuple[RawSourceReauthenticationInput, ...],
) -> bytes:
    """Build unsigned receipt bytes from two independently authenticated inputs.

    The base envelope supplies validator-authenticated package identity and
    filesystem acceptance. The raw registry supplies the first non-circular
    semantic/root attestations. The returned receipt must still be signed by
    the ordinary validator authority before a source registry accepts it.
    """

    from tools.phase4_v2.equivalence.core import (
        AuthenticatedValidatorEnvelope,
        frozen_package_ref_from_validator_envelope,
        validate_authenticated_validator_envelope,
    )

    if type(base_envelope) is not AuthenticatedValidatorEnvelope:
        raise RawSourceValidationError(
            "raw-source derivation requires an authenticated validator envelope"
        )
    base = validate_authenticated_validator_envelope(base_envelope)
    base_ref = frozen_package_ref_from_validator_envelope(base)
    try:
        registry = reauthenticate_raw_source_registry(
            raw_source_registry,
            inputs=raw_source_inputs,
        )
    except RawSourceAuthenticationError as error:
        raise RawSourceValidationError("raw-source registry authentication failed") from error
    identity = base.report.validated_artifact_identity
    collections = tuple(registry.entries)
    if not collections or any(
        item.package_ref_id != base_ref.content_id
        or (item.package_name, item.version_code, item.artifact_digest)
        != (identity.package_name, identity.version_code, identity.artifact_digest)
        for item in collections
    ):
        raise RawSourceValidationError("raw-source registry does not exactly cover this package")

    members_by_path: dict[str, dict[str, object]] = {}
    anchors: list[dict[str, object]] = []
    roots: list[dict[str, object]] = []
    anchor_ids: set[str] = set()
    for collection in collections:
        raw_members = {item.id: item for item in collection.members}
        used_members: set[str] = set()
        root_anchor_ids: dict[str, list[str]] = defaultdict(list)
        for raw_anchor in collection.anchors:
            if raw_anchor.id in anchor_ids:
                raise RawSourceValidationError("raw-source anchor IDs are not package-unique")
            anchor_ids.add(raw_anchor.id)
            raw_member = raw_members[raw_anchor.member_id]
            used_members.add(raw_member.id)
            member: dict[str, object] = {
                "member": raw_member.path,
                "owner": collection.artifact_digest,
                "sha256": raw_member.sha256,
            }
            existing = members_by_path.get(raw_member.path)
            if existing is not None and existing != member:
                raise RawSourceValidationError("raw-source member paths are ambiguous")
            members_by_path[raw_member.path] = member
            anchors.append(
                {
                    "end_byte": raw_anchor.end_byte,
                    "id": raw_anchor.id,
                    "ir_pointer": raw_anchor.source_ir_pointer,
                    "member": raw_member.path,
                    "member_sha256": raw_member.sha256,
                    "owner": collection.artifact_digest,
                    "representation": raw_anchor.representation,
                    "start_byte": raw_anchor.start_byte,
                    "value_sha256": raw_anchor.value_sha256,
                }
            )
            root_anchor_ids[raw_member.path].append(raw_anchor.id)
        if used_members != set(raw_members):
            raise RawSourceValidationError("raw-source members are not an exact anchor closure")
        roots.append(
            {
                "evidence_members": [
                    {
                        "evidence_anchor_ids": sorted(ids),
                        "member": path,
                        "member_sha256": cast(str, members_by_path[path]["sha256"]),
                    }
                    for path, ids in sorted(root_anchor_ids.items())
                ],
                "semantic_root_sha256": collection.semantic_root_sha256,
                "target_occurrence_identity_sha256": (
                    collection.occurrence_identity_sha256
                ),
                "target_root_id": collection.target_root_id,
            }
        )
    anchors.sort(key=lambda item: cast(str, item["id"]).encode("utf-8"))
    roots.sort(key=_canonical_receipt_bytes)
    try:
        receipt = json.loads(base.receipt_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RawSourceValidationError("base validator receipt is not JSON") from error
    if type(receipt) is not dict:
        raise RawSourceValidationError("base validator receipt is not an object")
    receipt = cast(dict[str, object], receipt)
    if receipt.get("accepted") is not True or receipt.get("source_unchanged") is not True:
        raise RawSourceValidationError("base validator receipt is not accepted and stable")
    receipt["evidence_anchors_checked"] = len(anchors)
    receipt["validated_evidence_members"] = [
        members_by_path[path] for path in sorted(members_by_path)
    ]
    receipt["validated_evidence_anchors"] = anchors
    receipt["validated_root_evidence"] = roots
    receipt["raw_source_receipt_sha256s"] = sorted(
        item.receipt_sha256 for item in collections
    )
    receipt["raw_source_binding_revision"] = RAW_SOURCE_VALIDATION_BINDING_REVISION
    receipt.pop("validation_receipt_sha256", None)
    receipt["validation_receipt_sha256"] = hashlib.sha256(
        _canonical_receipt_bytes(receipt)
    ).hexdigest()
    return _canonical_receipt_bytes(receipt)
