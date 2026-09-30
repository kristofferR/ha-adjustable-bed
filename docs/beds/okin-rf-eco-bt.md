# OKIN Smart Remote / RF ECO BT Single Actuator

**Status:** Supported

This profile is for the Elda BTH / RF ECO BT / MEGAMAT setup from
[issue #344](https://github.com/kristofferR/ha-adjustable-bed/issues/344). It is
not a normal adjustable bed profile: it exposes one cover entity named `Stair`
for a moving staircase actuator.

The [ELDA-BTH product page](https://elda-treppen.de/produkt/bth/) describes the
system as a semi-automatic loft stair with a quiet maintenance-free spindle
motor, gas spring support, switch and/or radio remote control, and electrical
emergency lowering.

## Features

| Feature | Supported |
|---------|-----------|
| Stair actuator cover | Yes |
| Stop | Yes |
| Presets | No |
| Memory buttons | No |
| Lights | No |
| Massage | No |
| Position feedback | No |

## Setup

Use manual setup and choose **OKIN Smart Remote / RF ECO BT single actuator**.

Choose this profile only for a single moving actuator. RF ECO BT is also used
as the receiver for adjustable beds. For a bed controlled by the FurniMove app,
choose **[FurniMove / OKIN Smart Remote](furnimove.md)** and select its exact
handset ID. For another app, use that app’s documented integration profile.
Legacy RF ECO BT entries receive an offline layout repair, including entries
with a configured count of one. Explicit staircase confirmation prevents the
repair from returning while preserving the existing Stair entity.

The reported device advertises as `OKIN-050226` with no service UUIDs, so the
integration cannot safely auto-detect it from advertisements alone. Diagnostics
can identify it after connecting when this GATT signature is present:

- Service `62741523-52f9-8864-b1ab-3b3a8d65950b`
- Write characteristic `62741525-52f9-8864-b1ab-3b3a8d65950b`
- CSS service `90311623-25fa-3346-12ef-3cfb7a2556ac`
- CSS write characteristic `90311625-25fa-3346-12ef-3cfb7a2556ac`

If the same device also exposes Nordic DFU service
`00001530-1212-efde-1523-785feabcd123`, it may be either this profile or a full
bed controller using [Okin CST](okin-cst.md). That service is not a safe
discriminator: the integration preserves an already configured RF ECO BT or
CST profile when these GATT signals disagree with it.

Full OKIMAT beds and RF ECO BT bed receivers expose the **same** OKIN write +
CSS GATT signature as this stair profile. The GATT signature alone is therefore
not enough to choose a topology. Confirmed Device Information models include:

- `MEGAMAT MBZ`: the single-actuator ELDA staircase from issue #344
- `OKIMAT 4 IPS/M`: the multi-motor Lattoflex bed from issue #406
- `RF eco BT`: a two-motor bed receiver using RF-TOPLINE handset `82620`, also
  reported in issue #344

The exact `MEGAMAT MBZ` model remains the stronger staircase signal. For other
shared-GATT receivers, selecting a valid handset code explicitly under the
Okin UUID profile is stronger evidence than the generic receiver identity and
keeps the multi-motor controller active.

Generic `OKIN-*` devices remain ambiguous because multiple unrelated OKIN
protocols use that naming pattern.

## Protocol

The accepted clean-room audit of `com.okin.okinsmartcomfort` 2.2.0 (19) proves
the shipped offline two-axis fallback table's M2 commands and six-byte frame.
The staircase retains its independently reported M2 actuator mapping from
issue #344. The generic zero-valued frame is not a valid staircase STOP: the
reporter found it switched a light on, while ending refresh stopped motion.
The integration therefore sends only the held direction and ends its cancellable
refresh on release. It does not fabricate a zero command.

| Action | Packet |
|--------|--------|
| Open / up | `04 02 00 00 00 01` |
| Close / down | `04 02 00 00 00 02` |
| Stop / release | End held-command refresh, no extra frame |

Direction refresh uses the app's 100 ms interval with the configured bounded
pulse count. Cancellation always clears the held motor state. An explicit stop
ends the running command; it sends no unsupported opcode.

## Safety

This controls a moving staircase, not a bed. Automations should only run where
motion is safe, visible, and supervised.

## Follow-up

If M2 is not the correct actuator channel for a single-actuator installation, a
future follow-up may need the reporter's OKIN Smart Remote ID or QR contents to
map the actual channel. Do not add M3, reversed, DOT, or RF-gateway variants to
the stair profile without new evidence. Beds using FurniMove belong on its explicit app profile with their selected
handset ID.
