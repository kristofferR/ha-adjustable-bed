# Row121 HJBed 2.1.2 dispositions

This is the separate source-comparison implementation of accepted
`com.richmat.hjbed` 2.1.2/code 21200. It does not amend a frozen analysis or audit.
The [machine ledger](row121-hjbed.json) gives every item exactly one disposition,
with source evidence and implementation/test references. Resolve each row's `proof_ref` and `reason_ref` through the top-level lookup tables.

| Inventory | Count |
| --- | ---: |
| Accepted candidates | 582 |
| Reachable command rows | 99 |
| Compiled / selectable / current / conditional products | 46 / 43 / 19 / 24 |
| Static / reachable details | 73 / 70 |
| Function enums | 260 |
| Parsed events / app consumers | 70 / 10 |
| Transport sinks | 11 |
| Structural / effective product bindings | 780 / 724 |
| Total durable ledger items | 1510 |
| IMPLEMENTED / ALREADY_IMPLEMENTED / EXCLUDED | 1208 / 0 / 302 |

The 1510 items include the candidates, commands, all structural bindings, receive
rules, feature domains and explicit state/timing/configuration paths. They are
not 1510 distinct commands. No protocol item is credited as already implemented
based on family resemblance.

All 99 reachable command rows are implemented. The 780 binding rows separately
exclude shadowed products and structural menu entries the actual selector never
uses. Eight independent static MusicPage routes survive those exclusions.
All in-scope passive bed events remain structured HA state even when the phone
has no subscriber. Desk/monitor-only and firmware events remain excluded.
Repeat-alarm query clears the observed list before replies (`6daf40/6daf80`),
and deletion removes the first full-equal selected bean (`7b7ed0/7b7efc/7b2f50`).
Single-alarm countdowns subtract epoch seconds (`7952f4/7956a8–79571c`), retaining
minute truncation and the 86400-second fallback across DST offset changes.
Normal/Motion callback registration identities are preserved separately in the
ledger; their shared model operations do not imply shared closure identity.

## Accepted identity

- Artifact set: `bd3a5e96393fb32be9059fbb9a0eae5639deb7f0d761b4a27b3b382433c4d291`.
- REPORT.SHA256: `88ce24aebae03a2a83fb0527d5b679329aaedc6624fd9a5c7efeb10fdf45d3f0` (601 members).
- EVIDENCE.SHA256: `9c8f459ecdffe9d7041d50ba79c9e3bdbc45eca3d84db6a46977c35dacc2880a` (13510 members).
- SUPERSESSION: `1e61acdbdce5a9a4ecfe8ede37561cab1116177982ebe93d357231a3279d745e`.
- Independent sol-round003 audit: `1924a67790cf5e1f6c153a9322d9f0854941aed92e704e441ffe8a3c5cc81220` (786 members).
- Findings: `569dc05eac3eb925779768e446a803d5d60309423c60c67935faf2deec874338`.

The implementation owner independently reverified every exact seal/member and
all 91 input members before comparison. Older negative/blocked reports and audits
remain immutable; none is used as acceptance. Reports, APKs and extraction output
stay machine-local. Only durable implementation, vectors and dispositions ship.

## Narrow safety and host mappings

- **S01, zero-length receive frame:** source `6fc4c0` cannot progress. Reject and
  clear only that input, dispatch no queued local frame. Other split, dispatch,
  callback, remainder and timer effects retain their source ordering.
- **S02, imported alarm toggle:** source `7b74e4` reconstructs kind1 without its
  data. Preserve the received custom payload when changing the enabled bit.
  Normal kind0 behavior and the exact serializer are unchanged.
- **S03, invalid menu fallback:** source `7ba5bc` maps an unknown menu to HEADUP.
  HA accepts only selected catalog controls, avoiding unintended movement.
- **S04, full alarm table:** the source returns -1, masked to `ff` by the plugin.
  Reject a new implicit slot when all seven valid numbers are occupied. Existing
  alarms and valid explicit slots remain available.
- **S06, unknown/pending alarm occupancy:** `_handleExtraProtocolAlarm@706f68`
  emits individual list/escalation beans, with no proven end or empty-table
  marker. The app's first-unobserved slot selection cannot prove a slot is free.
  HA therefore requires an explicit slot unless one was deleted in this live
  connection and has not since been observed occupied. Automatic reuse selects
  the smallest such slot, rechecks availability after write pacing under the BLE
  lock, and reserves it before awaiting the write. A late occupied-slot reply
  rejects implicit allocation before any add frame is sent. Query,
  disconnect and controller replacement discard free-slot knowledge. Uncertain
  write failures retain the reservation; no query-completion timer is invented.
  Explicit slot writes, received beans, delete/query behavior and packet builders
  remain available unchanged. Availability is host metadata, not a bed reading.

**S05, lifecycle cleanup:** the app's custom/generic gesture states have no own
`dispose`, and MotorPage `86b13c` unregisters callbacks without STOP. HA ends the
owned gesture on pointer/key cancellation, blur or page hide and runs only that
action's recovered release. This does not add STOP to presets or sofa reset.

HA's scheduler owns finite holds, cancellation and serialization. Both-side
frames share one bounded hold window; fixed monotonic 100 ms tick deadlines
avoid accumulating write latency. Count-based finite pulses share one write
deadline, allowing one recovered 100 ms pacing slot per selected side after the
last nominal tick. This admits a late one-pulse callback and its serialized side
attempts; explicit held durations retain their hard end. Stale refreshes are dropped at
the applicable deadline; an in-flight write and required release may finish afterward. Every
attempted side receives its own cleanup, even if another side's release fails.
Each cleanup
retains the original physical session and side; no frame crosses to a replacement
client. Future held refresh is discarded on cancellation instead of draining
stale motion. Releasing the card's gesture uses STOP admission to invalidate holds still
awaiting Bluetooth preflight, with a task-local context suppressing only the
extra STOP write. The controller's own cleanup remains responsible for release,
so presets and sofa reset do not acquire an extra STOP. Explicit Stop is separate.
Card release lookup follows the held entity's actual translation-key scheme:
single-address side children use suffixed keys, while physical two-address
children retain unsuffixed keys. Both remain confined to their own device.
Android widget mounting, camera input, SQLite implementation, permission UI,
reconnect dialogs and plugin MTU defaults are platform machinery, not extra bed
features. HA stores explicit profile/layout and acknowledged alarm preferences
per physical address/profile and uses its existing Bluetooth infrastructure.
HA's indexed manifest rejects wildcard characters in the first three name
characters. Its hints therefore use the five literal keyword prefixes and all
existing name-guarded service hints. All six GATT transports remain supported
after explicit selection; E0FF retains the existing passive-discovery exclusion
for non-bed false matches (`tests/test_detection.py:TestW5WiLinkeNameGuard`).
Service/manual detection preserves the app's complete
case-sensitive substring rule, including names with an earlier prefix. A name
without an eligible advertised service can be selected manually in that case.
Background profile recommendations retain an explicitly selected HJBed app but
exclude its scan hint from competing receiver signatures and from corroboration
of a shared service. Proven receiver recommendations and per-address decision
identities therefore retain their existing behavior; an app scan name does not
establish another protocol or product layout.

Wi-Fi/cloud/account/provisioning/network, firmware maintenance, desk-only and
phone-unrelated exclusions carry exact artifact source/reason entries. No
convenience, model prevalence, missing hardware or lack of an entity is an
exclusion reason. Physical effects, ATT and firmware acceptance remain unverified
and are deferred to real users after beta/release.

Implementation: [HJBed guide](../../beds/hjbed.md). Focused checks live in
`tests/test_hjbed.py`, its artifact fixtures, the controller/HA service/entity
contracts and the card's discovery/hold tests.
