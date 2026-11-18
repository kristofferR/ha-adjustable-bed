# Documentation

These guides describe `main`. The integration requires **Home Assistant
2026.11.0+**. The release version lives in
[`manifest.json`](../custom_components/adjustable_bed/manifest.json) and
[`pyproject.toml`](../pyproject.toml).

## Installation and Everyday Use

| Guide | Contents |
|-------|----------|
| [Project README](../README.md) | Installation, features and the supported beds table |
| [Dashboard card](DASHBOARD_CARD.md) | Adding the card, holds and tap to move, paired and compact cards, editor and YAML options |
| [Connection guide](CONNECTION_GUIDE.md) | Discovery, adapters, proxies and Bluetooth bonds |
| [Configuration](CONFIGURATION.md) | Options, choosing your remote, combined beds and restoring standalone controls |
| [Actions and automations](SERVICES.md) | Memory, movement, side targeting and specialized actions |
| [Estimated positions](ESTIMATED_POSITIONS.md) | Calibrated travel-time estimates and saved positions for beds without position feedback |
| [Wake-up automation](WAKE_UP.md) | Importable scheduled raise or memory recall, with optional lighting |
| [Apple Home and Siri](HOMEKIT.md) | Importable control blueprint, HomeKit scenes and Siri Shortcuts |
| [Troubleshooting](TROUBLESHOOTING.md) | Card loading, connections, position feedback and upgrade problems |
| [v5 breaking changes](V5_BREAKING_CHANGES.md) | What the 4.x to v5 upgrade migrates, adds and moves, and why a backup is the only rollback |
| [Getting help](GETTING_HELP.md) | Support bundles, diagnostics, issue reports and app traffic captures |

## Controller and Protocol Reference

Start with the [Supported Beds table](../README.md#supported-beds), which groups
every app, remote and brand by the family setup shows. Use [Supported Actuators](SUPPORTED_ACTUATORS.md)
to identify your controller and compare features.

Bed support is split into wire codecs and app profiles: a wire format shared by
several apps is encoded once, and each app or legacy route is a profile over it.
Each codec has one guide, with a section per profile:

| Codec guide | Profiles for |
|-------------|--------------|
| [Jiecang](beds/jiecang.md) | Jiecang, Comfort Motion, the Dream apps and the LOGICDATA apps |
| [Linx](beds/linx.md) | Linx 2.5 Q and Orbes, independent A00A / UART BLE routes |
| [Keeson](beds/keeson.md) | Keeson, Ergomotion, Serta, the Keeson-based apps, Ergomotion 4.0, OrmatekTechnoSmart and アシステック / Yamada |
| [Symphony Sleep Sense / Okin SoundWave](beds/okin-soundwave.md) | Explicit Symphony products and selectors over proven Keeson, N-frame and SoundWave carriers |
| [Okin N-frame](beds/okin-nframe.md) | Okimat, DewertOkin, Okin CB24/CST/DOT, Leggett & Platt Okin, Customatic, Jordan's, SIMMONS, SleepEase, AdjustableM5X4, Okin 64-Bit, Adjustable bed (Lumbar), Resident Adjustable Base, N32 Motion Bed, eShine and Comfort Enhancement 3 / Comfort Plus3 |
| [Okin 5A](beds/okin-5a.md) | Nectar, Mattress Firm 900, Okin CB35 and DewertOkin ELEVATE |
| [Malouf](beds/malouf.md) | Malouf and the Malouf Base / Lucid Base apps |
| [Richmat](beds/richmat.md) | Richmat, RMControl, BedTech, L&P MlRM, the L&P legacy app, the Richmat MH apps, HJBed, Eshine, Good Vibe Sleep, Casper Base, Hush Base, Luuna +, [SleepEvolution and W.Silver Products 3.x (fixed ASCII)](beds/richmat.md#sleepevolution--wsilver-products-3x) |
| [Limoss](beds/limoss.md) | Limoss, Limoss Remote and FSM Relax |
| [FFFF frame](beds/ff_frame.md) | Solace, Sophie, Woosa Sleep, BedSense and Motion Bed |
| [HHC `$#` frames](beds/motomotion.md) | MotoMotion, MotoSleep, Power Bob, Bedgear and L2 Motion |
| [JMC400](beds/jmc.md) | Jensen JMC400 and the Svane Remote app's JMC400 route |
| [Kaidi](beds/kaidi.md) | Rize Beds, Rize Seat, Floyd Home, ISleep, KomfyD and ComfyDS |
| [Vibradorm](beds/vibradorm.md) | Vibradorm, Caresse, Werkmeister, VMAT and V-MAT Basic |
| [CheersSleep](beds/cheerssleep.md) | CheersSleep P1 and P2, all 36 model keys |
| [OKIN Smart Sleep](beds/smart-sleep.md) | OKIN Smart Sleep legacy P1 and new P2 |
| [Nerum](beds/nerum.md) | Nerum P1 ORE, P2 Okin and P3 Smartbed profiles |
| [Snore Monitor BED](beds/onlysnore.md) | Snore Monitor direct BED controls and local alarms |
| [M Line](beds/mline.md) | M Line Sleep, Smart, Smart Sainuo, Okin and fallback selectors |
| [Smart Comfort seats](beds/smart-comfort.md) | Smart Comfort by SYNARGY and Smart Comfort (SYNERGY) |
| [Personal Comfort](beds/personal-comfort.md) | Personal Comfort air units and bases |
| [SUTA](beds/suta.md) | SUTA Smart Home name-selected P1 text and P2 mattress/heating profiles |
| [BedJet PowerLayer](beds/bedjet-powerlayer.md) | BedJet PowerLayer |

Beds with their own wire format have their own guide in [`beds/`](beds/). Every
guide follows the [bed guide format](BED_GUIDE_FORMAT.md) and records its
testing status.

| Design note | Contents |
|-------------|----------|
| [Protocol codecs and app profiles](design/protocol-codecs.md) | The codec, profile and controller layers, family registration, the app catalog convention, the vector harness and execution capabilities |
| [Bluetooth discovery hints](design/discovery-hints.md) | Per-family hints, the generated manifest matchers and detection's first pass |
| [Profile ids and schema 5](design/profile-id.md) | The profile id each entry and paired side runs, its migration record and which aliases share one |
| [Command lifecycle](COMMAND_LIFECYCLE.md) | Serialization, cancellation, STOP, timed movement and connection handoff |
| [Paired runtimes and registry ownership](design/paired-runtime-and-registry.md) | Runtime interfaces and registry transfer and rollback |
| [Guided setup changes](design/guided-setup-changes.md) | Staged app and layout changes, Repairs, Keep and the paired split rules |
| [Setup questions](design/setup-questions.md) | Profile-declared setup questions, owned generic fields and the generic setup step |

## Development and Validation

Work from `main`. Development uses Python **3.14.2+** with `uv`, and Bun for
the Lit/TypeScript card. Follow the environment and test commands in the
[repository instructions](../AGENTS.md#running-tests), including the Bluetooth
dependencies from Home Assistant's own manifests.

| Reference | Contents |
|-----------|----------|
| [Repository instructions](../AGENTS.md) | Architecture, controller contracts, contribution and release rules |
| [Design notes](#controller-and-protocol-reference) | Codecs and profiles, execution capabilities, command lifecycle and paired runtimes |
| [APK Protocol Audit workflow](apk-analysis/phase4-coordinator-workflow.md) | Coordination and evidence gates |
| [APK tracker rules](apk-analysis/TRACKERS.md) | What the #436, #443 and #447 issue bodies hold, and the guard that keeps them clean |
| [Analysis tooling](apk-analysis/TOOLING.md) | Protocol-neutral decompiler setup and stack coverage |
| [Analyst prompt](apk-analysis/phase4-analyst-prompt.md) and [schema](apk-analysis/analysis.schema.json) | Pinned clean-room inputs |

APK artifacts and frozen reports stay local and ignored. Consult the repository's
clean-room rules before protocol work. Documentation updates do not establish new
hardware evidence.
