// Native Lovelace card for the Adjustable Bed integration. Generic across all
// supported bed types: it discovers a device's entities (by translation_key) and
// renders only the sections that exist. Styling comes entirely from Home
// Assistant theme variables so it inherits the user's theme.
import {
  LitElement,
  type PropertyValues,
  type TemplateResult,
  css,
  html,
  nothing,
} from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  type BedGraphicTone,
  type DualBedGraphicSide,
  renderBedGraphic,
  renderDualBedGraphic,
} from "./bed-graphic";
import {
  PLATFORM,
  SECTION_ORDER,
  bedEntitiesForDevice,
  bedIsEmpty,
  isSingleAddressPairedDevice,
  pairedChildDeviceIds,
  resolvePairedParentId,
} from "./discovery";
import { localize } from "./localize";
import {
  type AdjustableBedCardConfig,
  type BedEntities,
  CARD_VERSION,
  type HassEntity,
  type HomeAssistant,
  type MemorySlot,
  type MotorEntity,
} from "./types";
// Side-effect import: registers <adjustable-bed-card-editor> in the same bundle.
import "./editor";

interface PairedPane {
  key: string;
  label: string;
  icon: string;
  bed: BedEntities;
  graphicTone?: BedGraphicTone;
}

interface BedGraphicState extends DualBedGraphicSide {
  upperMotor: MotorEntity;
  lowerMotor: MotorEntity;
}

type ConnectionStatus = "connected" | "idle" | "disconnected";
type SynchronizeSide = "left" | "right";

const SYNCHRONIZABLE_MOTORS = new Set(["back", "legs", "head", "feet"]);

@customElement("adjustable-bed-card")
export class AdjustableBedCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @state() private _config?: AdjustableBedCardConfig;
  // Transient UI state: when true, tapping a memory tile saves the current bed
  // position into that slot instead of recalling it.
  // Which memory section (by its stable per-section key) is currently in save
  // mode. Scoped per section so pressing "Save…" on one paired side does NOT flip
  // the other side's / both-sides' tiles into save actions (which risked saving
  // over the wrong preset). undefined = no section in save mode.
  @state() private _saveModeFor?: string;
  // Paired beds expose one focused control surface at a time. This avoids the
  // old three-bed vertical stack while keeping combined actions deliberately
  // separate from commands for an individual side.
  @state() private _activePairedPane = "both";
  @state() private _synchronizingTo?: SynchronizeSide;

  private _watched: string[] = [];

  public static async getConfigElement(): Promise<HTMLElement> {
    return document.createElement("adjustable-bed-card-editor");
  }

  public static getStubConfig(hass?: HomeAssistant): AdjustableBedCardConfig {
    const deviceId = hass
      ? Object.values(hass.entities).find((e) => e.platform === PLATFORM)
          ?.device_id
      : undefined;
    return { type: "custom:adjustable-bed-card", device_id: deviceId };
  }

  public setConfig(config: AdjustableBedCardConfig): void {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
  }

  public getCardSize(): number {
    return 8;
  }

  protected override shouldUpdate(changed: PropertyValues): boolean {
    // Local UI changes can be coalesced with Home Assistant's frequent `hass`
    // assignment. Never let the watched-entity optimization discard a tab or
    // save-mode interaction just because `hass` changed in the same cycle.
    if (
      changed.has("_config") ||
      changed.has("_saveModeFor") ||
      changed.has("_activePairedPane") ||
      changed.has("_synchronizingTo")
    )
      return true;
    if (!changed.has("hass") || !this.hass) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || old.entities !== this.hass.entities) return true;
    // Paired detection (pairedChildDeviceIds) reads the device registry, so a
    // registry change — sides linked/relinked or a device renamed — must
    // re-render even when no entity or watched state changed.
    if (old.devices !== this.hass.devices) return true;
    for (const id of this._watched) {
      if (old.states[id] !== this.hass.states[id]) return true;
    }
    return false;
  }

  protected override render() {
    if (!this.hass || !this._config) return nothing;
    if (!this._config.device_id) return this._notice("card.no_device");

    // A paired "Dual Bed": render the combined "both sides" controls (on the
    // parent device) plus a per-side section for each child device. The config
    // may point at the synthetic parent OR at one side's child device — resolve
    // a side up to its parent so either renders the whole pair. Falls back to
    // single-device rendering for a non-paired bed.
    const parentId = resolvePairedParentId(this.hass, this._config.device_id);
    const childIds = pairedChildDeviceIds(this.hass, parentId);
    if (parentId && childIds.length) return this._renderPaired(parentId, childIds);
    if (
      this._config.device_id &&
      isSingleAddressPairedDevice(this.hass, this._config.device_id)
    )
      return this._renderSingleAddressPaired(this._config.device_id);

    const bed = bedEntitiesForDevice(this.hass, this._config.device_id);
    this._watched = this._collectWatched(bed);

    if (bedIsEmpty(bed)) return this._notice("card.no_entities");

    return html`
      <ha-card>
        ${this._header(bed)}
        ${this._renderSections(bed)}
      </ha-card>
    `;
  }

  // The ordered section templates for a single bed (shared by single-device and
  // each per-side block of a paired bed).
  private _renderSections(
    bed: BedEntities,
    graphicTone: BedGraphicTone = "theme",
  ): (typeof nothing | TemplateResult)[] {
    const c = this._config!;
    const render: Record<string, () => typeof nothing | TemplateResult> = {
      graphic: () =>
        c.show_graphic !== false ? this._graphic(bed, graphicTone) : nothing,
      motors: () => (c.show_motors !== false ? this._motors(bed) : nothing),
      firmness: () => (c.show_firmness !== false ? this._firmness(bed) : nothing),
      presets: () => (c.show_presets !== false ? this._presets(bed) : nothing),
      memory: () => (c.show_memory !== false ? this._memory(bed) : nothing),
      lighting: () => (c.show_lighting !== false ? this._lighting(bed) : nothing),
      massage: () => (c.show_massage !== false ? this._massage(bed) : nothing),
      utility: () => (c.show_utility !== false ? this._utility(bed) : nothing),
      climate: () => (c.show_climate !== false ? this._climate(bed) : nothing),
      connection: () =>
        c.show_connection !== false ? this._connection(bed) : nothing,
    };
    return this._orderedSections().map((k) => render[k]?.() ?? nothing);
  }

  // Render a paired parent as a focused side switcher. The combined actions live
  // on the synthetic parent; each physical side remains on its child device.
  private _renderPaired(parentId: string, childIds: string[]): TemplateResult {
    const hass = this.hass!;
    const parentBed = bedEntitiesForDevice(hass, parentId);
    const sides = childIds.map((id, index) => ({
      key: id,
      label: this._deviceLabel(id),
      icon: "mdi:bed-single-outline",
      bed: bedEntitiesForDevice(hass, id),
      graphicTone: index === 0 ? ("left" as const) : ("right" as const),
    }));
    this._watched = [parentBed, ...sides.map((s) => s.bed)].flatMap((b) =>
      this._collectWatched(b),
    );

    // Preserve the single-bed fallback: if neither the parent nor any side
    // exposes renderable entities, show the notice instead of a header-only card.
    if (bedIsEmpty(parentBed) && sides.every((s) => bedIsEmpty(s.bed)))
      return this._notice("card.no_entities");

    return this._renderPairedCard(parentId, [
      {
        key: "both",
        label: localize(hass, "card.both_sides"),
        icon: "mdi:link-variant",
        bed: parentBed,
      },
      ...sides,
    ]);
  }

  private _renderSingleAddressPaired(deviceId: string): TemplateResult {
    const hass = this.hass!;
    const beds = {
      both: bedEntitiesForDevice(hass, deviceId, "both"),
      left: bedEntitiesForDevice(hass, deviceId, "left"),
      right: bedEntitiesForDevice(hass, deviceId, "right"),
    };
    this._watched = Object.values(beds).flatMap((bed) =>
      this._collectWatched(bed),
    );
    if (Object.values(beds).every((bed) => bedIsEmpty(bed)))
      return this._notice("card.no_entities");

    return this._renderPairedCard(deviceId, [
      {
        key: "both",
        label: localize(hass, "card.both_sides"),
        icon: "mdi:link-variant",
        bed: beds.both,
      },
      {
        key: "left",
        label: localize(hass, "card.left_side"),
        icon: "mdi:bed-single-outline",
        bed: beds.left,
        graphicTone: "left",
      },
      {
        key: "right",
        label: localize(hass, "card.right_side"),
        icon: "mdi:bed-single-outline",
        bed: beds.right,
        graphicTone: "right",
      },
    ]);
  }

  private _renderPairedCard(
    titleDeviceId: string,
    allPanes: PairedPane[],
  ): TemplateResult {
    const panes = allPanes.filter((pane) => !bedIsEmpty(pane.bed));
    const active =
      panes.find((pane) => pane.key === this._activePairedPane) ?? panes[0];
    const sidePanes = panes.filter((pane) => pane.key !== "both");
    const combined = active.key === "both";
    return html`
      <ha-card class="paired-card">
        ${this._header(active.bed, titleDeviceId)}
        <div
          class="pane-tabs"
          role="tablist"
          style=${`--pane-count:${panes.length}`}
        >
          ${panes.map(
            (pane) => html`
              <button
                class="pane-tab ${pane.key === active.key ? "active" : ""}"
                role="tab"
                aria-selected=${pane.key === active.key ? "true" : "false"}
                @click=${() => this._selectPairedPane(pane.key)}
              >
                <ha-icon icon=${pane.icon}></ha-icon>
                <span>${pane.label}</span>
                ${this._connectionDot(pane.bed)}
              </button>
            `,
          )}
        </div>
        <div class="pane" role="tabpanel" aria-label=${active.label}>
          ${combined && this._config?.show_graphic !== false
            ? this._pairedOverview(titleDeviceId, sidePanes)
            : nothing}
          ${this._renderSections(active.bed, active.graphicTone)}
          ${combined && this._config?.show_lighting !== false
            ? this._combinedLighting(active.bed, sidePanes)
            : nothing}
          ${combined && this._config?.show_connection !== false
            ? this._combinedBluetooth(sidePanes)
            : nothing}
        </div>
      </ha-card>
    `;
  }

  private _selectPairedPane(key: string): void {
    if (this._activePairedPane === key) return;
    this._activePairedPane = key;
    // Save mode is intentionally local to the visible side. Leaving a side
    // cancels it so returning later can never expose a stale destructive mode.
    this._saveModeFor = undefined;
  }

  private _connectionStatus(bed: BedEntities): ConnectionStatus | undefined {
    if (!bed.connectivity) return undefined;
    const state = this._state(bed.connectivity);
    return state?.state === "on"
      ? "connected"
      : state?.attributes?.state_detail === "idle"
        ? "idle"
        : "disconnected";
  }

  private _connectionDot(bed: BedEntities): typeof nothing | TemplateResult {
    const status = this._connectionStatus(bed);
    if (!status) return nothing;
    return html`<span
      class="connection-dot ${status}"
      title=${localize(this.hass, `status.${status}`)}
    ></span>`;
  }

  private _pairedOverview(
    parentDeviceId: string,
    sidePanes: PairedPane[],
  ): typeof nothing | TemplateResult {
    const sides = sidePanes
      .map((pane) => ({ pane, graphic: this._graphicState(pane.bed) }))
      .filter(
        (item): item is { pane: PairedPane; graphic: BedGraphicState } =>
          item.graphic !== undefined,
      );
    if (sides.length < 2) return nothing;
    const [left, right] = sides;
    return html`
      <div class="graphic dual-graphic">
        ${renderDualBedGraphic({
          left: left.graphic,
          right: right.graphic,
        })}
      </div>
      <div class="dual-readouts">
        ${[left, right].map(
          ({ pane, graphic }, index) => html`
            <div class="dual-readout side-${index === 0 ? "left" : "right"}">
              <span class="dual-side-name">
                <span class="dual-swatch"></span>${pane.label}
              </span>
              <span class="dual-position">
                ${this._positionSummary(graphic)}
              </span>
            </div>
          `,
        )}
      </div>
      ${this._synchronizeSelector(parentDeviceId, left.pane, right.pane)}
    `;
  }

  private _synchronizeSelector(
    parentDeviceId: string,
    left: PairedPane,
    right: PairedPane,
  ): typeof nothing | TemplateResult {
    const leftPlan = this._synchronizationPlan(left.bed, right.bed);
    const rightPlan = this._synchronizationPlan(right.bed, left.bed);
    if (leftPlan.length === 0 && rightPlan.length === 0) return nothing;

    const busy = this._synchronizingTo !== undefined;
    return html`
      <div class="dual-sync-row">
        <ha-icon icon="mdi:sync"></ha-icon>
        <span class="dual-sync-label">${localize(this.hass, "sync.label")}</span>
        <div class="dual-sync-actions">
          <button
            class="dual-sync-btn side-left ${
              this._synchronizingTo === "left" ? "is-active" : ""
            }"
            aria-label="${localize(this.hass, "sync.label")} ${left.label}"
            aria-busy=${this._synchronizingTo === "left" ? "true" : "false"}
            ?disabled=${busy || leftPlan.length === 0}
            @click=${() =>
              void this._synchronizePositions(parentDeviceId, left, right, "left")}
          >
            ${this._synchronizingTo === "left"
              ? html`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`
              : html`<span class="dual-swatch"></span>`}
            <span>${left.label}</span>
          </button>
          <button
            class="dual-sync-btn side-right ${
              this._synchronizingTo === "right" ? "is-active" : ""
            }"
            aria-label="${localize(this.hass, "sync.label")} ${right.label}"
            aria-busy=${this._synchronizingTo === "right" ? "true" : "false"}
            ?disabled=${busy || rightPlan.length === 0}
            @click=${() =>
              void this._synchronizePositions(parentDeviceId, left, right, "right")}
          >
            ${this._synchronizingTo === "right"
              ? html`<ha-icon class="dual-sync-spinner" icon="mdi:loading"></ha-icon>`
              : html`<span class="dual-swatch"></span>`}
            <span>${right.label}</span>
          </button>
        </div>
      </div>
    `;
  }

  private _synchronizationPlan(
    source: BedEntities,
    target: BedEntities,
  ): { motor: string; position: number }[] {
    const targetMotors = new Set(target.motors.map((motor) => motor.key));
    const shared = source.motors.filter(
      (motor) =>
        SYNCHRONIZABLE_MOTORS.has(motor.key) &&
        targetMotors.has(motor.key) &&
        (motor.angle !== undefined || motor.position !== undefined),
    );
    if (shared.length === 0) return [];

    const plan = shared.map((motor) => ({
      motor: motor.key,
      position: this._angle(motor),
    }));
    // Never perform a partial synchronization. If one shared motor's feedback
    // is unavailable, disable that reference side until all positions are known.
    if (plan.some((item) => item.position === undefined)) return [];
    return plan as { motor: string; position: number }[];
  }

  private async _synchronizePositions(
    parentDeviceId: string,
    left: PairedPane,
    right: PairedPane,
    sourceSide: SynchronizeSide,
  ): Promise<void> {
    if (this._synchronizingTo || !this.hass) return;
    const source = sourceSide === "left" ? left : right;
    const target = sourceSide === "left" ? right : left;
    const targetSide: SynchronizeSide =
      sourceSide === "left" ? "right" : "left";
    const plan = this._synchronizationPlan(source.bed, target.bed);
    if (plan.length === 0) return;

    this._synchronizingTo = sourceSide;
    try {
      for (const item of plan) {
        await this.hass.callService(PLATFORM, "set_position", {
          device_id: [parentDeviceId],
          motor: item.motor,
          position: item.position,
          side: targetSide,
        });
      }
    } catch {
      // Home Assistant surfaces service errors through its own notification UI.
    } finally {
      this._synchronizingTo = undefined;
    }
  }

  private _positionSummary(graphic: BedGraphicState): string {
    const motors =
      graphic.upperMotor === graphic.lowerMotor
        ? [graphic.upperMotor]
        : [graphic.upperMotor, graphic.lowerMotor];
    return motors
      .map((motor) => {
        const value = this._readout(motor);
        return value ? `${this._motorName(motor)} ${value}` : this._motorName(motor);
      })
      .join(" · ");
  }

  private _combinedLighting(
    parentBed: BedEntities,
    sidePanes: PairedPane[],
  ): typeof nothing | TemplateResult {
    // Prefer a native combined light when the protocol exposes one; it already
    // renders in the parent's normal Lighting section.
    if (this._hasLighting(parentBed)) return nothing;
    const lights = sidePanes
      .map((pane) => this._mainLight(pane.bed))
      .filter((id): id is string => id !== undefined);
    if (lights.length === 0) return nothing;
    const onCount = lights.filter((id) => this._state(id)?.state === "on").length;
    const allOn = onCount === lights.length;
    const anyOn = onCount > 0;
    const statusKey = allOn
      ? "combined.on"
      : anyOn
        ? "combined.mixed"
        : "combined.off";
    const label = localize(this.hass, "combined.lights");
    return html`
      ${this._heading("section.lighting")}
      <div class="entity-row combined-entity-row">
        <ha-icon
          class="icon ${anyOn ? "active" : ""}"
          icon="mdi:lightbulb-group-outline"
        ></ha-icon>
        <div class="entity-row-text">
          <span>${label}</span>
          <span class="secondary">${localize(this.hass, statusKey)}</span>
        </div>
        <button
          class="toggle ${anyOn ? "on" : ""} ${anyOn && !allOn ? "mixed" : ""}"
          role="switch"
          aria-label=${label}
          aria-checked=${allOn ? "true" : "false"}
          @click=${() => this._setEntities(lights, !allOn)}
        >
          <span class="knob"></span>
        </button>
      </div>
    `;
  }

  private _combinedBluetooth(
    sidePanes: PairedPane[],
  ): typeof nothing | TemplateResult {
    const connections = sidePanes
      .filter((pane) => pane.bed.connectivity)
      .map((pane) => ({ pane, entityId: pane.bed.connectivity! }));
    if (connections.length === 0) return nothing;
    return html`
      ${this._heading("section.bluetooth")}
      <div class="bluetooth-grid">
        ${connections.map(({ pane, entityId }) => {
          const status = this._connectionStatus(pane.bed)!;
          const state = this._state(entityId);
          const rssi = state?.attributes.rssi;
          return html`
            <button
              class="bluetooth-status ${status}"
              @click=${() => this._moreInfo(entityId)}
            >
              <ha-icon
                icon=${status === "connected"
                  ? "mdi:bluetooth-connect"
                  : status === "idle"
                    ? "mdi:bluetooth"
                    : "mdi:bluetooth-off"}
              ></ha-icon>
              <span class="bluetooth-copy">
                <span>${pane.label}</span>
                <span class="bluetooth-detail">
                  ${localize(this.hass, `status.${status}`)}${
                    typeof rssi === "number" ? ` · ${rssi} dBm` : ""
                  }
                </span>
              </span>
            </button>
          `;
        })}
      </div>
    `;
  }

  private _mainLight(bed: BedEntities): string | undefined {
    return bed.lights.light ?? bed.lights.switch;
  }

  private _hasLighting(bed: BedEntities): boolean {
    const lights = bed.lights;
    return !!(
      lights.light ||
      lights.switch ||
      lights.level ||
      lights.timer ||
      lights.toggle ||
      lights.cycle
    );
  }

  private _deviceLabel(id: string): string {
    const d = this.hass?.devices[id];
    return d?.name_by_user ?? d?.name ?? id;
  }

  // Section keys in render order: the configured order first, then any default
  // sections the config didn't mention (so new sections are never dropped).
  private _orderedSections(): string[] {
    const cfg = this._config?.section_order;
    if (!cfg?.length) return [...SECTION_ORDER];
    const known = new Set<string>(SECTION_ORDER);
    const head = cfg.filter((k) => known.has(k));
    const tail = SECTION_ORDER.filter((k) => !head.includes(k));
    return [...head, ...tail];
  }

  // ---- sections -----------------------------------------------------------

  private _header(bed: BedEntities, titleDeviceId?: string): TemplateResult {
    // Three connectivity states. "idle" means the bed intentionally dropped the
    // BLE link (idle timeout / manual disconnect) and reconnects on demand on the
    // next command — surfaced via the sensor's `state_detail` attribute (issue
    // #385) so an expected disconnect doesn't read as a fault.
    const conn = this._connectionStatus(bed);
    const CONN_META = {
      connected: { cls: "ok", icon: "mdi:bluetooth-connect", key: "status.connected" },
      idle: { cls: "idle", icon: "mdi:bluetooth", key: "status.idle" },
      disconnected: { cls: "off", icon: "mdi:bluetooth-off", key: "status.disconnected" },
    } as const;
    return html`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title(titleDeviceId)}</span>
        ${
          conn === undefined
            ? nothing
            : html`
                <button
                  class="conn ${CONN_META[conn].cls}"
                  @click=${() => this._moreInfo(bed.connectivity!)}
                  title=${localize(this.hass, CONN_META[conn].key)}
                >
                  <ha-icon icon=${CONN_META[conn].icon}></ha-icon>
                </button>
              `
        }
      </div>
    `;
  }

  private _graphic(
    bed: BedEntities,
    tone: BedGraphicTone = "theme",
  ): typeof nothing | TemplateResult {
    const graphic = this._graphicState(bed);
    if (!graphic) return nothing;
    return html`
      <div class="graphic">
        ${renderBedGraphic(graphic, tone)}
      </div>
    `;
  }

  private _graphicState(bed: BedEntities): BedGraphicState | undefined {
    const withAngle = bed.motors.filter((m) => m.angle);
    if (withAngle.length === 0) return undefined;
    const upper =
      bed.motors.find((m) => m.key === "back") ??
      bed.motors.find((m) => m.key === "head") ??
      withAngle[0];
    const lower =
      bed.motors.find((m) => m.key === "legs") ??
      bed.motors.find((m) => m.key === "feet") ??
      withAngle[withAngle.length - 1];
    const moving = bed.motors.some((m) => {
      const s = m.cover ? this._state(m.cover)?.state : undefined;
      return s === "opening" || s === "closing";
    });
    return {
      upperMotor: upper,
      lowerMotor: lower,
      upper: { label: this._motorName(upper), angle: this._angle(upper) },
      lower: { label: this._motorName(lower), angle: this._angle(lower) },
      moving,
    };
  }

  private _motors(bed: BedEntities): typeof nothing | TemplateResult {
    const motors = bed.motors.filter((m) => m.cover || m.up || m.down);
    // Beds with direct target numbers (and no cover) get a settable row instead.
    const positionRows = bed.motors.filter(
      (m) => !m.cover && !m.up && !m.down && m.position,
    );
    if (
      motors.length === 0 &&
      positionRows.length === 0 &&
      !bed.synchro &&
      !bed.stop
    )
      return nothing;
    const hasRows = motors.length > 0 || positionRows.length > 0 || !!bed.synchro;
    return html`
      ${hasRows ? this._heading("section.position") : nothing}
      ${bed.synchro ? this._toggleRow(bed.synchro) : nothing}
      ${
        motors.length
          ? html`<div class="rows">
              ${motors.map((m) => this._motorRow(m, bed.stop))}
            </div>`
          : nothing
      }
      ${
        positionRows.length
          ? html`<div class="rows">
              ${positionRows.map((m) => this._moreInfoRow(m.position!))}
            </div>`
          : nothing
      }
      ${
        bed.stop
          ? html`<button class="stop-all" @click=${() => this._press(bed.stop!)}>
              <ha-icon icon="mdi:stop"></ha-icon>
              <span>${localize(this.hass, "action.stop_all")}</span>
            </button>`
          : nothing
      }
    `;
  }

  private _firmness(bed: BedEntities): typeof nothing | TemplateResult {
    if (bed.firmness.length === 0) return nothing;
    return html`
      ${this._heading("section.firmness")}
      <div class="rows">${bed.firmness.map((id) => this._moreInfoRow(id))}</div>
    `;
  }

  // `stopId` is the STOP entity for the bed this row belongs to (a side's own
  // stop for a paired side, the parent's stop_both for the combined block) —
  // passed in rather than read from this._bed, which during a paired render
  // points at the parent for every side.
  private _motorRow(m: MotorEntity, stopId?: string): TemplateResult {
    const readout = this._readout(m);
    const upId = m.cover ?? m.up;
    const downId = m.cover ?? m.down;
    const canStop = !!m.cover || !!stopId;
    return html`
      <div class="row">
        <div class="row-label">
          <span>${this._motorName(m)}</span>
          ${readout ? html`<span class="readout">${readout}</span>` : nothing}
        </div>
        <div class="control-group">
          <button
            class="cg-btn"
            aria-label=${localize(this.hass, "action.up")}
            @click=${() => this._motorAction(m, "up")}
            ?disabled=${!upId}
          >
            <ha-icon icon="mdi:chevron-up"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${localize(this.hass, "action.stop")}
            @click=${() => this._motorStop(m, stopId)}
            ?disabled=${!canStop}
          >
            <ha-icon icon="mdi:stop"></ha-icon>
          </button>
          <button
            class="cg-btn"
            aria-label=${localize(this.hass, "action.down")}
            @click=${() => this._motorAction(m, "down")}
            ?disabled=${!downId}
          >
            <ha-icon icon="mdi:chevron-down"></ha-icon>
          </button>
        </div>
      </div>
    `;
  }

  private _presets(bed: BedEntities): typeof nothing | TemplateResult {
    if (bed.presets.length === 0) return nothing;
    return html`
      ${this._heading("section.presets")}
      <div class="tiles">
        ${bed.presets.map((id) => this._tile(id, () => this._press(id)))}
      </div>
    `;
  }

  private _utility(bed: BedEntities): typeof nothing | TemplateResult {
    if (bed.utility.length === 0) return nothing;
    return html`
      ${this._heading("section.utility")}
      <div class="tiles">
        ${bed.utility.map((id) => this._tile(id, () => this._press(id)))}
      </div>
    `;
  }

  private _memory(bed: BedEntities): typeof nothing | TemplateResult {
    let slots = bed.memory;
    const selected = this._config?.memory_slots;
    if (selected && selected.length) {
      const want = new Set(selected.map(Number));
      slots = slots.filter((s) => want.has(s.slot));
    }
    if (slots.length === 0) return nothing;
    const canSave =
      this._config?.memory_save !== false && slots.some((s) => s.save);
    // A stable key for THIS memory section (its slots' own entity ids), so save
    // mode is scoped to the section the user tapped, not shared globally.
    const sectionKey = slots
      .map((s) => s.save ?? s.goto ?? String(s.slot))
      .join("|");
    const saveMode = this._saveModeFor === sectionKey;
    return html`
      <div class="section-heading heading-row">
        <span>${localize(this.hass, "section.memory")}</span>
        ${
          canSave
            ? html`<button
                class="set-btn ${saveMode ? "active" : ""}"
                @click=${() => this._toggleSaveMode(sectionKey)}
              >
                <ha-icon
                  icon=${saveMode ? "mdi:close" : "mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${localize(this.hass, saveMode ? "memory.cancel" : "memory.set")}</span>
              </button>`
            : nothing
        }
      </div>
      ${
        saveMode
          ? html`<div class="hint">${localize(this.hass, "memory.set_hint")}</div>`
          : nothing
      }
      <div class="tiles">${slots.map((s) => this._memoryTile(s, saveMode))}</div>
    `;
  }

  private _memoryTile(slot: MemorySlot, saveMode: boolean): TemplateResult {
    const labelId = slot.goto ?? slot.save!;
    if (saveMode) {
      const savable = !!slot.save;
      return html`
        <button
          class="tile ${savable ? "save-mode" : "is-disabled"}"
          ?disabled=${!savable}
          @click=${() => savable && this._saveMemory(slot)}
        >
          <ha-icon class="icon" icon="mdi:content-save"></ha-icon>
          <span class="tile-label">${this._name(labelId)}</span>
        </button>
      `;
    }
    // Only a real goto recalls; a save-only slot must not be saved by a plain
    // tap (that requires Save mode), so its tile is disabled here.
    const canRecall = !!slot.goto;
    return html`
      <button
        class="tile ${canRecall ? "" : "is-disabled"}"
        ?disabled=${!canRecall}
        @click=${() => slot.goto && this._press(slot.goto)}
      >
        ${this._icon(labelId)}
        <span class="tile-label">${this._name(labelId)}</span>
      </button>
    `;
  }

  private _lighting(bed: BedEntities): typeof nothing | TemplateResult {
    const l = bed.lights;
    const main = l.light ?? l.switch;
    if (!main && !l.level && !l.timer && !l.toggle && !l.cycle) return nothing;
    return html`
      ${this._heading("section.lighting")}
      ${main ? this._toggleRow(main) : nothing}
      ${l.level ? this._moreInfoRow(l.level) : nothing}
      ${l.timer ? this._moreInfoRow(l.timer) : nothing}
      ${
        l.toggle || l.cycle
          ? html`<div class="tiles">
              ${l.toggle ? this._tile(l.toggle, () => this._press(l.toggle!)) : nothing}
              ${l.cycle ? this._tile(l.cycle, () => this._press(l.cycle!)) : nothing}
            </div>`
          : nothing
      }
    `;
  }

  private _massage(bed: BedEntities): typeof nothing | TemplateResult {
    const m = bed.massage;
    if (m.buttons.length === 0 && m.numbers.length === 0 && !m.timer)
      return nothing;
    return html`
      ${this._heading("section.massage")}
      ${
        m.buttons.length
          ? html`<div class="tiles">
              ${m.buttons.map((id) => this._tile(id, () => this._press(id)))}
            </div>`
          : nothing
      }
      ${m.numbers.map((id) => this._moreInfoRow(id))}
      ${m.timer ? this._moreInfoRow(m.timer) : nothing}
    `;
  }

  private _climate(bed: BedEntities): typeof nothing | TemplateResult {
    const items = [...bed.climate.entities, ...bed.climate.selects];
    if (items.length === 0) return nothing;
    return html`
      ${this._heading("section.climate")}
      ${items.map((id) => this._moreInfoRow(id))}
    `;
  }

  private _connection(bed: BedEntities): typeof nothing | TemplateResult {
    if (!bed.connect && !bed.disconnect) return nothing;
    return html`
      ${this._heading("section.connection")}
      <div class="tiles">
        ${bed.connect ? this._tile(bed.connect, () => this._press(bed.connect!), { icon: "mdi:bluetooth-connect", cls: "success" }) : nothing}
        ${bed.disconnect ? this._tile(bed.disconnect, () => this._press(bed.disconnect!), { icon: "mdi:bluetooth-off" }) : nothing}
      </div>
    `;
  }

  // ---- building blocks ----------------------------------------------------

  private _heading(key: string): TemplateResult {
    return html`<div class="section-heading">${localize(this.hass, key)}</div>`;
  }

  private _tile(
    entityId: string,
    onClick: () => void,
    opts: { cls?: string; icon?: string } = {},
  ): TemplateResult {
    return html`
      <button class="tile ${opts.cls ?? ""}" @click=${onClick}>
        ${this._icon(entityId, opts.icon)}
        <span class="tile-label">${this._name(entityId)}</span>
      </button>
    `;
  }

  // Activate a row from the keyboard (Enter/Space) for non-pointer users. Only
  // handle events that originate on the row itself, so key presses on the inner
  // toggle button don't also open more-info.
  private _onRowKey(e: KeyboardEvent, action: () => void): void {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      action();
    }
  }

  private _toggleRow(entityId: string): TemplateResult {
    const st = this._state(entityId);
    const on = st?.state === "on";
    const name = this._name(entityId);
    return html`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${name}
        @click=${() => this._moreInfo(entityId)}
        @keydown=${(e: KeyboardEvent) =>
          this._onRowKey(e, () => this._moreInfo(entityId))}
      >
        ${this._icon(entityId)}
        <div class="entity-row-text">
          <span>${name}</span>
          <span class="secondary">${this._stateText(entityId)}</span>
        </div>
        <button
          class="toggle ${on ? "on" : ""}"
          role="switch"
          aria-label=${name}
          aria-checked=${on ? "true" : "false"}
          @click=${(e: Event) => {
            e.stopPropagation();
            this._toggle(entityId);
          }}
        >
          <span class="knob"></span>
        </button>
      </div>
    `;
  }

  private _moreInfoRow(entityId: string): TemplateResult {
    const name = this._name(entityId);
    return html`
      <div
        class="entity-row"
        role="button"
        tabindex="0"
        aria-label=${name}
        @click=${() => this._moreInfo(entityId)}
        @keydown=${(e: KeyboardEvent) =>
          this._onRowKey(e, () => this._moreInfo(entityId))}
      >
        ${this._icon(entityId)}
        <div class="entity-row-text">
          <span>${name}</span>
        </div>
        <span class="secondary value">${this._stateText(entityId)}</span>
      </div>
    `;
  }

  private _icon(entityId: string, fallback?: string): TemplateResult {
    const st = this._state(entityId);
    if (st) {
      return html`<ha-state-icon
        class="icon"
        .hass=${this.hass}
        .stateObj=${st}
      ></ha-state-icon>`;
    }
    return html`<ha-icon class="icon" icon=${fallback ?? "mdi:bed"}></ha-icon>`;
  }

  private _notice(key: string): TemplateResult {
    return html`<ha-card><div class="notice">${localize(this.hass, key)}</div></ha-card>`;
  }

  // ---- data helpers -------------------------------------------------------

  private _state(entityId: string): HassEntity | undefined {
    return this.hass?.states[entityId];
  }

  private _title(deviceId?: string): string {
    if (this._config?.name) return this._config.name;
    return this._deviceName(deviceId) ?? localize(this.hass, "card.default_name");
  }

  private _deviceName(deviceId = this._config?.device_id): string | undefined {
    const dev = deviceId ? this.hass?.devices[deviceId] : undefined;
    return dev?.name_by_user || dev?.name || undefined;
  }

  // Entity name with the device-name prefix stripped (the card already shows the
  // bed name in its header). Falls back to the registry name or entity_id.
  private _name(entityId: string): string {
    const friendly =
      this._state(entityId)?.attributes.friendly_name ??
      this.hass?.entities[entityId]?.name ??
      entityId;
    // Use the entity's own device, not the card's configured device. This is
    // essential for paired beds where the visible controls may belong to the
    // parent, left child, or right child.
    const entityDeviceId = this.hass?.entities[entityId]?.device_id;
    const device = this._deviceName(entityDeviceId);
    if (device && friendly.startsWith(device + " ")) {
      return friendly.slice(device.length + 1);
    }
    return friendly;
  }

  private _motorName(m: MotorEntity): string {
    const key = `motor.${m.key}`;
    const translated = localize(this.hass, key);
    if (translated !== key) return translated;
    return m.key
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  private _angle(m: MotorEntity): number | undefined {
    const id = m.angle ?? m.position;
    if (!id) return undefined;
    const v = Number.parseFloat(this._state(id)?.state ?? "");
    return Number.isFinite(v) ? v : undefined;
  }

  private _readout(m: MotorEntity): string | undefined {
    if (m.angle) {
      const a = this._angle(m);
      return a === undefined ? undefined : `${Math.round(a)}°`;
    }
    if (m.position) {
      const p = this._angle(m);
      return p === undefined ? undefined : `${Math.round(p)}%`;
    }
    if (m.cover) {
      const pos = this._state(m.cover)?.attributes.current_position;
      return typeof pos === "number" ? `${Math.round(pos)}%` : undefined;
    }
    return undefined;
  }

  private _stateText(entityId: string): string {
    const st = this._state(entityId);
    if (!st) return "";
    // The frontend localizes this for us when available.
    const fmt = (this.hass as unknown as {
      formatEntityState?: (s: HassEntity) => string;
    })?.formatEntityState;
    if (typeof fmt === "function") return fmt(st);
    return st.state;
  }

  private _collectWatched(bed: BedEntities): string[] {
    const ids = new Set<string>();
    for (const m of bed.motors) {
      [m.cover, m.up, m.down, m.angle, m.position].forEach(
        (x) => x && ids.add(x),
      );
    }
    bed.presets.forEach((x) => ids.add(x));
    for (const s of bed.memory) {
      [s.goto, s.save].forEach((x) => x && ids.add(x));
    }
    [
      bed.stop,
      bed.synchro,
      bed.connect,
      bed.disconnect,
      bed.connectivity,
      bed.lights.light,
      bed.lights.switch,
      bed.lights.level,
      bed.lights.toggle,
      bed.lights.cycle,
      bed.lights.timer,
      bed.massage.timer,
    ].forEach((x) => x && ids.add(x));
    bed.firmness.forEach((x) => ids.add(x));
    bed.massage.buttons.forEach((x) => ids.add(x));
    bed.massage.numbers.forEach((x) => ids.add(x));
    bed.climate.entities.forEach((x) => ids.add(x));
    bed.climate.selects.forEach((x) => ids.add(x));
    return [...ids];
  }

  // ---- actions ------------------------------------------------------------

  private _motorAction(m: MotorEntity, dir: "up" | "down"): void {
    if (m.cover) {
      this._cover(m.cover, dir === "up" ? "open_cover" : "close_cover");
    } else {
      const id = dir === "up" ? m.up : m.down;
      if (id) this._press(id);
    }
  }

  private _motorStop(m: MotorEntity, stopId?: string): void {
    if (m.cover) this._cover(m.cover, "stop_cover");
    else if (stopId) this._press(stopId);
  }

  // Toggle save mode for ONE section: entering it on a section cancels any other
  // section's save mode (only one section is ever savable at a time).
  private _toggleSaveMode(sectionKey: string): void {
    this._saveModeFor = this._saveModeFor === sectionKey ? undefined : sectionKey;
  }

  // Save the bed's current position into a slot, then leave save mode so a
  // stray second tap can't overwrite another position.
  private _saveMemory(slot: MemorySlot): void {
    if (slot.save) this._press(slot.save);
    this._saveModeFor = undefined;
  }

  // Home Assistant already surfaces service failures to the user via its own
  // notification layer; we just swallow the rejection so a failed BLE command
  // doesn't bubble up as an unhandled promise rejection.
  private _call(
    domain: string,
    service: string,
    entityId: string,
  ): void {
    this.hass
      ?.callService(domain, service, { entity_id: entityId })
      ?.catch(() => undefined);
  }

  private _press(entityId: string): void {
    this._call("button", "press", entityId);
  }

  private _cover(entityId: string, service: string): void {
    this._call("cover", service, entityId);
  }

  private _toggle(entityId: string): void {
    this._call("homeassistant", "toggle", entityId);
  }

  private _setEntities(entityIds: string[], on: boolean): void {
    this.hass
      ?.callService("homeassistant", on ? "turn_on" : "turn_off", {
        entity_id: entityIds,
      })
      ?.catch(() => undefined);
  }

  private _moreInfo(entityId: string): void {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId },
        bubbles: true,
        composed: true,
      }),
    );
  }

  static override styles = css`
    :host {
      --ab-gap: 10px;
      --ab-side-left-rgb: 75, 0, 255;
      --ab-side-right-rgb: 234, 65, 65;
    }
    ha-card {
      padding: 12px 12px 16px;
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 4px 8px;
    }
    .header-icon {
      color: var(--state-icon-color, var(--primary-text-color));
      --mdc-icon-size: 22px;
    }
    .title {
      font-size: 1.1rem;
      font-weight: 500;
      color: var(--primary-text-color);
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .conn {
      border: none;
      background: none;
      cursor: pointer;
      padding: 4px;
      border-radius: 50%;
      display: inline-flex;
      --mdc-icon-size: 20px;
    }
    .conn.ok {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .conn.idle {
      color: var(--info-color, var(--secondary-text-color));
    }
    .conn.off {
      color: var(--secondary-text-color);
    }
    .section-heading {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 14px 4px 8px;
    }
    .pane-tabs {
      display: grid;
      grid-template-columns: repeat(var(--pane-count, 3), minmax(0, 1fr));
      gap: 4px;
      padding: 4px;
      margin: 0 0 6px;
      border-radius: 14px;
      background: var(--secondary-background-color);
    }
    .pane-tab {
      min-width: 0;
      height: 42px;
      padding: 0 8px;
      border: 0;
      border-radius: 11px;
      background: transparent;
      color: var(--secondary-text-color);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      font: inherit;
      font-size: 0.82rem;
      font-weight: 500;
      transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .pane-tab ha-icon {
      --mdc-icon-size: 19px;
      flex: none;
    }
    .pane-tab span:not(.connection-dot) {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pane-tab:hover {
      color: var(--primary-text-color);
    }
    .pane-tab.active {
      color: var(--primary-text-color);
      background: var(--card-background-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14);
    }
    .connection-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--disabled-text-color);
      flex: none;
    }
    .connection-dot.connected {
      background: var(--success-color, var(--state-active-color, #43a047));
    }
    .connection-dot.idle {
      background: var(--info-color, var(--secondary-text-color));
    }
    .connection-dot.disconnected {
      background: var(--error-color);
    }
    .pane {
      animation: ab-pane-in 0.16s ease-out;
    }
    @keyframes ab-pane-in {
      from {
        opacity: 0;
        transform: translateY(2px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .heading-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .set-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-color);
      border-radius: 999px;
      padding: 4px 12px 4px 9px;
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: none;
      cursor: pointer;
      --mdc-icon-size: 16px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .set-btn:hover {
      background: var(--secondary-background-color);
    }
    .set-btn.active {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .hint {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding: 0 6px 8px;
    }
    .tile.save-mode {
      border-color: var(--primary-color);
      border-style: dashed;
    }
    .tile.save-mode .icon {
      color: var(--primary-color);
    }
    .tile.is-disabled {
      opacity: 0.4;
      cursor: default;
    }
    .graphic {
      display: flex;
      justify-content: center;
      padding: 4px 8px 0;
    }
    .bed-graphic {
      width: 100%;
      max-width: 350px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic-theme {
      --ab-graphic-rgb: var(--rgb-primary-color, 33, 150, 243);
    }
    .bed-graphic-left {
      --ab-graphic-rgb: var(--ab-side-left-rgb);
    }
    .bed-graphic-right {
      --ab-graphic-rgb: var(--ab-side-right-rgb);
    }
    .bed-graphic.is-moving {
      animation: ab-pulse 2s ease-in-out infinite;
    }
    .bed-frame-stop {
      stop-color: var(--secondary-text-color);
    }
    .bed-graphic-theme .bed-mattress-stop {
      stop-color: rgb(var(--rgb-primary-color, 33, 150, 243));
    }
    .bed-graphic-left .bed-mattress-stop,
    .dual-bed-left-stop {
      stop-color: rgb(var(--ab-side-left-rgb));
    }
    .bed-graphic-right .bed-mattress-stop,
    .dual-bed-right-stop {
      stop-color: rgb(var(--ab-side-right-rgb));
    }
    .bed-frame,
    .dual-bed-frame {
      opacity: 0.78;
      stroke: var(--primary-text-color);
      stroke-opacity: 0.14;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
    }
    .bed-side-layer {
      opacity: 0.86;
    }
    .bed-graphic-left .bed-side-layer,
    .bed-graphic-right .bed-side-layer {
      opacity: 0.66;
    }
    .bed-surface,
    .dual-bed-surface {
      stroke: var(--primary-text-color);
      stroke-opacity: 0.1;
      stroke-width: 1px;
      vector-effect: non-scaling-stroke;
    }
    .bed-pillow,
    .dual-bed-pillow {
      opacity: 0.9;
    }
    .bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    .dual-graphic {
      padding-top: 8px;
    }
    .dual-bed-graphic {
      isolation: isolate;
    }
    .dual-bed-side {
      opacity: 0.66;
    }
    .dual-bed-panel {
      transition: transform 0.55s cubic-bezier(0.2, 0.7, 0.2, 1);
    }
    .dual-bed-side.is-moving {
      animation: ab-side-pulse 1.4s ease-in-out infinite;
    }
    .dual-readouts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      width: min(100%, 350px);
      margin: -2px auto 2px;
    }
    .dual-readout {
      min-width: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      padding: 8px 10px;
      border-radius: 10px;
      background: var(--secondary-background-color);
      text-align: center;
    }
    .dual-side-name {
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--primary-text-color);
      font-size: 0.8rem;
      font-weight: 600;
    }
    .dual-swatch {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      flex: none;
    }
    .side-left .dual-swatch {
      background: rgb(var(--ab-side-left-rgb));
    }
    .side-right .dual-swatch {
      background: rgb(var(--ab-side-right-rgb));
    }
    .dual-position {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      line-height: 1.25;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-row {
      box-sizing: border-box;
      width: min(100%, 350px);
      min-height: 52px;
      margin: 4px auto 2px;
      padding: 7px 9px;
      display: flex;
      align-items: center;
      gap: 8px;
      border: 1px solid var(--divider-color);
      border-radius: 11px;
      background: var(--card-background-color);
    }
    .dual-sync-row > ha-icon {
      flex: none;
      color: var(--secondary-text-color);
      --mdc-icon-size: 19px;
    }
    .dual-sync-label {
      min-width: 0;
      flex: 1;
      color: var(--primary-text-color);
      font-size: 0.78rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-actions {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 4px;
      min-width: 148px;
      max-width: 52%;
      flex: none;
    }
    .dual-sync-btn {
      min-width: 0;
      height: 34px;
      padding: 0 9px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      font: inherit;
      font-size: 0.74rem;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease, opacity 0.15s ease;
    }
    .dual-sync-btn:hover:not(:disabled),
    .dual-sync-btn:focus-visible {
      border-color: var(--primary-color);
    }
    .dual-sync-btn:disabled {
      cursor: default;
      opacity: 0.42;
    }
    .dual-sync-btn.is-active {
      opacity: 1;
      border-color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .dual-sync-btn span:last-child {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dual-sync-spinner {
      flex: none;
      animation: ab-spin 0.8s linear infinite;
      --mdc-icon-size: 15px;
    }
    @keyframes ab-spin {
      to {
        transform: rotate(360deg);
      }
    }
    @keyframes ab-pulse {
      0%,
      100% {
        filter: drop-shadow(0 0 3px rgba(var(--ab-graphic-rgb), 0.25));
      }
      50% {
        filter: drop-shadow(0 0 10px rgba(var(--ab-graphic-rgb), 0.55));
      }
    }
    @keyframes ab-side-pulse {
      0%,
      100% {
        opacity: 0.58;
      }
      50% {
        opacity: 0.88;
      }
    }
    .rows {
      display: flex;
      flex-direction: column;
      gap: var(--ab-gap);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      padding: 8px 12px;
    }
    .row-label {
      display: flex;
      flex-direction: column;
      flex: 1;
      min-width: 90px;
    }
    .row-label .readout {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .control-group {
      display: inline-flex;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--divider-color);
    }
    .cg-btn {
      border: none;
      background: var(--card-background-color);
      color: var(--primary-color);
      cursor: pointer;
      padding: 8px 14px;
      display: inline-flex;
      align-items: center;
      --mdc-icon-size: 22px;
      transition: background 0.15s ease;
    }
    .cg-btn:not(:last-child) {
      border-right: 1px solid var(--divider-color);
    }
    .cg-btn:hover {
      background: var(--secondary-background-color);
    }
    .cg-btn:active {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.18);
    }
    .cg-btn[disabled] {
      color: var(--disabled-text-color);
      cursor: default;
    }
    .stop-all {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      width: 100%;
      margin-top: var(--ab-gap);
      padding: 10px;
      border-radius: 12px;
      cursor: pointer;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      color: var(--error-color);
      font-size: 0.9rem;
      font-weight: 500;
      --mdc-icon-size: 20px;
      transition: background 0.15s ease, border-color 0.15s ease;
    }
    .stop-all:hover {
      background: var(--secondary-background-color);
    }
    .stop-all:active {
      border-color: var(--error-color);
    }
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
      gap: var(--ab-gap);
    }
    .tile {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      padding: 14px 6px 10px;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      cursor: pointer;
      color: var(--primary-text-color);
      transition: background 0.15s ease, border-color 0.15s ease;
      -webkit-user-select: none;
      user-select: none;
      touch-action: manipulation;
    }
    .tile:hover {
      background: var(--secondary-background-color);
    }
    .tile:active {
      border-color: var(--primary-color);
    }
    .tile .icon {
      color: var(--primary-color);
      --mdc-icon-size: 24px;
    }
    .tile.danger .icon {
      color: var(--error-color);
    }
    .tile.success .icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .tile-label {
      font-size: 0.78rem;
      text-align: center;
      line-height: 1.2;
    }
    .entity-row {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 8px 12px;
      background: var(--card-background-color);
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      cursor: pointer;
      margin-bottom: var(--ab-gap);
    }
    .entity-row .icon {
      color: var(--state-icon-color, var(--primary-color));
      --mdc-icon-size: 24px;
    }
    .combined-entity-row {
      cursor: default;
    }
    .combined-entity-row .icon.active {
      color: var(--state-light-active-color, var(--state-active-color, #ffc107));
    }
    .entity-row-text {
      display: flex;
      flex-direction: column;
      flex: 1;
    }
    .entity-row-text .secondary,
    .value {
      color: var(--secondary-text-color);
      font-size: 0.82rem;
    }
    .toggle {
      width: 42px;
      height: 24px;
      border-radius: 12px;
      border: none;
      background: var(--switch-unchecked-track-color, rgba(120, 120, 120, 0.4));
      position: relative;
      cursor: pointer;
      padding: 0;
      transition: background 0.2s ease;
      flex: none;
    }
    .toggle.on {
      background: var(--primary-color);
    }
    .toggle.mixed {
      background: rgba(var(--rgb-primary-color, 33, 150, 243), 0.55);
    }
    .toggle .knob {
      position: absolute;
      top: 2px;
      left: 2px;
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--switch-unchecked-button-color, #fff);
      transition: transform 0.2s ease;
    }
    .toggle.on .knob {
      transform: translateX(18px);
    }
    .bluetooth-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--ab-gap);
    }
    .bluetooth-status {
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px;
      border: 1px solid var(--divider-color);
      border-radius: 12px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    .bluetooth-status ha-icon {
      --mdc-icon-size: 22px;
      flex: none;
    }
    .bluetooth-status.connected ha-icon {
      color: var(--success-color, var(--state-active-color, #43a047));
    }
    .bluetooth-status.idle ha-icon {
      color: var(--info-color, var(--secondary-text-color));
    }
    .bluetooth-status.disconnected ha-icon {
      color: var(--secondary-text-color);
    }
    .bluetooth-copy {
      min-width: 0;
      display: flex;
      flex-direction: column;
    }
    .bluetooth-detail {
      overflow: hidden;
      color: var(--secondary-text-color);
      font-size: 0.72rem;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .notice {
      padding: 24px 16px;
      text-align: center;
      color: var(--secondary-text-color);
    }
  `;
}

// Register the card with Home Assistant's card picker.
interface CustomCard {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
  documentationURL?: string;
}
const w = window as unknown as { customCards?: CustomCard[] };
w.customCards = w.customCards || [];
w.customCards.push({
  type: "adjustable-bed-card",
  name: "Adjustable Bed Card",
  description: "Native control card for the Adjustable Bed integration.",
  preview: true,
  documentationURL: "https://github.com/kristofferR/ha-adjustable-bed",
});

// eslint-disable-next-line no-console
console.info(
  `%c adjustable-bed-card %c ${CARD_VERSION} `,
  "color:white;background:#3f51b5;border-radius:3px 0 0 3px;padding:2px",
  "color:#3f51b5;background:#e8eaf6;border-radius:0 3px 3px 0;padding:2px",
);

declare global {
  interface HTMLElementTagNameMap {
    "adjustable-bed-card": AdjustableBedCard;
  }
}
