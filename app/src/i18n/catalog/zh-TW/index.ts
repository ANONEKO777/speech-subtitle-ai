import type { Key } from "../index";
import { settings } from "./settings";

export const zhTW = { ...settings } satisfies Record<Key, string>;
