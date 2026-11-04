# ISleep

**Status:** ❓ Needs testing (accepted APK audit, hardware **UNVERIFIED**)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- ISleep bases (Kaidi OEM) advertising one of eight products: 129, 130, 131,
  132, 133, 134, 142 and 143 (see the
  [Kaidi product table](kaidi.md#apk-backed-product-ids))
- Selected only through the explicit **ISleep (com.kaidi_test4)** setup profile.
  A name, MAC prefix or service UUID alone does not select it.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [ISleep](https://play.google.com/store/apps/details?id=com.kaidi_test4) 1.6.3 (45) | `com.kaidi_test4` |

- The profile implements the accepted ISleep 1.6.3 (45) standalone APK audit.
- Rize/Floyd and existing Kaidi entries retain their separate legacy route;
  selecting a shared transport does not identify which app owns a bed.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (upper/back and feet; head and waist per product; press, timed hold, release) |
| Combined up/down | ✅ (**All up** / **All down** buttons) |
| Presets | ✅ (Flat, Zero-G, Anti-snore) |
| Memory Presets | ✅ (three slots, recall and explicit program) |
| Lights | ✅ (discrete on/off) |
| Massage | ✅ (on/off, patterns 1/2/3, strengths 0-100, timer; optimistic state) |
| Position Feedback | ❌ (no position, light or massage telemetry) |
| Single-address Left/Right | ⚠️ (products 130 and 143 only, when the actuator descriptor is not 2) |
| Room enrollment | ✅ (explicit action for unprovisioned mode09 beds) |
| Foreign-room reset (mode07) | ❌ (excluded for safety) |

### Product controls

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

- Every product also has combined up/down, Flat, Zero-G, anti-snore, three
  memory slots (recall and explicit program), light on/off and massage on/off.
- Product 143 has head strength only and displays 10/20/30-minute timer
  choices. All others have head/foot strengths and 15/30/45-minute choices.
- The firmware interpretation of product143's timer labels remains unverified:
  the phone's local countdown still uses 15-minute units. HA sends the
  corresponding choice opcode and does not present that phone bookkeeping as
  measured bed time.
- HA axes: upper/back is the back control, feet is the legs control and waist
  is the lumbar control.

## Protocol Details

**Service UUID:** none required (GATT discovery matches the write/notify characteristics across services; it does not require the server-only service UUID)
**Write Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc1386f`
**Notify Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc2386f` (notify/indicate)
**Format:** Room-authenticated frames with little-endian 32-bit destination and own addresses

### Packet Format

| Packet | Template | Bytes |
| --- | --- | --- |
| Auth | `011601 + LE32(room) + ASCII1122` | `01 16 01 LE32(room) 31 31 32 32` |
| Fresh enrollment | `0103 + LE32(room) + ASCII1122 + 00000000` | `01 03 LE32(room) 31 31 32 32 00 00 00 00` |
| Ping | `03FFFFFFFFFE + own[4]` | `03 ff ff ff ff fe` + own address (LE32) |
| Control | `03 + LE32(destination) + 20 + own[4] + 01 opcode parameter 00` | `03 LE32(target) 20 LE32(own) 01 opcode parameter 00` |

Example frames from `room_frame()` and `control_frame()`:

| Example | Bytes |
| --- | --- |
| Auth, room `1` | `01 16 01 01 00 00 00 31 31 32 32` |
| Auth, room `-1` (signed) | `01 16 01 ff ff ff ff 31 31 32 32` |
| Enrollment, room `1` | `01 03 01 00 00 00 31 31 32 32 00 00 00 00` |
| Head up, own `0x11223344`, target `0x55667788`, parameter `0` | `03 88 77 66 55 20 44 33 22 11 01 01 00 00` |
| Flat, own `ffffffff`, target `0`, parameter 50 | `03 00 00 00 00 20 ff ff ff ff 01 1c 32 00` |

- The room is the signed 32-bit identity sent during authentication, not a
  display name.
- The strength parameter starts at zero, changes on a strength write, and
  remains in subsequent movement, preset and release packets.
- No checksum, fragmentation, sequence number or command acknowledgment exists.

### Write Mode

- Platform-default response write (the controller writes with response), one
  GATT write per command with no retry or hold refresh.
- HA/Bleak own CCCD subscription, indication selection and Bluetooth
  adapter/proxy access.

### Session Setup

- Authentication must succeed and own/target addresses must be live before a
  control write.
- Incoming `010A` supplies own address (zero becomes `FFFFFFFF`); `0102`
  invalidates the roster; channel `FF` replies carry reverse MAC and virtual
  address.
- Incoming virtual zero and signed -2 normalize to destination zero; an absent
  MAC mapping is offline.
- Saved advertisement virtual addresses never authorize a control after
  reconnect.
- Android queue polling and reconnection timers are replaced by HA's managed
  Bluetooth lifecycle.

## Detection / Setup

### Setup and room identity

- Select ISleep explicitly and confirm the advertised product ID and actuator
  descriptor. The profile form uses those fields as defaults when HA has a
  matching advertisement.
- Keep the existing numeric room ID to adopt a provisioned bed. Existing rooms
  are adopted by explicit selection, without reset.
- Close the phone app before connecting.

| Signal | Value |
| --- | --- |
| Manufacturer payload marker | `FFFFC0FF` |
| Advertisement modes | 01/02/09 |
| Products | The eight allowed products above |
| Mode09 company gate | `4B44` |
| Actuator masks | `(acu >> 8) & 7 <= 5`, `acu & 15 <= 5`, `acu & 240 <= 5` (the artifact's exact masks) |

- Truncated alternate mode02 records are rejected safely.

### Room enrollment

For a genuinely unprovisioned mode09 bed, set the desired room during setup,
then press **Enroll unprovisioned bed in selected room** in the device's
entities.

- Requires the selected physical MAC's unprovisioned advertisement and matching
  product.
- Sends enrollment once, waits up to the artifact's eight seconds, and
  disconnects on either result.
- Only an accepted reply saves a pending enrollment acknowledgment.
- The next control authenticates the selected room, obtains a live roster match
  for this MAC, then sends the acknowledgment (opcode `0x45`) before the action.
- Failure, timeout, cancellation or another MAC cannot create a successful
  target.
- Retry after enrollment if the bed is not yet advertising its room.
- Setup verification alone never enrolls a device.

### Room reset and app infrastructure

- HA never advertises the destructive mode07 foreign-room reset. This safety
  exclusion preserves ownership by an existing room. Use the official app for a
  room transfer/reset, then select that room in HA.
- HA config entries replace the phone's random room generator, SQL row
  allocation, role-conflict dialogs and room labels. HA does not reproduce the
  proven SQL collision or optimistic success bugs.

### Home Assistant setup

Choose **ISleep (com.kaidi_test4)** and confirm its product ID, signed 32-bit
room ID and advertised actuator descriptor. The profile owns layout, massage,
feedback and movement timing. A two-address pair keeps these settings per side.
Adopt existing rooms explicitly; enrollment of fresh mode09 devices is a
separate device action. HA never resets an existing room. See the
[row064 ledger](../apk-analysis/dispositions/row064-isleep.md).

## Paired beds

- For one-address role1 layouts, Left/Both/Right send the exact three-column
  opcodes; Both is one combined opcode, not two sequential side commands.
- For a two-address pair, add both physical beds separately, then combine them.
  Each keeps its own product, room, session and capabilities.
- Mixed-product combined controls use HA's capability intersection rather than
  the phone's stale layout or wrong-target timer behavior.
- All single-address side conversion is checked against the selected
  product/actuator descriptor at runtime.
- Paired options reject a product/descriptor that loses side controls until the
  bed is reverted to standalone.

## Commands

Values are the `opcode` byte of the control frame, from `COMMANDS` and
`IsleepController._axis()` in
[`beds/isleep.py`](../../custom_components/adjustable_bed/beds/isleep.py). The
`parameter` byte is the retained strength parameter. Columns are the role1
lanes; products without one-address sides always send the Left / single column.

### Motor Control

| Command | Left / single | Right | Both | Products |
| --- | --- | --- | --- | --- |
| Upper/back up / down / release | `0x01` / `0x02` / `0x03` | `0x0A` / `0x0B` / `0x0C` | `0x13` / `0x14` / `0x15` | 129, 130, 143 |
| Upper/back up / down / release | `0x7A` / `0x7B` / `0x7C` | | | 131, 132, 133, 134, 142 |
| Head up / down / release | `0x01` / `0x02` / `0x03` | | | 131, 132, 133, 134 |
| Feet up / down / release | `0x04` / `0x05` / `0x06` | `0x0D` / `0x0E` / `0x0F` | `0x16` / `0x17` / `0x18` | All |
| Waist up / down / release | `0x83` / `0x84` / `0x85` | | | 132, 134 |
| All up / down / release | `0x07` / `0x08` / `0x09` | `0x10` / `0x11` / `0x12` | `0x19` / `0x1A` / `0x1B` | All except 142 |
| All up / down / release | `0x95` / `0x96` / `0x97` | | | 142 |

- Movement sends one press, waits for the HA gesture duration or cancellation,
  then sends its matching release with a fresh cancellation event.
- Cleanup retains the original side, target, own address and connection
  identity, and never reconnects to send a release into a different session.
- STOP sends supported axis/combined releases: the release of each product axis,
  then the combined release.

### Presets

| Command | Left / single | Right | Both |
| --- | --- | --- | --- |
| Flat | `0x1C` | `0x1D` | `0x1E` |
| Zero-G | `0x62` | `0x63` | `0x64` |
| Anti-snore | `0x65` | `0x66` | `0x67` |

> [!WARNING]
> Opcodes 28/29/30 (`0x1C`/`0x1D`/`0x1E`) are Flat in this app despite their
> constant names and are never emergency STOP commands.

### Memory

| Command | Left / single | Right | Both |
| --- | --- | --- | --- |
| Recall 1 / 2 / 3 | `0x29` / `0x2A` / `0x2B` | `0x31` / `0x32` / `0x33` | `0x39` / `0x3A` / `0x3B` |
| Program 1 / 2 / 3 | `0x25` / `0x26` / `0x27` | `0x2D` / `0x2E` / `0x2F` | `0x35` / `0x36` / `0x37` |

### Massage

| Command | Left / single | Right | Both | Parameter |
| --- | --- | --- | --- | --- |
| Massage on | `0x47` | `0x49` | `0x4B` | retained |
| Massage off | `0x48` | `0x4A` | `0x4C` | retained |
| Head strength | `0x4D` | `0x4E` | `0x51` | new strength 0-100 |
| Foot strength | `0x4F` | `0x50` | `0x52` | new strength 0-100 |
| Pattern 1 | `0x6B` | `0x6C` | `0x6D` | retained |
| Pattern 2 | `0x6E` | `0x6F` | `0x70` | retained |
| Pattern 3 | `0x71` | `0x72` | `0x73` | retained |
| Pattern cancel | `0x74` | `0x75` | `0x76` | retained |
| Timer choice 1 (15 min; 10 on product 143) | `0x53` | `0x56` | `0x59` | retained |
| Timer choice 2 (30 min; 20 on product 143) | `0x54` | `0x57` | `0x5A` | retained |
| Timer choice 3 (45 min; 30 on product 143) | `0x55` | `0x58` | `0x5B` | retained |
| Timer cancel | `0x77` | `0x78` | `0x79` | retained |

- Strength controls are 0-100 **massage intensity**, never motor positions.
- Pattern buttons select 1/2/3; pressing the selected pattern again cancels it.
  Pattern 0 explicitly cancels.
- Selecting the current timer choice again or selecting Off cancels the timer
  using its dedicated command; it does not turn massage off.
- HA saves requested massage state and the retained strength byte per physical
  address/profile. These are optimistic requests, with no feedback from the bed.
- A profile/room change clears incompatible saved intent.
- The requested timer and strength remain visible per side while disconnected.
- HA retains that intent across restart as well as reconnect; the phone's static
  wire byte resets at process startup.
- No timer expiry or external remote use is inferred as telemetry.

### Lights

| Command | Left / single | Right | Both |
| --- | --- | --- | --- |
| Light on | `0x5C` | `0x5E` | `0x60` |
| Light off | `0x5D` | `0x5F` | `0x61` |

### Session

| Command | Bytes |
| --- | --- |
| Enrollment acknowledgment | Control frame with opcode `0x45` |

## Position Feedback / Notifications

| Notification | Meaning |
| --- | --- |
| `02 16` + status | Authentication response; status `0` is accepted |
| `02 03` + status | Enrollment response; status `0` is accepted |
| `01 0A` + own address (LE32) | Own address; zero becomes `FFFFFFFF` |
| `01 02` … (at least 10 bytes) | Roster invalidation |
| `03` …, channel `FF` at byte 5 | Roster reply: bytes 6-11 reverse MAC, bytes 12-15 virtual address; used only when the MAC matches |

- Channel20 has no position, light or massage telemetry.
- Channel2F is a phone alarm trigger, not bed time reporting.
- Library product/group/remote-response parsers do not feed the app's product
  selector or controls and are excluded.

## Command Timing

- Five-second response deadlines are HA failure bounds, not artifact repeat
  timings.
- Enrollment waits up to eight seconds.
- The configured pulse count at 100ms per count bounds the HA gesture; it does
  not repeat the BLE packet.

## Notes

- Local phone alarms can be replaced with HA automations using the exposed
  presets.
- WiFi provisioning, network administration, cloud/accounts, themes, QR
  appearance downloads and unrelated app infrastructure are excluded.
- After beta/release, real users can supply captures to verify physical axis
  semantics, held/released/link-loss behavior, room enrollment and product143
  timers. No maintainer hardware acquisition or immediate physical test is
  needed to complete this artifact-driven implementation.

### Analysis provenance

- Package `com.kaidi_test4`, ISleep 1.6.3 (45).

| Seal | SHA-256 |
| --- | --- |
| Artifact set | `6102a03e00d45ac1c12a5c9effb2eb7255128d8dfd5e5c24c5af7f9929e2d897` |
| Accepted report (`report-revision-sol-002`) | `d00ec6709a9cfd53c7e254590e95fb9ee21151db47e35eb1a10ceeb47a2198f1` |
| Independent audit (`audit-sol-round03`, ACCEPT) | `fe33a01ce0a19ee55c172310f5344b5d5c5e18befcd65cd91bacad992d751fde` |

- The [comparison ledger](../apk-analysis/dispositions/row064-isleep.md)
  records every command, variant, session path and exclusion.
