import { type Translate, tZhTW } from "../i18n";
import { PROFILE_IDS, type ProfileId } from "./types";

export const profileName = (id: ProfileId, t: Translate): string => t(`profile.name.${id}`);

export const profileBlurb = (id: ProfileId, t: Translate): string => t(`profile.blurb.${id}`);

const inZhTW = (text: (id: ProfileId, t: Translate) => string): Record<ProfileId, string> =>
  Object.fromEntries(PROFILE_IDS.map((id) => [id, text(id, tZhTW)])) as Record<ProfileId, string>;

/** Traditional Chinese, for the wizard until W2 moves it to `profileName`. */
export const PROFILE_NAME = inZhTW(profileName);
export const PROFILE_BLURB = inZhTW(profileBlurb);
