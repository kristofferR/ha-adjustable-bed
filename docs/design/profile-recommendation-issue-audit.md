# Closed-issue profile coverage audit

Ref [#677](https://github.com/kristofferR/ha-adjustable-bed/issues/677),
implemented in [#678](https://github.com/kristofferR/ha-adjustable-bed/pull/678).

The 2026-10-07 audit read every body and all comments from the complete closed
issue inventory: **259 issues, 801 comments**, issue numbers 1 through 670.
Four independent read-only passes covered disjoint numerical ranges. They
inspected 175 supplied images and relevant diagnostic attachments. No relevant
image was inaccessible. Complete per-issue disposition ledgers and downloaded
evidence remain machine-local; this document preserves actionable conclusions.
No APK was inspected or protocol behavior changed. Replays use current accepted
detection/routing metadata and synthetic addresses, keeping advertised fields
distinct from connected GATT and Device Information.

## Selection cases

| Historical evidence | Current assessment and coverage |
|---|---|
| [#73](https://github.com/kristofferR/ha-adjustable-bed/issues/73), [#171](https://github.com/kristofferR/ha-adjustable-bed/issues/171): RC2 incorrectly selected as Solace/Richmat; Octo confirmed working. | RC2's existing name detection directly suggests Octo. Correct Octo stays quiet. |
| [#73 Star2 sibling](https://github.com/kristofferR/ha-adjustable-bed/issues/73#issuecomment-3776379400): explicit Standard fails; Auto/Star2 moves motors. | Existing dedicated Star2 advertisement signal now offers advisory Auto/Star2 variant review. It does not promise to solve separate light/timing defects. Auto/Star2 stay quiet. |
| [#180](https://github.com/kristofferR/ha-adjustable-bed/issues/180): Dynasty DM9000, historical Keeson ORE selection confirmed. | Current Dynasty Bases app choice is included in cautious review for generic Keeson/Sino/ORE. Explicit Dynasty stays quiet. |
| [#185](https://github.com/kristofferR/ha-adjustable-bed/issues/185): Smartbed209, Okin Nordic failed, CB24 enabled movement. | Corroborated name/manufacturer identity offers CB24 among cautious candidates. Remaining preset defects are not claimed solved by switching. |
| [#194](https://github.com/kristofferR/ha-adjustable-bed/issues/194): QRRM141291, BedTech failed, Richmat WiLinke worked. | Shared FEE9 identity offers Richmat as a cautious candidate. Generic QRRM remote review also includes the existing BT6500 layout. |
| [#47](https://github.com/kristofferR/ha-adjustable-bed/issues/47), [#393](https://github.com/kristofferR/ha-adjustable-bed/issues/393): Smartbed428 Nordic identity, Malouf S755. CB24 explicitly wrong in #393. | Existing specific name/manufacturer detection offers Malouf New Okin without overstating its 0.85 confidence. Correct Malouf stays quiet. |
| [#311](https://github.com/kristofferR/ha-adjustable-bed/issues/311): KSBT improved when changed to KSBT04C; later code fixes also needed. | Existing KSBT name resolver now offers Auto/KSBT04C when a conflicting generic KSBT variant is explicit. No unique app is inferred from the ambiguous name. |
| [#372](https://github.com/kristofferR/ha-adjustable-bed/issues/372), [#413](https://github.com/kristofferR/ha-adjustable-bed/issues/413): Star25 BOX25 incorrectly overwritten as CB35. | Cautious review includes BOX25. Existing connection-time Star-name refinement also restores BOX25. Healthy generic BOX25 can still receive app review, without a switch recommendation. |
| [#410](https://github.com/kristofferR/ha-adjustable-bed/issues/410): QRRM157738, FEE9 and exact BedTech manufacturer payload, incorrectly Richmat. | The corroborated advertisement directly suggests BedTech. Manufacturer-less QRRM observations cannot establish this winner. Casper/Richmat QRRM in [#300](https://github.com/kristofferR/ha-adjustable-bed/issues/300) must not inherit it. |
| [#504](https://github.com/kristofferR/ha-adjustable-bed/issues/504#issuecomment-5457401850), duplicate [#560](https://github.com/kristofferR/ha-adjustable-bed/issues/560): L&P QRRM remote selector restores missing presets. | Unresolved Richmat QRRM now includes L&P QRRM and BT6500 remote-layout candidates, with no winner. Explicit remote settings remove these remote prompts. App review may still apply independently. |
| [#670](https://github.com/kristofferR/ha-adjustable-bed/issues/670#issuecomment-6026322551): verified Lumbar Star254202 to BOX25 restores numbered memory. | Existing bounded advertisement plus connected-table/manufacturer rule suggests BOX25. No extension to all Star devices. |
| [#116](https://github.com/kristofferR/ha-adjustable-bed/issues/116): working explicit RF TOPLINE; actual recovery was pairing. | Same-route legacy aliases are no longer offered as improvements, including with explicit remote variants. Generic app review does not assert the remote is wrong. |

## Existing runtime correction

[#406](https://github.com/kristofferR/ha-adjustable-bed/issues/406) (OKIMAT model,
RF ECO to Okin UUID), [#370](https://github.com/kristofferR/ha-adjustable-bed/issues/370)
(NORA Device Information, Richmat to Okin 64-bit), and
[#358](https://github.com/kristofferR/ha-adjustable-bed/issues/358) (Malouf New to
Legacy from GATT) are already corrected during normal connection. The existing
refiners run before `_apply_runtime_bed_type_correction()` persists the effective
route and before the connected recommendation callback. They need no duplicate
Repairs notice or weaker advertisement-based guess.

`tests/test_detection.py` covers these exact refinements;
`tests/test_coordinator.py` covers correction persistence, Malouf override
preservation, NORA correction and the full QRRM connection path.

## Evidence limits and negative cases

- [#289](https://github.com/kristofferR/ha-adjustable-bed/issues/289) documents a
  Nordic-only Richmat auto fallback defect. Current auto selection already uses
  connected GATT correctly. There is no captured advertisement or user-confirmed
  explicit variant switch to replay. The suggestor cannot establish Nordic-only
  GATT from absent advertisement fields and does not invent a variant match.
- [#501](https://github.com/kristofferR/ha-adjustable-bed/issues/501) has a current
  CST/MF900 route, but its raw capture has no configured wrong entry and no
  advertised UUID/manufacturer. Upgrade success does not prove a specific profile
  switch. Quiet on that passive identity is appropriate.
- [#229](https://github.com/kristofferR/ha-adjustable-bed/issues/229) includes the
  Keeson candidate for BetterLiving, but the final saved choice was not recorded.
  [#244](https://github.com/kristofferR/ha-adjustable-bed/issues/244) lacks a proven
  replacement for a Hi-Lo layout. Neither supports a new unique matching rule.
- [#1](https://github.com/kristofferR/ha-adjustable-bed/issues/1) and
  [#130](https://github.com/kristofferR/ha-adjustable-bed/issues/130) lack enough
  identity to infer a remote or profile. Physical controls/app choice can guide
  manual configuration; missing bytes are not guessed.
- [#508](https://github.com/kristofferR/ha-adjustable-bed/issues/508) and
  [#510](https://github.com/kristofferR/ha-adjustable-bed/issues/510) were fixed by
  control implementation while Auto stayed selected. Recommending another profile
  is not a substitute for those fixes.
- Nearby scales/watches ([#187](https://github.com/kristofferR/ha-adjustable-bed/issues/187)),
  a different Dialog device ([#296](https://github.com/kristofferR/ha-adjustable-bed/issues/296)),
  SwitchBot ([#332](https://github.com/kristofferR/ha-adjustable-bed/issues/332)),
  Jura ([#450](https://github.com/kristofferR/ha-adjustable-bed/issues/450)) and Apple
  TV ([#577](https://github.com/kristofferR/ha-adjustable-bed/issues/577)) do not
  acquire bed-profile recommendations on the available observations. Selecting
  the wrong physical device cannot be repaired by picking another bed protocol.

Focused replays are in `tests/test_profile_recommendation_history.py`; lifecycle,
safe configuration handoff, persistent decisions, pairing and the #670 override
are in `tests/test_profile_recommendations.py`. This establishes coverage for the
recorded evidence, not universal hardware compatibility or perfect detection.
