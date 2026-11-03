# Documentation

These guides describe `main`. The integration requires **Home Assistant
2026.9.0+**. The release version lives in
[`manifest.json`](../custom_components/adjustable_bed/manifest.json) and
[`pyproject.toml`](../pyproject.toml).

## Installation and Everyday Use

| Guide | Contents |
|-------|----------|
| [Project README](../README.md) | Installation, supported beds, dashboard card and YAML options |
| [Connection guide](CONNECTION_GUIDE.md) | Discovery, adapters, proxies and Bluetooth bonds |
| [Configuration](CONFIGURATION.md) | Options, choosing your remote, combined beds and restoring standalone controls |
| [Actions and automations](SERVICES.md) | Memory, movement, side targeting and specialized actions |
| [Wake-up automation](WAKE_UP.md) | Importable scheduled raise or memory recall, with optional lighting |
| [Apple Home and Siri](HOMEKIT.md) | Importable control blueprint, HomeKit scenes and Siri Shortcuts |
| [Troubleshooting](TROUBLESHOOTING.md) | Card loading, connections, position feedback and upgrade problems |
| [Getting help](GETTING_HELP.md) | Support bundles, diagnostics, issue reports and app traffic captures |

## Controller and Protocol Reference

Start with the [Supported Beds table](../README.md#supported-beds), where related
brands, models and apps are grouped together. Use [Supported Actuators](SUPPORTED_ACTUATORS.md)
to identify your controller and compare features. The detailed guides in
[`beds/`](beds/) cover model-specific setup and testing status.

## Protocol Research

App-disposition ledgers in `beds/` and implementation records in `apk-analysis/`
preserve the scope and evidence of individual audits.

The [S02 Sleeptracker disposition ledger](apk-analysis/dispositions/S02-sleeptracker.md)
maps the accepted 3.6.2 audit to the separate [processor integration](beds/sleeptracker.md),
including direct BLE controls, explicit exclusions and hardware validation status.

The [Adjustable Comfort M1X12 protocol guide](beds/starcode-m1x12.md) links its
sealed accepted evidence to the complete 970-ID implementation ledger.

The [cluster033 durable disposition ledger](beds/cluster033-dispositions.json) maps all
562 accepted discoveries to implementation symbols, focused tests, narrowly
credited baseline behavior or exact evidence-backed exclusions. The eight app
profiles and their hardware-unverified status remain indexed by the Supported
Beds table.

The [row030 OCTO Smart Control disposition ledger](apk-analysis/dispositions/row030-octo-smart-control.md)
maps the accepted 1.03.02 artifact to the existing OCTO Standard protocol, including
direct BLE controls, explicit exclusions and deferred hardware validation.

The [row042 Nectar Move ledger](apk-analysis/dispositions/row042-nectar-motion.md)
maps all 43 accepted comparison rows to implementation proof or exact exclusions.

The [row068 Glideaway Motion ledger](apk-analysis/dispositions/row068-glideaway-motion.md)
accounts for the accepted 1.0.3 revision01 commands, models, parsers, timing and
explicit safety/product exclusions.

## Development and Validation

Work from `main`. Development uses Python **3.14.2+** with `uv`, and Bun for
the Lit/TypeScript card. Follow the environment and test commands in the
[repository instructions](../AGENTS.md#running-tests), including the Bluetooth
dependencies from Home Assistant's own manifests.

| Reference | Contents |
|-----------|----------|
| [Repository instructions](../AGENTS.md) | Architecture, controller contracts, contribution and release rules |
| [Command lifecycle](COMMAND_LIFECYCLE.md) | Serialization, cancellation, STOP, timed movement and connection handoff |
| [Paired runtimes and registry ownership](design/paired-runtime-and-registry.md) | Runtime interfaces and registry transfer/rollback |
| [Linak reversal assessment](design/linak-reversal-assessment.md) | Dated evidence and bounded follow-up |
| [APK Protocol Audit workflow](apk-analysis/phase4-coordinator-workflow.md) | Coordination and evidence gates |
| [Analysis tooling](apk-analysis/TOOLING.md) | Protocol-neutral decompiler setup and stack coverage |
| [Analyst prompt](apk-analysis/phase4-analyst-prompt.md) and [schema](apk-analysis/analysis.schema.json) | Pinned clean-room inputs |
| [Audit tooling](../tools/phase4_v2/README.md) and [preflight](../tools/phase4_v2/preflight/README.md) | Artifact identity, routing and historical inventory |

APK artifacts and frozen reports stay local and ignored. Consult the repository's
clean-room rules before protocol work. Documentation updates do not establish new
hardware evidence.
