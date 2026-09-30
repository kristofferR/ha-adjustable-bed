# Customatic app profiles

Select **Customatic Clarity**, **Customatic Jerome's**, or **Customatic Remedy** to match the Android app supplied with the bed. The profiles share their BLE service, command characteristic, and discovery names, so an advertisement cannot select the correct app profile. Device Information strings do not select capabilities either.

Support comes from accepted, frozen COMPLETE/FULL analyses of these three version 1.0.1 packages, followed by cluster 009 reconciliation and an independent acceptance check. Physical operation remains unverified. Existing OKIMAT, DewertOkin, and other controllers remain separate.

| Profile | Package | Motors | Memory page | Light |
|---|---|---|---|---|
| Clarity | `com.okin.bedding.customaticclarity` | Back, legs | Yes | Toggle |
| Jerome's | `com.okin.bedding.customaticjeromes` | Back, legs | No | None |
| Remedy | `com.okin.bedding.customaticremedy` | Back, legs, lumbar | Yes | Toggle |

Each package hard-codes its app constructor layout; unreachable product selectors do not create additional HA variants. Jerome's separately reachable restored fragment changes its Flat endpoint, as described below. The apps identify initial scan candidates using the case-sensitive prefixes `OKIN` and `iFlex_Bed`. Clarity and Remedy can reconnect using a saved address. Jerome's constant-true connection check makes its stored-address reconnect branch unreachable; selecting a physical bed slot directly remains reachable. Those shared names identify candidates, not the app. Manual selection remains necessary.

## BLE packets and movement

The command service is `62741523-52f9-8864-b1ab-3b3a8d65950b`; its writable characteristic is `62741525-52f9-8864-b1ab-3b3a8d65950b`.

Every command is exactly six bytes: `04 02` followed by an unsigned 32-bit mask in big-endian order. A temporary checksum buffer in the app is discarded and never transmitted. There is no transmitted checksum, sequence number, authentication payload, or position response.

| Action | Mask | Packet |
|---|---:|---|
| Back up | `0x00000001` | `04 02 00 00 00 01` |
| Back down | `0x00000002` | `04 02 00 00 00 02` |
| Legs up | `0x00000004` | `04 02 00 00 00 04` |
| Legs down | `0x00000008` | `04 02 00 00 00 08` |
| Lumbar up, Remedy only | `0x00000010` | `04 02 00 00 00 10` |
| Lumbar down, Remedy only | `0x00000020` | `04 02 00 00 00 20` |
| Motor release | `0x00000000` | `04 02 00 00 00 00` |
| Flat, Clarity/Remedy | `0x08000000` | `04 02 08 00 00 00` |
| Fresh Flat, Jerome's | `0x10000000` | `04 02 10 00 00 00` |
| Light toggle, Clarity/Remedy | `0x00020000` | `04 02 00 02 00 00` |

Motor commands refresh at 120 ms intervals. Ending a motor movement sends a fresh zero mask after 100 ms; explicit Stop sends zero immediately. Cleanup runs after cancellation and outside the requested movement deadline. HA's duration is an elapsed-time ceiling for active refresh, so no extra refresh occurs after that deadline. The configured pulse count applies to ordinary cover actions; the interval remains the app's 120 ms.

All motor covers on one physical bed share the global scheduler resource because zero releases every motor. A Stop from any axis can therefore preempt movement on another axis. Two-address paired children retain separate physical-side resources.

`adjustable_bed.customatic_move_simultaneously` accepts an `actions` mapping with `back`, `legs`, and, for Remedy, `lumbar` mapped to `up` or `down`, plus a duration in seconds. Different motors may run in opposite directions. All eight safe states for two motors and all 26 for three motors are supported. The controller uses canonical axis order back, legs, lumbar and exposes equivalent held-control strings such as `back_up+legs_down+lumbar_up`. Opposite directions on the same motor are rejected before any write.

The normal Flat action sends one packet on Clarity/Remedy. Jerome's fresh screen sends the alternate flat packet three times consecutively, without an app-side interval or release. Its restored fragment has a separately reachable generic flat action: the **Restored Flat** button sends `04 02 08 00 00 00` once. This persisted UI route does not justify switching every Jerome's flat action to the generic packet.

Light is a single toggle packet with no release. Its state and brightness are unknown; HA exposes no inferred on/off state or discrete power commands.

The artifacts leave the Android characteristic write type unchanged. Its runtime value is unknown. HA validates the exact command service/characteristic and uses acknowledged writes when the characteristic advertises `write`, otherwise unacknowledged writes when it advertises only `write-without-response`. This property policy is an implementation choice, not a claim that the app or every physical bed uses a fixed ATT write mode.

## Memory controls

Clarity and Remedy have five independently held app controls. HA preserves their literal names instead of assigning physical meanings to `ZG` or `ANTI`. These controls do not establish numbered memory slots.

| Control | Mask |
|---|---:|
| Flat | `0x08000000` |
| ZG | `0x00001000` |
| ANTI | `0x00008000` |
| Program | `0x80000000` |
| Incline | `0x00004000` |
| Save ZG, Program + ZG | `0x80001000` |
| Save Incline, Program + Incline | `0x80004000` |
| Reset, Flat + Program | `0x88000000` |

The named **ZG**, **ANTI**, **Incline**, **Program**, **Save ZG**, **Save Incline**, and **Reset** buttons hold their mask for 2700 ms. This is the app's save/reset confirmation threshold, not a hardware acknowledgement or proof of successful storage. Memory refresh ends without a STOP/release packet, including after cancellation. Generic numbered recall/program entities remain unavailable.

`adjustable_bed.customatic_hold_memory` accepts any nonempty subset of `flat`, `zg`, `anti`, `program`, and `incline` in its `actions` list. All 31 subsets are represented by OR-ing the corresponding bits. The duration accepts 0.1–60 seconds, in whole milliseconds. For example:

```yaml
action: adjustable_bed.customatic_hold_memory
data:
  device_id: YOUR_BED_DEVICE_ID
  actions: [program, zg]
  duration: 2.7
```

Duplicate or unknown controls, empty selections, and mixed motor/memory selections are rejected before writing. Flat + ZG (`0x08001000`) and Flat + ANTI (`0x08008000`) remain available as literal combinations. The unused app helper named `resetMemory()` does not redefine Flat + ZG as Reset.

HA starts an already-selected composite mask immediately and maintains one 120 ms refresh lane. It does not replay a particular sequence of Android touch-down events or their phase-dependent first composite tick. This preserves the reachable BLE masks while giving the HA action a deterministic duration.

## Device information and connection lifecycle

The Device Information service is `0000180a-0000-1000-8000-00805f9b34fb`.

| Read order | Field | Characteristic |
|---|---|---|
| 1 | Manufacturer | `00002a29-0000-1000-8000-00805f9b34fb` |
| 2 | Hardware revision | `00002a27-0000-1000-8000-00805f9b34fb` |
| 3 | Software revision | `00002a28-0000-1000-8000-00805f9b34fb` |
| 4 | Firmware revision | `00002a26-0000-1000-8000-00805f9b34fb` |
| 5 | Model | `00002a24-0000-1000-8000-00805f9b34fb` |

The app schedules these at 0/120/240/360/480 ms after connecting and retries the whole batch from its information screen if any cached field is null. HA reads all five at connection discovery and exposes **Refresh Device Information** for a whole-batch retry. Reads are serialized with at least 120 ms spacing and a two-second bound per read. Missing characteristics or read failures leave cached values intact and do not block bed controls. Successful reads decode UTF-8 with replacement for malformed sequences, matching Java's decoding behavior. Empty strings are cached values, not missing fields.

The five diagnostic sensor state keys are `customatic_manufacturer`, `customatic_hardware_revision`, `customatic_software_revision`, `customatic_firmware_revision`, and `customatic_model`. These strings are also included in controller diagnostics. No field controls packet construction, app selection, or capabilities.

There is no reachable notification subscription, motor position read, massage control, pairing/authentication exchange, custom settings write, firmware update, or MTU negotiation in these app profiles. Cached information requires no notification channel and works with angle sensing disabled.

Jerome's app can fan out the same packet to two selected physical beds. Use an explicit two-address HA pair or target both configured devices to reproduce that scope. These profiles have no packet-side selector and do not support a single-address logical pair. HA supplies connection checks, command serialization, cancellation, and reconnect management instead of inheriting the app's constant-true connection check.

## Evidence boundaries and exclusions

The comparison deliberately excludes these source behaviors:

- Unreachable alternate product constructors, hidden memory/lumbar/light actions outside their app profile, unused notify/custom-settings UUIDs, and the caller-free `resetMemory()` wrapper. Its mask remains reachable through Flat + ZG.
- Opposing direction bits for one motor, mixed motor/memory masks created by shared mutable UI state, cross-fragment command overwrites, and duplicate/interleaved touch refresh chains. HA exposes independent safe masks through its serialized command queue.
- The Android final-release callback reads a mutable command 100 ms later and can send a newly started movement instead of zero. HA captures the zero release explicitly and waits for cleanup before the next command.
- Held callbacks surviving disconnect or restarting motion after reconnect, uncancelled overlapping information batches, stale save/reset confirmation callbacks, and app-specific fragment/pager restoration plumbing. HA preserves the two reachable Jerome's flat endpoints, not the surrounding UI races.
- BLE library cache/LRU behavior, connection UI bookkeeping, Android permissions, localization, and package delivery differences. HA uses its own Bluetooth lifecycle and explicit physical targets.

Physical verification of movement labels, save/reset effects, light behavior, and write-property compatibility is deferred to real users after release. Exhaustive artifact-derived implementation does not depend on maintainer access to these beds.

Artifact-set SHA-256 identities:

| Package | SHA-256 |
|---|---|
| Clarity 1.0.1 | `1b1aeb6dc79d51b0b0ff4cce9fcb1e3fc0c1a99bc9fab12df683860d6e881c0d` |
| Jerome's 1.0.1 | `056431dcd500bbf02f3279d052e66f8f59ca5cd30bd51d1aab18c23a1782f268` |
| Remedy 1.0.1 | `382e76adcf0750d937b9f84669db0100111ba95ad92122b45a8547be6d609c57` |

The raw APKs, decompilation output, frozen reports, full promotion audits, and cluster reconciliation remain machine-local. Durable implementation vectors are in `tests/test_customatic.py`; configuration, entity, and service routing tests cover public integration exposure separately.
