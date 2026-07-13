// A refined, theme-aware bed silhouette. Two hinged mattress panels rotate with
// the back/legs (or head/feet) angle. All colour comes from --rgb-primary-color
// so it inherits any Home Assistant theme. Shown only for beds with angle
// feedback; purely decorative — not interactive.
import { type TemplateResult, svg } from "lit";

export interface BedGraphicPanel {
  label?: string;
  angle?: number; // degrees, 0 = flat
}

export interface BedGraphicOptions {
  upper: BedGraphicPanel; // head end (left)
  lower: BedGraphicPanel; // foot end (right)
  moving: boolean;
}

export interface DualBedGraphicSide {
  upper: BedGraphicPanel;
  lower: BedGraphicPanel;
  moving: boolean;
}

export interface DualBedGraphicOptions {
  left: DualBedGraphicSide;
  right: DualBedGraphicSide;
}

// Clamp so an out-of-range reading can never fold the mattress through the base.
const clamp = (deg: number): number => Math.max(0, Math.min(75, deg));

export function renderBedGraphic(opts: BedGraphicOptions): TemplateResult {
  const upper = clamp(opts.upper.angle ?? 0);
  const lower = clamp(opts.lower.angle ?? 0);
  // Positive rotation lifts the left (head) end; negative lifts the right (foot)
  // end. See derivation in the card design notes.
  const upperT = `rotate(${upper} 150 70)`;
  const lowerT = `rotate(${-lower} 150 70)`;

  const fmt = (p: BedGraphicPanel): string => {
    if (p.angle === undefined) return "";
    return `${p.label ? `${p.label} ` : ""}${Math.round(clamp(p.angle))}°`;
  };

  return svg`
    <svg
      class="bed-graphic ${opts.moving ? "is-moving" : ""}"
      viewBox="0 0 300 110"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abMattress" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.95)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.6)" />
        </linearGradient>
        <linearGradient id="abFrame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.45)" />
          <stop offset="100%" stop-color="rgba(var(--rgb-primary-color,33,150,243),0.2)" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect x="30" y="84" width="240" height="6" rx="3" fill="url(#abFrame)" />
      <rect x="34" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />
      <rect x="261" y="88" width="5" height="14" rx="2" fill="url(#abFrame)" />

      <!-- base mattress (static, behind the hinged panels) -->
      <rect x="42" y="64" width="216" height="20" rx="6"
        fill="rgba(var(--rgb-primary-color,33,150,243),0.28)" />

      <!-- foot panel (right of hinge) -->
      <g transform=${lowerT} style="transition: transform 0.5s ease;">
        <rect x="150" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
      </g>

      <!-- head/back panel (left of hinge) with pillow -->
      <g transform=${upperT} style="transition: transform 0.5s ease;">
        <rect x="42" y="58" width="108" height="18" rx="6" fill="url(#abMattress)" />
        <rect x="50" y="49" width="40" height="11" rx="5"
          fill="rgba(var(--rgb-primary-color,33,150,243),0.85)" />
      </g>

      <text x="86" y="22" text-anchor="middle" class="bed-graphic-label">${fmt(opts.upper)}</text>
      <text x="214" y="22" text-anchor="middle" class="bed-graphic-label">${fmt(opts.lower)}</text>
    </svg>
  `;
}

// Comparison view for paired beds. Both sides share the same hinge so their
// real positions can be compared at a glance. A small vertical offset and
// translucent, contrasting colours keep both silhouettes legible even when the
// positions are identical.
export function renderDualBedGraphic(
  opts: DualBedGraphicOptions,
): TemplateResult {
  const leftUpper = clamp(opts.left.upper.angle ?? 0);
  const leftLower = clamp(opts.left.lower.angle ?? 0);
  const rightUpper = clamp(opts.right.upper.angle ?? 0);
  const rightLower = clamp(opts.right.lower.angle ?? 0);

  const side = (
    name: "left" | "right",
    upper: number,
    lower: number,
    offset: number,
    moving: boolean,
  ): TemplateResult => svg`
    <g
      class="dual-bed-side dual-bed-side-${name} ${moving ? "is-moving" : ""}"
      style="--dual-offset:${offset}px"
    >
      <rect class="dual-bed-base" x="42" y="64" width="216" height="18" rx="6" />
      <g
        class="dual-bed-panel"
        transform=${`rotate(${-lower} 150 70)`}
      >
        <rect x="150" y="58" width="108" height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${`rotate(${upper} 150 70)`}
      >
        <rect x="42" y="58" width="108" height="18" rx="6" />
        <rect class="dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
    </g>
  `;

  return svg`
    <svg
      class="bed-graphic dual-bed-graphic ${
        opts.left.moving || opts.right.moving ? "is-moving" : ""
      }"
      viewBox="0 0 300 108"
      role="img"
      aria-hidden="true"
    >
      <rect class="dual-bed-frame" x="30" y="86" width="240" height="6" rx="3" />
      <rect class="dual-bed-frame" x="34" y="90" width="5" height="12" rx="2" />
      <rect class="dual-bed-frame" x="261" y="90" width="5" height="12" rx="2" />
      ${side(
        "left",
        leftUpper,
        leftLower,
        3,
        opts.left.moving,
      )}
      ${side(
        "right",
        rightUpper,
        rightLower,
        -3,
        opts.right.moving,
      )}
    </svg>
  `;
}
