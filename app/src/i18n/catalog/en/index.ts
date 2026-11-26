import { batch } from "./batch";
import { editor } from "./editor";
import { errors } from "./errors";
import { exports } from "./export";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { player } from "./player";
import { settings } from "./settings";
import { shell } from "./shell";
import { summary } from "./summary";
import { update } from "./update";

export const en = { ...batch, ...editor, ...errors, ...exports, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...player, ...settings, ...shell, ...summary, ...update } as const;
