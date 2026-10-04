# Adjustable bed (Lumbar) app profile

Select **Adjustable bed (Lumbar) app** manually when the bed uses the Android app `com.okin.bedding.adjustablelumbar` (shown as "Adjustable bed(Lumbar)"). The profile follows the accepted APK Protocol Audit of version 1.2.2 (code 33), a 20-APK Flutter XAPK with SHA-256 `ed65ed1b4970c95c2b1744687f94401447f851f23e81f8af6699a68854988b08`. Behavior is static-verified only: **hardware unverified**. The comparison ledger is [row054](../apk-analysis/dispositions/row054-adjustable-lumbar.md).

OKIN and Star Bluetooth names, the Nordic UART service and the OKIN `62741523` service are shared with other apps and bed types ([Okin 64-Bit](okin-64bit.md), [Sleepy's BOX25](sleepys.md) and others), so they never select this profile. Existing entries keep their bed type until you change it.

## Command tables

The app ships three tables and picks one per connection:

| Bluetooth name (lowercased prefix) | Device Information manufacturer (`0x2A29`) | Table | Service | Write | Notify | Write type |
|---|---|---|---|---|---|---|
| `okin` (checked first) | read, value unused | `36_33_04a` | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-…` | `62741625-…` | With response |
| `star` | exactly the four bytes `STAR` | `35_22_01` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-…` | `6e400003-…` | Without response |
| `star` | anything else, unreadable or absent | `25_42_02` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-…` | `6e400003-…` | Without response |

The manufacturer match is case-sensitive and exact: `STAR` followed by a NUL byte selects `25_42_02`. Any other name, including `smartbed` (which the app's scan accepts), has no table in the app, so the connection is refused with `auto`.

| Variant | Meaning |
|---|---|
| `auto` (default) | Apply the app's name rule |
| `adjustable_lumbar_okin` | Always use the `okin` row |
| `adjustable_lumbar_star` | Always use the `star` rows; the manufacturer read still chooses between them |

The name rule reads the raw Bluetooth name, not the entry's display name. HA stores the raw name at setup and on later real (non-address) observations; an address-like live name falls back to it. Use a fixed variant if Home Assistant sees a different name than the phone. In a two-address pair the variant belongs to each physical bed: unpair, set each bed, then combine them again.

## Connection requirements

Like the app, the profile requires the table's service with its write and notify characteristics, a write property matching the table's write type, and the Device Information service (`0x180A`). The `okin` row also requires the manufacturer characteristic. A missing requirement refuses the connection. The manufacturer is read once per connection before notifications are enabled; the generic Device Information read is skipped for this profile. Notifications stay enabled with angle sensing off, because the app only allows control after enabling them. No pairing, PIN or handshake exists.

Replies are not parsed. In every shipped table the massage-status dispatch can never match, alarm frames are only logged and the remaining callbacks have no consumers. Raw replies still appear in support bundles.

## Frames

- `25_42_02` and `36_33_04a`: `08 02` + eight table bytes (identical payloads, different transport).
- `35_22_01`: `5A 01` + four table bytes + `A5`.
- No checksum, sequence, side byte or encryption.

| Control | `25_42_02` / `36_33_04a` | `35_22_01` |
|---|---|---|
| Head up / down | `08 02 00 00 00 01 00 00 00 00` / `…02…` | `5A 01 03 10 30 00 A5` / `…30 01 A5` |
| Foot up / down | `08 02 00 00 00 04 00 00 00 00` / `…08…` | `5A 01 03 10 30 02 A5` / `…30 03 A5` |
| Lumbar up / down | `08 02 00 00 00 10 00 00 00 00` / `…20…` | `5A 01 03 10 30 06 A5` / `…30 07 A5` |
| STOP | `08 02 00 00 00 00 00 00 00 00` | `5A 01 03 10 30 0F A5` |
| Flat | `08 02 08 00 00 00 00 00 00 00` | `5A 01 03 10 30 10 A5` |
| Zero gravity | `08 02 00 00 10 00 00 00 00 00` | `5A 01 03 10 30 13 A5` |
| Lounge (app: LEISURE) | `08 02 00 00 20 00 00 00 00 00` | `5A 01 03 10 30 12 A5` |
| Incline (app: INCLINE) | `08 02 00 00 40 00 00 00 00 00` | `5A 01 03 10 30 11 A5` |
| Anti-snore | `08 02 00 00 80 00 00 00 00 00` | `5A 01 03 10 30 16 A5` |
| Save zero gravity / lounge / incline / anti-snore | `08 02 08 00 10…` / `…20…` / `…40…` / `…80…` | `5A 01 03 10 30 90/91/92/93 A5` |
| Light | `08 02 00 02 00 00 00 00 00 00` | `5A 01 03 10 30 71 A5` |
| Massage wave 1 / 2 / 3 | `08 02 00 00 00 00 00 08 00 00` / `…10…` / `…20…` | `5A 01 03 10 30 52/53/54 A5` |
| Massage stop | `08 02 02 00 00 00 00 00 00 00` | `5A 01 03 10 30 6F A5` |
| Massage intensity + / − | `08 02 00 00 0C 00 00 00 00 00` / `08 02 01 80 00 00 00 00 00 00` | `5A 01 03 10 40 60 A5` / `…40 61 A5` |
| Massage on (voice route) | `08 02 00 00 01 00 00 00 00 00` | `5A 01 03 10 30 52 A5` |
| Voice pre-STOP | ordinary STOP | `5A 01 03 10 30 1F A5` |
| Check massage (raw query) | `02 04` | `5A B0 00 A5` |

## Timing and controls

Held app controls write immediately and then every 100 ms. Releasing writes STOP immediately and again 300 ms later; both STOPs use fresh cancel events and are always attempted.

| Home Assistant control | Behavior |
|---|---|
| Head, Feet and Lumbar covers | Stream for the configured pulse count at 100 ms (default 10, about 1 s), then the release STOPs. Motor count and pulse delay are fixed. |
| Flat, Zero Gravity, Lounge, Incline, Anti-Snore presets; Toggle Light; Massage +/−; Wave 1–3 | App tap: one write, then the release STOPs. Use `hold_control` to hold longer. |
| Massage off | Massage stop, then the release STOPs (the release replaces the app's +100 ms repeat). |
| Save Zero Gravity / Lounge / Incline / Anti-Snore | Holds the Flat+preset save frame for 6 s, when the app reports "Setup" (its help text says 5 s), then the release STOPs. Whether the bed stores the position is unverified. |
| Massage On | The app's voice route: one pre-STOP, then the massage-on frame twice, 100 ms apart. It is the only path to this frame. |
| Check Massage | The massage page's raw query, written once. No reply is parsed. |
| Stop | The release STOPs. STOP has no side parameter; its physical scope is unverified. |

The app has no numbered memories, position feedback, light on/off, timers, alarms or firmware update path. Constants for those in its tables are never sent.

Not exposed: the app's speech-recognition commands (the same frames are available as buttons; voice movement is excluded because the app sends no STOP after it), and its chord edge cases (the first held preset briefly recalls before the save starts; an unsupported chord only stops).
