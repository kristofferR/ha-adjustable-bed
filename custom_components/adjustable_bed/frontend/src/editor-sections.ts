import { bedHasGraphicFeedback } from "./bed-graphic-state";
import { hasLightingControls } from "./discovery";
import type { BedEntities, HomeAssistant } from "./types";

export function presentSections(
  bed: BedEntities,
  hass: HomeAssistant,
): Record<string, boolean> {
  return {
    graphic: bedHasGraphicFeedback(bed, hass),
    motors:
      bed.motors.some((motor) => motor.cover || motor.up || motor.down) ||
      !!bed.stop ||
      !!bed.synchro,
    firmness: bed.firmness.length > 0,
    presets: bed.presets.length > 0,
    memory: bed.memory.length > 0,
    lighting: hasLightingControls(bed.lights) || !!bed.lights.state,
    massage:
      bed.massage.buttons.length > 0 ||
      bed.massage.numbers.length > 0 ||
      !!bed.massage.selects?.length ||
      !!bed.massage.timer,
    utility: bed.utility.length > 0,
    climate:
      bed.climate.entities.length > 0 ||
      bed.climate.selects.length > 0 ||
      bed.climate.numbers.length > 0,
    connection: !!(bed.connect || bed.disconnect),
  };
}
