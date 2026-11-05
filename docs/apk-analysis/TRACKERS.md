# APK Protocol Audit tracker issues

Three GitHub issues hold the audit's durable public state. They are reference
pages, not logs. A reader should learn the current state of any work unit from
one table row, without scrolling past run history.

| Issue | Owns |
|---|---|
| [#436](https://github.com/kristofferR/ha-adjustable-bed/issues/436) | Current counts and the single ordered queue, one row per work unit |
| [#443](https://github.com/kristofferR/ha-adjustable-bed/issues/443) | The audit method and gates, plus accepted evidence for scheduled queue rows |
| [#447](https://github.com/kristofferR/ha-adjustable-bed/issues/447) | Early and post-cutoff analyses: intake, accepted exclusions and their records |

Run progress has its own homes. Worker launches, review rounds, CI results,
retries, authorizations, receipts and handoffs go in the machine-local run
handoff and the [live status page](https://plans.kristofferr.com/d/1aydd9y2s65x).
They never go in a tracker body or a tracker comment.

## Editing a tracker

Change only what moved, in place:

- A unit changes stage: edit its queue row in #436, and the counts in #436's
  Status table if they changed.
- A report or cluster is accepted: add one row to the matching evidence table
  (#443 for scheduled rows, #447 for early or post-cutoff work). Give the
  package, exact version, seals and a short note in plain words.
- An implementation merges: set the queue row to `MERGED` with the PR link.
  The disposition ledger in `docs/apk-analysis/dispositions/` holds the detail.

Never:

- Add text above the first section, or add, rename or reorder `##` sections.
- Prepend or append a dated "current run" journal or status paragraph anywhere.
- Copy the same paragraph into several trackers. Link to the owning tracker.
- Put hashes, review state or CI state in #436. Queue cells are short status
  lines, at most 160 characters.
- Abbreviate or strip spaces to fit a size budget. If a record does not fit,
  it belongs in the owning disposition ledger or the handoff.
- Post status comments on a tracker issue.

## Guard

`.github/scripts/apk_tracker_guard.py` encodes these rules: the fixed first-line
marker, the exact section list, section and body size budgets, the queue table
format, and readable prose. Check a draft before publishing it:

```sh
python3 .github/scripts/apk_tracker_guard.py check 436 draft.md
gh issue view 436 --json body --jq .body | python3 .github/scripts/apk_tracker_guard.py check 436 -
```

The `APK tracker guard` workflow runs the same check on every edit to the three
issues. When an edit breaks a rule and the previous body passed, it restores the
previous body and fails the run, so the failure shows in Actions and nothing
needs to be cleaned up by hand.

To change the structure itself, for example to add a section, change the
`TRACKERS` table in the guard script in a reviewed PR first, then edit the issue.
