# Malouf Base and Lucid Base app profiles

**Status:** App behavior verified from the accepted Malouf Base 2.4.3 (54)
and Lucid Base 1.3.3 (16) artifacts. Physical validation of these explicit
profiles remains unverified.

The **Malouf/Lucid app profile** setup exposes the controls defined by the
selected app, model and Bluetooth transport. The existing
[Malouf/Lucid setup](malouf.md) remains available for previously configured
and tested devices.

## Setup

Choose the app and its model profile, then select the transport supported by
the bed's connected GATT services. A retail model name does not establish
the transport. In particular, the Nordic UART write characteristic is shared
by two incompatible packet formats, so its presence alone is insufficient.

The primary/secondary setting is the app's wire selector, used by six actions
on the framed-opcode transport. Other commands ignore it. For beds with two
separate Bluetooth addresses, configure each side first and use Home
Assistant's paired-bed setup; each child's app settings remain independent.

| Transport | Command service | Packet format |
|---|---|---|
| 32-bit legacy | `0000ffe5-0000-1000-8000-00805f9b34fb` | Nine bytes, little-endian command, one's-complement checksum |
| 32-bit middle | `62741523-52f9-8864-b1ab-3b3a8d65950b` | Ten bytes, big-endian command |
| 32-bit new | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Eight bytes, big-endian command |
| Legacy opcode | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | One-byte opcode |
| Framed opcode | `0000fee9-0000-1000-8000-00805f9b34fb` | Five bytes, side selector and additive checksum |

The app reports use opposite P1/P2 numbering for the two implementations.
The integration's transport names describe their formats instead.

## Capabilities

Controls follow each app's reachable model actions. Model profiles include
Altitude, E450, E455, Forte, the three Good Life bases, L300, L600, M455,
M550, M555, Premium, S655, S750 and S755. Memory counts range from zero to
two; massage, lights, extra actuators and presets vary by profile and
transport.

The 32-bit transports can report massage minutes and under-bed light state.
The opcode transports have no app-defined notification parser. Neither app
reports motor positions. A command being available in the controller SDK
does not by itself make it a reachable model control.

The app's massage timer button cycles the timer on the 32-bit transports.
On opcode transports, profiles with a timer selector can choose 10, 20 or
30 minutes. Massage wave and timer-cycle buttons are separate controls.
Premium's READ action follows the selected app's route; it is not silently
substituted with TV or Lounge where the app has no matching command.

Manual movement repeats at 150 ms and sends the transport's explicit STOP
after the app's 150 ms release delay, including cancellation. Preset repeats
and release frames are transport-specific. Memory programming on the 32-bit
transports ends its refresh stream without inventing a final packet for the
app's unhandled `stopCommand` string.

Lucid's three Good Life profiles also reach slot-2 programming through a
long-press fallback for their custom preset labels. This is available through
the app-routing service without adding unsupported memory recall buttons.

## App-specific split-bed routing

Ordinary entity and paired-side controls address the selected Home Assistant
side literally. `adjustable_bed.malouf_app_action` additionally reproduces
three app dispatch modes. Select the action, route and active side, with
`motor_swapped` available for native split-head routing:

| Mode | Behavior |
|---|---|
| Standard | Send to active bases |
| Split-head dual base | Also route foot/stop commands to the inactive base; presets reach both bases, programming reaches active bases only |
| Split-head native | Derive the wire selector from the active side and motor-swapped setting; selecting both uses the app's secondary selector, not two writes |

Malouf and Lucid differ in how an inactive dual base handles an `all` motor
action. The configured app determines the exact mapping. Routing validates
every destination before sending commands and uses the paired coordinator's
serialization. Select the paired parent for multi-address routing.

## Native alarm

`adjustable_bed.malouf_set_alarm` configures the controller's stored alarm on
the three 32-bit transports. Enabling it clears the previous alarm,
synchronizes local time and writes the replacement. Disabling clears it.
Use a whole-minute time and optional weekdays; an empty weekday list selects
the next occurrence of that time.

The native alarm accepts Zero-G, Lounge, TV, Anti-Snore, Memory 1, Memory 2,
Massage and Flat. These come from the app's persisted-alarm dispatch, which
is broader than its fresh alarm editor and independent of ordinary memory
button availability. The editor also has a memory-label indexing defect;
the integration uses the wire action names. No alarm protocol exists on the
two opcode transports.

## Readback limits

Massage minutes and light state follow the app's notification parsers.
Legacy light values retain their signed raw representation; only the
app's defined on value is treated as on. The middle transport's parser
returns a constant zero for light, so it does not establish physical light
state. There is no position telemetry or per-command acknowledgment.

## Evidence

This implementation reuses the two accepted frozen reports and the complete
cluster-007 reconciliation. The [finding disposition](malouf-app-disposition.md)
records exact artifact and report identities, implemented findings, reused
behavior and explicit exclusions. No new bulk analysis was performed.
