"""Bounded JSON CLI for Phase 4 v2 queue workers and tracker rendering."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from .core import Lease, Queue, QueueError, TerminalOutcome
from .tracker import render_html, render_markdown

_MAX_INPUT_BYTES = 1024 * 1024
_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json_file(path: Path) -> object:
    try:
        descriptor = os.open(path, _READ_FLAGS)
    except OSError as error:
        raise ValueError(f"unsafe or inaccessible JSON file: {path}") from error
    try:
        node = os.fstat(descriptor)
        identity = (node.st_mode, node.st_ino, node.st_dev, node.st_size, node.st_mtime_ns)
        if not stat.S_ISREG(node.st_mode) or node.st_size > _MAX_INPUT_BYTES:
            raise ValueError(f"JSON input must be a bounded regular file: {path}")
        chunks: list[bytes] = []
        remaining = node.st_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise ValueError(f"JSON input changed while reading: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (
            os.read(descriptor, 1)
            or (
                after.st_mode,
                after.st_ino,
                after.st_dev,
                after.st_size,
                after.st_mtime_ns,
            )
            != identity
        ):
            raise ValueError(f"JSON input changed while reading: {path}")
        try:
            return json.loads(
                b"".join(chunks),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=lambda value: _invalid_constant(value),
                parse_int=_bounded_integer,
            )
        except (UnicodeError, ValueError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError(f"invalid JSON input: {path}") from error
    finally:
        os.close(descriptor)


def _invalid_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number: {value}")


def _bounded_integer(value: str) -> int:
    if len(value.lstrip("-")) > 100:
        raise ValueError("JSON integer is too large")
    return int(value)


def _lease_from_file(path: Path) -> Lease:
    raw = _read_json_file(path)
    expected = {
        "unit_id",
        "attempt_id",
        "lease_id",
        "owner",
        "fencing_token",
        "expires_at",
        "input_digest",
        "workspace",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("lease file has unexpected fields")
    strings = (
        "unit_id",
        "attempt_id",
        "lease_id",
        "owner",
        "input_digest",
        "workspace",
    )
    if any(not isinstance(raw[field], str) for field in strings):
        raise ValueError("lease file string field is invalid")
    if type(raw["fencing_token"]) is not int or type(raw["expires_at"]) is not int:
        raise ValueError("lease file integer field is invalid")
    return Lease(
        unit_id=raw["unit_id"],
        attempt_id=raw["attempt_id"],
        lease_id=raw["lease_id"],
        owner=raw["owner"],
        fencing_token=raw["fencing_token"],
        expires_at=raw["expires_at"],
        input_digest=raw["input_digest"],
        workspace=Path(raw["workspace"]),
    )


def _lease_dict(lease: Lease) -> dict[str, object]:
    payload = asdict(lease)
    payload["workspace"] = str(lease.workspace)
    return payload


def _emit(payload: object) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase4-v2-queue")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--attempts-root", type=Path, required=True)
    parser.add_argument("--busy-timeout-ms", type=int, default=30_000)
    commands = parser.add_subparsers(dest="command", required=True)

    claim = commands.add_parser("claim")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--ttl-seconds", type=int, default=1_800)

    renew = commands.add_parser("renew")
    renew.add_argument("--lease-file", type=Path, required=True)
    renew.add_argument("--ttl-seconds", type=int, default=1_800)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--lease-file", type=Path, required=True)
    checkpoint.add_argument("--event-type", required=True)
    checkpoint.add_argument("--payload-file", type=Path)

    finish = commands.add_parser("finish")
    finish.add_argument("--lease-file", type=Path, required=True)
    finish.add_argument("--outcome", choices=tuple(TerminalOutcome), required=True)
    finish.add_argument("--output-digest")
    finish.add_argument("--completion-revision")
    finish.add_argument("--expected-input-digest")

    commands.add_parser("recover")
    retry = commands.add_parser("retry-repaired")
    retry.add_argument("--unit-id", required=True)
    retry_blocked = commands.add_parser("retry-blocked")
    retry_blocked.add_argument("--unit-id", required=True)
    status = commands.add_parser("status")
    status.add_argument("--unit-id")
    render = commands.add_parser("render")
    render.add_argument("--format", choices=("markdown", "html"), required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded queue operation and emit machine-readable output."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.database.is_file() or not args.attempts_root.is_dir():
        parser.error("database and attempts root must already be initialized")
    queue = Queue(
        args.database,
        args.attempts_root,
        busy_timeout_ms=args.busy_timeout_ms,
    )
    try:
        queue.verify_schema()
        if args.command == "claim":
            lease = queue.claim(args.owner, ttl_seconds=args.ttl_seconds)
            _emit({"claimed": lease is not None, "lease": _lease_dict(lease) if lease else None})
        elif args.command == "renew":
            lease = queue.renew(_lease_from_file(args.lease_file), ttl_seconds=args.ttl_seconds)
            _emit(_lease_dict(lease))
        elif args.command == "checkpoint":
            payload: object = (
                _read_json_file(args.payload_file) if args.payload_file is not None else {}
            )
            if not isinstance(payload, dict):
                raise ValueError("checkpoint payload must be a JSON object")
            queue.checkpoint(_lease_from_file(args.lease_file), args.event_type, payload)
            _emit({"checkpointed": True})
        elif args.command == "finish":
            lease = _lease_from_file(args.lease_file)
            outcome = TerminalOutcome(args.outcome)
            if outcome is TerminalOutcome.ACCEPTED:
                if (
                    args.output_digest is None
                    or args.completion_revision is None
                    or args.expected_input_digest is None
                ):
                    raise ValueError(
                        "accepted attempts require expected input digest, output digest, and revision"
                    )
                checked = queue.finish_accepted_if_input_matches(
                    lease,
                    expected_input_digest=args.expected_input_digest,
                    output_digest=args.output_digest,
                    completion_revision=args.completion_revision,
                )
                result = checked.finish_result
                emitted = {"input_check": checked.disposition, **asdict(result)}
            else:
                if args.expected_input_digest is not None:
                    raise ValueError(
                        "expected input digest is only valid for accepted attempts"
                    )
                result = queue.finish(
                    lease,
                    outcome,
                    output_digest=args.output_digest,
                    completion_revision=args.completion_revision,
                )
                emitted = asdict(result)
            _emit(emitted)
        elif args.command == "recover":
            _emit({"recovered": queue.recover()})
        elif args.command == "retry-repaired":
            queue.retry_repaired(args.unit_id)
            _emit({"retried": True, "unit_id": args.unit_id})
        elif args.command == "retry-blocked":
            queue.retry_blocked(args.unit_id)
            _emit({"retried": True, "unit_id": args.unit_id})
        elif args.command == "status":
            if args.unit_id is None:
                _emit(queue.snapshot().as_dict())
            else:
                _emit({"unit_id": args.unit_id, "status": queue.status(args.unit_id)})
        elif args.command == "render":
            snapshot = queue.snapshot()
            print(
                render_markdown(snapshot) if args.format == "markdown" else render_html(snapshot),
                end="",
            )
        else:  # pragma: no cover - argparse constrains commands
            parser.error("unknown command")
    except (QueueError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
