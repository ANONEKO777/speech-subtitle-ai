import type { Key } from "../index";
import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";

export const ja = { ...errors, ...hardware, ...importer, ...licenses, ...llm, ...settings, ...shell, ...update } satisfies Record<Key, string>;
