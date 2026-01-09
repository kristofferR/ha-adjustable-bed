# Smart Bed Home Assistant Integration

A Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE).

## Supported Beds

### Currently Implemented
- **Linak** - Full support for Linak-based adjustable beds

### Planned
- Richmat
- Solace
- MotoSleep
- Reverie
- Leggett & Platt (Okin and Richmat variants)
- Okimat
- Keeson
- Octo
- Sleeptracker AI (cloud-based: Tempur Ergo, BeautyRest, Serta)

## Features

### Linak Beds

- **Motor Control**: Control head, back, legs, and feet positions (depending on motor count)
- **Memory Presets**: 4 programmable memory positions
- **Under-Bed Lights**: On/Off control
- **Massage** (if equipped): Head and foot massage with intensity control
- **Position Feedback**: Real-time angle sensors for beds that support it

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu and select "Custom repositories"
3. Add this repository URL with category "Integration"
4. Search for "Smart Bed" and install
5. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/smartbed` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

### Automatic Discovery

The integration will automatically discover Linak beds via Bluetooth. When discovered:

1. Go to **Settings** → **Devices & Services**
2. You should see a notification about a discovered Smart Bed
3. Click **Configure** and follow the setup wizard

### Manual Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Smart Bed"
4. Enter the Bluetooth address manually or select from discovered devices
5. Configure:
   - **Name**: Friendly name for your bed
   - **Motor Count**: Number of motors (2, 3, or 4)
   - **Has Massage**: Whether your bed has massage functionality

## Bluetooth Setup

This integration uses Home Assistant's native Bluetooth stack, which supports:

- **Local Bluetooth**: Built-in Bluetooth adapter on your HA host
- **ESPHome Bluetooth Proxy**: ESP32 devices running ESPHome as Bluetooth proxies

### ESPHome Bluetooth Proxy

Unlike the old smartbed-mqtt addon, this integration works seamlessly with ESPHome Bluetooth proxies because it uses Home Assistant's Bluetooth stack directly. No need for dedicated proxies!

## Entities

### Cover Entities (Motor Control)

| Entity | Description | Requirements |
|--------|-------------|--------------|
| `cover.<name>_back` | Back/upper body section | 2+ motors |
| `cover.<name>_legs` | Leg section | 2+ motors |
| `cover.<name>_head` | Head section | 3+ motors |
| `cover.<name>_feet` | Feet section | 4 motors |

### Button Entities

| Entity | Description |
|--------|-------------|
| `button.<name>_preset_memory_1` | Go to Memory 1 position |
| `button.<name>_preset_memory_2` | Go to Memory 2 position |
| `button.<name>_preset_memory_3` | Go to Memory 3 position |
| `button.<name>_preset_memory_4` | Go to Memory 4 position |
| `button.<name>_program_memory_*` | Save current position to memory |
| `button.<name>_stop` | Stop all motors |
| `button.<name>_massage_*` | Massage controls (if equipped) |

### Sensor Entities

| Entity | Description | Requirements |
|--------|-------------|--------------|
| `sensor.<name>_back_angle` | Back section angle | 2+ motors |
| `sensor.<name>_leg_angle` | Leg section angle | 2+ motors |
| `sensor.<name>_head_angle` | Head section angle | 3+ motors |
| `sensor.<name>_feet_angle` | Feet section angle | 4 motors |

### Switch Entities

| Entity | Description |
|--------|-------------|
| `switch.<name>_under_bed_lights` | Under-bed lighting |

## Troubleshooting

For detailed troubleshooting steps, see the [Connection Guide](docs/CONNECTION_GUIDE.md).

### Quick Fixes

1. **Check Bluetooth range**: Ensure your Bluetooth adapter or ESPHome proxy is within range
2. **Disconnect manufacturer app**: Most beds only allow one BLE connection
3. **Restart the integration**: Go to Settings → Devices & Services → Smart Bed → Reload
4. **Check logs**: Enable debug logging for `custom_components.smartbed`

### Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smartbed: debug
    homeassistant.components.bluetooth: debug
```

## Documentation

- [Connection Guide](docs/CONNECTION_GUIDE.md) - Detailed setup and troubleshooting
- [ESPHome Bluetooth Proxy Setup](docs/CONNECTION_GUIDE.md#setting-up-an-esphome-bluetooth-proxy)
- [Identifying Your Bed](docs/CONNECTION_GUIDE.md#identifying-your-bed)
- [Technical Protocol Details](docs/CONNECTION_GUIDE.md#technical-details)

## Migration from smartbed-mqtt

If you're migrating from the smartbed-mqtt addon:

1. Install this integration
2. Configure your bed(s)
3. Test that everything works
4. Disable/remove the smartbed-mqtt addon
5. Delete old MQTT entities if desired

**Key Differences from smartbed-mqtt:**
- Uses Home Assistant's native Bluetooth stack (no ESPHome API compatibility issues!)
- Works seamlessly with ESPHome Bluetooth proxies
- No MQTT broker required
- Native Home Assistant entities instead of MQTT discovery

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Adding Support for New Bed Types

1. Capture BLE traffic using nRF Connect or similar
2. Document the GATT services and characteristics
3. Implement a new controller in `beds/`
4. Add bed detection to `config_flow.py`

See [Technical Details](docs/CONNECTION_GUIDE.md#technical-details) for protocol documentation format.

## License

This project is licensed under the MIT License.
