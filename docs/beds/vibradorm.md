# Vibradorm: generic controller

**Status:** ✅ Tested generic controller. The separate app profiles below have
artifact-verified behavior; physical operation remains unverified.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Vibradorm VMAT series beds
- Device names starting with "VMAT" (e.g., "VMATMEM047")

This page describes the existing generic Vibradorm route. Existing entries keep
that controller unless you explicitly select an app profile. Shared Bluetooth
identifiers, device names and model strings do not identify an app or its remote
layout.

The bed-type picker has one **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic** entry. Choose **Legacy setup** inside it for this controller, or
choose the app and matching remote/product. Existing entries keep their saved
controller until you explicitly reconfigure them. See the
[guided setup and migration](../CONFIGURATION.md#vibradorm-guided-setup-and-migration).

## App profiles

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

## Generic controller features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | Legacy notification handling on compatible variants |
| Memory Presets | ✅ (6 slots) |
| Flat Preset | ✅ |
| Light Control | ✅ |
| Massage | ✅ (vibration toggle via CBI characteristic) |

**Position Feedback:** The generic controller decodes raw encoder counts and
scales them into angle estimates using estimated raw travel limits and the
configured maximum angles. These are not measured degrees or device-reported
percentages. This path is disabled for the `VMAT-BASIC-RF-CBI` model. It is
separate from the explicitly selected app profiles.

**Motor Configurations:** The generic controller offers 2, 3, or 4 configured
motor groups. The standard 2-motor configuration has back and legs controls.

## Protocol Details

**Primary Service UUID:** `00001525-9f03-0de5-96c5-b8f4f3081186`
**Secondary Service UUID (some VMAT-BASIC-RF-CBI beds):** `00001527-9f03-0de5-96c5-b8f4f3081186`
**Command Characteristic:** `00001526-9f03-0de5-96c5-b8f4f3081186` (fallbacks: `00001528`, `00001534`)
**Light Characteristic:** `00001529-9f03-0de5-96c5-b8f4f3081186`
**Notify Characteristic:** `00001551-9f03-0de5-96c5-b8f4f3081186`

**Manufacturer ID:** 944 (0x03B0)

### Command Format

Commands are single bytes written to the command characteristic:

| Command | Value | Hex |
|---------|-------|-----|
| Stop | 255 | `0xFF` |
| Head Up | 11 | `0x0B` |
| Head Down | 10 | `0x0A` |
| Legs Up | 9 | `0x09` |
| Legs Down | 8 | `0x08` |
| All Down/Flat | 0 | `0x00` |
| Memory 1 | 14 | `0x0E` |
| Memory 2 | 15 | `0x0F` |
| Memory 3 | 12 | `0x0C` |
| Memory 4 | 26 | `0x1A` |
| Memory 5 | 27 | `0x1B` |
| Memory 6 | 28 | `0x1C` |

### Light Control

Light commands are 3 bytes written to the light characteristic:

```text
[brightness, 0x00, timer]
```
- `brightness`: 0 = off, 0xFF = full brightness
- `timer`: Auto-off timer value (0 = no timer)

The generic on/off actions send only levels 0/0xFF and timer 0. Adjustable
brightness and timers belong to the app profiles that explicitly support them.

### Position Feedback

The existing generic parser accepts `20 3f flags` followed by big-endian
16-bit counts, or the short `3f flags` form:

| Axis | Long-form bytes | Short-form bytes |
|------|-----------------|------------------|
| Back | 3–4 | 2–3 |
| Legs | 5–6 | 4–5 |
| Head, when configured | 7–8 | 6–7 |
| Feet, when configured | 9–10 | 8–9 |

Byte indices are zero-based. This describes the current implementation in
[`VibradormController`](../../custom_components/adjustable_bed/beds/vibradorm.py),
covered by `TestVibradormPositionFeedback` in
[`test_vibradorm.py`](../../tests/test_vibradorm.py). It does not establish a
calibrated physical angle, initialization-state handling or equivalent position
support in another app profile.

## Detection

The bed is detected by:
1. **Manufacturer ID:** 944 (0x03B0) - highest priority
2. **Service UUID:** `00001525-...` or `00001527-...`
3. **Device name pattern:** Names starting with "VMAT"

These are generic discovery hints, not proof of an app, remote layout or every
optional feature.

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
