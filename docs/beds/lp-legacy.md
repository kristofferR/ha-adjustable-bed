# L&P Adjustable Base, legacy app

This explicit controller follows **L&P Adjustable Base 2.2.1 (13)**,
package `com.richmat.lp`. Its 122 remote layouts are selected by the four-character
code used in that app's manual or QR setup. The implementation uses the accepted
Phase 4 report for queue row019. It does not change existing Richmat or L&P QRRM
configurations.

**Static verified, hardware unverified.** The app's labels describe the available
actions. Some are pictograms with uncertain physical meaning, so the integration
keeps those descriptions instead of assigning guessed head, foot or lumbar axes.

## Setup

Choose **L&P Adjustable Base (legacy app)** during manual setup, then select the
exact remote code and packet mode. Configure the bed's write characteristic UUID
and, when known, its response characteristic UUID. These must come from the
device's GATT information or a capture of the working app. The app selects its
characteristics at runtime; its accepted report contains no fixed service or
characteristic UUID that can safely be applied to every layout. Neither a name
prefix nor a remote code proves the packet mode.

- **Legacy** sends the first character of the selected control's command token
  as one byte.
- **Framed** sends the token's two encoded bytes inside a five-byte packet.
  Only controls with a proven encoding for that mode are exposed.

Choosing a different layout changes the available controls. I0RM has no proven
bed commands in this app and therefore exposes no remote action buttons.
For paired beds with separate addresses, each side's stored profile provides its
remote buttons even when that side is unavailable during startup.
Changing the layout or packet mode creates distinct action entities. Update
automations to use those new entities; old actions remain unavailable instead
of being silently reassigned to different commands.

## Controls

Home Assistant exposes the selected layout's actions as named buttons, including
separate long-press actions where the app defines them. They also appear in the
adjustable bed card's utility section. Automations can call the ordinary
`button.press` action on these entities.

Held controls repeat at the app's proven 100 ms cadence. The configured motor
pulse count determines how long a button invocation holds the control. The
integration preserves each control's own release behavior and sends its release
even when a running action is cancelled. One-shot controls do not inherit a
movement repeat loop. The Stop button cancels the active action and performs its
release cleanup. It cannot stop movement started outside this integration: the
artifact defines no separate global emergency-stop command.

The optional app-response diagnostic reports only the three exact patterns the
app recognizes. Their physical meaning is not established. They are not motor
positions, battery readings, a capability query or proof that an alarm is set.
There is no invented position feedback, pairing requirement or RGB capability.

## Evidence and validation

See [the complete implementation disposition](lp-legacy-disposition.md) for
catalog coverage, excluded application-only behavior and the frozen evidence
identity. Raw APKs and analysis remain machine-local. Physical confirmation is
deferred to users with the corresponding bed after a beta or release; it is
separate from static protocol verification.
