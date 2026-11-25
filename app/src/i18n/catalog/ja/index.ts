import type { Key } from "../index";
import { settings } from "./settings";

export const ja = { ...settings } satisfies Record<Key, string>;
