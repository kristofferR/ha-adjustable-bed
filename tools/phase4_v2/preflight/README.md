# Phase 4 v2 preflight

This package inventories APK deliveries without extracting into or modifying the source tree.
It produces two identities:

- `delivery_digest` identifies the exact caller-supplied files.
- `artifact_digest` identifies the logical APK member set, independent of XAPK/APKS packaging.

Package identity is derived from the sealed APKs with `aapt2 dump badging`; `apksigner verify`
cryptographically verifies each APK and supplies its signer-certificate digests. A verified install
set has exactly one base, unique split names, identical package/version/signer identity, and every
required `uses-split` present. Missing tools, malformed or unsigned APKs, ambiguity, and any mismatch
remain precise fail-closed blockers.

The v3 classification contract inventories every logical APK exactly once. Each member records a
canonical, sorted set of application substrates and the routes derived from a closed stack-to-route
table. It recognizes Android resources and DEX, native libraries, Flutter, React Native and Hermes,
AIR, shipped code bundles, and embedded archives. Resource-only splits retain the Android/apktool
route instead of being mistaken for an unknown application. Missing Android manifests and members
with no recognized application substrate remain member-specific blockers. Aggregate stacks and
routes are exact unions of the member records. The aggregate decision is `READY` only when the
artifact set is non-empty, package/version/signer/split identity is verified, every APK member is
classified, and neither the member nor aggregate decision has a blocker.
The apktool route is retained alongside jadx for DEX-bearing APKs so its smali output is available
as the deterministic fallback when later jadx coverage is suspicious or incomplete.

`READY` means that byte identity and deterministic routing are safe to hand to later preparation
stages. It does not claim that the required decompilers have run.

`execute_preparation` consumes a live `READY` result and an explicit `ToolSpec` for every routed
tool. Each specification pins the version command, normalized arguments, and deterministic flags.
The executor additionally hashes the resolved executable, captures bounded stdout and stderr,
rejects warnings, crashes, partial output, unsafe output nodes, and input or binary mutation, then
publishes a sealed package-local manifest and a protocol-neutral BLE API candidate index. A jadx
run that produces no Java or Kotlin source is accepted only as a recorded fallback when the same
APK member has a complete apktool result containing smali.

Complete invocations are cached by the input member digest, tool binary and version, arguments,
flags, schema revisions, and pipeline revision. Cache hits are fully rehashed. Tool paths, temporary
paths, cache-hit state, and analyst annotations are not part of the stable manifest. Callers provide
the tool specifications so installation-specific wrapper paths do not become an implicit execution
contract. `PREPARATION.COMPLETE` or `PREPARATION.BLOCKED` is published last beside the manifest and
candidate index.

Cache objects contain APK bytes and byte identity only, are addressed by cache-schema revision plus
`artifact_digest`, and never retain package identity or classification output. Mutable processing
status is separately namespaced by pipeline revision. Materialization always copies verified bytes
and never hardlinks.

This slice requires Linux interfaces including `fcntl.flock` and `renameat2`; it also uses
`O_NOATIME` where the filesystem permits it. ZIP64 deliveries are rejected because the bounded
ZIP64 central-directory parser is not implemented yet. Operators should account for these platform
and archive limits when diagnosing rejected large `.apks` or `.xapk` deliveries.

Preflight seals every supplied delivery file and each expanded APK member into private temporary
storage. Peak use can therefore approach the supplied delivery bytes plus the expanded APK-member
bytes. Production runs should pass a persistent, capacity-checked `sealing_directory`; omitting it
uses the host `TMPDIR` default.
