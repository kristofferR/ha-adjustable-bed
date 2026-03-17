# Kaidi

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Brands / Apps

- Rize Beds (`com.kaidi_test4.rize`)
- Floyd Home (`com.kaidi_test4.floyd`)
- ISleep (`com.kaidi_test4.isleep`)

These apps share the same Kaidi OEM transport and command family.

## Discovery And Transport

Kaidi beds are identified primarily by manufacturer data, not by advertised
service UUIDs.

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

The OEM APKs expose six control families that are now supported by one shared
`kaidi` bed type.

| Variant | Use |
|--------|-----|
| `seat_1` | Single-seat / lane 1 commands |
| `seat_2` | Single-seat / lane 2 commands |
| `seat_3` | Single-seat / lane 3 commands |
| `bed_1` | Split-bed lane 1 commands |
| `bed_2` | Split-bed lane 2 commands |
| `bed_12` | Split-bed combined commands |

### APK-backed product IDs

The OEM `MainActivity.getProductId()` logic only treats the following IDs as
explicit Kaidi bed products:

| Product IDs | Auto family |
|------------|-------------|
| `129`, `131`, `132`, `142` | `seat_1` |
| `130`, `133`, `134`, `143` | `bed_12` |

For other advertised `sofaType` values, the integration does not guess from the
number alone.

### `sofa_acu_no` heuristic

When the product ID is not one of the OEM `BED_TYPE` values, the integration
uses `sofa_acu_no` only for the narrow case the APK data supports cleanly:

- exactly one populated seat bar resolves to `seat_1`, `seat_2`, or `seat_3`

This is how issue `#247` style beds advertising `sofaType=136` are handled:
`136` is not in the OEM `BED_TYPE` list, but `sofa_acu_no=0x2004` resolves to a
single populated seat-1 profile, so the integration auto-selects `seat_1`.

If Kaidi metadata is present but does not map cleanly, `auto` refuses to guess
and a manual Kaidi variant override is required.

## Features By Family

| Feature | `seat_1` | `seat_2` | `seat_3` | `bed_1` | `bed_2` | `bed_12` |
|--------|----------|----------|----------|---------|---------|----------|
| Head/back + leg/foot movement | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Dedicated stop-all command | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Memory recall/programming | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Flat / Zero-G / Anti-Snore presets | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Massage / lights | Not exposed yet | Not exposed yet | Not exposed yet | Not exposed yet | Not exposed yet | Not exposed yet |

## Notes

1. The bed must already be provisioned in the official app. Home Assistant does not implement the add-device/reset workflow.
2. Kaidi devices named `Mouselet` are valid beds when the manufacturer payload matches Kaidi; the generic `"mouse"` exclusion no longer applies in that case.
3. If `auto` reports unresolved Kaidi metadata, switch the integration option to one of `seat_1`, `seat_2`, `seat_3`, `bed_1`, `bed_2`, or `bed_12`.
