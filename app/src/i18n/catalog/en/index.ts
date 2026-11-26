import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { models } from "./models";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";
import { wizard } from "./wizard";

export const en = { ...errors, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...models, ...settings, ...shell, ...update, ...wizard } as const;
