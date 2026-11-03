# Jordan's Tranquil

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled with the Jordan's Tranquil app (Android package `com.okin.bedding.tranquil`)
- OKIN receivers; their names and GATT UUIDs are shared with other apps
- Reuses the [Serenity](serenity.md) controller core: the same transport, 14-byte
  frame, refresh/release lifecycle and notification parser. Its action table,
  save codes and buttons are its own.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Jordan's Tranquil](https://play.google.com/store/apps/details?id=com.okin.bedding.tranquil) 1.0.2 (code 3) | `com.okin.bedding.tranquil` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head and Feet covers; Remote Selector 4/5 as literal buttons |
| Position Feedback | ❌ |
| Memory Presets | ✅ (M1, M2; plus Save Zero Gravity and Save Lounge) |
| Presets | ✅ Flat, Zero Gravity, Lounge, Anti-Snore (voice only); no TV |
| Massage | ✅ (head/foot/mode/timer cycles, toggle; voice-only off and Wave 1-3) |
| Lights | ✅ (native toggle, assumed-state on/off switch; no RGB or brightness) |
| Alarms | ❌ (no alarm page; alarm replies are parsed as diagnostic state only) |
| Diagnostic state | ✅ (manufacturer, status code, massage timer, save event, alarm reply) |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Manufacturer Read:** service `0000180a-0000-1000-8000-00805f9b34fb`, characteristic `00002a29-0000-1000-8000-00805f9b34fb`
**Format:** 14-byte CST frame: `0c 02`, a big-endian 32-bit primary field, a
big-endian 32-bit secondary field, then four zero bytes

### Packet Format

```text
[0x0C, 0x02, primary(4, big-endian), secondary(4, big-endian), 0x00, 0x00, 0x00, 0x00]
```

- There is no checksum, encryption, side selector, PIN or bonding.
- Example: Lounge `0c 02 00 00 20 00 00 00 00 00 00 00 00 00`; Release/Stop is
  `0c 02` plus twelve zero bytes.

### Write Mode

The app leaves the Android write type unchanged; HA prefers acknowledged writes
when `write` is advertised, otherwise `write-without-response`. This is a host
policy.

## Detection / Setup

- Select **Jordan's Tranquil app** manually. Shared OKIN names and GATT UUIDs do
  not identify this app.
- The app always shows its Z280 remote and massage pages; the stored model
  choice is ignored.
- Manufacturer strings, including CST13/CST14, never enable alarm controls in
  this app.

## Reachable commands

Values occupy the primary field unless a secondary value is listed. The
`hold_control` name is the service's `control` value.

### Motor Control

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Head up/down (`head_up`, `head_down`) | `0x1`, `0x2` | 0 | Touch and voice |
| Foot up/down (`foot_up`, `foot_down`) | `0x4`, `0x8` | 0 | Touch and voice |
| Remote Selector 4 up/down (`selector_4_up`, `selector_4_down`) | `0x10`, `0x20` | 0 | Lumbar-icon touch, voice "lumbar" |
| Remote Selector 5 up/down (`selector_5_up`, `selector_5_down`) | `0x40`, `0x80` | 0 | H TILT touch, voice "head tilt" |
| Release/Stop | 0 | 0 | Release, cancel and timed stops |

The lumbar-icon and H TILT buttons send builder operations 4 and 5, while the
app's presenter method names are swapped. Voice labels agree with the touch
labels. As with Serenity, HA exposes literal **Remote Selector 4/5 Up/Down**
buttons and creates covers only for Head and Feet. The physical actuator behind
each selector is unverified.

### Presets

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Flat (`flat`) | `0x08000000` | 0 | Touch and voice |
| Zero Gravity (`zero_g`) | `0x1000` | 0 | Touch and voice |
| Lounge (`lounge`) | `0x2000` | 0 | Touch, voice "lounge"/"leisure" |
| Anti-Snore (`anti_snore`) | `0x8000` | 0 | Voice only (the touch button is hidden) |

### Memory

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| M1, M2 (`memory_1`, `memory_2`) | `0x10000`, `0x40000` | 0 | Touch |
| Save Zero Gravity, Save Lounge (`save_zero_g`, `save_lounge`) | `0x08001000`, `0x08002000` | 0 | Flat + preset chord |
| Save M1, Save M2 (`save_memory_1`, `save_memory_2`) | `0x08010000`, `0x08040000` | 0 | Flat + preset chord |

Only M1 and M2 are numbered memory slots. **Save Zero Gravity** and **Save
Lounge** buttons cover the other chords.

### Massage

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Head/foot massage cycle (`massage_head_cycle`, `massage_foot_cycle`) | `0x800`, `0x400` | 0 | Massage page |
| Massage mode, timer cycle (`massage_mode_cycle`, `massage_timer_cycle`) | `0x10000000`, `0x200` | 0 | Massage page |
| Massage toggle (`massage_toggle`) | `0x100` | 0 | Massage page |
| Massage off (`massage_off`) | `0x02000000` | 0 | Voice only |
| Wave 1, 2, 3 (`wave_1`..`wave_3`) | 0 | `0x80000`, `0x100000`, `0x200000` | Voice only |

### Lights

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Light toggle (`light_toggle`) | `0x20000` | 0 | Massage page and voice |
| Light on, off (`light_on`, `light_off`) | 0 | `0x40`, `0x80` | Voice only |

Light on/off is an assumed-state switch; **Toggle Light** sends the native
toggle. There is no RGB or brightness command, although the app help mentions
color cycling.

## Command Timing

| Operation | Hold | Source |
|-----------|------|--------|
| Held controls | Repeat every 100 ms | App |
| Ordinary cover pulses | Configured count at the 100 ms interval | HA setting |
| Flat | 1500 ms | App voice deadline |
| Lounge, Zero Gravity, Anti-Snore, waves, massage off and light commands | 500 ms | App voice deadlines |
| Save buttons | Five seconds | App help; the app has no hold timer or storage acknowledgement |
| M1/M2 recall, selectors and massage-page buttons | Same 500 ms bound | HA policy |
| `hold_control` | Any literal action for 0.1 to 60 seconds | HA service |

Release attempts two zero frames at +100 and +200 ms from one origin, with a
fresh cancellation event so cancellation cannot suppress either. Every release
is global, so all covers share one scheduler resource.

## Notifications and diagnostic state

The parser is shared with [Serenity](serenity.md#notifications-and-diagnostic-state):

- Inputs of ten bytes or fewer are ignored.
- Byte 1 equal to 12 is an alarm reply: signed repeat/hour/minute at 4/6/7,
  subtype at 5, enabled at 9. Alarm replies are parsed even though this app has
  no alarm page.
- Otherwise signed byte 10 is a change-only status code. A changed status during
  a pending save reports the app's local save code (Zero Gravity 5, Lounge 3,
  M1 4, M2 8). Any recall clears it.
- Otherwise it updates the massage timer code; 1/2/3 mean 10/20/30 minutes in
  the app.

| State | Keys |
|-------|------|
| Diagnostic state | `tranquil_manufacturer`, `tranquil_status_code`, `tranquil_massage_timer_code`, `tranquil_massage_timer_minutes`, `tranquil_save_event_code`, `tranquil_alarm_type` |
| Alarm attributes | `tranquil_alarm_repeat`, `tranquil_alarm_hour`, `tranquil_alarm_minute`, `tranquil_alarm_on` |

The manufacturer is read one second after subscribing; **Refresh Manufacturer**
repeats the app's on-resume read.

## Notes

### Safety adaptations

Excluded app behavior:

- The voice "stop" branch sends Head Up before scheduling STOP, so HA sends STOP
  only.
- Unbounded voice motion, remote touch-mask replay, delayed stops that overlap
  newer commands, and streams that survive disconnect or device changes.

### Deferred validation

For real users after a release: actuator mapping of selectors 4 and 5, ATT write
mode, repeat and STOP arrival, save persistence and minimum hold time, massage
and light semantics, and notification contents.

### Analysis provenance

- Independently accepted APK Protocol Audit of `com.okin.bedding.tranquil`
  version 1.0.2/code 3, and the cluster 010 reconciliation with the
  [Customatic Z-Series](customatic-z-series.md) app.
- Artifact SHA-256: `595749e9f8eb2b654d88ad477fa80e4dfe5849335889b8c241fbd22faf3f5bda`
- Discovery ledger: [row052 dispositions](../apk-analysis/dispositions/row052-okin-zseries-tranquil.md)
