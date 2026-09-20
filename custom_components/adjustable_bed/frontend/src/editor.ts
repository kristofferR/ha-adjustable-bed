// Visual editor for the Adjustable Bed card.
//
// The device picker uses Home Assistant's ha-form (for the native device
// selector). Everything else is rendered with native HA controls (ha-switch,
// ha-checkbox, ha-icon) so we keep full, predictable control over the grouped
// layout, the per-section on/off + reordering, and the memory options — and
// avoid ha-form's expandable/flatten quirks entirely.
import { LitElement, type TemplateResult, css, html, nothing } from "lit";
import { property, state } from "lit/decorators.js";
import { SECTION_ORDER } from "./discovery";
import { applyCompactPreset, COMPACT_PRESETS, compactActionOptions,
  compactActions, compactTargets } from "./compact";
import { presentSections } from "./editor-sections";
import { localize } from "./localize";
import type {
  AdjustableBedCardConfig,
  BedEntities,
  HomeAssistant,
  LovelaceCardEditor,
  MemorySlot,
} from "./types";

interface HaFormSchema {
  name: string;
  required?: boolean;
  selector?: Record<string, unknown>;
}

// Inline chevron paths so the reorder buttons don't depend on ha-icon resolving
// inside the editor dialog's shadow DOM.
const CHEVRON_UP = "M7.41 15.41 12 10.83l4.59 4.58L18 14l-6-6-6 6z";
const CHEVRON_DOWN = "M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z";

const arraysEqual = (a: string[], b: string[]): boolean =>
  a.length === b.length && a.every((v, i) => v === b[i]);

export class AdjustableBedCardEditor
  extends LitElement
  implements LovelaceCardEditor
{
  @property({ attribute: false }) public hass?: HomeAssistant;
  @state() private _config?: AdjustableBedCardConfig;

  public setConfig(config: AdjustableBedCardConfig): void {
    this._config = config;
  }

  private _bed(): BedEntities | undefined {
    const deviceId = this._config?.device_id;
    if (!this.hass || !deviceId) return undefined;
    const beds = compactTargets(this.hass, deviceId).map((target) => target.bed);
    const first = beds[0];
    if (!first) return undefined;
    const slots = new Map<number, MemorySlot>();
    for (const bed of beds) {
      for (const slot of bed.memory) {
        const previous = slots.get(slot.slot);
        slots.set(slot.slot, {
          slot: slot.slot,
          goto: previous?.goto ?? slot.goto,
          save: previous?.save ?? slot.save,
        });
      }
    }
    return { ...first, memory: [...slots.values()].sort((a, b) => a.slot - b.slot) };
  }

  // Present section keys in their DEFAULT order.
  private _presentKeys(bed: BedEntities): string[] {
    const beds = this.hass ? compactTargets(this.hass, this._config?.device_id).map((t) => t.bed) : [bed];
    return SECTION_ORDER.filter((key) => beds.some((b) => presentSections(b, this.hass!)[key]));
  }

  // Present section keys in the user's configured order (with the default order
  // as the fallback for any not listed).
  private _orderedKeys(bed: BedEntities): string[] {
    const present = this._presentKeys(bed);
    const cfg = this._config?.section_order ?? [];
    const head = cfg.filter((k) => present.includes(k));
    const tail = present.filter((k) => !head.includes(k));
    return [...head, ...tail];
  }

  private _memorySlots(bed: BedEntities | undefined): number[] {
    return bed ? bed.memory.map((s) => s.slot) : [];
  }

  // Label for a memory slot — the entity's friendly name with the device prefix
  // stripped (so a renamed slot shows e.g. "Flat", not "Memory 1").
  private _slotLabel(slot: MemorySlot): string {
    const id = slot.goto ?? slot.save;
    const friendly =
      (id && this.hass?.states[id]?.attributes.friendly_name) ||
      `Memory ${slot.slot}`;
    const deviceId = id && this.hass?.entities[id]?.device_id;
    const dev = deviceId ? this.hass?.devices[deviceId] : undefined;
    const device = dev?.name_by_user || dev?.name;
    return device && friendly.startsWith(`${device} `)
      ? friendly.slice(device.length + 1)
      : friendly;
  }

  // ---- config emit --------------------------------------------------------

  private _emit(next: Record<string, unknown>): void {
    next.type = next.type ?? "custom:adjustable-bed-card";
    if (!next.name) delete next.name;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private get _cfg(): Record<string, unknown> {
    return { ...((this._config ?? {}) as Record<string, unknown>) };
  }

  // ---- device / name (ha-form) -------------------------------------------

  private _deviceSchema(): HaFormSchema[] {
    return [
      {
        name: "device_id",
        required: true,
        selector: { device: { integration: "adjustable_bed" } },
      },
      { name: "name", selector: { text: {} } },
    ];
  }

  private _computeLabel = (schema: HaFormSchema): string =>
    localize(this.hass, `editor.${schema.name}`);

  private _deviceChanged(ev: CustomEvent): void {
    ev.stopPropagation();
    const value = ev.detail.value as Record<string, unknown>;
    const next = this._cfg;
    if (next.device_id !== value.device_id) delete next.default_target;
    next.device_id = value.device_id || undefined;
    if (value.name) next.name = value.name;
    else delete next.name;
    this._emit(next);
  }

  // ---- section toggles + reorder -----------------------------------------

  private _toggleSection(key: string, checked: boolean): void {
    const next = this._cfg;
    if (checked) delete next[`show_${key}`];
    else next[`show_${key}`] = false;
    this._emit(next);
  }

  private _moveSection(bed: BedEntities, key: string, delta: number): void {
    const order = this._orderedKeys(bed);
    const i = order.indexOf(key);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    const next = this._cfg;
    if (arraysEqual(order, this._presentKeys(bed))) delete next.section_order;
    else next.section_order = order;
    this._emit(next);
  }

  // ---- memory options -----------------------------------------------------

  private _setMemorySave(checked: boolean): void {
    const next = this._cfg;
    if (checked) delete next.memory_save;
    else next.memory_save = false;
    this._emit(next);
  }

  private _slotChecked(slot: number): boolean {
    const sel = this._config?.memory_slots;
    return !sel || !sel.length || sel.map(Number).includes(slot);
  }

  private _toggleSlot(bed: BedEntities, slot: number, checked: boolean): void {
    const all = this._memorySlots(bed);
    const current = this._config?.memory_slots;
    let sel =
      current && current.length ? current.map(Number) : [...all];
    if (checked) {
      if (!sel.includes(slot)) sel.push(slot);
    } else {
      sel = sel.filter((s) => s !== slot);
    }
    sel.sort((a, b) => a - b);
    const next = this._cfg;
    if (sel.length === all.length) delete next.memory_slots;
    else next.memory_slots = sel;
    this._emit(next);
  }

  // ---- render -------------------------------------------------------------

  private _sectionsGroup(bed: BedEntities): TemplateResult | typeof nothing {
    const keys = this._orderedKeys(bed);
    if (!keys.length) return nothing;
    return html`
      <div class="group">
        <div class="group-title">${localize(this.hass, "editor.sections")}</div>
        ${keys.map((key, i) => {
          const shown = (this._config as Record<string, unknown> | undefined)
            ?.[`show_${key}`] !== false;
          return html`
            <div class="row">
              <div class="reorder">
                <button
                  class="icon-btn"
                  ?disabled=${i === 0}
                  @click=${() => this._moveSection(bed, key, -1)}
                  title=${localize(this.hass, "editor.move_up")}
                  aria-label=${localize(this.hass, "editor.move_up")}
                >
                  <svg viewBox="0 0 24 24"><path d=${CHEVRON_UP}></path></svg>
                </button>
                <button
                  class="icon-btn"
                  ?disabled=${i === keys.length - 1}
                  @click=${() => this._moveSection(bed, key, 1)}
                  title=${localize(this.hass, "editor.move_down")}
                  aria-label=${localize(this.hass, "editor.move_down")}
                >
                  <svg viewBox="0 0 24 24"><path d=${CHEVRON_DOWN}></path></svg>
                </button>
              </div>
              <span class="label">${localize(this.hass, `editor.show_${key}`)}</span>
              <ha-switch
                .checked=${shown}
                @change=${(e: Event) =>
                  this._toggleSection(key, (e.target as HTMLInputElement).checked)}
              ></ha-switch>
            </div>
          `;
        })}
      </div>
    `;
  }

  private _memoryGroup(bed: BedEntities): TemplateResult | typeof nothing {
    const shown =
      bed.memory.length > 0 && this._config?.show_memory !== false;
    if (!shown) return nothing;
    const canSave = bed.memory.some((s) => s.save);
    const multi = bed.memory.length > 1;
    if (!canSave && !multi) return nothing;
    return html`
      <div class="group">
        <div class="group-title">
          ${localize(this.hass, "editor.memory_group")}
        </div>
        ${
          canSave
            ? html`<div class="row">
                <span class="label">${localize(this.hass, "editor.memory_save")}</span>
                <ha-switch
                  .checked=${this._config?.memory_save !== false}
                  @change=${(e: Event) =>
                    this._setMemorySave((e.target as HTMLInputElement).checked)}
                ></ha-switch>
              </div>`
            : nothing
        }
        ${
          multi
            ? html`<div class="sub">
                <div class="sub-label">
                  ${localize(this.hass, "editor.memory_slots")}
                </div>
                ${bed.memory.map(
                  (s) => html`
                    <label class="check-row">
                      <ha-checkbox
                        .checked=${this._slotChecked(s.slot)}
                        @change=${(e: Event) =>
                          this._toggleSlot(
                            bed,
                            s.slot,
                            (e.target as HTMLInputElement).checked,
                          )}
                      ></ha-checkbox>
                      <span>${this._slotLabel(s)}</span>
                    </label>
                  `,
                )}
              </div>`
            : nothing
        }
      </div>
    `;
  }

  private _setOption<K extends keyof AdjustableBedCardConfig>(
    key: K, value: AdjustableBedCardConfig[K],
  ): void {
    this._emit({ ...this._cfg, [key]: value });
  }

  private _compactToggle(
    key: "show_header" | "show_graphic" | "show_side_selector" | "show_motors" |
      "show_lighting" | "show_connection" | "animate",
    defaultValue: boolean,
  ): TemplateResult {
    return html`<div class="row"><span class="label">${localize(this.hass, key === "show_connection" ? "editor.compact_connection" : `editor.${key}`)}</span>
      <ha-switch .checked=${this._config?.[key] ?? defaultValue}
        @change=${(e: Event) => this._setOption(key, (e.target as HTMLInputElement).checked)}></ha-switch>
    </div>`;
  }

  private _compactGroup(): TemplateResult {
    const c = this._config!;
    const targets = compactTargets(this.hass!, c.device_id);
    const target = targets.find((t) => t.key === (c.default_target ?? "both"));
    // The union includes capabilities that exist only on an individual side.
    const options = targets.flatMap((t) => compactActionOptions(this.hass!, t.bed))
      .filter((action, index, all) => all.findIndex((a) => a.key === action.key) === index);
    const selected = c.compact_actions ?? (target
      ? compactActions(this.hass!, target.bed).map((a) => a.key) : []);
    const ordered = [...selected.filter((key) => options.some((a) => a.key === key)),
      ...options.map((a) => a.key).filter((key) => !selected.includes(key))];
    return html`
      <div class="group">
        <div class="group-title">${localize(this.hass, "editor.compact_appearance")}</div>
        ${this._compactToggle("show_header", true)}
        ${this._compactToggle("show_graphic", true)}
        <label class="row"><span class="label">${localize(this.hass, "editor.compact_labels")}</span>
          <select .value=${c.compact_labels ?? "angles"}
            @change=${(e: Event) => this._setOption("compact_labels",
              (e.target as HTMLSelectElement).value as AdjustableBedCardConfig["compact_labels"])}>
            ${(["angles", "names", "none"] as const).map((value) => html`
              <option value=${value}>${localize(this.hass, `editor.labels_${value}`)}</option>`)}
          </select>
        </label>
        ${this._compactToggle("animate", true)}
        <label class="row path-row"><span class="label">${localize(this.hass, "editor.navigation_path")}</span>
          <input type="text" .value=${c.navigation_path ?? ""} placeholder="/dashboard/bed"
            @change=${(e: Event) => this._setOption("navigation_path", (e.target as HTMLInputElement).value || undefined)}>
        </label>
      </div>
      <div class="group">
        <div class="group-title">${localize(this.hass, "editor.compact_controls")}</div>
        ${targets.length > 1 || !target ? html`
          ${this._compactToggle("show_side_selector", true)}
          <label class="row"><span class="label">${localize(this.hass, "editor.default_target")}</span>
            <select .value=${c.default_target ?? "both"}
              @change=${(e: Event) => this._setOption("default_target", (e.target as HTMLSelectElement).value)}>
              ${!target ? html`<option value=${c.default_target}>${localize(this.hass, "compact.target_missing")}</option>` : nothing}
              ${targets.map((t) => html`<option value=${t.key}>${t.label}</option>`)}
            </select>
          </label>` : nothing}
        ${this._compactToggle("show_motors", false)}
        ${this._compactToggle("show_lighting", false)}
        ${this._compactToggle("show_connection", false)}
        <p class="hint">${localize(this.hass, "editor.compact_stop_hint")}</p>
      </div>
      <div class="group">
        <div class="group-title">${localize(this.hass, "editor.compact_actions")}</div>
        <p class="hint">${localize(this.hass, "editor.compact_actions_hint")}</p>
        <div class="recipes">
          <button @click=${() => this._setOption("compact_actions", undefined)}>${localize(this.hass, "editor.actions_auto")}</button>
          <button @click=${() => this._setOption("compact_actions", [])}>${localize(this.hass, "editor.labels_none")}</button>
        </div>
        ${ordered.map((key) => {
          const action = options.find((a) => a.key === key)!;
          const checked = selected.includes(key);
          const index = selected.indexOf(key);
          const move = (delta: number) => {
            const next = [...selected];
            [next[index], next[index + delta]] = [next[index + delta], next[index]];
            this._setOption("compact_actions", next);
          };
          const entity = this.hass!.states[action.entityId];
          return html`<div class="row">
            <ha-checkbox .checked=${checked} @change=${(e: Event) => this._setOption("compact_actions",
              (e.target as HTMLInputElement).checked ? [...selected, key] : selected.filter((k) => k !== key))}></ha-checkbox>
            <span class="label">${entity?.attributes.friendly_name ?? key}</span>
            <button class="icon-btn" ?disabled=${!checked || index === 0}
              aria-label=${localize(this.hass, "editor.move_up")} @click=${() => move(-1)}>↑</button>
            <button class="icon-btn" ?disabled=${!checked || index === selected.length - 1}
              aria-label=${localize(this.hass, "editor.move_down")} @click=${() => move(1)}>↓</button>
          </div>`;
        })}
      </div>`;
  }

  private _layoutGroup(): TemplateResult {
    return html`<div class="group">
      <label class="row"><span class="label">${localize(this.hass, "editor.layout")}</span>
        <select .value=${this._config?.layout ?? "full"}
          @change=${(e: Event) => this._setOption("layout", (e.target as HTMLSelectElement).value as "full" | "compact")}>
          <option value="full">${localize(this.hass, "editor.layout_full")}</option>
          <option value="compact">${localize(this.hass, "editor.layout_compact")}</option>
        </select>
      </label>
      <p class="hint">${localize(this.hass, "editor.recipe_hint")}</p>
      <div class="recipes">${COMPACT_PRESETS.map((preset) => html`
        <button @click=${() => this._emit({ ...applyCompactPreset(this._config!, preset) })}>
          ${localize(this.hass, `editor.recipe_${preset}`)}
        </button>`)}</div>
    </div>`;
  }

  protected override render(): TemplateResult | typeof nothing {
    if (!this.hass || !this._config) return nothing;
    const bed = this._bed();
    return html`
      <ha-form
        .hass=${this.hass}
        .data=${{ device_id: this._config.device_id, name: this._config.name }}
        .schema=${this._deviceSchema()}
        .computeLabel=${this._computeLabel}
        @value-changed=${this._deviceChanged}
      ></ha-form>
      ${this._layoutGroup()}
      ${this._config.layout === "compact" ? this._compactGroup() : html`
        ${bed ? this._sectionsGroup(bed) : nothing}
        ${bed ? this._memoryGroup(bed) : nothing}
      `}
    `;
  }

  static override styles = css`
    select, input { min-width: 0; max-width: 60%; box-sizing: border-box;
      background: var(--card-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 6px; padding: 8px; font: inherit; }
    .path-row { flex-wrap: wrap; }
    .path-row input { flex: 1; min-width: 180px; max-width: 100%; }
    .recipes { display: flex; gap: 6px; flex-wrap: wrap; }
    .recipes button { background: var(--secondary-background-color); color: var(--primary-text-color);
      border: 1px solid var(--divider-color); border-radius: 7px; min-height: 44px;
      padding: 8px 12px; cursor: pointer; font: inherit; font-size: .85rem; }
    .hint { color: var(--secondary-text-color); font-size: .8rem; line-height: 1.4; }
    button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

    .group {
      margin-top: 16px;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      padding: 8px 12px 12px;
    }
    .group-title {
      font-size: 0.72rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--secondary-text-color);
      padding: 4px 0 8px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 40px;
    }
    .label {
      flex: 1;
      color: var(--primary-text-color);
    }
    .reorder {
      display: inline-flex;
      gap: 2px;
    }
    .icon-btn {
      border: none;
      background: none;
      color: var(--secondary-text-color);
      cursor: pointer;
      width: 28px;
      height: 28px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
    }
    .icon-btn svg {
      width: 20px;
      height: 20px;
      fill: currentColor;
    }
    .icon-btn:hover:not([disabled]) {
      color: var(--primary-color);
      background: var(--secondary-background-color);
    }
    .icon-btn[disabled] {
      opacity: 0.3;
      cursor: default;
    }
    .sub {
      margin-top: 8px;
      padding-top: 8px;
      border-top: 1px solid var(--divider-color);
    }
    .sub-label {
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      padding-bottom: 4px;
    }
    .check-row {
      display: flex;
      align-items: center;
      gap: 4px;
      cursor: pointer;
    }
  `;
}

if (!customElements.get("adjustable-bed-card-editor")) {
  customElements.define("adjustable-bed-card-editor", AdjustableBedCardEditor);
}

declare global {
  interface HTMLElementTagNameMap {
    "adjustable-bed-card-editor": AdjustableBedCardEditor;
  }
}
