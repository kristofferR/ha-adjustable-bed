# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE). It replaces the broken `smartbed-mqtt` addon with a native HA integration that uses Home Assistant's Bluetooth stack directly.

**Current status:** 26 bed protocols implemented. Linak, Keeson, Richmat, MotoSleep, and Jensen tested. Other brands need community testing.

## Architecture

```
custom_components/adjustable_bed/
├── __init__.py          # Integration setup, platform loading, service registration
├── config_flow.py       # Device discovery and setup wizard
├── coordinator.py       # BLE connection management (central hub)
├── const.py             # Constants, UUIDs, bed type definitions, feature flags
├── entity.py            # Base entity class
├── adapter.py           # BLE adapter selection, device lookup
├── detection.py         # Bed type auto-detection from BLE services/names
├── controller_factory.py # Factory for creating bed controller instances
├── validators.py        # Config validation (MAC addresses, PIN, variants)
├── redaction.py         # Data redaction for diagnostics
├── support_report.py    # Support report generation
├── beds/                # Bed controller implementations
│   ├── base.py          # Abstract base class (BedController)
│   ├── linak.py         # Linak protocol (tested)
│   ├── richmat.py       # Richmat Nordic/WiLinke protocols (tested)
│   ├── keeson.py        # Keeson KSBT/BaseI4/I5/Ergomotion protocols (tested)
│   ├── motosleep.py     # MotoSleep HHC ASCII protocol (tested)
│   ├── solace.py        # Solace 11-byte packet protocol
│   ├── leggett_gen2.py  # Leggett & Platt Gen2 ASCII protocol
│   ├── leggett_okin.py  # Leggett & Platt Okin binary protocol
│   ├── leggett_wilinke.py # Leggett & Platt WiLinke 5-byte protocol
│   ├── reverie.py       # Reverie XOR checksum protocol
│   ├── okin_uuid.py     # Okin 6-byte via UUID protocol
│   ├── okin_handle.py   # Okin 6-byte via handle protocol
│   ├── okin_7byte.py    # Okin 7-byte protocol
│   ├── okin_nordic.py   # Okin 7-byte via Nordic UART
│   ├── okin_protocol.py # Shared Okin protocol utilities
│   ├── malouf.py        # Malouf NEW_OKIN/LEGACY_OKIN protocols
│   ├── jiecang.py       # Jiecang/Glide protocol
│   ├── serta.py         # Serta Motion Perfect III protocol
│   ├── octo.py          # Octo standard/Star2 protocols (PIN auth)
│   ├── jensen.py        # Jensen JMC400 protocol (tested, PIN auth)
│   ├── svane.py         # Svane LinonPI multi-service protocol
│   ├── bedtech.py       # BedTech 5-byte ASCII protocol
│   ├── okin_64bit.py    # OKIN 64-bit 10-byte protocol
│   ├── reverie_nightstand.py  # Reverie Protocol 110 (nightstand)
│   ├── sleepys.py       # Sleepy's Elite BOX15/BOX24 protocols
│   └── diagnostic.py    # Debug controller for unsupported beds
├── binary_sensor.py     # BLE connection status entity
├── button.py            # Preset and massage button entities
├── cover.py             # Motor control entities (open=up, close=down)
├── sensor.py            # Position angle feedback entities
├── switch.py            # Light control entities
├── diagnostics.py       # HA diagnostics download support
├── ble_diagnostics.py   # BLE protocol capture for new bed support
└── unsupported.py       # Unsupported device guidance (Repairs integration)
```

### Key Components

**AdjustableBedCoordinator** (`coordinator.py`): Central BLE connection manager
- Handles device discovery via HA's Bluetooth integration
- Connection retry with progressive backoff (3 attempts, 5-7.5s delays)
- Auto-disconnect after configurable idle time (default 40s)
- Registers conservative BLE connection parameters (30-50ms intervals)
- Supports preferred adapter selection for multi-proxy setups
- Command serialization via `_command_lock` prevents concurrent BLE writes
- `async_execute_controller_command()`: All entities use this for proper locking
- `async_stop_command()`: Cancels running command, acquires lock, then sends STOP
- Disconnect timer is cancelled during commands to prevent mid-command disconnects
- `_intentional_disconnect` flag prevents auto-reconnect after manual/idle disconnect

**BedController** (`beds/base.py`): Abstract interface all bed types must implement
- `write_command(command, repeat_count, repeat_delay_ms, cancel_event)`: Send command bytes
- `start_notify()` / `stop_notify()`: Position notification handling
- `read_positions()`: Read current motor positions
- Motor control methods: `move_head_up()`, `move_back_down()`, `move_legs_stop()`, etc.
- Preset methods: `preset_memory()`, `program_memory()`
- Optional features: `lights_on()`, `massage_toggle()`, etc.

**Config Flow** (`config_flow.py`):
- Automatic discovery via BLE service UUIDs and device name patterns
- Manual entry with bed type selection
- Per-device Bluetooth adapter/proxy selection
- Protocol variant selection where applicable
- Options flow for reconfiguration

**BLE Connection Binary Sensor** (`binary_sensor.py`):
- Shows real-time BLE connection state (device class: connectivity)
- Attributes: `last_connected`, `last_disconnected`, `connection_source`, `rssi`, `state_detail`
- Updates automatically when connection state changes

## Implemented Bed Types

| Brand | Controller | Protocol | Detection | Status |
|-------|------------|----------|-----------|--------|
| Linak | `LinakController` | 2-byte commands, write-with-response | Service UUID `99fa0001-...` | ✅ Tested |
| Richmat | `RichmatController` | Nordic (1-byte) or WiLinke (5-byte checksum) | Service UUIDs vary by variant | ✅ Tested |
| Keeson | `KeesonController` | KSBT (6-byte), BaseI4/I5 (8-byte XOR), or Ergomotion | Service UUID `0000ffe5-...` | ✅ Tested |
| MotoSleep | `MotoSleepController` | 2-byte ASCII `[$, char]` | Device name starts with "HHC" | ✅ Tested |
| Solace | `SolaceController` | 11-byte packets with built-in CRC | Service UUID `0000ffe0-...` | Needs testing |
| Leggett & Platt Gen2 | `LeggettGen2Controller` | Gen2 ASCII commands | Service UUID `45e25100-...` | Needs testing |
| Leggett & Platt Okin | `LeggettOkinController` | Okin binary protocol | Service UUID `62741523-...` + name | Needs testing |
| Leggett & Platt WiLinke | `LeggettWilinkeController` | WiLinke 5-byte protocol | Name prefix "MlRM*" | Needs testing |
| Reverie | `ReverieController` | XOR checksum, position-based motors | Service UUID `1b1d9641-...` | Needs testing |
| Okin UUID | `OkinUuidController` | Okin 6-byte via UUID, requires pairing | Service UUID `62741523-...` | Needs testing |
| Okin Handle | `OkinHandleController` | Okin 6-byte via handle (0x0013) | Name patterns | Needs testing |
| Okin 7-byte | `Okin7ByteController` | 7-byte via Okin service UUID | Service UUID `62741523-...` + name | Needs testing |
| Okin Nordic | `OkinNordicController` | 7-byte via Nordic UART | Service UUID `6e400001-...` | Needs testing |
| Serta | `SertaController` | Handle-based writes (0x0020) | Name patterns | Needs testing |
| Jiecang | `JiecangController` | Glide beds, Dream Motion app | Char UUID `0000ff01-...` | Needs testing |
| Octo | `OctoController` | Standard or Star2 variant, PIN auth | Service UUID `0000ffe0-...` or `0000aa5c-...` | Needs testing |
| Malouf NEW_OKIN | `MaloufController` | NEW_OKIN 6-byte protocol | Name patterns (Malouf, Lucid, CVB) | Needs testing |
| Malouf LEGACY_OKIN | `MaloufController` | LEGACY_OKIN 7-byte protocol | Name patterns (Malouf, Lucid, CVB) | Needs testing |
| Jensen | `JensenController` | 6-byte commands with PIN auth | Service UUID `00001234-...` or name "JMC*" | ✅ Tested |
| Svane | `SvaneController` | LinonPI multi-service 2-byte commands | Service UUID `0000abcb-...` or name "Svane Bed" | Needs testing |
| BedTech | `BedtechController` | 5-byte ASCII protocol | Service UUID `0000fee9-...` | Needs testing |
| Sleepy's BOX15 | `SleepysController` | 9-byte with checksum | Service UUID `0000ffe5-...` | Needs testing |
| Sleepy's BOX24 | `SleepysController` | 7-byte OKIN 64-bit | Service UUID `62741523-...` | Needs testing |
| Reverie Nightstand | `ReverieNightstandController` | Protocol 110 | Service UUID `db801000-...` | Needs testing |
| Okin 64-bit | `Okin64BitController` | 10-byte commands | Service UUID `62741523-...` | Needs testing |
| Diagnostic | `DiagnosticController` | Debug mode for unsupported beds | Manual selection only | Debug |

## Adding a New Bed Type

1. **Document the BLE protocol** - Use nRF Connect or the `run_diagnostics` service to capture GATT services, characteristics, and command bytes

2. **Add constants to `const.py`**:
   ```python
   BED_TYPE_NEWBED: Final = "newbed"
   NEWBED_SERVICE_UUID: Final = "..."
   NEWBED_CHAR_UUID: Final = "..."
   ```

3. **Create controller in `beds/`** (e.g., `newbed.py`):
   - Extend `BedController`
   - Implement all abstract methods
   - Define command bytes as a class (see existing controllers)

4. **Add detection to `detection.py`** in `detect_bed_type()`:

   ```python
   if NEWBED_SERVICE_UUID.lower() in service_uuids:
       return BED_TYPE_NEWBED
   ```

5. **Update `controller_factory.py`** `create_controller()`:

   ```python
   if bed_type == BED_TYPE_NEWBED:
       from .beds.newbed import NewbedController
       return NewbedController(coordinator)
   ```

6. **Add to `const.py`** `SUPPORTED_BED_TYPES` list

7. **Add to `manifest.json`** `bluetooth` array if using different service UUID for discovery

8. **Update `beds/__init__.py`** to export the new controller

9. **Create documentation** in `docs/beds/newbed.md`

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `motor_count` | 2, 3, or 4 motors | 2 |
| `has_massage` | Enable massage entities | false |
| `protocol_variant` | Protocol variant (bed-specific) | auto |
| `disable_angle_sensing` | Disable position feedback | true |
| `preferred_adapter` | Lock to specific BLE adapter | auto |
| `motor_pulse_count` | Command repeat count | 25 |
| `motor_pulse_delay_ms` | Delay between repeats | 50 |
| `disconnect_after_command` | Disconnect immediately after commands | false |
| `idle_disconnect_seconds` | Idle timeout before disconnect | 40 |
| `position_mode` | Speed vs accuracy tradeoff | speed |
| `octo_pin` | PIN for Octo beds | "" |
| `richmat_remote` | Remote code for Richmat beds | auto |

## Services

| Service | Description |
|---------|-------------|
| `adjustable_bed.goto_preset` | Move bed to memory position 1-4 |
| `adjustable_bed.save_preset` | Save current position to memory 1-4 |
| `adjustable_bed.stop_all` | Immediately stop all motors |
| `adjustable_bed.run_diagnostics` | Capture BLE protocol data for debugging |
| `adjustable_bed.generate_support_report` | Generate JSON support report with diagnostics (params: device_id, include_logs) |

## Critical Implementation Details

**IMPORTANT: Protocol values are hardware-specific.** Timing values (repeat counts, delays), command bytes, and packet formats vary between bed types. Do NOT copy values from one bed's protocol documentation to another. Each bed type's parameters must come from actual device testing or reverse engineering - never guess or extrapolate from other implementations.

1. **Always send STOP after movement** - Movement methods use `try/finally` to guarantee STOP is sent even if cancelled. The STOP command uses a fresh `asyncio.Event()` so it's not affected by the cancel signal.

2. **Command serialization** - All entities must use `coordinator.async_execute_controller_command()` instead of calling controller methods directly. This ensures proper locking and prevents concurrent BLE writes.

3. **Cancel event handling** - `write_command()` checks `coordinator._cancel_command` by default. When stop is requested, the cancel event is set, the running command exits early, then STOP is sent.

4. **Disconnect timer management** - Timer is cancelled when a command starts (inside the lock) and reset when it ends. This prevents mid-command disconnects for long operations.

5. **Intentional disconnect flag** - Set before `client.disconnect()`, checked in `_on_disconnect` to skip auto-reconnect. Cleared in finally block since callback may not fire on clean disconnects.

## Releases

When creating a release:

1. Update the version in **both** files:
   - `custom_components/adjustable_bed/manifest.json` - the `"version"` field
   - `pyproject.toml` - the `version` field in `[project]`

2. Commit, tag, and push:
   ```bash
   git commit -m "chore: Bump version to X.Y.Z"
   git tag vX.Y.Z
   git push && git push origin vX.Y.Z
   ```

3. Create a GitHub release with `gh release create` including a changelog with:
   - **What's New** - New features, new bed support
   - **Bug Fixes** - List of fixes with brief descriptions
   - **Upgrading** - Instructions (usually just "Update via HACS or manually replace folder")

## Development

### Testing in Home Assistant

1. Copy `custom_components/adjustable_bed` to your HA's `config/custom_components/`
2. Restart Home Assistant
3. Add debug logging to `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.adjustable_bed: debug
       homeassistant.components.bluetooth: debug
   ```

### Using BLE Diagnostics

The `run_diagnostics` service captures protocol data for debugging and adding new bed support:
1. Call the service with either a configured device or a raw MAC address
2. Operate the physical remote during the capture period
3. Find the JSON report in your HA config directory
4. The report contains GATT services, characteristics, and captured notifications

### Common Issues

- **Commands timeout**: Another device (app/remote) may be connected - beds only allow one BLE connection
- **Position sensing breaks physical remote**: Enable `disable_angle_sensing` option
- **Connection drops**: Move ESP32 proxy closer to bed, check for interference
- **Octo beds disconnect after 30s**: Configure the PIN in options

## Documentation

| File | Content |
|------|---------|
| `docs/SUPPORTED_ACTUATORS.md` | Which beds use which actuators, brand lookup |
| `docs/CONFIGURATION.md` | All configuration options explained |
| `docs/CONNECTION_GUIDE.md` | Bluetooth setup, ESPHome proxy configuration |
| `docs/TROUBLESHOOTING.md` | Common issues and solutions |
| `docs/beds/*.md` | Per-actuator protocol documentation |

## Reference Materials

- `smartbed-mqtt/` - Old Node.js addon (broken, but has protocol implementations for many bed types)
- `smartbed-mqtt-discord-chats/` - Discord exports with reverse-engineering discussions and user reports

## APK Reverse Engineering

The `disassembly/` folder contains tools and output from reverse engineering bed controller Android apps to extract BLE protocols.

See **[disassembly/AGENTS.md](disassembly/AGENTS.md)** for detailed instructions on:
- Decompiling APKs with jadx
- Analyzing Flutter apps with blutter
- Finding BLE UUIDs and command bytes
- Documenting protocol findings

**Folder structure:**
- `disassembly/apk/analyzed/` - APKs that have been analyzed
- `disassembly/apk/not-analyzed/` - APKs pending analysis
- `disassembly/output/<package_id>/` - Decompilation output per app (jadx/, blutter/, ANALYSIS.md)
