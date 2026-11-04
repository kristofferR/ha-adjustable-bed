# eShine E2000 / E3000 / E3100 / E5000

**Status:** ❓ Needs testing (static APK evidence; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- eShine app selectors: E2000, E3000/E3100 (one selector), E5000.
- The app accepts a case-sensitive `Smartbed` substring anywhere in a device name.
- Choose the product explicitly; the name/service does not identify the model.
- The [E6000 app profile](eshine.md) uses a different app and controller.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [eShine](https://play.google.com/store/apps/details?id=com.okin.eshine) 1.1.8 (22) | `com.okin.eshine` |

## Features

| Feature | E2000 | E3000 / E3100 | E5000 |
|---------|-------|---------------|-------|
| Motor Control | ✅ Head, Foot | ✅ Head, Foot | ✅ Head, Foot, Head Tilt |
| Position Feedback | ❌ | ❌ | ❌ |
| Named Presets | ✅ Flat, Zero Gravity, Anti Snore, Reading, Watch TV | ✅ Same | ✅ Same |
| Flat + Zero Gravity chord | ✅ | ✅ | ✅ |
| Numbered Memory Slots | ❌ | ❌ | ❌ |
| Massage | ❌ | ✅ On/off, separate strengths, wave, timer | ✅ Same |
| Night Light | ❌ | ✅ Held toggle and feedback | ✅ Same |
| Local Clock / Alarm | ✅ Zero Gravity / Flat | ✅ Zero Gravity / Flat / Massage | ✅ Same |
| Single-address Split / Coupling | ❌ | ❌ | ❌ |
| HA two-address pair | ✅ Independent sides | ✅ Independent sides | ✅ Independent sides |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`  
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`  
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e`  
**Format:** Direct 2-byte queries, 7-byte controls and 9-byte clock/alarm writes.

### Packet Format

No added header, checksum, encryption, sequence or terminator. Dynamic clock
fields use their low eight bits. Both exact characteristic roles are required;
a shared UART service does not prove that this app profile is appropriate.

### Write Mode

Write without response. The write characteristic must advertise that property.
The receive characteristic may notify or indicate; HA/Bleak manages its CCCD.
There is no app-specific authentication, bond request, or startup handshake.

## Detection / Setup

Select **eShine app** and the same E2000, E3000/E3100 or E5000 selector used in
the app. `Smartbed` advertisements offer an app candidate; they never select the
product. Identical names at different addresses remain separate devices.
Automatic discovery uses the existing advertised Nordic UART service registration.
HA rejects leading-wildcard name matchers, so a name-only advertisement with
`Smartbed` in the middle of its name remains available through **Add integration**
and the manual scan. No guessed name prefix or default product is substituted.
The app search hint does not question an already matching receiver profile.

Generic motor count, massage opt-in and refresh delay are owned by this profile.
The pulse count bounds an ordinary HA press; sustained actions accept a duration.
Single-address pairing is unavailable. For two independent addresses, configure
each side's own product before combining them using HA's existing paired setup.

## Commands

Values below come from the shipped `eshine_okin_protocol.py` command table.

| Command | Bytes | Description |
|---------|-------|-------------|
| `query_alarm` | `00 c0` | Query alarm |
| `query_state` | `00 b0` | Query massage/light state |
| `disable_alarm` | `07 05 00 00 00 00 00 00 00` | Disable local alarm |
| `massage_wave` | `05 02 10 00 00 00 00` | Increment wave, only while massage is reported on |
| `stop` | `05 02 00 00 00 00 00` | Movement/release request |
| `tv` | `05 02 00 00 40 00 00` | Watch TV, held |
| `anti_snore` | `05 02 00 00 80 00 00` | Anti Snore, held |
| `zero_g` | `05 02 00 00 10 00 00` | Zero Gravity, held |
| `feet_down` | `05 02 00 00 00 08 00` | Foot down, held |
| `feet_up` | `05 02 00 00 00 04 00` | Foot up, held |
| `head_down` | `05 02 00 00 00 02 00` | Head down, held |
| `head_up` | `05 02 00 00 00 01 00` | Head up, held |
| `pillow_down` | `05 02 00 00 00 20 00` | Head Tilt down, E5000 only, held |
| `pillow_up` | `05 02 00 00 00 10 00` | Head Tilt up, E5000 only, held |
| `light` | `05 02 00 02 00 00 00` | Night Light toggle, E3000/E3100/E5000, held |
| `flat` | `05 02 08 00 00 00 00` | Flat, held |
| `reading` | `05 02 00 00 20 00 00` | Reading, held |
| `massage_foot_strength` | `05 02 00 00 04 00 00` | Increment Foot strength |
| `massage_head_strength` | `05 02 00 00 08 00 00` | Increment Head strength |
| `massage_timer` | `05 02 00 00 02 00 00` | Cycle timer indicator |
| `massage_off` | `05 02 02 00 00 00 00` | Massage off |
| `massage_on` | `05 02 00 00 01 00 00` | Massage on |
| `flat_zero_g` | `05 02 08 00 10 00 00` | Flat + Zero Gravity chord, held |

### Clock and Alarms

| Command | Bytes | Description |
|---------|-------|-------------|
| Local clock | `07 04 YY MM DD WW hh mm ss` | Year minus 2000; weekday Monday=1 through Sunday=7 |
| Enable alarm | `07 05 days action hh mm 00 01 01` | `days` is one next-occurrence day bit, Sunday bit0 |
| Alarm action | `01` / `09` / `08` | Zero Gravity / Flat / Massage; Massage unavailable on E2000 |

`adjustable_bed.eshine_set_alarm` accepts `enabled`, minute-precision `time` and
`wake_mode` (`zero_g`, `flat`, `massage`). A time at or before now selects tomorrow.
An enabled alarm synchronizes the local clock first. Setting writes the same
snapshot twice with a query between them and after them, spaced 200 ms. Disabling
writes the nine-byte zero form and queries after 200 ms. No arbitrary weekday
schedule, massage intensity or alarm slot is inferred.

```yaml
action: adjustable_bed.eshine_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "07:00:00"
  wake_mode: zero_g
```

### Sustained Presets and Chord

Use `adjustable_bed.hold_control` with `flat`, `zero_g`, `anti_snore`, `reading`,
`tv` or `flat_zero_g` and a duration in seconds. The same held bytes are used for
long holds. The app's 5.5-second Set/Reset toast does not prove physical saving or
reset success; there is no separate save/reset packet or numbered memory command.
The ordinary preset buttons use a bounded pulse window rather than an assumed
one-shot motion.

## Position Feedback / Notifications

There are no angles, positions, battery or firmware/device-information parsers.
Massage and alarm sensors expose complete received state as attributes; the card
includes them in its existing massage and utility sections. A clock sync button,
state/alarm refresh buttons and separate strength/timer buttons are also exposed.

| Header | Fields |
|--------|--------|
| `a5 0b 0e` | Seconds=`d4*256+d5`; timer index=ceil(seconds/600); wave=`d6-1`; Head uses `d7&15`, Foot uses unmasked `d8`; each strength=`v%3+v//3+(v>1)`; light is on exactly when `d13==1` |
| `a5 0c 0e` | Weekday mask `d4`, action `d5`, hour `d6`, minute `d7`, enabled `d9`; enabled1 with all four preceding fields zero means off; other nonzero enabled means on |

Timer indexes 1/2/3 correspond to the app's 10/20/30-minute indicators. Reported
values remain unclamped, including wave -1, Head6, Foot86/87 or timer110. Disabled
massage zeroes its displayed wave/strengths while preserving raw observations.
Alarm actions map 1/9/8 to Zero Gravity/Flat/Massage; unknown action is reported as
unknown. Overflow hours/minutes normalize in the local reference date; raw fields
remain available. Received actions never enable additional product capabilities.

HA ignores incomplete or unknown notifications atomically. In particular, the
app's unknown `fe 16` marker is not treated as a proven fragmentation format and
cannot suppress the next valid delivery. State is invalidated on disconnect.
The [disposition ledger](../apk-analysis/dispositions/row122-eshine.md) explains
all intentional app-to-HA framing and lifecycle corrections.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Held movement, presets, chord and Night Light | Immediate write, refresh every 300 ms while held |
| Release / STOP | Captured literal after 200 ms, with uncancelled cleanup to original session |
| Night Light state refresh | 300 ms after release request |
| Massage increment/on/off | One write, query after 50 ms, no movement STOP |
| Clock | Wait 100 ms, clock write, alarm query after 200 ms |
| Alarm enable | Set, wait 200 ms, query then set, wait 200 ms, query |
| Connect | Subscribe once, query massage/light, wait 200 ms, query alarm |

HA serializes operations and bounds held controls to at most 60 seconds.
Cancellation/error release uses shielded, drained `finally` cleanup; delayed work cannot migrate to another
session. Timing describes requested writes, not measured on-air or firmware timing.

## Notes

- All physical behavior remains unverified, including STOP scope and long-hold
  preset persistence. Do not infer either from the shared transport.
- No WiFi/cloud/account/OTA management is included.
- Real users may validate physical behavior after a beta or release.

### Analysis provenance

- Package `com.okin.eshine` 1.1.8, version code 22.
- Six-file artifact set SHA-256: `fbf9cbc16b7f016c296821899e11e0d540f609af5ad9fb05bd3842a63acf9a5a`.
- Base APK SHA-256: `aa46126cc2dacb0ac8ecbdfb7968624cce4efba419c66ef3d1aa8000c45af7cd`.
- [Accepted evidence and all discovery dispositions](../apk-analysis/dispositions/row122-eshine.md).
