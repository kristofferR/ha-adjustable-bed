# BetterLiving2 1.3.0 (16), row082

Source: the root-accepted standalone FULL report for `com.ore.betterliving2`,
frozen acquisition 2026-07-14. Hardware is **UNVERIFIED**. This is not a new
latest-version claim.

- `vectors.json`: byte-for-byte copy of the accepted 100-vector file. Its
  95 outbound cases contain 78 commands, six calendars, eight alarm records
  and three queries. The five receive cases are not outbound encoding proof.
- `commands.json`: all 83 accepted command rows, with their original field
  values. Sixty-nine rows contain literals; fourteen contain parameterized
  formulas. Caller rows can overlap and are not unique-feature counts.
- `variants.json`: byte-for-byte copy of the six accepted route/layout entries.
- `receive.json`: the five receive rows selected without changing their values.
  The P1 `enabled` field is a raw projection, not the repaired stateful consumer
  or a claim about the physical bed alarm.
- `alarm_preferences.json`: byte-for-byte copy of the eight accepted local
  preference-priority cases. These are independent of wire encoding.
- `repair_observations.json`: the six accepted P1 consumer transitions and eight
  timer counterexamples, transcribed as data from the accepted repair. They
  preserve Android behavior as observations. They do not require HA to copy
  its untagged timer or unowned delayed STOP.

Report manifest pin:
`b06a1e1850c895ec1cb65841d07a6c71d47f7282a180e0e3dc311213a5ec8a2d`.
Final scoped audit002 findings pin:
`397b9e02d853cc3822b82352dee204d05a59b9783e390e3952fad06faace4a3a`.
Root acceptance supersedes the report's retained pre-acceptance wording.

The production proof imports the integration's candidate app packet functions;
it never imports or executes the analyst reproducer or repair evaluator. No
controller or codec-family registration was selected before proof PASS. The
single granted proof later passed all 95 outbound comparisons and two census
checks. Runtime/state/setup tests are separate and await their own grant.
