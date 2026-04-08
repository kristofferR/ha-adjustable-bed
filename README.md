<p align="center">
  <img src="docs/header.png" alt="Adjustable Bed Integration for Home Assistant">
</p>

<p align="center">
  <a href="https://github.com/kristofferR/ha-adjustable-bed/releases"><img src="https://img.shields.io/github/v/release/kristofferR/ha-adjustable-bed" alt="GitHub Release"></a>
  <a href="https://github.com/kristofferR/ha-adjustable-bed/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/kristofferR/ha-adjustable-bed/validate.yml?label=validation" alt="Validation"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-blue.svg" alt="HACS"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.10%2B-blue" alt="Home Assistant 2025.10+">
  <a href="https://github.com/sponsors/kristofferR"><img src="https://img.shields.io/badge/Sponsor-%E2%99%A1-ec6cb9" alt="Sponsor"></a>
</p>

<p align="center">
  A Home Assistant custom integration for controlling smart adjustable beds via Bluetooth.
</p>

## Quick Start

1. **Install** via [HACS](https://hacs.xyz): Search for "Adjustable Bed" and install
2. **Discover** your bed automatically, or add manually via Settings → Integrations
3. **Control** your bed from Home Assistant dashboards, automations, and voice assistants!

## Features

- **Motor Control** - Raise/lower head, back, legs, and feet
- **Direct Position Control** - Native 0-100 target controls on supported beds
- **Memory Presets** - Jump to saved positions with one tap
- **Under-bed Lights** - RGB color control on supported beds, toggle on/off on others
- **Climate Controls** - Cooling, heating, and footwarming on supported beds
- **Massage Control** - Adjust massage intensity and patterns
- **Position Feedback** - See current angles on supported beds
- **Presence Sensors** - Occupancy sensors on supported beds
- **Automations** - "Flat when leaving", "TV mode at 8pm", etc.

## Need Help?

| Guide | What's Inside |
|-------|---------------|
| **[Troubleshooting](docs/TROUBLESHOOTING.md)** | Connection issues, commands not working |
| **[Getting Help](docs/GETTING_HELP.md)** | Bug reports, support requests, diagnostics |
| **[Connection Guide](docs/CONNECTION_GUIDE.md)** | ESPHome proxy setup, finding your bed's address |
| **[Supported Actuators](docs/SUPPORTED_ACTUATORS.md)** | Protocol details, bed brand lookup |

| | |
|---|---|
| 💬 **[Ask a Question](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=q-a)** | Get help from the community |
| 💡 **[Suggest an Idea](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=ideas)** | Feature requests and improvements |
| ❤️ **[Praise and Feedback](https://github.com/kristofferR/ha-adjustable-bed/discussions/131)** | Share your experience or say thanks |

<details>
<summary><b>Quick troubleshooting</b></summary>

1. **Check range** - Bluetooth adapter or proxy within ~10m of bed
2. **Disconnect other apps** - Most beds allow only one BLE connection
3. **Reload integration** - Settings → Devices & Services → Adjustable Bed → Reload
4. **Enable debug logs** - Settings → Devices & Services → Adjustable Bed → ⋮ menu → Enable debug logging. Reproduce issue, then disable to download logs.

</details>

## Donate

If you love this integration, please consider [sending a thanks my way](https://github.com/sponsors/kristofferR).

## Supported Beds

The names below refer to motor/actuator manufacturers. Your bed might use one of these internally - check the [Supported Actuators guide](docs/SUPPORTED_ACTUATORS.md) to find your bed brand.

| Actuator | Example Brands |
|----------|----------------|
| ✅ [Linak](docs/beds/linak.md) | Tempur-Pedic, Bedre Nætter, Jensen |
| ✅ [Keeson](docs/beds/keeson.md) | Ergomotion, Tempur, Beautyrest, King Koil, Member's Mark, Purple, GhostBed, ErgoSportive |
| ✅ [Richmat](docs/beds/richmat.md) | Casper, MLILY, Sven & Son, Avocado, Luuna, Jerome's |
| ✅ [MotoSleep](docs/beds/motosleep.md) | HHC, Power Bob |
| ✅ [Octo](docs/beds/octo.md) | Octo |
| ✅ [Solace](docs/beds/solace.md) | Solace, Sealy, Woosa Sleep, QMS |
| ✅ [Leggett & Platt](docs/beds/leggett-platt.md) | Leggett & Platt |
| ✅ [Reverie](docs/beds/reverie.md) | Reverie |
| ✅ [Okimat/Okin](docs/beds/okimat.md) | Lucid, CVB, Smartbed |
| ✅ [Jiecang](docs/beds/jiecang.md) | Glideaway, Dream Motion, LOGICDATA |
| ✅ [Kaidi](docs/beds/kaidi.md) | Rize Remedy III / newer Mouselet-based Rize beds, Floyd Home, ISleep |
| ✅ [Limoss](docs/beds/limoss.md) | Limoss, Stawett |
| ✅ [Jensen](docs/beds/jensen.md) | Jensen (JMC400, LinON Entry) |
| ✅ [Svane](docs/beds/svane.md) | Svane |
| ✅ [DewertOkin](docs/beds/dewertokin.md) | Many older Rize models, Simmons, Nectar, Resident, Symphony |
| ✅ [Serta](docs/beds/serta.md) | Serta Motion Perfect |
| ✅ [Mattress Firm 900](docs/beds/mattressfirm.md) | Mattress Firm, iFlex |
| ✅ [Nectar](docs/beds/nectar.md) | Nectar |
| ✅ [Malouf](docs/beds/malouf.md) | Malouf, Structures |
| ✅ [BedTech](docs/beds/bedtech.md) | BedTech |
| 🧪 [Sleep Number](docs/beds/sleep_number.md) | Climate 360, FlexFit, FlexFit Smart |
| ✅ [Sleepy's Elite](docs/beds/sleepys.md) | Sleepy's |
| ✅ [Vibradorm](docs/beds/vibradorm.md) | Vibradorm |
| ✅ [SUTA Smart Home](docs/beds/suta.md) | SUTA |
| ✅ [TiMOTION AHF](docs/beds/timotion-ahf.md) | TiMOTION |
| ✅ [Rondure](docs/beds/rondure.md) | 1500 Tilt Base |
| ✅ [Remacro](docs/beds/remacro.md) | CheersSleep, Jeromes, Slumberland, The Brick |
| ✅ [Cool Base](docs/beds/coolbase.md) | Cool Base (Keeson with fan) |
| ✅ [Scott Living](docs/beds/scott-living.md) | Scott Living |
| ✅ [SBI/Q-Plus](docs/beds/sbi.md) | Q-Plus (Costco) |
| ✅ [Logicdata](docs/beds/logicdata.md) | SILVERmotion, SimplicityFrame |
| ✅ [Okin CB35](docs/beds/okin-cb35.md) | Sealy Posturematic |
| ✅ [Okin CST](docs/beds/okin-cst.md) | Rize MF900 |

**Have one of these?** [Let us know](https://github.com/kristofferR/ha-adjustable-bed/issues) how well it works!

Some brands span multiple controller families. For example, many older Rize beds are DewertOkin, while newer `Mouselet`-advertising Rize beds use [Kaidi](docs/beds/kaidi.md).

## Will This Work With My Bed?

**Just try it!** The integration auto-detects most beds. Install it and see if your bed shows up.

**Didn't auto-detect?** Check the [Supported Actuators guide](docs/SUPPORTED_ACTUATORS.md) to find your bed's actuator brand, then add it manually.

**Still stuck?** [Open an issue](https://github.com/kristofferR/ha-adjustable-bed/issues) with your bed brand/model and we'll help!

**Other beds:** [Eight Sleep](https://github.com/lukas-clarke/eight_sleep) still has its own integration. Sleep Number Climate 360 / FlexFit BLE bases are supported here; see the [Sleep Number guide](docs/beds/sleep_number.md).

**WiFi and cloud-based beds [won't be supported](https://github.com/kristofferR/ha-adjustable-bed/issues/167)** — this is a Bluetooth-only integration for the reasons stated in the link.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Search for "Adjustable Bed"
3. Click Install
4. Restart Home Assistant

### Manual

Copy `custom_components/adjustable_bed` to your `config/custom_components/` directory and restart.

## Configuration

Your bed should auto-discover via Bluetooth. If not:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Adjustable Bed"
3. Enter your bed's Bluetooth address or select from discovered devices

To adjust settings after setup, click the **gear icon** on your device in Settings → Devices & Services.

<details>
<summary><b>Quick reference</b></summary>

| Setting | Description |
|---------|-------------|
| Motor Count | 2 (back/legs), 3 (adds head), or 4 (adds feet) |
| Has Massage | Enable if your bed has massage |
| Protocol Variant | Usually auto-detected, override if needed |
| Motor Pulse Settings | Fine-tune movement timing |
| Disable Angle Sensing | Keep on to allow physical remote to work |
| Jensen PIN | 4-digit PIN for Jensen beds (default: 3060) |
| Octo PIN | 4-digit PIN for Octo beds that require authentication |
| Richmat Remote | Remote model code for Richmat beds |

See the [Configuration Guide](docs/CONFIGURATION.md) for all options.

</details>

## Bluetooth Setup

Works with Home Assistant's native Bluetooth:
- **Local adapter** on your HA host
- **[ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html)** for extended range

See the [Connection Guide](docs/CONNECTION_GUIDE.md) for setup help.

## Contributing

**We'd love your help!** This integration is actively developed and we're especially looking for:

- **Testers** - Own a bed we haven't fully tested? Your feedback is invaluable
- **Bug reports** - Found something wrong? [Open an issue](https://github.com/kristofferR/ha-adjustable-bed/issues)
- **Code contributions** - PRs welcome!


## Credits

Massive thanks to the [smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt) developers for their pioneering work reverse-engineering bed protocols!

<details>
<summary><b>Migrating from smartbed-mqtt?</b></summary>

This integration replaces smartbed-mqtt with several advantages:
- Uses Home Assistant's native Bluetooth (no ESPHome API issues)
- Works seamlessly with ESPHome Bluetooth proxies
- No MQTT broker required
- Native HA entities

To migrate: Install this integration, configure your bed, verify it works, then remove smartbed-mqtt.

</details>

## License

MIT License - see [LICENSE](LICENSE) for details.
