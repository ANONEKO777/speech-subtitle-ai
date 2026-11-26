import type { Key } from "../index";
import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";

export const zhTW = { ...errors, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...settings, ...shell, ...update } satisfies Record<Key, string>;
