# ISleep

The explicit **ISleep (com.kaidi_test4)** setup profile implements the accepted
ISleep 1.6.3 (45) standalone APK audit. Hardware remains **UNVERIFIED**. The
[comparison ledger](../apk-analysis/dispositions/row064-isleep.md) records every
command, variant, session path and exclusion. Rize/Floyd and existing Kaidi
entries retain their separate legacy route; selecting a shared transport does
not identify which app owns a bed.

## Setup and room identity

Select ISleep explicitly and confirm the advertised product ID and actuator
descriptor. The manufacturer payload has marker `FFFFC0FF`, modes 01/02/09,
eight allowed products, a mode09 company gate `4B44`, and the artifact's exact
actuator masks. Truncated alternate mode02 records are rejected safely. The
profile form uses those fields as defaults when HA has a matching advertisement.
A name, MAC prefix or service UUID alone does not select the ISleep app profile.

Keep the existing numeric room ID to adopt a provisioned bed. It is the signed
32-bit identity sent during authentication, not a display name. Close the phone
app before connecting. GATT discovery matches the write/notify characteristics
across services; it does not require the server-only service UUID. HA/Bleak own
CCCD subscription, indication selection and Bluetooth adapter/proxy access.

For a genuinely unprovisioned mode09 bed, set the desired room during setup, then
press **Enroll unprovisioned bed in selected room** in the device's entities.
This action requires the selected physical MAC's unprovisioned advertisement and
matching product. It sends enrollment once, waits up to the artifact's eight
seconds, and disconnects on either result. Only an accepted reply saves a
pending enrollment acknowledgment. The next control authenticates the selected
room, obtains a live roster match for this MAC, then sends the acknowledgment
before the action. Failure, timeout, cancellation or another MAC cannot create a
successful target. Retry after enrollment if the bed is not yet advertising its
room. Setup verification alone never enrolls a device.

HA never advertises the destructive mode07 foreign-room reset. This safety
exclusion preserves ownership by an existing room. Use the official app for a
room transfer/reset, then select that room in HA. HA config entries replace the
phone's random room generator, SQL row allocation, role-conflict dialogs and
room labels; it does not reproduce the proven SQL collision or optimistic
success bugs. Existing rooms are adopted by explicit selection, without reset.

## Product controls

| Product | Visible independent axes | One-address side selection |
|---|---|---|
| 129 | Upper/back, feet | No |
| 130 | Upper/back, feet | Only when actuator descriptor is not 2 |
| 131 | Upper/back, feet, head | No |
| 132 | Upper/back, feet, head, waist | No |
| 133 | Upper/back, feet, head | No |
| 134 | Upper/back, feet, head, waist | No |
| 142 | Upper/back, feet | No, UI5 does not mean five motors |
| 143 | Upper/back, feet | Only when actuator descriptor is not 2 |

Each also has combined up/down, Flat, Zero-G, anti-snore, three memory slots
(recall and explicit program), light on/off and massage on/off. Product 143
has head strength only and displays 10/20/30-minute timer choices; all others
have head/foot strengths and 15/30/45-minute choices. The firmware interpretation
of product143's timer labels remains unverified: the phone's local countdown
still uses 15-minute units. HA sends the corresponding choice opcode and does
not present that phone bookkeeping as measured bed time.

Strength controls are 0-100 **massage intensity**, never motor positions. Pattern
buttons select 1/2/3; pressing the selected pattern again cancels it. Pattern 0
explicitly cancels. Selecting the current timer choice again or selecting Off
cancels the timer using its dedicated command; it does not turn massage off.
HA saves requested massage state and the retained strength byte per physical
address/profile. These are optimistic requests, with no feedback from the bed.
A profile/room change clears incompatible saved intent. The requested timer and
strength remain visible per side while disconnected. Paired options reject a
product/descriptor that loses side controls until the bed is reverted to
standalone. HA retains that intent
across restart as well as reconnect; the phone's static wire byte resets at
process startup. No timer expiry or external remote use is inferred as telemetry.

For one-address role1 layouts, Left/Both/Right send the exact three-column
opcodes; Both is one combined opcode, not two sequential side commands. For a
two-address pair, add both physical beds separately, then combine them. Each
keeps its own product, room, session and capabilities. Mixed-product combined
controls use HA's capability intersection rather than the phone's stale layout
or wrong-target timer behavior. All single-address side conversion is checked
against the selected product/actuator descriptor at runtime.

## Wire and lifecycle

- Write: `9e5d1e47-5c13-43a0-8635-82adffc1386f`, platform-default response write.
- Notify/indicate: `9e5d1e47-5c13-43a0-8635-82adffc2386f`.
- Auth: `011601 + LE32(room) + ASCII1122`.
- Fresh enrollment: `0103 + LE32(room) + ASCII1122 + 00000000`.
- Ping: `03FFFFFFFFFE + own[4]`.
- Control: `03 + LE32(destination) + 20 + own[4] + 01 opcode parameter 00`.

The strength parameter starts at zero, changes on a strength write, and remains
in subsequent movement, preset and release packets. No checksum, fragmentation,
sequence number or command acknowledgment exists. Incoming `010A` supplies own
address (zero becomes `FFFFFFFF`); `0102` invalidates the roster; channel `FF`
replies carry reverse MAC and virtual address. Incoming virtual zero and signed
-2 normalize to destination zero; an absent MAC mapping is offline. Saved
advertisement virtual addresses never authorize a control after reconnect.
Authentication must succeed and own/target addresses must be live before a
control write. Five-second response deadlines are HA failure bounds, not
artifact repeat timings. Android queue polling and reconnection timers are
replaced by HA's managed Bluetooth lifecycle.

Movement sends one press, waits for the HA gesture duration or cancellation,
then sends its matching release with a fresh cancellation event. The configured
pulse count at 100ms per count bounds the HA gesture; it does not repeat the BLE
packet. Cleanup retains the original side, target, own address and connection
identity, and never reconnects to send a release into a different session.
STOP sends supported axis/combined releases. Opcodes 28/29/30 are Flat in this
app despite their constant names and are never emergency STOP commands.

Channel20 has no position, light or massage telemetry. Channel2F is a phone
alarm trigger, not bed time reporting. Library product/group/remote-response
parsers do not feed the app's product selector or controls and are excluded.
Local phone alarms can be replaced with HA automations using the exposed
presets. WiFi provisioning, network administration, cloud/accounts, themes,
QR appearance downloads and unrelated app infrastructure are excluded.

After beta/release, real users can supply captures to verify physical axis
semantics, held/released/link-loss behavior, room enrollment and product143
timers. No maintainer hardware acquisition or immediate physical test is needed
to complete this artifact-driven implementation.
