# Q-Plus Adjustable Remote

Select **Q-Plus Adjustable Remote** explicitly in the bed-type list. Use the Bluetooth
address of the bed and choose the layout shown by your app in **App controls**.
The layout is a UI choice, not proof of physical motor count or bed model.
Shared services, names and manufacturer data do not select this app automatically.
Generic SBI, Keeson and other app profiles keep their existing behavior.

Accepted artifact: `com.sbi.costco` version **1.8**.
Artifact-set SHA-256: `0b1be16e910c944624a6a2991a23840e23dae88a8eba750a12f3c773ffd63803`.
Static app behavior is proven; actual bed effects, radio delivery and firmware
interpretation remain **UNVERIFIED**. Real users can validate these after a beta
or release; no immediate maintainer hardware test is required.

## Setup and controls

Layouts: **H**, **M1**, **M2**, **M3**, **MX**. Each physical side of a two-address
pair retains its own app settings. Target the native child device, or choose the
paired service's `side`; conflicting child/side requests are rejected.
No app-specific physical left/right mapping or one-address pairing is inferred.

The app-labelled buttons use the existing coordinator command scheduler and BLE
lane. A button press provides a finite held adapter based on the configured
pulse count. A source held command repeats every **100 ms**, starting immediately.
All protocol-defined releases run with a fresh cancellation event. Disconnects
invalidate handles, pending work and stale notifications. No Android mutable
characteristic queue or stale-handle behavior is reproduced.

| Layout | App-labelled control | Control key | Mask | Event behavior |
|---|---|---|---|---|
| H | Head Up | `head_up` | `0x1` | held |
| H | Head Down | `head_down` | `0x2` | held |
| H | Foot Up | `foot_up` | `0x4` | held |
| H | Foot Down | `foot_down` | `0x8` | held |
| H | Tilt Up | `tilt_up` | `0x10` | held |
| H | Tilt Down | `tilt_down` | `0x20` | held |
| H | Lumbar Up | `lumbar_up` | `0x40` | held |
| H | Lumbar Down | `lumbar_down` | `0x80` | held |
| H | Level | `level` | `0x100` | single |
| H | Zero_G | `zero_g` | `0x1000` | single |
| H | Read | `read` | `0x2000` | held |
| H | Flat | `flat` | `0x8000000` | single |
| H | Reset | `reset` | `0x8001000` | held |
| H | Massage Head | `massage_head` | `0x800` | single |
| H | Massage Foot | `massage_foot` | `0x400` | single |
| H | Music | `music` | `0x4000` | held |
| H | TV | `tv` | `0x8000` | held |
| H | Light | `light` | `0x20000` | single |
| H | Lumbar Massage | `lumbar_massage` | `0x400000` | single |
| H | Massage Mode 3 | `massage_mode_3` | `0x80000` | single |
| H | Massage Mode 1 | `massage_mode_1` | `0x100000` | single |
| H | Massage Mode 2 | `massage_mode_2` | `0x200000` | single |
| M1 | Head Up | `head_up` | `0x1` | held |
| M1 | Head Down | `head_down` | `0x2` | held |
| M1 | Foot Up | `foot_up` | `0x4` | held |
| M1 | Foot Down | `foot_down` | `0x8` | held |
| M1 | Level | `level` | `0x100` | single |
| M1 | Zero_G | `zero_g` | `0x1000` | single |
| M1 | Read | `read` | `0x2000` | held |
| M1 | Flat | `flat` | `0x8000000` | single |
| M1 | Reset | `reset` | `0x8001000` | held |
| M1 | Massage Head | `massage_head` | `0x800` | single |
| M1 | Massage Foot | `massage_foot` | `0x400` | single |
| M1 | Music | `music` | `0x4000` | held |
| M1 | TV | `tv` | `0x8000` | held |
| M1 | Light | `light` | `0x20000` | single |
| M1 | Lumbar Massage | `lumbar_massage` | `0x400000` | single |
| M2 | Head Up | `head_up` | `0x1` | held |
| M2 | Head Down | `head_down` | `0x2` | held |
| M2 | Foot Up | `foot_up` | `0x4` | held |
| M2 | Foot Down | `foot_down` | `0x8` | held |
| M2 | Tilt Up | `tilt_up` | `0x10` | held |
| M2 | Tilt Down | `tilt_down` | `0x20` | held |
| M2 | Level | `level` | `0x100` | single |
| M2 | Zero_G | `zero_g` | `0x1000` | single |
| M2 | Read | `read` | `0x2000` | held |
| M2 | Flat | `flat` | `0x8000000` | single |
| M2 | Reset | `reset` | `0x8001000` | held |
| M2 | Massage Head | `massage_head` | `0x800` | single |
| M2 | Massage Foot | `massage_foot` | `0x400` | single |
| M2 | TV | `tv` | `0x4000` | held |
| M2 | Anti-snore | `anti_snore` | `0x8000` | single |
| M3 | Head Up | `head_up` | `0x1` | held |
| M3 | Head Down | `head_down` | `0x2` | held |
| M3 | Foot Up | `foot_up` | `0x4` | held |
| M3 | Foot Down | `foot_down` | `0x8` | held |
| M3 | Level | `level` | `0x100` | single |
| M3 | Zero_G | `zero_g` | `0x1000` | single |
| M3 | Read | `read` | `0x2000` | held |
| M3 | Flat | `flat` | `0x8000000` | single |
| M3 | Reset | `reset` | `0x8001000` | held |
| MX | Head Up | `head_up` | `0x1` | held |
| MX | Head Down | `head_down` | `0x2` | held |
| MX | Foot Up | `foot_up` | `0x4` | held |
| MX | Foot Down | `foot_down` | `0x8` | held |
| MX | Tilt Up | `tilt_up` | `0x10` | held |
| MX | Tilt Down | `tilt_down` | `0x20` | held |
| MX | Anti-snore | `anti_snore` | `0x8000` | held |
| MX | MX Memory 1 | `mx_memory1` | `0x10000` | held |
| MX | Flat | `flat` | `0x8000000` | single |
| MX | Light | `light` | `0x4000` | single |
| MX | Massage head | `massage_head` | `0x800` | pulse |
| MX | Massage foot | `massage_foot` | `0x400` | pulse |
| MX | Massage timer | `massage_timer` | `0x200` | pulse |

`held` repeats until bounded release; `pulse` sends once then releases after
300 ms; `single` sends once. `tap_zeros` sends once followed by zero frames at
+300/+400/+500 ms. `held_zeros` also schedules those three zero frames from the
start of the hold, retaining them after ordinary early release. Cancellation
and disconnect never leave background writers from an old operation.

The regular key frame is `E5 FE 16`, a low32 little-endian mask and one inverted
sum byte. Clock frames are `E7 80 01`, local year minus 1900 (low byte), zero-based
month, day, hour, minute, second and checksum. Name frames are `EF 02` with a
15-byte zero-filled region and checksum. The supported UI limit is 14 UTF-16
units. The source copies that many bytes from an unnamed default charset;
HA documents and uses the frozen UTF-8 model, including incomplete encoded
characters for some non-ASCII names. This does not establish firmware encoding.

Q-Plus **A/B/Both** is a separate app wire selector, not paired Left/Right.
P1 uses `E5` for Both or `E6 ... 01/02` for A/B. MX uses the sparse six-byte
`04 02` builder with big-endian payload and no checksum. MX initializes with
`00 B0` at +300/+600/+900 ms. The existing diagnostic query hook retains the
first-five-second, then-thirty-second live-session status-query cadence, with
command priority and without renewing the idle deadline.

**MX Memory 1** is an opaque app-named held action, not an invented physical
save or recall operation. It attempts `04 02 00 01 00 00` every 100 ms. Release
stops repetition and, while connected, queries `00 B0` at +300/+600/+900 ms.
It sends no STOP/zero/clear-key packet. Single MX actions query at +500/+800 ms;
MX massage waits 300 ms before its release query triplet. There is no accepted
Q-Plus clock-sync writer and no reachable angle-target writer in this artifact.

## Alarm tables

Use [`adjustable_bed.configure_alarm_schedule`](../SERVICES.md#configure_alarm_schedule).
Both `weekly` and `one_time` lists and `dispatch` are required. There are three
enabled slots in each table. Disabled rows consume no slots; `wake: false`
enabled rows still consume a slot. Both full tables and every physical target
are checked before checksums or any sends, including an unselected table.

Weekday encoding: marker bit7 plus weekday bits; Monday through Saturday use bits1..6,
Sunday bit0. Wake byte: **0x10**, otherwise zero.
The frames are `ED 80 03` (weekly) and `ED 80 02` (one-time), each 16 bytes,
with three four-byte records and an inverted-sum checksum at15. `both` sends
weekly then waits 500 ms then one-time; selected single-table dispatch still
waits 500 ms after the send. A transport failure can leave only one table sent;
there is no wire rollback. Empty-table bytes are attempted writes, not proof
that the firmware clears a schedule.

An enabled one-time row is a future HH:MM on the same Home Assistant local
date. One captured local `now` is shared by every target and serialization.
Past/equal, nonexistent DST and ambiguous DST times are rejected before writes.
No tomorrow rollover or Android date-parser behavior is invented. Absolute
timestamps use Java Date millisecond precision before positive integer
hour/minute/second decomposition;
a positive subsecond remainder may serialize zero seconds, without asserting
that zero clears firmware. Negative source deltas and fourth-row corruption
are never sent. This applies even to Omazz/Ergomotion's source partial-overflow
cases. Weekly and disabled zero fields are not blanket-rejected as zero delays.

The source snooze path stores55+10 as minute65 without carrying. HA's
public table input requires valid HH:MM; an automation must normalize date/time
first and reject a cross-date result. Phone AlarmManager scheduling remains
outside the integration. The BLE table writer preserves the original weekly
versus one-time dispatch choice and has no next-day adjustment.

## Notifications and evidence

The **App timer status** sensor reports only the accepted source statuses:
-1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Unknown statuses leave the
prior value unchanged. The parser does not infer acknowledgement, battery,
physical motor count, light state or physical memory meaning. Incoming packets
are not reassembled or given invented header/checksum guards.

Accept lengths 16/19/20/23. A5 0B 0D at16 bytes precedes normal bit5 suppression and maps a big-endian seconds word1..600/601..1200/1201..1800 to1/2/3. Normal16 requires byte13 bit5 clear and bytes 7..9 zero for timer updates. At19, byte16 second-side bit drops for every current A/B/Both selector, and bytes 7..9 must be zero; status15. Length 20 uses14,23 uses15. No physical side identity is assigned.

The GATT selector independently retains the last matching notification and
write characteristics across all services. Both are required. FFE4/FFE9 are
used by these profiles; Q-Plus also accepts NUS read/write roles, independently
of UI style. HA subscribes through Bleak and chooses response mode from current
characteristic properties; the APK's unset Android write type does not prove
an on-air mode. No authentication, arbitrary-packet service or guessed firmware
operation is added.

The [durable disposition ledger](cluster033-dispositions.json) retains all 562
stable discoveries: 380 implementation dispositions, 12 narrowly credited
baseline behaviors, 170 exact evidence-backed exclusions. Its per-item symbols
and test cases accompany 413 frozen vector fixtures. The 16150 historical
owners, 3386 semantic occurrences, 10158 projections and 672 dependencies are
coverage metadata, not extra features or new audit credit. Raw APKs,
decompilation and full audit reports stay local and ignored.

## Native card holds

The native card uses each entity's flat declared hold metadata and calls the
registered bounded `hold_control` action once. Pointer release, Enter/Space
release, blur and page abandonment retain the owning side's STOP target.
A normal button press and accessibility click retain the finite action.
Combined parent motor buttons advertise a held direction only when every
eligible side declares the same control and start/release delays on a concurrent
pair. Mixed, unknown, legacy and sequential sides keep finite controls.

The scalar metadata is `held_control` on buttons, or `held_control_up` and
`held_control_down` on covers, plus `hold_start_delay_ms` and
`hold_release_delay_ms`. Source-held cluster033 controls start at0ms. Immediate
zero releases use0ms; Q-Plus MX uses300ms to its first query, followed by the
remaining600/900ms queries. These delays do not invent a physical STOP for MX.

Rename keeps this app's14-unit editor domain. HA rejects outer whitespace;
it does not infer another package's trimmed caller semantics for Q-Plus.
