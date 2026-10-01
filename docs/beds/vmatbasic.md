# V-MAT Basic app profiles

Select **V-MAT Basic app** and the product explicitly: V-MAT-BASIC-RF, V-MAT-BASIC-RF-CBI, or V-MAT-BASIC-RF-CBI with XT-Box. Existing generic Vibradorm and Caresse/Werkmeister entries keep their separate controllers. A shared Bluetooth identifier, device name or model string cannot choose one of these profiles.

The protocol comes from the accepted `com.vibradorm.vmatbasic` 2.4.3 APK, version code 14. Its artifact-set SHA-256 is `5d266015494edf9ad595c5b4c6d11fcde3ea53fc78e008b4990e4ce834a31980`. The accepted repair report manifest is `5d73627f5b010b372b3cdec39091faa817a4a596ead49db9ec507ee6025a5d0d`; its independent audit manifest is `7892663c50ea99a3174bfa1fd86cd27ed276ef4be1270bf256ac13133a0c155b`. All package evidence stays machine-local. The [row037 disposition ledger](../apk-analysis/row037-dispositions.md) records the separate implementation comparison. Current code and focused executed tests cover the accepted behavior. Workflow progress is recorded in the canonical APK audit trackers and published queue plan. Hardware operation remains unverified.

## Controls and profiles

| Profile | Movement | Floor lighting | XT accessories |
|---|---|---|---|
| Basic (`basic`) | Back, legs, all up/down | None | None |
| CBI (`cbi`) | Same single-byte movement | Fresh-read toggle, level 0–255, timer 0–1439 minutes | None |
| CBI with XT-Box (`xtbox`) | Same single-byte movement | Held floor action, level 1–6, timer 0–255 minutes | Twenty-color mood palette, brightness 0–100%, three effects, speed 0–255, toggle/nightlight, six massage actions |

These are two named movement groups, not proof of physical motor topology. No head/feet/extra-axis, position slider, automatic flat preset, memory, arbitrary RGB, massage intensity or measured massage state is exposed. Generic motor count, angle sensing and pulse settings do not override the app profile.

Ordinary movement buttons hold for one second as a bounded Home Assistant policy. `vmatbasic_hold_control` accepts `all_up`, `all_down`, `back_up`, `back_down`, `legs_up`, `legs_down`, and XT-only `floor_hold`, with 0.1–60 seconds in whole milliseconds. The source refreshes held movement at 30 ms scheduling attempts; this is not a guaranteed on-air cadence. A fresh `ff` release follows admitted movement on completion, cancellation or failure, with bounded cleanup. All-down is a direction, not a measured flat position. XT floor hold repeats `00 11` and stops by ending the stream; no separate release frame is proven.

## Exact GATT and packets

Vendor UUIDs use suffix `-9f03-0de5-96c5-b8f4f3081186`.

| Role | Service | Characteristic |
|---|---|---|
| Movement | `00001525` + vendor suffix | `00001526` + vendor suffix |
| CBI floor read/write | Same control service | `00001529` + vendor suffix |
| XT write | Same control service | `00001550` + vendor suffix |
| ED read | `00001527` + vendor suffix | `00001531` + vendor suffix |
| Controller temperature read | Same status service | `00001532` + vendor suffix |
| Rename | GAP `1800` | Device Name `2a00` |
| Model / firmware read | DIS `180a` | `2a24` / `2a26` |

Every selected receiver must expose the control service, status service and GAP before control starts. DIS is optional: missing DIS fails only its diagnostic fields. The first exact service and then first exact characteristic within it are authoritative. Writes require the response-capable write property and use `response=True`. No arbitrary characteristic fallback, write-without-response downgrade, notification subscription, position request, checksum, crypto, fragmentation or MTU command is added.

Movement packets are one byte: all up/down `10`/`00`, back up/down `0b`/`0a`, legs up/down `09`/`08`, release `ff`. CBI floor writes are level U8 plus timer BE16. XT floor settings are `00 11 level minutes`. XT mood uses group `00 77`; color is `00 77 01 00 R G B`, effects are `00 77 08 01` through `03`, and speed is `00 77 09 ((progress + 1) & ff)`. Progress 255 deliberately encodes zero. The palette uses the APK's HSV conversion and truncation; the tests preserve all 2,020 palette/brightness outputs.

XT massage literals are back `00 2c`, legs `00 2d`, off `00 34`, and programs 1–3 `00 31`, `00 28`, `00 29`. Motor STOP does not turn massage off. Power, effect, speed and massage feedback are unknown; successful writes publish requested intent only.

## Floor and mood state

CBI toggle reads the current three-byte floor status first. A positive level sends all-zero OFF; zero sends the saved level and timer. A missing ON-button level defaults to 255, whereas the settings screen's absent level is zero. An explicitly saved zero stays zero. A failed or short read cannot select a toggle branch from stale state.

Floor settings are applied immediately, including timer changes. Requested settings persist per physical receiver through HA configuration; observed level, minutes and derived percent are separate read-backed diagnostic values. XT's public range stays within its shipped UI even though the raw builder has upper clamps. No measured ON/OFF state is inferred from a successful write.

Mood starts with white and 100% brightness in a cold control session. A typed exact-address process holder preserves the selected color/brightness across BLE reconstruction within HA's continuous control session. Profile changes reset that holder; another physical receiver cannot share it. Admitted color construction retains local intent even if delivery fails, while public requested state is published only after a successful write. This preserves the dependency of the next brightness/color command without claiming a hardware acknowledgment. The six massage buttons are separate literal actions, with no invented toggle state.

## Diagnostics, discovery and pairing

Initial diagnostics and three-second refresh attempts read model, controller temperature, floor status, firmware, then ED. Each operation has an 800 ms host deadline; a failed field becomes unknown and later fields can still refresh. Temperature is signed LE32 divided by four minus seven degrees Celsius. Floor is level U8 and timer BE16; percent is level × 100 / 255. ED is bit zero of the first byte and is not a position parser. String decoding preserves Java UTF-8 replacement semantics without trimming.

Background reads use an already live connection, yield to commands, preserve the existing idle disconnect deadline, and stop/invalidate on disconnect. They do not reconnect or keep an idle receiver awake. Immediate/two-second signal samples use HA advertisement history, with scanner source and observation timestamp attributes. They are not remote GATT RSSI reads; unavailable or invalidated signal remains unknown. Signal strength never chooses a receiver or adds a connection prerequisite.

The source scan predicate uses the first raw manufacturer AD record, ignores its company ID, and checks `ba be` followed by low nibbles 1/1. The safe raw parser preserves that first-record rule. HA's manufacturer map loses AD order, duplicates and declared lengths, even with one company: diagnostics report conditional per-record matches and keep the exact source scan verdict unknown. A conditional candidate hint cannot infer a profile. Existing cached-address selection remains explicit; rename and optional model strings are not identity proof.

Bonded status is advisory in this app. The integration does not invent native bonding, a PIN, authentication exchange or authenticated-GATT proof.

## Separate receivers and rename

Combine two independently configured CBI or CBI with XT-Box receivers at distinct addresses only when linked movement is wanted. The Basic profile has no linked control. Each side retains its explicit profile and settings. Movement on both sides requires both concurrent physical GATT sessions validated before either starts. A failed receiver, cancellation, disconnect or sequential fallback cannot release a partial group. Separate-side commands remain independent. Single-address pairing is unsupported.

Only movement and its release mirror across a linked pair. Floor, mood, massage, reads and rename belong to one physical child unless the user explicitly addresses another independently configured child. `floor_hold` and `vmatbasic_rename` reject a multi-target request before writing. Split a pair to change its per-side profile, then combine it again.

`vmatbasic_rename` trims code points up to U+0020, allows an empty name, and limits the result to ten UTF-16 units. UTF-8 is written without a terminator. A further host safety limit of 20 encoded bytes avoids inventing fragmentation. Save the confirmed name only after the write succeeds; failed delivery leaves the stored name unchanged.

Physical packet delivery, movement effects, floor timing/scales, mood and massage effects, rename persistence, temperature interpretation, optional read support, dual connection behavior and security remain deferred user validation after beta/release. Static acceptance does not claim those hardware outcomes.

Hardware status: **UNVERIFIED**. The dedicated app bed type keeps these accepted profiles separate from the existing generic and Caresse/Werkmeister routes; it is a Home Assistant configuration boundary, not an inferred protocol identity.
