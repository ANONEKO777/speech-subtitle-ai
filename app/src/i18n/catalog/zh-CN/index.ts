import type { Key } from "../index";
import { settings } from "./settings";

export const zhCN = { ...settings } satisfies Record<Key, string>;
