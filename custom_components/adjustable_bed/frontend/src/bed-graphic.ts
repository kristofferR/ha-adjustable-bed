// A refined bed silhouette. Two hinged mattress panels rotate with the
// back/legs (or head/feet) feedback, and an optional separate lumbar section
// bows upward with its own. Percentage poses are schematic. Purely decorative,
// not interactive.
import { type TemplateResult, svg } from "lit";

export type BedGraphicTone = "theme" | "left" | "right";

// How a panel's position is known. Only measured feedback is drawn solid; each
// estimate state (#601) has its own style, set per panel by the card's CSS.
export type PanelFeedback = "measured" | "estimated" | "unconfirmed" | "unknown";

export interface BedGraphicPanel {
  label?: string;
  angle?: number; // degrees, 0 = flat; undefined = unknown, drawn flat
  readout?: string; // the value text, when it is not the measured angle
  feedback?: PanelFeedback; // omitted = measured, or unknown without an angle
}

export interface BedGraphicOptions {
  showLabels?: boolean;
  // The motor name above its value, so three labels never overlap.
  stackLabels?: boolean;
  upper: BedGraphicPanel; // head end (left)
  lower: BedGraphicPanel; // foot end (right)
  middle?: BedGraphicPanel; // lumbar support, when this motor exists
  moving: boolean;
}

export interface DualBedGraphicSide {
  upper: BedGraphicPanel;
  lower: BedGraphicPanel;
  middle?: BedGraphicPanel;
  moving: boolean;
}

export interface DualBedGraphicOptions {
  left: DualBedGraphicSide;
  right: DualBedGraphicSide;
}

// Clamp so an out-of-range reading can never fold the mattress through the base.
export const clampGraphicAngle = (deg: number): number => Math.max(0, Math.min(75, deg));

const feedbackClass = (p: BedGraphicPanel): `is-${PanelFeedback}` =>
  `is-${p.angle === undefined ? "unknown" : p.feedback ?? "measured"}`;

const value = (p: BedGraphicPanel): string =>
  p.angle === undefined ? "?" : p.readout ?? `${Math.round(clampGraphicAngle(p.angle))}°`;

/** Schematic geometry: lumbar extension changes only the middle support. */
export function bedGraphicGeometry(opts: BedGraphicOptions) {
  const upperHinge = opts.middle ? 122 : 150;
  const lowerHinge = opts.middle ? 178 : 150;
  const lift = clampGraphicAngle(opts.middle?.angle ?? 0) / 75 * 28;
  return {
    upperTransform: `rotate(${clampGraphicAngle(opts.upper.angle ?? 0)} ${upperHinge} 70)`,
    lowerTransform: `rotate(${-clampGraphicAngle(opts.lower.angle ?? 0)} ${lowerHinge} 70)`,
    upperWidth: upperHinge - 42,
    lowerX: lowerHinge,
    lowerWidth: 258 - lowerHinge,
    middlePath: `M 125 58 C 137 ${58 - lift} 163 ${58 - lift} 175 58 L 175 76 C 163 ${76 - lift} 137 ${76 - lift} 125 76 Z`,
  };
}

export function renderBedGraphic(
  opts: BedGraphicOptions,
  tone: BedGraphicTone = "theme",
): TemplateResult {
  const geometry = bedGraphicGeometry(opts);
  // Positive rotation lifts the left (head) end; negative lifts the right (foot)
  // end. See derivation in the card design notes.
  const upperT = geometry.upperTransform;
  const lowerT = geometry.lowerTransform;

  const label = (x: number, p: BedGraphicPanel) => opts.stackLabels && p.label
    ? svg`<text x=${x} y="124" text-anchor="middle" class="bed-graphic-label"><tspan
        x=${x}>${p.label}</tspan><tspan x=${x} dy="14">${value(p)}</tspan></text>`
    : svg`<text x=${x} y="128" text-anchor="middle" class="bed-graphic-label">${
        `${p.label ? `${p.label} ` : ""}${value(p)}`}</text>`;

  return svg`
    <svg
      class="bed-graphic bed-graphic-${tone} ${opts.moving ? "is-moving" : ""}"
      viewBox=${opts.stackLabels ? "0 -44 300 190" : "0 -44 300 180"}
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abSingleMattress" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-mattress-stop" offset="0%" stop-opacity="1" />
          <stop class="bed-mattress-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abSingleFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
      </defs>

      <!-- frame + legs -->
      <rect class="bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />
      <rect class="bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abSingleFrame)" />

      <g class="bed-side-layer" fill="url(#abSingleMattress)">
        <!-- foot panel (right of hinge) -->
        <g class="bed-panel ${feedbackClass(opts.lower)}" transform=${lowerT}>
          <rect class="bed-surface" x=${geometry.lowerX} y="58" width=${geometry.lowerWidth} height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel ${feedbackClass(opts.upper)}" transform=${upperT}>
          <rect class="bed-surface" x="42" y="58" width=${geometry.upperWidth} height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
        ${opts.middle ? svg`<g class="bed-panel bed-lumbar-panel ${feedbackClass(opts.middle)}">
          <path class="bed-surface" d=${geometry.middlePath} />
        </g>` : ""}
      </g>

      ${opts.showLabels !== false ? svg`
      ${label(opts.middle ? 80 : 86, opts.upper)}
      ${opts.middle ? label(150, opts.middle) : ""}
      ${label(opts.middle ? 220 : 214, opts.lower)}
      ` : ""}
    </svg>
  `;
}

// Comparison view for paired beds. Both sides share the same hinge so their
// real positions can be compared at a glance. Translucent blue and red
// silhouettes blend to violet wherever their positions coincide.
export function renderDualBedGraphic(
  opts: DualBedGraphicOptions,
): TemplateResult {
  const side = (name: "left" | "right", opts: DualBedGraphicSide): TemplateResult => {
    const geometry = bedGraphicGeometry(opts);
    return svg`
    <g
      class="dual-bed-side dual-bed-side-${name} ${opts.moving ? "is-moving" : ""}"
      fill=${`url(#abDual${name === "left" ? "Left" : "Right"})`}
    >
      <g
        class="dual-bed-panel ${feedbackClass(opts.lower)}"
        transform=${geometry.lowerTransform}
      >
        <rect class="dual-bed-surface" x=${geometry.lowerX} y="58" width=${geometry.lowerWidth} height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel ${feedbackClass(opts.upper)}"
        transform=${geometry.upperTransform}
      >
        <rect class="dual-bed-surface" x="42" y="58" width=${geometry.upperWidth} height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
      ${opts.middle ? svg`<g class="dual-bed-panel bed-lumbar-panel ${feedbackClass(opts.middle)}">
        <path class="dual-bed-surface" d=${geometry.middlePath} />
      </g>` : ""}
    </g>
  `;
  };

  return svg`
    <svg
      class="bed-graphic dual-bed-graphic ${
        opts.left.moving || opts.right.moving ? "is-moving" : ""
      }"
      viewBox="0 -44 300 160"
      role="img"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="abDualFrame" x1="0" y1="0" x2="0" y2="1">
          <stop class="bed-frame-stop" offset="0%" stop-opacity="0.88" />
          <stop class="bed-frame-stop" offset="100%" stop-opacity="0.58" />
        </linearGradient>
        <linearGradient id="abDualLeft" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-left-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-left-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
        <linearGradient id="abDualRight" x1="0" y1="0" x2="0" y2="1">
          <stop class="dual-bed-right-stop" offset="0%" stop-opacity="1" />
          <stop class="dual-bed-right-stop" offset="100%" stop-opacity="0.84" />
        </linearGradient>
      </defs>
      <rect class="dual-bed-frame" x="30" y="78" width="240" height="8" rx="4" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="34" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      <rect class="dual-bed-frame" x="260" y="83" width="6" height="24" rx="3" fill="url(#abDualFrame)" />
      ${side("right", opts.right)}
      ${side("left", opts.left)}
    </svg>
  `;
}
