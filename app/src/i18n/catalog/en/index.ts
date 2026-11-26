import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";

export const en = { ...errors, ...hardware, ...importer, ...licenses, ...llm, ...settings, ...shell, ...update } as const;
