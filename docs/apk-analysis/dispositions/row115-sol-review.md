# Row115 local review receipt

Intent: complete the accepted Comfort Motion 2.2.1 direct BLE implementation, selected explicitly under Jiecang app profiles, with exhaustive discovery dispositions. No other row, global queue, merge or deployment is in scope.

## Authority

| Artifact | SHA-256 |
| --- | --- |
| Artifact set | `ee964a8074ab8776f1b54ba936372ce22bcca8e1b37a0af95775959b633e7879` |
| Accepted report manifest | `3db8d22c26c6e9a73a13b9cc93055ab0d9df2572017d6ce576a4c1c2cc8fd431` |
| Supersession | `d66f50c4835aab4c81f59773a139937b9d495003016c162d230f9c5d0e5495fd` |
| Independent audit manifest | `718c801a22518c84d7b2e7b68acb77600707729071cdf1b93a83b03f2ed5a63f` |
| Audit prose | `4bbfc5ee7b7200b4c6393ead1ffe970e87c78b31d453987ef4842ee007a0ae1d` |
| Audit findings | `114d09e68fa51971094d7bdbe2eac1e374742d1ab016bf98740f4a16426ada47` |
| Acceptance record | `e18773021d6d1a1ed687443646b39f2ff06431203ced539aa83fad1cef079a90` |

The author independently verified all 38 report, 122 audit and 42 input members read-only. The accepted report is `work/report-repair-sol-002`, independent audit `audit/sol-round003`, both in the package/version row115 run. The full [implementation ledger](row115-comfort-motion.md) records 74 candidates, 33 actions, 24 variants and 25 cross-cutting rows: 113 IMPLEMENTED, 4 ALREADY_IMPLEMENTED, 39 EXCLUDED.

## Independent Sol loop

Both rounds used independent GPT-6.1 Sol reviewers with xhigh reasoning effort through the Codex provider. Each round was a fresh delegated review context, one reviewer at a time, with read-only source/evidence ownership and no children or GitHub writes. Review base: `c74cfe4611e4277b4db9380f5a45f94b812fef6e`. Raw review receipts remain machine-local, separate from this durable summary.

| Round | Scope | Verdict and evidence |
| --- | --- | --- |
| 1 | Entire base-to-working-tree change, including new files and surrounding real callers | CHANGES: one should finding S1. All 32 framed literals matched accepted evidence; no additional material ledger gap. Independently ran 321 controller/HA tests and 22 setup/profile tests. |
| 2 | S1 fix, affected platform callers, test and ledger reference | APPROVE: S1 RESOLVED. Independently ran all 322 affected tests, verified all 17 snapshot files unchanged, and restored old capability behavior only in memory to confirm the new test fails. No new delta bug. |

S1: inherited light-toggle capability remained true with local lighting disabled, exposing failing toggle/assumed-light controls. Fixed by returning the local light flag from `supports_light_toggle_control`. The actual HA setup test `test_disabled_light_has_no_controls` proves neither light entity nor light-toggle button is registered when disabled. No shared platform behavior changed for this fix. No findings were disagreed with or declined; no open blocker/should remains.

The code delta between rounds is one four-line capability property plus one actual-HA absence test and its ledger reference. It does not change bytes, timing, parser or lifecycle behavior. The round-two snapshot digest is `d3adbf9cd7c0652d47d0285de5754f50f355a144f32b976430f1576cd58da222`; each listed member was rechecked by the author after approval.

## Author validation

- Integrated related suite: 982 passed, covering this controller, existing Jiecang app config/controller/entities/services, controller contracts, profile ownership, general entities and generic services.
- After the sole Sol fix: all 322 affected tests passed. Both reviewers distinguish their independent validation from these author results.
- Repository-wide Ruff and Pyright passed with zero errors. Existing HA socket warnings are retained in local logs.
- No full-suite rerun or frontend build was needed: frontend source is unchanged, and focused contracts cover the small shared number-state change.
- Physical hardware/ATT/effect validation remains deferred to real users after beta/release, without claiming device testing.

Final local-review verdict: APPROVE. Configured remote Codex review and CI still gate PR convergence. No CodeRabbit preflight or review was run because the fresh repository policy is `primary_off=true`, Codex required.
