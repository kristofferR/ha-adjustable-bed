# ERGOBALANCE, Dream Motion and Dream Motion HD app profiles

These explicit profiles implement the accepted APK Protocol Audit cluster-004 evidence for
`com.jiecang.dreamask.app.android.bed` **1.0.8 (8)** and
`com.jiecang.dreamotion.app.android.bed` **1.0.5 (11)**.
**Static verified, hardware unverified.** Existing legacy Jiecang configurations
keep their previous behavior.

## Setup

Select **Jiecang (ERGOBALANCE / Dream Motion / Dream Motion HD apps)**, then choose the exact app
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
- `adjustable_bed.rename` (or the older `jiecang_rename`) writes a Bluetooth
  name of up to 20 ASCII letters or digits. This changes the advertised device name, separately from
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


## Dream Motion HD 1.0.4

Choose **Dream Motion HD** for `com.dreamhd.jiecang.android.pad.bed`
1.0.4 (4). This explicit tablet profile is based on independently accepted
row105 evidence. It does not migrate existing phone-app or legacy entries.
See the [complete discovery ledger](dreamhd-disposition.md) for evidence seals,
all 50 command rows, 90 candidate dispositions, consumer behavior and safe HA
adaptations. Static behavior is verified; physical effects remain unverified.

The HD app has six standard layouts: two motors; neck, lumbar, height or
split-upper; and four motors with neck/lumbar. Each has independent massage and
light choices, plus a separate split-series layout, totaling 25 app
configurations. Bilateral and split-after-bilateral belong to other profiles
and are rejected for HD. Layout, massage and light are user choices, never
inferred from the name or a shared service. The existing setup massage option
and **Enable light controls** apply. Motor refresh is fixed at 100 ms.

HD uses its own startup status queries and one short release 100 ms after
movement or a preset. It has two memory slots with different packet payloads
from the phone apps. Massage is Off and levels 1–3 (wire 0/2/3/4); normal steps,
mode changes and stop write once. Right-back and leg feedback share byte 6 on
split layouts, so both sliders report that value rather than inventing a third
feedback field. Intensity changes await notification feedback.

RGB color, brightness and timeout use the app's BGR packet. The repaired
feature predicate uses minimal binary, appends zeros, truncates and reverses;
it is not a conventional bit mask. A negative reply hides the picker and
persists suppression. A later positive reply reveals it without clearing
suppression. A light-status reply reveals only the picker when suppression is
clear, never the automatic-light switch. Connection resets light visibility
and cached color. HA always honors **Enable light controls**, even where the
Android UI would reveal a picker despite that preference. Automatic-light
status treats zero as off and any nonzero value as on. Its physical sensor
meaning has not been established.

The normal controls, weekly-alarm services and wake services above work for
HD. Its broadcast-derived wake routine starts leg massage at 500 ms, split
right massage at 180 ms, and repeats the preset at 800–920 ms. HA adds the
proven short release on completion and independently attempts to stop wake
massage on cancellation or failure, including a failed release write. It never copies Android's missing release/cancel cleanup.

`adjustable_bed.rename` accepts 1–20 printable ASCII characters, including
spaces, for HD. G1 writes the bare name; G3 prefixes a byte length. HA safely
corrects Android's malformed G3 lengths 10–15 and rejects its lossy non-ASCII
encoding. The older `jiecang_rename` alias keeps its narrower released schema.
G2 has no name channel and no startup-query burst when selected alone; it can
be connected manually but standalone setup completion is not a hardware claim.

Late capability and RGB replies add the corresponding controls without reloading
HA. Repeated negative and positive feature replies retire and recreate the
RGB, brightness, timer, automatic-light and Yoga controls as their gates change.
