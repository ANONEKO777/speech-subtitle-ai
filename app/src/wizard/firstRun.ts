export const SKIPPED_KEY = "vst.wizard.skipped";

export interface ModelState {
  readonly kind: string;
  readonly state: string;
}

/**
 * The wizard is for a machine that cannot run the pipeline yet: no speech model or no
 * translation model installed. A person who left the wizard is not asked again.
 */
export function needsWizard(models: readonly ModelState[], skipped: boolean): boolean {
  if (skipped) return false;
  const has = (kind: string) => models.some((m) => m.kind === kind && m.state === "installed");
  return !(has("asr") && has("llm"));
}
