# OKIN Smart Remote / RF ECO BT Single Actuator

**Status:** Supported, needs reporter validation

This profile is for the Elda BTH / RF ECO BT / MEGAMAT setup from
[issue #344](https://github.com/kristofferR/ha-adjustable-bed/issues/344). It is
not a normal adjustable bed profile: it exposes one cover entity named `Stair`
for a moving staircase actuator.

The [ELDA-BTH product page](https://elda-treppen.de/produkt/bth/) describes the
system as a semi-automatic loft stair with a quiet maintenance-free spindle
motor, gas spring support, switch and/or radio remote control, and electrical
emergency lowering.

## Features

| Feature | Supported |
|---------|-----------|
| Stair actuator cover | Yes |
| Stop | Yes |
| Presets | No |
| Memory buttons | No |
| Lights | No |
| Massage | No |
| Position feedback | No |

## Setup

Use manual setup and choose **OKIN Smart Remote / RF ECO BT single actuator**.

The reported device advertises as `OKIN-050226` with no service UUIDs, so the
integration cannot safely auto-detect it from advertisements alone. Diagnostics
can identify it after connecting when this GATT signature is present:

- Service `62741523-52f9-8864-b1ab-3b3a8d65950b`
- Write characteristic `62741525-52f9-8864-b1ab-3b3a8d65950b`
- CSS service `90311623-25fa-3346-12ef-3cfb7a2556ac`
- CSS write characteristic `90311625-25fa-3346-12ef-3cfb7a2556ac`

If the same device also exposes Nordic DFU service
`00001530-1212-efde-1523-785feabcd123`, it may be a full bed controller using
[Okin CST](okin-cst.md), not this single-actuator stair profile.

Generic `OKIN-*` devices remain ambiguous because multiple unrelated OKIN
protocols use that naming pattern.

## Protocol

The local OKIN Smart Remote APK artifact is package `com.okin.okinsmartcomfort`.
Evidence used for this profile:

- `ApiService.java` returns RF-TOPLINE fallback actuator commands:
  - `M2Out`: `0x00000001`
  - `M2In`: `0x00000002`
  - `DisobeyStandbyTime`: `0x00000000`
- `HexValueConverter.java` encodes normal commands as `04 02` followed by the
  4-byte keycode.
- `BluetoothCharacteristics.java` defines the standard OKIN write
  characteristic `62741525-...` and the CSS characteristic `90311625-...` seen
  in the support bundle.

Packets:

| Action | Packet |
|--------|--------|
| Open / up | `04 02 00 00 00 01` |
| Close / down | `04 02 00 00 00 02` |
| Stop / release | `04 02 00 00 00 00` |

## Safety

This controls a moving staircase, not a bed. Automations should only run where
motion is safe, visible, and supervised.

## Follow-up

If M2 is not the correct actuator channel for a specific installation, a future
follow-up may need the reporter's OKIN Smart Remote ID or QR contents to map the
actual channel. Do not add M3, reversed, DOT, or RF-gateway variants without
new evidence.
