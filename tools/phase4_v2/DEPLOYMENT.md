# Phase 4 v2 activation gates

The tooling library and synthetic acceptance harness are implemented. This is not yet a turnkey
bulk runner. Do not replace the #443 workflow or start untouched APKs until every gate below passes.

## Selected execution path: T3-managed agents

The maintainer selected the existing T3-managed workflow, not a new standalone worker service.
Prepare the accepted-artifact benchmark through fresh analyst contexts using the unchanged #443
prompt and schema. Keep prior reports and the frozen benchmark oracle outside analyst inputs.
The coordinator owns package assignments, persistent attempt directories, validation, independent
audit handoffs, and milestone tracker updates. No untouched bulk artifacts may start.

Before trials, freeze the exact 8–12 accepted artifact sets, oracle, trial order, tool versions,
and timing/token collection method. Record the actual execution mode in every result. Checkpoint
assignments and frozen output hashes so a resumed chat can recover without repeating accepted work.
Do not claim a process or filesystem isolation guarantee from a fresh conversation alone.

This workflow does not impersonate the signed-service APIs below. Do not install fixture keys,
bypass production guards, or describe manually checked reports as authenticated queue completions.
T3 benchmark results can establish only the quality and performance of the workflow actually run;
they do not certify the undeployed signed-service pipeline. Its adoption remains separately gated.

## Optional signed-service deployment: worker boundary

Implement the host adapter for `orchestration.launcher.FreshContextAdapter`. It must start each
analyst in a fresh context with access only to its frozen inputs, protocol-neutral instructions,
tools, and isolated output workspace. The analyst must not inherit repository history, credentials,
other reports, or the coordinator's conversation.

A separate trusted process must own preparation signing and queue writes. Analysts must run under
a different OS UID and must not read that process's keys or memory or write its database, WAL, SHM,
parent directories, or executable code. Expose specific validated operations, never arbitrary
Python evaluation, shell execution, signing, or caller-supplied completion snapshots. The trusted
process must reconstruct completion facts itself. Neither private Python classes nor a
caller-selected SQLite file provides this separation.

For this deployment mode, the adapter and trusted service are outstanding implementation work.
They are not prerequisites for preparing the T3-managed benchmark. Do not install a nominal
service that simply runs analyst-controlled Python with the signing credentials.

## Optional signed-service deployment: operator installation

Installation requires root on the execution host. Install bubblewrap, GCC with static libc,
the real decompiler runtimes, and the root-owned GitHub CLI at `/usr/bin/gh`. Verify user namespaces
work for the chosen sandbox. Register the exact real tool binaries, versions, arguments, output
contracts, and runtime closures; synthetic registry entries are not deployment inputs.

Create `/etc/ha-adjustable-bed` owned by root with no group/other writes. Generate fresh signing
keys in the trusted service, never copy fixture keys. The preparation executor key is exactly
32 raw Ed25519 bytes in `phase4-v2-preparation-executor.ed25519`, root-owned mode `0600` or stricter.
Install canonical authority documents and their matching pins using the exported payload builders:

- Preparation, validator, validator execution, target inventory, exact reuse, and raw source.
- Stage authorities and tracker publication configuration.
- Benchmark authority only after committing the blinded plan, oracle, schedule, and collector.
- `phase4-v2-queue.json` with revision `phase4-v2-queue-deployment-v1`, canonical absolute database
  path, distinct `writer_uid` and `analyst_uid`, and the actual database `device` and `inode`.

Use mode `0444` or stricter for public authority/pin documents and keep secret keys inaccessible
to analysts. Give only the trusted publisher its `GH_TOKEN`; it uses explicit `github.com` and
does not inherit host, home, proxy, or executable-path overrides. Use an existing dedicated tracker
branch whose protection forbids force pushes and deletion.

On the host inspected on 2026-09-05, `/etc/ha-adjustable-bed` was absent and `sudo -n true` required
a password. No production authority was installed or emulated by this session.

## Acceptance before bulk

1. Exercise the selected T3 handoff and recovery procedure with synthetic inputs before real trials.
   If adopting the signed-service mode, also exercise its real adapter and service, including stale
   leases, a failed decompiler with authoritative fallback, and persisted publication receipt reload.
   Demonstrate its analyst UID cannot access credentials or change queue state directly. Do not
   credit these service-specific guarantees to a T3-only trial.
2. Reconcile the 30 permission-opaque legacy inventory paths read-only into a new generation, or
   obtain explicit acceptance of the named coverage limitation. Never chmod or rewrite old evidence.
3. Select 8 to 12 already accepted artifacts for #550. Freeze the oracle separately before fresh
   analysts start, retaining exact artifact identities, split sets, and all legacy reports.
4. Execute the committed trial order, each case in plan order, LEGACY then V2 without overlapping
   intervals. Record real durations and orchestration tokens; never substitute synthetic timings.
5. Require all material findings, zero unexplained candidates, accepted independent audits,
   historical mutation coverage, at least 3x throughput, and at least 5x lower orchestration/token
   cost. A failed gate rejects rollout and names the specific remediation.
6. Freeze the accepted routing ledger and synchronize #436, #443, #447, #542 and the published queue.
   Verify completion excludes accepted packages and retains all incomplete work.
7. Leave the queue stopped. Bulk launch still requires the maintainer's command.
