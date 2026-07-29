# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration for controlling smart adjustable beds via Bluetooth Low Energy (BLE). It replaces the broken `smartbed-mqtt` addon with a native HA integration that uses Home Assistant's Bluetooth stack directly.

**Current status:** Dozens of bed protocols implemented. The README's "Supported Beds" table is the single source of truth for which protocols exist and which are confirmed working — don't duplicate that list here.

## GitHub Comment Approval

- Never post GitHub comments (issues, pull requests, discussions, releases, etc.) without explicit and specific user approval for that exact comment action.
- If approval is missing or ambiguous, ask before posting.
- Never use em dashes (—) in drafted/suggested GitHub replies. Rephrase with commas, colons, parentheses, or separate sentences instead.

### Pull request review loops

- A user request to run a PR loop for a specific PR approves only the exact
  `@coderabbitai review` comments needed by that loop: one for its then-current
  head and one for each new head produced while addressing feedback in the same
  loop. This bounded approval expires when the loop converges, the user cancels
  it, or the task changes. It does not authorize any other comment or reply.
- Do not treat `Review skipped: automatic reviews are disabled` as completion.
  Post the approved trigger, then track that specific trigger through completion.
- CodeRabbit is complete only when the newest `@coderabbitai review` trigger has
  a later `Review finished` response, the top CodeRabbit summary no longer says
  `Currently processing new changes in this PR` (or otherwise marks the review
  in progress), and the review covers the latest head commit. An older finished
  response or a green CodeRabbit status is not sufficient for a newer trigger.
- Re-fetch the top summary, trigger/reply timeline, and thread-aware review state
  after the apparent terminal transition. Do not infer completion from cached
  output captured before that transition.
- If the user has also posted `@codex review`, wait for that review and include
  its findings in the same loop.
- After addressing feedback, commit and push the fixes, resolve only the threads
  demonstrably addressed, trigger review for the new head, and continue.
- The loop is complete only when CI is green, all requested review systems have
  finished against the latest head, no unresolved actionable threads remain,
  the PR is mergeable, and the worktree is clean.

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
├── bluetooth_transport.py # Which path (host adapter vs proxy) reaches a bed
├── bluetooth_freshness.py # Refuses to connect on stale advertisement history
├── bluetooth_bond.py     # Exact host BlueZ bond inspection and removal
├── bond_verification.py  # Strict bond proof + who owns the bond
├── setup_operation.py    # Progress-backed background operations for flows
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

1. **Document the BLE protocol** - Use APK reverse engineering (see `docs/apk-analysis/TOOLING.md`) to extract UUIDs and command bytes. The `generate_support_bundle` service captures GATT structure and device responses. User-provided nRF Connect logs can supplement APK analysis with real traffic captures.

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
   - Declare capabilities by **overriding the properties `BedController` already
     defines** (`supports_massage`, `memory_slot_count`, `auto_stops_on_idle`, …).
     Entity platforms read these directly, so a typo is a type error rather than a
     silently-wrong default. Do not invent a new capability by setting an
     undeclared attribute — add it to the base class first.

4. **Add detection to `detection.py`** in `detect_bed_type()`:

   ```python
   if NEWBED_SERVICE_UUID.lower() in service_uuids:
       return BED_TYPE_NEWBED
   ```

5. **Register the controller in `controller_factory.py`.** Most beds are one line
   in the `_SIMPLE_CONTROLLERS` registry, which lazily imports the module so
   integration startup does not pay for ~50 unused controllers:

   ```python
   BED_TYPE_NEWBED: _ControllerSpec("newbed", "NewbedController"),
   ```

   Pass fixed constructor kwargs as a third argument when needed. Only add an
   explicit branch in `create_controller()` when construction needs runtime
   detection, variant resolution, or arguments derived from the advertisement.
   A bed type must not be both registered and branched on: the registry is
   consulted last, so the entry would be silently unreachable.
   `tests/test_controller_contract.py` enforces this and resolves every entry.

6. **Add to `const.py`** `SUPPORTED_BED_TYPES` list

7. **Add to `manifest.json`** `bluetooth` array if using different service UUID for discovery

8. **Update `beds/__init__.py`** to export the new controller

9. **If the bed reports motor positions**, override `position_number_specs` to
   return the sliders, building each with `build_position_number_spec()`:

   ```python
   @property
   def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
       return (
           build_position_number_spec("back", max_value=68.0, unit=POSITION_UNIT_DEGREES),
           build_position_number_spec("legs", max_value=45.0, unit=POSITION_UNIT_DEGREES),
       )
   ```

   Pass `position_key=` when the firmware reports an axis under a different name.
   Also add the bed type to `BEDS_WITH_POSITION_FEEDBACK` in `const.py`, and to
   `BEDS_WITH_PERCENTAGE_POSITIONS` if it reports 0-100 percentages rather than
   degrees. A bed that reports no position data at all belongs in neither, or in
   `BEDS_WITHOUT_ANGLE_FEEDBACK` if angle sensing would otherwise create degree
   sensors stuck at "unknown". Note that `position_number_specs` requires a live
   controller, so these entities only appear once the bed has connected.

10. **Create documentation** in `docs/beds/newbed.md`

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `motor_count` | 2, 3, or 4 motors | 2 |
| `malouf_layout` | Malouf/Lucid physical actuator layout, independent of protocol | auto |
| `malouf_memory_slots` | Malouf/Lucid remote memory capacity (auto, 1, or 2) | auto |
| `has_massage` | Enable massage entities | false |
| `protocol_variant` | Protocol variant (bed-specific) | auto |
| `disable_angle_sensing` | Disable position feedback | true |
| `preferred_adapter` | Lock to specific BLE adapter | auto |
| `connection_profile` | BLE connection profile | balanced |
| `motor_pulse_count` | Command repeat count | 10 |
| `motor_pulse_delay_ms` | Delay between repeats | 100 |
| `disconnect_after_command` | Disconnect immediately after commands | per bed type (`disconnect_after_command_default_enabled`) |
| `idle_disconnect_seconds` | Idle timeout before disconnect | 40 |
| `disable_discovery` | Suppress automatic discovery (global, stored via `discovery_settings`) | false |
| `position_mode` | Speed vs accuracy tradeoff | speed |
| `octo_pin` | PIN for Octo beds | "" |
| `jensen_pin` | PIN for Jensen beds | "" |
| `cb24_bed_selection` | Bed A/B selection for CB24 split beds | default (neither side) |
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
| `adjustable_bed.generate_support_bundle` | Capture the full JSON support bundle (BLE diagnostics, GATT details, pairing evidence, command trace, logs). Params: `device_id` or `target_address` (exactly one), `capture_duration`, `include_logs` |

## Critical Implementation Details

**IMPORTANT: Protocol values are hardware-specific.** Timing values (repeat counts, delays), command bytes, and packet formats vary between bed types. Do NOT copy values from one bed's protocol documentation to another. Each bed type's parameters must come from actual device testing or reverse engineering - never guess or extrapolate from other implementations.

1. **Always perform protocol-specific STOP/release cleanup after movement** - Movement methods use `try/finally` so cleanup runs even if cancelled. When the protocol defines a STOP or release frame, send it with a fresh `asyncio.Event()` so the cancel signal cannot suppress it. If complete artifact evidence proves that a protocol stops solely by ending its held-command refresh and defines no release frame, ending that cancellable refresh is the required cleanup; never invent or extrapolate a hardware command merely to send an extra packet.

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
  bun run check   # tsc (TypeScript 7) typecheck + esbuild bundle
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

### Running tests

Run the Python test suite with `uv run pytest`. Automatic worker selection
detects the available CPUs but is capped at four workers; explicit numeric
overrides remain available.
Use `uv run pytest -n 0 <test-path>` for focused or debug runs. Agents must not
run multiple full suites concurrently, since the worker cap applies to each
pytest process. On a suitably powerful desktop, one full-suite run may override
the automatic selection explicitly, for example: `uv run pytest -n 8`.

### Testing in Home Assistant

1. Copy `custom_components/adjustable_bed` to your HA's `config/custom_components/`
2. Restart Home Assistant
3. Enable debug logging: Settings → Devices & Services → Adjustable Bed → ⋮ menu → Enable debug logging. Use the integration, then disable debug logging to download the log file.

### Using BLE Diagnostics

The `generate_support_bundle` service captures protocol data for debugging and adding new bed support:
1. Call the service with either a configured device (`device_id`) or a raw MAC address (`target_address`) - exactly one of the two
2. Operate the physical remote during the capture period (default 120 seconds)
3. A persistent notification provides a download link; the JSON report is also saved in the HA config directory as `adjustable_bed_support_bundle_*.json`
4. The report contains GATT services, characteristics, captured notifications, advertisements per source, pairing evidence, and the recent command trace

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

### Mandatory clean-room analysis while issue #436 is open

Until [issue #436](https://github.com/kristofferR/ha-adjustable-bed/issues/436) is complete and its work is merged, any task that inspects an APK must produce reusable Phase 4 evidence so the package does not need to be analyzed again later. This is also required before implementing a bug fix or enhancement that depends on BLE protocol behavior, including command bytes, packet construction, timing, STOP/release behavior, discovery, authentication, parsing, model variants, or capability selection.

- Use the verified latest artifact from the frozen acquisition corpus. Include the complete APK/XAPK/split set and record its identity and hashes.
- Follow the clean-room workflow and completion gates in [issue #443](https://github.com/kristofferR/ha-adjustable-bed/issues/443). Analyze the artifact in a fresh isolated workspace before consulting integration code, existing protocol documentation, legacy analyses, issues, PRs, commits, captures, or reports for other apps.
- Workspace location: create the run under `disassembly/output/phase4-early/<package_id>-<version>-<date>/` with `input/`, `work/` and `report/` subdirectories. It must be on persistent storage: `/tmp` is tmpfs on the maintainer machine and is wiped by a reboot, which has already destroyed a workspace mid-analysis. Name the directory by package ID only, never by a presumed protocol family (#443 §4.1).
- Contamination firewall: this file is auto-injected into every agent, including the analyst. Every auto-injected instruction file is process instructions only, never evidence. Brand, protocol-family, controller-class and model names appear in this file; the analyst must not use them to name, group, select, or corroborate anything in a report, must not read any other file in this repository, and must record in `SEARCH_LOG.md` which instruction files were injected and that nothing in them was used as evidence. Stop and report BLOCKED if an injected file hands over protocol answers: a service or characteristic UUID, a command or packet byte value, a framing or checksum description, a device-name matching pattern, or a command repeat/hold interval attributed to a bed protocol. That is a repository defect, not an acceptable exposure. Integration-level configuration defaults and BLE connection-management timeouts documented in this file are not protocol evidence and are not grounds to block, but they are still unusable as evidence. `disassembly/PROTOCOL_NOTES.md` is exactly such a file, and it sits directly above the run workspaces, so it must never be named `AGENTS.md` or `CLAUDE.md`: either name is auto-injected by directory and would hand the analyst the comparison notes before its first action. Only the repository root may hold an instruction file under those names. `tests/test_cleanroom_guard.py` enforces this.
- If the current context has already accessed forbidden comparison material, start a new isolated analyst context with only the artifact, identity manifest, pinned schema, protocol-neutral tools, and the reusable #443 prompt. Do not call a contaminated run clean-room or COMPLETE.
- Cover every application stack that contains app logic. Flutter requires Blutter, React Native/Hermes requires shipped-bundle analysis, AIR requires FFDec, and suspicious or failed jadx output requires smali or another authoritative fallback.
- Freeze package-local `ANALYSIS.md`, schema-valid `analysis.json`, `SEARCH_LOG.md`, reproducer/test-vector scripts, and `REPORT.SHA256`. A PARTIAL or BLOCKED report must identify the exact gap and actionable next step.
- Register analyses completed ahead of the scheduled Phase 4B bulk run in [issue #447](https://github.com/kristofferR/ha-adjustable-bed/issues/447), including the exact package/version, artifact-set hash, report status, and originating issue or PR. An accepted COMPLETE report that passes the #443 gates replaces that package's Phase 4A route and must be excluded from the later bulk run. PARTIAL or BLOCKED work remains in the completion queue.
- Only after the clean-room report is frozen may a separate comparison pass inspect the integration and historical evidence, implement corrections, and update durable protocol documentation.
- Keep raw artifacts, decompilation output, and Phase 4 reports machine-local and ignored as required by #436. Commit only durable integration, test, documentation, and workflow-instruction changes.
- Do not assume maintainers can physically test a discovered bed. A report may be COMPLETE when app behavior is exhaustively proven from the artifact while hardware status remains explicitly unverified. Treat physical checks and captures as deferred external validation for real users after a beta or release, not as an immediately actionable maintainer task or an automatic reason to fail the analysis.
- Never guess protocol behavior when the required artifact or analysis layer is unavailable. Record the precise APK or runtime-table blocker. If only physical semantics remain, record a deferred validation request for real users after beta/release; do not ask a maintainer to acquire or immediately test the bed.

See **[docs/apk-analysis/TOOLING.md](docs/apk-analysis/TOOLING.md)** for decompiler setup and
invocation (jadx, apktool, blutter, ffdec) and the required per-stack coverage. It is method-only
by construction and states no UUID, byte value, or device-name pattern, so it is safe to hand to a
clean-room analyst.

The canonical #443 analyst prompt and pinned `analysis.json` schema are
[`docs/apk-analysis/phase4-analyst-prompt.md`](docs/apk-analysis/phase4-analyst-prompt.md) and
[`docs/apk-analysis/analysis.schema.json`](docs/apk-analysis/analysis.schema.json). Copy both into
a run's `input/` unchanged and fill only the `<<...>>` placeholders. Do not hand-edit a workspace
copy.

**Folder structure:**
- `disassembly/apk/analyzed/` - APKs that have been analyzed
- `disassembly/apk/not-analyzed/` - APKs pending analysis
- `disassembly/output/phase4-early/<package_id>-<version>-<date>/` - clean-room run workspace
  (`input/`, `work/`, `report/`), machine-local and gitignored

`disassembly/PROTOCOL_NOTES.md` holds historical protocol and cross-app comparison notes. It is for the
post-freeze comparison pass only and must never be read during a clean-room run.
