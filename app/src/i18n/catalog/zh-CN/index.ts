import type { Key } from "../index";
import { errors } from "./errors";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { models } from "./models";
import { player } from "./player";
import { settings } from "./settings";
import { shell } from "./shell";
import { update } from "./update";
import { wizard } from "./wizard";

export const zhCN = { ...errors, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...models, ...player, ...settings, ...shell, ...update, ...wizard } satisfies Record<Key, string>;
