# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE). It replaces the broken `smartbed-mqtt` addon with a native HA integration that uses Home Assistant's Bluetooth stack directly.

**Current status:** 15 bed types implemented. Linak, Keeson, Richmat, and MotoSleep tested. Other brands need community testing.

## Architecture

```
custom_components/adjustable_bed/
├── __init__.py          # Integration setup, platform loading, service registration
├── config_flow.py       # Device discovery and setup wizard
├── coordinator.py       # BLE connection management (central hub)
├── const.py             # Constants, UUIDs, bed type definitions, feature flags
├── entity.py            # Base entity class
├── beds/                # Bed controller implementations
│   ├── base.py          # Abstract base class (BedController)
│   ├── linak.py         # Linak protocol (tested)
│   ├── richmat.py       # Richmat Nordic/WiLinke protocols (tested)
│   ├── keeson.py        # Keeson KSBT/BaseI4/I5/Ergomotion protocols (tested)
│   ├── motosleep.py     # MotoSleep HHC ASCII protocol (tested)
│   ├── solace.py        # Solace 11-byte packet protocol
│   ├── leggett_platt.py # Leggett & Platt Gen2/Okin protocols
│   ├── reverie.py       # Reverie XOR checksum protocol
│   ├── okimat.py        # Okimat/Okin binary protocol
│   ├── jiecang.py       # Jiecang/Glide protocol
│   ├── dewertokin.py    # DewertOkin handle-based protocol
│   ├── serta.py         # Serta Motion Perfect III protocol
│   ├── octo.py          # Octo standard/Star2 protocols (PIN auth)
│   ├── mattressfirm.py  # Mattress Firm 900 7-byte protocol
│   ├── nectar.py        # Nectar 7-byte protocol
│   └── okin_protocol.py # Shared Okin protocol utilities
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

## Implemented Bed Types

| Brand | Controller | Protocol | Detection | Status |
|-------|------------|----------|-----------|--------|
| Linak | `LinakController` | 2-byte commands, write-with-response | Service UUID `99fa0001-...` | ✅ Tested |
| Richmat | `RichmatController` | Nordic (1-byte) or WiLinke (5-byte checksum) | Service UUIDs vary by variant | ✅ Tested |
| Keeson | `KeesonController` | KSBT (6-byte), BaseI4/I5 (8-byte XOR), or Ergomotion | Service UUID `0000ffe5-...` | ✅ Tested |
| MotoSleep | `MotoSleepController` | 2-byte ASCII `[$, char]` | Device name starts with "HHC" | ✅ Tested |
| Solace | `SolaceController` | 11-byte packets with built-in CRC | Service UUID `0000ffe0-...` | Needs testing |
| Leggett & Platt | `LeggettPlattController` | Gen2 (ASCII) or Okin (binary) | Service UUID `45e25100-...` (Gen2) | Needs testing |
| Reverie | `ReverieController` | XOR checksum, position-based motors | Service UUID `1b1d9641-...` | Needs testing |
| Okimat | `OkimatController` | Okin binary, multiple remote variants | Service UUID `62741523-...` | Needs testing |
| Jiecang | `JiecangController` | Glide beds, Dream Motion app | Char UUID `0000ff01-...` | Needs testing |
| DewertOkin | `DewertOkinController` | Handle-based writes (0x0013) | Name patterns | Needs testing |
| Serta | `SertaController` | Handle-based writes (0x0020) | Name patterns | Needs testing |
| Octo | `OctoController` | Standard or Star2 variant, PIN auth | Service UUID `0000ffe0-...` or `0000aa5c-...` | Needs testing |
| Mattress Firm | `MattressFirmController` | 7-byte Nordic UART protocol | Service UUID `6e400001-...` | Needs testing |
| Nectar | `NectarController` | 7-byte protocol (similar to MF900) | Service UUID `62741523-...` + name | Needs testing |

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

4. **Add detection to `config_flow.py`** in `detect_bed_type()`:
   ```python
   if NEWBED_SERVICE_UUID.lower() in service_uuids:
       return BED_TYPE_NEWBED
   ```

5. **Update `coordinator.py`** `_create_controller()`:
   ```python
   if self._bed_type == BED_TYPE_NEWBED:
       from .beds.newbed import NewbedController
       return NewbedController(self)
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

## Linak BLE Protocol Reference

```
Control Service:   99fa0001-338a-1024-8a49-009c0215f78a
  Write Char:      99fa0002-338a-1024-8a49-009c0215f78a
  Write Mode:      WITH RESPONSE (response=True) - bed expects acknowledgment

Command format: [command_byte, 0x00]

Motor commands:
  0x0B/0x0A = back up/down
  0x09/0x08 = legs up/down
  0x03/0x02 = head up/down
  0x05/0x04 = feet up/down
  0x00 = stop all

Motor timing:
  - 15 repeats at 100ms intervals (1.5 seconds total movement)
  - Send STOP (0x00) after movement using try/finally with fresh asyncio.Event()

Presets:
  0x0E, 0x0F, 0x0C, 0x44 = Memory 1-4
  0x38, 0x39, 0x3A, 0x45 = Program Memory 1-4

Preset timing:
  - 100 repeats at 300ms intervals (30 seconds for full preset movement)
  - NO stop command needed after presets

Single-shot commands (1 write, no repeat):
  - Lights: 0x92 (on), 0x93 (off), 0x94 (toggle)
  - Program memory: 0x38-0x3A, 0x45
  - Massage controls: all massage commands

Position Service: 99fa0020-338a-1024-8a49-009c0215f78a
  Back:  99fa0028 (max 820 raw = 68°)
  Legs:  99fa0027 (max 548 raw = 45°)
  Head:  99fa0026 (3+ motors)
  Feet:  99fa0025 (4 motors)

Position data format:
  - Little-endian 16-bit: raw = data[0] | (data[1] << 8)
  - Angle = max_angle * (raw / max_raw)
```

## Critical Implementation Details

1. **Write with response** - Use `response=True` for all GATT writes. The bed expects write-with-response.

2. **Always send STOP after movement** - Movement methods use `try/finally` to guarantee STOP is sent even if cancelled. The STOP command uses a fresh `asyncio.Event()` so it's not affected by the cancel signal.

3. **Command serialization** - All entities must use `coordinator.async_execute_controller_command()` instead of calling controller methods directly. This ensures proper locking and prevents concurrent BLE writes.

4. **Cancel event handling** - `write_command()` checks `coordinator._cancel_command` by default. When stop is requested, the cancel event is set, the running command exits early, then STOP is sent.

5. **Disconnect timer management** - Timer is cancelled when a command starts (inside the lock) and reset when it ends. This prevents mid-command disconnects for long operations.

6. **Presets are long operations** - 100 repeats × 300ms = 30 seconds max. Idle timeout is 40s.

7. **Intentional disconnect flag** - Set before `client.disconnect()`, checked in `_on_disconnect` to skip auto-reconnect. Cleared in finally block since callback may not fire on clean disconnects.

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
