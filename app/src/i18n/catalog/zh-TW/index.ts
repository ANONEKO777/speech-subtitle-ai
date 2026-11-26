import type { Key } from "../index";
import { batch } from "./batch";
import { editor } from "./editor";
import { errors } from "./errors";
import { exports } from "./export";
import { hardware } from "./hardware";
import { importer } from "./importer";
import { languages } from "./languages";
import { licenses } from "./licenses";
import { llm } from "./llm";
import { models } from "./models";
import { player } from "./player";
import { settings } from "./settings";
import { shell } from "./shell";
import { summary } from "./summary";
import { update } from "./update";
import { wizard } from "./wizard";

export const zhTW = { ...batch, ...editor, ...errors, ...exports, ...hardware, ...importer, ...languages, ...licenses, ...llm, ...models, ...player, ...settings, ...shell, ...summary, ...update, ...wizard } satisfies Record<Key, string>;
