# Documentation

These guides describe version 5 of the integration. It requires **Home Assistant 2026.11.0+**. The release version lives in
[`manifest.json`](../custom_components/adjustable_bed/manifest.json) and
[`pyproject.toml`](../pyproject.toml).

## Installation and Everyday Use

| Guide | Contents |
|-------|----------|
| [Project README](../README.md) | Installation, features and the supported beds table |
| [Dashboard card](DASHBOARD_CARD.md) | Adding the card, holds and tap to move, paired and compact cards, editor and YAML options |
| [Connection guide](CONNECTION_GUIDE.md) | Discovery, adapters, proxies and Bluetooth bonds |
| [Configuration](CONFIGURATION.md) | Settings, choosing your app or remote, and combined beds |
| [Actions and automations](SERVICES.md) | Memory, movement, side targeting and specialized actions |
| [Estimated positions](ESTIMATED_POSITIONS.md) | Calibrated travel-time estimates and saved positions for beds without position feedback |
| [Wake-up automation](WAKE_UP.md) | Importable scheduled raise, memory recall or saved position, with optional lighting |
| [Apple Home and Siri](HOMEKIT.md) | Importable control blueprint, HomeKit scenes and Siri Shortcuts |
| [Troubleshooting](TROUBLESHOOTING.md) | Card loading, connections, position feedback and upgrade problems |
| [v5 breaking changes](V5_BREAKING_CHANGES.md) | What the 4.x to v5 upgrade migrates, adds and moves, and why a backup is the only rollback |
| [Getting help](GETTING_HELP.md) | Support bundles, diagnostics, issue reports and app traffic captures |

## Bed Guides

Start with the [Supported Beds table](../README.md#supported-beds), which groups
every app, remote and brand by bed family, or look up a brand in the
[brand lookup](SUPPORTED_ACTUATORS.md).

Each bed guide lists the apps and models it covers, the features, the setup
questions and the command tables, and records its testing status. Guides marked
**Shared** cover one command format that several apps use, with a section per
app. Every guide follows the [bed guide format](BED_GUIDE_FORMAT.md).

| Guide | Covers | Shared |
|-------|--------|--------|
| [Personal Comfort / Instant Comfort](beds/personal-comfort.md) | ANM and RA air units, Malouf and Reverie bases |
| [BedJet PowerLayer](beds/bedjet-powerlayer.md) | The BedJet PowerLayer adjustable frame | |
| [SILVERmotion Android](beds/silvermotion.md) | SILVERmotion Android SimplicityFrame beds | |
| [Casper Base](beds/casper-base.md) | The Casper Base app, sleep sensors and remote finder | |
| [CheersSleep](beds/cheerssleep.md) | The CheersSleep app | |
| [Solace and related apps](beds/ff_frame.md) | Solace remotes and apps, Sophie, Sealy FlexiRest, Woosa Sleep, BedSense and Motion Bed | Shared |
| [FurniMove / OKIN Smart Remote](beds/furnimove.md) | The FurniMove app and OKIN handset codes | |
| [GM Control](beds/gmmotor.md) | The GM Control app and sleep modules | |
| [Hush Base](beds/hush-base.md) | The Hush Base app, sleep sensors and remote finder | |
| [Jensen](beds/jensen.md) | The Jensen Adjustable Sleep app | |
| [Jiecang](beds/jiecang.md) | Jiecang remotes, Comfort Motion, the Dream apps and the LOGICDATA apps | Shared |
| [JMC400](beds/jmc.md) | Jensen JMC400 beds, from the Jensen and Svane Remote apps | Shared |
| [Kaidi](beds/kaidi.md) | Rize Beds, Rize Seat, Floyd Home, ISleep, KomfyD and ComfyDS | Shared |
| [Keeson](beds/keeson.md) | Keeson remotes, Ergomotion, Serta, Tempur, Purple, Sino, the ORE apps, Ergomotion 4.0, OrmatekTechnoSmart, Somos, Yamada and other Keeson-based apps | Shared |
| [Flexispot](beds/flexispot.md) | Flexispot app and EB632, EB703, EB704 and EB803 models | |
| [Langjue](beds/langjue.md) | The Comfort Smart Bed app | |
| [Leggett & Platt](beds/leggett-platt.md) | LP Control, LP Comfort Connect and the L&P remotes | |
| [Vindö](beds/vindo.md) | Carpe Diem Beds Vindö (Linak two-byte controls) |
| [Limoss](beds/limoss.md) | Limoss Remote, FSM Relax, Stawett and older Limoss controls | Shared |
| [Linak](beds/linak.md) | Linak Bed Control, Bed Connect and Performance Series | |
| [Linx](beds/linx.md) | The Linx app | |
| [LOGICDATA SimplicityFrame](beds/logicdata.md) | SILVERmotion / SimplicityFrame | |
| [LOGICDATA Sleep Smart](beds/logicdata-sleep-smart.md) | The Sleep Smart air mattress pump | |
| [M Line and Sinca Comfort Bed](beds/mline.md) | The M Line and Sinca Comfort Bed apps | Shared |
| [Malouf / Lucid](beds/malouf.md) | The Malouf Base and Lucid Base apps and receivers | Shared |
| [M3 Ambient](beds/ambient.md) | The M3 Ambient app, one-piece and split beds | |
| [MotoMotion, MotoSleep and others](beds/motomotion.md) | MotoMotion, MotoSleep, Power Bob, Bedgear, L2 Motion, MoodBase and ErgoBed Control | Shared |
| [Nerum](beds/nerum.md) | The Nerum app | |
| [OCTO Smart Control](beds/octo.md) | OCTO receivers, the RTV TV lift and Octo Remote Star2 | |
| [Nectar, Mattress Firm 900 and Sealy (Okin)](beds/okin-5a.md) | Nectar, Mattress Firm 900 / iFlex, Sealy Posturematic (the CB35 receiver and the Sealy Posturematic app) and DewertOkin ELEVATE | Shared |
| [Okin and DewertOkin](beds/okin-nframe.md) | Okimat, DewertOkin, Okin CST and DOT, Leggett & Platt Okin, Customatic, Jordan's, SIMMONS, Simmons Blue, SleepEase, StarCode AdjustableM5X4, Shuda, Okin 64-Bit, eShine E2000 to E5000, Superior sleep, Leva Bed Remote and other Okin apps | Shared |
| [Okin SoundWave and Symphony](beds/okin-soundwave.md) | Symphony Sleep Sense and the SoundWave pages | Shared |
| [OKIN Smart Sleep](beds/smart-sleep.md) | The OKIN Smart Sleep app | |
| [Paramount](beds/paramount.md) | The Paramount bed operation app | |
| [Personal Comfort](beds/personal-comfort.md) | Personal Comfort air units with their base | |
| [Restonic](beds/restonic.md) | The Restonic app, Prime, Lombar and Infinity layouts | |
| [Remacro](beds/remacro.md) | The Slumberland, The Brick and Jerome's apps | |
| [Reverie](beds/reverie.md) | The Reverie Nightstand app and Reverie receivers | |
| [Reverie Pairlink](beds/reverie-pairlink-sdk.md) | Reverie Pairlink (R510L / Harmoniq) | |
| [Likimio](beds/richmat.md#likimio) | The Likimio app and ABM10 beds | Shared |
| [Dorsal / Roomi](beds/richmat.md#dorsal--roomi) | The Dorsal app, saved Dorsal projects and Roomi controls | Shared |
| [Richmat](beds/richmat.md) | Richmat remotes, RMControl, Maxprime, BedTech and Bed Tech, BedSmart / X-Series, L&P MlRM and both L&P Adjustable Base apps, the Richmat MH apps, ENSO Sleep Control, HJBed, eShine E6000, Good Vibe Sleep, Lunio, Luuna, Majestic Home, MLILY, Saatva, Dream Sense Bed, Dreamlab Control, Super Colchones, SleepEvolution, S&S Base (Silk & Snow) and other Richmat-based apps | Shared |
| [RUF and related apps](beds/ruf-richmat-apps.md) | RUF Betten, W.Silver Products, AMERICANSTAR, Bailey's Bed Control and TX | |
| [Sleep Assist](beds/sleep-assistant.md) | The original Sleep Assist app | |
| [Sleep Assist Pro](beds/sleep-assist-pro.md) | The Sleep Assist Pro app and its five Bluetooth routes | |
| [Sleep Number](beds/sleep_number.md) | Sleep Number Fuzion and BAM/MCR bases ([commands](beds/sleep-number-services.md)) | |
| [SleepSpa S9000AI](beds/sleepstar.md) | The SleepSpa S9000AI | |
| [Sleeptracker](beds/sleeptracker.md) | The Tempur Sleeptracker-AI processor | |
| [Sleepy's Elite](beds/sleepys.md) | The MFRM Sleepy's Elite app and the BOX15, BOX24 and BOX25 receivers | |
| [Smart Comfort seats](beds/smart-comfort.md) | Smart Comfort by SYNARGY and Smart Comfort (SYNERGY) | |
| [Snore Monitor](beds/onlysnore.md) | The Snore Monitor app | |
| [StarCode Adjustable Comfort M1X12](beds/starcode-m1x12.md) | The Adjustable Comfort M1X12 app | |
| [StarCode AdjustableM5X5](beds/starcode-m5x5.md) | The AdjustableM5X5 app | |
| [SUTA](beds/suta.md) | SUTA Smart Home and trueMotion | Shared |
| [Svane Remote](beds/svane.md) | The Svane Remote app | |
| [TiMOTION AHF](beds/timotion-ahf.md) | TiMOTION AHF | |
| [Relax Motion](beds/relax-motion.md) | Relax Motion numeric models and app-page routes |
| [SmartBed app](beds/smartbed.md) | SmartBed receiver profiles and headboards |
| [Vibradorm](beds/vibradorm.md) | Vibradorm remotes, Caresse, Werkmeister, VMAT and V-MAT Basic | Shared |

## Design Notes

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

Development uses Python **3.14.2+** with `uv`, and Bun for
the Lit/TypeScript card. Follow the environment and test commands in the
[repository instructions](../AGENTS.md#running-tests), including the Bluetooth
dependencies from Home Assistant's own manifests.

| Reference | Contents |
|-----------|----------|
| [Repository instructions](../AGENTS.md) | Architecture, controller contracts, contribution and release rules |
| [Design notes](#design-notes) | Codecs and profiles, execution capabilities, command lifecycle and paired runtimes |
| [APK Protocol Audit workflow](apk-analysis/phase4-coordinator-workflow.md) | Coordination and evidence gates |
| [APK tracker rules](apk-analysis/TRACKERS.md) | What the #436, #443 and #447 issue bodies hold, and the guard that keeps them clean |
| [Analysis tooling](apk-analysis/TOOLING.md) | Protocol-neutral decompiler setup and stack coverage |
| [Analyst prompt](apk-analysis/phase4-analyst-prompt.md) and [schema](apk-analysis/analysis.schema.json) | Pinned clean-room inputs |

APK artifacts and frozen reports stay local and ignored. Consult the repository's
clean-room rules before protocol work. Documentation updates do not establish new
hardware evidence.
