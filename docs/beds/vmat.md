# VMAT app profile

This explicit profile implements the accepted `de.vibradorm.vmat` 1.11 (49)
application contract. App behavior is artifact verified; physical operation
remains unverified. Generic Vibradorm entries keep their existing controller.
Shared Bluetooth identifiers and device-information strings cannot select this
app or its remote layout.

## Setup and remote selection

Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
bed-type picker, then **VMAT** and the same zero-based remote ordinal used by
the app. **Legacy setup** inside the family chooser retains the older generic
controller for fresh setup. Existing entries change through the
[guided migration](../CONFIGURATION.md#vibradorm-guided-setup-and-migration).
The choices distinguish setup contracts; some command paths overlap. Resource names identify
shipped images, not proven physical products. Controls and features follow this
exact selection.
Successfully reconfiguring to Caresse or Werkmeister removes the VMAT remote from the saved
profile. Separate-address sides keep their own remote selections.

| Remote | Image | Logical groups | Memory | Sync | Floor | Mood / massage |
| --- | --- | --- | --- | --- | --- | --- |
| 00 | sender_010 | Back, legs | No | No | No | No |
| 01 | sender_020 | Back, legs | No | No | Yes | No |
| 02 | sender_180 | Back, legs | No | No | No | No |
| 03 | sender_190 | Back, legs | No | No | No | No |
| 04 | sender_200 | Back, legs | No | No | Yes | No |
| 05 | sender_210 | Back, legs | No | No | Yes | No |
| 06 | sender_220 | Back, legs | No | No | Yes | No |
| 07 | sender_230 | Back, legs | 6 | Yes | Yes | No |
| 08 | sender_240 | Back, legs | 6 | Yes | Yes | No |
| 09 | sender_250 | Back, legs | 6 | Yes | Yes | No |
| 10 | sender_260 | Back, legs | 6 | Yes | Yes | No |
| 11 | sender_270 | Head, back, legs | 6 | Yes | No | No |
| 12 | sender_090 | Back, legs | No | No | No | Yes |
| 13 | sender_100 | Head, back, legs, feet | 6 | No | No | Yes |

The app's neck/calf groups use HA's head/feet controls; physical actuator
identity remains unverified. Remotes 12/13 set the extension flag but expose no
floor route. Quick memory buttons are subsets of the six-slot contract.

Setup requires positive native bond evidence for the exact address and actual
host route. An unverified pairing RPC cannot finish setup or authorize control.
Metadata does not identify a wire layout or prove a bond. No app PIN/key exchange
is proven. Unsupported proxy pairing should use a supported host adapter;
existing bonds are never silently removed.

The exact service `1525` requires CBI `1550` (without response), response `1551`
(notify), and DIS model/firmware/software reads. Basic profiles additionally
require COMMAND `1526` and LIGHT `1529` (with response), even without floor UI.
Setup also requires management service `1527` / characteristic `1533` by
existence only. Vendor UUIDs use `0000XXXX-9f03-0de5-96c5-b8f4f3081186`; DIS
uses standard service `180a` and characteristics `2a24`, `2a26`, `2a28`.

The supported stack owns MTU negotiation and CCCD operations. Frames fit MTU 23.
Initialization settles for 500 ms and subscribes for every remote. Setup reads
the three DIS fields, then serially issues seven CBI stages:

| Stage | Request | Response |
| --- | --- | --- |
| Status | `01 b3 4c 01` | `21 b3 value`, unsigned byte |
| Operating mode | `01 b3 f4 01` | `21 b3 value`, signed byte |
| Article | `01 a0 c8` | `21 a0 c8` plus UTF-8 |
| Name | `01 a0 c9` | `21 a0 c9` plus UTF-8 |
| Revision ID | `01 a0 ca 00` | `21 a0 ca` plus UTF-8 |
| Revision string | `01 a0 ca` | `21 a0 ca` plus UTF-8 |
| Variant | `01 a0 cc` | `21 a0 cc` plus UTF-8 |

The first response timeout is 2 seconds and the others 1 second. Each
notification can complete one current stage; the two CA stages stay separate.
Missing replies advance after timeout without a fabricated acknowledgment.
Transport write timeouts abort onboarding before native pairing.
Short/mismatched replies are guarded. UTF-8 retains whitespace and NULs.
After native pairing/proof, setup sends `01 a7` and disconnects. Runtime
onboarding also closes its link before a separate control connection, whose
actual route must prove the bond. Normal sessions issue no onboarding queries
or position polls. Explicit information refresh reads only three DIS fields.
An existing native bond skips onboarding and pairing, while setup still validates
the selected remote's ordinary GATT roles before accepting the address.
Disconnect still runs if setup close fails or is cancelled. Cancellation
propagates, and a failed or interrupted disconnect retains the live client
owner for cleanup rather than dropping its tracking or runtime pointer.
An RPC error after observed native closure does not turn completed teardown
into a failure. An earlier setup error or cancellation still propagates.
Notification cleanup preserves an earlier setup error or cancellation. A
cleanup failure after successful reads still fails setup before native pairing.
The physical BLE connection remains visible until it actually closes. A
failed config or runtime setup link stays owned by Home Assistant's exact address lock
after the progress worker or flow ends, including local bond replacement.
Retry, another flow, runtime and diagnostic capture cannot open a second link
until native closure is observed. Cleanup retries only that retained client's
disconnect; it supplies no bond proof and sends no additional protocol frame.
Other addresses and ordinary setup flows retain their existing behavior.
A retained setup or failed-startup link cannot serve commands or be replaced by
retry/reconnect. Sequential paired verification must release it before opening
the other side. Successful observed teardown restores normal connection admission.

Onboarding connection timeout is 5 seconds. HA bounds the complete operation
with a separate 45-second resource budget, not a device pairing timing claim.

## Controls and state

P1 uses big-endian 16-bit CBI opcodes without response. Basic movement uses
one-byte COMMAND; basic floor uses three-byte LIGHT with response. Basic
accessories still use CBI. Payloads are immutable snapshots, without guessed
checksums, encryption or fragmentation. Construction toggle is 0/`8000`,
including invisible basic motor flips; held packets repeat unchanged. Floor
actions retain their extra action/execution flips. Unsafe Android shared
static payload overwrites are excluded.

Enabled motor directions, All Up/All Down and recall are held actions. All Down
is movement, not a timed flat preset. First delivery is immediate on an idle
lane; repeats/queued writes wait 100 ms after successful completion. Release,
cancellation and failure use fresh STOP (`ff` basic, `00 ff` CBI), prioritizing
cleanup over pending ordinary traffic. No hardware watchdog is claimed.

Memory slots 1–6 use `0e,0f,0c,1a,1b,1c`. Programming sends four alternating
STORE `000d/800d` frames, an untoggled slot frame, then four `00ff` frames.
Sync on control 8/9 queries `3d|T,3f`; `20 3f flags` or `3f flags extra`
(minimum length 3) selects held opcode 25 when bit `40` is set, otherwise 24.
Late replies cannot restart released movement. No partner selector is proven.

Floor levels 0–8 map to `0,32,64,96,128,160,192,224,250`. Off is 0; remembered
default is 8 for selectable floor remotes. Timer minutes 1–60 and enabled state
apply to the next floor packet; timer-only changes send nothing. Cold current
level 0 is assumed local state, not measured physical off state.

Mood exposes 18 shipped palette choices with VMAT-specific conversion rounding,
three effects, and speed 0–8 mapping `18,16,…,2`. Color/effects use `0077` basic
or `1077` nonbasic; toggle uses `1077` for both. Arbitrary RGB and discrete
physical on/off guarantees are absent.

Massage on remotes 12/13 exposes automatic/individual modes, two zone toggles
and steps, four waves and speed 1–5. Complete current/saved settings and flags
are retained. Intensity is 0–5, minimum 1 with nonzero effect; first automatic
restore is effect 1/speed 1/zones 3/3. ON is the full 10-byte `0030/1030` state;
OFF is `0034/1034` plus `00`. Mode switching preserves off/restore order.
Unreachable OFF `01` and the unexposed massage timer are disabled.

Floor/timer/mood/massage state is process-local intent. Reconnect and reload
retain it for the exact address/app/remote; profile changes clear the holder.
Failed/cancelled VMAT accessory writes roll back the requested state.
Successful delivery remains assumed intent, not readback. Restart clears
current intent while retaining the configured floor default.

No live position parser, angle target, battery query, firmware update,
calibration or named presets are proven. Diagnostics retain raw notifications;
unsolicited EEPROM/log recognition does not enable dead collectors or queries.

## Discovery and completion

The bounded raw parser concatenates FF records in original AD order, including
company IDs. It preserves company `03b0`, `ffff/BABE`, revisions 3/4/5, exact
flags, GID, signed revision 4/5 SGID and customer metadata. Company `03b0`
remains eligible even with an unknown revision. A complete raw record without
a Flags field uses the shipped SDK's `-1` default; an available Flags field
uses its first payload byte. Teach selection uses the current third eligible
report, followed by owner teardown, rather than a cached strongest RSSI device.
Exact-address reconnect bypasses manufacturer classification.

HA's manufacturer mapping loses original AD order, duplicate records and raw
advertising flags. Diagnostics leave these unavailable flags unknown, never
replace them with zero or the raw-record default, and never infer the
app/remote. Select the exact address explicitly.
Malformed lengths that make Android hang, crash or pad missing bytes are
rejected safely.

The [disposition ledger](vmat-dispositions.json) binds all 282 comparison items:
240 IMPLEMENTED, 0 ALREADY_IMPLEMENTED and 42 EXCLUDED. Its exact exclusions
cover 26 unreachable selectors, Android scanner/permission/bond APIs, phone
presentation and unsafe queue/parser/cancellation behavior. Hardware absence
does not defer implementation. Focused tests exercise real controller/setup
delivery, frozen vectors, native-proof gates, timing and failure cleanup.
Physical validation remains for users after beta/release.

## Issue #403 reconciliation

The original [parity request](https://github.com/kristofferR/ha-adjustable-bed/issues/403)
predates the accepted independent app audits. Its assumption that Caresse,
Werkmeister, VMAT and V-MAT Basic expose one interchangeable contract is
superseded by their explicit profiles. The VMAT profile shipped in
[v4.1.0](https://github.com/kristofferR/ha-adjustable-bed/releases/tag/v4.1.0).
The outcomes below describe existing implementation and accepted exclusions;
they do not change the frozen audit ledger.

| Original request | Current outcome | Existing evidence |
| --- | --- | --- |
| Live positions, initialization flags and raw motor counts | EXCLUDED as a VMAT app feature: no reachable live position parser is proven. The generic controller retains its separate historical parser and angle estimates. | `VibradormAppController.supports_position_feedback`; `test_remote_contract_and_no_guessed_capabilities`; [generic controller](vibradorm.md#position-feedback) |
| Full EEPROM collection and diagnostic field sensors | EXCLUDED as a supported app operation: unsolicited EEPROM/log recognition does not establish a reachable collector or query. | Accepted VMAT notification/capability dispositions; Caresse dead parser routes `R031-0548`–`R031-0550` in the [row031 ledger](../apk-analysis/row031-dispositions.md) |
| Memory recall M1–M6 and store handshake | ALREADY_IMPLEMENTED where the selected remote enables memory, with the exact nine-frame save sequence. | `hold_control`, `program_memory`; `test_every_reachable_held_control_releases`, `test_complete_nine_frame_save_sequence` |
| Status request and sync | ALREADY_IMPLEMENTED for the VMAT sync remotes as a reply-gated held action. The observed sync flag is exposed; it is not a position measurement. | `hold_control`, `_notification`, `controller_state_sensor_specs`; `test_sync_only_streams_while_response_is_pending_and_held`, `test_registered_notifications_are_bound_to_live_role_and_generation` |
| Floor light, level and timer | ALREADY_IMPLEMENTED for selectable floor remotes, with their exact LIGHT or CBI route and pending timer state. | `_floor`, `set_pending_floor_timer`; `test_floor_delivery_full_shipped_range` |
| Mood color, effects, speed and toggle | ALREADY_IMPLEMENTED for remotes 12/13, using the shipped palette and effect choices. | `_mood`, `set_mood_palette`, `set_mood_effect`, `set_mood_speed`; `test_all_shipped_palette_packets`, `test_all_mood_speed_positions` |
| Unrestricted RGB color | EXCLUDED from app parity: the shipped UI supplies palette choices, not an arbitrary RGB control. | Accepted VMAT light/profile contract and palette vectors |
| Massage modes, speed and two intensity zones | ALREADY_IMPLEMENTED for remotes 12/13, with full current/saved state and exact mode/off/restore ordering. | `_plan_massage_mode`, `_write_massage_packets`; `test_full_massage_state_packets_from_frozen_builder_vectors`, `test_automatic_individual_restore_clamps_and_exact_off_restore_order` |
| Massage timer and OFF-command payload `01` | EXCLUDED from app parity: neither is exposed by a reachable shipped control. | Accepted VMAT massage contract and disabled-action gates |
| Toggle, accessory bus selection, refresh and STOP | ALREADY_IMPLEMENTED per selected remote. Logical construction advances the toggle; held repeats reuse the packet. | `_header`, `_write`, `_release`; `test_every_reachable_held_control_releases`, `test_single_shots_wait_after_success_completion_and_stop_bypasses_delay` |
| Automatic generic layout from control-version metadata | EXCLUDED: shared metadata does not select the app's remote or establish physical actuator identity. All fourteen shipped VMAT selections are explicitly available. | `VMAT_REMOTES`; `test_remote_contract_and_no_guessed_capabilities`, `test_remote_flags_cannot_be_spoofed` |

Code references above are in
[`vibradorm_app.py`](../../custom_components/adjustable_bed/beds/vibradorm_app.py)
and [`vibradorm_vmat_profiles.py`](../../custom_components/adjustable_bed/vibradorm_vmat_profiles.py).
Test references are in
[`test_vibradorm_vmat.py`](../../tests/test_vibradorm_vmat.py); the
[VMAT ledger](vmat-dispositions.json) retains the exact accepted source bindings.
[Caresse / Werkmeister](vibradorm_app.md) and [V-MAT Basic](vmatbasic.md)
have their own independent feature gates, vectors and dispositions.

The requested MC4-MD08 retest remains deferred physical validation for its
owner after release. The accepted app implementation does not prove that
[issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162) is fixed
or that a particular controller reports positions. No in-scope implementation
item is deferred for lack of maintainer hardware.
