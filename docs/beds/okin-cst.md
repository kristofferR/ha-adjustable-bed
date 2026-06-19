# Okin CST (CSTProtocol)

**Status:** Needs testing
**Ref:** Reverse-engineered from `com.okin.bedding.rizemf900` APK

## Known Brands

- Mattress Firm 900-O / MFirm 900-O
- Rize MF900
- Nectar Motion / some `OKIN-*` Nectar bases
- Leggett & Platt Prodigy Comfort Elite / `LP BED CONTROL` when diagnostics
  show the CST connected GATT signature

## Detection

| Signal | Value |
|--------|-------|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN) |
| Name patterns | Varies (shared UUID requires disambiguation; some report as `OKIN-XXXXXX`) |
| Connected GATT hint | CSS `90311623-...` plus Nordic DFU `00001530-...` |
| BLE Pairing | Required |

Manual selection may be needed since the service UUID is shared with other Okin protocols.
Choose this profile for Nectar Motion style `OKIN-*` bases when diagnostics show
both the CSS service and Nordic DFU service.
This also applies to Mattress Firm 900-O / MFirm 900-O bases advertising as
`OKIN-XXXXXX` with the same connected GATT signature.

## Pairing

These bases require an OS-level Bluetooth **bond** before commands are accepted.
Pairing is "Just Works" — **no PIN** and **no dedicated Bluetooth pairing button**.
The bond is negotiated automatically by the OS when a client accesses one of the
firmware's encrypted characteristics; on a real device every read/notify and
Device Information characteristic returns GATT `error=5` "Insufficient
authentication" until the link is bonded, while the command write characteristic
(`62741525-…`) is reachable unbonded.

**To enter pairing mode, power-cycle the control box:** unplug it for ~30 seconds,
then plug it back in. The status light blinks blue, then turns green after ~20 s —
that window is when the base accepts a new bond. Some models instead use the
under-bed lamp/light button (hold until it blinks blue). The physical "Pair"/"Learn"
button found on some OKIN control boxes only syncs the **RF remote**, not Bluetooth.

The integration requests `pair=True` automatically and verifies the bond after
connecting; if the link connected but did not bond it clears its cached bond state,
re-pairs on the next attempt, and surfaces a **"Bluetooth pairing required"** repair
with a guided **Fix** button. ESPHome Bluetooth proxies can pair only on ESPHome
≥ 2024.3.0; a local adapter near the bed is the most reliable for the first bond.

## Protocol

Uses a 14-byte command format with two separate 32-bit fields:

```text
[0x0C, 0x02, motor[4], control[4], 0x00, 0x00, 0x00, 0x00]
```

- **Motor field** (bytes 2-5): Head, foot, tilt, lumbar motor control
- **Control field** (bytes 6-9): Presets, massage, lights
- **Write characteristic:** `62741525-...` (write-with-response)
- **Position notify:** `62741524-...` (same as Okimat)

### Motor Commands (motor field)

| Action | Value |
|--------|-------|
| Stop | `0x00000000` |
| Head Up | `0x00000001` |
| Head Down | `0x00000002` |
| Foot Up | `0x00000004` |
| Foot Down | `0x00000008` |
| Head Tilt Up | `0x00000010` |
| Head Tilt Down | `0x00000020` |
| Lumbar Up | `0x00000040` |
| Lumbar Down | `0x00000080` |

Multiple motor bits can be OR'd together for simultaneous movement.

### Control Commands (control field)

| Action | Value |
|--------|-------|
| Flat | `0x08000000` |
| Zero-G | `0x00001000` |
| Memory 1 | `0x00002000` |
| Memory 2 | `0x00004000` |
| Memory 3 | `0x00008000` |
| Memory 4 | `0x00010000` |
| Light Toggle | `0x00020000` |
| Massage On/Off | `0x04000000` |
| Massage Stop | `0x02000000` |
| Massage Head + | `0x00000800` |
| Massage Head - | `0x00800000` |
| Massage Feet + | `0x00000400` |
| Massage Feet - | `0x01000000` |
| Massage Wave 1 | `0x00080000` |
| Massage Wave 2 | `0x00100000` |
| Massage Timer | `0x00000200` |

## Features

- 4 motors: head, foot, tilt, lumbar
- 4 memory presets (recall only, no programming)
- Toggle lights
- Massage with head/foot intensity control and wave modes
- Position feedback (same as Okimat)

## Relationship to Other Okin Protocols

Command values are identical to Okimat/Okin UUID values. The difference is the packet framing: 14-byte with dual motor+control fields vs 6-byte with a single field.

## App

- **Android:** Mattress Firm 900 - O / MFirm 900-O (`com.okin.bedding.rizemf900`)
- **Android:** `com.okin.bedding.nectarmotion`

## Source

Protocol reverse-engineered from `CSTProtocol.java` in the Rize MF900 and
Nectar Motion APKs.
