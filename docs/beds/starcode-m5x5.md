# AdjustableM5X5 app

Select **AdjustableM5X5 app** for the artifact-verified behavior of `com.starcode.abm5_5` 1.2.3 (version code 6). Hardware validation remains unverified. The generic BOX25 and Elevate routes retain their other app contracts.

## Exact profile and session

Enter the exact case-sensitive Bluetooth name separately from a friendly name:

| Prefix, in factory order | Profile |
|---|---|
| `STAR254205`, `STAR255401` | F23 |
| `STAR255402`, `STAR255403` | Kneading |
| Remaining `STAR25` | CB25 |
| `ELEVATE` | Elevate |

These names and the shared transport cannot distinguish the app from other software. Discovery asks the user to choose the app. All four bedding classes may occupy either the main or an independently addressed lift slot. Desk, TV, seating and unknown fallback classes fail the artifact's bedding feature guards.

Required services/roles are Nordic UART `6e400001-b5a3-f393-e0a9-e50e24dcca9e`, write `6e400002-…`, notify `6e400003-…`, Device Information `0000180a-0000-1000-8000-00805f9b34fb`, and readable firmware `00002a28-…`. Optional manufacturer is `00002a29-…`. RX subscribes before the sender initializes. Every write uses **without response**. Bleak selects notification/indication subscription from actual properties; the Android request for MTU 512 does not establish a mandatory peripheral MTU.

Each manufacturer byte becomes a character, is lowercased and is compared **exactly** with `star`. Equal selects the Star dialect; empty, missing, failure or other strings select legacy. No substring match or whitespace stripping occurs. Firmware uses the same character-code concatenation; a failed five-second read is explicit diagnostic state. Manufacturer has a one-second read budget. No custom PIN or owned bonding call is inferred.

Star CB25/F23/kneading and Elevate enqueue one `5a0b00a5` initialization frame on the next 100 ms tick. Legacy CB25/F23/kneading do not unconditionally wake. F23/kneading then send local-clock correction. RGB query follows settled manufacturer selection. Every session owns its callbacks; old subscriptions cannot publish into a replacement session.

## Packets and commands

| Builder | Legacy | Star |
|---|---|---|
| Normal key | `05 02 BE32(key) 00` | `5a 01 BE32(key) a5` |
| Extended value | `04 e0 key value 00 00` | `5a e0 04 key value 00 00 a5` |
| Query | `00 b0` | `5a b0 00 a5` |

Legacy light on/off uses `08 02 00 00 00 00 BE32(key)`, with keys `40` and `80`. Star bedding keys have high bytes `03 10 30`. The delimiter is literal, with no inferred checksum, sequence, encryption or fragmentation. Dynamic extended fields retain their low eight bits; normal builders retain the low 32 bits.

| Action | Legacy key | Star low byte |
|---|---|---|
| Head up/down | `1` / `2` | `00` / `01` |
| Foot up/down | `4` / `8` | `02` / `03` |
| Lumbar up/down | `10` / `20` | `04` / `05` |
| Head and foot union up/down | `5` / `a` | `0c` / `0d` |
| STOP/release | `0` | `0f` |
| Main interrupt | `0` | `1f` |
| Flat / Ascent (TV) / Zero Gravity | `08000000` / `4000` / `1000` | `10` / `11` / `13` |
| Anti-Snore / Lounge / M1 / M2 | `8000` / `2000` / `10000` / `40000` | `16` / `17` / `1a` / `1b` |
| Save Ascent / Zero Gravity / Lounge | `08004000` / `08001000` / `08002000` | `92` / `90` / `91` |
| Save M1 / M2 / reset saved positions | `08010000` / `08040000` / `88000000` | `94` / `95` / `96` |
| Head massage increase/decrease | `0800` / `00800000` | `66` / `67` |
| Foot massage increase/decrease | `0400` / `01000000` | `68` / `69` |
| Wave increase/decrease | `10000000` / `04000000` | `58` / `59` |
| Massage toggle/off | `0100` / `02000000` | `5a` / `6f` |
| Light cycle | `040000` | `70` |

Elevate uses Star low bytes `40/41` for actuator 1, `42/43` for actuator 2, `44/45` for both, `46` for one-shot flat, `0f` STOP and `4f` interrupt. It has no inferred lumbar, programming, massage, RGB or semantic notification state.

Commands run on the next available **100 ms** sender tick, with one write in flight. Held app actions become bounded HA pulses and remain cancellable. Movement always releases with a fresh STOP event; relative massage adds the manufacturer-selected **base** query after neutral, including on F23/kneading. No configurable delay replaces the artifact's cadence.

Recalls send three copies followed by neutral. Ordinary light/massage toggle/off send two followed by neutral. Timer, palette and brightness send one followed by neutral. F23/kneading light overrides send one followed by **Star** neutral, independent of the movement dialect. Five named/memory saves and reset send 55 attempts after STOP and have safe release cleanup. Completion means awaited transport delivery, never proof of physical motion or retained memory.

Extended keys `0`, `1`, `7` select brightness 1–6, palette index 0–7 and massage 10/20/30-minute choices respectively. No arbitrary RGB or absolute massage-intensity setter is inferred. F23/kneading RGB on/off/cycle/mode use Star low bytes `73/74/70/8a`, and their brightness, palette and query always use Star framing. Other inherited controls keep manufacturer selection.

For CB25, only names longer than 14 characters provide remote substring `[4:10]`. Remotes `252201`, `254202`, `352201` send mode 1 for 35 attempts, using legacy `00020004` or Star `7a`, without an extra neutral. Other names use Star `8a` followed by Star `0f`, including legacy sessions. F23/kneading always use that overridden mode path.

## Feedback and public controls

Head, foot and lumbar reports are clamped percentages; the other three raw progress slots remain diagnostics, not invented axes. HA exposes their confirmed percentage sliders and exact union control. No dead direct-position packet is enabled.

| Frame | Safe minimum | State |
|---|---:|---|
| `a5/0d` | 18 | Positions at 4/6/8; raw parts at 10/5/7; stopped when byte 17 is zero |
| `a5/0b` | 20 | Normal massage, RGB, and distinct sonic feedback |
| CB25 `a5/0c` | 17 | Main alarms, second slot only in Star dialect |
| F23/kneading `a5/0c` | 25 | Two advanced alarm records |
| F23/kneading `a5/0e` | 22 | EQ, volume/preset, frequency offsets and USB state |
| Kneading `a5/0f` | 8 | On/demo, mode clamped to 0–2, raw time |

Normal massage active uses OR of the encoded level nibbles; sonic active uses AND. Sonic frequency labels are 30 for raw 5, 40 for 9, otherwise 50 when either level is nonzero, and zero when both are zero. Normal, sonic and kneading time values stay **raw**, without invented physical units. Alarm repeat and hour/minute values remain raw; typed alarm attributes retain the exact enums and slot layout. EQ magnitudes/signs, raw volume, USB bit and prior sonic fields are retained. These alarm/sound/sonic/kneading domains are read-only because no reachable setters were established.

RGB palette values are white, red, orange, yellow, green, blue and purple. Wire indices 0–7 map through `max(index-1,0)`; larger nibbles use bytes 16–18 as direct RGB and select the nearest palette by RGB distance. HA reports that nearest palette color in the same wire numbering the palette select writes (0 off, 1 white through 7 purple), so a direct white reads as `1`, not off. Diagnostics expose the original/direct branch, RGB value, light mode and raw index. The physical meaning of index 7 still requires real-user validation.

Changed notifications are processed even within 200 ms. Short frames cannot publish a partial domain or crash. F23 receives base motor/normal state and independently applies sonic, advanced alarm and EQ handlers; kneading adds its own handler. It does not inherit the sibling CB25 main-alarm layout. No optimistic requested setting replaces received state. One feedback light owns on/off control, without a duplicate under-bed-light switch. Toggle uses the last observed state to choose the exact discrete on/off command; unknown or disconnected feedback requires an explicit turn-on or turn-off action. Native toggle packets from other app profiles retain their own behavior.

The Flutter Home page's RGB listener can request mode 1 from the currently selected main controller. HA replaces that page-selection behavior with the explicit **Light mode 1** action, preserving its exact builders and repeat counts. Received light state remains feedback; an old emitter cannot retarget a replacement controller or trigger a write merely because a page used to be visible. Startup checks session ownership after every read and initialization await, so a disposed or replaced session cannot revive the sender.

Read results stay local until ownership is checked before publication. Queued writes retain their original client and generation through sender-tick and BLE-lock waits; superseded work cannot emit packets into a replacement session or overwrite its firmware diagnostics.

## One main plus three lifts

Configure up to three other AdjustableM5X5 entries on the main entry. This supports **four physical targets**, one main plus three lifts, each with its own BLE coordinator. Use `adjustable_bed.starcode_move_lifts` with `up`, `down`, `flat` or `stop`. Each lift may be any of the four bedding classes; lift fanout uses only native union movement, STOP/interrupt and flat. Individual Elevate actuator controls remain available when restored in a main slot.

All selected targets must be ready before group writes. Individual main movement interrupts reachable ready lifts; individual lift movement interrupts its reachable ready main. Unloaded, disconnected or unready peers, and peer write failures, do not block a healthy individual control. Related pending group admissions are cancelled before peer writes, without requiring an offline peer to reconnect. Dedicated group movement still requires every selected member to be ready. Composite flat interrupts the group, sends main flat, waits **1600 ms**, then sends lift flat. Every target's connection is held through dispatch, delay and cleanup, including with Disconnect After Command enabled. STOP, changed selection, lost transport, replacement coordinator/controller/client/session or unload cancels delayed writes. Failure/cancellation cleans every admitted target. Group STOP first cancels retained delayed operations and attempts STOP on every reachable configured member, even if the main or another lift is unavailable. It reports missing members or transport errors after attempting the remaining targets. Movement admission still requires the complete selection to be ready. Successful Elevate flat receives no invented immediate STOP. Grouping does not transfer entity/device ownership into the Left/Right paired registry, and never fans out RGB, massage, programming or firmware updates.

## Evidence and deferred validation

The full [225-item disposition ledger](../apk-analysis/row005-dispositions.md) binds implementation and exclusions to code and executed tests. All 111 owned command rows, 138 inherited command routes, accepted packet/parser vectors and exhaustive enum branches have focused tests. Raw APKs, decompilation and frozen reports stay machine-local.

Real users after beta/release can validate five physical domains: movement/release and programming duration; units/actuator mapping; palette/brightness/modes; manufacturer/GATT/session observations; and multiple-device interrupt/flat/feedback behavior. Hardware is not needed to complete the proven static implementation. Actual peripheral write delivery, actuator cessation, negotiated MTU and the physical meanings of raw fields remain separately unverified.

## Group ownership and profile changes

A configured main and its selected lifts retain their standalone entry IDs.
Remove the lift selection before combining any group member into a Dual Bed.
The pairing picker rechecks this ownership when a previous selection is submitted.

A replacement group action waits for prior commands and their native STOP
cleanup on every shared member before claiming its targets. Cancelling a waiting
replacement leaves that cleanup running and admits no new writes. Explicit group
or individual STOP also invalidates pending admission, including during connection
preflight. Changed selection or unloaded members are rechecked before scheduled
actions; internal cleanup STOP does not invalidate the intended replacement.

Group-command suppression applies only while the exact scheduled group action
runs. A later ordinary command on the same scheduler still interrupts the group,
cancels its retained delayed movement and cleans up the admitted targets.
An individual command waits for those STOPs before scheduler admission, so old
cleanup cannot cancel its new movement. Caller cancellation leaves old cleanup
running; explicit STOP, changed selection, unload or a newer individual request
invalidates a waiting admission. Failed cleanup on an unavailable peer does not
block the healthy individual target.

Selecting Elevate retires the previous back, legs and lumbar position sliders
and every M5X5 telemetry entity. The BLE connection sensor and unrelated registry
rows retain their identities. Other profiles keep their active feedback entities.
