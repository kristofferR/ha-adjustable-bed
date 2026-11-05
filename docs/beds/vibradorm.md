# Vibradorm: generic controller

**Status:** ✅ Tested (generic controller; the separate app profiles below have
artifact-verified behavior, physical operation unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Vibradorm VMAT series beds
- Device names starting with "VMAT" (e.g., "VMATMEM047")
- `VMAT-BASIC-RF-CBI` beds (some use the secondary service)

This page describes the existing generic Vibradorm route. Existing entries keep
that controller unless you explicitly select an app profile. Shared Bluetooth
identifiers, device names and model strings do not identify an app or its remote
layout.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [VIBRADORM Remote](https://play.google.com/store/apps/details?id=de.vibradorm.vra) | `de.vibradorm.vra` |
| ✅ | [VIBRADORM Remote for Beds](https://play.google.com/store/apps/details?id=com.vibradorm.vmatbasic) | `com.vibradorm.vmatbasic` |

The generic controller's protocol comes from these two apps.

### App profiles

[v4.1.0](https://github.com/kristofferR/ha-adjustable-bed/releases/tag/v4.1.0)
includes separate, explicitly selected app profiles. Follow the guide for the
app and remote you use; capabilities and packet behavior are profile-specific.

| Guide | App | Package ID |
|-------|-----|------------|
| [Caresse / Werkmeister](vibradorm_app.md) | Caresse Remote; Werkmeister Unterfederung | `de.vibradorm.diamant`; `de.vibradorm.werkmeister` |
| [VMAT](vmat.md) | VMAT, fourteen shipped remote selections | `de.vibradorm.vmat` |
| [V-MAT Basic](vmatbasic.md) | VIBRADORM Remote for Beds, Basic / CBI / XT-Box | `com.vibradorm.vmatbasic` |

The [issue #403 reconciliation](vmat.md#issue-403-reconciliation) explains which
parts of the original parity request shipped and which were ruled out by the
accepted app audits. Those audits do not establish live position or EEPROM
support for the Caresse, Werkmeister or VMAT app profiles.

## Features

These are the generic controller's features; app profiles are listed above.

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2, 3 or 4 configured motor groups) |
| Position Feedback | ⚠️ (legacy notification handling on compatible variants; angle estimates) |
| Memory Presets | ✅ (6 slots) |
| Flat Preset | ✅ |
| Light Control | ✅ |
| Massage | ✅ (vibration toggle via CBI characteristic) |

**Motor Configurations:** The generic controller offers 2, 3, or 4 configured
motor groups. The standard 2-motor configuration has back and legs controls.

## Protocol Details

**Primary Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
**Secondary Service UUID (some VMAT-BASIC-RF-CBI beds):** `00001527-9f03-0de5-96c5-b8f4f3081186`
**Command Characteristic:** `00001526-9f03-0de5-96c5-b8f4f3081186` (fallbacks: `00001528`, `00001534`)
**Light Characteristic:** `00001529-9f03-0de5-96c5-b8f4f3081186`
**CBI Characteristic:** `00001550-9f03-0de5-96c5-b8f4f3081186`
**Notify Characteristic:** `00001551-9f03-0de5-96c5-b8f4f3081186`
**Format:** Single-byte motor commands; 3-byte light frames; 2-byte CBI headers

**Manufacturer ID:** 944 (0x03B0)

### CBI framing

CBI writes start with a big-endian 16-bit header: the command ORed with a toggle
bit that alternates between `0x0000` and `0x8000` on each CBI send. Extra
parameter bytes follow the header.

### Write Mode

- The controller writes with response when the resolved characteristic advertises
  `write`, and without response when only `write-without-response` is advertised.
- When a proxy surfaces the exact VMAT UUID without usable property metadata, it
  prefers write with response, which the native apps use for these control paths.
- The `VMAT-BASIC-RF-CBI` model drives movement only through `0x1526`; the
  `00001528`/`00001534` fallbacks are not probed for it.

## Detection

The bed is detected by:
1. **Manufacturer ID:** 944 (0x03B0) - highest priority
2. **Service UUID:** `00001525-...` or `00001527-...`
3. **Device name pattern:** Names starting with "VMAT"

These are generic discovery hints, not proof of an app, remote layout or every
optional feature.

### Setup

The bed-type picker has one **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic** entry. Choose **Legacy setup** inside it for this controller,
which then asks the motor count, whether massage motors are fitted and whether
to read positions before pairing, or choose the app and matching
remote/product. Existing entries keep their saved
controller until you explicitly reconfigure them. See the
[guided setup and migration](#guided-setup-and-migration).

#### Guided setup and migration

The bed-type list has one **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic** choice. Choose the app you use on your phone, then its remote or
product. **Legacy setup** remains available inside this choice for fresh setup,
and in Reconfigure an app or V-MAT Basic entry can move back to it.
The family choice shares setup navigation, while each selected app keeps its
existing controller, features and Bluetooth pairing requirements.

For an existing bed, open **Settings → Devices & services → Adjustable Bed**,
then the entry's three-dot menu and **Reconfigure** (see
[Changing the app or layout](../CONFIGURATION.md#changing-the-app-or-layout-of-an-existing-bed)).
The app review in Repairs opens the same wizard. Choose **Keep current setup**
to keep your working controls and answer the review, or choose your app and
remote/product.
Keeping the same app seeds the form with your saved settings.

The wizard temporarily releases Home Assistant's connection to check the chosen
setup. It checks the exact app's required Bluetooth roles and existing pairing
requirements, without moving the bed. A missing scanner, failed check or link
that cannot be closed cannot save the new selection. Retry or keep the current
setup. Closing the wizard leaves the saved configuration and pending review
unchanged. A failed connection remains owned until it is observed closed, so
another setup attempt cannot overlap it.

After a successful check, a final review shows the chosen app and
remote/product, and the controls it adds and removes. Saving keeps the entry,
address, device and unchanged entity IDs. Controls follow the selected profile;
obsolete controls and angle estimates may disappear. This check does not prove physical movement, lighting or massage
behavior. If settings changed in another window, the wizard refuses to overwrite
them. Routine brightness, timer and connection changes remain in **Configure**.

A paired bed must first be split explicitly, or have its standalone controls
restored for a one-address pair. The wizard offers the existing reversible split
action and preserves identities. Each receiver keeps its current connection
preferences and gets back its original bed settings. Afterwards,
reconfigure the intended receiver separately and combine compatible beds again
if needed. It never assigns one app/remote to both receivers or guesses from
Bluetooth identifiers or motor count.

## Commands

### Command Format

Commands are single bytes written to the command characteristic. Motor names
come from German: K = Kopf (head/back), OS = Oberschenkel (thigh/legs),
N = Nacken (neck), F = Fuß (foot), H = Hoch (up), R = Runter (down).

| Command | Value | Hex | Description |
|---------|-------|-----|-------------|
| Stop | 255 | `0xFF` | Stops all motors |
| Head Up | 11 | `0x0B` | KH: back; also head on 2-motor beds |
| Head Down | 10 | `0x0A` | KR: back; also head on 2-motor beds |
| Legs Up | 9 | `0x09` | OSH; also feet on 2/3-motor beds |
| Legs Down | 8 | `0x08` | OSR; also feet on 2/3-motor beds |
| Neck Up | 3 | `0x03` | NH: head on 3/4-motor beds |
| Neck Down | 2 | `0x02` | NR: head on 3/4-motor beds |
| Foot Up | 5 | `0x05` | FH: feet on 4-motor beds |
| Foot Down | 4 | `0x04` | FR: feet on 4-motor beds |
| All Down/Flat | 0 | `0x00` | AR, used as the flat preset |

### Memory

| Command | Value | Hex |
|---------|-------|-----|
| Memory 1 | 14 | `0x0E` |
| Memory 2 | 15 | `0x0F` |
| Memory 3 | 12 | `0x0C` |
| Memory 4 | 26 | `0x1A` |
| Memory 5 | 27 | `0x1B` |
| Memory 6 | 28 | `0x1C` |
| Store | 13 | `0x0D` |

Recall sends the memory byte to the command characteristic. Saving follows the
app's store sequence:

1. Send STORE (`0x0D`) four times to the CBI characteristic, each with the toggle bit.
2. Send the memory slot byte to the CBI characteristic, with the toggle bit.
3. Send STOP (`0xFF`) four times to the command characteristic.

### Light Control

Light commands are 3 bytes written to the light characteristic:

```text
[brightness, 0x00, timer]
```
- `brightness`: 0 = off, 0xFF = full brightness
- `timer`: Auto-off timer value (0 = no timer)

| Command | Bytes |
|---------|-------|
| Light on | `FF 00 00` |
| Light off | `00 00 00` |

The generic on/off actions send only levels 0/0xFF and timer 0. Adjustable
brightness and timers belong to the app profiles that explicitly support them.
The toggle follows the last on/off command HA sent.

### Massage

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| Vibration on / off | CBI | `[MSB(T \| 0x34), LSB(T \| 0x34), 01]` / `[..., 00]` |

`T` is the CBI toggle bit. The toggle alternates on and off from HA's last
command.

### Position request

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| CmdGetStatusMotMon | CBI | `[MSB(T \| 0x3D), LSB(T \| 0x3D), 0x3F]` |

This mirrors the app's SYNC button and asks the bed to send a position
notification. It is skipped for `VMAT-BASIC-RF-CBI`.

## Position Feedback

**Position Feedback:** The generic controller decodes raw encoder counts and
scales them into angle estimates using estimated raw travel limits and the
configured maximum angles. These are not measured degrees or device-reported
percentages. This path is disabled for the `VMAT-BASIC-RF-CBI` model. It is
separate from the explicitly selected app profiles.

The existing generic parser accepts `20 3f flags` followed by big-endian
16-bit counts, or the short `3f flags` form:

| Axis | Long-form bytes | Short-form bytes |
|------|-----------------|------------------|
| Back | 3–4 | 2–3 |
| Legs | 5–6 | 4–5 |
| Head, when configured | 7–8 | 6–7 |
| Feet, when configured | 9–10 | 8–9 |

- Byte indices are zero-based.
- Higher counts mean more raised; 0 is flat.
- Each count becomes a percentage of the estimated raw travel for that axis, then
  an angle estimate. The initial travel estimates are 7000 (back, head) and 14000
  (legs, feet), raised whenever a larger count is observed.
- Other notifications (for example `20 EF` or `21 A0`) are logged for diagnostics
  but otherwise ignored.
- Earlier versions of this document described the counts as little-endian; the
  current parser reads them big-endian.

This describes the current implementation in
[`VibradormController`](../../custom_components/adjustable_bed/beds/vibradorm.py),
covered by `TestVibradormPositionFeedback` in
[`test_vibradorm.py`](../../tests/test_vibradorm.py). It does not establish a
calibrated physical angle, initialization-state handling or equivalent position
support in another app profile.

## Command Timing

- Motor movement uses the configured pulse settings, by default 10 writes at
  100 ms, and always sends STOP (`0xFF`) at the end with a fresh cancel signal.
- Flat and memory recall are hold-to-run: the bed moves only while the command is
  sent. HA sends it up to 200 times at 100 ms (20 s), enough for the slowest
  motors (about 14 s of full travel), then sends STOP. The bed stops on its own at
  the stored position; a STOP request ends the command early.
- Movement-time position polling is disabled, because interleaving CBI status
  requests with hold-to-run commands can cause stutter or premature motor stops.

## Troubleshooting

**Commands not working:**
- Ensure no other device (app, remote) is connected to the bed
- BLE beds only allow one connection at a time

**Position values seem incorrect:**
- Position calibration may vary by bed model
- Open an issue with your bed's position values for calibration assistance

## References

- [GitHub Issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162)
- [GitHub Issue #403](https://github.com/kristofferR/ha-adjustable-bed/issues/403)
- [Accepted Caresse / Werkmeister dispositions](../apk-analysis/row031-dispositions.md)
- [Accepted VMAT dispositions](vmat-dispositions.json)
