# ROW Control

Select **ROW Control** explicitly in the bed-type list. Use the Bluetooth
address of the bed and choose the layout shown by your app in **App controls**.
The layout is a UI choice, not proof of physical motor count or bed model.
Shared services, names and manufacturer data do not select this app automatically.
Generic SBI, Keeson and other app profiles keep their existing behavior.

**Reset** is an opaque app-named held action for Elevate, Lifestyle and Curve.
Its physical effect is unverified; the name does not promise a factory reset.
It sends `e5fe1600100008ee` every100ms while held and the ordinary zero release
`e5fe160000000006` when ended or cancelled. The card button also offers the
existing finite press adapter. Lifestyle Plus and Zero-G Box do not expose
Reset, because their Reset views are inactive in the accepted app source.

Accepted artifact: `com.sfd.row` version **2.0**.
Artifact-set SHA-256: `eeb3fac46a412395cddd0986d85cf2d4b141880b068f4e4f81baac305e1d43ee`.
Static app behavior is proven; actual bed effects, radio delivery and firmware
interpretation remain **UNVERIFIED**. Real users can validate these after a beta
or release; no immediate maintainer hardware test is required.

## Setup and controls

Layouts: **Elevate**, **Lifestyle**, **Curve**, **Lifestyle Plus**, **Zero-G Box**. Each physical side of a two-address
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
| Elevate | Head Up | `head_up` | `0x1` | held |
| Elevate | Head Down | `head_down` | `0x2` | held |
| Elevate | Foot Up | `foot_up` | `0x4` | held |
| Elevate | Foot Down | `foot_down` | `0x8` | held |
| Elevate | Anti Snore | `anti_snore` | `0x8000` | held |
| Elevate | Tv | `tv` | `0x4000` | held |
| Elevate | Lounge | `lounge` | `0x2000` | held |
| Elevate | Reset | `reset` | `0x08001000` | held |
| Elevate | Flat | `flat` | `0x8000000` | single |
| Elevate | Zero G | `zero_g` | `0x1000` | single |
| Elevate | Timer | `timer` | `0x200` | pulse |
| Elevate | Massage Head | `massage_head` | `0x800` | pulse |
| Elevate | Massage Foot | `massage_foot` | `0x400` | pulse |
| Lifestyle | Head Up | `head_up` | `0x1` | held |
| Lifestyle | Head Down | `head_down` | `0x2` | held |
| Lifestyle | Foot Up | `foot_up` | `0x4` | held |
| Lifestyle | Foot Down | `foot_down` | `0x8` | held |
| Lifestyle | Anti Snore | `anti_snore` | `0x8000` | held |
| Lifestyle | Tv | `tv` | `0x4000` | held |
| Lifestyle | Lounge | `lounge` | `0x2000` | held |
| Lifestyle | Reset | `reset` | `0x08001000` | held |
| Lifestyle | Flat | `flat` | `0x8000000` | single |
| Lifestyle | Zero G | `zero_g` | `0x1000` | single |
| Lifestyle | Timer | `timer` | `0x200` | pulse |
| Lifestyle | Massage Head | `massage_head` | `0x800` | pulse |
| Lifestyle | Massage Foot | `massage_foot` | `0x400` | pulse |
| Curve | Head Up | `head_up` | `0x1` | held |
| Curve | Head Down | `head_down` | `0x2` | held |
| Curve | Foot Up | `foot_up` | `0x4` | held |
| Curve | Foot Down | `foot_down` | `0x8` | held |
| Curve | Anti Snore | `anti_snore` | `0x8000` | held |
| Curve | Tv | `tv` | `0x4000` | held |
| Curve | Lounge | `lounge` | `0x2000` | held |
| Curve | Reset | `reset` | `0x08001000` | held |
| Curve | Flat | `flat` | `0x8000000` | single |
| Curve | Zero G | `zero_g` | `0x1000` | single |
| Curve | Light | `light` | `0x20000` | single |
| Curve | Timer | `timer` | `0x200` | pulse |
| Curve | Massage Head | `massage_head` | `0x800` | pulse |
| Curve | Massage Foot | `massage_foot` | `0x400` | pulse |
| Lifestyle Plus | Head Up | `head_up` | `0x1` | held |
| Lifestyle Plus | Head Down | `head_down` | `0x2` | held |
| Lifestyle Plus | Foot Up | `foot_up` | `0x4` | held |
| Lifestyle Plus | Foot Down | `foot_down` | `0x8` | held |
| Lifestyle Plus | Anti Snore | `anti_snore` | `0x8000` | held |
| Lifestyle Plus | Tv | `tv` | `0x4000` | held |
| Lifestyle Plus | Lounge | `lounge` | `0x2000` | held |
| Lifestyle Plus | Flat | `flat` | `0x8000000` | single |
| Lifestyle Plus | Zero G | `zero_g` | `0x1000` | single |
| Lifestyle Plus | Light | `light` | `0x20000` | single |
| Lifestyle Plus | Timer | `timer` | `0x200` | pulse |
| Lifestyle Plus | Massage Head | `massage_head` | `0x800` | pulse |
| Lifestyle Plus | Massage Foot | `massage_foot` | `0x400` | pulse |
| Zero-G Box | Head Up | `head_up` | `0x1` | held |
| Zero-G Box | Head Down | `head_down` | `0x2` | held |
| Zero-G Box | Foot Up | `foot_up` | `0x4` | held |
| Zero-G Box | Foot Down | `foot_down` | `0x8` | held |
| Zero-G Box | Anti Snore | `anti_snore` | `0x8000` | held |
| Zero-G Box | Tv | `tv` | `0x4000` | held |
| Zero-G Box | Lounge | `lounge` | `0x10000` | held |
| Zero-G Box | Flat | `flat` | `0x8000000` | single |
| Zero-G Box | Zero G | `zero_g` | `0x1000` | single |
| Zero-G Box | Light | `light` | `0x20000` | single |
| Zero-G Box | Timer | `timer` | `0x200` | pulse |
| Zero-G Box | Massage Head | `massage_head` | `0x50` | held |
| Zero-G Box | Massage Foot | `massage_foot` | `0xa0` | held |

`held` repeats until bounded release; `pulse` sends once then releases after
300 ms; `single` sends once. `tap_zeros` sends once followed by zero frames at
+300/+400/+500 ms. `held_zeros` also schedules those three zero frames from the
start of the hold, retaining them after ordinary early release. Cancellation
and disconnect never leave background writers from an old operation.

The regular key frame is `E5 FE 16`, a low32 little-endian mask and one inverted
sum byte. Clock frames are `E7 80 01`, local year minus 1900 (low byte), zero-based
month, day, hour, minute, second and checksum. Name frames are `EF 02` with a
15-byte zero-filled region and checksum. ROW has no observed UI maximum; HA
accepts the safely fitting 15 UTF-16 units and rejects 16 units (checksum overwrite)
or more before writing. The copy count is measured in UTF-16
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

Accept 16/19/20 with bit5 gates at13 for16 and14 for19; status14/15/14. Zero-G Box has an empty timer-update method, so it gets no invented timer state.

The app queues its initial clock after 2 seconds, with 500 ms post-write pacing.

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
