# Supported Actuators

This document provides an overview of supported bed brands. Click on a brand name for detailed protocol information and command references.

| Brand | Status | Key Features |
|-------|--------|--------------|
| [Linak](beds/linak.md) | ✅ Supported | Position feedback, 4 memory presets, massage, lights |
| [Keeson](beds/keeson.md) | ✅ Supported | Position feedback (Ergomotion), 4 presets, massage, lights |
| [Richmat](beds/richmat.md) | ✅ Supported | 2 memory presets, massage, lights, Zero-G |
| [MotoSleep](beds/motosleep.md) | ✅ Supported | 2 memory presets, massage, lights, Zero-G |
| [Octo](beds/octo.md) | ✅ Supported | Two protocol variants, optional PIN auth, lights |
| [Solace](beds/solace.md) | ✅ Supported | 5 memory presets, lift/tilt, Zero-G |
| [Leggett & Platt](beds/leggett-platt.md) | ✅ Supported | 4 memory presets, massage (0-10), RGB lighting |
| [Reverie](beds/reverie.md) | ✅ Supported | Position control (0-100%), 4 presets, wave massage |
| [Okimat/Okin](beds/okimat.md) | ✅ Supported | 4 memory presets, massage, lights (requires pairing) |
| [Jiecang](beds/jiecang.md) | ✅ Supported | Presets only (no direct motor), 2 memory slots |
| [Jensen](beds/jensen.md) | ✅ Supported | 1 memory preset, dynamic feature detection (lights, massage) |
| [DewertOkin](beds/dewertokin.md) | ✅ Supported | 2 memory presets, wave massage, lights |
| [Serta](beds/serta.md) | ✅ Supported | Massage intensity control, Zero-G/TV/Lounge |
| [Mattress Firm 900](beds/mattressfirm.md) | ✅ Supported | Lumbar control, 3-level massage, built-in presets |
| [Nectar](beds/nectar.md) | ✅ Supported | Lumbar control, massage, lights, Zero-G/Anti-Snore/Lounge |
| [Malouf](beds/malouf.md) | ✅ Supported | 2 memory presets, lumbar, head tilt, massage, lights |
| [BedTech](beds/bedtech.md) | ✅ Supported | 5 presets, 4 massage modes, dual-base support |
| [Sleepy's Elite](beds/sleepys.md) | ✅ Supported | Lumbar (BOX15), Zero-G, Flat presets |
| [Svane](beds/svane.md) | ⚠️ Beta | LinonPI protocol, multi-service |
| [Vibradorm](beds/vibradorm.md) | 🧪 Needs Testing | Position feedback, 4 memory presets, lights |

---

## Configuration

For detailed configuration options including motor pulse settings, protocol variants, and bed-specific settings, see the [Configuration Guide](CONFIGURATION.md).

---

## Okin Protocol Family

Several bed brands use Okin-based BLE controllers. While they share common roots, each uses a different command format or write method:

| Bed Type | Command Format | Write Method | Pairing Required | Detection |
|----------|---------------|--------------|------------------|-----------|
| [Okimat](beds/okimat.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | Name patterns or fallback |
| [Okin 64-bit](beds/sleepys.md#box24-protocol-7-byte-packets) | 10-byte (64-bit cmd) | Nordic UART or UUID | ❌ No | Manual selection |
| [Leggett & Platt Okin](beds/leggett-platt.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | Name patterns |
| [Nectar](beds/nectar.md) | 7-byte (32-bit cmd) | UUID `62741525-...` | ❌ No | Name contains "nectar" |
| [DewertOkin](beds/dewertokin.md) | 6-byte (32-bit cmd) | Handle `0x0013` | ❌ No | Name patterns |
| [Mattress Firm 900](beds/mattressfirm.md) | 7-byte (32-bit cmd) | Nordic UART | ❌ No | Name starts with "iflex" |
| [Malouf](beds/malouf.md) | 8-byte (32-bit cmd) | Nordic UART or FFE5 | ❌ No | Service UUID detection |
| [Keeson/Ergomotion](beds/keeson.md) | 8-byte (32-bit cmd) | Nordic UART | ❌ No | Name patterns |

**Key differences:**
- **6-byte vs 7-byte vs 8-byte vs 10-byte**: Different command structures - not interchangeable
- **32-bit vs 64-bit commands**: Okin 64-bit uses 8-byte command values instead of 4-byte
- **UUID vs Handle**: DewertOkin writes to a BLE handle instead of a characteristic UUID
- **Nordic UART**: Many newer beds use the Nordic UART service

**If auto-detection picks the wrong type:** Go to Settings → Devices & Services → Adjustable Bed → Configure and change the bed type.

**Detection priority** (for beds with Okin service UUID):
1. Name contains "nectar" → Nectar
2. Name contains "leggett", "l&p", or "adjustable base" → Leggett & Platt Okin
3. Name contains "okimat", "okin rf", or "okin ble" → Okimat
4. Fallback → Okimat (with warning logged)

---

## Not Yet Supported

### Sleeptracker AI (Cloud-based)
- Tempur-Pedic Ergo series (cloud-connected models)
- Beautyrest SmartMotion (cloud-connected models)
- Serta Motion series (cloud-connected models)

**Reason:** Requires cloud API, not local BLE control.

### Logicdata (Local Network)
- Tempur-Pedic beds with Logicdata controllers
- Uses local UDP/HTTP protocol, not BLE

### ErgoWifi (Cloud-based)
- Beds using Xlink cloud platform
- Requires Chinese cloud API authentication

### Eight Sleep
Will not be implemented. Use the [Eight Sleep](https://github.com/lukas-clarke/eight_sleep) integration instead.

### Sleep Number
Will not be implemented. Use the [SleepIQ](https://www.home-assistant.io/integrations/sleepiq/) integration instead.

---

## Identifying Your Bed Type

1. **Check the remote or controller** for brand markings
2. **Scan for BLE devices** using nRF Connect app
3. **Look at device names:**
   - `HHC*` → MotoSleep
   - `DPG*` or `Desk*` → Linak
   - `Nectar*` → Nectar
   - `Okimat*`, `Okin RF*`, `Okin BLE*` → Okimat
   - `Leggett*`, `L&P*`, `Adjustable Base*` → Leggett & Platt
   - `Ergomotion*` or `Ergo*` → Keeson
   - `Jiecang*`, `JC-*`, or `Glide*` → Jiecang
   - `Dewert*`, `A H Beard*`, or `Hankook*` → DewertOkin
   - `Serta*` or `Motion Perfect*` → Serta
   - `Octo*` → Octo (Standard variant)
   - `iFlex*` → Mattress Firm 900
   - `Malouf*`, `Structures*` → Malouf
   - `Sleepy*` → Sleepy's Elite (try BOX24 first, BOX15 if lumbar needed)
   - `VMAT*` → Vibradorm
4. **Check service UUIDs** (using nRF Connect):
   - Service `62741523-...` → Okin family (see [Okin Protocol Family](#okin-protocol-family))
   - Service `45e25100-...` → Leggett & Platt Gen2
   - Service `0000aa5c-...` → Octo Star2 variant
   - Service `01000001-...` → Malouf (New OKIN)
   - Service `0000ffe5-...` → Malouf (Legacy OKIN) or Keeson OKIN variant
   - Service `0000fee9-...` → Richmat WiLinke or BedTech
   - Service `00001525-...` → Vibradorm

If your bed isn't auto-detected, use manual configuration and try different bed types.

---

## Credits

This integration relies heavily on protocol research from the [smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt) project by [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), which documented BLE protocols for many adjustable bed brands.

Community contributors who helped reverse-engineer specific protocols:

| Protocol | Contributors |
|----------|-------------|
| Richmat | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), getrav, [kristofferR](https://github.com/kristofferR) |
| Linak | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), jascdk |
| Solace | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), Bonopaws, [kristofferR](https://github.com/kristofferR) |
| MotoSleep | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), waynebowie99 |
| Reverie | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), Vitaliy, [kristofferR](https://github.com/kristofferR) |
| Leggett & Platt | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), MarcusW |
| Okimat | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), david_nagy, corne, PT, [kristofferR](https://github.com/kristofferR) |
| Keeson/Ergomotion | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), [kristofferR](https://github.com/kristofferR) |
| Octo | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), _pm, goedh452, Murp, Brokkert, [kristofferR](https://github.com/kristofferR) |
| Jiecang | [kristofferR](https://github.com/kristofferR) |
| Serta | [kristofferR](https://github.com/kristofferR) |
| Malouf | [kristofferR](https://github.com/kristofferR) |
| BedTech | [kristofferR](https://github.com/kristofferR) |
| Okin 64-bit | [kristofferR](https://github.com/kristofferR) |
| Sleepy's Elite | [kristofferR](https://github.com/kristofferR) |
| Jensen | [kristofferR](https://github.com/kristofferR) |
| Svane | [kristofferR](https://github.com/kristofferR) |
| Vibradorm | [kristofferR](https://github.com/kristofferR) |
| Mattress Firm 900 | [David Delahoz](https://github.com/daviddelahoz/BLEAdjustableBase) |
| Nectar | [MaximumWorf](https://github.com/MaximumWorf/homeassistant-nectar) |
