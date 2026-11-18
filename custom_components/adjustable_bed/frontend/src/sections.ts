// What each card section shows. The card renders a section and the editor
// offers its toggle from these same checks, so the two cannot drift apart.
import { bedHasGraphicFeedback } from "./bed-graphic-state";
import { hasLightingControls } from "./discovery";
import type { AdjustableBedCardConfig, BedEntities, HomeAssistant, MotorEntity } from "./types";

export const motorHasControls = (m: MotorEntity): boolean => !!(m.cover || m.up || m.down);

// A motor without movement controls still shows a row for its position setter.
export const positionOnlyMotors = (bed: BedEntities): MotorEntity[] =>
  bed.motors.filter((m) => m.position && !motorHasControls(m));

export const motorsPresent = (bed: BedEntities): boolean =>
  bed.motors.some(motorHasControls) || positionOnlyMotors(bed).length > 0 ||
  !!bed.synchro || !!bed.controlSide || !!bed.stop;

export const lightingPresent = (bed: BedEntities): boolean =>
  hasLightingControls(bed.lights) || !!bed.lights.state;

export const presetsPresent = (bed: BedEntities): boolean =>
  bed.presets.length + bed.presetSaves.length > 0;

export const massagePresent = ({ massage: m }: BedEntities): boolean =>
  m.buttons.length > 0 || m.numbers.length > 0 || !!m.selects?.length ||
  !!m.switches?.length || !!m.states?.length || !!m.timer;

export const utilityPresent = (bed: BedEntities): boolean =>
  bed.utility.length > 0 || !!bed.utilitySwitches?.length || !!bed.utilityNumbers?.length ||
  !!bed.utilitySelects?.length || !!bed.utilityStates?.length;

export const climateEntities = ({ climate: c }: BedEntities): string[] =>
  [...c.entities, ...c.selects, ...c.numbers];

export function presentSections(
  bed: BedEntities,
  hass: HomeAssistant,
  config?: AdjustableBedCardConfig,
): Record<string, boolean> {
  return {
    graphic: bedHasGraphicFeedback(bed, hass, config?.show_percentage_graphic === true),
    motors: motorsPresent(bed),
    firmness: bed.firmness.length > 0,
    presets: presetsPresent(bed),
    saved_positions: !!bed.savedPositions,
    memory: bed.memory.length > 0,
    lighting: lightingPresent(bed),
    massage: massagePresent(bed),
    utility: utilityPresent(bed),
    climate: climateEntities(bed).length > 0,
    connection: !!(bed.connect || bed.disconnect),
  };
}
