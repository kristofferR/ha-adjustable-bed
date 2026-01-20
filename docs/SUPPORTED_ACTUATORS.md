# Supported Actuators

This document provides an overview of supported bed brands. Click on a brand name for detailed protocol information and command references.

| Brand | Status | Key Features |
|-------|--------|--------------|
| [Linak](beds/linak.md) | ✅ Tested | Position feedback, 4 memory presets, massage, lights |
| [Keeson](beds/keeson.md) | ✅ Tested | Position feedback (Ergomotion), 4 presets, massage, lights |
| [MotoSleep](beds/motosleep.md) | 🔄 Works | 2 memory presets, massage, lights, Zero-G |
| [Richmat](beds/richmat.md) | 🔄 Works | 2 memory presets, massage, lights, Zero-G |
| [Octo](beds/octo.md) | 🔄 Works | Two protocol variants, optional PIN auth, lights |
| [Solace](beds/solace.md) | ❓ Untested | 5 memory presets, lift/tilt, Zero-G |
| [Leggett & Platt](beds/leggett-platt.md) | ❓ Untested | 4 memory presets, massage (0-10), RGB lighting |
| [Reverie](beds/reverie.md) | ❓ Untested | Position control (0-100%), 4 presets, wave massage |
| [Okimat/Okin](beds/okimat.md) | ❓ Untested | 4 memory presets, massage, lights (requires pairing) |
| [Jiecang](beds/jiecang.md) | ❓ Untested | Presets only (no direct motor), 2 memory slots |
| [DewertOkin](beds/dewertokin.md) | ❓ Untested | 2 memory presets, wave massage, lights |
| [Serta](beds/serta.md) | ❓ Untested | Massage intensity control, Zero-G/TV/Lounge |
| [Mattress Firm 900](beds/mattressfirm.md) | ❓ Untested | Lumbar control, 3-level massage, built-in presets |
| [Nectar](beds/nectar.md) | ❓ Untested | Lumbar control, massage, lights, Zero-G/Anti-Snore/Lounge |

## Status Legend

- ✅ **Tested** - Confirmed working by community members
- 🔄 **Works** - Working but may have improvements in progress
- ❓ **Untested** - Implemented based on protocol documentation, needs testing

---

## Configuration

For detailed configuration options including motor pulse settings, protocol variants, and bed-specific settings, see the [Configuration Guide](CONFIGURATION.md).

---

## Okin Protocol Family

Several bed brands use Okin-based BLE controllers. While they share common roots, each uses a different command format or write method:

| Bed Type | Command Format | Write Method | Pairing Required | Detection |
|----------|---------------|--------------|------------------|-----------|
| [Okimat](beds/okimat.md) | 6-byte binary | UUID `62741525-...` | ✅ Yes | Name patterns or fallback |
| [Leggett & Platt Okin](beds/leggett-platt.md) | 6-byte binary | UUID `62741525-...` | ✅ Yes | Name patterns |
| [Nectar](beds/nectar.md) | 7-byte binary | UUID `62741525-...` | ❌ No | Name contains "nectar" |
| [DewertOkin](beds/dewertokin.md) | 6-byte binary | Handle `0x0013` | ❌ No | Name patterns |
| [Mattress Firm 900](beds/mattressfirm.md) | 7-byte binary | Nordic UART | ❌ No | Name starts with "iflex" |

**Key differences:**
- **6-byte vs 7-byte**: Different command structures - not interchangeable
- **UUID vs Handle**: DewertOkin writes to a BLE handle instead of a characteristic UUID
- **Nordic UART**: Mattress Firm uses a completely different BLE service

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
   - `Ergomotion*` or `Ergo*` → Ergomotion (use Keeson)
   - `Jiecang*`, `JC-*`, or `Glide*` → Jiecang
   - `Dewert*`, `A H Beard*`, or `Hankook*` → DewertOkin
   - `Serta*` or `Motion Perfect*` → Serta
   - `Octo*` → Octo (Standard variant)
   - `iFlex*` → Mattress Firm 900
4. **Check service UUIDs** (using nRF Connect):
   - Service `62741523-...` → Okin family (see [Okin Protocol Family](#okin-protocol-family))
   - Service `45e25100-...` → Leggett & Platt Gen2
   - Service `0000aa5c-...` → Octo Star2 variant

If your bed isn't auto-detected, use manual configuration and try different bed types.

---

## Credits

This integration relies heavily on protocol research from the [smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt) project by [Richard Hopton](https://github.com/richardhopton), which documented BLE protocols for many adjustable bed brands.

Community contributors who helped reverse-engineer specific protocols:

| Protocol | Contributors |
|----------|-------------|
| Richmat | getrav |
| Linak | jascdk |
| Solace | Bonopaws |
| MotoSleep | waynebowie99 |
| Reverie | Vitaliy |
| Leggett & Platt | MarcusW |
| Okimat | david_nagy, corne, PT |

Additional contributions:
- **Mattress Firm 900**: [David Delahoz](https://github.com/daviddelahoz) - [BLEAdjustableBase](https://github.com/daviddelahoz/BLEAdjustableBase)
- **Nectar**: [MaximumWorf](https://github.com/MaximumWorf) - [homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar)
- **Octo**: [_pm](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10), Murp, [Brokkert](https://github.com/Brokkert)
