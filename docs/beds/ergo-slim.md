# Ergo Slim

Select **Ergo Slim** explicitly in the bed-type list. Use the Bluetooth
address of the bed and choose the layout shown by your app in **App controls**.
The layout is a UI choice, not proof of physical motor count or bed model.
Shared services, names and manufacturer data do not select this app automatically.
Generic SBI, Keeson and other app profiles keep their existing behavior.

Accepted artifact: `com.sfd.slim` version **1.3**.
Artifact-set SHA-256: `57fc9f61148e8eefa885e006ab371de02f79ffb92d49677d306b1999007f7019`.
Static app behavior is proven; actual bed effects, radio delivery and firmware
interpretation remain **UNVERIFIED**. Real users can validate these after a beta
or release; no immediate maintainer hardware test is required.

## Setup and controls

Layouts: **A**, **B**, **C**. Each physical side of a two-address
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
| A | Reset | `reset` | `0x8001000` | held |
| A | Head Up | `head_up` | `0x1` | held |
| A | Head Down | `head_down` | `0x2` | held |
| A | Foot Up | `foot_up` | `0x4` | held |
| A | Foot Down | `foot_down` | `0x8` | held |
| A | Massage Head Min | `massage_head_min` | `0x800000` | pulse |
| A | Massage Foot Min | `massage_foot_min` | `0x1000000` | pulse |
| A | Level | `level` | `0x2000000` | single |
| A | Zero Gravity | `zero_gravity` | `0x1000` | single |
| A | Flat | `flat` | `0x8000000` | pulse |
| A | Tv | `tv` | `0x4000` | held |
| A | Lounge | `lounge` | `0x2000` | held |
| A | Light | `light` | `0x20000` | single |
| B | Massage Head | `massage_head` | `0x800` | pulse |
| B | Massage Timer | `massage_timer` | `0x200` | pulse |
| B | Massage Foot | `massage_foot` | `0x400` | pulse |
| B | Ubb | `ubb` | `0x20000` | single |
| B | Massage All | `massage_all` | `0x100` | pulse |
| B | Music | `music` | `0x10000` | held |
| B | Head Up | `head_up` | `0x1` | held |
| B | Head Down | `head_down` | `0x2` | held |
| B | Foot Up | `foot_up` | `0x4` | held |
| B | Foot Down | `foot_down` | `0x8` | held |
| B | Flat | `flat` | `0x8000000` | pulse |
| B | Anti Snore | `anti_snore` | `0x8000` | held |
| B | Lounge | `lounge` | `0x2000` | held |
| B | Tv | `tv` | `0x4000` | held |
| B | Zero Gravity | `zero_gravity` | `0x1000` | single |
| C | Massage Head | `massage_head` | `0x800` | pulse |
| C | Massage Timer | `massage_timer` | `0x200` | pulse |
| C | Massage Foot | `massage_foot` | `0x400` | pulse |
| C | M3 Out | `m3_out` | `0x10` | held |
| C | Ubb | `ubb` | `0x20000` | single |
| C | M3 In | `m3_in` | `0x20` | held |
| C | Head Up | `head_up` | `0x1` | held |
| C | Head Down | `head_down` | `0x2` | held |
| C | Foot Up | `foot_up` | `0x4` | held |
| C | Foot Down | `foot_down` | `0x8` | held |
| C | Zero Gravity | `zero_gravity` | `0x1000` | single |
| C | Memory 4 | `memory_4` | `0x8000` | held |
| C | Memory 2 | `memory_2` | `0x2000` | held |
| C | Memory 3 | `memory_3` | `0x4000` | held |
| C | Flat | `flat` | `0x8000000` | pulse |

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

## Alarm tables

Use [`adjustable_bed.configure_alarm_schedule`](../SERVICES.md#configure_alarm_schedule).
Both `weekly` and `one_time` lists and `dispatch` are required. There are three
enabled slots in each table. Disabled rows consume no slots; `wake: false`
enabled rows still consume a slot. Both full tables and every physical target
are checked before checksums or any sends, including an unselected table.

Weekday encoding: marker bit7 plus weekday bits; Monday through Saturday use bits1..6,
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

Accept 16 only with byte13 bit5 clear and bytes 7..9 zero;19 F1 uses14, F4 uses15, all other markers do nothing;20 uses14. These are distinct from the other profiles.

The accepted report proves an init-handler RTC write but no fixed pre-write delay; HA sends it during session initialization and keeps the proven500 ms post-write pacing.

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

The connected rename caller applies Java `String.trim` (outer code points
U+0000 through U+0020) before encoding and rejects an empty result. This is
package-specific caller handling, not Unicode whitespace normalization. The
conditional UTF-8/code-unit-copy model above remains qualified as documented.
