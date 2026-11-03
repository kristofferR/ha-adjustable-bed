# Woosa Sleep app profile

**Status:** ⚠️ Partially tested ([the reporter confirmed working controls](https://github.com/kristofferR/ha-adjustable-bed/issues/606#issuecomment-5982450770) with v4.0.1 after explicitly selecting Woosa)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

Woosa is an explicit protocol variant of the [Solace](solace.md) 11-byte FFE1
controller. Exhaustive hardware behavior and the iOS app's BLE equivalence
remain unverified. See [issue #606](https://github.com/kristofferR/ha-adjustable-bed/issues/606).

## Known Models

- Woosa Sleep adjustable bases controlled by the Woosa Sleep app (Android and iOS)
- Bluetooth names containing `QMS-MQ` or `QMS2`. These are shared across apps
  and do not identify a Woosa product.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Woosa Sleep](https://play.google.com/store/apps/details?id=com.sn.woosa) 1.1.9 (version code 13) | `com.sn.woosa` |

**Static evidence:** Accepted APK Protocol Audit of `com.sn.woosa` 1.1.9 (version code 13).
**Hardware validation:** the reporter confirmed working controls; exhaustive
hardware behavior and the iOS app's BLE equivalence remain unverified. See
[Analysis provenance](#analysis-provenance).

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Back and legs |
| Position Feedback | ❌ (no measured position feedback) |
| Presets | ✅ Flat, Favourite (Memory 1), Anti-Snore, TV, Zero-G |
| Memory Presets | ✅ (1 Favourite slot; save actions for all four stored presets; no second numbered memory slot) |
| Lights | ✅ (dimmable levels 0–10, timed lighting, dedicated Off) |
| Massage | ✅ (back and leg levels 0–3, four alternating modes, timers, steps, Off) |
| Controller alarm | ✅ (Favourite, Zero gravity or no action) |
| Audio player | ❌ |
| Wire-level side selector | ❌ |

## Protocol Details

**Service UUID:** none required (the app enumerates services)
**Write/Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** fixed 11-byte frames copied from the artifact, plus two dynamic builders

- The artifact searches local names for case-sensitive `QMS-MQ` or `QMS2`
  substrings, with no advertised service or manufacturer filter.
- It enumerates services and selects FFE1 for writes and notifications.
- No fixed service UUID, explicit numeric write type, PIN exchange, pairing
  request, MTU negotiation, or device capability query is established.
- HA owns connection selection, notification subscription and command
  serialization.

### Packet Format

- There are 59 distinct fixed 11-byte frames and two dynamic builders.
- Fixed-frame trailers are copied from the accepted artifact; no inferred
  general checksum algorithm is needed.
- Clock and alarm builders append a little-endian additive checksum. The clock
  contains BCD hour, minute, second, weekday, year, month and day. Alarm fields
  include enabled state, BCD time, weekdays, repeat flag, action, massage and
  sound. Both builders are shared with [Solace MotionFlex](solace.md#motionflex-audio-clock-and-alarm).

## Detection / Setup

Use bed type **Solace** and explicitly select protocol variant **`woosa`**
(Woosa Sleep) when your bed uses the Woosa Sleep app.

1. For an existing entry, update the integration and restart Home Assistant.
2. Open **Settings → Devices & Services → Adjustable Bed → Configure → Change settings**
   and change the protocol variant to **`woosa`**.
3. Submit the change so the integration reloads its entities.

- For a separate-address pair, unpair and configure each side before changing
  this profile.
- Woosa massage controls are enabled automatically by this profile.
- Automatic `QMS-MQ` and `QMS2` discovery retains the conservative common
  Solace profile. Those names are shared across apps and do not identify a
  Woosa product.
- An nRF Connect scan proves an advertised name, address and GATT structure,
  not which app's commands or physical layout a bed implements. Select this
  profile from the app/product you use, not merely from its BLE name.

## Commands

### Motor Control

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Back Up | `FF FF FF FF 05 00 00 00 03 97 01` | Start |
| Back Down | `FF FF FF FF 05 00 00 00 04 D6 C3` | Start |
| Legs Up | `FF FF FF FF 05 00 00 00 06 57 02` | Start |
| Legs Down | `FF FF FF FF 05 00 00 00 08 D6 C6` | Same frame as Flat |
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` | Global STOP on release |

The app sends the **same frame for leg down and Flat**
(`FF FF FF FF 05 00 00 00 08 D6 C6`). The profile preserves this evidence
instead of substituting another app's leg-down command. Whether it lowers only
the legs or flattens multiple sections requires a real user's capture after
release.

### Presets

| HA action | Woosa app label | Recall | Recall (saved position reported) | Save |
|---|---|---|---|---|
| Flat | Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` | | |
| Memory 1 recall/save | CUSTOM / Favourite | | `FF FF FF FF 05 00 00 A1 0A 2E 97` | `FF FF FF FF 05 00 00 A0 0A 2F 07` |
| Anti-Snore recall/save | Preset 1 / Anti-Snore (reporter's iOS app), Love (audited Android app) | `FF FF FF FF 05 00 00 00 0F 97 04` | `FF FF FF FF 05 00 00 F1 0F D2 94` | `FF FF FF FF 05 00 00 F0 0F D3 04` |
| TV recall/save | Preset 2 / TV | `FF FF FF FF 05 00 00 00 05 17 03` | `FF FF FF FF 05 00 00 51 05 2A 93` | `FF FF FF FF 05 00 00 50 05 2B 03` |
| Zero-G recall/save | Preset 3 / Zero gravity | `FF FF FF FF 05 00 00 00 09 17 06` | `FF FF FF FF 05 00 00 91 09 7A 96` | `FF FF FF FF 05 00 00 90 09 7B 06` |

- Favourite and named preset activation sends STOP, waits 200 ms, then sends
  the selected frame. The direct Flat button sends its frame once without that
  preamble.
- Favourite recall is refused until the bed reports a saved Favourite position.
- After a save, HA repeats the four stored-preset queries 300 ms apart, as the
  app does; only replies establish saved state.
- Stored-preset replies report that a saved position exists; they do not
  report a measured angle or a currently selected position. Named presets can
  choose a stored position when its presence is known.
- The app's Dashboard and preset editor disagree about several stored-preset
  branches. The integration uses explicit HA actions and records this
  discrepancy in the [discovery ledger](woosa-disposition.md); it does not
  present the inconsistent Android switch state as hardware truth.

### Lights

| Command | Bytes (hex) |
|---------|-------------|
| Level 0 | `FF FF FF FF 05 00 00 00 23 96 D9` |
| Level 1–10 | `FF FF FF FF 05 00 00 <level> 23 …`, the same frames as [Solace](solace.md#lights) |
| Off | `FF FF FF FF 05 00 00 00 4B 97 37` |
| On for 10 min | `FF FF FF FF 05 00 00 00 19 16 CA` |
| On for 8 hours | `FF FF FF FF 05 00 00 00 1A 56 CB` |
| On for 10 hours | `FF FF FF FF 05 00 00 00 1B 97 0B` |
| Light-state query | `FF FF FF FF 05 00 05 FF 23 C7 28` |

- Lighting has levels 0–10 and on durations of 10 minutes, 8 hours or 10 hours.
  Turning the light on uses the last selected duration (10 minutes by default).
- The dedicated Off action uses the app's separate light-off frame; brightness
  level 0 also remains available.
- Light state is optimistic after HA writes. Brightness, light timer and Off
  actions synchronize the optimistic light switch state.
- Timers program the controller, not an HA delay. HA's optimistic state turns
  off when the selected duration elapses.
- The app's loose brightness reply pattern overlaps massage packets, so
  received brightness candidates remain diagnostic data rather than confirmed
  light state.

### Massage

| Command | Bytes (hex) |
|---------|-------------|
| Back (head zone) level 0 | `FF FF FF FF 05 00 00 00 4F 96 F4` |
| Back (head zone) level 1 | `FF FF FF FF 05 00 00 00 50 D7 3C` |
| Back (head zone) level 2 | `FF FF FF FF 05 00 00 00 51 16 FC` |
| Back (head zone) level 3 | `FF FF FF FF 05 00 00 00 52 56 FD` |
| Leg (foot zone) level 0 | `FF FF FF FF 05 00 00 00 53 97 3D` |
| Leg (foot zone) level 1 | `FF FF FF FF 05 00 00 00 54 D6 FF` |
| Leg (foot zone) level 2 | `FF FF FF FF 05 00 00 00 55 17 3F` |
| Leg (foot zone) level 3 | `FF FF FF FF 05 00 00 00 56 57 3E` |
| Mode 1 | `FF FF FF FF 05 00 00 00 57 96 FE` |
| Mode 2 | `FF FF FF FF 05 00 00 00 58 D6 FA` |
| Mode 3 | `FF FF FF FF 05 00 00 00 59 17 3A` |
| Mode 4 | `FF FF FF FF 05 00 00 00 5A 57 3B` |
| Mode step | `FF FF FF FF 05 00 05 00 14 C7 0E` |
| Back step up | `FF FF FF FF 05 00 00 00 10 D6 CC` |
| Back step down | `FF FF FF FF 05 00 00 00 11 17 0C` |
| Leg step up | `FF FF FF FF 05 00 00 00 12 57 0D` |
| Leg step down | `FF FF FF FF 05 00 00 00 13 96 CD` |
| Timer 10 min | `FF FF FF FF 05 00 00 00 16 56 CE` |
| Timer 20 min | `FF FF FF FF 05 00 00 00 17 97 0E` |
| Timer 30 min | `FF FF FF FF 05 00 00 00 18 D7 0A` |
| Off | `FF FF FF FF 05 00 00 00 1C D6 C9` |

- Massage has back and leg levels 0–3, four alternating modes, 10/20/30-minute
  timers, step controls and Off. Steps stay within 0–3.
- The app's full massage-start sequence is Off, timer, back level, leg level,
  mode, with 400 ms between writes. HA starts from the stored preferences
  (back 2, leg 2, mode 2, 10 minutes until set) and sends Off if the sequence
  is interrupted.
- Requested massage start levels are retained separately from reported
  activity, so Off and zero-level notifications do not erase the settings used
  on the next start.
- HA retains displayed levels and timer across its normal Bluetooth
  disconnect, then clears activity when the selected timer expires.
- The Android Dashboard mistakenly chooses the back setting from the leg
  preference; HA's separately labeled back and leg controls use the
  corresponding settings.
- Independent level, mode, timer, step and Off controls can compose the app's
  alternative screen sequences with their proven 400 ms spacing.
- The profile does not expose HomeKobo's additional hip/lumbar or circulation
  controls, or the Solace wave controls.

### Startup and status queries

| Command | Bytes (hex) |
|---------|-------------|
| Initialization | `FF FF FF FF 02 00 0E 0B 00 17 04` |
| Alarm query | `FF FF FF FF 01 00 0A 0B 0F 21 04` |
| Stored-preset queries | `FF FF FF FF 03 00 28 00 03 9F 09`, `FF FF FF FF 03 00 18 00 03 9F 06`, `FF FF FF FF 03 00 20 00 03 1E CB`, `FF FF FF FF 03 00 38 00 03 9E CC` |
| Light-state query | `FF FF FF FF 05 00 05 FF 23 C7 28` |

Startup includes the app's initialization write, clock write, alarm query, four
stored-preset queries and light-state query. There is no position query. HA
keeps each app worker's offsets and serializes coincident writes:
initialization at 500 ms, preset queries at 600 ms and 900 ms, clock at 1.0 s,
preset query at 1.2 s, then alarm query, last preset query and light-state
query at 1.5 s.

## Notifications

- Notification handling covers saved-preset presence, massage levels/mode,
  brightness and alarm state; malformed replies are not allowed to crash entity
  updates.
- Saved-preset replies start `FF FF FF FF 03 06 00` followed by selector `0A`
  (Favourite), `0F` (Anti-Snore/Love), `05` (TV) or `09` (Zero-G).
- Massage replies are matched against these frames:

  | Reply | Frames for level/mode 0–3 (back, leg) or 1–4 (mode) |
  |---|---|
  | Back level | `FF FF FF FF 05 00 00 01 00 D6 90`, `FF FF FF FF 05 00 00 01 1E 56 98`, `FF FF FF FF 05 00 00 01 1F 97 58`, `FF FF FF FF 05 00 00 01 20 D7 48` |
  | Leg level | `FF FF FF FF 05 00 00 02 00 D6 60`, `FF FF FF FF 05 00 00 02 21 16 78`, `FF FF FF FF 05 00 00 02 22 56 79`, `FF FF FF FF 05 00 00 02 23 97 B9` |
  | Mode | `FF FF FF FF 05 00 00 03 24 D7 EB`, `FF FF FF FF 05 00 00 03 25 16 2B`, `FF FF FF FF 05 00 00 03 26 56 2A`, `FF FF FF FF 05 00 00 03 27 97 EA` |

- Byte 7 of any `FF FF FF FF 05 00` reply is kept as the diagnostic light
  candidate.
- Alarm replies starting `FF FF FF FF 01 00 03 0B 00` report no alarm; replies
  starting `FF FF FF FF 01 00 04 13` carry enabled state, time, weekdays,
  action, massage and sound.

## Controller alarm

The existing **Adjustable Bed: Set Solace alarm** action
(`adjustable_bed.solace_set_alarm`) also programs the Woosa controller alarm. To
set it up in Home Assistant:

1. Open **Developer Tools → Actions** and select **Adjustable Bed: Set Solace alarm**.
2. Select your Woosa bed under **Device** and turn **Enabled** on.
3. Set the time and any repeating weekdays, then choose the **Bed action** from the table below.
4. Choose whether to enable massage and set **Sound** to `none` or `alarm`, then run the action.

| Bed action value | Alarm behavior |
|---|---|
| `memory_1` | Recall Favourite, the saved Memory 1 position |
| `zero_g` | Recall Zero gravity |
| `no_action` | No preset movement; massage and sound can still be selected |

- Favourite and Zero gravity are also the preset choices in
  [the reporter's iOS alarm screenshot](https://github.com/user-attachments/assets/25224a7f-13cb-4b6e-9e2b-fce0a6dc3939).
- For Favourite, save the desired position using **Save to Memory 1** before
  setting the alarm.
- The controller alarm does not offer TV or Anti-Snore. Music tracks belong to
  the MotionFlex profile and are rejected for Woosa.
- HA sends the alarm query after each alarm write.

The same action can be used in a script or automation. This example sets a
weekday alarm for Zero gravity at 07:30:

```yaml
action: adjustable_bed.solace_set_alarm
data:
  device_id: YOUR_BED_DEVICE_ID
  enabled: true
  time: "07:30:00"
  weekdays: [monday, tuesday, wednesday, thursday, friday]
  mode: zero_g
  massage: false
  sound: alarm
```

Change `mode` to `memory_1` for Favourite. To disable the controller alarm, run
the action with **Enabled** off, or use:

```yaml
action: adjustable_bed.solace_set_alarm
data:
  device_id: YOUR_BED_DEVICE_ID
  enabled: false
```

- Select the bed in the action's device picker to fill in its `device_id`; it
  is Home Assistant's device ID, not the Bluetooth address.
- The **Alarm Enabled** binary sensor shows the controller's reported enabled
  state, with time, weekdays, action, massage and sound in its attributes.
- The controller clock is synchronized to HA local time during notification
  startup. Alarm replies expose the controller's returned settings. Saving an
  alarm is not an acknowledgement that hardware executed it.

## Command Timing

- The app sends one movement-start frame on touch down and a global STOP on
  release, without held-command repetition.
- HA movement uses the integration's bounded movement lifecycle and always
  sends STOP during cleanup. This cap is an integration safety limit, not a
  claimed firmware timeout.
- Preset activation: STOP, 200 ms, preset frame. Massage start: 400 ms between
  writes. Preset save: four re-queries 300 ms apart.

## Notes

### Anti-Snore versus Love

- The [remote illustration supplied with issue #606](https://github.com/user-attachments/assets/b3752885-7151-4b51-9649-eb0ec4b3ad62)
  labels the remaining preset **Anti-Snore**.
- The [reporter's iOS Dashboard screenshot](https://github.com/user-attachments/assets/f81a2d68-083a-477f-9dd5-f6a74cbfd99d)
  likewise shows **Preset 1 / ANTI SNORE**, alongside Favourite, TV and Zero
  Gravity.
- HA displays **Anti-Snore** and **Save Anti-Snore position** to match the
  reporter's iOS app and remote.
- The audited Android app calls the same preset category **Love**; that name is
  retained in this documentation only.
- This is a presentation correction based on those labels, not proof of
  equivalent iOS BLE commands or physical preset angles. Existing entity IDs
  and command behavior are preserved.

### Analysis provenance

- The frozen acquisition corpus contains version 1.1.9, not a claim about the
  current store release.
- Artifact-set SHA-256: `21778ac636d9fed83d7809d0dd47521deb2b2e25d24867bf3e2458740c47b217`
- Accepted `REPORT.SHA256` file digest: `995677ce2204b2f8255b5a47f9b7c597928255d636e2f50ba1aff3cdfcf70851`
- The independent review passed all 17 completion gates. The report covers 61
  command rows, 92 reproducible vectors, 51 selector entries and 30 candidate
  paths.
- Raw APKs, decompilation and audit reports remain machine-local. The
  [implementation ledger](woosa-disposition.md) maps this evidence to durable
  code and tests. See [issue #606](https://github.com/kristofferR/ha-adjustable-bed/issues/606).

### Validation requests

After beta or release, useful real-user captures include leg-down versus Flat,
the four preset save/recall paths, brightness, clock/alarm behavior and runtime
GATT properties. These are deferred physical checks, not missing static
implementation evidence. No maintainer hardware is assumed.
