"""Protected authority descriptors reject mutation and bounded JSON abuse."""

from __future__ import annotations

import json
import os
import stat
from types import ModuleType

import pytest

from tools.phase4_v2.benchmark import model as benchmark
from tools.phase4_v2.equivalence import core, execution, inventory


def _metadata(*, directory: bool = False, size: int = 1, changed: str = "") -> os.stat_result:
    values = [stat.S_IFDIR | 0o755 if directory else stat.S_IFREG | 0o444, 5, 2, 1, 0, 0, size, 0, 0, 0]
    fields = {"mode": 0, "inode": 1, "device": 2, "links": 3, "uid": 4, "gid": 5, "size": 6}
    if changed in fields:
        values[fields[changed]] += 1
    return os.stat_result(values, {
        "st_mtime_ns": 2 if changed == "mtime" else 1,
        "st_ctime_ns": 2 if changed == "ctime" else 1,
    })


@pytest.mark.parametrize("module", [core, execution, inventory, benchmark])
@pytest.mark.parametrize("changed", ["", "mode", "uid", "gid", "links", "device", "inode", "size", "mtime", "ctime", "directory"])
def test_protected_reads_verify_security_metadata_before_and_after(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, changed: str,
) -> None:
    if module is benchmark:
        raw = {"authority_sha256": "a" * 64, "generation": 1, "signing_public_key": "b" * 64}
        read = benchmark._load_protected_authority_config
    else:
        prefix = "validator" if module is core else module.__name__.rsplit(".", 1)[-1]
        raw = {"activation_sha256": "a" * 64, "schema": getattr(module, f"{prefix.upper()}_AUTHORITY_PIN_SCHEMA")}
        read = getattr(module, f"_read_protected_{prefix}_pin")
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    reads = iter([payload, b""])
    descriptors = iter([11, 12])
    metadata = iter([
        _metadata(directory=True),
        _metadata(size=len(payload)),
        _metadata(size=len(payload), changed=changed),
        _metadata(directory=True, changed="gid" if changed == "directory" else ""),
    ])
    with monkeypatch.context() as patched:
        patched.setattr(os, "open", lambda *_args, **_kwargs: next(descriptors))
        patched.setattr(os, "read", lambda *_args: next(reads))
        patched.setattr(os, "fstat", lambda *_args: next(metadata))
        patched.setattr(os, "close", lambda *_args: None)
        if changed:
            with pytest.raises(ValueError, match="changed while reading"):
                read()
        else:
            read()


@pytest.mark.parametrize("module", [execution, inventory])
@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":' + b'[' * 100 + b'0' + b']' * 100 + b'}'])
def test_envelope_decoders_reject_duplicate_keys_and_excessive_depth(module: ModuleType, payload: bytes) -> None:
    with pytest.raises(ValueError):
        module._document(payload)


@pytest.mark.parametrize("module", [execution, inventory])
def test_envelope_decoders_bound_bytes_before_parsing(module: ModuleType) -> None:
    with pytest.raises(ValueError, match="bounded exact bytes"):
        module._document(b"x" * 9, maximum_bytes=8)
