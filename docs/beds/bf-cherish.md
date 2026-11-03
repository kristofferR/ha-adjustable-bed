# BF and Cherish

Choose **BF (com.BF app, three motors)** or **Cherish
(com.okin.ore.cherish app)** in manual setup. Select the Bluetooth address
used by that app. Neither app provides an advertisement signature that can
safely select its profile. Shared FFE9/FFE4 characteristics do not identify
either product. Existing beds using other profiles are unchanged.

Support comes from accepted APK audits of `com.BF` 1.2.3 (11) and
`com.okin.ore.cherish` 1.0.4 (5), reconciled together as row063/cluster-001.
**Hardware status: UNVERIFIED.** Real-user captures after beta/release are
deferred external validation, not a prerequisite for implementing the proven
app behavior. Physical posture, stopping distance, alarm recurrence and
successful on-air delivery have not been established.

## Controls

| Feature | BF | Cherish |
| --- | --- | --- |
| Motors | Back, legs, independent head | Back and legs, plus combined up/down buttons |
| Presets | Flat, Zero Gravity, Quiet Sleep (anti-snore) | Flat, Zero Gravity, Quiet Sleep (anti-snore) |
| Memory | A/B, recall and program | A/B, recall and program |
| Light | Omitted: both app light branches send the Zero Gravity command | Separate on/off commands, assumed state |
| Massage | None | On/off, intensity 1–3, wave 1–3, timer 10/20/30 minutes |
| Bed alarm | Clock query, setting, notification state | Setting, persisted command intent, no response parser |
| Position feedback | None | None |

A second press of the same preset sends that profile's preset STOP. Preset
and memory taps share the app's selection state. Programming a memory preserves
the shared count: programming as the first action suppresses a subsequent tap
of that same memory until another preset or movement changes the selection.
Programming after a running preset makes the next same-memory tap send STOP.
This state survives reconnects but is not a hardware acknowledgement.

Movement refreshes use the app's 200 ms interval with a bounded HA pulse count.
Movement release uses `E5FE160000000006`; preset STOP is profile-specific.
HA attempts release on cancellation and errors, and explicit STOP attempts
both families. It cannot guarantee delivery on a failed Bluetooth link. Presets
and saves are single writes, without an automatic touch-release STOP.

Cherish starts massage with timer, wave after 100 ms, and intensity after
another 200 ms. Off sends intensity 0 and wave 0 after 100 ms, keeping the
selected levels and timer. At the bounds, +/- does not write. Selecting a timer
sends only its timer command and disables level changes until massage is
started again; it does not prove that the receiver stopped massage. There is
no massage feedback. HA serializes these sequences and finishes cancellation
cleanup, so an Android delayed callback cannot restart massage after Off.
The extra combined-motion buttons, massage numbers and alarm query are
available as entities in Home Assistant.

## Alarm action

```yaml
action: adjustable_bed.bf_cherish_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "08:30:00"
  memory: memory_1
```

`memory` is `none`, `memory_1` (A), or `memory_2` (B), never a bed side. Use
`enabled: false` to disable; the previous selected schedule remains in local
intent. Enabling always supplies a complete, valid time and explicit memory.
The clock comes from Home Assistant's configured local timezone.

BF sends an EB schedule with Sunday-zero weekday and a day mask for the next
occurrence; an equal hour/minute remains today. Cherish sends EA with its three
FF fields unchanged. These bytes do not prove any further recurrence semantics.
BF disable sends EB then EA; Cherish disable sends EA twice. The two packets
sample the current clock independently. There is no application alarm ACK.

The **Bed alarm** sensor exposes the last command or BF report, with time,
memory, raw BF selector and source attributes. Cherish intent persists across
HA restarts; expiry clears its local enabled indication. It does not restore
phone alarms or infer receiver state. BF's **Query bed alarm** button sends the
live E2 clock query. Cherish has no reachable query or alarm notification
consumer, so neither is synthesized for it.

BF recognizes E2FE16 and unsigned minute/hour/selector offsets 3/4/9. The app's
disabled condition is preserved exactly: minute > 59 **and** hour > 24. Unknown
selectors preserve the prior memory. HA safely ignores short packets rather
than reproducing the app's substring/index exceptions. Reports may contain
invalid times; they are diagnostic values, never automatically programmed.

HA deliberately requires explicit valid alarm fields instead of reproducing
the apps' unset FF time fields, BF's untouched 88 selector, delayed wheel races,
or Cherish's A-while-B branch that displays A while sending B. Selection and
persisted intent use the actual memory requested by the HA caller. No extra
bed command is invented to correct these phone defects.

## BLE transport and failures

Both profiles discover the parent service of FFE9 writes and FFE4 notifications;
they do not require the unused fixed service UUID declarations. Writes require
the ordinary WRITE property and use GATT responses, without inferring an Android
numeric write type. Each matching FFE4 attempts notification subscription;
failed subscription does not block controls. The last matching role is used
for payload consumption. There is no selected app read, authentication packet,
MTU request, fragmentation, capability query or firmware update route.

HA validates a connected writable role before submitting. Cancelled operations
can perform no write; write errors propagate and do not advance local preset
state. Transport submission, GATT completion and reported bed state are distinct.
HA's coordinator owns adapter/proxy selection, connection recovery, bounded
retry, command serialization and STOP preemption. It does not recreate Android's
100-pending FIFO, 10/100 ms queue scheduling, numeric errors or reflection-based
cache refresh. The apps themselves can reject an incoming STOP at queue capacity;
that defect is not copied into HA. No failure, disconnect or timeout alone
establishes physical stopping.

Wi-Fi provisioning, SSID/passwords, bed network administration, cloud/account
services and unrelated phone infrastructure are outside this BLE integration.
The exhaustive [disposition ledger](../apk-analysis/dispositions/row063-cluster001.md)
records the evidence and implementation treatment.
