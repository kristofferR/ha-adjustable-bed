# Evidence-backed profile recommendations

Ref [#677](https://github.com/kristofferR/ha-adjustable-bed/issues/677).

`profile_recommendations.py` evaluates observations from normal connections and
passive advertisements for existing and newly configured beds. It never opens a
connection, probes a command, or changes a profile to test a hypothesis. This
operates independently of `profile_review.py`'s one-time upgrade review.

A Repairs notice explains the current profile, the suggested profile, the reason,
and known changes to controls. Review hands off to the existing options flow:
selecting the suggested bed type re-renders its settings, and only the user's
subsequent submission saves them. Cancelling leaves both the configuration and
notice intact. Existing device and matching entity IDs use the options flow's
normal preservation behavior. Removed controls can affect automations.

Keep current profile, including Home Assistant's native Ignore action, stores a
decision in the reserved `profile_recommendations` slot of the existing per-address
app-state store. It does not reload the entry or disconnect the bed. Decisions
survive restart, integration/HA updates and pair/split ownership transfers. Removing
the last entry owning an address removes its app-state store as usual.

Rule IDs identify materially distinct recommendations. Do not change them for a
release, wording change, RSSI, display-name change, or serial suffix. A new rule
requires new evidence and a documented reason to ask again. A dropped connection
retains the last observation within the setup session; the next successful
connection replaces it, including an unsuccessful manufacturer read. Setup waits
for normal observations again after a restart. Conflicting observations withdraw
the notice. Repeated advertisements do not repeat detection or its log messages.

Two-address pairs have independent observers and decisions per physical address.
The notice names the affected side. Review opens the existing Configure menu and
explains the required explicit split; it never changes or splits either side.
The initial source profile does not support single-address pairing.

## Initial rule: Lumbar to BOX25 for Star254202

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

- `IMPLEMENTED`: the narrow recommendation, passive observation, persistent
  dismissal, stale-notice rejection, configuration handoff and paired-side isolation.
  Covered by `tests/test_profile_recommendations.py`.
- `ALREADY_IMPLEMENTED`: current-profile table/manufacturer selection and controls,
  `beds/adjustable_lumbar.py`, `tests/test_adjustable_lumbar.py`; target-profile
  numbered memories, `beds/sleepys_box25.py`, `tests/test_sleepys.py`.
- `EXCLUDED`: none of the requested notification behavior. Other model identities
  remain unsupported by this rule because there is no equivalent matching evidence;
  they are not declared incompatible or queued for guessed protocol changes.

Future rules need their own exact evidence, controls comparison and focused tests.
Shared UUIDs, newly released app profiles, and generic confidence thresholds are
not substitutes for that evidence.
