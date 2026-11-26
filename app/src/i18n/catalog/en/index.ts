import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { player } from "./player";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";

export const en = { ...errors, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...player, ...settings, ...shell, ...update } as const;
