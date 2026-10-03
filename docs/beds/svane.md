# Svane Remote

Svane Remote **Version 1.8 (8)**, package `com.svane.svaneremote`, has two explicit BLE profiles. Static artifact behavior is verified; these profiles have not been validated on physical hardware. The separate [Jensen](jensen.md) and [Jensen LinOn](jensen.md#linon) profiles retain their own behavior.

| Configuration | App route | Endpoint |
| --- | --- | --- |
| `svane_remote_multi` | P1 multi-service | Exact head, feet and lamp roles below |
| `svane_remote_jmc` | P2 JMC400 | `1234` / `1111` |
| `auto`, or an older Svane entry without a variant | P1 compatibility default | No automatic rewrite of existing entries |
| `jensen_linon` | Jensen Adjustable Sleep | Separate one-byte controller |

Select the Svane app explicitly. A new setup with a scanned name containing case-sensitive `JMC` chooses its JMC variant; explicit variants override that new-selection rule. Existing entries retain their stored variant. The shared JMC name and service also occur in the Jensen route and do not prove this app's features. The source's individual discovery names are exactly case-sensitive `Svane Bed` and `JMC400`; its selected-name rule uses case-sensitive `JMC` to choose P2. HA accepts a known address with an explicit profile, including a changed advertising name. No PIN, pairing, model inference or manufacturer filter is introduced for Svane Remote.

The source exposes two axes, head/backrest and feet/seat+footrest. Their cover identities retain the integration's existing `back` and `legs` keys. Physical actuator count and numeric position units are unknown. Motor-count, angle sensing, massage and repeat-count settings are hidden for these app profiles. There are no measured-angle sensors or position sliders.

## Roles and initialization

All short UUIDs below expand to `0000xxxx-0000-1000-8000-00805f9b34fb`. Roles are resolved by **service and characteristic**, because direction and position UUIDs occur in both axis services.

| Service | Characteristic | Role |
| --- | --- | --- |
| `abcb` | `01ac`, `bae9`, `143d`, `fb6e` | Head up, down, opaque position, Svane position |
| `c258` | `01ac`, `bae9`, `143d` | Feet up, down, opaque position |
| `d07b` | `a8e0`, `b5e9`, `3fb2` | Lamp intensity/on/off, increase, decrease |
| `1234` | `1111` | P2 commands and opaque position; normal initialization also uses this role on P1 |
| `180a` | `2a26`, `2a27`, `2a29` | Firmware, hardware, manufacturer observations |
| `f92a` | `a592` | Normal software query `040000000000` |

Writes require an advertised write property. HA prefers write without response when advertised, otherwise uses the advertised write-with-response mode. This is a host delivery policy; the APK inherits Android's characteristic write type. Missing, ambiguous or nonwritable command roles fail before a guessed fallback write.

The app waits 100 ms after its connection callback before discovery. Bleak owns service resolution during connection; the controller retains a 100 ms initialization pause before its application reads. It reads firmware, waits one second, reads hardware, waits one second, reads manufacturer and waits one second. HA runs these paced reads in the background after the subscription below, so they do not delay the first command, and a failed read never fails the connection. Completed fields survive a later read failure within the physical target's process session.

Normal initialization subscribes to old `1234/1111`, even on P1, then submits the software query to `f92a/a592`. Host subscription completion precedes the query. Missing old notification support is reported as unavailable, rather than reproducing the app's null dereference. A failed subscription (for example a proxy without a free notification slot) is reported as failed and keeps motor control. Initial descriptor state advances to the feet position read, followed by the old role read. Explicit refresh/save reads head then old, followed by feet then old. Every present pair is attempted in order even if an earlier read succeeds or fails. Supported notification roles use the backend subscription API, which owns CCCD writes.

Connection, metadata and successful submissions do not prove authentication or hardware acknowledgement. The query has no inferred response decoder. Refresh Device Information exposes the normal reads again.

## Motion and release

P1 writes `0100` to the selected axis/direction role and releases with `0000` to that same started role. Host STOP attempts every started direction, including downward movement. There is no invented global P1 destination.

P2 sends `10 MASK 00 00 00 00`: head up/down masks `01`/`02`, feet up/down `10`/`20`, and combined masks `11`/`21`/`12`/`22`. Final held-motion release and explicit global STOP use `100000000000` on `1234/1111`. Explicit STOP sends this frame even when no held role is tracked, including during or after a memory recall. Failed or cancelled delivery retains that role for retry. Releasing one axis while the other remains active removes its mask and continues the remaining refresh without an immediate global STOP.

Head and P2 combined actions start immediately and schedule the next pass 100 ms after work. Feet-only and P1 separate-axis fallback wait 100 ms before feet, then schedule another 100 ms after work. These are held refreshes, not a source fixed repeat count. Ordinary cover actions use a bounded one-second host duration. Generic `timed_move` uses its active task-local pulse plan to keep the selected axis active through the caller's elapsed ceiling, with the same native cadence and cleanup. All selected targets validate before dispatch, including the existing delayed-feet minimum; the explicit service accepts 0.1–60 seconds. Feet-only actions and P1 combinations require more than 0.1 seconds. If awaited writes or scheduling consume that remaining budget before the selected feet axis starts, the action reports an error and releases any started head role instead of reporting a successful incomplete combination. Cancellation and an explicit axis release remain normal exit paths. Cancellation, failed writes and controller detach attempt the actual movement releases independently of the cancelled event. A failed or cancelled release keeps its started role pending for the next serialized STOP; a successfully released role is retired.

`adjustable_bed.hold_control` offers `head_up`, `head_down`, `feet_up`, `feet_down`, the four corresponding `head_*_feet_*` combinations, and `light_adjust`. All selected profiles and live roles are validated before the first motion. Paired physical sides retain their own P1/P2 routes. `adjustable_bed.svane_release_axis` signals the active writer to release `head` or `feet`; it performs no separate BLE write outside command serialization. Global STOP still cancels and releases the whole action. A public hold captures each physical session's release boundary before connection preflight and scheduler admission; a later acknowledged axis release survives those waits and controller reconstruction. Earlier idle releases do not cancel a new hold. Generic timed movement validates static duration/profile constraints on disconnected capability controllers, then reconnects and validates every selected live GATT role before any movement.

## Memory and presets

The **Svane position** action keeps the `preset_zero_g` button ID that existing entries use, and sends one P1 `0300` to `abcb/fb6e`, or one P2 `108100000000` to `1234/1111`. The artifact does not prove a Flat, Zero-G or Anti-Snore meaning. Preset, lamp and memory actions do not append movement STOP.

The two source-labelled positions are **Read** and **TV** (public numbered memory slots 1 and 2). Save copies valid bytes from successful reads in its own head/old/feet/old refresh sequence; it sends no firmware save opcode. Missing, failed, empty or cancelled required reads leave the old slot intact instead of copying an earlier observation. Completed diagnostic observations remain available even when save fails.

- P1 copies the entire opaque head and feet arrays. Recall writes head bytes to `abcb/143d`, waits a cancellable second, then writes feet bytes to `c258/143d`. Length and endian interpretation are not invented. The app keeps these slots only in process memory; HA persists the saved bytes in the entry's Svane preferences, so they also survive a restart. A genuine app-profile change still clears them.
- P2 copies bytes 2–5 of a valid target position record. Slots persist per physical target, with source defaults Read `81388113` and TV `82738204`. Recall sends `1004` plus the stored four bytes. Missing observations and malformed preferences produce an unavailable/validation error, never a null overwrite or dormant command fallback.

Generic memory services and the paired parent's combined Memory button validate every selected target before dispatch. An unsaved P1 slot or malformed stored payload rejects the whole call before an earlier target can move; the controller still checks the slot during locked execution. A mixed P1/P2 pair recalls each physical target's own saved bytes after both slots pass validation.

Normal recall still appends no STOP. P2's explicit global STOP can interrupt recall independently of held-motion tracking. P1's opaque absolute-position recall has no proven STOP on its position characteristic and supplies no direction to select a directional release. Host STOP cancels a pending feet write during the one-second gap, but does not claim to halt a head recall already delivered. The integration does not guess a direction or write a fabricated STOP to the position characteristic. Idle notification teardown does not append a global STOP; started held-motion roles still receive their proven cleanup.

Physical-side caches survive paired parent ownership migration and separation. A genuine app-profile change clears the changed physical target's session and persisted Svane preferences, so switching back cannot restore old slots or intensity. Selecting an explicit P1 alias from `auto` or an older missing variant preserves that same effective profile and its local slots. A shared options form cannot change a Svane profile across two separate addresses: unpair and configure each side separately first. Common options and an unchanged rendered profile preserve mixed P1/P2 routes and target-local caches. The old dormant `3fff`, `3f40`, `3f80` and `3f81` writes are not reachable controls in this profile.

## Lamp and observations

Cold app-local lamp intent is off, remembered intensity is 90 and adjustment direction starts +5. The literal toggle sends remembered intensity on, or `130200000000` off. Explicit HA ON/OFF resends its requested branch. The switch remains unknown until an explicit lamp command, including attempted failed or cancelled delivery; that knowledge is process-local and survives same-target/profile reloads, while cold restart or profile reset loses it. Subsequent optimistic values are assumed; there is no native physical lamp-state feedback.

Lamp intensity is a persisted local preference, exposed through the established 0-100 light level slider so existing entries keep their entity. Setting 0 turns the lamp off; other values snap to the app's 5-100 steps of five and command the lamp on; action buttons, the light level number and the assumed-state switch share that local intent. Intent is published before delivery and remains local command intent after a failed or cancelled write, not physical readback. The source builder is `13 02 (JavaInt & ff) 01 00 64`; it is not clamped to 100. Full signed-32-bit boundary vectors test that builder, while the public control accepts the source user-step domain. P1 increase/decrease uses `b5e9`/`3fb2`; intensity and on/off use `a8e0`. P2 always uses `1111`.

The frozen app's held adjustment begins after more than 200 ms while local intent is on. It unconditionally reverses step at current intensity >=100 or <=6 before adding five: 90→95→100→95, and 10→5→10. The held HA control accepts the same 5–100, step-five range as the intensity number. At 5 or 100 it reverses only an outward step; an inward retained step continues toward the interior. This preserves valid HA local preferences after direct selections without broadening native builder inputs. It refreshes every 100 ms after work. Release ends the refresh without OFF or STOP. Local intent changes before each attempted delivery and survives write failure. Held adjustment persists changed final preferences once on exit, including failure or cancellation; neither is a hardware observation.

Diagnostic sensors expose completed firmware/hardware/manufacturer and opaque head, feet and P2 position bytes with separate observation timestamps. DIS has dispatch precedence. Exact axis `143d` responses preserve whole nonempty buffers; exact old `1111` records require at least six bytes and first byte `10`, preserve bytes 2–5 and ignore byte 1. Unknown roles, empty and short records are rejected. Raw records, stored slots and successful writes do not become angles, percentages, capability flags or hardware state.

See the [complete disposition ledger](../apk-analysis/dispositions/row130-svane.md) for all 663 rows and every exclusion. Classic RFCOMM, firmware updates, dead builders, phone-only functions and precise unsafe source fragments remain excluded. Physical captures are deferred to real users after beta/release.
