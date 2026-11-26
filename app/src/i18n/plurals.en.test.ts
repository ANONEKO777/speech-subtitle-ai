import { describe, expect, it } from "vitest";
import { type PluralBase, plural } from ".";

type Pin = { readonly args: Readonly<Record<string, string | number>>; readonly one: string; readonly other: string };

/** Every English plural, at 1 and at 2. The Record type makes tsc fail when a plural key has no pin. */
const PINS: Record<PluralBase, Pin> = {
  "hw.missingTitle": { args: { size: "1 GB" }, one: "1 item still missing, 1 GB in total:", other: "2 items still missing, 1 GB in total:" },
  "hw.optionMissing": { args: { size: "1 GB" }, one: "1 item missing, 1 GB to download", other: "2 items missing, 1 GB to download" },
  "download.retries": { args: {}, one: "Retried 1 time", other: "Retried 2 times" },
  "models.summary": {
    args: { size: "1 GB" },
    one: "1 item installed, 1 GB in total. Models and runtimes are downloaded separately from the app. You can delete, verify, repair or download them again here.",
    other: "2 items installed, 1 GB in total. Models and runtimes are downloaded separately from the app. You can delete, verify, repair or download them again here.",
  },
  "storage.confirm.body": {
    args: { size: "1 GB", notInstalled: "Not installed" },
    one: "1 installed model (1 GB) is in the old folder. If you only change the folder, it stays where it is, and the app will show it as “Not installed” in the new folder.",
    other: "2 installed models (1 GB) are in the old folder. If you only change the folder, they stay where they are, and the app will show them as “Not installed” in the new folder.",
  },
  "storage.moving": {
    args: { percent: 50, filesDone: 0, done: "1 MB", total: "2 MB" },
    one: "Moving 50%: 0 / 1 file, 1 MB / 2 MB",
    other: "Moving 50%: 0 / 2 files, 1 MB / 2 MB",
  },
  "storage.moved": {
    args: { size: "2 MB", target: "F:/x" },
    one: "Move complete: 1 file (2 MB) moved to F:/x",
    other: "Move complete: 2 files (2 MB) moved to F:/x",
  },
  "edits.kept": { args: {}, one: "Kept 1 manual edit after re-translating", other: "Kept 2 manual edits after re-translating" },
  "edits.unmatched": {
    args: {},
    one: "1 edit was not applied because its source text changed, and it is still in the edits file in the project folder",
    other: "2 edits were not applied because their source text changed, and they are still in the edits file in the project folder",
  },
  "queue.added": { args: {}, one: "1 item added to the queue", other: "2 items added to the queue" },
  "player.foot.edited": {
    args: {},
    one: "1 subtitle edited. Edits are kept when you translate again.",
    other: "2 subtitles edited. Edits are kept when you translate again.",
  },
  "player.failedNote": {
    args: { parts: "X" },
    one: "1 subtitle failed to translate: X. The model's answers failed the checks several times, for example by mixing in Japanese or having the wrong length.",
    other: "2 subtitles failed to translate: X. The model's answers failed the checks several times, for example by mixing in Japanese or having the wrong length.",
  },
};

const say = plural as (locale: "en", base: PluralBase, n: number, args: Pin["args"]) => string;

describe("English plurals", () => {
  for (const [base, pin] of Object.entries(PINS) as [PluralBase, Pin][]) {
    it(`${base} reads right for one and for two`, () => {
      expect(say("en", base, 1, pin.args)).toBe(pin.one);
      expect(say("en", base, 2, pin.args)).toBe(pin.other);
    });
  }
});
