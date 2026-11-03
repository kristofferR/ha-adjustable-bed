# Kaidi

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Brands / Apps

- Rize Beds (`com.kaidi_test4.rize`)
- Floyd Home (`com.kaidi_test4.floyd`)
- ISleep (`com.kaidi_test4.isleep`)

Floyd Home now has a separately audited [product 139 profile](floyd.md).
Its capabilities and control behavior come from its accepted artifact, not from
other apps sharing this transport. The remaining sections describe the legacy
Seat profiles unless stated otherwise.

## Discovery And Transport

Kaidi beds are identified primarily by manufacturer data, not by advertised
service UUIDs.

> **PairLink caveat:** the `0xFFFF`/`0xC0FF` manufacturer blob is the PairLink
> mesh SDK transport (`com.pairlink.mesh_lib` in the OEM APKs), which non-bed
> products — notably BLE mesh LED controllers — also emit. An ESPHome ESP32-C6
> LED controller advertising a structurally valid PairLink payload was
> misdetected as a Kaidi bed (issue #417); the OEM app's own scan validation
> accepts that payload too and filters on mesh room-ID membership, which the
> integration cannot replicate. Detection therefore requires a corroborating
> Kaidi signal — the `Mouselet` name, the FFC0/mesh service UUID, or a known
> Kaidi MAC OUI — alongside a parseable payload. The separately audited Floyd
> product 139 signature can also admit a bed without those shared signals.

| Signal | Value |
|--------|-------|
| Manufacturer data company ID | `0xFFFF` in Home Assistant advertisements |
| Manufacturer data marker | `0xC0FF` |
| Common device name | `Mouselet` |
| Known MAC OUIs in OEM app | `00:95:69`, `F0:AC:D7` |
| Connected GATT service | `9e5d1e47-5c13-43a0-8635-82adffc0386f` |
| Write characteristic | `9e5d1e47-5c13-43a0-8635-82adffc1386f` |
| Notify characteristic | `9e5d1e47-5c13-43a0-8635-82adffc2386f` |

Supported advertisement layouts:

- `0x01`: single-bed payload with `room_id`
- `0x02`: broadcast payload with `room_id` and `vAddr`
- `0x09`: discoverable/add-device payload

The integration caches the following Kaidi metadata in the config entry when it
can see a valid advertisement:

- `room_id`
- `vaddr`
- `product_id` (from advertised `sofaType`)
- `sofa_acu_no`
- advertisement type
- resolved Kaidi variant and the source used to resolve it

## Session Setup

Home Assistant follows the same bootstrap flow as the OEM apps:

1. Parse manufacturer data to recover the room/home ID and any advertised `vAddr`
2. Send the Kaidi join packet with ASCII password `"1122"`
3. Use the advertised `vAddr`, or ping to discover it if only a single-bed advertisement is visible
4. Send 4-byte control payloads wrapped in Kaidi's mesh-style GATT frame

## Command Families

The integration exposes the Floyd app profile and four legacy Seat variants
under the shared `kaidi` bed type.
The current implementation uses the OEM apps' Seat commands; the old `bed_1`,
`bed_2`, and `bed_12` choices are not current variants.

| Variant | Use |
|---------|-----|
| `floyd` | Floyd Home product 139, see [dedicated guide](floyd.md) |
| `seat_1` | Single-base / lane 1 commands |
| `seat_2` | Lane 2 commands |
| `seat_3` | Lane 3 commands |
| `seat_1_2` | Dual base, sends the matching Seat 1 and Seat 2 commands |

### APK-backed product IDs

The resolver recognizes these product IDs from Rize 1.3.0, ISleep 1.6.3,
and Floyd 1.0.7:

| Product IDs | Auto family |
|-------------|-------------|
| `129`, `131`, `132`, `135`, `136`, `137`, `138`, `142` | `seat_1` |
| `130`, `133`, `134`, `143` | `seat_1_2` |
| `139` | `floyd` |

IDs `140` and `141` are not in those app versions and are not inferred from
neighboring values. Other IDs use the narrow fallback below or require an
explicit variant.

### `sofa_acu_no` heuristic

When the product ID is not one of the OEM `BED_TYPE` values, the integration
uses `sofa_acu_no` only for the narrow case the APK data supports cleanly:

- exactly one populated seat bar resolves to `seat_1`, `seat_2`, or `seat_3`

Product `136` (Remedy 4, including the issue #247 report) now resolves directly
from its recognized product ID, rather than relying on this fallback.

If Kaidi metadata is present but does not map cleanly, `auto` refuses to guess
and a manual Kaidi variant override is required.

## Features By Family

- The legacy Seat variants expose core movement and four memory recall/save slots.
- Floyd exposes three slots, a corrected Flat/release mapping, light controls and
  confirmed built-in preset programming. It has no direct position or massage controls.
- Seat 1, Seat 2, and Seat 1+2 expose Flat, Zero G, Anti-Snore, direct back/legs
  percentage targets, and massage start/stop and 15/30/45-minute timers. Massage
  entities also require **Has massage** in configuration.
- Product metadata gates extra axes, lights, and Book/Leisure presets. Unknown
  products retain the basic layout rather than gaining every optional feature.
- Seat 3 has a more limited command set, including lumbar movement, without
  direct position targets or the Seat 1/2 named presets and massage controls.
- Direct targets are commands, not measured position feedback; an accepted target
  must not be interpreted as confirmation that the bed reached it.

The current mappings and capability gates are in
[`kaidi_variants.py`](../../custom_components/adjustable_bed/kaidi_variants.py) and
[`beds/kaidi.py`](../../custom_components/adjustable_bed/beds/kaidi.py), with
[focused tests](../../tests/test_kaidi.py). This documents the shipped
implementation, not new physical validation.

### Single-address paired controls

Only `seat_1_2` can opt into **Enable Left / Right / Both controls** in the entry's
options. Left binds Seat 1, Right binds Seat 2, and Both retains the dual-command
behavior over the same Bluetooth connection. Other Kaidi variants remain
standalone. See [paired-side configuration](../CONFIGURATION.md#single-address-left--right-controls).

## Notes

1. The bed must already be provisioned in the official app. Home Assistant does not implement the add-device/reset workflow.
2. Kaidi devices named `Mouselet` are valid beds when the manufacturer payload matches Kaidi; the generic `"mouse"` exclusion no longer applies in that case.
3. If `auto` reports unresolved Kaidi metadata, switch the integration option to the verified layout: `seat_1`, `seat_2`, `seat_3`, or `seat_1_2`.
