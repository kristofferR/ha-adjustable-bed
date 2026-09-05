"""Shared synthetic tracker and stage-signing fixtures."""

from __future__ import annotations

import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools.phase4_v2.orchestration import ActivatedStageAuthority
from tools.phase4_v2.queue import TrackerDocument, TrackerDocumentSet, document_set_sha256


class SyntheticTrackerGateway:
    def __init__(self, repository: str, branch: str = "tracker") -> None:
        self.repository = repository
        self.branch = branch
        self.revision = "a" * 40
        self.documents: dict[str, bytes] = {}

    def read(self, paths: tuple[str, ...]) -> TrackerDocumentSet:
        return TrackerDocumentSet(
            self.revision,
            tuple(TrackerDocument(path, self.documents.get(path)) for path in paths),
        )

    def compare_and_replace(
        self,
        *,
        expected_revision: str,
        expected_documents_sha256: str,
        documents: tuple[TrackerDocument, ...],
    ) -> bool:
        current = tuple(
            TrackerDocument(item.path, self.documents.get(item.path)) for item in documents
        )
        if expected_revision != self.revision or expected_documents_sha256 != document_set_sha256(
            current
        ):
            return False
        self.documents = {item.path: item.body or b"" for item in documents}
        self.revision = hashlib.sha1(
            (self.revision + expected_documents_sha256).encode(), usedforsecurity=False
        ).hexdigest()
        return True


def sign_stage(
    stage: str,
    payload: dict[str, object],
    key: Ed25519PrivateKey,
    authority: ActivatedStageAuthority,
) -> bytes:
    payload = {**payload, "authority_sha256": authority.authority_sha256, "stage": stage}
    signature = key.sign(
        f"phase4-v2:signed-stage-receipt:{stage}".encode() + b"\0" + canonical(payload)
    ).hex()
    return canonical({"payload": payload, "signature": signature})


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


