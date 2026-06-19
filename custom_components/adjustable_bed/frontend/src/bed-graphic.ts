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
