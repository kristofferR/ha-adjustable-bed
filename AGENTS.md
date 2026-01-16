# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE). It replaces the broken `smartbed-mqtt` addon with a native HA integration that uses Home Assistant's Bluetooth stack directly, avoiding the ESPHome Native API compatibility issues that broke the old addon.

**Current status:** All major BLE bed types implemented. Linak beds fully tested. Other brands need community testing.

## Why the Old Integration Broke

The `smartbed-mqtt` addon (in the `smartbed-mqtt/` folder) broke due to:

1. **ESPHome 2023.6.0+**: BLE proxy became single-client only - HA's ESPHome integration would block smartbed-mqtt from receiving BLE advertisements
2. **ESPHome 2025.5.0+**: New Native API messages (especially `BluetoothScannerStateResponse` id 126) crash the `@2colors/esphome-native-api` JS library

See `smartbed-mqtt-discord-chats/esphome-bug-llm-generated.md` for detailed documentation.

**The new integration solves this** by using HA's native Bluetooth stack (bleak) instead of ESPHome's Native API.

## Architecture

```
custom_components/adjustable_bed/
├── __init__.py          # Integration setup, platform loading
├── config_flow.py       # Device discovery and setup wizard
├── coordinator.py       # BLE connection management (central hub)
├── const.py             # Constants, UUIDs, bed type definitions
├── entity.py            # Base entity class
├── beds/                # Bed controller implementations
│   ├── base.py          # Abstract base class (BedController)
│   ├── linak.py         # Linak protocol (tested)
│   ├── richmat.py       # Richmat Nordic/WiLinke protocols
│   ├── keeson.py        # Keeson KSBT/BaseI4/I5 protocols
│   ├── solace.py        # Solace 11-byte packet protocol
│   ├── motosleep.py     # MotoSleep HHC ASCII protocol
│   ├── leggett_platt.py # Leggett & Platt Gen2/Okin protocols
│   ├── reverie.py       # Reverie XOR checksum protocol
│   └── okimat.py        # Okimat/Okin binary protocol
├── button.py            # Preset and massage button entities
├── cover.py             # Motor control entities (open=up, close=down)
├── sensor.py            # Position angle feedback entities
└── switch.py            # Light control entities
```

### Key Components

**AdjustableBedCoordinator** (`coordinator.py`): Central BLE connection manager
- Handles device discovery via HA's Bluetooth integration
- Connection retry with progressive backoff (3 attempts, 5-7.5s delays)
- Auto-disconnect after 40s idle (allows physical remote/app to connect)
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
- Automatic discovery via BLE service UUIDs
- Manual entry with bed type selection
- Per-device Bluetooth adapter/proxy selection

## Implemented Bed Types

| Brand | Controller | Protocol | Detection |
|-------|------------|----------|-----------|
| Linak | `LinakController` | 2-byte commands, write-with-response | Service UUID `99fa0001-...` |
| Richmat | `RichmatController` | Nordic (1-byte) or WiLinke (5-byte checksum) | Service UUIDs vary by variant |
| Keeson | `KeesonController` | KSBT (6-byte) or BaseI4/I5 (8-byte XOR) | Service UUID `0000ffe5-...` |
| Solace | `SolaceController` | 11-byte packets with built-in CRC | Service UUID `0000ffe0-...` |
| MotoSleep | `MotoSleepController` | 2-byte ASCII `[$, char]` | Device name starts with "HHC" |
| Leggett & Platt | `LeggettPlattController` | Gen2 (ASCII) or Okin (binary) | Service UUID `45e25100-...` (Gen2) |
| Reverie | `ReverieController` | XOR checksum, position-based motors | Service UUID `1b1d9641-...` |
| Okimat | `OkimatController` | Okin binary, requires BLE pairing | Service UUID `62741523-...` |

## Adding a New Bed Type

1. **Document the BLE protocol** - Use nRF Connect or similar to capture GATT services, characteristics, and command bytes

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

## Other Protocol References

### Richmat
```
Nordic variant:
  Service: 6e400001-b5a3-f393-e0a9-e50e24dcca9e
  Write:   6e400002-b5a3-f393-e0a9-e50e24dcca9e
  Command: Single byte [cmd]

WiLinke variant:
  Service: Various (8ebd4f76-..., 0000fee9-..., 0000fff0-...)
  Command: [110, 1, 0, cmd, checksum] where checksum = cmd + 111
```

### Keeson (Member's Mark, Purple, ErgoMotion)
```
BaseI4/I5 variant:
  Service: 0000ffe5-0000-1000-8000-00805f9b34fb
  Write:   0000ffe9-0000-1000-8000-00805f9b34fb
  Command: [0xe5, 0xfe, 0x16, ...int_bytes_le, xor_checksum]

Commands are 32-bit values with motor bits that can be combined:
  Head up/down: 0x1/0x2, Feet up/down: 0x4/0x8
  Tilt up/down: 0x10/0x20, Lumbar up/down: 0x40/0x80
```

### MotoSleep (HHC controllers)
```
Service: 0000ffe0-0000-1000-8000-00805f9b34fb
Write:   0000ffe1-0000-1000-8000-00805f9b34fb
Command: [0x24, ASCII_char] (0x24 = '$')

Device identification: BLE name starts with "HHC"
```

### Leggett & Platt
```
Gen2 variant (ASCII commands):
  Service: 45e25100-3171-4cfc-ae89-1d83cf8d8071
  Write:   45e25101-3171-4cfc-ae89-1d83cf8d8071
  Commands: ASCII strings like "MEM 0", "STOP", "MVI 0:5"

Okin variant (binary, requires pairing):
  Service: 62741523-52f9-8864-b1ab-3b3a8d65950b
  Write:   62741525-52f9-8864-b1ab-3b3a8d65950b
  Command: [0x04, 0x02, ...int_to_bytes(cmd)]
```

### Reverie
```
Service: 1b1d9641-b942-4da8-89cc-98e6a58fbd93
Write:   6af87926-dc79-412e-a3e0-5f85c2d55de2
Command: [0x55, ...bytes, xor_checksum]
  Checksum = all bytes XOR'd together XOR 0x55

Unique: Position-based motor control (0-100%)
  Motor head: [0x51, position]
  Motor feet: [0x52, position]
```

### Okimat (requires BLE pairing)
```
Service: 62741523-52f9-8864-b1ab-3b3a8d65950b
Write:   62741525-52f9-8864-b1ab-3b3a8d65950b
Command: [0x04, 0x02, ...int_to_bytes(cmd)]

Same protocol as Leggett & Platt Okin variant.
32-bit command values similar to Keeson.
```

## Critical Implementation Details

These details were discovered by comparing with the working smartbed-mqtt implementation:

1. **Write with response** - Use `response=True` for all GATT writes. The bed expects write-with-response.

2. **Always send STOP after movement** - Movement methods use `try/finally` to guarantee STOP is sent even if cancelled. The STOP command uses a fresh `asyncio.Event()` so it's not affected by the cancel signal.

3. **Command serialization** - All entities must use `coordinator.async_execute_controller_command()` instead of calling controller methods directly. This ensures proper locking and prevents concurrent BLE writes.

4. **Cancel event handling** - `write_command()` checks `coordinator._cancel_command` by default. When stop is requested, the cancel event is set, the running command exits early, then STOP is sent.

5. **Disconnect timer management** - Timer is cancelled when a command starts (inside the lock) and reset when it ends. This prevents mid-command disconnects for long operations.

6. **Presets are long operations** - 100 repeats × 300ms = 30 seconds max. Idle timeout is 40s.

7. **Intentional disconnect flag** - Set before `client.disconnect()`, checked in `_on_disconnect` to skip auto-reconnect. Cleared in finally block since callback may not fire on clean disconnects.

## Integration Features

- **Options Flow** - Reconfigure bed settings without deleting the integration
- **Diagnostics** - Download debug info from Settings > Devices > Adjustable Bed
- **Custom Services** - `adjustable_bed.goto_preset`, `adjustable_bed.save_preset`, `adjustable_bed.stop_all`
- **Auto-reconnection** - Automatically reconnects after unexpected disconnections
- **MAC Validation** - Validates Bluetooth address format during manual setup

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

### Key Configuration Options

- **motor_count**: 2, 3, or 4 motors
- **has_massage**: Enable massage button entities
- **disable_angle_sensing**: Default `true` - keeps physical remote working
- **preferred_adapter**: Lock device to specific ESPHome proxy

### Common Issues

- **Commands timeout**: Another device (app/remote) may be connected - beds only allow one BLE connection
- **Position sensing breaks physical remote**: Enable `disable_angle_sensing` option
- **Connection drops**: Move ESP32 proxy closer to bed, check for interference

## Known Issues / Future Work

See `GEMINI_BUGS.md` for a detailed list of architectural improvements and known limitations. Key items by priority:

**HIGH PRIORITY:**
- Hardcoded max angles in `cover.py` → incorrect position % for non-Linak beds

**MEDIUM PRIORITY:**
- `async_connect` is ~400 lines → should be refactored into smaller methods
- Detection order in `config_flow.py` → beds might be misidentified
- Private HA Bluetooth manager attributes → could break in future HA versions

**LOW PRIORITY (Design limitations):**
- 30-second blocking preset loops (required by protocol)
- Optimistic switch state (expected behavior)
- Memory 1 = Flat assumption (Linak convention)
- Unsynchronized massage state (no hardware feedback)

## Reference Materials

- `smartbed-mqtt/` - Old Node.js addon (broken, but has protocol implementations for many bed types)
- `smartbed-mqtt-discord-chats/` - Discord exports with reverse-engineering discussions and user reports
- `docs/CONNECTION_GUIDE.md` - User-facing setup and troubleshooting guide
- `GEMINI_BUGS.md` - Detailed known issues and recommendations
