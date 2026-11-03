# BF and Cherish

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the BF app (`com.BF`, three motors)
- Beds controlled by the Cherish app (`com.okin.ore.cherish`)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BF](https://play.google.com/store/apps/details?id=com.BF) 1.2.3 (11) | `com.BF` |
| ✅ | [Cherish](https://play.google.com/store/apps/details?id=com.okin.ore.cherish) 1.0.4 (5) | `com.okin.ore.cherish` |

- Support comes from accepted APK audits of both apps, reconciled together as
  row063/cluster-001 (see [Analysis provenance](#analysis-provenance)).
- The apps share framing, not their command tables or alarm format.

## Features

| Feature | BF | Cherish |
| --- | --- | --- |
| Motors | Back, legs, independent head | Back and legs, plus combined up/down buttons |
| Presets | Flat, Zero Gravity, Quiet Sleep (anti-snore) | Flat, Zero Gravity, Quiet Sleep (anti-snore) |
| Memory | A/B, recall and program | A/B, recall and program |
| Light | Omitted: both app light branches send the Zero Gravity command | Separate on/off commands, assumed state |
| Massage | None | On/off, intensity 1–3, wave 1–3, timer 10/20/30 minutes |
| Bed alarm | Clock query, setting, notification state | Setting, persisted command intent, no response parser |
| Position feedback | None | None |

The extra combined-motion buttons, massage numbers and alarm query are
available as entities in Home Assistant.

## Protocol Details

**Service UUID:** none required (the parent service of the FFE9/FFE4 characteristics is used)
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** Fixed-length frames ending in a complement checksum

### Packet Format

| Packet | Bytes |
| --- | --- |
| Control key | `E5 FE 16` + key (4, big-endian) + checksum |
| Clock/alarm query (BF) | `E2 FE 16` + second, minute, hour, weekday (Sunday = 0) + checksum |
| BF alarm setting | `EB FE 16` + clock second, minute, hour + alarm minute, hour + weekday + day mask + `00 00` + selector + checksum |
| Cherish alarm setting | `EA FE 16` + clock second, minute, hour + alarm minute, hour + `FF FF FF` + selector + checksum |

- Checksum: the complement of the sum of all preceding bytes, low byte
  (`~sum & 0xFF`).
- Alarm frames carry the current Home Assistant clock (second, minute, hour).

### Write Mode

- Writes require the ordinary WRITE property and use GATT responses, without
  inferring an Android numeric write type.
- HA validates a connected writable role before submitting.

### GATT Roles

- Both profiles discover the parent service of FFE9 writes and FFE4
  notifications; they do not require the unused fixed service UUID
  declarations.
- Each matching FFE4 attempts notification subscription; failed subscription
  does not block controls.
- The last matching role is used for payload consumption.
- There is no selected app read, authentication packet, MTU request,
  fragmentation, capability query or firmware update route.

## Detection / Setup

- Choose **BF (com.BF app, three motors)** or **Cherish
  (com.okin.ore.cherish app)** in manual setup.
- Select the Bluetooth address used by that app.
- Neither app provides an advertisement signature that can safely select its
  profile. Shared FFE9/FFE4 characteristics do not identify either product.
- Existing beds using other profiles are unchanged.

## Commands

All frames below are exact `control_frame()` output from
[`beds/bf_cherish.py`](../../custom_components/adjustable_bed/beds/bf_cherish.py).

### Motor Control

| Command | Key | Frame | Profile |
| --- | --- | --- | --- |
| Back up | `0x00000001` | `E5FE160000000105` | BF, Cherish |
| Back down | `0x00000002` | `E5FE160000000204` | BF, Cherish |
| Legs up | `0x00000004` | `E5FE160000000402` | BF, Cherish |
| Legs down | `0x00000008` | `E5FE1600000008FE` | BF, Cherish |
| Head up | `0x00000010` | `E5FE1600000010F6` | BF only |
| Head down | `0x00000020` | `E5FE1600000020E6` | BF only |
| Back and legs up | `0x00000005` | `E5FE160000000501` | Cherish only |
| Back and legs down | `0x0000000A` | `E5FE160000000AFC` | Cherish only |
| Movement release | `0x00000000` | `E5FE160000000006` | BF, Cherish |

### Presets

| Command | BF key / frame | Cherish key / frame |
| --- | --- | --- |
| Zero Gravity | `0x01000001` / `E5FE160100000104` | `0x21000001` / `E5FE1621000001E4` |
| Flat | `0x01000002` / `E5FE160100000203` | `0x21000002` / `E5FE1621000002E3` |
| Quiet Sleep (anti-snore) | `0x01000004` / `E5FE160100000401` | `0x21000003` / `E5FE1621000003E2` |
| Preset STOP | `0x01000000` / `E5FE160100000005` | `0x21000000` / `E5FE1621000000E5` |

### Memory

| Command | BF key / frame | Cherish key / frame |
| --- | --- | --- |
| Recall A (memory 1) | `0x01000008` / `E5FE1601000008FD` | `0x21000004` / `E5FE1621000004E1` |
| Recall B (memory 2) | `0x01000009` / `E5FE1601000009FC` | `0x21000006` / `E5FE1621000006DF` |
| Program A (memory 1) | `0x20000008` / `E5FE1620000008DE` | `0x21000014` / `E5FE1621000014D1` |
| Program B (memory 2) | `0x20000009` / `E5FE1620000009DD` | `0x21000016` / `E5FE1621000016CF` |

### Lights (Cherish)

| Command | Key | Frame |
| --- | --- | --- |
| Light on | `0x31000001` | `E5FE1631000001D4` |
| Light off | `0x31000000` | `E5FE1631000000D5` |

BF has no light entity: both of its app light branches send the Zero Gravity
command.

### Massage (Cherish)

| Command | Key | Frame |
| --- | --- | --- |
| Timer 10 / 20 / 30 min | `0x10000030` / `0x10000031` / `0x10000032` | `E5FE1610000030C6` / `E5FE1610000031C5` / `E5FE1610000032C4` |
| Wave 1 / 2 / 3 | `0x10000021` / `0x10000022` / `0x10000023` | `E5FE1610000021D5` / `E5FE1610000022D4` / `E5FE1610000023D3` |
| Wave 0 (off) | `0x10000020` | `E5FE1610000020D6` |
| Intensity 1 / 2 / 3 | `0x10000011` / `0x10000012` / `0x10000013` | `E5FE1610000011E5` / `E5FE1610000012E4` / `E5FE1610000013E3` |
| Intensity 0 (off) | `0x10000010` | `E5FE1610000010E6` |

### Preset and Memory Selection State

- A second press of the same preset sends that profile's preset STOP.
- Preset and memory taps share the app's selection state.
- Programming a memory preserves the shared count: programming as the first
  action suppresses a subsequent tap of that same memory until another preset
  or movement changes the selection.
- Programming after a running preset makes the next same-memory tap send STOP.
- This state survives reconnects but is not a hardware acknowledgement.

### Massage Sequences (Cherish)

- Start: timer, wave after 100 ms, then intensity after another 200 ms.
- Off: intensity 0, then wave 0 after 100 ms, keeping the selected levels and
  timer.
- At the bounds, +/- does not write.
- Selecting a timer sends only its timer command and disables level changes
  until massage is started again; it does not prove that the receiver stopped
  massage.
- There is no massage feedback.
- HA serializes these sequences and finishes cancellation cleanup, so an
  Android delayed callback cannot restart massage after Off.

## Alarm action

```yaml
action: adjustable_bed.bf_cherish_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "08:30:00"
  memory: memory_1
```

- `memory` is `none`, `memory_1` (A), or `memory_2` (B), never a bed side.
- Use `enabled: false` to disable; the previous selected schedule remains in
  local intent.
- Enabling always supplies a complete, valid time and explicit memory.
- The clock comes from Home Assistant's configured local timezone.

### Alarm Frames

| Field | BF (EB) | Cherish (EA) |
| --- | --- | --- |
| Selector: none / A / B | `255` / `248` / `249` | `255` / `4` / `6` |
| Schedule | Sunday-zero weekday and a day mask for the next occurrence; an equal hour/minute remains today | Three FF fields unchanged |
| Disable | EB then EA | EA twice |

- These bytes do not prove any further recurrence semantics.
- The two disable packets sample the current clock independently.
- Disabled fields (alarm minute/hour, day mask and selector; BF's two zero
  bytes) are sent as `FF`.
- There is no application alarm ACK.

Example frames from `alarm_frame()` with an HA clock of Tuesday 07:15:30:

| Request | Frame |
| --- | --- |
| BF, enable 08:30, `memory_1` | `EBFE161E0F071E0802040000F8A8` |
| BF, disable (first frame) | `EBFE161E0F07FFFF02FFFFFFFFD0` |
| Cherish, enable 08:30, `memory_1` | `EAFE161E0F071E08FFFFFF04A6` |
| Cherish (and BF second frame), disable | `EAFE161E0F07FFFFFFFFFFFFD3` |
| BF clock query | `E2FE161E0F0702D3` |

### Alarm State

- The **Bed alarm** sensor exposes the last command or BF report, with time,
  memory, raw BF selector and source attributes.
- Cherish intent persists across HA restarts; expiry clears its local enabled
  indication. It does not restore phone alarms or infer receiver state.
- BF's **Query bed alarm** button sends the live E2 clock query.
- Cherish has no reachable query or alarm notification consumer, so neither is
  synthesized for it.

### Deliberate App Differences

- HA requires explicit valid alarm fields instead of reproducing the apps'
  unset FF time fields, BF's untouched 88 selector, delayed wheel races, or
  Cherish's A-while-B branch that displays A while sending B.
- Selection and persisted intent use the actual memory requested by the HA
  caller.
- No extra bed command is invented to correct these phone defects.

## Notifications / State

BF alarm report on FFE4:

| Field | Value |
| --- | --- |
| Prefix | E2FE16 |
| Minute / hour / selector | Unsigned offsets 3/4/9 |
| Disabled | minute > 59 **and** hour > 24 (the app's condition, preserved exactly) |
| Selector | `248` A, `249` B, `255` none; unknown selectors preserve the prior memory |

- HA safely ignores short packets rather than reproducing the app's
  substring/index exceptions.
- Reports may contain invalid times; they are diagnostic values, never
  automatically programmed.
- Cherish registers the notification but has no consuming alarm parser.

## Command Timing

- Movement refreshes use the app's 200 ms interval with a bounded HA pulse
  count.
- Movement release uses `E5FE160000000006`; preset STOP is profile-specific.
- HA attempts release on cancellation and errors, and explicit STOP attempts
  both families. It cannot guarantee delivery on a failed Bluetooth link.
- Presets and saves are single writes, without an automatic touch-release STOP.

## Notes

### BLE Transport and Failures

- Cancelled operations can perform no write; write errors propagate and do not
  advance local preset state.
- Transport submission, GATT completion and reported bed state are distinct.
- HA's coordinator owns adapter/proxy selection, connection recovery, bounded
  retry, command serialization and STOP preemption.
- It does not recreate Android's 100-pending FIFO, 10/100 ms queue scheduling,
  numeric errors or reflection-based cache refresh.
- The apps themselves can reject an incoming STOP at queue capacity; that
  defect is not copied into HA.
- No failure, disconnect or timeout alone establishes physical stopping.

### Scope

Wi-Fi provisioning, SSID/passwords, bed network administration, cloud/account
services and unrelated phone infrastructure are outside this BLE integration.

### Hardware Status

**Hardware status: UNVERIFIED.**

- Real-user captures after beta/release are deferred external validation, not
  a prerequisite for implementing the proven app behavior.
- Physical posture, stopping distance, alarm recurrence and successful on-air
  delivery have not been established.

### Analysis provenance

| Package | Version | Artifact SHA-256 |
| --- | --- | --- |
| `com.BF` | 1.2.3 (11) | `64982c7a35fed0c902061b7b0f732b15798a38688119c1d92d343052781a83d1` |
| `com.okin.ore.cherish` | 1.0.4 (5) | `2f32624027a0f3a950f796f87c18feda2eafad1fa253927751a02426824b8520` |

The exhaustive [disposition ledger](../apk-analysis/dispositions/row063-cluster001.md)
records the evidence and implementation treatment, including report, audit and
reconciliation seals.
