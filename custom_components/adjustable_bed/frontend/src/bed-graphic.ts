// A refined bed silhouette. Head/feet panels rotate, with an optional separate
// lumbar support section that bows upward according to its own feedback.
// back/legs (or head/feet) feedback. Percentage poses are schematic;
// purely decorative — not interactive.
import { type TemplateResult, svg } from "lit";

export type BedGraphicTone = "theme" | "left" | "right";

export interface BedGraphicPanel {
  label?: string;
  angle?: number; // degrees, 0 = flat
  readout?: string; // original percentage, when angle is only a schematic pose
}

export interface BedGraphicOptions {
  showLabels?: boolean;
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
const clamp = (deg: number): number => Math.max(0, Math.min(75, deg));

/** Schematic geometry: lumbar extension changes only the middle support. */
export function bedGraphicGeometry(opts: BedGraphicOptions) {
  const upperHinge = opts.middle ? 122 : 150;
  const lowerHinge = opts.middle ? 178 : 150;
  const lift = clamp(opts.middle?.angle ?? 0) / 75 * 28;
  return {
    upperTransform: `rotate(${clamp(opts.upper.angle ?? 0)} ${upperHinge} 70)`,
    lowerTransform: `rotate(${-clamp(opts.lower.angle ?? 0)} ${lowerHinge} 70)`,
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

  const fmt = (p: BedGraphicPanel): string => {
    if (p.angle === undefined) return `${p.label ? `${p.label} ` : ""}?`;
    return `${p.label ? `${p.label} ` : ""}${p.readout ?? `${Math.round(clamp(p.angle))}°`}`;
  };

  return svg`
    <svg
      class="bed-graphic bed-graphic-${tone} ${opts.moving ? "is-moving" : ""}"
      viewBox="0 -44 300 180"
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
        <g class="bed-panel" transform=${lowerT}>
          <rect class="bed-surface" x=${geometry.lowerX} y="58" width=${geometry.lowerWidth} height="18" rx="6" />
        </g>

        <!-- head/back panel (left of hinge) with pillow -->
        <g class="bed-panel" transform=${upperT}>
          <rect class="bed-surface" x="42" y="58" width=${geometry.upperWidth} height="18" rx="6" />
          <rect class="bed-surface bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
        </g>
        ${opts.middle ? svg`<g class="bed-panel bed-lumbar-panel" opacity=${opts.middle.angle === undefined ? "0.35" : "1"}>
          <path class="bed-surface" d=${geometry.middlePath} />
        </g>` : ""}
      </g>

      ${opts.showLabels !== false ? svg`
      <text x=${opts.middle ? 80 : 86} y="128" text-anchor="middle" class="bed-graphic-label">${fmt(opts.upper)}</text>
      ${opts.middle ? svg`<text x="150" y="128" text-anchor="middle" class="bed-graphic-label">${fmt(opts.middle)}</text>` : ""}
      <text x=${opts.middle ? 220 : 214} y="128" text-anchor="middle" class="bed-graphic-label">${fmt(opts.lower)}</text>
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
  const leftUpper = clamp(opts.left.upper.angle ?? 0);
  const leftLower = clamp(opts.left.lower.angle ?? 0);
  const rightUpper = clamp(opts.right.upper.angle ?? 0);
  const rightLower = clamp(opts.right.lower.angle ?? 0);

  const side = (
    name: "left" | "right",
    upper: number,
    lower: number,
    moving: boolean,
    middle?: BedGraphicPanel,
  ): TemplateResult => {
    const geometry = bedGraphicGeometry({upper: {angle: upper}, lower: {angle: lower}, middle, moving});
    return svg`
    <g
      class="dual-bed-side dual-bed-side-${name} ${moving ? "is-moving" : ""}"
      fill=${`url(#abDual${name === "left" ? "Left" : "Right"})`}
    >
      <g
        class="dual-bed-panel"
        transform=${geometry.lowerTransform}
      >
        <rect class="dual-bed-surface" x=${geometry.lowerX} y="58" width=${geometry.lowerWidth} height="18" rx="6" />
      </g>
      <g
        class="dual-bed-panel"
        transform=${geometry.upperTransform}
      >
        <rect class="dual-bed-surface" x="42" y="58" width=${geometry.upperWidth} height="18" rx="6" />
        <rect class="dual-bed-surface dual-bed-pillow" x="50" y="49" width="40" height="11" rx="5" />
      </g>
      ${middle ? svg`<g class="dual-bed-panel bed-lumbar-panel" opacity=${middle.angle === undefined ? "0.35" : "1"}>
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
      ${side(
        "right",
        rightUpper,
        rightLower,
        opts.right.moving,
        opts.right.middle,
      )}
      ${side(
        "left",
        leftUpper,
        leftLower,
        opts.left.moving,
        opts.left.middle,
      )}
    </svg>
  `;
}
