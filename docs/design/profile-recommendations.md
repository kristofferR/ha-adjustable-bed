# Profile recommendations

Ref [#677](https://github.com/kristofferR/ha-adjustable-bed/issues/677).

`profile_recommendations.py` checks every configured bed profile, including fresh
entries and paired beds. It reuses the existing advertisement detector and the
known app choices in `profile_review.py`. It never opens a connection, probes a
command, reads another characteristic, or switches protocols to test a hypothesis.
No detection predicate or bed protocol changes are introduced by this feature.
The [closed-issue audit](profile-recommendation-issue-audit.md) records historical
selection failures and the evidence available to assess them.

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
is insufficient; below 0.9 or any ambiguity also needs a name, manufacturer or MAC
signal. A shared service with ambiguous alternatives stays quiet even at 0.9.
A clear suggestion needs at least 0.9, no ambiguity, no characteristic-check requirement,
and no known related app choices. App candidates come from existing supported
profile metadata, never assumed controller-family equivalence.
For Keeson Auto, app lookup uses the existing dedicated JSON detector signal,
corroborated Sino detector signal, or generic KSBT name resolver shared with the
controller factory, with Base as its fallback. KSBT04C and KSBT03CR stay quiet;
generic KSBT offers only its existing Adjustable Lite candidate. Base and Sino
use their narrower app lists instead of the broad historical Auto upgrade list.
These are advisory candidates, not proof of a particular app or control layout.

Ordinary protocol variants can also need review. The existing dedicated Octo
Star2 detector signal questions an explicit Standard selection. Keeson's existing
KSBT name resolver, shared with the controller factory, and corroborated Sino
detector signal question a conflicting explicit generic variant, including Base.
Auto and explicit reviews use the same observed-transport resolver. Its dedicated
JSON service takes precedence over Sino and KSBT names and can also question an
explicit app variant configured through the protocol-variant selector. Shared
names preserve those explicit app selections, including Sleep Harmony and Purple;
the selector's app metadata alone does not identify every app-specific variant.
These reviews list Auto and the observed generic variant,
open settings unchanged, and require user confirmation. Auto is not questioned
for these transport differences; it already resolves them on normal connection.

QRRM does not identify the physical Richmat remote layout. A corroborated Richmat
QRRM identity with Auto/generic QRRM remote settings includes the existing L&P
QRRM and BT6500 remote selections alongside app candidates. Closed issues confirm
both layouts on QRRM receivers, but neither is selected or presented as a unique
match. An explicit remote setting is respected. Remote candidates are labels for
Configure's separate remote field, never submitted as bed-type selector values.
Legacy aliases resolving to the current protocol are excluded from candidates.

## Review and dismissal

### Tempur compatibility entries

The [ProSmart Air report in #681](https://github.com/kristofferR/ha-adjustable-bed/issues/681)
identifies two `KSSF05C` receivers, advertising Nordic UART and configured with
Adjustable Lite. Once the separately registered Tempur Sleeptracker-AI profile
is available, that combination receives a targeted app review. The bounded
name shape and selected variant identify a reported compatibility setup, not
the official app or a processor endpoint for every similarly named bed. The
notice asks the user to confirm they use Tempur Sleeptracker-AI.

The [accepted processor implementation in #684](https://github.com/kristofferR/ha-adjustable-bed/pull/684)
uses a different BLE endpoint. Review therefore shows instructions to add the
actual processor with its own profile and verify its controls before retiring
the UART entries. It does not open their options flow, split a pair, send a
command, or claim preserved entity IDs on the newly added device. Paired notices
remain scoped to each physical address. Acknowledging the guide records a
durable dismissal, not a completed or verified processor migration. Closing it
records nothing. The rule stays silent until the companion profile is registered,
so either PR can merge first. Focused tests replay both reported names, negative
identities, profile availability, safe setup guidance and paired-side isolation.
No APK was reanalyzed and no protocol behavior changes in this notification rule.

### Existing endpoint reviews

Repairs explains the current profile and either a proposed match or the available
app/product choices. Generic notices explain that controls and automations may
change; verified rules can give a specific controls comparison. Standalone Review
hands off to Configure. A unique suggestion re-renders its settings without saving;
an ambiguous assessment keeps the current selection. Only the user's subsequent
submission applies settings. Closing settings keeps the current profile and notice.
Saving a Repairs handoff confirms the selected route, including a choice to keep
an ambiguous generic profile, so it does not immediately ask again. A rule for
the selected route is confirmed only while the evidence still produces the
assessment presented at handoff. New assessments remain visible after saving.
Single-address paired settings run the same decision and completion hooks as
standalone settings, including unchanged saves.

Keep current profile, including Home Assistant's native Ignore action, stores a
decision in the reserved `profile_recommendations` slot of the per-address app-state
store. It does not reload or disconnect the bed. Decisions survive restarts,
integration/HA updates and pair/split ownership transfers. Removing the last entry
owning an address clears app preferences but retains the reserved decision slot,
so re-adding the bed or capturing its raw address preserves support evidence.
An ongoing assessment also
suppresses a duplicate one-time upgrade notice only when the relevant physical beds
have a replacement assessment covering that review or a saved decision confirming it.
An unrelated active recommendation leaves the upgrade notice visible; coverage
is cached with the assessment's evidence so RSSI updates do not repeat detection.
Offline or unassessed beds retain their pending upgrade review. Confirmation keys
include the physical bed's route/variant and known app choices, so unrelated old
decisions cannot suppress it. A decision confirms the upgrade review only when
the assessment presented every candidate in that review. Keeping an unrelated
mismatch restores the pending app review. The migration mark is not mutated.
Coverage uses the watcher's retained advertisement when global Bluetooth history
expires, matching the evidence used to present the assessment.

Generic decision keys include the assessment kind, configured route/variant and
sorted candidates. A materially different selection or candidate set can ask
again; RSSI, serial suffixes, translated labels and release versions cannot.
Verified rules retain their own stable evidence keys.

## Decision history in support exports

The same per-address slot retains an append-only history alongside suppression
flags. Every Keep, native Ignore, or validated settings submission through Review
records a UTC timestamp, the decision source, original rule/current profile,
suggested profile/candidate list, every confirmed rule, and the previous and selected profile selectors.
Changing selectors records `accepted`; keeping them records `dismissed`.
Cancelling or failing validation/hardware commit records neither. Acceptance means the
user chose those settings, not that the controls were physically verified.
PINs, names and unrelated entry data are not copied into decision history.

History and flags are saved atomically after settings commit actions. A failed
hardware transaction never confirms the review. If the subsequent history write
fails, the completed choice stays in memory for support exports and a delayed
storage write is scheduled; it does not abort already committed settings or their
entry unload. A failed unload flush retains the pending data and schedules another
retry. Taking a background snapshot does not clear its pending state.
Entry-unload saves share the decision-update lock, so a reload cannot queue an
older app-state snapshot that loses a decision while its write is in progress.
Keep/Ignore require a successful immediate write. A failed native Ignore resets
HA's ignored state so the user can retry the notice without losing the decision.
When evidence changes during an Ignore write, the replacement rule clears the
old native Ignore flag before publication. The original decision still records
only the rule presented to the user; the replacement remains visible.
An accepted unique match is retained even if the new route needs no further assessment.
After a successful settings save, the notice is refreshed immediately, including
when unchanged entry data produces no Home Assistant update-listener event.
If an unconfirmed assessment loses its qualifying evidence, the still-pending
upgrade review is restored during the same setup session.

Every support bundle includes `profile_recommendations.history`, loaded from the
capture's physical address, independent of runtime observers or logging options.
This covers configured devices, paired physical-side targets and raw-address
captures. HA diagnostics and the older support-report format export it too, with
paired diagnostics keeping each address's history in its own side section.
Legacy boolean dismissals are exported in `legacy_dismissed_rules`; their missing
timestamps and profile details are not reconstructed or invented.
Newly confirmed rules remain associated with their history event, including
rules recomputed for the selected profile. Older events lacking that rule list
are exported unchanged.

`tests/test_profile_decisions.py` covers durable append, concurrent decisions,
address isolation, removal/re-add retention, legacy flags and selector-only data.
Recommendation, support-bundle and diagnostics tests cover the actual UI actions,
successful/failed saves, cancellation and future captures after storage reload.

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
