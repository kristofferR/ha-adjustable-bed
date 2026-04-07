# Juna Sleep Protocol Analysis

**Package:** `com.keeson.junasleep`  
**Version:** 1.0.1  
**APK Source:** APKPure XAPK  
**Analysis Date:** 2026-04-07  
**Status:** Analysis complete. This app materially expands the Keeson family coverage and is the clearest source for the direct LV 6-byte path.

## Overview

Juna Sleep is not a minor Keeson clone. It clearly spans two related but distinct transport families:

- `Quest`, `Rewind`, `Restore`, and `Relax` use a JSON command envelope over the `0000a00a` / `0000b002` service pair.
- `LVrestore` and `LVrelax` use direct Nordic-UART-style packets over `6e400001` / `6e400002`.

That matters because the app is not just renaming the same remote. It contains:

- A real JSON/A00A command family for the non-LV remotes
- A real direct 6-byte LV command family for the LV remotes
- Separate held-motion metadata for `Quest` versus the other JSON remotes

It still does **not** reveal a bed-speaker / sound-therapy BLE path. The sound-related code is local phone audio.

## Primary Sources

- `com/keeson/junasleep/utils/Constants.java`
- `com/keeson/junasleep/service/FastBleService.java`
- `com/keeson/junasleep/manager/ControlManager.java`
- `com/keeson/junasleep/utils/deviceByte2/DataUtilSec.java`
- `com/keeson/junasleep/utils/widget/QuestBed.java`
- `com/keeson/junasleep/utils/widget/RewindBed.java`
- `com/keeson/junasleep/utils/widget/RestoreOrRelax.java`
- `com/keeson/junasleep/ui/fragment/RemoteFragment.java`
- `com/keeson/junasleep/entity/Cmd.java`
- `com/keeson/junasleep/entity/DeviceData.java`

## BLE UUIDs

From `utils/Constants.java`:

- `UUID_SERVICE = 0000a00a-0000-1000-8000-00805f9b34fb`
- `UUID_WRITE = 0000b002-0000-1000-8000-00805f9b34fb`
- `UUID_IN = 0000b004-0000-1000-8000-00805f9b34fb`
- `UUID_SERVICELV = 6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- `UUID_WRITELV = 6E400002-B5A3-F393-E0A9-E50E24DCCA9E`
- `UUID_NOTIFYLV = 6E400003-B5A3-F393-E0A9-E50E24DCCA9E`

Remote constants in the same file:

- `REMOTE_TYPE_RESTORE = 100`
- `REMOTE_TYPE_RELAX = 101`
- `REMOTE_TYPE_LVRESTORE = 102`
- `REMOTE_TYPE_LVRELAX = 103`

## Remote Family Mapping

`ui/fragment/RemoteFragment.java` explicitly switches on these server-provided remote names:

- `Quest`
- `Rewind`
- `Restore`
- `Relax`
- `LVrestore`
- `LVrelax`

Transport selection in that fragment is explicit:

- `connectBleDevice(..., true)` for `Quest`, `Rewind`, `Restore`, `Relax`
- `connectBleDevice(..., false)` for `LVrestore`, `LVrelax`

So the app itself treats the LV remotes as a separate no-WiFi / direct-BLE command path, not just a visual variant.

## Transport 1: JSON / A00A Family

### Envelope format

`QuestBed`, `RewindBed`, and `RestoreOrRelax` all construct the same object model:

```json
{
  "code": 2,
  "dvid": "<ble name>",
  "cmd": {
    "key": "00001000",
    "ctrm": 1,
    "km": 1,
    "keykt": 0
  }
}
```

The field names come directly from `entity/DeviceData.java` and `entity/Cmd.java`:

- `code`
- `dvid`
- `cmd.key`
- `cmd.ctrm`
- `cmd.km`
- `cmd.keykt`

`JsonHelp.toJson(...)` is plain Gson serialization, so there is no extra wrapper logic hiding elsewhere.

### One-shot buttons

All JSON remotes use the same one-shot metadata:

- `ctrm = 1`
- `km = 1`
- `keykt = 0`

This applies to presets, flat, zero-G, light, timer, and massage buttons.

### Held movement

Held motion is the interesting split:

- `QuestBed.onTouch(...)` uses:
  - `ctrm = 0`
  - `km = 3`
  - `keykt = 1`
- `RewindBed.onTouch(...)` uses:
  - `ctrm = 1`
  - `km = 3`
  - `keykt = 1`
- `RestoreOrRelax.onTouch(...)` for `remoteType 100/101` uses:
  - `ctrm = 1`
  - `km = 3`
  - `keykt = 1`

So `Quest` is the outlier. The motor key values are shared, but the held-motion metadata is not.

### Stop command

`ControlManager.stopAddOrSubtract(...)` builds a JSON stop:

- `key = "00000000"`
- `ctrm = 0`
- `km = 1`
- `keykt = 0`

That stop structure is shared across the JSON family.

## Transport 2: Direct LV 6-byte Family

`utils/deviceByte2/DataUtilSec.buildInstruct(int key)` builds this exact 6-byte packet:

```text
04 02 cmd3 cmd2 cmd1 cmd0
```

Properties:

- fixed prefix `04 02`
- 32-bit command value in big-endian order
- no trailer byte
- no checksum

Examples:

- Stop `0x00000000` -> `04 02 00 00 00 00`
- Head up `0x00000001` -> `04 02 00 00 00 01`
- Head down `0x00000002` -> `04 02 00 00 00 02`
- Foot up `0x00000004` -> `04 02 00 00 00 04`
- Foot down `0x00000008` -> `04 02 00 00 00 08`
- Light `0x00020000` -> `04 02 00 02 00 00`
- Flat `0x08000000` -> `04 02 08 00 00 00`

This is the same framing shape as the integration's existing KSBT 6-byte command family.

## Query / Session Handling

`DataUtilSec.buildQueryData()` returns:

```text
00 B0
```

Observed usage:

- `FastBleService.sendDataToDeviceNo()` enables notify on `UUID_SERVICELV` / `UUID_NOTIFYLV`, then writes `00 B0`
- `ControlManager.sendToDevice(...)` sends the requested payload, then schedules three follow-up `00 B0` writes at 300 / 600 / 900 ms
- `ControlManager.sendQueryData(...)` also schedules the same three `00 B0` writes
- `ControlManager.stopAddOrSubtractLv(...)` stops the scheduler and sends `00 B0`

This differs from the sibling `com.keeson.connectedbed` app, whose LV stop path sends a direct LV stop packet instead of `00 B0`.

## FastBleService Notes

Two things are clear:

- `sendDataToDeviceIn(...)` enables indicate on `0000a00a` / `0000b004`
- `sendDataToDeviceNo(...)` enables notify on Nordic UART and writes the LV query packet

One thing is **not** cleanly resolved:

- In Juna's decompiled `FastBleService.writeDataToDevice(...)`, the method appears to always write to `UUID_SERVICELV` / `UUID_WRITELV`, regardless of `isHasWifi`

That is suspicious because:

- `RemoteFragment` clearly distinguishes WiFi/non-WiFi remote families
- the sibling `com.keeson.connectedbed` app branches cleanly between `UUID_SERVICE/UUID_WRITE` and `UUID_SERVICELV/UUID_WRITELV`

Best interpretation:

- the Juna decompile is either misleading in this one method
- or the app funnels both payload types through a shared write helper in a way JADX flattened poorly

I would not treat that single decompiled method as stronger evidence than the rest of the app structure.

## Confirmed Command Values

### Shared core values

- Stop: `0x00000000`
- Head up: `0x00000001`
- Head down: `0x00000002`
- Foot up: `0x00000004`
- Foot down: `0x00000008`
- Head+foot up: `0x00000005` (`Quest` only, confirmed in UI code)
- Head+foot down: `0x0000000A` (`Quest` only, confirmed in UI code)
- Timer: `0x00000200`
- Foot massage: `0x00000400`
- Head massage: `0x00000800`
- Zero-G: `0x00001000`
- 0x2000 address: `0x00002000`
- 0x4000 address: `0x00004000`
- 0x8000 address: `0x00008000`
- 0x10000 address: `0x00010000`
- Light: `0x00020000`
- Flat: `0x08000000`

### Quest

From `utils/widget/QuestBed.java`:

- `questM1` -> `0x00002000`
- `questM2` -> `0x00004000`
- `questM3` -> `0x00008000`
- `questM4` -> `0x00010000`
- Zero-G -> `0x00001000`
- Flat -> `0x08000000`
- Light -> `0x00020000`
- Timer -> `0x00000200`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`
- Massage mode cycle:
  - `0x04000000`
  - `0x00080000`
  - `0x00100000`
  - `0x00200000`

Held motion uses:

- Head up `0x00000001`
- Head down `0x00000002`
- Foot up `0x00000004`
- Foot down `0x00000008`
- Head+foot up `0x00000005`
- Head+foot down `0x0000000A`

### Rewind

From `utils/widget/RewindBed.java`:

- `read` -> `0x00002000`
- `tv` -> `0x00004000`
- `show` -> string `"4000000"`
- Zero-G -> `0x00001000`
- Flat -> `0x08000000`
- Light -> `0x00020000`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`
- Massage cycle:
  - `0x04000000`
  - `0x00080000`
  - `0x00100000`
  - `0x00200000`

Held motion uses the normal single-motor keys with JSON `ctrm=1, km=3, keykt=1`.

### Restore

`RestoreOrRelax(remoteType=100)` uses JSON commands:

- `read` -> `0x00002000`
- `tv` -> `0x00004000`
- `show` -> string `"4000000"`
- Zero-G -> `0x00001000`
- Flat -> `0x08000000`
- Time -> `0x00000200`
- Light -> `0x00020000`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`

Held motion uses JSON `ctrm=1, km=3, keykt=1`.

### Relax

`RestoreOrRelax(remoteType=101)` uses JSON commands:

- `m` -> `0x00002000`
- `sleep` -> `0x00008000`
- `show` -> string `"4000000"`
- Zero-G -> `0x00001000`
- Flat -> `0x08000000`
- Time -> `0x00000200`
- Light -> `0x00020000`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`

Held motion uses JSON `ctrm=1, km=3, keykt=1`.

### LVrestore

`RestoreOrRelax(remoteType=102)` switches to direct LV packets:

- Zero-G -> `0x00001000`
- `read` -> `0x00002000`
- `tv` -> `0x00004000`
- Flat -> `0x08000000`
- Time -> `0x00000200`
- Light -> `0x00020000`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`
- `show` -> `0x40000000` via `DataUtilSec.buildInstruct(1073741824)`

Held motion uses direct LV keys `1 / 2 / 4 / 8`.

### LVrelax

`RestoreOrRelax(remoteType=103)` also uses direct LV packets:

- Zero-G -> `0x00001000`
- `m` -> `0x00002000`
- `sleep` -> `0x00008000`
- Flat -> `0x08000000`
- Time -> `0x00000200`
- Light -> `0x00020000`
- Head massage -> `0x00000800`
- Foot massage -> `0x00000400`
- `show` -> `0x40000000`

Held motion uses direct LV keys `1 / 2 / 4 / 8`.

## Ambiguities Worth Preserving

Two things should stay called out rather than silently normalized:

### 1. JSON `show` value looks inconsistent

For the JSON remotes, `RewindBed` and `RestoreOrRelax` set:

- `cmd.setKey("4000000")`

That is seven hex digits, i.e. `0x04000000`, not `0x40000000`.

That is odd because:

- LV `show` uses `0x40000000`
- `Quest` also uses `0x04000000` as one of its massage-mode cycle values

Possible explanations:

- the JSON family really does use `0x04000000` for the `show` button
- the OEM code is missing a leading zero in string form
- the decompile obscured a formatting helper

This is real source evidence, so it should be documented as-is rather than silently "fixed".

### 2. Juna's write routing is weaker evidence than its widget code

The widget code and fragment routing clearly define the two transport families. The single suspicious `writeDataToDevice(...)` decompile should not override that broader picture without captured BLE traffic.

## Audio Findings

The sound-related classes are app-side media / alarm features:

- `AlarmSoundActivity`
- `MusicUtil`
- `SoundItem`
- `SoundAdapter`
- `MediaPlayerManger`

They use Android audio APIs and bundled media. I did **not** find:

- a bed-speaker BLE characteristic
- white / pink / brown noise control packets
- speaker volume BLE commands
- light+sound therapy BLE packets

So this APK is valuable for bed motion and preset transport, not for integrated audio.

## Practical Takeaways For The Integration

- Treat `0000a00a / 0000b002` as a distinct Keeson JSON command family.
- Treat `LVrestore` / `LVrelax` as direct 6-byte `04 02 cmd3 cmd2 cmd1 cmd0` devices.
- Do not assume JSON held-motion metadata is uniform: `Quest` differs from `Rewind` / `Restore` / `Relax`.
- Do not claim Juna proves bed audio support. It does not.

## Conclusion

Juna Sleep is the strongest APK in this set for real Keeson-family protocol coverage. It confirms:

- non-LV JSON remotes: `Quest`, `Rewind`, `Restore`, `Relax`
- LV direct-packet remotes: `LVrestore`, `LVrelax`
- the exact LV 6-byte framing
- a meaningful split in held-motion metadata within the JSON family

It improves preset, light, massage, and movement coverage substantially, but it still does **not** solve the integrated-audio question.
