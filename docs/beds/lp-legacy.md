# L&P Adjustable Base, legacy app

**Status:** ❓ Needs testing. Static verified, hardware unverified.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

This explicit controller follows **L&P Adjustable Base 2.2.1 (13)**, package
`com.richmat.lp`. It does not change existing Richmat or L&P QRRM
configurations.

## Known Models

- Beds controlled by the L&P Adjustable Base legacy app
- 122 remote layouts, each selected by the four-character code used in that
  app's manual or QR setup (for example `A2RM`, `B1RM`, `ZR00`); the full list
  is `LP_LEGACY_PROFILE_CODES` in `lp_legacy_profiles.py`
- I0RM has no proven bed commands in this app and therefore exposes no remote
  action buttons

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp) 2.2.1 (13) | `com.richmat.lp` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ⚠️ Layout-specific app buttons; no generic head, foot or lumbar axes |
| Position Feedback | ❌ |
| Memory, Massage, Lights | ⚠️ Only as the selected layout's named app buttons |
| RGB Lights | ❌ |
| Global Stop | ⚠️ Cancels and releases the active action only (no emergency-stop command) |
| BLE Pairing | ❌ Not required |

The app's labels describe the available actions. Some are pictograms with
uncertain physical meaning, so the integration keeps those descriptions instead
of assigning guessed head, foot or lumbar axes.

## Protocol Details

**Service UUID:** none fixed; selected from the device's GATT information
**Write Characteristic:** user-configured
**Notify Characteristic:** optional user-configured response characteristic
**Format:** one byte (Legacy) or a five-byte packet (Framed)

The app selects its characteristics at runtime; its accepted report contains no
fixed service or characteristic UUID that can safely be applied to every layout.

### Packet Format

Every control event has a command token: one character, optionally followed by
four hex digits (for example `n006E`).

| Mode | Packet | Example (`n006E`) |
|---|---|---|
| **Legacy** | The first character of the token as one byte | `6E` |
| **Framed** | `6E 01 <hi> <lo> <checksum>`: the token's final four hex digits as two bytes, then the low byte of the sum of the first four bytes | `6E 01 00 6E DD` |

- Only controls with a proven encoding for the selected mode are exposed.
  Single-character tokens have no framed encoding.
- The two modes can send different bytes for the same token. For example
  6BRM's `40024` sends `34` in Legacy mode and `6E 01 00 24 93` in Framed mode.

### Write Mode

The configured characteristic must be writable. Writes use write-with-response
when it has the `write` property, otherwise write-without-response.

## Detection / Setup

Choose the **L&P Adjustable Base (legacy app)** row, or answer **L&P Adjustable
Base legacy app (2.2.1)** in the
[L&P question](leggett-platt.md#home-assistant-setup), then select the exact
remote code and packet mode. An existing legacy entry reaches the other L&P
routes through the same question in **Reconfigure**; **Configure** still changes
its own settings.

- Configure the bed's write characteristic UUID and, when known, its response
  characteristic UUID. These must come from the device's GATT information or a
  capture of the working app.
- Neither a name prefix nor a remote code proves the packet mode.
- Choosing a different layout changes the available controls.
- For paired beds with separate addresses, each side's stored profile provides
  its remote buttons even when that side is unavailable during startup.
- Profile, packet mode and GATT UUIDs stay specific to each side and are not
  shown in the pair's shared settings. To change them, unpair the beds, update
  the individual entries, then pair them again.
- Changing the layout or packet mode creates distinct action entities. Update
  automations to use those new entities; old actions remain unavailable instead
  of being silently reassigned to different commands.

## Commands

Home Assistant exposes the selected layout's actions as named buttons, including
separate long-press actions where the app defines them. They also appear in the
adjustable bed card's utility section. Automations can call the ordinary
`button.press` action on these entities.

Each app button has a press event and a release (completion) event. Their
state decides how the integration sends them:

| State | Event | Integration behavior |
|---|---|---|
| 1 | Held press | Writes immediately, then every 100 ms for the configured motor pulse count |
| 2 | Release | Always written after the press, even when the action is cancelled |
| 3 | Long press | **(long press)** button: waits 3.1 s, then writes once |
| 4 | Short-press completion | Written after a completed press of 3 s or less that was not cancelled; on long-press controls it is the plain button |
| 5 | One-shot press | Writes once, then waits one 100 ms tick |

### Example layout tokens

| Token | Legacy | Framed | Notes |
|---|---|---|---|
| `n006E` | `6E` | `6E 01 00 6E DD` | Release used by 1,372 of the 1,715 catalogued controls |
| `$0024` | `24` | `6E 01 00 24 93` | |
| `40024` | `34` | `6E 01 00 24 93` | 6BRM; the two modes differ |
| `2` | `32` | Undefined | Single character, Legacy only |

The complete per-layout catalog is `lp_legacy_profiles.json`.

## Notifications

The optional app-response diagnostic reports only the three exact patterns the
app recognizes. Their physical meaning is not established. They are not motor
positions, battery readings, a capability query or proof that an alarm is set.

| Frame | Reported effect |
|---|---|
| `6E 09 01 00 78` | `app_status_5` |
| `6E 07 01 01 77` | `alarm_routine_1` |
| `6E 07 01 02 78` | `alarm_routine_2` |

- The response characteristic is subscribed when it notifies or indicates, or
  read once when it is only readable.
- The diagnostic sensor is disabled by default.
- There is no invented position feedback, pairing requirement or RGB capability.

## Command Timing

- Held controls repeat at the app's proven 100 ms cadence. The configured motor
  pulse count determines how long a button invocation holds the control. The
  wait between writes accounts for time spent awaiting the Bluetooth write.
- The integration preserves each control's own release behavior and sends its
  release even when a running action is cancelled.
- One-shot controls do not inherit a movement repeat loop.
- The Stop button cancels the active action and performs its release cleanup.
  It cannot stop movement started outside this integration: the artifact
  defines no separate global emergency-stop command.

## Notes

### Analysis provenance

The implementation uses the accepted APK Protocol Audit report for queue
row019. See [the complete implementation disposition](lp-legacy-disposition.md)
for catalog coverage, excluded application-only behavior and the frozen
evidence identity. Raw APKs and analysis remain machine-local. Physical
confirmation is deferred to users with the corresponding bed after a beta or
release; it is separate from static protocol verification.
