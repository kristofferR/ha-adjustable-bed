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
import { renderBedGraphic } from "./bed-graphic";
import {
  PLATFORM,
  SECTION_ORDER,
  bedEntitiesForDevice,
  bedIsEmpty,
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

@customElement("adjustable-bed-card")
export class AdjustableBedCard extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;
  @state() private _config?: AdjustableBedCardConfig;
  // Transient UI state: when true, tapping a memory tile saves the current bed
  // position into that slot instead of recalling it.
  @state() private _saveMode = false;

  private _bed?: BedEntities;
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
    if (changed.has("_config")) return true;
    if (!changed.has("hass") || !this.hass) return true;
    const old = changed.get("hass") as HomeAssistant | undefined;
    if (!old || old.entities !== this.hass.entities) return true;
    for (const id of this._watched) {
      if (old.states[id] !== this.hass.states[id]) return true;
    }
    return false;
  }

  protected override render() {
    if (!this.hass || !this._config) return nothing;
    if (!this._config.device_id) return this._notice("card.no_device");

    const bed = bedEntitiesForDevice(this.hass, this._config.device_id);
    this._bed = bed;
    this._watched = this._collectWatched(bed);

    if (bedIsEmpty(bed)) return this._notice("card.no_entities");
    const c = this._config;

    const render: Record<string, () => typeof nothing | TemplateResult> = {
      graphic: () => (c.show_graphic !== false ? this._graphic(bed) : nothing),
      motors: () => (c.show_motors !== false ? this._motors(bed) : nothing),
      firmness: () => (c.show_firmness !== false ? this._firmness(bed) : nothing),
      presets: () => (c.show_presets !== false ? this._presets(bed) : nothing),
      memory: () => (c.show_memory !== false ? this._memory(bed) : nothing),
      lighting: () => (c.show_lighting !== false ? this._lighting(bed) : nothing),
      massage: () => (c.show_massage !== false ? this._massage(bed) : nothing),
      climate: () => (c.show_climate !== false ? this._climate(bed) : nothing),
      connection: () =>
        c.show_connection !== false ? this._connection(bed) : nothing,
    };

    return html`
      <ha-card>
        ${this._header(bed)}
        ${this._orderedSections().map((k) => render[k]?.() ?? nothing)}
      </ha-card>
    `;
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

  private _header(bed: BedEntities): TemplateResult {
    const connected = bed.connectivity
      ? this._state(bed.connectivity)?.state === "on"
      : undefined;
    return html`
      <div class="header">
        <ha-icon class="header-icon" icon="mdi:bed-king-outline"></ha-icon>
        <span class="title">${this._title()}</span>
        ${
          connected === undefined
            ? nothing
            : html`
                <button
                  class="conn ${connected ? "ok" : "off"}"
                  @click=${() => this._moreInfo(bed.connectivity!)}
                  title=${localize(
                    this.hass,
                    connected ? "status.connected" : "status.disconnected",
                  )}
                >
                  <ha-icon
                    icon=${connected
                      ? "mdi:bluetooth-connect"
                      : "mdi:bluetooth-off"}
                  ></ha-icon>
                </button>
              `
        }
      </div>
    `;
  }

  private _graphic(bed: BedEntities): typeof nothing | TemplateResult {
    const withAngle = bed.motors.filter((m) => m.angle);
    if (withAngle.length === 0) return nothing;
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
    return html`
      <div class="graphic">
        ${renderBedGraphic({
          upper: { label: this._name(upper.cover ?? upper.angle!), angle: this._angle(upper) },
          lower: { label: this._name(lower.cover ?? lower.angle!), angle: this._angle(lower) },
          moving,
        })}
      </div>
    `;
  }

  private _motors(bed: BedEntities): typeof nothing | TemplateResult {
    const motors = bed.motors.filter((m) => m.cover || m.up || m.down);
    // Beds with direct target numbers (and no cover) get a settable row instead.
    const positionRows = bed.motors.filter(
      (m) => !m.cover && !m.up && !m.down && m.position,
    );
    if (motors.length === 0 && positionRows.length === 0 && !bed.stop)
      return nothing;
    const hasRows = motors.length > 0 || positionRows.length > 0;
    return html`
      ${hasRows ? this._heading("section.position") : nothing}
      ${
        motors.length
          ? html`<div class="rows">${motors.map((m) => this._motorRow(m))}</div>`
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
              <span>${this._name(bed.stop)}</span>
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

  private _motorRow(m: MotorEntity): TemplateResult {
    const readout = this._readout(m);
    const upId = m.cover ?? m.up;
    const downId = m.cover ?? m.down;
    const canStop = !!m.cover || !!this._bed?.stop;
    return html`
      <div class="row">
        <div class="row-label">
          <span>${this._name(m.cover ?? m.up ?? m.down ?? m.angle ?? m.key)}</span>
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
            @click=${() => this._motorStop(m)}
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
    return html`
      <div class="section-heading heading-row">
        <span>${localize(this.hass, "section.memory")}</span>
        ${
          canSave
            ? html`<button
                class="set-btn ${this._saveMode ? "active" : ""}"
                @click=${() => this._toggleSaveMode()}
              >
                <ha-icon
                  icon=${this._saveMode ? "mdi:close" : "mdi:content-save-edit-outline"}
                ></ha-icon>
                <span>${localize(this.hass, this._saveMode ? "memory.cancel" : "memory.set")}</span>
              </button>`
            : nothing
        }
      </div>
      ${
        this._saveMode
          ? html`<div class="hint">${localize(this.hass, "memory.set_hint")}</div>`
          : nothing
      }
      <div class="tiles">${slots.map((s) => this._memoryTile(s))}</div>
    `;
  }

  private _memoryTile(slot: MemorySlot): TemplateResult {
    const labelId = slot.goto ?? slot.save!;
    if (this._saveMode) {
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

  // Activate a row from the keyboard (Enter/Space) for non-pointer users.
  private _onRowKey(e: KeyboardEvent, action: () => void): void {
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

  private _title(): string {
    if (this._config?.name) return this._config.name;
    return this._deviceName() ?? localize(this.hass, "card.default_name");
  }

  private _deviceName(): string | undefined {
    const dev = this._config?.device_id
      ? this.hass?.devices[this._config.device_id]
      : undefined;
    return dev?.name_by_user || dev?.name || undefined;
  }

  // Entity name with the device-name prefix stripped (the card already shows the
  // bed name in its header). Falls back to the registry name or entity_id.
  private _name(entityId: string): string {
    const friendly =
      this._state(entityId)?.attributes.friendly_name ??
      this.hass?.entities[entityId]?.name ??
      entityId;
    const device = this._deviceName();
    if (device && friendly.startsWith(device + " ")) {
      return friendly.slice(device.length + 1);
    }
    return friendly;
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

  private _motorStop(m: MotorEntity): void {
    if (m.cover) this._cover(m.cover, "stop_cover");
    else if (this._bed?.stop) this._press(this._bed.stop);
  }

  private _toggleSaveMode(): void {
    this._saveMode = !this._saveMode;
  }

  // Save the bed's current position into a slot, then leave save mode so a
  // stray second tap can't overwrite another position.
  private _saveMemory(slot: MemorySlot): void {
    if (slot.save) this._press(slot.save);
    this._saveMode = false;
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
      max-width: 320px;
      height: auto;
      overflow: visible;
    }
    .bed-graphic.is-moving {
      animation: ab-pulse 2s ease-in-out infinite;
    }
    .bed-graphic-label {
      fill: var(--secondary-text-color);
      font-size: 11px;
      font-family: var(--ha-font-family-body, var(--primary-font-family, sans-serif));
    }
    @keyframes ab-pulse {
      0%,
      100% {
        filter: drop-shadow(0 0 3px rgba(var(--rgb-primary-color, 33, 150, 243), 0.25));
      }
      50% {
        filter: drop-shadow(0 0 10px rgba(var(--rgb-primary-color, 33, 150, 243), 0.55));
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
