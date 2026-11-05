# MotoMotion

**Status:** ❓ Needs testing (MotoMotion 3.1.9, static artifact evidence; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- The app selects 17 primary routes: 13 panel classes and four aliases.
- Case-sensitive local names containing `SOFA` with length 15, `BT201` with length 9, or containing `MOTO` are scan candidates. These are contains tests, not prefixes.
- `BT201` selects binary music first. Otherwise zero-based name index 9 selects `1`, `2`, `3`, `5`, `6`, `7`, `8`, `9`, `A`, `D`, `E`, `G`, `H`, or `J`. `MM` at indices 9 and 10 selects ASCII music. Other selectors use the One panel.
- No physical brand/model equivalence is inferred from those selectors. MotoSleep and Power Bob remain separate app profiles.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [MotoMotion](https://play.google.com/store/apps/details?id=com.HHC.MotoMotion) 3.1.9 (code 2026051101) | `com.HHC.MotoMotion` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ App-labelled headrest, lumbar, main, back, legrest and tilt controls, selected by panel |
| Position Feedback | ❌ No measured motor angle/percentage response |
| Memory Presets | ✅ 0–4 slots, with panel-specific recall and programming |
| Massage | ✅ Name-selected level controls |
| Heat | ✅ Name/panel-selected level or cycle controls |
| Lights | ✅ Panel light cycle/toggle, RGB and timer where admitted |
| Music | ✅ ASCII or binary equalizer controls; binary playback buttons |
| User postures | ✅ Local measurements, four generated/custom raw Hall target postures, fine tuning |
| Side selection | ✅ Left/right when `SOFA` name index 10 is `S` |
| Binding | ✅ Eight-byte application binding and explicit application unbinding |

## Protocol Details

| Service match | Write characteristic match | Notify characteristic match | Binding |
|---------------|----------------------------|-----------------------------|---------|
| `FFE0` | `FFE1` | Same `FFE1`, after 100 ms | `FFE2` |
| Otherwise `FFF0` | `FFF1` | `FFF2` | None |

Matches use the discovered UUID strings uppercased and containing the indicated fragment. The full discovered characteristic is retained. Later matching services may replace roles. Normal writes require a response. Only application unbinding uses write without response. Unbinding resolves FFE0/FFE1 independently, even when later FFF0 roles win for normal commands. Home Assistant/Bleak owns notification subscription and CCCD management.

### Packet Format

| Format | Bytes |
|--------|-------|
| A | ASCII `$#` + command padded to five decimal digits + parameter padded to five digits + numeric-digit XOR padded to five digits + `R\r` |
| B | `24 23 cmdHi cmdLo paramHi paramLo xor(bytes2..5) 41 0d` |
| C | ASCII `$#` + `M`, `T`, `B` or `V` + truncated value padded to two digits + `\r` |
| D | `41 49 4f 4b` + five big-endian saturated unsigned 16-bit targets in head/lumbar/back/base/tilt order + `52 0d` |
| E | Eight random bytes, each 0–254, without framing/checksum |

Padding does not truncate A/C values. B masks words to 16 bits. D saturates each word to 0–65535. No extra CRC, encryption, fragmentation or command acknowledgment layer is inferred.

## Detection / Setup

Choose **MotoMotion app** and enter the exact Bluetooth local name. The Home Assistant display name never selects a panel. Discovery offers a candidate without overriding another app's confident match. Shared service UUIDs alone do not select this app.

Name lengths and zero-based indices follow the app’s UTF-16 code units. A supplementary Unicode character occupies two units in both profile selection and receive routing.

Name flags are independent:

| Name condition | Behavior |
|----------------|----------|
| `SOFA`, index 10 `S` | Left parameter `S=0`, right `S=10000` |
| `SOFA`, index 12 `E` | Memory recall release requests STOP |
| `SOFA`, index 11 `B`/`D` | Light kind 1; index 11 `C` selects kind 2 |
| `SOFA`, index 13 `F` | Kind 2 still validates RGB, then sends A(300,S) |
| `SOFA`, index 14 `H` | Heat-only mode; `M` admits heat/massage tab |
| `SOFA`, index 11 `D` | RGB tab, except panel 6 with index 10 `A` |
| `SOFA`, index 10 `A` | Users/posture tab |
| `SOFA`, index 9/10 `M`, index 9 `8`, or index 10 `S` | Music tab |
| Contains `MOTO` | Shared movement uses B; STOP independently tests `MOTOA` |
| Panel Five, index 14 `M`/`X` | Main up/down use 32776/32775; its embedded heat button is hidden |

Short names that would make the app index outside the name are rejected during HA setup. Controls are available from the stored profile before connecting. Two-address pairs keep profile names, binding codes, users and settings per physical address. One-address side controls are available only for the exact S name flag and retain their child side. Parent Both operations fan out left then right; there is no native Both value or synchronized hardware operation claim.

## Commands

`A(c,p)` and `B(c,p)` refer to the shipped controller builders above. `S` is a decimal parameter, never a bit mask. Tables describe app-labelled actions, without inferred motor remapping.

### Motor Control

| Panel/action | Command up / down |
|--------------|-------------------|
| Shared headrest | A(2,S) / A(1,S); selector `2` is labelled Back in the app and always uses ASCII A(32,S) / A(16,S), including MOTO names |
| Shared lumbar | A(8,S) / A(4,S) |
| Shared main | A(128,S) / A(85,S); home A(262,S) |
| G main | A(32773,S) / A(32774,S) |
| A/H main | A(165,S) / A(64,S) |
| J/Five main | A(165,S) / A(80,S), with Five M/X override above |
| Explicit back | A(32,S) / A(16,S) |
| Five back slider | A(16,S) / A(32,S), intentionally reversed from the button bar |
| Explicit legrest | A(64,S) / A(128,S) |
| Six main | A(1445,S) / A(80,S), or B(1445,0) / B(80,0) |
| Six tilt | A(337,S) / A(338,S), or B(512,0) / B(256,0) |
| Shared binary headrest / lumbar / back / legrest | B(2/1,0), B(128/64,0), B(32/16,0), B(8/4,0) |
| STOP | B(0,0) for `MOTOA`; otherwise A(0,S), three writes at the same 50 ms deadline |

### Memory

| Panel | Available hardware memories |
|-------|-----------------------------|
| One (including aliases), Three, Five, J | 2 |
| G | 4 |
| D | 1 exposed slot, using the app's M2 command |
| E | 1 |
| Six | 1, or none when its heat-only center is selected |
| A, Seven, H, ASCII/binary music | None |

| Action | Command |
|--------|---------|
| Recall slots 1/2/3/4 | A(256,S), A(257,S), A(32779,S), A(32780,S) |
| Program slots 1/2/3/4 | A(263,S), A(264,S), A(33052,S), A(33053,S) |
| D single exposed memory | Recall A(257,S), program A(264,S) |
| E program | A(33050,0), then A(263,S) after 300 ms |
| Six binary recall/program | B(32777,0) / B(33050,0) |
| Program/release button | A(0,S) |
| D memory/lumbar combined gesture | Wait 3000 ms, then A(33050,0); programming remains an explicit separate action |

### Massage, Heat and Lights

| Action | Commands |
|--------|----------|
| Heat levels 0–3 | A(335/332/333/334,S) |
| Massage levels 0–3 | A(353/350/351/352,S) |
| Five heat cycle | A([332,333,334][heat % 3],S) |
| H heat cycle | A([332,334,335][heat % 3],S); CM heat 3 displays as 2, HSW is unchanged |
| Six heat cycle | A([335,332,333,334][(heat + (2 if heat==1 else 1)) & 3],S) |
| D lumbar, unknown / known zero | A(33055,0) at 0/100/200 ms / once |
| D lumbar, known nonzero | A(33050,0), then A(16,0) after 300 ms |
| E lumbar | A(352,0) if unknown/zero, otherwise A(353,0), at 0/100/200 ms |
| D/E light cycle | A(32787+next,0), `next` in 1–8; off A(32787,0) |
| Kind 1 light | A(262,S) |
| Kind 2 light | RGB zero total selects white (120 each), nonzero selects black (0 each), or A(300,S) for flag F |
| RGB | A(315/316/317,S+level), level=floor(channel/255*120), values below 10 become 0 |
| RGB timer | Literal `24 7a`, then A(32999,seconds) after 50 ms; off 0, enable default 15, picker 0–120 minutes and 0–59 seconds |

Level up/down normalizes received 4 to 0, then bounds to 0–3. D/E light cycling wraps each signed 64-bit increment before remainder modulo nine and maps zero to one. RGB zero testing wraps each intermediate signed 64-bit addition. Invalid strings fail before a new command. Partial receive stores can change the next action without an event.

### Music and Postures

| Action | Command / range |
|--------|-----------------|
| Binary music initialization | B(10,0), B(8,0) |
| Binary play / next / previous | B(14,0) / B(12,0) / B(13,0) |
| Binary volume / treble / bass / vibration | B(9,v), B(1,v) then B(2,v) after 50 ms, B(3,v), B(4,v); ranges 0–63 / 0–31 / 0–31 / 0–31 |
| ASCII channels | C(M/T/B/V,value); ranges volume 0–22, other channels 0–15 |
| Music modes | Custom, wide, electric, live; volume retained; binary seven writes spaced 50 ms, ASCII concatenates four frames |
| User posture / fine tune | One full D frame, raw Hall targets; no degree feedback |
| Application unbinding | Literal `$#005001234500004R\r`, without response; disconnect after 1000 ms |

The `adjustable_bed.motomotion` action manages named local users and postures. `dimensions` is `[height, buttocks_height, knee_height]` in centimetres. All must be finite. The four posture keys are `upright`, `recline`, `tv`, and `lay`. Fine-tuning targets require all five keys: head 0–863, base 0–3174, back 0–1454, lumbar 0–874, tilt 0–629. Generated head targets can reach 867; that source mismatch is preserved. Local custom saves do not program hardware memory. Switching user or posture invalidates unsent working targets; a save request must match the user and posture that own those targets.

## Position Feedback / Notifications

The framer waits for `$` then CR, discards preceding noise and the entire coalesced suffix, and clears the buffer before parsing. It strips all characters other than ASCII digits/spaces, then splits literal spaces, retaining empty tokens. Supported token counts: 11, 16, 24, 31, 37, 38, 39, 42, 43, 50, 62 and 71. Count 43 emits two events.

The status sensor retains RGB/D/comfort/HSW fields and parse errors. Heat, massage, lift/calibration flags and the unidentified `field_1b` remain protocol state, not invented angle sensors. Completed stores survive later parse failures. Events are asynchronous names and read current state when delivered. Numeric consumers accept nonnegative signed-64-bit decimal values with arbitrarily many leading zeroes; actual overflow and empty fields fail in source order.

## Command Timing

Held movement refreshes every 100 ms, first write after 100 ms. HA button presses are bounded to one second; the hold action accepts an explicit duration. STOP cleanup uses a fresh cancellation event. The shared Home control refreshes every 100 ms and ends by stopping refresh, without a release frame. The controller owns the first-tick and release timing; the card adds no extra delay. Card gesture release cancels the admitted hold and lets that hold own its cleanup; a separate explicit STOP still sends the source STOP packets. Normal settings are one-shots; source nonrepeat controls use a 200 ms delay. RGB components are sent at 0/100/200 ms. Notify callbacks and pending commands are tied to the current connection session.

HA deliberately cancels delayed writes on release/cancellation, always performs admitted movement cleanup, and separates saving from recall. The shipped app can retain a delayed write after release, suppress queued STOP on re-press, or recall on the release of a save gesture. Those hazards are not reproduced. Exact findings and negative tests are in the ledger.

## Notes

Binding status uses manufacturer ID 1465 (`0x05b9`): empty data is unbound, leading `01` requests binding, other first bytes indicate bound. The app and HA reject bound devices unless the entire advertised hex suffix after the first byte exactly matches the saved code for that address. A missing or mismatched code rejects session admission before notification subscription or ordinary writes; no additional mask or firmware ACK is inferred. A binding request generates eight bytes, updates local cache and starts a persistence request before the FFE2 write. Neither the app nor HA claims that durability has completed at that point. No cached-code retransmission, auth ACK gate, PIN, or OS bond is invented.

### Analysis provenance

- Accepted package: `com.HHC.MotoMotion` 3.1.9, code 2026051101.
- Frozen XAPK SHA-256: `b1a590b6f24c8d4f5b8dfd10293b5266b4d0a95abd3a04f27786524bfd6accc2`.
- Separate APK-member-set SHA-256: `a354614e81258f020f5207de3b3f85393535beedb8f1028e3dc2aa6221e60522`. These identify different things.
- Five-APK arm64-v8a/en/fr/mdpi delivery only. Public Play metadata establishes versionName only, not versionCode, signer or exact delivery. Same-version replacement and other device/region deliveries are not excluded. Acquisition source-stamp and application signer digests were separated by the accepted audit.
- [Per-item discovery ledger](../apk-analysis/dispositions/row113-motomotion.json) records report/audit seals, all command and candidate mappings, corrections and exclusions. Raw artifacts, decompilation and audit reports remain local.
- ATT acceptance, actual firmware responses and physical effects need real-user validation after beta/release. No maintainer hardware check is required to complete the static implementation.
