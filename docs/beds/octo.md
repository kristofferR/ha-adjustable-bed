# OCTO Smart Control

**Integration profile:** Standard OCTO Smart Control uses the existing OCTO bed type. Star2 remains a separate protocol variant.

## Evidence and validation

The protocol implementation follows the accepted clean-room analysis of `de.octoactuators.octosmartcontrolapp` version 1.03.02 (version code 10302), acquired as a complete 19 APK / 21 member set. The evidence establishes app behavior for that delivered artifact. It does not establish that the delivery contains every Play Store variant or all 57 optional locale splits. No physical bed was available for validation, so hardware behavior remains unverified and is deferred for real users after beta or release.

The complete finding ledger, including already-covered behavior and explicit exclusions, is in [row030 dispositions](../apk-analysis/dispositions/row030-octo-smart-control.md). This artifact defines no separate protocol profile selected by OEM branding, CID, PID, hardware, firmware, locale or device name. Standard P1 remains the existing OCTO bed type; Star2 remains separate.

## Session and packet handling

Standard OCTO uses service `FFE0` and characteristic `FFE1`. After notifications are active, the controller sends the P1 ping and requires its exact reply. It then requests device information and accepts only a ten-byte result before asking for capabilities. The session becomes ready only after the complete capability list ends with `FFFFFF`. A failed or incomplete required discovery is retried as a failed connection; it does not publish PIN state or replace the previous complete capability snapshot. Star2 does not use this P1 handshake.

P1 frames use `40` delimiters, an unsigned big-endian length, a two's-complement checksum and byte escaping. Valid flagged source and destination addresses are six bytes and are removed before dispatch. The parser requires the declared frame length and checksum to match exactly. Malformed flagged addresses and undeclared trailing data are rejected.

Capabilities are retained as typed records containing the feature ID, read-only flag, characteristic bytes, value type and value bytes. Writes replace only the value bytes and preserve the advertised metadata. Device information and capabilities are stored per physical receiver when a pair is configured.

## Motor layout and motion

The active `CAP_MOTORCOUNT` record advertises one through four motors. Auto layout follows the advertised count; the OCTO-only motor-count option can set an explicit one-to-four override. A one-motor Standard receiver is shown as a TV Lift. No other app metadata selects a different protocol.

Motor commands use the advertised layout, and movement cleanup sends the receiver's global STOP with a fresh cancellation event. The bundled card uses the existing bounded `hold_control` service for held motor and memory actions, then sends STOP to the selected side when the hold ends. The service's 60-second maximum is a Home Assistant safety bound. It is not an app timing value. The OCTO controller owns the app-evidenced 350 ms command cadence; the card's motor start/release delays are 100 ms, while memory starts after 100 ms and releases after 200 ms.

Position feedback, angle sensing, massage, battery, alarm and motor-status reporting are not exposed by this app protocol. The integration does not create those states from command timing.

## Memory positions

`CAP_MEMCOUNT` supplies the advertised slot count. When a valid three-byte `CAP_MEMINFO` record exists, its first characteristic byte supplies the display count and the next two describe fixed and locked slots. Descriptions are used only when the record has one value byte per slot. Locked slots cannot be overwritten; fixed slots remain savable but are not presented as editable. Home Assistant numbers slots from one, and the wire protocol numbers them from zero.

Memory recall uses the same bounded held-control path as motor movement. Saving a slot sends the direct save command once. Each memory action is created only when the current complete capability set advertises that slot.

## PIN control

The PIN capability separates whether PIN control is enabled, whether a PIN is configured and whether the receiver is unlocked. Normal motor, memory and settings controls are unavailable while a configured PIN is locked or its live state is unknown. Stop and PIN recovery remain available. PIN digits are never included in command traces or support diagnostics.

The app retries a stored PIN once, one second after a lock challenge. The integration follows that event-driven retry and does not use a periodic PIN timer. PIN entry and enrollment require exactly four ASCII digits. To enroll a PIN, call `adjustable_bed.octo_enroll_pin` for one Standard receiver, enter the PIN twice, and target a single side when the bed is paired. Home Assistant stores the PIN for reconnects after sending the enrollment command.

## Lights and settings

Light and setting entities are created from the latest complete capability list and retired only after a later complete list proves a capability is gone. An incomplete discovery preserves the prior known surfaces. The app exposes these direct BLE controls:

| Capability | Home Assistant surface |
| --- | --- |
| Synchro / linked mode | Switch |
| Remote-control lock | Switch, hidden while PIN-locked |
| Under-bed light power | Light entity when its writable record is active |
| RGB (`CAP_LIGHT_RGB`) | RGB color mode |
| RGBWI (`CAP_LIGHT_RGBWI`) | RGBW color mode with independent intensity/brightness |
| RGB and RGBWI together | Both RGB and RGBW modes; each writes its own record |
| Light duration, 0 to 60 minutes | Number |
| Automatic light | Switch |
| Light sensitivity, 6 / 35 / 85 | Select |
| Remote teach | Button, only when active and PIN-unlocked |

Read-only and inactive records do not create writable controls. The RGB and RGBWI records keep their own metadata and values. Switching color modes writes only the requested record; the RGBWI intensity remains unchanged unless an RGBW brightness value is sent.

## Receiver reset

`adjustable_bed.octo_reset_defaults` sends the receiver's reset-default command only after the user supplies `confirmed: true` and the Standard receiver is in an unlocked session. The controller disconnects five seconds after the command. This action is destructive and targets one physical receiver; paired beds require selecting one side. Tests mock the command and do not connect to physical hardware.

## Star2

Star2 uses a distinct GATT endpoint and its own fixed command protocol. It does not declare the Standard P1 session requirement, PIN workflow, dynamic lights or memory features. The Standard-only session gate does not apply to Star2.
