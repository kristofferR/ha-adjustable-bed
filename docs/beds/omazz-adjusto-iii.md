# Omazz Adjusto III

Select **Omazz Adjusto III** explicitly in the bed-type list. Use the Bluetooth
address of the bed and choose the layout shown by your app in **App controls**.
The layout is a UI choice, not proof of physical motor count or bed model.
Shared services, names and manufacturer data do not select this app automatically.
Generic SBI, Keeson and other app profiles keep their existing behavior.

Accepted artifact: `com.sfd.Omazz` version **1.0.5**.
Artifact-set SHA-256: `bfb77d2660c8b7dd62472d063eed6e2b0c476dcfbce83edf956f54bec0130d87`.
Static app behavior is proven; actual bed effects, radio delivery and firmware
interpretation remain **UNVERIFIED**. Real users can validate these after a beta
or release; no immediate maintainer hardware test is required.

## Setup and controls

Layouts: **RemoteB**. Each physical side of a two-address
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
| RemoteB | Head Up | `head_up` | `0x1` | held |
| RemoteB | Head Down | `head_down` | `0x2` | held |
| RemoteB | Foot Up | `foot_up` | `0x4` | held |
| RemoteB | Foot Down | `foot_down` | `0x8` | held |
| RemoteB | Lounge | `lounge` | `0x2000` | held |
| RemoteB | Demonstration | `demonstration` | `0x40000000` | held |
| RemoteB | Tv | `TV` | `0x4000` | held |
| RemoteB | Music | `music` | `0x10000` | held |
| RemoteB | Flat | `flat` | `0x8000000` | single |
| RemoteB | Zg | `zg` | `0x1000` | single |
| RemoteB | Ubb | `ubb` | `0x20000` | single |
| RemoteB | Massage Head | `massage_head` | `0x800` | pulse |
| RemoteB | Massage Timer | `massage_timer` | `0x200` | pulse |
| RemoteB | Massage Foot | `massage_foot` | `0x400` | pulse |
| RemoteB | Massage All | `massage_all` | `0x100` | pulse |

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

This app has no reachable device-name writer; the generic rename action is unavailable.

## Alarm tables

Use [`adjustable_bed.configure_alarm_schedule`](../SERVICES.md#configure_alarm_schedule).
Both `weekly` and `one_time` lists and `dispatch` are required. There are three
enabled slots in each table. Disabled rows consume no slots; `wake: false`
enabled rows still consume a slot. Both full tables and every physical target
are checked before checksums or any sends, including an unselected table.

Weekday encoding: no marker, weekday bits only; Monday through Saturday use bits1..6,
Sunday bit0. Wake byte: **0x03**, otherwise zero.
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

## Notifications and evidence

The **App timer status** sensor reports only the accepted source statuses:
-1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Unknown statuses leave the
prior value unchanged. The parser does not infer acknowledgement, battery,
physical motor count, light state or physical memory meaning. Incoming packets
are not reassembled or given invented header/checksum guards.

Accept 16/20/23; only16 drops byte13 bit5; status14/14/15. Length19 is rejected.

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
