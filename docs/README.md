# v4 Documentation

These guides describe `main`. The integration requires **Home Assistant
2026.9.0+**. The release version lives in
[`manifest.json`](../custom_components/adjustable_bed/manifest.json) and
[`pyproject.toml`](../pyproject.toml).

## Installation and Everyday Use

| Guide | Contents |
|-------|----------|
| [Project README](../README.md) | Installation, supported beds, dashboard card and YAML options |
| [Compatibility and migration](HA_2026_9.md) | HA minimum, v3 backup/rollback, native child devices |
| [Connection guide](CONNECTION_GUIDE.md) | Discovery, adapters, proxies and Bluetooth bonds |
| [Configuration](CONFIGURATION.md) | Options, choosing your remote, combined beds and restoring standalone controls |
| [Actions and automations](SERVICES.md) | Memory, movement, side targeting and specialized actions |
| [Wake-up automation](WAKE_UP.md) | Importable scheduled raise or memory recall, with optional lighting |
| [Apple Home and Siri](HOMEKIT.md) | Importable control blueprint, HomeKit scenes and Siri Shortcuts |
| [Troubleshooting](TROUBLESHOOTING.md) | Card loading, connections, position feedback and migration problems |
| [Getting help](GETTING_HELP.md) | Support bundles, diagnostics, issue reports and app traffic captures |

## Controller and Protocol Reference

Start with the [Supported Beds table](../README.md#supported-beds), where related
brands, models and apps are grouped together. Use [Supported Actuators](SUPPORTED_ACTUATORS.md)
to identify your controller and compare features. The detailed guides in
[`beds/`](beds/) cover model-specific setup and testing status.

## Protocol Research

App-disposition ledgers in `beds/` and implementation records in `apk-analysis/`
preserve the scope and evidence of individual audits.

## Development and Validation

Work from `main` for v4 changes. Development uses Python **3.14.2+** with
`uv`, and Bun for the Lit/TypeScript card. Follow the environment and test commands
in the [v4 validation matrix](V4_VALIDATION.md#reproduce-automated-validation),
including the Bluetooth dependencies from Home Assistant's own manifests.

| Reference | Contents |
|-----------|----------|
| [Repository instructions](../AGENTS.md) | Architecture, controller contracts, contribution and release rules |
| [Command lifecycle](COMMAND_LIFECYCLE.md) | Serialization, cancellation, STOP, timed movement and connection handoff |
| [Paired runtimes and registry ownership](design/paired-runtime-and-registry.md) | Runtime interfaces and registry transfer/rollback |
| [v4 validation matrix](V4_VALIDATION.md) | Automated coverage and installed release-candidate gates |
| [Linak reversal assessment](design/linak-reversal-assessment.md) | Dated evidence and bounded follow-up |
| [APK Protocol Audit workflow](apk-analysis/phase4-coordinator-workflow.md) | Coordination and evidence gates |
| [Analysis tooling](apk-analysis/TOOLING.md) | Protocol-neutral decompiler setup and stack coverage |
| [Analyst prompt](apk-analysis/phase4-analyst-prompt.md) and [schema](apk-analysis/analysis.schema.json) | Pinned clean-room inputs |
| [Audit tooling](../tools/phase4_v2/README.md) and [preflight](../tools/phase4_v2/preflight/README.md) | Artifact identity, routing and historical inventory |

APK artifacts and frozen reports stay local and ignored. Consult the repository's
clean-room rules before protocol work. Documentation updates do not establish new
hardware evidence or complete the release-candidate gates.
