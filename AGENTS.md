# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE). It replaces the broken `smartbed-mqtt` addon with a native HA integration that uses Home Assistant's Bluetooth stack directly.

**Current status:** Dozens of bed protocols implemented. The README's "Supported Beds" table is the single source of truth for which protocols exist and which are confirmed working — don't duplicate that list here.

## GitHub Comment Approval

- Never post GitHub comments (issues, pull requests, discussions, releases, etc.) without explicit and specific user approval for that exact comment action.
- If approval is missing or ambiguous, ask before posting.

## Architecture

Key modules (not an exhaustive listing — check the folder for the rest):

```text
custom_components/adjustable_bed/
├── __init__.py           # Integration setup, platform loading, service registration
├── config_flow.py        # Device discovery and setup wizard
├── coordinator.py        # BLE connection management (central hub)
├── const.py              # Constants, UUIDs, bed type definitions, feature flags
├── detection.py          # Bed type auto-detection from BLE services/names
├── controller_factory.py # Factory for creating bed controller instances
├── entity.py             # Base entity class
├── beds/                 # Bed controllers — one module per protocol
│   ├── base.py           # Abstract base class (BedController)
│   ├── diagnostic.py     # Debug controller for unsupported beds
│   └── ...               # See the README "Supported Beds" table and docs/beds/
├── cover.py / button.py / sensor.py / switch.py / light.py / climate.py /
│       select.py / number.py / binary_sensor.py   # HA entity platforms
├── diagnostics.py        # HA diagnostics download support
├── ble_diagnostics.py    # BLE protocol capture for new bed support
└── ...                   # Helpers: adapter, validators, redaction, support_report, etc.
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

The supported-protocol list lives in the README's "Supported Beds" table — that is the single source of truth; don't mirror it here. To find how a specific bed works:

- `custom_components/adjustable_bed/beds/` — one controller module per protocol
- `detection.py` — how each bed type is auto-detected (service UUIDs, name patterns)
- `controller_factory.py` — which bed type maps to which controller class, including
  variants that share a controller (e.g. Serta/Ergomotion → `KeesonController`)
- `docs/beds/*.md` — per-protocol documentation including command formats and
  tested/untested status

## Adding a New Bed Type

1. **Document the BLE protocol** - Use APK reverse engineering (see `disassembly/AGENTS.md`) to extract UUIDs and command bytes. The `run_diagnostics` service captures GATT structure and device responses. User-provided nRF Connect logs can supplement APK analysis with real traffic captures.

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
| `connection_profile` | BLE connection profile | balanced |
| `motor_pulse_count` | Command repeat count | 10 |
| `motor_pulse_delay_ms` | Delay between repeats | 100 |
| `disconnect_after_command` | Disconnect immediately after commands | false |
| `idle_disconnect_seconds` | Idle timeout before disconnect | 40 |
| `disable_discovery` | Suppress automatic discovery (global, stored via `discovery_settings`) | false |
| `position_mode` | Speed vs accuracy tradeoff | speed |
| `octo_pin` | PIN for Octo beds | "" |
| `jensen_pin` | PIN for Jensen beds | "" |
| `cb24_bed_selection` | Bed A/B selection for CB24 split beds | 0x00 |
| `richmat_remote` | Remote code for Richmat beds | auto |
| `back_max_angle` | Max angle for back motor (degrees) | 68.0 |
| `legs_max_angle` | Max angle for legs motor (degrees) | 45.0 |

## Services

| Service | Description |
|---------|-------------|
| `adjustable_bed.goto_preset` | Move bed to memory position 1-4 |
| `adjustable_bed.save_preset` | Save current position to memory 1-4 |
| `adjustable_bed.stop_all` | Immediately stop all motors |
| `adjustable_bed.set_position` | Move motor to a specific position |
| `adjustable_bed.timed_move` | Move motor for a specified duration |
| `adjustable_bed.run_diagnostics` | Capture BLE protocol data for debugging |
| `adjustable_bed.generate_support_bundle` | Generate JSON support bundle with diagnostics (params: device_id, include_logs) |

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
   - Do NOT include an "Upgrading" section - users already know how to update

## Frontend (Lovelace Card)

The integration ships a native Lovelace card, `custom:adjustable-bed-card`,
under `custom_components/adjustable_bed/frontend/`.

- **Source**: `frontend/src/*.ts` (Lit + TypeScript). Key modules:
  - `discovery.ts` — given a `device_id`, buckets the device's entities by
    `translation_key` into UI sections. This is what makes the card generic
    across all bed types; **when you add a new entity, give it a stable
    `translation_key`** and, if it belongs in the card, add it to a bucket here.
  - `adjustable-bed-card.ts` — the card element (renders only sections that have
    entities; all colour comes from HA theme CSS variables).
  - `editor.ts` — visual editor (`ha-form` + device picker + section toggles).
  - `bed-graphic.ts` — theme-aware angle SVG. `localize.ts` + `translations/`
    hold the card's own strings (section headers / editor labels) in `en`/`nb`;
    entity names come from HA's localized `friendly_name`.
- **Build** (requires [bun](https://bun.sh)):
  ```bash
  cd custom_components/adjustable_bed/frontend
  bun install
  bun run check   # tsgo typecheck + esbuild bundle
  bun test        # discovery unit tests
  ```
  The bundle is written to `frontend/dist/adjustable-bed-card.js` and is
  **committed** (it ships with the integration). Rebuild and commit it whenever
  you change `frontend/src`.
- **Registration**: `frontend.py` serves `frontend/dist` as a static path and
  calls `add_extra_js_url`, so the card auto-loads with no manual Lovelace
  resource. `frontend` is listed in `manifest.json` `after_dependencies` for
  setup ordering; registration is best-effort and never blocks integration
  setup.

## Development

### Testing in Home Assistant

1. Copy `custom_components/adjustable_bed` to your HA's `config/custom_components/`
2. Restart Home Assistant
3. Enable debug logging: Settings → Devices & Services → Adjustable Bed → ⋮ menu → Enable debug logging. Use the integration, then disable debug logging to download the log file.

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
