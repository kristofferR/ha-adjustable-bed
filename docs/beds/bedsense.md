# BedSense app

**Status:** ❓ Needs testing (artifact-proven, physical hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

Select **BedSense app (com.fenmenbielei.bedsense)** during manual setup for
beds controlled by Android BedSense 1.8 (18). This is separate from
**Bedsense Bases** (`com.ore.bedsense`), which has its own
[profile](ore-comfort-bed.md). The implementation is artifact-proven; physical
hardware is unverified.

## Known Models

App layouts (see [Detection / Setup](#detection--setup)): BEDSENSE-850,
BEDSENSE-890, BEDSENSE-1150, BEDSENSE-1050, BEDSENSE-250, BEDSENSE-150,
BEDSENSE-350, Resten Hi-Low and the app's Default layout.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BedSense](https://play.google.com/store/apps/details?id=com.fenmenbielei.bedsense) 1.8 (18) | `com.fenmenbielei.bedsense` |

Bedsense Bases (`com.ore.bedsense`) is a different app; see its
[profile](ore-comfort-bed.md).

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (per layout: back, waist/hip, head, legs, back and leg, lift, rise and fall) |
| Position Feedback | ❌ (no angles, battery, model or physical position feedback is claimed) |
| Presets | ✅ Flat, TV, Zero Gravity, Anti Snore where the app exposes them |
| Memory Presets | ✅ (five recalls and saves, explicit clear buttons) |
| Circulation massage | ✅ Types 1–5 |
| Massage | ✅ head/foot increase/decrease, wave frequency, 10/20/30-minute timers |
| Lights | ⚠️ Light-duration buttons only (no proven off, brightness, RGB, or channel command) |
| Shortcuts | ✅ Music, Leg Relax (types 4/5); Lumbar (types 6/8); RISE/DECLINE (type 9) |

## Protocol Details

**Service UUID:** none inferred (the app iterates all services)
**Write/Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** fixed 11-byte literals

- All fixed packets are 11-byte literals. Their trailers, including anomalies,
  are preserved without inventing a checksum.
- Every matching FFE1 characteristic is subscribed and read after 200 ms; the
  last is the write target.
- The discovered write-without-response property selects that write mode,
  otherwise writes use a response. Bleak owns CCCD setup.
- No PIN, bonding handshake, side selection, authentication, or capability
  query is defined by the app.

## Detection / Setup

Choose a layout explicitly, or use **BedSense layout from the Bluetooth name**.
Auto uses the original, case-sensitive Bluetooth name with the following
ordered rules. A custom HA display name does not select the layout.

| Type | Name rule, first match wins | App layout | Movement controls |
| --- | --- | --- | --- |
| 1 | `JQ` or `NQ`, after type 2 | BEDSENSE-850 | Back, waist, back and leg, legs |
| 2 | `JQ-D`, checked first | BEDSENSE-890 | Back, waist, head, legs |
| 3 | Unmatched or absent name | Default | Back, waist, head, legs |
| 4 | `IQ` | BEDSENSE-1150 | Back, hip, head, legs |
| 5 | `LQ` | BEDSENSE-1050 | Back, hip, head, legs |
| 6 | `KQ` without `H` | BEDSENSE-250 | Back |
| 7 | `MQ` or `UPS` | BEDSENSE-150 | Back, legs |
| 8 | `H` without `S4`, after type 9 | BEDSENSE-350 | Back, rise and fall |
| 9 | `S4-2`, after type 7 | Resten Hi-Low | Back, hip, lift, legs |

- The app's type 3 idle WAIST label changes to HIP while pressed. HA keeps the
  idle waist label; physical actuator identity is unverified.
- Type 9 has separate HIP and LIFT controls. Visible axes do not establish a
  physical motor count.
- There is no automatic discovery signature: the app accepts any named device
  and iterates all services for characteristic
  `0000ffe1-0000-1000-8000-00805f9b34fb`. These short name substrings and this
  shared characteristic cannot safely identify a BedSense bed. No service UUID
  is inferred.

## Commands

The **Row** column is the accepted report's command ID (C001–C079). **Types**
lists the layouts that expose the control.

### Motor Control

| Row | Command | Bytes (hex) | Types |
|-----|---------|-------------|-------|
| C001 | Back up | `FF FF FF FF 05 00 00 00 03 97 01` | All |
| C002 | Back down | `FF FF FF FF 05 00 00 00 04 D6 C3` | All |
| C003 | Head up | `FF FF FF FF 05 00 00 00 01 16 C0` | 2, 3, 4, 5 |
| C004 | Head down | `FF FF FF FF 05 00 00 00 02 56 C1` | 2, 3, 4, 5 |
| C005 | Lift up | `FF FF FF FF 05 00 00 00 01 16 C0` | 9 |
| C006 | Lift down | `FF FF FF FF 05 00 00 00 02 56 C1` | 9 |
| C007 | Waist up (type 3 pressed label HIP) | `FF FF FF FF 05 00 00 00 0D 16 C5` | 1, 2, 3 |
| C008 | Waist down (type 3 pressed label HIP) | `FF FF FF FF 05 00 00 00 0E 56 C4` | 1, 2, 3 |
| C009 | Hip up | `FF FF FF FF 05 00 00 00 0D 16 C5` | 4, 5, 9 |
| C010 | Hip down | `FF FF FF FF 05 00 00 00 0E 56 C4` | 4, 5, 9 |
| C011 | Leg up | `FF FF FF FF 05 00 00 00 06 57 02` | 1, 2, 3, 4, 5, 7, 9 |
| C012 | Leg down | `FF FF FF FF 05 00 00 00 07 96 C2` | 1, 2, 3, 4, 5, 7, 9 |
| C013 | Rise and fall up | `FF FF FF FF 05 00 00 00 06 57 02` | 8 |
| C014 | Rise and fall down | `FF FF FF FF 05 00 00 00 07 96 C2` | 8 |
| C015 | Back and leg up | `FF FF FF FF 05 00 00 00 2B 97 1F` | 1 |
| C016 | Back and leg down | `FF FF FF FF 05 00 00 00 2C D6 DD` | 1 |
| C017 | Release / quick-background or light-background tap | `FF FF FF FF 05 00 00 00 00 D7 00` | All |
| C018 | Movement or massage background tap (physical meaning unverified) | `FF FF FF FF 05 00 00 00 00 D8 14` | All |

- Covers provide each layout's movement controls. One press sends one movement
  frame. HA holds for the configured finite movement window, then sends release
  `FF FF FF FF 05 00 00 00 00 D7 00`. STOP, cancellation and dashboard release
  also end movement. The app has no movement refresh cadence.
- A separate movement/massage **background tap** action preserves the app's
  distinct `D8 14` trailer. Its physical effect is unverified; it is not
  labelled as STOP or massage off. Quick/light background taps use the normal
  release.

### Shortcuts

| Row | Command | Bytes (hex) | Types |
|-----|---------|-------------|-------|
| C026 | Flat Bed / recovery | `FF FF FF FF 05 00 00 00 08 D6 C6` | 1, 2, 3, 4, 5, 7, 9 |
| C027 | Lumbar shortcut | `FF FF FF FF 05 00 00 00 2E 57 1C` | 6, 8 |
| C028 | Music shortcut | `FF FF FF FF 05 00 00 00 28 D7 1E` | 4, 5 |
| C029 | Leg Relax shortcut | `FF FF FF FF 05 00 00 00 29 16 DE` | 4, 5 |
| C030 | RISE click | `FF FF FF FF 05 00 00 00 01 16 C0` | 9 |
| C031 | DECLINE click | `FF FF FF FF 05 00 00 00 02 56 C1` | 9 |

Types 4/5 add Music and Leg Relax; types 6/8 add Lumbar. Type 9 also has
single-shot RISE/DECLINE buttons. These send the same literals as lift
up/down, but append no release, matching the app's distinct click behavior.

### Memory and presets

| Slot | Save | Clear | Recall | Built-in recall | Types |
|------|------|-------|--------|-----------------|-------|
| M1 (C032–C034) | `FF FF FF FF 05 00 00 A0 0A 2F 07` | `FF FF FF FF 05 00 00 AF 0A 2A F7` | `FF FF FF FF 05 00 00 A1 0A 2E 97` | | All |
| M2 (C035–C037) | `FF FF FF FF 05 00 00 B0 0B E3 07` | `FF FF FF FF 05 00 00 BF 0B E6 F7` | `FF FF FF FF 05 00 00 B1 0B E2 97` | | All |
| M3 TV (C038–C041) | `FF FF FF FF 05 00 00 50 05 2B 03` | `FF FF FF FF 05 00 00 5F 05 2E F3` | `FF FF FF FF 05 00 00 51 05 2A 93` | `FF FF FF FF 05 00 00 00 05 17 03` | All |
| M4 Zero Gravity (C042–C045) | `FF FF FF FF 05 00 00 90 09 7B 06` | `FF FF FF FF 05 00 00 9F 09 7E F6` | `FF FF FF FF 05 00 00 91 09 7A 96` | `FF FF FF FF 05 00 00 00 09 17 06` | All |
| M5 Anti Snore (C046–C049) | `FF FF FF FF 05 00 00 F0 0F D3 04` | `FF FF FF FF 05 00 00 FF 0F D6 F4` | `FF FF FF FF 05 00 00 F1 0F D2 94` | `FF FF FF FF 05 00 00 00 0F 97 04` | 1, 2, 3, 4, 5, 7, 9 |
| M5 Special Flat Bed (C050–C051) | `FF FF FF FF 05 00 00 F0 0F D3 04` | | `FF FF FF FF 05 00 00 F1 0F D2 94` | | 6, 8 |

- Flat, TV, Zero Gravity and Anti Snore presets, five memory recalls and
  saves, and explicit clear buttons are available where the app exposes them.
- Slots 1/2 require a saved indicator. Slots 3/4/5 select stored or built-in
  TV/Zero Gravity/Anti Snore according to the indicator.
- Types 6/8 replace slot 5 with a Flat Bed save/recall, regardless of the
  flag, and have no slot-5 clear.

### Circulation massage

| Row | Command | Bytes (hex) | Types |
|-----|---------|-------------|-------|
| C019 | Whole body circulation | `FF FF FF FF 05 00 05 00 E4 C7 4A` | 1, 2, 4, 5 |
| C020 | Whole body circulation (type 3 literal) | `FF FF FF FF 05 00 00 00 E7 97 4A` | 3 |
| C021 | Back and leg circulation | `FF FF FF FF 05 00 05 00 E8 C7 4F` | 1 |
| C022 | Head circulation | `FF FF FF FF 05 00 05 00 E3 86 88` | 2, 3, 4, 5 |
| C023 | Waist circulation | `FF FF FF FF 05 00 05 00 E6 46 8B` | 1, 2, 3 |
| C024 | Hip circulation | `FF FF FF FF 05 00 05 00 E6 46 8B` | 4, 5 |
| C025 | Leg circulation | `FF FF FF FF 05 00 05 00 E5 06 8A` | 1, 2, 3, 4, 5 |

Types 1–5 have their app-labelled circulation buttons. Type 3 uses a different
whole-body literal. The app's two-second circulation UI unlock sends no BLE
packet; HA exposes the resulting actions directly.

### Massage

| Row | Command | Bytes (hex) | Types |
|-----|---------|-------------|-------|
| C052 | Head massage increase | `FF FF FF FF 05 00 00 00 10 D6 CC` | All |
| C053 | Head massage decrease | `FF FF FF FF 05 00 00 00 11 17 0C` | All |
| C054 | Foot massage increase | `FF FF FF FF 05 00 00 00 12 57 0D` | All |
| C055 | Foot massage decrease | `FF FF FF FF 05 00 00 00 13 96 CD` | All |
| C056 | Wave/frequency increase | `FF FF FF FF 05 00 00 00 14 D7 0F` | All |
| C057 | Wave/frequency decrease | `FF FF FF FF 05 00 00 00 15 16 CF` | All |
| C058 | Massage 10-minute selection | `FF FF FF FF 05 00 00 00 16 56 CE` | All |
| C059 | Massage 20-minute selection | `FF FF FF FF 05 00 00 00 17 97 0E` | All |
| C060 | Massage 30-minute selection | `FF FF FF FF 05 00 00 00 18 D7 0A` | All |
| C061 | Cancel selected massage timer | `FF FF FF FF 05 00 00 00 1C D6 C9` | All |

- Every layout has head/foot massage increase/decrease, wave frequency
  increase/decrease, and 10/20/30-minute timer selections.
- Selecting the same timer twice cancels it; an explicit cancel button is also
  provided.
- Step counters clamp at 0–3 (head/foot) and 0–4 (wave), but every tap still
  writes.

### Lights

| Row | Command | Bytes (hex) | Types |
|-----|---------|-------------|-------|
| C062 | Light duration **10 min** | `FF FF FF FF 05 00 00 00 19 16 CA` | All |
| C063 | Light duration **8 h** | `FF FF FF FF 05 00 00 00 1A 56 CB` | All |
| C064 | Light duration **10 h** | `FF FF FF FF 05 00 00 00 1B 97 0B` | All |

Every layout has light-duration buttons labelled **10 min**, **8 h**, and
**10 h**. Hardware timing is unverified. There is no proven dedicated light
off, brightness, RGB, or channel command.

### Memory queries

Each group is sent in slot order 3, 4, 1, 2, 5.

| Group (types) | Slot 3 TV | Slot 4 Zero Gravity | Slot 1 | Slot 2 | Slot 5 Anti Snore |
|---|---|---|---|---|---|
| Default (1, 2, 3, 4, 5, 9), C065–C069 | `FF FF FF FF 03 00 16 00 09 7E C2` | `FF FF FF FF 03 00 1F 00 09 AE C0` | `FF FF FF FF 03 00 28 00 09 1F 0E` | `FF FF FF FF 03 00 31 00 09 CE C9` | `FF FF FF FF 03 00 3A 00 09 BF 0B` |
| Types 6/8, C070–C074 | `FF FF FF FF 03 00 14 00 03 5F 05` | `FF FF FF FF 03 00 1C 00 03 DE C7` | `FF FF FF FF 03 00 24 00 03 5F 0A` | `FF FF FF FF 03 00 2C 00 03 DE C8` | `FF FF FF FF 03 00 3A 00 09 BF 0B` |
| Type 7, C075–C079 | `FF FF FF FF 03 00 18 00 03 9F 06` | `FF FF FF FF 03 00 20 00 03 1E CB` | `FF FF FF FF 03 00 28 00 03 9F 09` | `FF FF FF FF 03 00 30 00 03 1F 0E` | `FF FF FF FF 03 00 38 00 03 9E CC` |

## State and indicators

- Memory indicators, massage bars, local step counters, circulation and
  selected light/massage durations are exposed as entities. They are **app
  indicators**, not measured positions or device acknowledgments.
- Local successful writes feed the app parser, just as Android write callbacks
  feed its shared receive path. `bedsense_state_source` identifies the last
  published source. Failed HA writes do not fabricate success.
- Memory flags persist per physical bed and app profile, instead of sharing the
  phone app's global flags between unrelated beds.
- A per-address BedSense app session shares the current flags, timer
  selection, step counters and indicators across live/offline controller
  recreation. Only the saved-memory flags persist across Home Assistant
  restarts, matching the app's saved flags versus process-local selections.
- The parser preserves all 41 ordered memory predicates, exact-versus-substring
  matches, the M1-clear exception, association state and unmatched reset
  to 10. The default M1 query has no association rule.
- Foot massage patterns update the **head** display bar in the app; HA
  preserves and labels this as a display width, not foot intensity or physical
  percent.
- Notifications do not update local step counters or selected timers. No
  angles, battery, model or physical position feedback is claimed.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Movement | One frame per press, held for the configured finite movement window, then release |
| Notification read | 200 ms after subscribing |
| Memory queries | After a nominal 2-second setup delay, then 200 ms spacing in slot order 3, 4, 1, 2, 5 |
| **Refresh memory indicators** button | Repeats the memory query sequence |

Types 6/8 and 7 use their own query tables.

## Notes

### Safety adaptations

- HA serializes commands and reads. Movement always attempts release in
  cleanup, including task cancellation.
- Explicit memory save/clear actions replace the phone app's two-second long
  press and buggy uncancelled timers.
- HA does not replay its unassigned/stale initialization write or read
  arbitrary unrelated GATT descriptors.
- BLE failures remain visible. HA's normal adapter/proxy, connection
  freshness, idle handoff and reconnection policies apply.

### Analysis provenance

The [discovery ledger](../apk-analysis/dispositions/row108-bedsense.md) accounts
for all command, parser, transport and excluded behavior. Real users can
validate GATT roles/properties, memory replies, held versus single-shot lift
behavior, background taps, massage and actual light durations after
beta/release.
