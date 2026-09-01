"""Preimage-safe tracker publication against an atomic issue gateway."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from .core import Lease, Queue
from .tracker import (
    GITHUB_ISSUE_BODY_MAX_CHARS,
    managed_block_generation,
    managed_block_length,
    managed_block_sha256,
    render_markdown,
    replace_managed_block,
)


class PublisherConflictError(RuntimeError):
    """The issue or queue changed during tracker publication."""


class PublisherReadbackError(RuntimeError):
    """The issue write did not read back byte-for-byte."""


class PublisherPostWriteConflictError(PublisherConflictError):
    """The issue was written but queue drift requires an immediate retry."""


@dataclass(frozen=True, slots=True)
class IssueDocument:
    """One exact issue-body read."""

    body: str
    revision: str


class AtomicIssueGateway(Protocol):
    """Issue transport that can atomically compare and replace a full body."""

    def read(self, issue_number: int) -> IssueDocument: ...

    def compare_and_replace(
        self,
        issue_number: int,
        *,
        expected_revision: str,
        expected_body_sha256: str,
        body: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class PublishReceipt:
    """Deterministic evidence for one successful or unnecessary publication."""

    issue_number: int
    queue_generation: str
    before_body_sha256: str
    after_body_sha256: str
    issue_revision: str
    changed: bool


def publish_tracker(
    queue: Queue,
    lease: Lease,
    gateway: AtomicIssueGateway,
    issue_number: int,
) -> PublishReceipt:
    """Render, CAS-publish, and read back one exact queue snapshot."""
    if issue_number < 1:
        raise ValueError("issue_number must be positive")
    with _publication_guard(queue):
        queue.renew(lease, ttl_seconds=300)
        snapshot = queue.snapshot()
        before = gateway.read(issue_number)
        before_digest = _sha256(before.body)
        current_generation = managed_block_generation(before.body)
        current_block_digest = managed_block_sha256(before.body)
        separator_length = (
            0
            if current_generation is not None or not before.body or before.body.endswith("\n\n")
            else 2
        )
        tracker_budget = (
            GITHUB_ISSUE_BODY_MAX_CHARS
            - (len(before.body) - managed_block_length(before.body) + separator_length)
        )
        rendered_budget = tracker_budget + (1 if current_generation is not None else 0)
        try:
            rendered = render_markdown(snapshot, max_characters=rendered_budget)
        except ValueError as error:
            raise PublisherConflictError("issue body leaves no room for the tracker") from error
        updated = replace_managed_block(
            before.body,
            rendered,
            expected_generation=current_generation,
            expected_block_sha256=current_block_digest,
        )
        if len(updated) > GITHUB_ISSUE_BODY_MAX_CHARS:
            raise PublisherConflictError("tracker update exceeds GitHub's issue-body limit")
        after_digest = _sha256(updated)
        if updated == before.body:
            _require_current(queue, lease, snapshot.generation_id, post_write=False)
            queue._checkpoint_internal(
                lease,
                "TRACKER_ALREADY_CURRENT",
                {"generation": snapshot.generation_id, "issue": issue_number},
            )
            _require_current(queue, lease, snapshot.generation_id, post_write=False)
            return PublishReceipt(
                issue_number,
                snapshot.generation_id,
                before_digest,
                after_digest,
                before.revision,
                False,
            )
        _require_current(queue, lease, snapshot.generation_id, post_write=False)
        if not gateway.compare_and_replace(
            issue_number,
            expected_revision=before.revision,
            expected_body_sha256=before_digest,
            body=updated,
        ):
            raise PublisherConflictError("issue body changed before tracker publication")
        after = gateway.read(issue_number)
        if after.body != updated:
            raise PublisherReadbackError("published tracker failed exact issue-body readback")
        _require_current(queue, lease, snapshot.generation_id, post_write=True)
        try:
            queue._checkpoint_internal(
                lease,
                "TRACKER_PUBLISHED",
                {
                    "after_body_sha256": after_digest,
                    "before_body_sha256": before_digest,
                    "generation": snapshot.generation_id,
                    "issue": issue_number,
                },
            )
        except Exception as error:
            raise PublisherPostWriteConflictError(
                "tracker was written but the publication event could not be recorded"
            ) from error
        _require_current(queue, lease, snapshot.generation_id, post_write=True)
        return PublishReceipt(
            issue_number,
            snapshot.generation_id,
            before_digest,
            after_digest,
            after.revision,
            True,
        )


def _require_current(
    queue: Queue,
    lease: Lease,
    generation: str,
    *,
    post_write: bool,
) -> None:
    try:
        queue.renew(lease, ttl_seconds=300)
    except Exception as error:
        if post_write:
            raise PublisherPostWriteConflictError(
                "tracker was written but publisher lease is no longer current"
            ) from error
        raise PublisherConflictError("publisher lease is no longer current") from error
    if queue.snapshot().generation_id != generation:
        if post_write:
            raise PublisherPostWriteConflictError(
                "tracker was written but queue changed during publication"
            )
        raise PublisherConflictError("queue changed before tracker publication")


@contextmanager
def _publication_guard(queue: Queue) -> Iterator[None]:
    try:
        descriptor = queue._try_acquire_publication_guard()
    except Exception as error:
        raise PublisherConflictError("publisher guard is unsafe or inaccessible") from error
    if descriptor is None:
        raise PublisherConflictError("another tracker publisher holds the guard")
    try:
        yield
    finally:
        os.close(descriptor)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
