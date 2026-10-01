# VMAT app profile

This explicit profile implements the accepted `de.vibradorm.vmat` 1.11 (49)
application contract. App behavior is artifact verified; physical operation
remains unverified. Generic Vibradorm entries keep their existing controller.
Shared Bluetooth identifiers and device-information strings cannot select this
app or its remote layout.

## Setup and remote selection

Choose **VMAT** in the explicit app controller, then the same zero-based remote
ordinal used by the app. Resource names identify shipped images, not proven
physical products. Controls and features follow this exact selection.

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
Short/mismatched replies are guarded. UTF-8 retains whitespace and NULs.
After native pairing/proof, setup sends `01 a7` and disconnects. Runtime
onboarding also closes its link before a separate control connection, whose
actual route must prove the bond. Normal sessions issue no onboarding queries
or position polls. Explicit information refresh reads only three DIS fields.
Disconnect still runs if setup close fails or is cancelled. Cancellation
propagates, and a failed or interrupted disconnect retains the live client
owner for cleanup rather than dropping its tracking or runtime pointer.
The physical BLE connection remains visible until it actually closes. A
failed config setup link stays owned by Home Assistant's exact address lock
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
