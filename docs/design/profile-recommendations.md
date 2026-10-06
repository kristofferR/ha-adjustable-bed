# Profile recommendations

Ref [#677](https://github.com/kristofferR/ha-adjustable-bed/issues/677).

`profile_recommendations.py` checks every configured bed profile, including fresh
entries and paired beds. It reuses the existing advertisement detector and the
known app choices in `profile_review.py`. It never opens a connection, probes a
command, reads another characteristic, or switches protocols to test a hypothesis.
No detection predicate or bed protocol changes are introduced by this feature.

## Assessment

- A high-confidence, unambiguous detector disagreement with no required
  characteristic check or related app alternatives offers a **possible better
  match**. Detection confidence ranks existing signatures; it does not prove the
  bed's controls or quantify a probability of compatibility.
- A corroborated identity with multiple supported routes or known related app
  choices offers **app/product review**, without selecting a winner. This also
  covers generic profiles whose correct app cannot be determined over Bluetooth.
- An explicitly selected matching app, an accepted alternative, or an existing
  legacy alias is kept. No known match, a weak match, or a bare ambiguous shared
  service produces no notice. A new app's existence alone is insufficient.
- More specific, verified evidence can improve an assessment. The reported
  Star254202 case below remains one such rule, rather than the feature's scope.

Generic assessment uses the detector's existing confidence categories: below 0.6
is insufficient; below 0.9 also needs a name, manufacturer or MAC signal. A clear
suggestion needs at least 0.9, no ambiguity, no characteristic-check requirement,
and no known related app choices. App candidates come from existing supported
profile metadata, never assumed controller-family equivalence.

## Review and dismissal

Repairs explains the current profile and either a proposed match or the available
app/product choices. Generic notices explain that controls and automations may
change; verified rules can give a specific controls comparison. Standalone Review
hands off to Configure. A unique suggestion re-renders its settings without saving;
an ambiguous assessment keeps the current selection. Only the user's subsequent
submission applies settings. Closing settings keeps the current profile and notice.
Saving a Repairs handoff confirms the selected route, including a choice to keep
an ambiguous generic profile, so it does not immediately ask again.

Keep current profile, including Home Assistant's native Ignore action, stores a
decision in the reserved `profile_recommendations` slot of the per-address app-state
store. It does not reload or disconnect the bed. Decisions survive restarts,
integration/HA updates and pair/split ownership transfers. Removing the last entry
owning an address removes its app-state store as usual. An ongoing assessment also
suppresses a duplicate one-time upgrade notice without mutating its migration mark.

Generic decision keys include the assessment kind, configured route/variant and
sorted candidates. A materially different selection or candidate set can ask
again; RSSI, serial suffixes, translated labels and release versions cannot.
Verified rules retain their own stable evidence keys.

Observers retain the last advertisement and connected controller diagnostics
within the setup session while Bluetooth history expires or the bed disconnects.
New observations replace them, including failed manufacturer reads and conflicting
identities. A restart waits for observations again. Missing optional advertisement
fields are normalized, addresses are compared case-insensitively, and unchanged
advertisements do not repeat detection/logging.

Two-address pairs have independent observers and decisions per physical address;
notices identify the affected side. Single-address pairs observe their one physical
coordinator once. Paired Review opens Configure and explains the existing explicit
split or restore-standalone action. It never changes either side or splits a pair.

## Specific verified rule: Lumbar to BOX25 for Star254202

This deliberately narrow rule requires all of:

- Configured `adjustable_lumbar` with auto or the explicit Star variant.
- Observed `Star254202` followed by six decimal digits, case-insensitively.
- The existing detector selects `sleepys_box25`, requires no characteristic
  check, and has no alternative except the known shared-name `starcode_abm5_4`
  candidate. A generic detector disagreement is never sufficient.
- The already connected controller reports branch `star`, table `35_22_01`, and
  the exact manufacturer bytes `STAR`. No extra Device Information read is added.

The six-digit suffix is the unit-specific part of the observed name, not a
universal naming rule. Other model prefixes, incomplete names, manufacturer values,
protocol tables and newly ambiguous detection results do not qualify.

### Evidence and limits

The accepted row054 report for `com.okin.bedding.adjustablelumbar` 1.2.2 (33)
proves the existing current-profile selection and the absence of reachable
numbered-memory actions. Its artifact-set hash is
`ed65ed1b4970c95c2b1744687f94401447f851f23e81f8af6699a68854988b08`;
accepted `REPORT.SHA256` hash is
`39a64e7895b238a518498a671a37ae686252b8a68156ecf8a6b261ddb610050d`;
`analysis.json` hash is
`43073da1665399a64c146aa32e2040c91f3cd9e53850a212591e37ab03e0ced1`.
The frozen report manifest was verified before reuse. See the existing
[row054 dispositions](../apk-analysis/dispositions/row054-adjustable-lumbar.md).
No APK was reanalyzed, no audit acceptance was changed, and no queue unit was
advanced by this notification feature.

The [support bundle and control-box photograph in #670](https://github.com/kristofferR/ha-adjustable-bed/issues/670#issuecomment-6026118933)
add the observed Star254202 name, `STAR` manufacturer, model `254202`, selected
Lumbar profile, and runtime table. The photograph shows an OKIN control box with
head, foot, lumbar and head-tilt connections, but does not by itself establish a
unique app profile. The [user's follow-up](https://github.com/kristofferR/ha-adjustable-bed/issues/670#issuecomment-6026322551)
confirms that switching to BOX25 restored Memory 1 saving and recall. This is
hardware confirmation for that user's bed, not all beds with that identity.
The notice therefore says **may**, never promises compatibility or automatically
selects a protocol. Tests use a synthetic unit suffix and address.

The controls comparison reads the current controllers' public capabilities:
BOX25 exposes numbered memories; Lumbar's custom named-save, wave, Massage On
and Check Massage buttons disappear on switching, as does its Incline preset
(BOX25 exposes TV). These are entity-surface differences, not assertions that
named preset positions or physical meanings are equivalent. No additional
hardware capability is inferred and no packet, timing or controller is changed.

### Feature dispositions and verification

- `IMPLEMENTED`: universal assessment, the specific recommendation, passive
  observation, persistent dismissal, stale-notice rejection, configuration handoff
  and paired-side isolation.
  Covered by `tests/test_profile_recommendations.py`.
- `ALREADY_IMPLEMENTED`: current-profile table/manufacturer selection and controls,
  `beds/adjustable_lumbar.py`, `tests/test_adjustable_lumbar.py`; target-profile
  numbered memories, `beds/sleepys_box25.py`, `tests/test_sleepys.py`.
- `EXCLUDED`: none of the requested notification behavior. Other model identities
  remain unsupported by this rule because there is no equivalent matching evidence;
  they are not declared incompatible or queued for guessed protocol changes.

Additional verified overrides need their own exact evidence, controls comparison
and focused tests. Generic assessment remains advisory; it does not create new
protocol facts or establish physical compatibility.
