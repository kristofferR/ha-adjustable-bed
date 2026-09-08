# LOGICDATA MOTIONrelax phone and tablet apps

These explicit app profiles implement the accepted Phase 4 cluster-006 evidence:
`com.logicdata.app.android.bed` **1.0.6 (7)** and
`com.logicdata.app.android.pad.bed` **1.0.4 (5)**.
**Static verified, hardware unverified.**

## Setup

Select the LOGICDATA MOTIONrelax app option and choose the phone or tablet app,
packet family, and physical layout. The Bluetooth service alone cannot identify
those choices. Existing Jiecang and SILVERmotion/SimplicityFrame configurations
retain their previous behavior.

The standard family supports two motors; three motors with neck, lumbar, height
or split-upper controls; four motors; and split-series controls. Standard layouts
have independent massage and under-bed light settings. Vienna and Toronto are
aliases for two-motor layouts with different massage settings. The middle-motor
family provides back, legs, flat, two memory slots and lighting.
Choose its dedicated middle layout with P2; the remaining layouts use P1.

For two separately addressed beds, configure each side before combining them.
Shared paired-bed options preserve each side's app, packet family, layout and
transport. Unpair temporarily to change those per-side settings.

Automatic transport selection keeps each service's write, notification and name
characteristics together. Explicit T1, T2 and T3 choices are available. T2 can be
used through a known address, but its standalone route has no startup query burst
in either app. No PIN or pairing flow is inferred from these artifacts.

## Controls and state

Both families provide two memory recall and save actions. Movement repeats every
100 ms, with the app's final movement write on normal completion and short release
after 100 ms. Cancellation sends the proven release without another movement
write. Timed moves include the terminal write and release delay in the requested
duration, rounded up to the next 100 ms interval. A 100 ms request sends one
movement frame and releases at 100 ms; a 1000 ms request releases at 1000 ms.
Memory, lighting and massage keep their own action-specific timing.

For the middle family, `adjustable_bed.logicdata_hold_preset` holds flat, memory 1
or memory 2 for a chosen duration. It refreshes flat every 100 ms or memory every
200 ms and releases on completion or cancellation. Ordinary one-shot preset
buttons remain available.

Standard massage controls expose Off and levels 1–3, including the separate right
zone on split layouts. Under-bed lighting is a toggle with notification readback.
Neither app reports motor positions, brightness or RGB color, so the integration
does not create those controls.

The phone profile synchronizes the clock and supports weekly native alarm
configuration through `adjustable_bed.logicdata_set_alarm` when the standard
family is selected. Choose weekdays, time, a supported preset, and back/leg
massage levels. The tablet profile has no clock or alarm BLE implementation.
The apps' dormant local wake automation is excluded.

`adjustable_bed.logicdata_rename` changes the Bluetooth device name when the chosen
transport provides a name characteristic. Its service description lists the
supported input. This is separate from the Home Assistant friendly name.
The service accepts 1–255 printable ASCII characters, a deliberate input policy
that avoids the tablet app's malformed Unicode name encoding.

## Evidence

The [whole-cluster disposition](logicdata-app-disposition.md) records every
reachable command, the phone/tablet differences, report hashes and exclusions.
Accepted frozen reports remain unchanged. Hardware actuator mapping, delivery
timing and firmware behavior remain deferred validation for users after a beta
or release.
