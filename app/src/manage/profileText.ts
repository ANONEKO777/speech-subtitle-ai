import type { Translate } from "../i18n";
import type { ProfileId } from "./types";

export const profileName = (id: ProfileId, t: Translate): string => t(`profile.name.${id}`);

export const profileBlurb = (id: ProfileId, t: Translate): string => t(`profile.blurb.${id}`);
