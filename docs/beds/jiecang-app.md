# ERGOBALANCE and Dream Motion app profiles

These explicit profiles implement the accepted Phase 4 cluster-004 evidence for
`com.jiecang.dreamask.app.android.bed` **1.0.8 (8)** and
`com.jiecang.dreamotion.app.android.bed` **1.0.5 (11)**.
**Static verified, hardware unverified.** Existing legacy Jiecang configurations
keep their previous behavior.

## Setup

Select **Jiecang (ERGOBALANCE / Dream Motion apps)**, then choose the exact app
profile and control layout. Both apps use the same Bluetooth services, so a
service UUID cannot determine which app's release behavior or layout applies.

Layouts cover standard two motors; three motors with neck, lumbar, height or
split-upper controls; four motors with legacy or bilateral controls; and the
split series. The separate split-after-bilateral option preserves the app's
reachable combination of standard split movement and bilateral global commands.
It does not rely on accidentally retained Android settings.

Automatic transport selection uses a coherent GATT service and its corresponding
write, notification and name channels. Explicit G1/G2/G3 overrides are available.
ERGOBALANCE requires G1 or G3 to be present when selecting G2; standalone G2 is
supported only by Dream Motion's manual connection route. No pairing, PIN or
device-name pattern is inferred from these apps.

## Controls and state

The selected layout determines movement controls and massage zones. There are
two memory slots, with separate recall and save actions. Massage levels are
shown as Off and levels 1–3, mapped to the app's exact wire values. Optional light
controls include RGB, brightness, timeout and automatic under-bed lighting.
Notifications update available state; actuator-status packets are not motor
position feedback, so no position sliders or angle sensors are created.

Movement repeats every 100 ms. ERGOBALANCE sends its long release at 50 and
150 ms after a hold; Dream Motion sends its final movement packet followed by
short and long releases at 100 and 800 ms. Cleanup also runs when Home Assistant
cancels a command. Presets, save operations, massage and lighting retain their
own command sequences instead of sharing a universal repeat/stop schedule.

## Automations and services

- `adjustable_bed.jiecang_set_alarm` writes the app's weekly alarm configuration.
  It accepts a time, weekdays, wake preset and massage levels. Storing that
  configuration is separate from executing the Android app's local wake routine.
- `adjustable_bed.jiecang_wake` executes the proven wake packet sequence. Use a
  Home Assistant time trigger when local scheduling is required. Yoga can be
  encoded in the alarm configuration but is not an implemented wake choice in
  either app's executor.
- `adjustable_bed.jiecang_stop_wake` stops active wake massage without changing
  the saved alarm schedule.
- `adjustable_bed.jiecang_rename` writes a Bluetooth name of up to 20 ASCII
  letters or digits. This changes the advertised device name, separately from
  its friendly name in Home Assistant.

The normal cover, button, light, number and select actions remain available for
individual movement, presets, massage and lighting.

## Evidence and compatibility

The [complete cluster disposition](jiecang-app-disposition.md) records every
command group, both accepted report identities, shared behavior, six material
differences, implementation choices and exclusions. The implementation serializes
GATT operations, validates inputs and performs cancellation cleanup. It does not
reproduce Android's duplicate startup bursts, unsafe parser exceptions or
missing key/cancel cleanup.

Physical actuator mapping, GATT properties and behavior on real firmware remain
deferred validation for users after a beta or release. No raw APK or frozen
analysis is shipped with the integration.
