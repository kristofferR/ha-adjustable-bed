# Nectar

**Status:** ❓ Needs testing (legacy seven-byte protocol)

**Credit:** Reverse engineering by [MaximumWorf](https://github.com/MaximumWorf) - [homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar)

> [!NOTE]
> This page describes the legacy seven-byte Nectar protocol. The newer Nectar
> Motion app is a separate, explicit **Nectar Move** profile of [Okin CST](okin-cst.md).
> An `OKIN-*` name, shared OKIN UUID, or Device Information value does not select
> that app profile automatically.

## Known Models

- Nectar Split King Luxe Adjustable Foundation
- Nectar adjustable bases
- Other beds using Okin controllers with 7-byte command format
- Some Nectar Motion bases use the [Okin CST](okin-cst.md) 14-byte protocol
  instead of this 7-byte protocol (see [Detection / Setup](#detection--setup))

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ⬜ | Nectar Adjustable | (no longer available) |
| ✅ | Nectar Motion / Nectar Move | `com.okin.bedding.nectarmotion` (select **Nectar Move** under Okin CST) |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (Head, Feet, Lumbar; legacy seven-byte profile) |
| Position Feedback | ❌ |
| Memory Presets | ⚠️ (recall of slots 1-2 only, no programming; see [Notes](#notes)) |
| Massage | ✅ (global on, wave and off; no intensity commands) |
| Under-bed Lights | ✅ (separate on/off) |
| Zero-G / Anti-Snore / Lounge | ✅ |
| TV | ⚠️ (sends the Lounge byte) |
| BLE Pairing | ❌ Not required |

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b` (OKIN Primary Service)
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 7-byte commands: `5A 01 03 10 30 [XX] A5`
**Write Mode:** write without response

> [!NOTE]
> Nectar beds share the Okin service UUID with Okimat but use a **7-byte
> command format** (vs Okimat's 6-byte format). The commands are not
> interchangeable: if your bed is detected as the wrong type, change it in
> integration settings.

These command details apply only to the legacy `nectar` integration profile.
Nectar Move uses the separate Okin CST framing and actions documented on the
[Okin CST page](okin-cst.md). Do not interchange the command sets.

## Detection / Setup

- The legacy protocol may be detected by a device name containing `nectar`
  (case-insensitive) with the Okin service UUID. That signal does not identify
  the Nectar Move app profile.
- Some Nectar bases advertise only as `OKIN-XXXXXX`. Those names are ambiguous
  with classic Okimat, 7-byte Nectar, and newer CST controllers, so setup
  prompts for the Okin-family protocol. Choose `Nectar` only for the 7-byte
  protocol.
- Select **Nectar Move** explicitly when setting up that app profile; shared
  advertisements and Device Information are not sufficient to choose it.
- The `62741523-...` OKIN service, `90311623-...` CSS service, and Nordic DFU
  service `00001530-...` are not sufficient by themselves to identify CST
  because RF ECO BT stair actuators share that GATT inventory. Choose **Okin
  CST (Rize product profiles, 14-byte dual-field)** only when the known base or app identity also
  corroborates CST. Device Information model `MEGAMAT MBZ` identifies RF ECO BT
  instead.
- Or manually configured with bed type: `nectar` (a legacy alias that resolves
  to the `okin_7byte` protocol type).

## Commands

### Motor Control

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Head Up | `5A 01 03 10 30 00 A5` | Raise head |
| Head Down | `5A 01 03 10 30 01 A5` | Lower head |
| Foot Up | `5A 01 03 10 30 02 A5` | Raise feet |
| Foot Down | `5A 01 03 10 30 03 A5` | Lower feet |
| Lumbar Up | `5A 01 03 10 30 04 A5` | Raise lumbar |
| Lumbar Down | `5A 01 03 10 30 07 A5` | Lower lumbar |
| Stop | `5A 01 03 10 30 0F A5` | Stop all motors |

### Presets

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Flat | `5A 01 03 10 30 10 A5` | Go to flat position |
| Lounge | `5A 01 03 10 30 11 A5` | Go to lounge position |
| TV | `5A 01 03 10 30 11 A5` | Same byte as Lounge |
| Zero Gravity | `5A 01 03 10 30 13 A5` | Go to zero-G position |
| Anti-Snore | `5A 01 03 10 30 16 A5` | Go to anti-snore position |

### Memory

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Memory 1 | `5A 01 03 10 30 1A A5` | Recall memory 1 |
| Memory 2 | `5A 01 03 10 30 1B A5` | Recall memory 2 |

Memory programming is not supported.

### Massage

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Massage On | `5A 01 03 10 30 58 A5` | Turn on massage (also sent by the massage, head and foot toggles) |
| Massage Wave | `5A 01 03 10 30 59 A5` | Switch to wave pattern (massage mode step) |
| Massage Off | `5A 01 03 10 30 5A A5` | Turn off massage |

### Lights

| Command | Hex Value | Description |
|---------|-----------|-------------|
| Light On | `5A 01 03 10 30 73 A5` | Turn on under-bed lights |
| Light Off | `5A 01 03 10 30 74 A5` | Turn off under-bed lights |
| Light Toggle | `5A 01 03 10 30 71 A5` | Controller method only; HA hides the toggle button because discrete on/off exists |

## Command Timing

| Command type | Integration behavior |
|---|---|
| Motor movement | Repeats at the configured motor pulse count and delay, then sends Stop |
| Presets and memory recall | Repeats 100 times at 300 ms, then sends Stop |
| Massage and lights | One write |

The cleanup Stop uses a fresh cancel event so a pending stop request cannot
suppress it.

## Notes

### Protocol Family

Nectar is part of the [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family). Key differences from other Okin beds:

- Uses **7-byte** command format (similar to Mattress Firm 900)
- Does **not** require Bluetooth pairing
- No position feedback support

### Behavior

- Nectar beds share the Okin service UUID with Okimat beds but use a different command protocol
- Generic `OKIN-XXXXXX` names require user confirmation because several Okin protocols share the same advertised UUID
- Nectar Motion using the newer app uses the explicit [Nectar Move profile](okin-cst.md#nectar-move-profile) under Okin CST
- Massage control is global (no separate head/foot control)
- Lights have separate on/off commands (no toggle button)

> [!NOTE]
> Earlier versions of this page listed no memory presets, no TV preset and no
> light toggle. The controller sends Memory 1/2 recall (`1A`/`1B`), TV with the
> Lounge byte (`11`) and a light toggle (`71`). Those bytes were absent from
> the earlier documented command list and are unverified on hardware.
