# OCTO Smart Control

**Integration profile:** Standard OCTO Smart Control uses the existing OCTO bed type. Star2 remains a separate protocol variant.

## Evidence and validation

The protocol implementation follows the accepted clean-room analysis of `de.octoactuators.octosmartcontrolapp` version 1.03.02 (version code 10302), acquired as a complete 19 APK / 21 member set. The evidence establishes app behavior for that delivered artifact. It does not establish that the delivery contains every Play Store variant or all 57 optional locale splits. No physical bed was available for validation, so hardware behavior remains unverified and is deferred for real users after beta or release.

The complete finding ledger, including already-covered behavior and explicit exclusions, is in [row030 dispositions](../apk-analysis/dispositions/row030-octo-smart-control.md). This artifact defines no separate protocol profile selected by OEM branding, CID, PID, hardware, firmware, locale or device name. Standard P1 remains the existing OCTO bed type; Star2 remains separate.

## Session and packet handling

Standard OCTO uses service `FFE0` and characteristic `FFE1`. When a receiver answers, the controller follows the app's order: P1 ping, ten-byte device information, then the capability request. A complete advertised list ends with `FFFFFF` and is the only source of authoritative capability records. Malformed replies remain strict failures.

For established receivers that omit a ping or device-info reply, the integration continues to the next ordered request. If the capability list is absent or incomplete, it keeps any previous complete snapshot and uses the integration's field-compatible legacy defaults, including the historical assume-lights path. These defaults are not reported as complete discovery and cannot retire known entities or be persisted as a capability snapshot. This absence fallback preserves the behavior used by field-reported receivers; it does not change the accepted app behavior when valid replies arrive. Star2 does not use this P1 handshake.

Initial setup uses the same absence-only path to reach capability verification when ping or device-info replies are omitted. Setup still needs a complete valid `FFFFFF` capability list and, when PIN capability requires it, a current PIN-state reply. A malformed or partial reply remains inconclusive and cannot be treated as an absent optional response.

P1 frames use `40` delimiters, an unsigned big-endian length, a two's-complement checksum and byte escaping. Valid flagged source and destination addresses are six bytes and are removed before dispatch. The parser requires the declared frame length and checksum to match exactly. Malformed flagged addresses and undeclared trailing data are rejected.

Capabilities are retained as typed records containing the feature ID, read-only flag, characteristic bytes, value type and value bytes. Writes replace only the value bytes and preserve the advertised metadata. Device information and capabilities are stored per physical receiver when a pair is configured.

## Motor layout and motion

The active `CAP_MOTORCOUNT` record advertises one through four motors. Auto layout follows the advertised count; the OCTO-only motor-count option can set an explicit one-to-four override. If no motor count is discovered, the existing RTV-name setup fallback selects one motor; a valid advertised count or explicit override takes precedence. A one-motor Standard receiver is shown as a TV Lift. This is a layout default only and does not select a different protocol.

After a session accepts an absent capability-list fallback, Standard OCTO keeps motor covers for that known effective layout, including configured and RTV defaults. The fallback remains non-authoritative: it creates no capability records or persisted snapshot. Stable cover IDs remain available to the paired child while its link is released; movement still requires a ready session, and a later complete list reconciles the registry to its advertised layout. Malformed replies do not activate this fallback.

Motor commands use the advertised layout, and movement cleanup sends the receiver's global STOP with a fresh cancellation event. The bundled card uses the existing bounded `hold_control` service for held motor and memory actions, then sends STOP to the selected side when the hold ends. The service's 60-second maximum is a Home Assistant safety bound. It is not an app timing value. The OCTO controller owns the app-evidenced 350 ms command cadence; the card's motor start/release delays are 100 ms, while memory starts after 100 ms and releases after 200 ms.

Position feedback, angle sensing, massage, battery, alarm and motor-status reporting are not exposed by this app protocol. The integration does not create those states from command timing.

## Memory positions

`CAP_MEMCOUNT` supplies the advertised slot count. When a valid three-byte `CAP_MEMINFO` record exists, its first characteristic byte supplies the display count and the next two describe fixed and locked slots. Descriptions are used only when the record has one value byte per slot. Locked slots cannot be overwritten; fixed slots remain savable but are not presented as editable. Home Assistant numbers slots from one, and the wire protocol numbers them from zero.

Memory recall uses the same bounded held-control path as motor movement. Saving a slot sends the direct save command once. Each memory action is created only when the current complete capability set advertises that slot.

## PIN control

The PIN capability separates whether PIN control is enabled, whether a PIN is configured and whether the receiver is unlocked. Normal motor, memory and settings controls are unavailable while a configured PIN is locked or its live state is unknown. Stop and PIN recovery remain available. PIN digits are never included in command traces or support diagnostics.

The integration keeps the established periodic PIN keepalive while a configured-PIN link is held, serialized through the coordinator command lane. Like earlier releases, it runs only for a receiver that reports a PIN or never reports its PIN state, and a receiver without a complete capability list also gets the configured PIN at connect. During a long held motor or memory operation, the controller tracks the existing monotonic refresh deadline from the last successful PIN write and refreshes within that admitted lane. Movement-write transport time counts toward each pulse interval. A due refresh is sent as soon as an in-flight movement write completes; its own write consumes the remaining pulse gap and can delay the next pulse if still in flight. The requested hold deadline remains finite. It also retries a stored PIN once after the app's one-second lock challenge. The keepalive interval is host behavior, not an app timing claim. PIN entry and enrollment require exactly four ASCII digits. To enroll a PIN, call `adjustable_bed.octo_enroll_pin` for one Standard receiver, enter the PIN twice, and target a single side when the bed is paired. Home Assistant stores the PIN for reconnects after sending the enrollment command.

## Lights and settings

For complete app-authoritative capability lists, light and setting entities follow the latest records and retire only after a later complete list proves a capability is gone. An incomplete discovery preserves prior known surfaces. If discovery replies are absent, the separate field-compatibility path may expose the legacy assumed-light switch without declaring capability records authoritative. The app exposes these direct BLE controls:

| Capability | Home Assistant surface |
| --- | --- |
| Synchro / linked mode | Switch |
| Remote-control lock | Switch, hidden while PIN-locked |
| Under-bed light power | Existing switch for on/off-only records; light entity for color/intensity records |
| RGB (`CAP_LIGHT_RGB`) | RGB color mode |
| RGBWI (`CAP_LIGHT_RGBWI`) | RGBW color mode with independent intensity/brightness |
| RGB and RGBWI together | Both RGB and RGBW modes; each writes its own record |
| Light duration, 0 to 60 minutes | Number |
| Automatic light | Switch |
| Light sensitivity, 6 / 35 / 85 | Select |
| Remote teach | Button, only when active and PIN-unlocked |

Read-only and inactive records do not create writable controls. The RGB and RGBWI records keep their own metadata and values. Switching color modes writes only the requested record; the RGBWI intensity remains unchanged unless an RGBW brightness value is sent.

For complete advertised capabilities, a valid positive light-duration record gives its advertised minutes, while an explicit zero means permanent lighting. If duration is absent, the integration retains the established five-minute state-expiry fallback. An active malformed duration is not replaced with that fallback. For both switch and color-light surfaces, a deliberate ON command restarts the host expiry; identical on-state updates and an equivalent reconnect keep the existing deadline. Expiration updates the current controller without a BLE write. Explicit off, duration changes, authoritative capability loss and entity removal cancel or replace the deadline. For an on/off-only receiver, the existing `switch.*_under_bed_lights` entity and unique ID remain in place so existing automations continue to target the same entity. Newly discovered color or intensity capabilities may create a light entity without migrating or deleting that switch. When no capability list arrives, the legacy assumed-light command path uses the established on/off switch and does not invent a writable capability record.

## Receiver reset

`adjustable_bed.octo_reset_defaults` sends the receiver's reset-default command only after the user supplies `confirmed: true` and the Standard receiver is in an unlocked session. The controller disconnects five seconds after the command. This action is destructive and targets one physical receiver; paired beds require selecting one side. Tests mock the command and do not connect to physical hardware.

## Star2

Star2 uses a distinct GATT endpoint and its own fixed command protocol. It does not declare the Standard P1 session requirement, PIN workflow, dynamic lights or memory features. The Standard-only session gate does not apply to Star2.
