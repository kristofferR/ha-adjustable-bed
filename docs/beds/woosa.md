# Woosa Sleep app profile

**Static evidence:** Accepted APK Protocol Audit of `com.sn.woosa` 1.1.9 (version code 13).
**Hardware validation:** Unverified. The Android artifact proves the app's BLE behavior; it does not establish behavior on every physical bed or the iOS app.

## Selecting the profile

Use bed type **Solace** and explicitly select protocol variant **`woosa`** (Woosa Sleep) when your bed uses the Woosa Sleep app. For an existing entry, update the integration, restart Home Assistant, then open **Settings → Devices & Services → Adjustable Bed → Configure → Change settings** and change the protocol variant to **`woosa`**. Submit the change so the integration reloads its entities. For a separate-address pair, unpair and configure each side before changing this profile. Woosa massage controls are enabled automatically by this profile.

Automatic `QMS-MQ` and `QMS2` discovery retains the conservative common Solace profile. Those names are shared across apps and do not identify a Woosa product. An nRF Connect scan proves an advertised name, address and GATT structure, not which app's commands or physical layout a bed implements. Select this profile from the app/product you use, not merely from its BLE name.

The profile supplies back and leg controls, Flat, Favourite (Memory 1), Love, TV and Zero-G presets, save actions for all four stored presets, dimmable lighting, timed lighting, massage levels/modes/timers, and a controller alarm. It has no measured position feedback, second numbered memory slot, audio player, or wire-level side selector.

The [remote illustration supplied with issue #606](https://github.com/user-attachments/assets/b3752885-7151-4b51-9649-eb0ec4b3ad62) shows back/leg adjustment, one memory button, Flat, TV, Zero Gravity, massage and an LED night light. Its remaining preset is labeled **Anti-Snore**, while the audited Android app labels its corresponding preset category **Love**. The illustration supplies no BLE bytes, so it does not establish that those differently named actions are equivalent. This explicit app profile retains the audited app label; the remote/iOS mapping remains a deferred hardware check.

## Movement and presets

The app sends one movement-start frame on touch down and a global STOP on release, without held-command repetition. HA movement uses the integration's bounded movement lifecycle and always sends STOP during cleanup. This cap is an integration safety limit, not a claimed firmware timeout.

The app sends the **same frame for leg down and Flat** (`FF FF FF FF 05 00 00 00 08 D6 C6`). The profile preserves this evidence instead of substituting another app's leg-down command. Whether it lowers only the legs or flattens multiple sections requires a real user's capture after release.

| HA action | Woosa app meaning |
|---|---|
| Memory 1 recall/save | CUSTOM / Favourite |
| Love recall/save | Preset 1 / Love |
| TV recall/save | Preset 2 / TV |
| Zero-G recall/save | Preset 3 / Zero gravity |

Favourite and named preset activation sends STOP, waits 200 ms, then sends the selected frame. The direct Flat button sends its frame once without that preamble. Stored-preset replies report that a saved position exists; they do not report a measured angle or a currently selected position. Named presets can choose a stored position when its presence is known. The app's Dashboard and preset editor disagree about several stored-preset branches. The integration uses explicit HA actions and records this discrepancy in the [discovery ledger](woosa-disposition.md); it does not present the inconsistent Android switch state as hardware truth. Love is not labeled anti-snore.

## Lighting and massage

Lighting has levels 0–10 and on durations of 10 minutes, 8 hours or 10 hours. The dedicated Off action uses the app's separate light-off frame; brightness level 0 also remains available. Light state is optimistic after HA writes. The app's loose brightness reply pattern overlaps massage packets, so received brightness candidates remain diagnostic data rather than confirmed light state. Explicit light timer and Off actions also synchronize the optimistic light switch state. Timers program the controller, not an HA delay.

Massage has back and leg levels 0–3, four alternating modes, 10/20/30-minute timers, step controls and Off. The app's full massage-start sequence uses 400 ms between writes. Requested massage start levels are retained separately from reported activity, so Off and zero-level notifications do not erase the settings used on the next start. The Android Dashboard mistakenly chooses the back setting from the leg preference; HA's separately labeled back and leg controls use the corresponding settings. Independent level, mode, timer, step and Off controls can compose the app's alternative screen sequences with their proven 400 ms spacing. The profile does not expose HomeKobo's additional hip/lumbar or circulation controls.

## Controller alarm

`adjustable_bed.solace_set_alarm` programs the Woosa controller alarm. Supply a time, optional weekdays, `zero_g`, `memory_1` (Favourite) or `no_action`, a massage flag, and sound `none` or `alarm`. Music tracks belong to the MotionFlex profile and are rejected for Woosa.

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

The controller clock is synchronized to HA local time during notification startup. Alarm replies expose the controller's returned settings. Saving an alarm is not an acknowledgement that hardware executed it.

## Transport and protocol evidence

The artifact searches local names for case-sensitive `QMS-MQ` or `QMS2` substrings, with no advertised service or manufacturer filter. It enumerates services and selects characteristic `0000ffe1-0000-1000-8000-00805f9b34fb` for writes and notifications. No fixed service UUID, explicit numeric write type, PIN exchange, pairing request, MTU negotiation, or device capability query is established. HA owns connection selection, notification subscription and command serialization.

There are 59 distinct fixed 11-byte frames and two dynamic builders. Fixed-frame trailers are copied from the accepted artifact; no inferred general checksum algorithm is needed. Clock and alarm builders append a little-endian additive checksum. The clock contains BCD hour, minute, second, weekday, year, month and day. Alarm fields include enabled state, BCD time, weekdays, repeat flag, action, massage and sound.

Startup includes the app's initialization write, clock write, alarm query, four stored-preset queries and light-state query. There is no position query. Notification handling covers saved-preset presence, massage levels/mode, brightness and alarm state; malformed replies are not allowed to crash entity updates.

## Evidence identity and validation

The frozen acquisition corpus contains version 1.1.9, not a claim about the current store release. Artifact-set SHA-256:

```text
21778ac636d9fed83d7809d0dd47521deb2b2e25d24867bf3e2458740c47b217
```

Accepted `REPORT.SHA256` file digest:

```text
995677ce2204b2f8255b5a47f9b7c597928255d636e2f50ba1aff3cdfcf70851
```

The independent review passed all 17 completion gates. The report covers 61 command rows, 92 reproducible vectors, 51 selector entries and 30 candidate paths. Raw APKs, decompilation and audit reports remain machine-local. The [implementation ledger](woosa-disposition.md) maps this evidence to durable code and tests. See [issue #606](https://github.com/kristofferR/ha-adjustable-bed/issues/606).

After beta or release, useful real-user captures include leg-down versus Flat, the four preset save/recall paths, brightness, clock/alarm behavior and runtime GATT properties. These are deferred physical checks, not missing static implementation evidence. No maintainer hardware is assumed.
