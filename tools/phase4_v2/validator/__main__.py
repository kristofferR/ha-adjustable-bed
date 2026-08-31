"""Command-line entry point for the Phase 4 bundle validator."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from .binding import DependencyPins
from .bundle import validate_report_bundle
from .lineage import EvidenceLineageTrust, TrustedProducer

_MAX_LINEAGE_BYTES = 64 * 1024**2


def main() -> int:
    """Validate one report directory and print its canonical receipt."""
    parser = argparse.ArgumentParser(
        description="Validate a frozen Phase 4 report bundle without modifying it."
    )
    parser.add_argument("report_root", type=Path)
    parser.add_argument("--preflight-sha256")
    parser.add_argument("--ir-sha256")
    parser.add_argument("--schema-sha256")
    parser.add_argument("--corpus-sha256")
    parser.add_argument("--evidence-lineage", type=Path)
    parser.add_argument("--evidence-lineage-sha256")
    parser.add_argument(
        "--trusted-producer",
        action="append",
        default=[],
        metavar="PIPELINE,ROUTE,TOOL_SHA256",
    )
    args = parser.parse_args()

    supplied = (
        args.preflight_sha256,
        args.ir_sha256,
        args.schema_sha256,
        args.corpus_sha256,
    )
    if any(supplied) and not all(supplied):
        parser.error("all four dependency digests must be supplied together")
    pins = (
        DependencyPins(
            preflight_sha256=args.preflight_sha256,
            ir_sha256=args.ir_sha256,
            schema_sha256=args.schema_sha256,
            corpus_sha256=args.corpus_sha256,
        )
        if all(supplied)
        else None
    )
    lineage_arguments = (
        args.evidence_lineage,
        args.evidence_lineage_sha256,
        args.trusted_producer,
    )
    if pins is not None and not all(lineage_arguments):
        parser.error("bound validation requires the complete external evidence-lineage trust set")
    if pins is None and any(lineage_arguments):
        parser.error("evidence-lineage trust arguments require all four dependency digests")
    lineage = None
    if pins is not None:
        producers = _parse_producers(parser, args.trusted_producer)
        lineage_payload = _read_external_lineage(parser, args.report_root, args.evidence_lineage)
        lineage = EvidenceLineageTrust(
            payload=lineage_payload,
            expected_manifest_sha256=args.evidence_lineage_sha256,
            trusted_producers=producers,
        )
    receipt = validate_report_bundle(
        args.report_root,
        expected_dependencies=pins,
        expected_evidence_lineage=lineage,
    )
    sys.stdout.write(receipt.to_json())
    return 0 if receipt.accepted else 1


def _parse_producers(
    parser: argparse.ArgumentParser, values: list[str]
) -> tuple[TrustedProducer, ...]:
    parsed: list[TrustedProducer] = []
    for item in values:
        parts = item.split(",")
        if len(parts) != 3 or any(not part for part in parts):
            parser.error("each --trusted-producer must be PIPELINE,ROUTE,TOOL_SHA256")
        parsed.append(TrustedProducer(*parts))
    return tuple(parsed)


def _read_external_lineage(
    parser: argparse.ArgumentParser, report_root: Path, path: Path
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        parser.error(f"cannot open external evidence lineage: {error}")
    try:
        before = os.fstat(descriptor)
        opened_path = Path(f"/proc/self/fd/{descriptor}").resolve()
        report_path = report_root.resolve()
        if opened_path == report_path or opened_path.is_relative_to(report_path):
            parser.error("evidence lineage must be outside the report workspace")
        if not stat.S_ISREG(before.st_mode) or before.st_size > _MAX_LINEAGE_BYTES:
            parser.error("evidence lineage must be a bounded regular file")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if len(payload) != before.st_size or identity_before != identity_after:
            parser.error("evidence lineage changed while being read")
        return payload
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
